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
# SEGURIDAD DEL DATO — POR QUÉ SE RECHAZAN COSAS:
#   Cada movimiento en pesos guarda su equivalente en USD (monto_usd) calculado
#   con la cotización de ESE momento, y ese número queda congelado en la fila.
#   Una cotización falsa (0, negativa, NaN, infinita, absurda) escribiría un
#   monto_usd falso PARA SIEMPRE, y después no se distingue de uno bueno.
#   app.py ya se niega a convertir con una cotización inservible
#   (_calcular_monto_usd, el ÚLTIMO resguardo); acá se blinda el ORIGEN: lo que
#   no sirve no entra nunca a config.json.
#
#   Se RECHAZA, y NO se toca cotizacion_valor ni cotizacion_fecha:
#     1. Un valor que no sea un número finito, mayor que 0 y menor que
#        COTIZACION_MAXIMA: 0, negativos, NaN, infinito, booleanos, texto que no
#        es un número, ausente.
#     2. Un salto de más de ±SALTO_MAXIMO (50%) contra el último valor ACEPTADO
#        (cotizacion_valor de config.json). Exactamente ±50% se acepta.
#        EXCEPCIÓN DE ARRANQUE: si nunca hubo una actualización exitosa
#        (cotizacion_fecha vacía: el 1500.0 de DEFAULTS es solo un bootstrap) o
#        el valor anterior no sirve, el primer valor válido entra sin este control.
#     3. Una respuesta de más de MAX_RESPUESTA_BYTES (5 MB).
#   Una falla de conexión (timeout, error HTTP, JSON roto) tampoco toca el valor.
#   En TODOS esos casos solo se escribe cotizacion_ultimo_intento y
#   cotizacion_ok=False, y refrescar_cache devuelve (False, mensaje) con el
#   motivo en español simple (lo loguea el scheduler y lo muestra Settings).
#
#   SI HAY UNA DEVALUACIÓN REAL DE MÁS DEL 50%: el control la va a rechazar. Se
#   destraba a mano, editando cotizacion_valor en config.json (se lee en
#   caliente, no hace falta reiniciar) con un valor cercano al real; el próximo
#   refresh (o el botón de Settings) ya compara contra ese.
#
# ESTRATEGIA DE FALLBACK:
#   Si la API cae o trae algo que no se acepta, la app no crashea: se mantiene el
#   último valor aceptado y se marca cotizacion_ok=False junto a la fecha del
#   último intento. refrescar_cache NUNCA levanta una excepción hacia afuera
#   (tampoco si config.json está ilegible: ahí devuelve (False, mensaje) sin
#   escribir nada).
#
# DEPENDENCIAS:
#   Solo librerías estándar (urllib.request, json, decimal). No se agrega nada al
#   requirements.txt.
#
# =============================================================================

import http.client
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from decimal import Decimal


# =============================================================================
# CONSTANTES DE CONFIGURACIÓN DE LAS APIs
# =============================================================================

URL_COTIZACION_ACTUAL     = 'https://dolarapi.com/v1/dolares/oficial'
URL_COTIZACIONES_HISTORICAS = 'https://api.argentinadatos.com/v1/cotizaciones/dolares/oficial'
USER_AGENT                = 'Gastos-Casa/1.0'
TIMEOUT_SEGUNDOS          = 5
MAX_DIAS_RETROCESO        = 10

# Blindaje del dato (ver "SEGURIDAD DEL DATO" arriba).
MAX_RESPUESTA_BYTES = 5 * 1024 * 1024   # lo máximo que se lee de una respuesta (5 MB)
COTIZACION_MAXIMA   = 10_000_000        # tope de cordura: un valor válido es MENOR que esto
SALTO_MAXIMO        = 0.5               # ±50% contra el último valor aceptado

# Cache en memoria del dict histórico, para no bajarlo varias veces por run.
_cache_historicas = None


# =============================================================================
# EXCEPCIONES
# =============================================================================

class CotizacionRechazada(ValueError):
    """
    La API CONTESTÓ, pero lo que trajo no se acepta (valor inválido, formato
    inesperado o un salto de más de ±50%). `str(e)` es el mensaje listo para
    mostrar: empieza con "Cotización rechazada:".

    Es un ValueError a propósito: es lo que ya levantaba esta función cuando
    faltaba la clave 'venta', y quien la atrapaba como ValueError sigue andando.
    `cierre` es la última frase del mensaje (por defecto, qué pasó con el valor).
    """

    def __init__(self, detalle, cierre='Se mantiene la cotización anterior.'):
        super().__init__(f"Cotización rechazada: {detalle} {cierre}".rstrip())


class RespuestaDemasiadoGrande(ValueError):
    """La respuesta de la API pasa de MAX_RESPUESTA_BYTES. No se usa nada de ella."""


# =============================================================================
# FUNCIÓN: _http_get_json(url)
# Propósito: Hace un GET HTTP y parsea la respuesta como JSON.
# =============================================================================
#
# Wrapper fino sobre urllib.request que:
#   - Setea el User-Agent "Gastos-Casa/1.0".
#   - Aplica un timeout de 5 segundos.
#   - Lee COMO MUCHO MAX_RESPUESTA_BYTES (5 MB): se piden UN byte de más y, si
#     ese byte llega, la respuesta se pasó del tope y se levanta
#     RespuestaDemasiadoGrande. Así una API rota (o alguien en el medio) no puede
#     llenar la memoria del servicio.
#   - Decodifica utf-8 y parsea el JSON.
#   - Propaga las excepciones (URLError, HTTPError, json.JSONDecodeError, etc.)
#     para que el que llama decida cómo manejarlas.
#
def _http_get_json(url):
    request_obj = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request_obj, timeout=TIMEOUT_SEGUNDOS) as resp:
        crudo = resp.read(MAX_RESPUESTA_BYTES + 1)
    if len(crudo) > MAX_RESPUESTA_BYTES:
        host = urllib.parse.urlsplit(url).hostname or url
        raise RespuestaDemasiadoGrande(
            f"la respuesta de {host} pesa más de {MAX_RESPUESTA_BYTES // (1024 * 1024)} MB")
    return json.loads(crudo.decode('utf-8'))


# =============================================================================
# VALIDACIÓN DEL DATO QUE VIENE DE AFUERA
# =============================================================================
#
# Todo lo que trae la API es dato no confiable: se valida ANTES de que toque
# config.json. Estos helpers son puros (no leen ni escriben nada).

_RE_FECHA = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}')  # [0-9] y no \d: \d acepta dígitos de otros alfabetos
_MAXIMA_TEXTO = f"{COTIZACION_MAXIMA:,}".replace(',', '.')   # "10.000.000", para los mensajes


def _valor_valido(crudo):
    """
    Devuelve `crudo` como float si es una cotización creíble, o None si no.

    Creíble = un número (o un texto que sea un número, como se aceptaba antes)
    FINITO, mayor que 0 y menor que COTIZACION_MAXIMA. No sirven: 0, negativos,
    NaN, infinito (json.loads de Python los acepta como literales NaN/Infinity),
    booleanos (float(True) es 1.0), texto que no es un número, None, listas.

    El orden importa: `nan <= 0` es False, así que el isfinite va ANTES del
    `<= 0`. Un entero gigante (10**400) hace que float() levante OverflowError.
    """
    if isinstance(crudo, bool):
        return None
    try:
        valor = float(crudo)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(valor) or valor <= 0 or valor >= COTIZACION_MAXIMA:
        return None
    return valor


def _fecha_valida(crudo):
    """
    'YYYY-MM-DD' si `crudo` EMPIEZA con una fecha real (acepta el ISO 8601 con
    hora que manda dolarapi, '2026-04-18T15:30:00.000Z', y se queda con el día);
    None si no. Lo que se devuelve son siempre 10 caracteres ASCII de una fecha
    de calendario válida: nunca texto de la API, que va a config.json y de ahí a
    las pantallas.

    Una fecha FUTURA también da None (el que llama usa la de hoy). Una
    `fechaActualizacion` de 2099 dejaría el indicador "Al día" de Settings
    prendido para siempre. Y hay un caso legítimo que cae acá: dolarapi manda
    la hora en UTC, así que después de las 21 h de Argentina el día UTC ya es
    "mañana"; para la app ese valor es de HOY.
    """
    if not isinstance(crudo, str):
        return None
    candidata = crudo[:10]
    if not _RE_FECHA.fullmatch(candidata):
        return None
    try:
        dia = datetime.strptime(candidata, '%Y-%m-%d')  # descarta 2026-13-45, 2026-02-30, año 0000
    except ValueError:
        return None
    if dia.date() > datetime.now().date():
        return None
    return candidata


def _exigir_valor(crudo):
    """`crudo` como float, o CotizacionRechazada (con el mensaje para mostrar) si no sirve."""
    valor = _valor_valido(crudo)
    if valor is None:
        raise CotizacionRechazada(
            f"dolarapi.com dio un valor inválido ({_mostrar(crudo)}): tiene que ser "
            f"un número mayor que 0 y menor que {_MAXIMA_TEXTO}.")
    return valor


def _acotar(texto, limite=60):
    """`texto` recortado a `limite` caracteres. Lo que viene de afuera va al log y a Settings."""
    texto = str(texto)
    return texto if len(texto) <= limite else texto[:limite - 3] + '...'


def _mostrar(valor):
    """`valor` tal como vino (con su tipo: 'abc' lleva comillas, True no), acotado."""
    try:
        return _acotar(repr(valor), 40)
    except Exception:
        return '(ilegible)'


# =============================================================================
# CONTROL DEL SALTO (±50% contra el último valor aceptado)
# =============================================================================

def _salto_excesivo(nuevo, anterior):
    """
    True si `nuevo` se aleja de `anterior` MÁS de SALTO_MAXIMO (exactamente ±50%
    se acepta).

    La cuenta va en Decimal, sobre el texto más corto de cada float (repr, que es
    lo que se escribió en el JSON). Con floats, un +50% exacto de valores no
    redondos se rechazaría por error: abs(2429.76 - 1619.84) / 1619.84 da
    0.5000000000000001 y 2429.76 ES exactamente 1619.84 más el 50%.
    """
    n, a = Decimal(repr(nuevo)), Decimal(repr(anterior))
    return abs(n - a) > a * Decimal(repr(SALTO_MAXIMO))


def _porcentaje(nuevo, anterior):
    """
    El cambio de `nuevo` contra `anterior` como texto con signo ('+60.0%').
    Usa los decimales justos para que el número mostrado SE VEA pasado del tope:
    en el borde (+50.001%) agrega decimales hasta que no diga "+50.0%" y "más
    del ±50%" en la misma frase.
    """
    pct = (nuevo - anterior) / anterior * 100
    for decimales in (1, 2, 3, 4, 6):
        texto = f"{pct:+.{decimales}f}"
        if abs(float(texto)) > SALTO_MAXIMO * 100:
            break
    return texto + '%'


def _controlar_salto(nuevo, cfg):
    """
    Levanta CotizacionRechazada si `nuevo` se pasa del ±SALTO_MAXIMO contra el
    último valor aceptado (`cfg['cotizacion_valor']`). `cfg` es la config actual.

    No controla (deja pasar) en el ARRANQUE, y es lo único que lo saltea:
      - cotizacion_fecha vacía: nunca hubo una actualización exitosa y el
        1500.0 de DEFAULTS es solo un bootstrap, no un valor que haya que
        defender.
      - el valor anterior no sirve (0, basura, fuera del tope): no hay contra qué
        comparar, y el primer valor válido lo repara solo.
    """
    if not cfg.get('cotizacion_fecha'):
        return
    anterior = _valor_valido(cfg.get('cotizacion_valor'))
    if anterior is None:
        return
    if _salto_excesivo(nuevo, anterior):
        raise CotizacionRechazada(
            f"dolarapi.com dio AR$ {nuevo:.2f}, un cambio de {_porcentaje(nuevo, anterior)} "
            f"respecto de AR$ {anterior:.2f} (más del ±{SALTO_MAXIMO:.0%}).",
            cierre="Si el salto es real, actualizá cotizacion_valor a mano en config.json.")


# =============================================================================
# FUNCIÓN: obtener_cotizacion_actual()
# Propósito: Consulta dolarapi.com y retorna el valor de venta oficial actual.
# =============================================================================
#
# Retorna: dict con {'valor': float, 'fecha': 'YYYY-MM-DD'}. El valor ya está
#          validado (finito, > 0, < COTIZACION_MAXIMA) y la fecha es siempre una
#          fecha real: la de la API si venía bien, y si no la de hoy.
# Levanta: CotizacionRechazada (un ValueError) si la API contestó algo que no se
#          acepta: no es un objeto, falta 'venta' o el valor no sirve. Cualquier
#          otra excepción (red, HTTP, JSON, tamaño) se propaga tal cual.
#
# El control del salto de ±50% NO está acá: necesita el valor anterior, que vive
# en config.json, y lo hace refrescar_cache.
#
def obtener_cotizacion_actual():
    """Obtiene la cotización oficial actual (dolarapi.com) y la retorna como dict."""
    datos = _http_get_json(URL_COTIZACION_ACTUAL)

    if not isinstance(datos, dict):
        raise CotizacionRechazada(
            "la respuesta de dolarapi.com no tiene el formato esperado (un objeto con 'venta').")

    if 'venta' not in datos:
        raise CotizacionRechazada("la respuesta de dolarapi.com no trae el campo 'venta'.")

    valor = _exigir_valor(datos['venta'])

    # fechaActualizacion viene en formato ISO 8601 (ej: 2024-06-12T15:40:00.000Z).
    # Nos quedamos solo con la parte de la fecha (YYYY-MM-DD) y solo si es una
    # fecha real. Si falta o no sirve, usamos hoy.
    fecha = _fecha_valida(datos.get('fechaActualizacion')) or datetime.now().strftime('%Y-%m-%d')

    return {'valor': valor, 'fecha': fecha}


# =============================================================================
# FUNCIÓN: obtener_cotizaciones_historicas()
# Propósito: Consulta argentinadatos.com y retorna un dict {fecha: valor}.
# =============================================================================
#
# Retorna: dict con todas las cotizaciones históricas en formato
#          {'YYYY-MM-DD': valor_float}. Se cachea en memoria en el módulo.
#          Las entradas basura (no son un objeto, fecha que no es una fecha real,
#          valor que no cumple las reglas de _valor_valido) se IGNORAN: una fila
#          rota no tira abajo todo el histórico. Un resultado vacío también se
#          cachea; para reintentar, forzar_refresh=True.
#          OJO: acá NO rige el ±50%, porque entre un día y otro del histórico
#          hubo saltos reales de más de eso (la devaluación de diciembre 2023).
# Levanta: cualquier excepción de la API, y ValueError si la raíz no es una lista.
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
        if not isinstance(item, dict):
            continue
        # Normalizamos la fecha al formato YYYY-MM-DD (ya viene así, pero por las dudas)
        fecha = _fecha_valida(item.get('fecha'))
        venta = _valor_valido(item.get('venta'))
        if fecha is None or venta is None:
            continue
        historicas[fecha] = venta

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
#   1. Llama a dolarapi.com (obtener_cotizacion_actual: valida valor y fecha) y
#      vuelve a validar el resultado: segundo control, ya en la puerta de
#      config.json, que no depende de que el origen haya validado bien.
#   2. Controla el salto de ±50% contra el cotizacion_valor actual
#      (_controlar_salto; con la excepción de arranque).
#   3. Si todo está bien: escribe cotizacion_valor, cotizacion_fecha,
#      cotizacion_ultimo_intento (ahora) y cotizacion_ok=True.
#   4. Si algo falla o se rechaza: SOLO escribe cotizacion_ultimo_intento y
#      cotizacion_ok=False. El valor y la fecha anteriores quedan intactos.
#
# Retorna: tupla (ok: bool, mensaje: str). NUNCA levanta: si config.json está
#          ilegible (config.ConfigIlegible) no se escribe nada y se devuelve
#          (False, mensaje) diciendo que hay que arreglarlo a mano.
#
# Los mensajes de un rechazo empiezan con "Cotización rechazada:" (la API
# contestó pero no se acepta) y los de una falla con "No se pudo actualizar la
# cotización:" (red, HTTP, JSON, tamaño, escritura).
#
def refrescar_cache(config_path):
    """Refresca la cotización actual desde la API y actualiza config.json."""
    # Import diferido para evitar importación circular con app.py / config.py.
    import config as _cfg_mod

    ahora_iso = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 1) Traer el valor y revisarlo. La config se lee DESPUÉS de la llamada a la
    #    API: si alguien destraba a mano mientras tanto, se compara con lo nuevo.
    try:
        resultado = obtener_cotizacion_actual()
        # SEGUNDO control, ya en la puerta de config.json. Lo que se escribe no
        # puede depender de que el origen haya validado bien (si la fuente cambia
        # o se refactoriza, esto sigue en pie), y en el arranque no hay ±50% que
        # frene a un NaN o a un 0. Con un resultado sano no cambia nada.
        valor = _exigir_valor(resultado['valor'])
        fecha = _fecha_valida(resultado['fecha']) or datetime.now().strftime('%Y-%m-%d')
        _controlar_salto(valor, _cfg_mod.cargar_config(config_path))
    except CotizacionRechazada as e:
        return _registrar_fallo(_cfg_mod, config_path, ahora_iso, str(e))
    except Exception as e:
        return _registrar_fallo(
            _cfg_mod, config_path, ahora_iso,
            f"No se pudo actualizar la cotización: {_explicar(e)}. "
            f"Se mantiene la cotización anterior.")

    # 2) Guardarlo. Es una fase aparte a propósito: un PermissionError al escribir
    #    no es "falta de conexión con dolarapi.com".
    try:
        _cfg_mod.guardar_config({
            'cotizacion_valor':          valor,
            'cotizacion_fecha':          fecha,
            'cotizacion_ultimo_intento': ahora_iso,
            'cotizacion_ok':             True,
        }, config_path)
    except _cfg_mod.ConfigIlegible as e:
        # No se escribió nada (ni siquiera el intento): ya sabemos que el
        # archivo no se puede tocar, y reintentar solo repetiría el AVISO.
        return False, (f"No se pudo actualizar la cotización: {_acotar(e, 200)}. "
                       f"No se escribió nada: arreglá config.json a mano "
                       f"(el log dice en qué línea) y probá de nuevo.")
    except Exception as e:
        return _registrar_fallo(
            _cfg_mod, config_path, ahora_iso,
            f"No se pudo guardar la cotización en config.json "
            f"({type(e).__name__}: {_acotar(e, 120)}). Se mantiene la cotización anterior.")

    return True, f"Cotización actualizada: 1 USD = AR$ {valor:.2f} ({fecha})"


def _registrar_fallo(cfg_mod, config_path, ahora_iso, mensaje):
    """
    Anota un intento que no se pudo aplicar, SIN tocar cotizacion_valor ni
    cotizacion_fecha: solo cotizacion_ultimo_intento y cotizacion_ok=False.
    Devuelve (False, mensaje). Si ni eso se puede escribir, lo agrega al mensaje
    en vez de levantar.
    """
    try:
        cfg_mod.guardar_config({
            'cotizacion_ultimo_intento': ahora_iso,
            'cotizacion_ok':             False,
        }, config_path)
    except cfg_mod.ConfigIlegible:
        mensaje += (" Además, config.json está ilegible y no se escribió nada: "
                    "arreglalo a mano (el log dice en qué línea).")
    except Exception as e:
        mensaje += (f" Además, no se pudo anotar el intento en config.json "
                    f"({type(e).__name__}: {_acotar(e, 120)}).")
    return False, mensaje


def _explicar(e):
    """Una falla al pedir la cotización (red, HTTP, formato, tamaño), en español simple."""
    if isinstance(e, urllib.error.HTTPError):  # va antes que URLError: es su subclase
        return f"dolarapi.com respondió con error HTTP {e.code}"
    if isinstance(e, (urllib.error.URLError, OSError, http.client.HTTPException)):
        # OSError cubre el timeout y los cortes de conexión; URLError trae el motivo en .reason.
        return f"no hubo conexión con dolarapi.com ({_acotar(getattr(e, 'reason', e))})"
    if isinstance(e, RespuestaDemasiadoGrande):
        return str(e)
    if isinstance(e, ValueError):  # JSONDecodeError, UnicodeDecodeError
        return f"la respuesta de dolarapi.com no es un JSON válido ({_acotar(e)})"
    return f"{type(e).__name__}: {_acotar(e, 120)}"
