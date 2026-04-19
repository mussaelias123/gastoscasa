# =============================================================================
# ARCHIVO: cotizacion.py
# =============================================================================
#
# QUÉ ES ESTE ARCHIVO:
#   Módulo responsable de obtener la cotización del dólar oficial desde APIs
#   públicas. Sostiene el cacheo en config.json y la lógica de consulta histórica
#   usada por el script de backfill.
#
# FUENTES DE DATOS:
#   - Cotización actual: https://dolarapi.com/v1/dolares/oficial
#         Retorna un JSON con {compra, venta, casa, nombre, fechaActualizacion}.
#         Se usa el campo "venta".
#   - Cotizaciones históricas: https://api.argentinadatos.com/v1/cotizaciones/dolares/oficial
#         Retorna una lista completa con {fecha, compra, venta, casa}.
#         Se usa para el backfill de movimientos ya cargados.
#
# ESTRATEGIA DE FALLBACK:
#   Si la API cae al refrescar, la app no crashea: se mantiene el último valor
#   cacheado y se marca cotizacion_ok=False junto a la fecha del último intento.
#
# DEPENDENCIAS:
#   Solo librerías estándar (urllib.request, json). No se agrega nada al
#   requirements.txt.
#
# =============================================================================

import json
import urllib.request
from datetime import datetime, timedelta


# =============================================================================
# CONSTANTES DE CONFIGURACIÓN DE LAS APIs
# =============================================================================

URL_COTIZACION_ACTUAL     = 'https://dolarapi.com/v1/dolares/oficial'
URL_COTIZACIONES_HISTORICAS = 'https://api.argentinadatos.com/v1/cotizaciones/dolares/oficial'
USER_AGENT                = 'Gastos-Casa/1.0'
TIMEOUT_SEGUNDOS          = 5
MAX_DIAS_RETROCESO        = 10

# Cache en memoria del dict histórico, para no bajarlo varias veces por run.
_cache_historicas = None


# =============================================================================
# FUNCIÓN: _http_get_json(url)
# Propósito: Hace un GET HTTP y parsea la respuesta como JSON.
# =============================================================================
#
# Wrapper fino sobre urllib.request que:
#   - Setea el User-Agent "Gastos-Casa/1.0".
#   - Aplica un timeout de 5 segundos.
#   - Decodifica utf-8 y parsea el JSON.
#   - Propaga las excepciones (URLError, HTTPError, json.JSONDecodeError, etc.)
#     para que el que llama decida cómo manejarlas.
#
def _http_get_json(url):
    request_obj = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request_obj, timeout=TIMEOUT_SEGUNDOS) as resp:
        datos = resp.read().decode('utf-8')
    return json.loads(datos)


# =============================================================================
# FUNCIÓN: obtener_cotizacion_actual()
# Propósito: Consulta dolarapi.com y retorna el valor de venta oficial actual.
# =============================================================================
#
# Retorna: dict con {'valor': float, 'fecha': 'YYYY-MM-DD'}.
# Levanta: cualquier excepción de la API (red, HTTP, JSON, clave faltante).
#
def obtener_cotizacion_actual():
    """Obtiene la cotización oficial actual (dolarapi.com) y la retorna como dict."""
    datos = _http_get_json(URL_COTIZACION_ACTUAL)

    if 'venta' not in datos:
        raise ValueError("La respuesta de dolarapi.com no contiene 'venta'.")

    valor = float(datos['venta'])

    # fechaActualizacion viene en formato ISO 8601 (ej: 2024-06-12T15:40:00.000Z).
    # Nos quedamos solo con la parte de la fecha (YYYY-MM-DD). Si no está, usamos hoy.
    fecha_iso = datos.get('fechaActualizacion') or ''
    if fecha_iso:
        fecha = fecha_iso[:10]
    else:
        fecha = datetime.now().strftime('%Y-%m-%d')

    return {'valor': valor, 'fecha': fecha}


# =============================================================================
# FUNCIÓN: obtener_cotizaciones_historicas()
# Propósito: Consulta argentinadatos.com y retorna un dict {fecha: valor}.
# =============================================================================
#
# Retorna: dict con todas las cotizaciones históricas en formato
#          {'YYYY-MM-DD': valor_float}. Se cachea en memoria en el módulo.
# Levanta: cualquier excepción de la API.
#
def obtener_cotizaciones_historicas(forzar_refresh=False):
    """Descarga la lista histórica completa y la convierte a dict {fecha: valor}."""
    global _cache_historicas

    if _cache_historicas is not None and not forzar_refresh:
        return _cache_historicas

    lista = _http_get_json(URL_COTIZACIONES_HISTORICAS)

    if not isinstance(lista, list):
        raise ValueError("argentinadatos.com no retornó una lista.")

    historicas = {}
    for item in lista:
        fecha = item.get('fecha')
        venta = item.get('venta')
        if fecha and venta is not None:
            # Normalizamos la fecha al formato YYYY-MM-DD (ya viene así, pero por las dudas)
            historicas[str(fecha)[:10]] = float(venta)

    _cache_historicas = historicas
    return historicas


# =============================================================================
# FUNCIÓN: cotizacion_para_fecha(fecha, historicas)
# Propósito: Retorna el valor de la cotización para una fecha específica.
# =============================================================================
#
# Si la fecha exacta no está en el dict (feriados, fines de semana), retrocede
# día por día hasta encontrar una cotización válida. Máximo 10 días atrás.
#
# Retorna: float con el valor, o None si no se encuentra en el rango permitido.
#
def cotizacion_para_fecha(fecha, historicas):
    """Devuelve la cotización para 'fecha' (YYYY-MM-DD). Retrocede hasta 10 días."""
    if isinstance(fecha, str):
        fecha_dt = datetime.strptime(fecha[:10], '%Y-%m-%d')
    else:
        # Si viene como date/datetime, la convertimos a datetime.
        fecha_dt = datetime(fecha.year, fecha.month, fecha.day)

    for delta in range(MAX_DIAS_RETROCESO + 1):
        candidata = (fecha_dt - timedelta(days=delta)).strftime('%Y-%m-%d')
        if candidata in historicas:
            return historicas[candidata]

    return None


# =============================================================================
# FUNCIÓN: refrescar_cache(config_path)
# Propósito: Obtiene la cotización actual y la persiste en config.json.
# =============================================================================
#
# Flujo:
#   1. Intenta llamar a dolarapi.com.
#   2. Si OK:     escribe cotizacion_valor, cotizacion_fecha,
#                 cotizacion_ultimo_intento (ahora) y cotizacion_ok=True.
#   3. Si falla:  solo escribe cotizacion_ultimo_intento y cotizacion_ok=False.
#                 El valor anterior permanece intacto (fallback).
#
# Retorna: tupla (ok: bool, mensaje: str).
#
def refrescar_cache(config_path):
    """Refresca la cotización actual desde la API y actualiza config.json."""
    # Import diferido para evitar importación circular con app.py / config.py.
    import config as _cfg_mod

    ahora_iso = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        resultado = obtener_cotizacion_actual()
        _cfg_mod.guardar_config({
            'cotizacion_valor':          resultado['valor'],
            'cotizacion_fecha':          resultado['fecha'],
            'cotizacion_ultimo_intento': ahora_iso,
            'cotizacion_ok':             True,
        }, config_path)
        mensaje = f"Cotización actualizada: 1 USD = AR$ {resultado['valor']:.2f} ({resultado['fecha']})"
        return True, mensaje

    except Exception as e:
        # Fallback: dejamos el valor anterior intacto, solo marcamos el intento.
        _cfg_mod.guardar_config({
            'cotizacion_ultimo_intento': ahora_iso,
            'cotizacion_ok':             False,
        }, config_path)
        return False, f"No se pudo actualizar la cotización: {e}"
