# =============================================================================
# ARCHIVO: app.py
# =============================================================================
#
# QUÉ ES ESTE ARCHIVO:
#   Es el BACKEND principal. Es el "servidor web" de nuestra aplicación.
#   Define qué URLs existen, qué hacer cuando el navegador las pide,
#   y qué respuesta enviar de vuelta.
#
# MODELO DE NEGOCIO:
#   2 personas: Elías y Mari
#   2 monedas:  AR$ (pesos) y USD (dólares)
#   4 saldos:   elias_ars, elias_usd, mari_ars, mari_usd
#   Los saldos se calculan dinámicamente sumando ingresos y restando gastos.
#
# MODOS DE EJECUCIÓN:
#   - Normal/Dev:  python app.py   (lo levanta también NSSM en producción)
#   - Servicio:    NSSM envuelve `python app.py` (no hay comandos de servicio
#                  propios; ver docs/CONTEXT_DEPLOY.md).
#
# CÓMO CORRER ESTE PROGRAMA:
#   1. Abrir terminal en la carpeta gastos-casa/
#   2. pip install -r requirements.txt  (solo la primera vez)
#   3. python app.py
#   4. Abrir Chrome en http://localhost:5000
#   5. Para detenerlo: Ctrl+C
#
# =============================================================================

import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
import threading
import time
from datetime import datetime, timedelta, date

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

# -----------------------------------------------------------------------------
# Carpeta base del proyecto: templates/ y static/ viven junto a este .py.
# -----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

import re as _re
from flask import (Flask, render_template, request, redirect, url_for, jsonify,
                   flash, Response)
import database
import config
import cotizacion
import psutil
from logutil import log


# =============================================================================
# METADATA DE LA PALETA — usada por la página Settings para renderizar las tablas
# =============================================================================
# Orden y textos siguen la tabla de docs/CONTEXT_FRONTEND.md.
# Las claves coinciden con las de cfg.paleta_light / cfg.paleta_dark.
PALETA_META = [
    ("acento",         "Acento",            "Botones primarios, links, focus ring"),
    ("acento-oscuro",  "Acento oscuro",     "Hover de botones, fondo nav"),
    ("fondo",          "Fondo",             "Fondo general"),
    ("superficie",     "Superficie",        "Tarjetas, inputs, modales"),
    ("texto",          "Texto",             "Texto principal"),
    ("texto-muted",    "Texto muted",       "Texto secundario"),
    ("texto-invertido","Texto invertido",   "Texto sobre botones de color (acento, peligro, éxito)"),
    ("borde",          "Borde",             "Bordes, separadores"),
    ("exito",          "Éxito",             "Ingresos, OK, semáforo verde"),
    ("alerta",         "Alerta",            "Pendiente, advertencia"),
    ("peligro",        "Peligro",           "Eliminar, error, saldo negativo"),
    ("exito-suave",    "Éxito suave",       "Fondo badge OK"),
    ("alerta-suave",   "Alerta suave",      "Fondo badge alerta"),
    ("peligro-suave",  "Peligro suave",     "Fondo badge error"),
    ("persona-elias",  "Persona — Elías",   "Identificador visual Elías"),
    ("persona-mari",   "Persona — Mari",    "Identificador visual Mari"),
    ("persona-leon",   "Persona — León",    "Identificador visual León (rutina, lactancia)"),
    ("moneda-ars",     "Moneda — AR$",      "Badge AR$, gauge total ARS"),
    ("moneda-usd",     "Moneda — USD",      "Badge USD, gauge total USD"),
    ("deco-1",         "Deco 1",            "Barra de título (header)"),
    ("deco-2",         "Deco 2",            "Barra de navegación"),
    ("deco-3",         "Deco 3",            "Separadores, iconos secundarios"),
    ("deco-4",         "Deco 4",            "Hover backgrounds, divisores ligeros"),
]

_HEX_RE = _re.compile(r'^#[0-9a-fA-F]{6}$')


# =============================================================================
# MÓDULO CALENDARIO — constantes y helpers de fecha/estado
# Propósito: tareas del hogar recurrentes (actividades). La capa de datos pura
# vive en database.py (tablas actividades / actividades_historial); acá vive
# el cálculo de próxima fecha y estado (vencida/próxima/al día), a propósito
# fuera de database.py (ver docs/CONTEXT_DB.md).
# =============================================================================

CAL_AREAS = {
    'auto':       ('Auto',       '🚗'),
    'casa':       ('Casa',       '🏠'),
    'salud':      ('Salud',      '🩺'),
    'documentos': ('Documentos', '📄'),
    'mascotas':   ('Mascotas',   '🐾'),
    'finanzas':   ('Finanzas',   '💳'),
    'hogar':      ('Hogar',      '🔧'),
}
CAL_RESPONSABLES = {'familia': 'Familia', 'elias': 'Elías', 'mari': 'Mari'}
CAL_UNIDADES = ('dias', 'semanas', 'meses', 'anios')


def _act_sumar_intervalo(fecha, n, unidad):
    """Suma n unidades (dias|semanas|meses|anios) a una fecha `date`.

    Para meses/años: si el día no existe en el mes destino, clampea al
    último día de ese mes (ej. 31-ene +1 mes → 28/29-feb)."""
    import calendar

    if unidad == 'dias':
        return fecha + timedelta(days=n)
    if unidad == 'semanas':
        return fecha + timedelta(weeks=n)

    if unidad == 'meses':
        total_meses = (fecha.month - 1) + n
        anio  = fecha.year + total_meses // 12
        mes   = total_meses % 12 + 1
    elif unidad == 'anios':
        anio = fecha.year + n
        mes  = fecha.month
    else:
        raise ValueError(f"Unidad de intervalo inválida: {unidad}")

    ultimo_dia = calendar.monthrange(anio, mes)[1]
    dia = min(fecha.day, ultimo_dia)
    return fecha.replace(year=anio, month=mes, day=dia)


def _act_proxima_fecha(act):
    """Calcula la próxima fecha (date) de una actividad, o None si no aplica.

    Prioridad:
      1. proxima_manual → esa fecha (fija, para únicas o override manual).
      2. recurrente y ultima → ultima + intervalo.
      3. ultima (no recurrente, sin próxima manual) → esa fecha.
      4. Ninguno de los anteriores → None.
    """
    proxima_manual = act.get('proxima_manual')
    if proxima_manual:
        return datetime.strptime(str(proxima_manual), '%Y-%m-%d').date()

    ultima = act.get('ultima')
    if act.get('recurrente') and ultima:
        fecha_ultima = datetime.strptime(str(ultima), '%Y-%m-%d').date()
        n = act.get('intervalo_n')
        u = act.get('intervalo_u')
        if n and u:
            return _act_sumar_intervalo(fecha_ultima, int(n), u)
        return fecha_ultima

    if ultima:
        return datetime.strptime(str(ultima), '%Y-%m-%d').date()

    return None


def _act_estado(act):
    """Estado de una actividad: 'terminada' | 'vencida' | 'proxima' | 'aldia'."""
    from datetime import date

    if act.get('terminada'):
        return 'terminada'

    proxima = _act_proxima_fecha(act)
    if proxima is None:
        return 'aldia'

    dias = (proxima - date.today()).days
    if dias < 0:
        return 'vencida'
    if act.get('avisar') and dias <= int(act.get('lead_dias') or 0):
        return 'proxima'
    return 'aldia'


def _act_enriquecer(row):
    """Convierte una fila de `actividades` en dict serializable JSON,
    agregando proxima_fecha (ISO|None), estado y dias_restantes (int|None)."""
    from datetime import date

    act = dict(row)
    proxima = _act_proxima_fecha(act)
    dias_restantes = (proxima - date.today()).days if proxima is not None else None

    act['proxima_fecha']  = proxima.isoformat() if proxima is not None else None
    act['estado']         = _act_estado(act)
    act['dias_restantes'] = dias_restantes
    return act


def _act_payload():
    """Payload completo del módulo Calendario: actividades enriquecidas + historial.

    Usado por GET /api/actividades y por TODAS las mutaciones (el cliente
    re-renderiza todo con la respuesta fresca)."""
    actividades = [_act_enriquecer(a) for a in database.obtener_actividades()]
    historial = [
        {'actividad_id': h['actividad_id'], 'fecha_hecha': h['fecha_hecha']}
        for h in database.obtener_historial()
    ]
    return {'actividades': actividades, 'historial': historial}


def _home_calendario_payload():
    """Proyección de _act_payload() para la tarjeta Calendario del Inicio
    (mini mes con puntitos + lista de pendientes, 100% server-render).

    JAMÁS recalcula estado/próxima fecha: _act_enriquecer/_act_estado son la
    única fuente. Devuelve:
      - mes_nombre: 'Julio 2026' (es-AR, como fmtMesAnio del módulo).
      - hoy: día del mes (int).
      - semanas: monthdayscalendar del mes actual (lunes primero, 0 = celda
        vacía) — mismo arranque de semana que la grilla de /calendario.
      - dias: {dia_int: [estados]} — espejo de mapaPorDia() + dotsDelDia()
        de calendario.js: próxima fecha de actividades activas (estado
        vencida|proxima|aldia) + 'hecha' del historial; por día se dedupe
        con prioridad vencida → proxima → hecha → aldia y tope de 3 puntos.
      - pendientes: no terminadas con estado vencida|proxima, vencidas
        primero y luego proxima_fecha asc (mismo orden que renderAgenda),
        cap 6. Ítems: id, nombre, estado, proxima_fecha, dias_restantes."""
    import calendar as _calendar   # alias: no pisar la función de ruta `calendario`
    from datetime import date

    hoy = date.today()
    datos = _act_payload()
    prefijo_mes = hoy.strftime('%Y-%m')

    crudos = {}   # dia_int → [estados sin dedup]
    def _sumar(iso, estado):
        if iso and str(iso)[:7] == prefijo_mes:
            crudos.setdefault(int(str(iso)[8:10]), []).append(estado)

    pendientes = []
    for a in datos['actividades']:
        if a.get('terminada'):
            continue
        if a.get('proxima_fecha'):
            _sumar(a['proxima_fecha'], a['estado'])
        if a['estado'] in ('vencida', 'proxima'):
            pendientes.append({
                'id':             a['id'],
                'nombre':         a['nombre'],
                'estado':         a['estado'],
                'proxima_fecha':  a['proxima_fecha'],
                'dias_restantes': a['dias_restantes'],
            })
    for h in datos['historial']:
        _sumar(h.get('fecha_hecha'), 'hecha')

    ORDEN_PUNTOS = ('vencida', 'proxima', 'hecha', 'aldia')
    dias = {d: [e for e in ORDEN_PUNTOS if e in ests][:3]
            for d, ests in crudos.items()}

    pendientes.sort(key=lambda p: (0 if p['estado'] == 'vencida' else 1,
                                   p['proxima_fecha'] or ''))
    pendientes = pendientes[:6]

    MESES_ES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    return {
        'mes_nombre': f"{MESES_ES[hoy.month - 1]} {hoy.year}",
        'hoy':        hoy.day,
        'semanas':    _calendar.Calendar(firstweekday=0).monthdayscalendar(hoy.year, hoy.month),
        'dias':       dias,
        'pendientes': pendientes,
    }


# =============================================================================
# MÓDULO LACTANCIA — constantes y helpers de vencimiento/estado
# Propósito: banco de leche materna (partidas de freezer y heladera). La capa
# de datos pura vive en database.py (tabla lactancia_partidas); acá vive el
# cálculo de vencimiento y estado (disponible / vence pronto / vencida), a
# propósito fuera de database.py, igual que el módulo Calendario. Vencimiento
# y estado NUNCA se almacenan: cambiar un parámetro en Settings recalcula
# todo al refrescar (mismo comportamiento que el Excel que reemplaza).
# =============================================================================

LAC_UBICACIONES = ('freezer', 'heladera')
LAC_MOTIVOS_CIERRE = ('usada', 'descartada', 'trasladada')


# Los parámetros que la usuaria ajusta desde el panel "Ajustes" de /lactancia.
# Numéricos y booleanos van por separado porque castean distinto: en los
# numéricos un 0 es un valor válido (combinar_min_horas = 0 significa "no me
# lo verifiques"), así que nunca se decide por verdadero/falso.
LAC_PARAMS_NUM = (
    ('freezer_meses',            'lactancia_freezer_meses'),
    ('heladera_horas',           'lactancia_heladera_horas'),
    ('descongelada_horas',       'lactancia_descongelada_horas'),
    ('aviso_freezer_dias',       'lactancia_aviso_freezer_dias'),
    ('aviso_heladera_horas',     'lactancia_aviso_heladera_horas'),
    ('aviso_descongelada_horas', 'lactancia_aviso_descongelada_horas'),
    ('freezar_hasta_horas',      'lactancia_freezar_hasta_horas'),
    ('combinar_min_horas',       'lactancia_combinar_min_horas'),
    ('bolsa_capacidad_ml',       'lactancia_bolsa_capacidad_ml'),
)

LAC_PARAMS_BOOL = (
    ('bolsa_capacidad_activa', 'lactancia_bolsa_capacidad_activa'),
    ('pedir_confirmacion',     'lactancia_pedir_confirmacion'),
)


def _lac_params(cfg=None):
    """Devuelve los parámetros de conservación/aviso del módulo con claves
    cortas (las que viajan al front dentro de `params`). Si un valor viene
    corrupto en config.json, cae al DEFAULT."""
    if cfg is None:
        cfg = config.cargar_config(CONFIG_FILE)
    params = {}
    for corta, clave in LAC_PARAMS_NUM:
        try:
            params[corta] = int(cfg.get(clave, config.DEFAULTS[clave]))
        except (TypeError, ValueError):
            params[corta] = config.DEFAULTS[clave]
    for corta, clave in LAC_PARAMS_BOOL:
        valor = cfg.get(clave, config.DEFAULTS[clave])
        params[corta] = bool(valor)
    return params


def _lac_extraccion_dt(p):
    """Momento real de extracción (datetime): `fecha_extraccion` +
    `hora_extraccion`. Sin hora (solo filas legacy: alta y editar la exigen),
    cae a las 00:00 de ese día — el fallback conservador: nunca le regala
    vida útil a la leche."""
    fecha = datetime.strptime(str(p['fecha_extraccion']), '%Y-%m-%d')
    hora = (p.get('hora_extraccion') or '').strip()
    if hora:
        h, m = hora.split(':')
        return fecha.replace(hour=int(h), minute=int(m))
    return fecha


def _lac_vencimiento(p, params):
    """Vencimiento (datetime) de una partida, SIEMPRE desde la extracción
    real (la leche se degrada desde que se extrae, no desde que se carga en
    la app — issue #48; `cargada` queda como metadato de auditoría).

    Freezer: extracción + N meses (clamp fin de mes vía _act_sumar_intervalo),
    al fin del día (23:59:59): la partida es usable el día que vence, igual
    que el Excel (HOY() > vencimiento). Heladera: extracción (fecha + hora) +
    N horas — corre por timestamp, así que cruza medianoche sin caso
    especial."""
    from datetime import time
    if p['ubicacion'] == 'freezer':
        extraccion = datetime.strptime(str(p['fecha_extraccion']), '%Y-%m-%d').date()
        venc_dia = _act_sumar_intervalo(extraccion, params['freezer_meses'], 'meses')
        return datetime.combine(venc_dia, time(23, 59, 59))
    # Leche descongelada (bajada del freezer): la vida útil corre desde que se
    # baja (`cargada`), no desde la extracción, que puede ser de hace meses.
    if p.get('tipo') == 'descongelada':
        return datetime.fromisoformat(p['cargada']) + timedelta(hours=params['descongelada_horas'])
    return _lac_extraccion_dt(p) + timedelta(hours=params['heladera_horas'])


def _lac_estado(p, params, ahora):
    """Estado de una partida, en cascada (mismo espíritu que el Excel):
    cierre manual (usada/descartada/trasladada) > vencida > vence_pronto >
    en_jardin > disponible (freezer) | en_heladera (heladera).

    `en_jardin` vale en las DOS ubicaciones: la bolsita puede estar de back up
    en el freezer del jardín o ya descongelada en su heladera, que es lo que
    pasa el día que León se va con una bolsita bajada acá.

    Va DEBAJO del aviso a propósito: que esté en el jardín no puede tapar que se
    está por vencer — menos todavía en la heladera, donde el reloj corre en
    horas. Para no perder de vista dónde está, la tarjeta muestra la etiqueta 🏫
    aparte de esta pastilla."""
    if p.get('motivo_cierre'):
        return p['motivo_cierre']
    venc = _lac_vencimiento(p, params)
    if ahora > venc:
        return 'vencida'
    if p['ubicacion'] == 'freezer':
        dias = (venc.date() - ahora.date()).days
        if dias <= params['aviso_freezer_dias']:
            return 'vence_pronto'
        return 'en_jardin' if p.get('en_jardin') else 'disponible'
    horas = (venc - ahora).total_seconds() / 3600
    umbral = (params['aviso_descongelada_horas'] if p.get('tipo') == 'descongelada'
              else params['aviso_heladera_horas'])
    if horas <= umbral:
        return 'vence_pronto'
    return 'en_jardin' if p.get('en_jardin') else 'en_heladera'


def _lac_horas_en_heladera(p, ahora):
    """Horas transcurridas desde que la leche entró a la heladera. Para leche
    fresca es desde la extracción (issue #48); para la descongelada, desde que
    se bajó del freezer (`cargada`), que es cuando arranca su vida útil."""
    base = (datetime.fromisoformat(p['cargada']) if p.get('tipo') == 'descongelada'
            else _lac_extraccion_dt(p))
    return (ahora - base).total_seconds() / 3600


def _lac_freezable(p, params, ahora):
    """True si una partida de heladera todavía puede pasar al freezer: debe
    estar abierta, no vencida y NO ser leche descongelada (la que ya estuvo
    congelada no se vuelve a congelar). Sin tope de antigüedad — el usuario
    decide caso a caso (ver `_lac_freezar_reciente` para el default del check)."""
    if p['ubicacion'] != 'heladera' or p.get('motivo_cierre') or p.get('tipo') == 'descongelada':
        return False
    return _lac_estado(p, params, ahora) != 'vencida'


def _lac_freezar_reciente(p, params, ahora):
    """True si la partida lleva menos de `freezar_hasta_horas` en la heladera.
    Solo define si el checkbox arranca tildado por defecto — no bloquea nada,
    una partida más vieja sigue siendo freezable si el usuario la tilda."""
    return _lac_horas_en_heladera(p, ahora) < params['freezar_hasta_horas']


def _lac_enriquecer(row, params, ahora):
    """Convierte una fila de `lactancia_partidas` en dict serializable JSON,
    agregando vencimiento (ISO), estado, dias_restantes (solo freezer) y
    horas_restantes + horas_en_heladera + freezable + freezar_reciente (solo
    heladera). Los textos relativos ("vence en 5 h") los arma el JS."""
    p = dict(row)
    venc = _lac_vencimiento(p, params)
    p['vencimiento'] = venc.isoformat(timespec='seconds')
    p['estado'] = _lac_estado(p, params, ahora)
    # Las filas viejas (previas a la columna) traen NULL: el front espera un
    # booleano firme para decidir si dibuja la etiqueta del jardín.
    p['en_jardin'] = bool(p.get('en_jardin'))
    if p['ubicacion'] == 'freezer':
        p['dias_restantes'] = (venc.date() - ahora.date()).days
        p['horas_restantes'] = None
    else:
        p['dias_restantes'] = None
        p['horas_restantes'] = int((venc - ahora).total_seconds() // 3600)
        p['horas_en_heladera'] = int(_lac_horas_en_heladera(p, ahora))
        p['freezable'] = _lac_freezable(p, params, ahora)
        p['freezar_reciente'] = _lac_freezar_reciente(p, params, ahora)
    return p


def _lac_payload():
    """Payload completo del módulo Lactancia: listas FIFO + historial +
    tablero + params + badge. Usado por GET /lactancia, GET /api/lactancia y
    TODAS las mutaciones (el cliente re-renderiza todo con datos frescos).

    FIFO = vencimiento ascendente; desempate freezer por hora de extracción y
    luego id (dos extracciones el mismo día salen en orden). La heladera va
    SEPARADA de los totales de freezer, igual que el Excel."""
    params = _lac_params()
    ahora = datetime.now()
    partidas = [_lac_enriquecer(f, params, ahora)
                for f in database.obtener_partidas_lactancia()]

    abiertas = [p for p in partidas if not p['motivo_cierre']]
    freezer = sorted((p for p in abiertas if p['ubicacion'] == 'freezer'),
                     key=lambda p: (p['vencimiento'], p['hora_extraccion'] or '', p['id']))
    heladera = sorted((p for p in abiertas if p['ubicacion'] == 'heladera'),
                      key=lambda p: (p['vencimiento'], p['id']))
    historial = sorted((p for p in partidas if p['motivo_cierre']),
                       key=lambda p: (p['fecha_cierre'] or '', p['id']), reverse=True)

    # "Usables" = disponible + en_jardin + vence_pronto (las vencidas NO suman al
    # stock). La del jardín cuenta igual: es leche sana de León, solo que
    # guardada allá.
    usables = [p for p in freezer if p['estado'] in ('disponible', 'en_jardin', 'vence_pronto')]
    heladera_vigente = [p for p in heladera if p['estado'] in ('en_heladera', 'en_jardin', 'vence_pronto')]

    # KPIs de ciclo de vida. Se calculan sobre TODAS las partidas (abiertas +
    # historial). La producción ("litros de amor") cuenta SOLO las 'fresca':
    # cada extracción entra una vez como fresca; la 'congelada' y la
    # 'descongelada' son la MISMA leche movida, no producción nueva (si no,
    # se contaría 2-3 veces al freezar y descongelar).
    def _consumido(p):
        # 'usada' sin dato de consumo = se asume que se tomó toda la bolsa.
        return p['consumido_ml'] if p.get('consumido_ml') is not None else p['volumen_ml']
    usadas = [p for p in partidas if p['motivo_cierre'] == 'usada']
    # Desperdicio = todo lo descartado + lo que sobró en bolsas usadas con
    # consumo real anotado (sin anotar → no se puede saber, no suma).
    desperdicio_ml = (
        sum(p['volumen_ml'] for p in partidas if p['motivo_cierre'] == 'descartada')
        + sum(p['volumen_ml'] - p['consumido_ml'] for p in usadas if p.get('consumido_ml') is not None)
    )
    # Tamaño sugerido de bolsita: promedio de lo que León realmente tomó en las
    # bolsas con consumo anotado. Se auto-ajusta con cada dato nuevo (ej. de la
    # maestra). Sin datos todavía → None (el front muestra "según consumo").
    con_consumo = [p['consumido_ml'] for p in usadas if p.get('consumido_ml') is not None]
    bolsa_sugerida_ml = round(sum(con_consumo) / len(con_consumo)) if con_consumo else None
    # Días de stock: stock usable del freezer / consumo diario promedio de la
    # última semana (promedio móvil de 7 días). Sin consumo en la ventana → None
    # (todavía no se puede estimar; empieza cuando León tome de las bolsitas).
    def _fecha_cierre(p):
        try:
            return datetime.strptime(str(p['fecha_cierre']), '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return None
    ventana = ahora.date() - timedelta(days=6)
    consumo_semana = sum(_consumido(p) for p in usadas
                         if _fecha_cierre(p) and _fecha_cierre(p) >= ventana)
    # Se mide sobre TODA la leche que León tiene para tomar: freezer + heladera +
    # la que está de back up en el jardín. El resto del tablero sigue separando
    # freezer y heladera (son stocks de naturaleza distinta); este KPI es la
    # excepción a propósito.
    stock_usable_ml = (sum(p['volumen_ml'] for p in usables)
                       + sum(p['volumen_ml'] for p in heladera_vigente))
    dias_stock = int(stock_usable_ml / (consumo_semana / 7)) if consumo_semana else None

    tablero = {
        'freezer_bolsas':        len(usables),
        'freezer_ml':            sum(p['volumen_ml'] for p in usables),
        'freezer_vence_pronto':  sum(1 for p in freezer if p['estado'] == 'vence_pronto'),
        'freezer_vencidas':      sum(1 for p in freezer if p['estado'] == 'vencida'),
        'freezer_proximo_venc':  min((p['vencimiento'] for p in usables), default=None),
        # Lo que está en el jardín, esté congelado allá o ya descongelado en su
        # heladera (ya viene contado arriba, en el freezer o en la heladera
        # según corresponda; se muestra aparte para saber qué NO hay en casa).
        'jardin_bolsas':         sum(1 for p in usables + heladera_vigente if p['en_jardin']),
        'jardin_ml':             sum(p['volumen_ml'] for p in usables + heladera_vigente
                                     if p['en_jardin']),
        # Las trasladadas no cuentan como usadas ni descartadas: la leche
        # sigue existiendo, solo cambió de ubicación.
        'usadas_total':          sum(1 for p in partidas if p['motivo_cierre'] == 'usada'),
        'descartadas_total':     sum(1 for p in partidas if p['motivo_cierre'] == 'descartada'),
        'heladera_bolsas':       len(heladera_vigente),
        'heladera_ml':           sum(p['volumen_ml'] for p in heladera_vigente),
        'heladera_proximo_venc': min((p['vencimiento'] for p in heladera_vigente), default=None),
        # De lo vigente en heladera, cuánto es leche descongelada (bajada del
        # freezer) vs fresca — para diferenciar los dos tipos en la vista.
        'heladera_descongelada_ml': sum(p['volumen_ml'] for p in heladera_vigente
                                        if p.get('tipo') == 'descongelada'),
        'heladera_fresca_ml':       sum(p['volumen_ml'] for p in heladera_vigente
                                        if p.get('tipo') != 'descongelada'),
        # KPIs de ciclo de vida (totales históricos; los cortes por mes de
        # vida de León y los promedios móviles se agregan en el front).
        'producido_ml':          sum(p['volumen_ml'] for p in partidas if p.get('tipo') == 'fresca'),
        'descongelada_ml':       sum(p['volumen_ml'] for p in partidas if p.get('tipo') == 'descongelada'),
        'consumida_ml':          sum(_consumido(p) for p in usadas),
        'desperdicio_ml':        desperdicio_ml,
        'dias_stock':            dias_stock,          # None = aún sin datos
        'bolsa_sugerida_ml':     bolsa_sugerida_ml,   # None = aún sin datos
    }
    badge = sum(1 for p in abiertas if p['estado'] in ('vencida', 'vence_pronto'))

    rec = _lac_recordatorio()
    recordatorio = {**rec, 'pendiente': _lac_recordatorio_pendiente(rec, ahora)}
    bebe = _lac_bebe(ahora=ahora)

    return {'freezer': freezer, 'heladera': heladera, 'historial': historial,
            'tablero': tablero, 'params': params, 'badge': badge,
            'recordatorio': recordatorio, 'bebe': bebe,
            'muestras': _lac_muestras(partidas, bebe)}


def _home_lactancia_payload():
    """Proyección de _lac_payload() para la tarjeta Lactancia del Inicio:
    TODAS las partidas de heladera + la PRIMERA del freezer (FIFO: la que se
    consumiría a continuación). Solo recorta el payload completo — JAMÁS
    reimplementa vencimientos/estados (viven en los helpers _lac_*).

    `params` viaja también porque el form de alta del Inicio es el MISMO partial
    que el de /lactancia: necesita los tiempos para pintar el vencimiento en
    vivo mientras se carga."""
    datos = _lac_payload()
    return {'heladera': datos['heladera'],
            'freezer_primera': datos['freezer'][0] if datos['freezer'] else None,
            'params': datos['params']}


def _lac_parsear_volumen(valor):
    """Valida el volumen en ml: entero 1..2000 (las bolsas Lansinoh son de
    180 ml; el tope generoso cubre cualquier contenedor). Lanza ValueError."""
    try:
        volumen = int(str(valor if valor is not None else '').strip())
    except ValueError:
        raise ValueError("El volumen (ml) debe ser un número entero.")
    if not 1 <= volumen <= 2000:
        raise ValueError("El volumen debe estar entre 1 y 2000 ml.")
    return volumen


def _lac_parsear_extraccion(form):
    """Valida fecha (YYYY-MM-DD) y hora (HH:MM) de extracción. El momento
    combinado fecha+hora no puede ser futuro (es la base del vencimiento,
    issue #48). Devuelve (fecha, hora). Lanza ValueError."""
    fecha = (form.get('fecha_extraccion') or '').strip()
    try:
        datetime.strptime(fecha, '%Y-%m-%d')
    except ValueError:
        raise ValueError(f"Fecha de extracción inválida: {fecha}")
    hora = (form.get('hora_extraccion') or '').strip()
    try:
        datetime.strptime(hora, '%H:%M')
    except ValueError:
        raise ValueError(f"Hora de extracción inválida: {hora}")
    if datetime.fromisoformat(f"{fecha}T{hora}") > datetime.now():
        raise ValueError("La extracción (fecha + hora) no puede ser futura.")
    return fecha, hora


def _lac_parsear_fecha_cierre(valor):
    """'' o ausente → hoy. Si viene, valida YYYY-MM-DD no futura. Lanza ValueError."""
    from datetime import date
    valor = (valor or '').strip()
    if not valor:
        return date.today().isoformat()
    try:
        fecha_dt = datetime.strptime(valor, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f"Fecha de cierre inválida: {valor}")
    if fecha_dt > date.today():
        raise ValueError("La fecha de cierre no puede ser futura.")
    return valor


def _lac_leer_form_alta(form):
    """Lee y valida el alta de una partida. Devuelve dict listo para
    database.agregar_partida_lactancia. Lanza ValueError.

    El flujo estándar es a heladera (toda extracción entra por ahí, con su
    fecha/hora de extracción — base del vencimiento en AMBAS ubicaciones,
    issue #48; el momento de carga lo pone el servidor en `cargada`, solo
    auditoría). Al freezar la combinación, la extracción más vieja define el
    vencimiento de freezer."""
    ubicacion = form.get('ubicacion', '')
    if ubicacion not in LAC_UBICACIONES:
        raise ValueError(f"Ubicación inválida: {ubicacion}")

    volumen_ml = _lac_parsear_volumen(form.get('volumen_ml'))
    notas = (form.get('notas') or '').strip()[:200]
    fecha, hora = _lac_parsear_extraccion(form)
    return dict(ubicacion=ubicacion, fecha_extraccion=fecha, hora_extraccion=hora,
                volumen_ml=volumen_ml, notas=notas)


def _lac_dia_de_vida(nac, dia):
    """(día de vida, mes de vida) de una fecha, o (None, None) sin nacimiento.

    El día del parto es el DÍA 1 y el MES 1 (así se cuenta en pediatría), y el
    mes cambia el mismo número de día de cada mes (14/05 → 14/06 = mes 2)."""
    if nac is None or dia < nac:
        return None, None
    meses = (dia.year - nac.year) * 12 + (dia.month - nac.month)
    if dia.day < nac.day:
        meses -= 1
    return (dia - nac).days + 1, max(meses, 0) + 1


def _lac_muestras(partidas=None, bebe=None):
    """Una fila por EXTRACCIÓN REAL: la materia prima del gráfico del Resumen.

    Cada fila es una vez que se sacó leche: cuándo (fecha, hora y día de la
    semana), cuánta, y qué edad tenía el bebé ese día. Con esa lista el
    navegador puede cruzar cualquier par de variables —hora contra volumen, día
    de la semana contra cantidad, lo que sea— sin volver a preguntarle nada al
    servidor: cambiar de eje no es un pedido más, es reagrupar lo que ya tiene.

    Cuenta SOLO la leche FRESCA, el mismo criterio de _lac_dia_a_dia. Una bolsa
    freezada (varias de heladera combinadas en una) o una bajada a descongelar
    es la MISMA leche cambiando de lugar: si se contara otra vez, los mismos
    mililitros aparecerían dos y tres veces y el gráfico mentiría.

    Una bolsita ya usada o descartada SÍ cuenta: esa extracción existió igual, y
    acá se mira lo que se produjo, no lo que queda guardado.

    Sin fecha de nacimiento cargada, dia_vida y mes_vida quedan en None (la
    pantalla deshabilita esos ejes; nada se rompe). Lo mismo con la hora: la
    app la pide siempre, pero en la base puede faltar.
    """
    if partidas is None:
        partidas = database.obtener_partidas_lactancia()
    if bebe is None:
        bebe = _lac_bebe()
    try:
        nac = datetime.strptime(bebe['fecha_nacimiento'], '%Y-%m-%d').date()
    except ValueError:
        nac = None

    muestras = []
    for fila in partidas:
        p = dict(fila)
        if (p.get('tipo') or 'fresca') != 'fresca':
            continue
        try:
            dia = datetime.strptime(str(p['fecha_extraccion']), '%Y-%m-%d').date()
        except (TypeError, ValueError):
            continue
        dia_vida, mes_vida = _lac_dia_de_vida(nac, dia)
        muestras.append({
            'id':         p['id'],
            'fecha':      dia.isoformat(),
            'hora':       (p.get('hora_extraccion') or '').strip() or None,
            'ml':         p['volumen_ml'],
            'dia_vida':   dia_vida,
            'mes_vida':   mes_vida,
            'dia_semana': dia.weekday(),      # 0 = lunes … 6 = domingo
        })
    return muestras


def _lac_dia_a_dia(hoy=None):
    """Un renglón por cada día de vida del bebé: qué se extrajo y qué tomó.

    Es la base de la descarga. Cada renglón mira el día completo:
      - ml extraídos: lo que se sacó ESE día. Solo cuenta la leche FRESCA: una
        bolsa combinada (freezada) o una bajada a descongelar es la MISMA leche
        cambiando de lugar, contarla otra vez la duplicaría.
      - ml tomados: lo de las bolsitas marcadas "usada" ese día. Si se anotó
        cuánto tomó de verdad, va ese número; si no, lo que tenía la bolsita
        (mismo criterio que la tarjeta "Consumida por" del Resumen).
      - ml descartados: lo de las bolsitas tiradas ese día.

    Sin fecha de nacimiento cargada la tabla igual sale: arranca en el primer
    movimiento y las columnas de día/mes de vida quedan vacías."""
    from datetime import date
    if hoy is None:
        hoy = date.today()
    partidas = [dict(f) for f in database.obtener_partidas_lactancia()]
    bebe = _lac_bebe()
    try:
        nac = datetime.strptime(bebe['fecha_nacimiento'], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        nac = None

    def _fecha(valor):
        try:
            return datetime.strptime(str(valor), '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return None

    extraido, tomado, descartado = {}, {}, {}
    movimientos = []
    for p in partidas:
        f_ex = _fecha(p['fecha_extraccion'])
        if f_ex:
            movimientos.append(f_ex)
            if (p.get('tipo') or 'fresca') == 'fresca':
                extraido[f_ex] = extraido.get(f_ex, 0) + p['volumen_ml']
        f_ci = _fecha(p.get('fecha_cierre'))
        if f_ci:
            movimientos.append(f_ci)
            if p.get('motivo_cierre') == 'usada':
                ml = (p['consumido_ml'] if p.get('consumido_ml') is not None
                      else p['volumen_ml'])
                tomado[f_ci] = tomado.get(f_ci, 0) + ml
            elif p.get('motivo_cierre') == 'descartada':
                descartado[f_ci] = descartado.get(f_ci, 0) + p['volumen_ml']

    candidatas = [d for d in [nac] + movimientos if d is not None]
    desde = min(candidatas) if candidatas else hoy
    hasta = max([hoy] + movimientos) if movimientos else hoy

    filas = []
    dia = desde
    while dia <= hasta:
        dia_vida, mes_vida = _lac_dia_de_vida(nac, dia)
        filas.append({
            'fecha': dia.isoformat(),
            'dia_vida': dia_vida,
            'mes_vida': mes_vida,
            'extraido_ml': extraido.get(dia, 0),
            'tomado_ml': tomado.get(dia, 0),
            'descartado_ml': descartado.get(dia, 0),
        })
        dia += timedelta(days=1)

    return {
        'filas': filas,
        'bebe': bebe,
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'totales': {
            'extraido_ml': sum(f['extraido_ml'] for f in filas),
            'tomado_ml': sum(f['tomado_ml'] for f in filas),
            'descartado_ml': sum(f['descartado_ml'] for f in filas),
        },
    }


def _horas_texto(horas):
    """Horas (float) → texto corto para un mensaje: '40 min', '2 h', '2 h 20 min'.
    Se usa en el aviso de cuánto le falta a una partida para poder combinarse."""
    minutos = max(1, int(round(horas * 60)))
    h, m = divmod(minutos, 60)
    if not h:
        return f"{m} min"
    return f"{h} h" if not m else f"{h} h {m} min"


def _lac_validar_capacidad(volumen_ml, params):
    """Si la capacidad de bolsita está activada, no deja pasar un volumen que
    no entre en una bolsita. Es un tope declarado por la usuaria en Ajustes,
    no una regla sanitaria: apagado por defecto. Lanza ValueError."""
    if not params.get('bolsa_capacidad_activa'):
        return
    tope = params['bolsa_capacidad_ml']
    if volumen_ml > tope:
        raise ValueError(
            f"Son {volumen_ml} ml y tus bolsitas son de {tope} ml. "
            "Cambiá la capacidad en Ajustes o repartilo en varias bolsitas.")


# =============================================================================
# MÓDULO NOTIFICACIONES — helpers y registry de providers
# Propósito: campana de notificaciones genérica en el header (reemplaza los
# badges de nav por módulo). Cada módulo de negocio expone un "provider":
# una función sin argumentos que devuelve una lista de ítems con el contrato
# CERRADO documentado en docs/CONTEXT_NOTIFICATIONS.md (claves: modulo,
# modulo_nombre, icono, titulo, detalle, url, severidad). _notificaciones()
# agrega los providers de NOTIF_PROVIDERS; un provider roto NUNCA tumba la
# campana (try/except individual, logueado con AVISO). Para sumar un módulo
# nuevo: escribir su función `_notif_<modulo>()` y agregarla a
# NOTIF_PROVIDERS — nada más (ver checklist en CONTEXT_NOTIFICATIONS.md).
# =============================================================================

def _notif_lactancia():
    """Provider de notificaciones del módulo Lactancia: 1 ítem por partida
    ABIERTA (sin motivo_cierre) cuyo estado sea 'vencida' o 'vence_pronto'.
    Reusa _lac_params()/_lac_enriquecer() tal cual — el cálculo de
    vencimiento/estado vive únicamente en los helpers _lac_* (NUNCA se
    reimplementa acá). Orden interno: vencidas primero, luego por vencer;
    dentro de cada grupo, por vencimiento ascendente."""
    params = _lac_params()
    ahora = datetime.now()
    partidas = [_lac_enriquecer(f, params, ahora)
                for f in database.obtener_partidas_lactancia()
                if not f['motivo_cierre']]
    relevantes = [p for p in partidas if p['estado'] in ('vencida', 'vence_pronto')]
    relevantes.sort(key=lambda p: (0 if p['estado'] == 'vencida' else 1, p['vencimiento']))

    def _dias_texto(n):
        return f"{n} día" if n == 1 else f"{n} días"

    items = []
    for p in relevantes:
        vencida = p['estado'] == 'vencida'
        if p['ubicacion'] == 'freezer':
            dias = abs(p['dias_restantes'])
            if vencida:
                tiempo = 'venció hoy' if dias == 0 else f'venció hace {_dias_texto(dias)}'
            else:
                tiempo = 'vence hoy' if dias == 0 else f'vence en {_dias_texto(dias)}'
            # Si está de back up en el jardín, avisarlo: hay que ir a buscarla
            # allá, no está en casa.
            ubicacion_txt = 'Freezer del jardín 🏫' if p['en_jardin'] else 'Freezer'
        else:
            tiempo = 'venció' if vencida else f"vence en {p['horas_restantes']} h"
            ubicacion_txt = 'Heladera del jardín 🏫' if p['en_jardin'] else 'Heladera'
        items.append({
            'modulo':        'lactancia',
            'modulo_nombre': 'Lactancia',
            'icono':         '🍼',
            'titulo':        'Partida vencida' if vencida else 'Partida por vencer',
            'detalle':       f"{ubicacion_txt} · {p['volumen_ml']} ml · {tiempo}",
            'url':           '/lactancia',
            'severidad':     'peligro' if vencida else 'alerta',
        })
    return items


def _lac_recordatorio(cfg=None):
    """Config del recordatorio nocturno de "bajar bolsitas": activo (modo
    jardín on/off) y hora (HH:MM). Claves faltantes o corruptas → DEFAULTS."""
    if cfg is None:
        cfg = config.cargar_config(CONFIG_FILE)
    activo = bool(cfg.get('lactancia_recordatorio_activo',
                          config.DEFAULTS['lactancia_recordatorio_activo']))
    hora = str(cfg.get('lactancia_recordatorio_hora',
                       config.DEFAULTS['lactancia_recordatorio_hora']))
    try:
        datetime.strptime(hora, '%H:%M')
    except ValueError:
        hora = config.DEFAULTS['lactancia_recordatorio_hora']
    dias_txt = cfg.get('lactancia_recordatorio_dias') or config.DEFAULTS['lactancia_recordatorio_dias']
    try:
        dias = {int(d) for d in str(dias_txt).split(',') if d.strip() != ''}
    except ValueError:
        dias = set(range(7))
    return {'activo': activo, 'hora': hora, 'dias': sorted(dias)}


def _lac_bajo_leche_hoy(ahora):
    """True si YA se bajó al menos una bolsa a descongelar hoy (hay una partida
    'descongelada' con `cargada` de hoy). Así el recordatorio se autolimpia
    cuando la usuaria efectivamente baja algo."""
    hoy = ahora.date()
    for f in database.obtener_partidas_lactancia('heladera'):
        p = dict(f)
        if p.get('tipo') == 'descongelada':
            try:
                if datetime.fromisoformat(p['cargada']).date() == hoy:
                    return True
            except (TypeError, ValueError):
                pass
    return False


def _lac_recordatorio_pendiente(rec=None, ahora=None):
    """True si el recordatorio de bajar bolsitas está VIGENTE ahora: activo, ya
    pasó la hora de hoy, hay leche ABIERTA en el freezer para bajar, y todavía
    no se bajó ninguna hoy. Es solo un aviso — nunca bloquea nada."""
    if ahora is None:
        ahora = datetime.now()
    if rec is None:
        rec = _lac_recordatorio()
    if not rec['activo']:
        return False
    manana = ahora.date() + timedelta(days=1)
    if manana.weekday() not in rec.get('dias', range(7)):
        return False
    hh, mm = rec['hora'].split(':')
    hora_dt = ahora.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    if ahora < hora_dt:
        return False
    hay_freezer = any(not f['motivo_cierre']
                      for f in database.obtener_partidas_lactancia('freezer'))
    if not hay_freezer:
        return False
    return not _lac_bajo_leche_hoy(ahora)


def _notif_recordatorio_bajar():
    """Provider: recordatorio nocturno de bajar bolsitas del freezer a la
    heladera (para el día siguiente de jardín). Aviso in-app (la campana); el
    ping al celular con la app cerrada llega con la futura app instalable."""
    if not _lac_recordatorio_pendiente():
        return []
    rec = _lac_recordatorio()
    return [{
        'modulo':        'lactancia',
        'modulo_nombre': 'Lactancia',
        'icono':         '🌙',
        'titulo':        'Bajá bolsitas para mañana',
        'detalle':       f"Pasá leche del freezer a la heladera para que se descongele "
                         f"(recordatorio de las {rec['hora']}).",
        'url':           '/lactancia',
        'severidad':     'alerta',
    }]


def _edad_desde(fecha_nacimiento, hoy=None):
    """Edad derivada de una fecha de nacimiento 'YYYY-MM-DD'.

    Lo usan el perfil del bebé de Lactancia (_lac_bebe) y la ficha de cada
    miembro de Rutina (_rut_edad), que necesitan lo mismo: un texto legible
    y el mes de vida. Devuelve dict con claves siempre presentes; si la fecha
    es inválida, vacía o futura, todo queda en None/'' (nunca lanza).

    Formato del texto: hasta los 2 años se cuenta en meses y días ("2 meses y
    9 días"), porque a esa edad el detalle importa; después, en años y meses.
    """
    fnac = str(fecha_nacimiento or '').strip()
    vacio = {'fecha_nacimiento': fnac, 'edad_texto': '',
             'mes_de_vida': None, 'dias': None}
    try:
        nac = datetime.strptime(fnac, '%Y-%m-%d').date()
    except ValueError:
        return vacio

    # Acepta datetime o date; por default, ahora.
    if hoy is None:
        hoy = datetime.now()
    if isinstance(hoy, datetime):
        hoy = hoy.date()
    dias = (hoy - nac).days
    if dias < 0:
        return vacio

    meses = (hoy.year - nac.year) * 12 + (hoy.month - nac.month)
    if hoy.day < nac.day:
        meses -= 1
    meses = max(meses, 0)
    # Días sueltos desde el último "cumple-mes" (clamp fin de mes vía
    # _act_sumar_intervalo, el mismo helper que usa el vencimiento).
    dias_resto = (hoy - _act_sumar_intervalo(nac, meses, 'meses')).days

    def _plur(n, sing, plur):
        return f"{n} {sing}" if n == 1 else f"{n} {plur}"

    if meses < 24:
        partes = []
        if meses:
            partes.append(_plur(meses, 'mes', 'meses'))
        if dias_resto or not meses:
            partes.append(_plur(dias_resto, 'día', 'días'))
        edad_texto = ' y '.join(partes)
    else:
        anios, resto = divmod(meses, 12)
        edad_texto = _plur(anios, 'año', 'años')
        if resto:
            edad_texto += ' y ' + _plur(resto, 'mes', 'meses')

    return {'fecha_nacimiento': fnac, 'edad_texto': edad_texto,
            'mes_de_vida': meses + 1, 'dias': dias}   # el 1er mes de vida es el mes 1


def _lac_bebe(cfg=None, ahora=None):
    """Perfil del bebé para la UI: nombre (se usa en los textos) + fecha de
    nacimiento, con la edad y el mes de vida derivados. A propósito NO guarda
    ni calcula nada médico (peso, estatura, cuánta leche "debería" tomar)."""
    if cfg is None:
        cfg = config.cargar_config(CONFIG_FILE)
    if ahora is None:
        ahora = datetime.now()
    nombre = (str(cfg.get('bebe_nombre', config.DEFAULTS['bebe_nombre'])).strip()
              or 'el bebé')
    edad = _edad_desde(cfg.get('bebe_fecha_nacimiento',
                               config.DEFAULTS['bebe_fecha_nacimiento']), ahora)
    return {'nombre': nombre, 'fecha_nacimiento': edad['fecha_nacimiento'],
            'edad_texto': edad['edad_texto'], 'mes_de_vida': edad['mes_de_vida']}


NOTIF_PROVIDERS = [_notif_lactancia, _notif_recordatorio_bajar]


def _notificaciones():
    """Agrega los ítems de TODOS los providers de NOTIF_PROVIDERS. Cada
    provider corre aislado: si uno falla, se loguea (AVISO) y se sigue con
    los demás — un módulo roto nunca tumba la campana. Orden final: peligro
    → alerta → info; el sort es estable, así que respeta el orden interno de
    cada provider y el orden de NOTIF_PROVIDERS entre módulos distintos con
    la misma severidad."""
    items = []
    for provider in NOTIF_PROVIDERS:
        try:
            items.extend(provider())
        except Exception as e:
            log(f"AVISO: provider de notificaciones '{provider.__name__}' falló: {e}")
    orden_severidad = {'peligro': 0, 'alerta': 1, 'info': 2}
    items.sort(key=lambda it: orden_severidad.get(it['severidad'], 3))
    return items


# =============================================================================
# HELPER: _calcular_monto_usd(monto, moneda, cfg)
# Propósito: Centraliza la conversión ARS→USD al insertar/editar movimientos.
# =============================================================================
#
# - Si moneda == 'usd' → (monto, None)                       (no hay conversión)
# - Si moneda == 'ars' → (monto/cotizacion, cotizacion)      (se guarda la tasa)
#
# La cotización se toma de config.json ('cotizacion_valor'), que se refresca
# 1 vez por día desde dolarapi.com vía el módulo cotizacion.py.
#
def _calcular_monto_usd(monto, moneda, cfg):
    """Retorna (monto_usd, cotizacion_usd_aplicada) para un movimiento nuevo/editado."""
    if moneda == 'usd':
        return float(monto), None
    cot = float(cfg.get('cotizacion_valor') or 1.0)
    if cot <= 0:
        cot = 1.0  # Guardia defensiva: evita división por cero si algo salió mal.
    return float(monto) / cot, cot

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))
app.config['TEMPLATES_AUTO_RELOAD'] = True  # Recargar templates sin reiniciar

# ── Autenticación con Google OAuth ───────────────────────────────────────────
# init_auth() configura: secret_key persistente, OAuth con Google,
# middleware before_request que protege TODAS las rutas.
from auth import init_auth
init_auth(app, CONFIG_FILE)


# =============================================================================
# FILTROS DE TEMPLATE — Formateo de montos
# =============================================================================
#
# Los filtros de Jinja2 se usan en los templates con la sintaxis:
#   {{ valor | fmt_ars }}   →  $ 1.250.000
#   {{ valor | fmt_usd }}   →  USD 1.250,50
#
# Se registran con el decorador @app.template_filter('nombre_filtro').
#

@app.context_processor
def inject_config():
    from flask import session as flask_session
    return {
        'cfg': config.cargar_config(CONFIG_FILE),
        'user_email': flask_session.get('user_email', ''),
        'user_name': flask_session.get('user_name', ''),
        'user_photo': flask_session.get('user_photo', ''),
        # mtime de los estáticos → cache-busting automático: el navegador
        # recarga style.css/app.js cuando cambian, sin Ctrl+F5.
        'static_version': _static_version(),
    }


@app.context_processor
def inject_notif_badge():
    """Expone `notif_badge` (cantidad total de notificaciones activas de
    TODOS los módulos, vía _notificaciones()) a todos los templates, para el
    contador de la campana en el header. Con red de seguridad: un fallo acá
    jamás debe romper el render de una página."""
    try:
        return {'notif_badge': len(_notificaciones())}
    except Exception:
        return {'notif_badge': 0}


def _static_version():
    """Devuelve el mtime más reciente de los archivos estáticos principales."""
    try:
        paths = [
            os.path.join(app.static_folder, 'style.css'),
            os.path.join(app.static_folder, 'app.js'),
            os.path.join(app.static_folder, 'calendario.js'),
            os.path.join(app.static_folder, 'lactancia.js'),
            os.path.join(app.static_folder, 'grafico.js'),
            os.path.join(app.static_folder, 'rutina.js'),
            os.path.join(app.static_folder, 'rutina-actividades.js'),
            os.path.join(app.static_folder, 'rutina-sueno.js'),
            os.path.join(app.static_folder, 'rutina-dibujos.js'),
            os.path.join(app.static_folder, 'home.js'),
        ]
        return str(int(max(os.path.getmtime(p) for p in paths if os.path.exists(p))))
    except Exception:
        return '0'


@app.template_filter('fmt_ars')
def fmt_ars(valor):
    """
    Formatea un número como pesos argentinos.
    Ejemplo: 1250000.0  →  $ 1.250.000
             -50000.0   →  $ -50.000
    """
    signo = '-' if valor < 0 else ''
    # {:,} en Python usa coma como separador de miles: 1,250,000
    # .replace(',', '.') lo convierte al estilo argentino: 1.250.000
    entero = f"{abs(round(valor)):,}".replace(',', '.')
    return f"$ {signo}{entero}"


@app.template_filter('fmt_fecha')
def fmt_fecha(valor):
    """
    Convierte fecha ISO (YYYY-MM-DD) a formato argentino (DD/MM/AAAA).
    Ejemplo: '2026-03-24' → '24/03/2026'
    """
    try:
        partes = str(valor).split('-')
        return f"{partes[2]}/{partes[1]}/{partes[0]}"
    except Exception:
        return str(valor)


@app.template_filter('fmt_usd')
def fmt_usd(valor):
    """
    Formatea un número como dólares con 2 decimales, estilo argentino.
    Ejemplo: 1250.50   →  USD 1.250,50
             -300.0    →  USD -300,00
    """
    signo = '-' if valor < 0 else ''
    # {:,.2f} → "1,250.50" (estilo anglosajón)
    # Luego intercambiamos punto y coma al estilo argentino:
    #   coma → X (temporal)  →  punto → coma  →  X → punto
    n = f"{abs(valor):,.2f}"
    n = n.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f"USD {signo}{n}"


@app.template_filter('fmt_fecha_hora')
def fmt_fecha_hora(valor):
    """
    Convierte un datetime ISO (YYYY-MM-DDTHH:MM:SS[...]) a formato argentino
    'DD/MM/AAAA HH:MM'. Si el input es sólo fecha (YYYY-MM-DD), devuelve
    DD/MM/AAAA. Si no se puede parsear, devuelve el valor original como string.
    """
    if not valor:
        return ''
    s = str(valor)
    try:
        # Soportar tanto 'YYYY-MM-DDTHH:MM:SS' como 'YYYY-MM-DD HH:MM:SS'
        fecha_part = s.split('T')[0].split(' ')[0]
        hora_part  = s.split('T')[1] if 'T' in s else (s.split(' ')[1] if ' ' in s else '')
        partes_f = fecha_part.split('-')
        fecha_arg = f"{partes_f[2]}/{partes_f[1]}/{partes_f[0]}"
        if hora_part:
            # Tomar sólo HH:MM
            hhmm = hora_part[:5]
            return f"{fecha_arg} {hhmm}"
        return fecha_arg
    except Exception:
        return s


@app.template_global('dias_desde_fecha')
def dias_desde_fecha(fecha_str):
    """
    Retorna la cantidad de días transcurridos desde una fecha dada hasta hoy.
    Acepta 'YYYY-MM-DD' o ISO datetime. Si no se puede parsear, retorna un
    número grande (99999) para que la lógica del template trate la situación
    como "muy viejo / desconocido".
    """
    if not fecha_str:
        return 99999
    try:
        s = str(fecha_str).split('T')[0].split(' ')[0]
        fecha = datetime.strptime(s, '%Y-%m-%d').date()
        return (datetime.now().date() - fecha).days
    except Exception:
        return 99999


# =============================================================================
# HELPER: _calcular_gauges(saldos, cotizacion_valor, historico=False)
# Propósito: arma el dict de los 3 gauges de distribución (ARS, USD, Total).
#   Compartido por '/' (Inicio), '/gastos' y la API '/api/saldos'.
# =============================================================================
def _calcular_gauges(saldos, cotizacion_valor, historico=False):
    """Distribución para los 3 gauges circulares.

    - ARS / USD: Elías vs Mari en cada moneda (exacto, valores nativos).
    - Total: ARS vs USD de toda la caja.
        · historico=False: valúa los pesos a la cotización vigente
          (distribución *actual* de la caja).
        · historico=True: usa la suma de monto_usd congelado por fila
          (ars_total_usd vs usd_total_usd), fiel al valor de cada fecha,
          sin inventar una cotización anacrónica que no guardamos.
    """
    def _gauge(a, b):
        """(pct_a, pct_b) normalizados a 100, usando solo valores ≥ 0."""
        pa, pb = max(float(a), 0), max(float(b), 0)
        total = pa + pb
        if total <= 0:
            return 0.0, 0.0
        return round(pa / total * 100, 2), round(pb / total * 100, 2)

    cotizacion_valor = float(cotizacion_valor or 1.0)
    g_ars = _gauge(saldos['elias_ars'], saldos['mari_ars'])
    g_usd = _gauge(saldos['elias_usd'], saldos['mari_usd'])

    if historico:
        g_total = _gauge(saldos.get('ars_total_usd', 0.0),
                         saldos.get('usd_total_usd', 0.0))
    else:
        total_ars = float(saldos.get('elias_ars', 0.0)) + float(saldos.get('mari_ars', 0.0))
        total_usd = float(saldos.get('elias_usd', 0.0)) + float(saldos.get('mari_usd', 0.0))
        total_ars_en_usd = (total_ars / cotizacion_valor) if cotizacion_valor > 0 else 0.0
        g_total = _gauge(total_ars_en_usd, total_usd)

    return {
        'ars':   {'elias': g_ars[0],   'mari':  g_ars[1]},
        'usd':   {'elias': g_usd[0],   'mari':  g_usd[1]},
        'total': {'ars':   g_total[0], 'usd':   g_total[1]},
        # Valor informativo que el frontend muestra como "1 USD = AR$ X".
        'cotizacion': int(cotizacion_valor),
        # El frontend usa esto para ocultar la tasa "@ $X/USD" en modo histórico.
        'historico':  historico,
    }


# =============================================================================
# HELPER: gastos fijos activos → JSON para el form rápido (window.GASTOS_FIJOS)
# Compartido por /gastos y / (Inicio): ambos renderizan el form de movimiento.
# =============================================================================

def _gastos_fijos_json():
    """JSON con los gastos fijos activos (descripcion + datos de cuota) que
    el frontend usa para poblar el select de descripciones cuando la
    categoría es 'Fijo' (variable global GASTOS_FIJOS en app.js)."""
    import json
    fijos_activos = database.obtener_gastos_fijos(solo_activos=True)
    return json.dumps([
        {
            'descripcion': f['descripcion'],
            'es_cuota':    f['es_cuota'] or 0,
            'cuota_actual': f['cuota_actual'] or 0,
            'total_cuotas': f['total_cuotas'],
        }
        for f in fijos_activos
    ])


# =============================================================================
# RUTA: Inicio — home de la app con lo más usado de cada módulo
# URL: http://localhost:5000/
# =============================================================================

@app.route('/')
def index():
    """Inicio: home de la app. Tarjetas Gastos (form de movimiento),
    Saldos (tarjeta completa compartida con /gastos vía _tarjeta_saldos.html:
    título + selector de fecha + tabla + gauges → necesita `gauges` en el
    context, mismo cálculo que gastos()), Lactancia (cargar extracción +
    consumir partidas), Calendario (mini mes + pendientes, 100%
    server-render) y Rutina (qué hace cada uno AHORA + qué viene después:
    rut_home = _rut_payload de HOY, rango de 1 día — mismo helper que
    /rutina; lo consume rutina.js vía window.RUT_DATOS y lo renderiza
    home.js con window.Rutina.hoyAhora). `cfg` llega vía inject_config."""
    from datetime import date
    cfg    = config.cargar_config(CONFIG_FILE)
    saldos = database.calcular_saldos()

    # ── Gauges de distribución (mismo cálculo que /gastos) ────────────────────
    cotizacion_valor = float(cfg.get('cotizacion_valor') or 1.0)
    gauges = _calcular_gauges(saldos, cotizacion_valor)

    hoy_iso = date.today().isoformat()
    return render_template('index.html',
                           saldos=saldos,
                           gauges=gauges,
                           gastos_fijos_json=_gastos_fijos_json(),
                           lac_home=_home_lactancia_payload(),
                           cal_home=_home_calendario_payload(),
                           rut_home=_rut_payload(hoy_iso, hoy_iso))


# =============================================================================
# RUTA: PWA — manifest de instalación (ventana propia, sin barra de dirección)
# URL: GET /manifest.json
# =============================================================================
#
# QUÉ HABILITA: que Edge/Chrome muestren el botón "Instalar" en la barra de
# direcciones y que la app abra como ventana propia (`display: standalone`).
#
# POR QUÉ ES UNA RUTA Y NO UN ARCHIVO SUELTO EN static/:
#   a. Tiene que colgar de la RAÍZ. El `scope` de un manifest no puede subir
#      de carpeta: servido desde /static/ el scope máximo sería /static/.
#   b. El Content-Type tiene que ser `application/manifest+json`. Flask sirve
#      los estáticos como `application/json` y algunos validadores chillan.
#   c. Los colores salen de `paleta_light` EN CALIENTE, así siguen lo que se
#      guarde en Settings → Paleta. Cero hex escrito a mano acá (regla 1).
#
# FUERA DEL LOGIN: el endpoint 'manifest' está listado en `rutas_publicas` de
# auth.py. El navegador pide el manifest antes de que haya sesión; si cayera
# en el redirect al login leería el HTML del login como manifest, y no habría
# botón de instalar. Los PNG ya son públicos: viven en static/.
#
# SIN SERVICE WORKER a propósito. El botón de instalar y la ventana propia no
# lo necesitan. Si algún día se suma, va network-first y SIN cachear /api/*:
# la app nunca debe mostrar saldos viejos.
# =============================================================================

@app.route('/manifest.json')
def manifest():
    import json
    cfg     = config.cargar_config(CONFIG_FILE)
    paleta  = cfg.get('paleta_light') or {}
    oscura  = cfg.get('paleta_dark') or {}

    datos = {
        'id':          '/',
        'name':        'Núcleo',
        'short_name':  'Núcleo',
        'description': 'Nuestra familia: gastos, lactancia, calendario y rutina.',
        'start_url':   '/',
        'scope':       '/',
        'display':     'standalone',
        'lang':        'es-AR',
        'dir':         'ltr',
        # Barra de título de la ventana = el color del banner superior. El
        # `.site-header` es vidrio (`--color-superficie` al 62%), y un manifest
        # no sabe de `color-mix`: se usa el color base de ese banner.
        #
        # Va el valor OSCURO a propósito (pedido del usuario, 2026-08-26). Este
        # color lo usa el sistema para pintar el marco ANTES de que cargue la
        # página; recién ahí el MutationObserver de `base.html` lo ajusta al
        # tema real. Arrancar oscuro y pasar a claro molesta menos que al
        # revés, y con el tema en dark —el caso habitual acá— ya no hay salto:
        # el color de arranque es exactamente el que va a quedar.
        'theme_color':      oscura.get('superficie'),
        'background_color': paleta.get('fondo'),
        'icons': [
            {'src':   url_for('static', filename='img/icon-192.png'),
             'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
            {'src':   url_for('static', filename='img/icon-512.png'),
             'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
            # Maskable: va a sangre y con ~10% de aire, porque Android recorta
            # el ícono con la forma del launcher (círculo, gota, rombo).
            {'src':   url_for('static', filename='img/icon-512-maskable.png'),
             'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
        ],
    }

    # Si a la paleta le faltara una clave, mejor omitir el campo que mandar
    # null: un color inválido invalida el manifest entero y se cae el botón.
    datos = {k: v for k, v in datos.items() if v is not None}

    return Response(json.dumps(datos, ensure_ascii=False, indent=2),
                    mimetype='application/manifest+json')


# =============================================================================
# RUTA: Módulo Gastos — Saldos + formulario + tabla de movimientos (ex /)
# URL: http://localhost:5000/gastos
# =============================================================================

@app.route('/gastos')
def gastos():
    import re
    from datetime import date

    cfg    = config.cargar_config(CONFIG_FILE)
    saldos = database.calcular_saldos()

    # ── Gauges de distribución (helper compartido con /api/saldos) ────────────
    cotizacion_valor = float(cfg.get('cotizacion_valor') or 1.0)
    gauges = _calcular_gauges(saldos, cotizacion_valor)

    mes_actual = date.today().strftime('%Y-%m')
    mes = request.args.get('mes', mes_actual)
    if not re.match(r'^\d{4}-\d{2}$', mes):
        mes = mes_actual

    year, month = int(mes[:4]), int(mes[5:])

    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year  = year if month < 12 else year + 1
    mes_prev = f"{prev_year:04d}-{prev_month:02d}"
    mes_next = f"{next_year:04d}-{next_month:02d}"

    MESES_ES = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
                'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
    mes_nombre = f"{MESES_ES[month - 1]} {year}"

    vista = request.args.get('vista', 'mes')
    if vista == 'ultimos100':
        movimientos, total = database.obtener_movimientos(limite=100)
    elif vista == 'todos':
        movimientos, total = database.obtener_movimientos()
    else:
        vista = 'mes'
        movimientos, total = database.obtener_movimientos(mes=mes)

    checklist = database.verificar_gastos_fijos(mes)

    gastos_fijos_json = _gastos_fijos_json()

    return render_template('gastos.html',
        saldos=saldos,
        movimientos=movimientos,
        cfg=cfg,
        mes=mes,
        mes_prev=mes_prev,
        mes_next=mes_next,
        mes_nombre=mes_nombre,
        total_movimientos=total,
        checklist=checklist,
        gastos_fijos_json=gastos_fijos_json,
        vista=vista,
        gauges=gauges,
    )


# =============================================================================
# RUTA: API — saldos a una fecha (JSON, para recalcular sin recargar)
# URL: GET /api/saldos?hasta=YYYY-MM-DD   (sin 'hasta' = toda la base)
# =============================================================================
@app.route('/api/saldos')
def api_saldos():
    try:
        hasta = (request.args.get('hasta') or '').strip()
        # 'hasta' inválido o vacío → None: agrega toda la base (modo actual).
        if not _re.match(r'^\d{4}-\d{2}-\d{2}$', hasta):
            hasta = None

        cfg = config.cargar_config(CONFIG_FILE)
        cotizacion_valor = float(cfg.get('cotizacion_valor') or 1.0)
        saldos = database.calcular_saldos(hasta)
        gauges = _calcular_gauges(saldos, cotizacion_valor, historico=bool(hasta))

        return jsonify({
            'ok':        True,
            'saldos':    saldos,
            'gauges':    gauges,
            'historico': bool(hasta),
            'fecha':     hasta,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# =============================================================================
# RUTA: Agregar un movimiento nuevo
# URL: http://localhost:5000/agregar
# Método: POST (solo recibe datos del formulario, no muestra página)
# =============================================================================

@app.route('/agregar', methods=['POST'])
def agregar():
    try:
        fecha       = request.form['fecha']
        descripcion = request.form['descripcion']
        persona     = request.form['persona']   # 'elias' o 'mari'
        moneda      = request.form['moneda']    # 'ars' o 'usd'
        tipo        = request.form['tipo']      # 'ingreso', 'gasto' o 'cambio'
        monto       = float(request.form['monto'])

        # Cotización vigente para calcular monto_usd. Se carga una sola vez por
        # request, pero cada movimiento usa la suya según su propia moneda.
        cfg_actual = config.cargar_config(CONFIG_FILE)

        # ── Tipo "cambio": genera 2 movimientos (salida + entrada) ──
        if tipo == 'cambio':
            persona_final = request.form['persona_final']
            moneda_final  = request.form['moneda_final']
            monto_final_str = request.form.get('monto_final', '').strip()
            monto_final = float(monto_final_str) if monto_final_str else monto

            # Cada movimiento del cambio se calcula con SU propia moneda.
            monto_usd_1, cot_1 = _calcular_monto_usd(monto, moneda, cfg_actual)
            monto_usd_2, cot_2 = _calcular_monto_usd(monto_final, moneda_final, cfg_actual)

            # Movimiento 1: salida (gasto del origen)
            id1 = database.agregar_movimiento(
                fecha, descripcion, persona, moneda, 'gasto', monto,
                categoria='Cambio',
                monto_usd=monto_usd_1, cotizacion_usd_aplicada=cot_1)

            # Movimiento 2: entrada (ingreso al destino)
            id2 = database.agregar_movimiento(
                fecha, descripcion, persona_final, moneda_final, 'ingreso', monto_final,
                categoria='Cambio',
                monto_usd=monto_usd_2, cotizacion_usd_aplicada=cot_2)

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                saldos = database.calcular_saldos()
                return jsonify({
                    'ok': True,
                    'movimiento': {
                        'id':              id1,
                        'fecha':           fecha,
                        'descripcion':     descripcion,
                        'persona':         persona,
                        'moneda':          moneda,
                        'tipo':            'cambio',
                        'monto':           monto,
                        'categoria':       'Cambio',
                        'costo_envio':     0,
                        'factor_aplicado': None,
                        'cuota_numero':    None,
                        'cuota_total':     None,
                    },
                    'movimiento2': {
                        'id':              id2,
                        'persona':         persona_final,
                        'moneda':          moneda_final,
                        'monto':           monto_final,
                    },
                    'saldos': {k: float(v) for k, v in saldos.items()},
                })

            mes = request.form.get('mes', '')
            return redirect(url_for('gastos', mes=mes) if mes else url_for('gastos'))

        # ── Tipo "gasto" o "ingreso": flujo existente ──
        categoria   = request.form.get('categoria') or None
        costo_envio_str = request.form.get('costo_envio', '').strip()
        costo_envio = float(costo_envio_str) if costo_envio_str else None

        factor_aplicado = None
        if tipo == 'ingreso' and (categoria or '').lower() == 'sueldo':
            _cfg_factor = config.cargar_config(CONFIG_FILE)
            factor_aplicado = _cfg_factor.get('factor_sueldo', 0.7)

        # Lógica de cuotas
        cuotas_checkbox = request.form.get('cuotas_checkbox') == '1'
        total_cuotas_str = request.form.get('total_cuotas', '').strip()
        total_cuotas = int(total_cuotas_str) if total_cuotas_str else None

        cuota_numero = None
        cuota_total = None
        crear_fijo_cuotas = False
        fijo_cuota_id = None

        if cuotas_checkbox and total_cuotas:
            cuota_numero = 1
            cuota_total = total_cuotas
            crear_fijo_cuotas = True
        elif (categoria or '').lower() == 'fijo':
            fijo = database.obtener_gasto_fijo_por_descripcion(descripcion)
            if fijo and fijo['es_cuota']:
                cuota_numero = (fijo['cuota_actual'] or 0) + 1
                cuota_total = fijo['total_cuotas']
                fijo_cuota_id = fijo['id']

        # Cálculo de equivalente en USD (ARS/USD según la moneda del movimiento).
        monto_usd, cotizacion_aplicada = _calcular_monto_usd(monto, moneda, cfg_actual)

        nuevo_id = database.agregar_movimiento(fecha, descripcion, persona, moneda, tipo, monto, categoria, costo_envio, factor_aplicado, cuota_numero, cuota_total, monto_usd, cotizacion_aplicada)

        # Acciones post-insert de cuotas
        if crear_fijo_cuotas:
            database.agregar_gasto_fijo_cuotas(descripcion, total_cuotas)
        elif fijo_cuota_id is not None:
            database.avanzar_cuota(fijo_cuota_id)

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            saldos = database.calcular_saldos()
            return jsonify({
                'ok': True,
                'movimiento': {
                    'id':              nuevo_id,
                    'fecha':           fecha,
                    'descripcion':     descripcion,
                    'persona':         persona,
                    'moneda':          moneda,
                    'tipo':            tipo,
                    'monto':           monto,
                    'categoria':       categoria or 'No Definido',
                    'costo_envio':     costo_envio or 0,
                    'factor_aplicado': factor_aplicado,
                    'cuota_numero':    cuota_numero,
                    'cuota_total':     cuota_total,
                },
                'saldos': {k: float(v) for k, v in saldos.items()},
            })

        mes = request.form.get('mes', '')
        return redirect(url_for('gastos', mes=mes) if mes else url_for('gastos'))

    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'ok': False, 'error': str(e)}), 500
        mes = request.form.get('mes', '')
        return redirect(url_for('gastos', mes=mes) if mes else url_for('gastos'))


# =============================================================================
# RUTA: Eliminar un movimiento
# URL: http://localhost:5000/eliminar/3
# Método: POST
# =============================================================================

@app.route('/eliminar/<int:id>', methods=['POST'])
def eliminar(id):
    database.eliminar_movimiento(id)
    mes = request.args.get('mes', '')
    return redirect(url_for('gastos', mes=mes) if mes else url_for('gastos'))


# =============================================================================
# RUTA: Editar un movimiento existente
# URL: http://localhost:5000/editar/3
# Métodos: GET (mostrar formulario) y POST (guardar cambios)
# =============================================================================

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    if request.method == 'POST':
        fecha       = request.form['fecha']
        descripcion = request.form['descripcion']
        persona     = request.form['persona']
        moneda      = request.form['moneda']
        tipo        = request.form['tipo']
        monto       = float(request.form['monto'])
        categoria   = request.form.get('categoria') or None
        costo_envio_str = request.form.get('costo_envio', '').strip()
        costo_envio = float(costo_envio_str) if costo_envio_str else None

        # Recalculamos monto_usd con la cotización actual cada vez que se edita.
        cfg_actual = config.cargar_config(CONFIG_FILE)
        monto_usd, cotizacion_aplicada = _calcular_monto_usd(monto, moneda, cfg_actual)

        database.editar_movimiento(id, fecha, descripcion, persona, moneda, tipo, monto, categoria, costo_envio, monto_usd, cotizacion_aplicada)
        mes = request.form.get('mes', '') or request.args.get('mes', '')
        return redirect(url_for('gastos', mes=mes) if mes else url_for('gastos'))
    else:
        mov = database.obtener_movimiento(id)
        if mov is None:
            return redirect(url_for('gastos'))
        return render_template('editar.html', mov=mov)


# =============================================================================
# RUTA: Página de resumen
# URL: http://localhost:5000/resumen
# =============================================================================

@app.route('/resumen')
def resumen():
    _cfg                = config.cargar_config(CONFIG_FILE)
    saldos              = database.calcular_saldos()
    cotizacion_valor    = float(_cfg.get('cotizacion_valor') or 1.0)
    movimientos, _total = database.obtener_movimientos()
    gastos_fijos        = database.obtener_gastos_fijos()
    movimientos_json    = [
        {
            'id':          int(m['id']),
            'fecha':       str(m['fecha']),
            'descripcion': str(m['descripcion']),
            'persona':     str(m['persona']),
            'moneda':      str(m['moneda']),
            'tipo':        str(m['tipo']),
            'monto':       float(m['monto']),
            'categoria':   str(m['categoria']) if m['categoria'] else None,
            'costo_envio': float(m['costo_envio']) if m['costo_envio'] else None,
            # Equivalente en USD calculado al insertar/editar (cotización histórica).
            # Puede ser None en movimientos previos al backfill.
            'monto_usd':                float(m['monto_usd']) if m['monto_usd'] is not None else None,
            'cotizacion_usd_aplicada':  float(m['cotizacion_usd_aplicada']) if m['cotizacion_usd_aplicada'] is not None else None,
        }
        for m in movimientos
    ]
    gastos_fijos_json = [
        {
            'id':           int(gf['id']),
            'descripcion':  str(gf['descripcion']),
            'activo':       bool(gf['activo']),
            'es_cuota':     bool(gf['es_cuota']),
            'total_cuotas': int(gf['total_cuotas']) if gf['total_cuotas'] else None,
            'cuota_actual': int(gf['cuota_actual']) if gf['cuota_actual'] else None,
        }
        for gf in gastos_fijos
    ]
    return render_template('resumen.html', saldos=saldos,
                           movimientos_json=movimientos_json,
                           gastos_fijos_json=gastos_fijos_json,
                           cotizacion_valor=cotizacion_valor)


# =============================================================================
# MÓDULO CALENDARIO — rutas (tareas del hogar)
# =============================================================================
#
# GET  /calendario                          → página completa (template la hace frontend-dev)
# GET  /api/actividades                     → payload fresco (JSON)
# POST /api/actividades/crear               → alta
# POST /api/actividades/<id>/editar         → edición completa
# POST /api/actividades/<id>/completar      → marcar hecha (repetir o archivar)
# POST /api/actividades/<id>/reactivar      → reactivar archivada
# POST /api/actividades/<id>/eliminar       → borrado (con su historial)
#
# Todas las mutaciones responden AJAX con {'ok': True, **_act_payload()} —
# el cliente re-renderiza todo con datos frescos. Errores: {'ok': False,
# 'error': str(e)}, 400 (validación) / 500 (excepción). No-AJAX: redirect.

def _es_ajax():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _act_parsear_fecha_opcional(valor, nombre_campo):
    """Valida que `valor` sea '' o 'YYYY-MM-DD'. Lanza ValueError si es inválida."""
    valor = (valor or '').strip()
    if not valor:
        return None
    try:
        datetime.strptime(valor, '%Y-%m-%d')
    except ValueError:
        raise ValueError(f"Fecha inválida en '{nombre_campo}': {valor}")
    return valor


def _act_leer_form_comun(form):
    """Lee y valida los campos comunes a crear/editar. Devuelve dict listo
    para pasar a database.agregar_actividad / editar_actividad (mismo orden
    de parámetros salvo el id)."""
    nombre = (form.get('nombre') or '').strip()
    if not nombre:
        raise ValueError("El nombre es obligatorio.")

    area = form.get('area', '')
    if area not in CAL_AREAS:
        raise ValueError(f"Área inválida: {area}")

    responsable = form.get('responsable', '')
    if responsable not in CAL_RESPONSABLES:
        raise ValueError(f"Responsable inválido: {responsable}")

    recurrente = 1 if form.get('recurrente') == '1' else 0

    intervalo_n = None
    intervalo_u = form.get('intervalo_u') or None
    if recurrente:
        if intervalo_u not in CAL_UNIDADES:
            raise ValueError(f"Unidad de intervalo inválida: {intervalo_u}")
        intervalo_n_str = (form.get('intervalo_n') or '').strip()
        try:
            intervalo_n = int(intervalo_n_str)
        except ValueError:
            raise ValueError("El intervalo debe ser un número entero.")
        if intervalo_n <= 0:
            raise ValueError("El intervalo debe ser mayor a 0.")
    elif intervalo_u is not None and intervalo_u not in CAL_UNIDADES:
        raise ValueError(f"Unidad de intervalo inválida: {intervalo_u}")

    ultima = _act_parsear_fecha_opcional(form.get('ultima'), 'ultima')
    proxima_manual = _act_parsear_fecha_opcional(form.get('proxima_manual'), 'proxima_manual')

    avisar = 1 if form.get('avisar') == '1' else 0

    lead_dias_str = (form.get('lead_dias') or '').strip()
    try:
        lead_dias = int(lead_dias_str) if lead_dias_str else 0
    except ValueError:
        raise ValueError("lead_dias debe ser un número entero.")
    if lead_dias < 0:
        raise ValueError("lead_dias no puede ser negativo.")

    uso_nota = (form.get('uso_nota') or '').strip() or None

    return dict(
        nombre=nombre, area=area, responsable=responsable,
        recurrente=recurrente, intervalo_n=intervalo_n, intervalo_u=intervalo_u,
        ultima=ultima, proxima_manual=proxima_manual,
        avisar=avisar, lead_dias=lead_dias, uso_nota=uso_nota,
    )


@app.route('/calendario')
def calendario():
    return render_template('calendario.html',
        datos=_act_payload(),
        cal_areas=CAL_AREAS,
        cal_responsables=CAL_RESPONSABLES,
    )


@app.route('/api/actividades')
def api_actividades():
    return jsonify({'ok': True, **_act_payload()})


@app.route('/api/actividades/crear', methods=['POST'])
def api_actividades_crear():
    try:
        datos = _act_leer_form_comun(request.form)
        database.agregar_actividad(**datos)
        if _es_ajax():
            return jsonify({'ok': True, **_act_payload()})
        return redirect(url_for('calendario'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('calendario'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('calendario'))


@app.route('/api/actividades/<int:id>/editar', methods=['POST'])
def api_actividades_editar(id):
    try:
        if database.obtener_actividad(id) is None:
            raise ValueError(f"No existe la actividad {id}.")
        datos = _act_leer_form_comun(request.form)
        database.editar_actividad(id, **datos)
        if _es_ajax():
            return jsonify({'ok': True, **_act_payload()})
        return redirect(url_for('calendario'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('calendario'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('calendario'))


@app.route('/api/actividades/<int:id>/completar', methods=['POST'])
def api_actividades_completar(id):
    from datetime import date
    try:
        if database.obtener_actividad(id) is None:
            raise ValueError(f"No existe la actividad {id}.")

        fecha_hecha = (request.form.get('fecha_hecha') or '').strip()
        if not fecha_hecha:
            raise ValueError("fecha_hecha es obligatoria.")
        try:
            fecha_hecha_dt = datetime.strptime(fecha_hecha, '%Y-%m-%d').date()
        except ValueError:
            raise ValueError(f"Fecha inválida en 'fecha_hecha': {fecha_hecha}")
        if fecha_hecha_dt > date.today():
            raise ValueError("fecha_hecha no puede ser futura.")

        repetir = request.form.get('repetir') == '1'

        intervalo_n = None
        intervalo_u = request.form.get('intervalo_u') or None
        if intervalo_u is not None or (request.form.get('intervalo_n') or '').strip():
            if intervalo_u not in CAL_UNIDADES:
                raise ValueError(f"Unidad de intervalo inválida: {intervalo_u}")
            intervalo_n_str = (request.form.get('intervalo_n') or '').strip()
            try:
                intervalo_n = int(intervalo_n_str)
            except ValueError:
                raise ValueError("El intervalo debe ser un número entero.")
            if intervalo_n <= 0:
                raise ValueError("El intervalo debe ser mayor a 0.")

        database.completar_actividad(id, fecha_hecha, repetir, intervalo_n, intervalo_u)
        if _es_ajax():
            return jsonify({'ok': True, **_act_payload()})
        return redirect(url_for('calendario'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('calendario'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('calendario'))


@app.route('/api/actividades/<int:id>/reactivar', methods=['POST'])
def api_actividades_reactivar(id):
    try:
        if database.obtener_actividad(id) is None:
            raise ValueError(f"No existe la actividad {id}.")
        database.reactivar_actividad(id)
        if _es_ajax():
            return jsonify({'ok': True, **_act_payload()})
        return redirect(url_for('calendario'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('calendario'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('calendario'))


@app.route('/api/actividades/<int:id>/eliminar', methods=['POST'])
def api_actividades_eliminar(id):
    try:
        if database.obtener_actividad(id) is None:
            raise ValueError(f"No existe la actividad {id}.")
        database.eliminar_actividad(id)
        if _es_ajax():
            return jsonify({'ok': True, **_act_payload()})
        return redirect(url_for('calendario'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('calendario'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('calendario'))


# =============================================================================
# MÓDULO LACTANCIA — rutas (banco de leche)
# =============================================================================
#
# GET  /lactancia                        → página completa
# GET  /api/lactancia                    → payload fresco (JSON)
# POST /api/lactancia/crear              → alta (flujo estándar: heladera)
# POST /api/lactancia/<id>/cerrar        → marcar usada o descartada
# POST /api/lactancia/freezar            → combinar heladeras tildadas → 1 freezer
# POST /api/lactancia/<id>/reabrir       → deshacer un cierre (traslado: completo)
# POST /api/lactancia/<id>/editar        → corregir volumen/fecha/hora/notas
# POST /api/lactancia/<id>/eliminar      → borrado definitivo
#
# Mismo contrato que Calendario: mutaciones responden AJAX con
# {'ok': True, **_lac_payload()} (el cliente re-renderiza todo). Errores:
# {'ok': False, 'error': str(e)}, 400 (validación) / 500. No-AJAX: redirect.

@app.route('/lactancia')
def lactancia():
    return render_template('lactancia.html', datos=_lac_payload())


@app.route('/api/lactancia')
def api_lactancia():
    return jsonify({'ok': True, **_lac_payload()})


@app.route('/api/lactancia/crear', methods=['POST'])
def api_lactancia_crear():
    try:
        datos = _lac_leer_form_alta(request.form)
        _lac_validar_capacidad(datos['volumen_ml'], _lac_params())
        database.agregar_partida_lactancia(**datos)
        if _es_ajax():
            return jsonify({'ok': True, **_lac_payload()})
        return redirect(url_for('lactancia'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('lactancia'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('lactancia'))


@app.route('/api/lactancia/<int:id>/cerrar', methods=['POST'])
def api_lactancia_cerrar(id):
    try:
        partida = database.obtener_partida_lactancia(id)
        if partida is None:
            raise ValueError(f"No existe la partida {id}.")
        if partida['motivo_cierre']:
            raise ValueError("La partida ya está cerrada.")

        motivo = request.form.get('motivo', '')
        if motivo not in ('usada', 'descartada'):
            raise ValueError(f"Motivo de cierre inválido: {motivo}")

        fecha_cierre = _lac_parsear_fecha_cierre(request.form.get('fecha_cierre'))
        notas = (request.form.get('notas') or '').strip()[:200] or None

        # Consumo real de León (opcional, solo 'usada'): cuántos ml tomó de la
        # bolsa. El resto es desperdicio. Sin dato = se asume que tomó todo.
        consumido_ml = None
        if motivo == 'usada':
            crudo = (request.form.get('consumido_ml') or '').strip()
            if crudo:
                try:
                    consumido_ml = int(crudo)
                except ValueError:
                    raise ValueError("El consumo (ml) debe ser un número entero.")
                if not 0 <= consumido_ml <= partida['volumen_ml']:
                    raise ValueError(
                        f"El consumo debe estar entre 0 y {partida['volumen_ml']} ml "
                        "(lo que tenía la bolsa).")

        database.cerrar_partida_lactancia(id, motivo, fecha_cierre, notas, consumido_ml)
        if _es_ajax():
            return jsonify({'ok': True, **_lac_payload()})
        return redirect(url_for('lactancia'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('lactancia'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('lactancia'))


@app.route('/api/lactancia/<int:id>/jardin', methods=['POST'])
def api_lactancia_jardin(id):
    """Marca o desmarca una partida como que está en el jardín.

    Vale en las dos ubicaciones: el back up congelado que queda en el freezer de
    allá, y la bolsita que se bajó acá y se fue con León. No cierra nada ni la
    mueve de lista: sigue contando como stock. Lo único que cambia es que no la
    tenemos en casa. Es reversible con el mismo botón (volvió a casa), así que
    no pide fecha ni confirmación."""
    try:
        partida = database.obtener_partida_lactancia(id)
        if partida is None:
            raise ValueError(f"No existe la partida {id}.")
        if partida['motivo_cierre']:
            raise ValueError("La partida ya está cerrada.")

        en_jardin = (request.form.get('en_jardin') or '').strip() == '1'
        database.marcar_jardin_lactancia(id, en_jardin)
        if _es_ajax():
            return jsonify({'ok': True, **_lac_payload()})
        return redirect(url_for('lactancia'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('lactancia'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('lactancia'))


@app.route('/api/lactancia/freezar', methods=['POST'])
def api_lactancia_freezar():
    """Freezar en bloque: combina las partidas de heladera tildadas en UNA
    partida nueva de freezer (volumen = suma; fecha/hora de extracción = la
    más vieja, que es la que define el vencimiento — criterio conservador).
    Acción SIEMPRE manual (botón), nunca automática."""
    from datetime import date
    try:
        params = _lac_params()
        ahora = datetime.now()
        crudo = (request.form.get('ids') or '').strip()
        try:
            ids = [int(x) for x in crudo.split(',') if x.strip()]
        except ValueError:
            raise ValueError(f"Ids inválidos: {crudo}")
        if not ids:
            raise ValueError("Tildá al menos una partida de heladera para freezar.")

        # Una partida VENCIDA igual se puede freezar, pero solo si la usuaria
        # confirma que en la realidad se pasó al freezer antes de vencerse
        # (caso típico: se freezó a término y se cargó en la app más tarde).
        # Sin esa confirmación explícita, se rechaza como antes.
        confirmar_vencidas = request.form.get('confirmar_vencidas') == '1'
        partidas = []
        vencidas = 0
        for pid in ids:
            row = database.obtener_partida_lactancia(pid)
            if row is None:
                raise ValueError(f"No existe la partida {pid}.")
            p = dict(row)  # los helpers _lac_* esperan dict (no sqlite3.Row)
            if p['ubicacion'] != 'heladera':
                raise ValueError("Solo se freezan partidas de heladera.")
            if p['motivo_cierre']:
                raise ValueError("Una de las partidas tildadas ya está cerrada.")
            if not _lac_freezable(p, params, ahora):
                vencidas += 1   # acá solo puede ser por vencida (lo demás ya se validó)
            partidas.append(p)

        if vencidas and not confirmar_vencidas:
            raise ValueError(
                "Hay partidas vencidas entre las tildadas: confirmá que se pasaron "
                "al freezer antes de vencerse para poder freezarlas."
            )

        # Para juntar DOS o más extracciones en una misma bolsita las dos tienen
        # que estar a la misma temperatura, así que cada una necesita un mínimo
        # de horas en la heladera. Con una sola partida no aplica (no se mezcla
        # nada) y con el parámetro en 0 la usuaria pidió que no lo verifiquemos.
        if len(partidas) >= 2 and params['combinar_min_horas'] > 0:
            minimo = params['combinar_min_horas']
            for p in partidas:
                horas = _lac_horas_en_heladera(p, ahora)
                if horas < minimo:
                    falta = minimo - horas
                    raise ValueError(
                        f"La bolsita de {p['volumen_ml']} ml lleva "
                        f"{_horas_texto(horas)} en la heladera y para juntarla con "
                        f"otra necesita {minimo} h. Faltan {_horas_texto(falta)}.")

        volumen_ml = sum(p['volumen_ml'] for p in partidas)
        if volumen_ml > 2000:
            raise ValueError("El volumen combinado supera los 2000 ml; freezá en tandas.")
        _lac_validar_capacidad(volumen_ml, params)

        # La más vieja: fecha asc, luego hora asc (hora NULL primero = conservador)
        mas_vieja = min(partidas,
                        key=lambda p: (p['fecha_extraccion'], p['hora_extraccion'] or ''))
        database.combinar_partidas_lactancia(
            ids, mas_vieja['fecha_extraccion'], mas_vieja['hora_extraccion'],
            volumen_ml, date.today().isoformat())
        if _es_ajax():
            return jsonify({'ok': True, **_lac_payload()})
        return redirect(url_for('lactancia'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('lactancia'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('lactancia'))


@app.route('/api/lactancia/<int:id>/bajar', methods=['POST'])
def api_lactancia_bajar(id):
    """Baja una bolsa del freezer a la heladera para descongelar: crea una
    partida de heladera tipo 'descongelada' (vence a las N horas de bajarla,
    no desde la extracción) y cierra la de freezer como trasladada. Como todo
    aviso del módulo, el vencimiento NO bloquea: una bolsa que 'vence pronto' o
    ya venció igual se puede bajar — la usuaria decide."""
    from datetime import date
    try:
        database.bajar_partida_lactancia(id, date.today().isoformat())
        if _es_ajax():
            return jsonify({'ok': True, **_lac_payload()})
        return redirect(url_for('lactancia'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('lactancia'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('lactancia'))


@app.route('/api/lactancia/recordatorio', methods=['POST'])
def api_lactancia_recordatorio():
    """Guarda la config del recordatorio nocturno de bajar bolsitas: activo
    (modo jardín) + hora (HH:MM). Devuelve el payload fresco para re-renderizar
    y refrescar la campana."""
    try:
        activo = request.form.get('activo') in ('1', 'true', 'on', 'True')
        hora = (request.form.get('hora') or '').strip()
        try:
            datetime.strptime(hora, '%H:%M')
        except ValueError:
            raise ValueError("La hora del recordatorio debe ser HH:MM (ej. 21:00).")
        cambios = {
            'lactancia_recordatorio_activo': activo,
            'lactancia_recordatorio_hora':   hora,
        }
        dias_raw = request.form.get('dias')
        if dias_raw is not None:
            try:
                dias = sorted({int(d) for d in dias_raw.split(',') if d.strip() != ''})
            except ValueError:
                raise ValueError("Los días del recordatorio no son válidos.")
            if any(d < 0 or d > 6 for d in dias):
                raise ValueError("Los días del recordatorio no son válidos.")
            cambios['lactancia_recordatorio_dias'] = ','.join(str(d) for d in dias)
        config.guardar_config(cambios, CONFIG_FILE)
        if _es_ajax():
            return jsonify({'ok': True, **_lac_payload()})
        return redirect(url_for('lactancia'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('lactancia'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('lactancia'))


@app.route('/api/lactancia/bebe', methods=['POST'])
def api_lactancia_bebe():
    """Guarda el perfil del bebé: nombre + fecha de nacimiento (YYYY-MM-DD,
    opcional, no futura). Devuelve el payload fresco para re-renderizar."""
    try:
        nombre = (request.form.get('nombre') or '').strip()[:40]
        fnac = (request.form.get('fecha_nacimiento') or '').strip()
        if fnac:
            try:
                nac = datetime.strptime(fnac, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError("La fecha de nacimiento debe ser una fecha válida (día/mes/año).")
            if nac > datetime.now().date():
                raise ValueError("La fecha de nacimiento no puede ser futura.")
        config.guardar_config({
            'bebe_nombre': nombre,           # vacío → la UI usa "el bebé"
            'bebe_fecha_nacimiento': fnac,
        }, CONFIG_FILE)
        if _es_ajax():
            return jsonify({'ok': True, **_lac_payload()})
        return redirect(url_for('lactancia'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('lactancia'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('lactancia'))


# ── Descarga: la tabla día a día, para abrir en Excel ────────────────────────
# Un renglón por cada día de vida de León (aunque ese día no haya pasado nada),
# así se puede mirar la evolución completa y hacer gráficos aparte.
# Detalles que hacen que Excel la abra bien de una: empieza con la marca
# invisible (BOM) — sin eso rompe los acentos — y el separador es ';', que es
# lo que espera el Excel en castellano. Las fechas en día/mes/año.
def _csv_campo(valor, sep):
    """Un valor listo para el CSV: se entrecomilla solo si hace falta."""
    texto = '' if valor is None else str(valor)
    if any(c in texto for c in (sep, '"', '\n', '\r')):
        return '"' + texto.replace('"', '""') + '"'
    return texto


@app.route('/descargar/dia-a-dia.csv')
def descargar_dia_a_dia():
    tabla = _lac_dia_a_dia()
    sep = ';'

    def dmy(iso):
        d = datetime.strptime(iso, '%Y-%m-%d').date()
        return f"{d.day:02d}/{d.month:02d}/{d.year}"

    encabezados = ['Fecha', 'Día de vida', 'Mes de vida',
                   'ml extraídos', 'ml tomados', 'ml descartados']
    lineas = [sep.join(_csv_campo(h, sep) for h in encabezados)]
    for f in tabla['filas']:
        lineas.append(sep.join(_csv_campo(v, sep) for v in (
            dmy(f['fecha']), f['dia_vida'], f['mes_vida'],
            f['extraido_ml'], f['tomado_ml'], f['descartado_ml'],
        )))
    t = tabla['totales']
    lineas.append(sep.join(_csv_campo(v, sep) for v in (
        'Totales', '', '',
        t['extraido_ml'], t['tomado_ml'], t['descartado_ml'],
    )))

    csv = '\ufeff' + '\r\n'.join(lineas) + '\r\n'
    nombre = f"lactancia-dia-a-dia-{datetime.now().date().isoformat()}.csv"
    return Response(csv, mimetype='text/csv', headers={
        'Content-Disposition': f'attachment; filename="{nombre}"',
        'Cache-Control': 'no-store',
    })


@app.route('/api/lactancia/config', methods=['POST'])
def api_lactancia_config():
    """Guarda el panel "Ajustes" del módulo: tiempos de conservación, ventanas
    de aviso, mínimo para combinar, capacidad de bolsitas y confirmaciones.

    Solo se tocan los campos que vengan en el formulario, así que cada grupo de
    la pantalla puede guardarse por su cuenta sin pisar el resto."""
    try:
        campos = {}

        for corto, clave in LAC_PARAMS_NUM:
            if corto not in request.form:
                continue
            crudo = (request.form.get(corto) or '').strip()
            try:
                valor = int(crudo)
            except ValueError:
                raise ValueError(f"«{corto.replace('_', ' ')}» tiene que ser un número entero.")
            minimo, maximo = config.LIMITES_LACTANCIA[corto]
            if not minimo <= valor <= maximo:
                raise ValueError(
                    f"«{corto.replace('_', ' ')}» tiene que estar entre {minimo} y {maximo}.")
            campos[clave] = valor

        for corto, clave in LAC_PARAMS_BOOL:
            if corto in request.form:
                campos[clave] = request.form.get(corto) in ('1', 'true', 'on', 'True')

        if not campos:
            raise ValueError("No llegó ninguna configuración para guardar.")

        # Coherencia: avisar ANTES de que venza, no después. Se valida sobre la
        # mezcla de lo guardado y lo que llega, porque el formulario puede mandar
        # un solo grupo (ej. cambiar el aviso sin tocar el vencimiento).
        nuevos = {**_lac_params(), **{c: campos[k] for c, k in LAC_PARAMS_NUM if k in campos}}
        if nuevos['aviso_heladera_horas'] > nuevos['heladera_horas']:
            raise ValueError("El aviso de la heladera no puede ser mayor que el "
                             "tiempo de vencimiento en la heladera.")
        if nuevos['aviso_descongelada_horas'] > nuevos['descongelada_horas']:
            raise ValueError("El aviso de la leche descongelada no puede ser mayor "
                             "que su tiempo de vencimiento.")
        if nuevos['aviso_freezer_dias'] > nuevos['freezer_meses'] * 30:
            raise ValueError("El aviso del freezer no puede ser mayor que el tiempo "
                             "de vencimiento en el freezer.")

        config.guardar_config(campos, CONFIG_FILE)
        if _es_ajax():
            return jsonify({'ok': True, **_lac_payload()})
        return redirect(url_for('lactancia'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('lactancia'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('lactancia'))


@app.route('/api/lactancia/<int:id>/reabrir', methods=['POST'])
def api_lactancia_reabrir(id):
    try:
        partida = database.obtener_partida_lactancia(id)
        if partida is None:
            raise ValueError(f"No existe la partida {id}.")
        if not partida['motivo_cierre']:
            raise ValueError("La partida no está cerrada.")
        database.reabrir_partida_lactancia(id)
        if _es_ajax():
            return jsonify({'ok': True, **_lac_payload()})
        return redirect(url_for('lactancia'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('lactancia'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('lactancia'))


@app.route('/api/lactancia/<int:id>/editar', methods=['POST'])
def api_lactancia_editar(id):
    try:
        partida = database.obtener_partida_lactancia(id)
        if partida is None:
            raise ValueError(f"No existe la partida {id}.")

        volumen_ml = _lac_parsear_volumen(request.form.get('volumen_ml'))
        notas = (request.form.get('notas') or '').strip()[:200]
        # Fecha/hora de extracción editables en ambas ubicaciones — corregirlas
        # recalcula el vencimiento (la extracción es su base, issue #48).
        # `cargada` sigue inmutable (auditoría).
        fecha, hora = _lac_parsear_extraccion(request.form)

        database.editar_partida_lactancia(id, fecha, hora, volumen_ml, notas)
        if _es_ajax():
            return jsonify({'ok': True, **_lac_payload()})
        return redirect(url_for('lactancia'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('lactancia'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('lactancia'))


@app.route('/api/lactancia/<int:id>/eliminar', methods=['POST'])
def api_lactancia_eliminar(id):
    try:
        if database.obtener_partida_lactancia(id) is None:
            raise ValueError(f"No existe la partida {id}.")
        database.eliminar_partida_lactancia(id)
        if _es_ajax():
            return jsonify({'ok': True, **_lac_payload()})
        return redirect(url_for('lactancia'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('lactancia'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('lactancia'))


# =============================================================================
# MÓDULO RUTINA — helpers (rutina diaria de la familia)
# =============================================================================
#
# La FAMILIA vive en la base (tabla rutina_miembros): el usuario la carga desde
# el menú de /rutina. Para los miembros marcados como bebé, la rutina se GENERA
# en el front a partir de las ventanas de sueño según la edad
# (static/rutina-sueno.js); para el resto sale de sus actividades.
# Acá solo se persisten los AJUSTES de horario por (fecha, etapa, item_id) para
# que ambos teléfonos vean lo mismo. La cascada de horarios se calcula en el
# front. La fecha-clave la define SIEMPRE el cliente (su fecha local): el server
# solo filtra por rango y hace upsert/delete — así no hay ambigüedad de
# timezone entre server y teléfonos.

# La columna `etapa` sobrevive al rework: las tres etapas viejas quedan
# aceptadas solo para no romper filas históricas de rutina_ajustes/rutina_dur/
# rutina_ocultos (nunca se dropea nada, ver docs/CONTEXT_DB.md). Todo lo que
# escribe el front nuevo usa 'plan'.
_RUT_ETAPA = 'plan'
_RUT_ETAPAS = ('plan', 'actual', 'tres', 'guarderia')
_RUT_ITEM_RE = _re.compile(r'^[a-z0-9-]{1,40}$')

_RUT_ROLES = ('mama', 'papa', 'hijo', 'otro')

# Tokens de color por miembro (nombre de la var CSS sin el prefijo --color-).
# Los tres primeros son los que ya usaba la app; los rut-p* se definen en el
# bloque scoped de Rutina en static/style.css.
_RUT_COLORES = ('persona-leon', 'persona-mari', 'persona-elias',
                'rut-p4', 'rut-p5', 'rut-p6', 'rut-p7', 'rut-p8',
                'rut-p9', 'rut-p10', 'rut-p11', 'rut-p12',
                'rut-p13', 'rut-p14', 'rut-p15', 'rut-p16')
# ⚠ Esta lista vive TRES veces y las tres tienen que coincidir: acá (valida lo
# que entra), COLOR_CICLO en static/rutina.js (arma los círculos para elegir) y
# las vars --color-rut-p* en static/style.css (los pinta). Si agregás un color
# y te olvidás de alguna, el síntoma cambia según cuál: el backend lo rechaza
# con "Color inválido", el círculo no aparece, o aparece transparente.

# Frecuencia de una actividad, tal como la guarda la base: 7 chars '0'/'1' con
# LUNES primero (la grilla de la UI arranca en lunes, no en domingo) y 12 chars
# con enero primero. Quién los interpreta es actividadAplica() en rutina.js.
_RUT_DIAS_RE = _re.compile(r'^[01]{7}$')
_RUT_MESES_RE = _re.compile(r'^[01]{12}$')


def _rut_semana_servidor():
    """Domingo..sábado (ISO) de la semana que contiene a hoy. Solo fallback
    para cuando el cliente no manda rango (p.ej. GET /rutina inicial)."""
    from datetime import date
    hoy = date.today()
    desde = hoy - timedelta(days=(hoy.weekday() + 1) % 7)  # weekday(): lunes=0
    return desde.isoformat(), (desde + timedelta(days=6)).isoformat()


def _rut_parsear_fecha(valor, campo):
    """Valida que `valor` sea 'YYYY-MM-DD' real (rechaza 2026-02-31)."""
    valor = (valor or '').strip()
    try:
        datetime.strptime(valor, '%Y-%m-%d')
    except ValueError:
        raise ValueError(f"Fecha inválida en '{campo}': {valor}")
    return valor


def _rut_parsear_rango(fuente):
    """Lee desde/hasta (form o query). Default: semana del servidor.
    Tope de 31 días como defensa contra rangos absurdos."""
    desde = fuente.get('desde')
    hasta = fuente.get('hasta')
    if not desde or not hasta:
        return _rut_semana_servidor()
    desde = _rut_parsear_fecha(desde, 'desde')
    hasta = _rut_parsear_fecha(hasta, 'hasta')
    if hasta < desde:
        raise ValueError("Rango inválido: 'hasta' es anterior a 'desde'.")
    dias = (datetime.strptime(hasta, '%Y-%m-%d') - datetime.strptime(desde, '%Y-%m-%d')).days
    if dias > 31:
        raise ValueError("Rango demasiado largo (máximo 31 días).")
    return desde, hasta


def _rut_edad(fecha_nacimiento, hoy=None):
    """Edad de un miembro + datos de cumpleaños para la tarjeta de saludo.

    Reusa _edad_desde (el mismo cálculo que el perfil del bebé de Lactancia) y
    le suma lo propio de Rutina: si hoy cumple y cuántos cumple. El "cumple
    hoy" del 29/2 se resuelve el 28/2 en los años no bisiestos, así no se saltea.
    """
    if hoy is None:
        hoy = date.today()
    if isinstance(hoy, datetime):
        hoy = hoy.date()

    edad = _edad_desde(fecha_nacimiento, hoy)
    edad['cumple_hoy'] = False
    edad['cumple_anios'] = None
    if edad['dias'] is None:
        return edad

    nac = datetime.strptime(edad['fecha_nacimiento'], '%Y-%m-%d').date()
    dia_cumple = nac.day
    if nac.month == 2 and nac.day == 29:
        try:
            date(hoy.year, 2, 29)
        except ValueError:
            dia_cumple = 28
    if hoy.month == nac.month and hoy.day == dia_cumple:
        edad['cumple_hoy'] = True
        edad['cumple_anios'] = hoy.year - nac.year
    return edad


def _rut_miembros(hoy=None):
    """La familia, con la edad y el cumpleaños ya derivados para la UI."""
    salida = []
    for fila in database.obtener_miembros_rutina():
        m = dict(fila)
        m['es_bebe'] = bool(m['es_bebe'])
        m['activo'] = bool(m['activo'])
        m.update(_rut_edad(m['fecha_nacimiento'], hoy))
        salida.append(m)
    return salida


def _rut_hora_a_min(valor, default_min):
    """'HH:MM' → minutos desde 00:00. Si viene basura, cae al default."""
    try:
        h, m = str(valor or '').strip().split(':')
        minutos = int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return default_min
    return minutos if 0 <= minutos <= 1439 else default_min


def _rut_config(cfg=None):
    """Preferencias de la hoja: inicio de la noche y del día (las usan el motor
    de ventanas de sueño y el fondo día/noche) + interruptor de cumpleaños."""
    if cfg is None:
        cfg = config.cargar_config(CONFIG_FILE)
    hora_noche = str(cfg.get('rutina_hora_noche',
                             config.DEFAULTS['rutina_hora_noche']) or '').strip()
    hora_amanecer = str(cfg.get('rutina_hora_amanecer',
                                config.DEFAULTS['rutina_hora_amanecer']) or '').strip()
    return {
        'hora_noche': hora_noche or config.DEFAULTS['rutina_hora_noche'],
        'hora_amanecer': hora_amanecer or config.DEFAULTS['rutina_hora_amanecer'],
        'noche_min': _rut_hora_a_min(hora_noche, 1200),
        'amanecer_min': _rut_hora_a_min(hora_amanecer, 390),
        'cumple_activo': bool(cfg.get('rutina_cumple_activo',
                                      config.DEFAULTS['rutina_cumple_activo'])),
    }


def _rut_payload(desde, hasta):
    """Ajustes del rango como dict anidado: fecha → etapa → item_id → minutos.
    Incluye también la familia (con edades), las preferencias de la hoja, las
    tareas añadidas, los ítems quitados (modo edición) y las actividades del
    Calendario cuya próxima fecha es HOY (para la tarjeta "Hoy por calendario",
    que ofrece añadirlas a la rutina)."""
    from datetime import date
    hoy = date.today().isoformat()
    ajustes = {}
    for fila in database.obtener_ajustes_rutina(desde, hasta):
        ajustes.setdefault(fila['fecha'], {}) \
               .setdefault(fila['etapa'], {})[fila['item_id']] = fila['inicio_min']
    duraciones = {}
    for fila in database.obtener_duraciones_rutina(desde, hasta):
        duraciones.setdefault(fila['fecha'], {}) \
                  .setdefault(fila['etapa'], {})[fila['item_id']] = fila['dur_min']
    calendario = []
    for a in database.obtener_actividades(incluir_terminadas=False):
        act = _act_enriquecer(a)
        if act['proxima_fecha'] == hoy:
            calendario.append({'id': act['id'], 'nombre': act['nombre'],
                               'responsable': act['responsable']})
    return {'ajustes': ajustes, 'duraciones': duraciones, 'hoy': hoy,
            'desde': desde, 'hasta': hasta,
            'miembros': _rut_miembros(),
            'actividades': database.obtener_actividades_rutina(),
            'config': _rut_config(),
            'tareas': [dict(f) for f in database.obtener_tareas_rutina(desde, hasta)],
            'ocultos': [dict(f) for f in database.obtener_ocultos_rutina(desde, hasta)],
            'calendario': calendario}


def _rut_parsear_fecha_opcional(valor, campo):
    """'' = permanente (todos los días); si no, fecha YYYY-MM-DD válida."""
    valor = (valor or '').strip()
    if valor == '':
        return ''
    return _rut_parsear_fecha(valor, campo)


def _rut_miembro_id(valor, campo='miembro_id'):
    """Valida que `valor` sea el id de un miembro activo de la familia.
    Reemplaza a la vieja tupla fija ('leon', 'mama', 'papa')."""
    try:
        miembro_id = int(str(valor or '').strip())
    except ValueError:
        raise ValueError(f"{campo} debe ser el id de un miembro.")
    ids = {fila['id'] for fila in database.obtener_miembros_rutina()}
    if miembro_id not in ids:
        raise ValueError(f"No existe un miembro activo con id {miembro_id}.")
    return miembro_id


def _rut_ids_lista(valor, campo, excluir=None, tope=8):
    """'3,7' → [3, 7]: lista de ids de miembros activos, sin repetidos y sin
    `excluir` (el dueño de la actividad, o el propio bebé). Vacío → []. Una
    sola query para todos, a diferencia de _rut_miembro_id(), que valida uno.
    Lo usan los participantes de una actividad compartida y la lista de quién
    acompaña a un bebé en las tomas."""
    crudo = str(valor or '').strip()
    if not crudo:
        return []
    ids = {fila['id'] for fila in database.obtener_miembros_rutina()}
    salida = []
    for parte in crudo.split(','):
        parte = parte.strip()
        if not parte:
            continue
        try:
            miembro_id = int(parte)
        except ValueError:
            raise ValueError(f"{campo} debe ser una lista de ids de miembros.")
        if miembro_id not in ids:
            raise ValueError(f"No existe un miembro activo con id {miembro_id}.")
        if excluir is not None and miembro_id == int(excluir):
            continue
        if miembro_id not in salida:
            salida.append(miembro_id)
    if len(salida) > tope:
        raise ValueError(f"Demasiados en {campo} (máximo {tope}).")
    return salida


def _rut_leer_form_tarea(form):
    """Valida el form de /api/rutina/tarea/crear. Lanza ValueError si falla."""
    etapa = (form.get('etapa') or '').strip()
    if etapa not in _RUT_ETAPAS:
        raise ValueError(f"Etapa inválida: {etapa}")
    # `usuario` pasó de ser un string fijo a ser el id del miembro. La columna
    # sigue siendo TEXT, así que se guarda el id como string.
    usuario = str(_rut_miembro_id(form.get('usuario'), 'usuario'))
    titulo = (form.get('titulo') or '').strip()
    if not 1 <= len(titulo) <= 60:
        raise ValueError("El título debe tener entre 1 y 60 caracteres.")
    emoji = (form.get('emoji') or '').strip()[:8]   # emoji compuestos ocupan varios chars
    try:
        inicio_min = int(form.get('inicio_min', ''))
    except ValueError:
        raise ValueError("inicio_min debe ser un entero (minutos desde 00:00).")
    if not 0 <= inicio_min <= 1439:
        raise ValueError(f"inicio_min fuera de rango (0..1439): {inicio_min}")
    try:
        dur = int(form.get('dur', ''))
    except ValueError:
        raise ValueError("dur debe ser un entero (minutos).")
    if not 5 <= dur <= 720:
        raise ValueError(f"Duración fuera de rango (5..720): {dur}")
    fecha = _rut_parsear_fecha_opcional(form.get('fecha'), 'fecha')
    return etapa, usuario, titulo, emoji, inicio_min, dur, fecha


def _rut_leer_form_ajuste(form):
    """Valida el form de /api/rutina/ajustar. Lanza ValueError si algo falla."""
    fecha = _rut_parsear_fecha(form.get('fecha'), 'fecha')
    etapa = (form.get('etapa') or '').strip()
    if etapa not in _RUT_ETAPAS:
        raise ValueError(f"Etapa inválida: {etapa}")
    item_id = (form.get('item_id') or '').strip()
    if not _RUT_ITEM_RE.match(item_id):
        raise ValueError(f"item_id inválido: {item_id}")
    # Ya no hay ítems "derivados no editables": con la familia en la base, cada
    # ítem tiene id propio ('b<miembro>-siesta1' generado, 'a<actividad>'
    # cargado) y todos se ajustan igual. Una actividad compartida es UN solo
    # ítem: moverla desde cualquiera de las dos rutinas la mueve en ambas, que
    # es lo que se espera de "la teta involucra al bebé y a mamá".
    try:
        inicio_min = int(form.get('inicio_min', ''))
    except ValueError:
        raise ValueError("inicio_min debe ser un entero (minutos desde 00:00).")
    if not 0 <= inicio_min <= 2879:
        raise ValueError(f"inicio_min fuera de rango (0..2879): {inicio_min}")
    return fecha, etapa, item_id, inicio_min


def _rut_leer_form_miembro(form):
    """Valida el form de alta/edición de un miembro de la familia."""
    nombre = (form.get('nombre') or '').strip()
    if not 1 <= len(nombre) <= 40:
        raise ValueError("El nombre debe tener entre 1 y 40 caracteres.")

    rol = (form.get('rol') or '').strip()
    if rol not in _RUT_ROLES:
        raise ValueError(f"Rol inválido: {rol}")

    es_bebe = 1 if (form.get('es_bebe') or '').strip() in ('1', 'true', 'on') else 0
    if es_bebe and rol != 'hijo':
        raise ValueError("Solo un hijo puede marcarse como bebé.")

    fecha_nacimiento = _rut_parsear_fecha_opcional(
        form.get('fecha_nacimiento'), 'fecha_nacimiento')
    if fecha_nacimiento:
        nac = datetime.strptime(fecha_nacimiento, '%Y-%m-%d').date()
        if nac > date.today():
            raise ValueError("La fecha de nacimiento no puede ser futura.")
    elif es_bebe:
        # Sin fecha no hay edad, y sin edad no hay ventana de sueño: la rutina
        # del bebé no se podría generar.
        raise ValueError("Para un bebé hace falta la fecha de nacimiento.")

    dibujo = (form.get('dibujo') or '').strip()[:30]

    color_token = (form.get('color_token') or '').strip()
    if color_token and color_token not in _RUT_COLORES:
        raise ValueError(f"Color inválido: {color_token}")

    try:
        ancla_min = int(form.get('ancla_min', '390') or 390)
    except ValueError:
        raise ValueError("ancla_min debe ser un entero (minutos desde 00:00).")
    if not 0 <= ancla_min <= 1439:
        raise ValueError(f"ancla_min fuera de rango (0..1439): {ancla_min}")

    # Quién lo acompaña en las tomas. Solo tiene sentido en un bebé: si se
    # destilda "es bebé" se fuerza '' en vez de dejar el dato colgado, que
    # volvería a aplicarse solo si algún día se vuelve a tildar.
    propio = str(form.get('id') or '').strip()
    acompanan = ''
    if es_bebe:
        ids = _rut_ids_lista(form.get('acompanan'), 'acompanan',
                             excluir=propio if propio.isdigit() else None, tope=3)
        acompanan = ','.join(str(i) for i in ids)

    return (nombre, rol, es_bebe, fecha_nacimiento, dibujo, color_token,
            ancla_min, acompanan)


def _rut_bits(valor, regex, campo, defecto):
    """Valida un patrón de frecuencia ('1111100' / '111111111111').
    Rechaza el todo-ceros: una actividad sin ningún día (o sin ningún mes) no
    aparecería NUNCA y no habría forma de darse cuenta mirando la pantalla."""
    bits = (valor or '').strip() or defecto
    if not regex.match(bits):
        raise ValueError(f"{campo} inválido: {bits}")
    if '1' not in bits:
        raise ValueError(f"Elegí al menos un {campo}.")
    return bits


def _rut_leer_form_actividad(form):
    """Valida el form de alta/edición de una actividad con frecuencia."""
    miembro_id = _rut_miembro_id(form.get('miembro_id'))

    titulo = (form.get('titulo') or '').strip()
    if not 1 <= len(titulo) <= 60:
        raise ValueError("El título debe tener entre 1 y 60 caracteres.")

    # La librería de dibujos vive en el front; acá solo se guarda la clave (o
    # el emoji suelto). dibujoHtml() cae con gracia si no la reconoce.
    dibujo = (form.get('dibujo') or '').strip()[:30]

    try:
        inicio_min = int(form.get('inicio_min', ''))
    except ValueError:
        raise ValueError("inicio_min debe ser un entero (minutos desde 00:00).")
    if not 0 <= inicio_min <= 1439:
        raise ValueError(f"inicio_min fuera de rango (0..1439): {inicio_min}")

    try:
        dur_min = int(form.get('dur_min', ''))
    except ValueError:
        raise ValueError("dur_min debe ser un entero (minutos).")
    if not 5 <= dur_min <= 720:
        raise ValueError(f"Duración fuera de rango (5..720): {dur_min}")

    dias = _rut_bits(form.get('dias'), _RUT_DIAS_RE, 'día de la semana', '1111111')
    meses = _rut_bits(form.get('meses'), _RUT_MESES_RE, 'mes', '111111111111')

    desde, hasta, anual = _rut_leer_rango_anual(form)

    nota = (form.get('nota') or '').strip()[:200]

    # Con quién se comparte. El dueño se descarta si viniera en la lista: la
    # actividad ya sale en su línea de tiempo y se duplicaría.
    participantes = _rut_ids_lista(form.get('participantes'), 'participantes',
                                   excluir=miembro_id)

    return (miembro_id, titulo, dibujo, inicio_min, dur_min, dias, meses,
            desde, hasta, anual, nota, participantes)


def _rut_leer_rango_anual(form):
    """Rango de vigencia + repetición anual. Lo comparten las actividades y los
    recesos, con la MISMA regla en los dos lados.

    ⚠ Los campos se llaman `vig_desde` / `vig_hasta` y NO `desde` / `hasta`:
    esos dos ya están tomados por el rango de la SEMANA QUE SE ESTÁ MIRANDO, que
    postAccion() le agrega a todas las mutaciones del módulo y que
    _rut_parsear_rango() limita a 31 días. Con el nombre corto, una escuela del
    1/3 al 15/12 se rechazaba con "Rango demasiado largo"."""
    desde = _rut_parsear_fecha_opcional(form.get('vig_desde'), 'desde')
    hasta = _rut_parsear_fecha_opcional(form.get('vig_hasta'), 'hasta')
    anual = 1 if (form.get('anual') or '').strip() in ('1', 'true', 'on') else 0
    # ⚠ Si es anual NO se comparan: un rango anual puede cruzar el año nuevo
    # (una temporada de verano del 1/12 al 28/2 es válida y da hasta < desde).
    # dentroAnual() en rutina.js ya contempla ese caso.
    if not anual and desde and hasta and hasta < desde:
        raise ValueError("La fecha de fin no puede ser anterior a la de inicio.")
    return desde, hasta, anual


def _rut_leer_form_pausa(form):
    """Valida el form de alta de un receso (las vacaciones de la escuela)."""
    try:
        actividad_id = int(str(form.get('actividad_id') or '').strip())
    except ValueError:
        raise ValueError("actividad_id debe ser el id de una actividad.")
    if not database.actividad_rutina_existe(actividad_id):
        raise ValueError(f"No existe una actividad con id {actividad_id}.")

    desde, hasta, anual = _rut_leer_rango_anual(form)
    if not desde or not hasta:
        raise ValueError("Un receso necesita fecha de inicio y de fin.")

    motivo = (form.get('motivo') or '').strip()[:60]
    return actividad_id, desde, hasta, anual, motivo


# =============================================================================
# MÓDULO RUTINA — rutas
# =============================================================================
#
# GET  /rutina             → página completa (ajustes de la semana actual)
# GET  /api/rutina         → payload fresco; query desde/hasta (fechas del cliente)
# POST /api/rutina/ajustar → upsert de un ajuste (fecha, etapa, item_id, inicio_min)
# POST /api/rutina/reset   → borra los ajustes de fecha+etapa ("↺ Plan original")
# POST /api/rutina/soltar  → borra el ajuste de UN ítem ("Soltar" del popover)
#
# Mismo contrato que Lactancia: mutaciones responden AJAX con
# {'ok': True, **_rut_payload(desde, hasta)} (el cliente re-renderiza todo).
# Errores: {'ok': False, 'error': str(e)}, 400 (validación) / 500. No-AJAX:
# redirect. Los POST reciben también desde/hasta para responder el rango
# que el cliente tiene en pantalla.

@app.route('/rutina')
def rutina():
    desde, hasta = _rut_semana_servidor()
    return render_template('rutina.html', datos=_rut_payload(desde, hasta))


@app.route('/api/rutina')
def api_rutina():
    try:
        desde, hasta = _rut_parsear_rango(request.args)
        return jsonify({'ok': True, **_rut_payload(desde, hasta)})
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/rutina/ajustar', methods=['POST'])
def api_rutina_ajustar():
    try:
        fecha, etapa, item_id, inicio_min = _rut_leer_form_ajuste(request.form)
        database.guardar_ajuste_rutina(fecha, etapa, item_id, inicio_min)
        if _es_ajax():
            desde, hasta = _rut_parsear_rango(request.form)
            return jsonify({'ok': True, **_rut_payload(desde, hasta)})
        return redirect(url_for('rutina'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('rutina'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('rutina'))


@app.route('/api/rutina/duracion', methods=['POST'])
def api_rutina_duracion():
    """Estirar/encoger un ítem en la línea de tiempo (drag estilo Teams).
    Misma validación que /ajustar (mismos ítems editables); dur 5..720."""
    try:
        fecha = _rut_parsear_fecha(request.form.get('fecha'), 'fecha')
        etapa = (request.form.get('etapa') or '').strip()
        if etapa not in _RUT_ETAPAS:
            raise ValueError(f"Etapa inválida: {etapa}")
        item_id = (request.form.get('item_id') or '').strip()
        if not _RUT_ITEM_RE.match(item_id):
            raise ValueError(f"item_id inválido: {item_id}")
        try:
            dur_min = int(request.form.get('dur_min', ''))
        except ValueError:
            raise ValueError("dur_min debe ser un entero (minutos).")
        if not 5 <= dur_min <= 720:
            raise ValueError(f"dur_min fuera de rango (5..720): {dur_min}")
        database.guardar_duracion_rutina(fecha, etapa, item_id, dur_min)
        if _es_ajax():
            desde, hasta = _rut_parsear_rango(request.form)
            return jsonify({'ok': True, **_rut_payload(desde, hasta)})
        return redirect(url_for('rutina'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('rutina'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('rutina'))


@app.route('/api/rutina/reset', methods=['POST'])
def api_rutina_reset():
    try:
        fecha = _rut_parsear_fecha(request.form.get('fecha'), 'fecha')
        etapa = (request.form.get('etapa') or '').strip()
        if etapa not in _RUT_ETAPAS:
            raise ValueError(f"Etapa inválida: {etapa}")
        database.borrar_ajustes_rutina(fecha, etapa)
        if _es_ajax():
            desde, hasta = _rut_parsear_rango(request.form)
            return jsonify({'ok': True, **_rut_payload(desde, hasta)})
        return redirect(url_for('rutina'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('rutina'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('rutina'))


@app.route('/api/rutina/soltar', methods=['POST'])
def api_rutina_soltar():
    """Borra el ajuste de UN ítem: lo "suelta" y vuelve a acomodarse solo.
    Es el complemento de /ajustar en la rutina generada de un bebé, donde la
    fila de rutina_ajustes es lo que convierte al bloque en un pin. Sin esto,
    la única forma de deshacer un bloque fijado era "↺ Plan original", que
    borra los ajustes de TODO el día."""
    try:
        fecha = _rut_parsear_fecha(request.form.get('fecha'), 'fecha')
        etapa = (request.form.get('etapa') or '').strip()
        if etapa not in _RUT_ETAPAS:
            raise ValueError(f"Etapa inválida: {etapa}")
        item_id = (request.form.get('item_id') or '').strip()
        if not _RUT_ITEM_RE.match(item_id):
            raise ValueError(f"item_id inválido: {item_id}")
        database.borrar_ajuste_rutina(fecha, etapa, item_id)
        if _es_ajax():
            desde, hasta = _rut_parsear_rango(request.form)
            return jsonify({'ok': True, **_rut_payload(desde, hasta)})
        return redirect(url_for('rutina'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('rutina'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('rutina'))


# --- Modo edición: tareas añadidas y quitadas --------------------------------
# POST /api/rutina/tarea/crear  → alta (fecha '' = permanente, o YYYY-MM-DD)
# POST /api/rutina/tarea/borrar → baja definitiva de una tarea añadida
# POST /api/rutina/ocultar      → quita un ítem (base, derivado o añadido)
# POST /api/rutina/restaurar    → deshace TODOS los quitados de un ítem

@app.route('/api/rutina/tarea/crear', methods=['POST'])
def api_rutina_tarea_crear():
    try:
        etapa, usuario, titulo, emoji, inicio_min, dur, fecha = \
            _rut_leer_form_tarea(request.form)
        database.crear_tarea_rutina(etapa, usuario, titulo, emoji, inicio_min, dur, fecha)
        if _es_ajax():
            desde, hasta = _rut_parsear_rango(request.form)
            return jsonify({'ok': True, **_rut_payload(desde, hasta)})
        return redirect(url_for('rutina'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('rutina'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('rutina'))


@app.route('/api/rutina/tarea/borrar', methods=['POST'])
def api_rutina_tarea_borrar():
    try:
        try:
            tarea_id = int(request.form.get('id', ''))
        except ValueError:
            raise ValueError("id de tarea inválido.")
        database.borrar_tarea_rutina(tarea_id)
        if _es_ajax():
            desde, hasta = _rut_parsear_rango(request.form)
            return jsonify({'ok': True, **_rut_payload(desde, hasta)})
        return redirect(url_for('rutina'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('rutina'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('rutina'))


@app.route('/api/rutina/ocultar', methods=['POST'])
def api_rutina_ocultar():
    try:
        etapa = (request.form.get('etapa') or '').strip()
        if etapa not in _RUT_ETAPAS:
            raise ValueError(f"Etapa inválida: {etapa}")
        item_id = (request.form.get('item_id') or '').strip()
        # A diferencia de /ajustar, acá SÍ se aceptan ids derivados de adultos
        # ('mama-*'/'papa-*'): quitar una fila vinculada es válido.
        if not _RUT_ITEM_RE.match(item_id):
            raise ValueError(f"item_id inválido: {item_id}")
        fecha = _rut_parsear_fecha_opcional(request.form.get('fecha'), 'fecha')
        database.ocultar_item_rutina(etapa, item_id, fecha)
        if _es_ajax():
            desde, hasta = _rut_parsear_rango(request.form)
            return jsonify({'ok': True, **_rut_payload(desde, hasta)})
        return redirect(url_for('rutina'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('rutina'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('rutina'))


@app.route('/api/rutina/restaurar', methods=['POST'])
def api_rutina_restaurar():
    try:
        etapa = (request.form.get('etapa') or '').strip()
        if etapa not in _RUT_ETAPAS:
            raise ValueError(f"Etapa inválida: {etapa}")
        item_id = (request.form.get('item_id') or '').strip()
        if not _RUT_ITEM_RE.match(item_id):
            raise ValueError(f"item_id inválido: {item_id}")
        database.restaurar_item_rutina(etapa, item_id)
        if _es_ajax():
            desde, hasta = _rut_parsear_rango(request.form)
            return jsonify({'ok': True, **_rut_payload(desde, hasta)})
        return redirect(url_for('rutina'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('rutina'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('rutina'))


# --- Familia y preferencias de la hoja --------------------------------------
# POST /api/rutina/miembro/crear  → alta (nombre, rol, es_bebe, fecha_nacimiento,
#                                    acompanan = quién lo acompaña en las tomas…)
# POST /api/rutina/miembro/editar → edición completa (pide id)
# POST /api/rutina/miembro/nocturnas → cuántas tomas de madrugada (id, n;
#                                    n = -1 → las que sugiere la edad)
# POST /api/rutina/miembro/borrar → baja definitiva + limpieza de sus ítems
# POST /api/rutina/ajustes        → hora de inicio de noche / amanecer / cumples
# Mismo contrato AJAX que el resto del módulo.

@app.route('/api/rutina/miembro/crear', methods=['POST'])
def api_rutina_miembro_crear():
    try:
        datos = _rut_leer_form_miembro(request.form)
        database.crear_miembro_rutina(*datos)
        if _es_ajax():
            desde, hasta = _rut_parsear_rango(request.form)
            return jsonify({'ok': True, **_rut_payload(desde, hasta)})
        return redirect(url_for('rutina'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('rutina'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('rutina'))


@app.route('/api/rutina/miembro/editar', methods=['POST'])
def api_rutina_miembro_editar():
    try:
        miembro_id = _rut_miembro_id(request.form.get('id'), 'id')
        nombre, rol, es_bebe, fnac, dibujo, color, ancla, acompanan = \
            _rut_leer_form_miembro(request.form)
        activo = 0 if (request.form.get('activo') or '1').strip() == '0' else 1
        database.editar_miembro_rutina(miembro_id, nombre, rol, es_bebe, fnac,
                                       dibujo, color, ancla, acompanan, activo)
        if _es_ajax():
            desde, hasta = _rut_parsear_rango(request.form)
            return jsonify({'ok': True, **_rut_payload(desde, hasta)})
        return redirect(url_for('rutina'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('rutina'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('rutina'))


@app.route('/api/rutina/miembro/nocturnas', methods=['POST'])
def api_rutina_miembro_nocturnas():
    """Cuántas tomas de madrugada mostrarle a un bebé ("− 2 +" de la franja
    Madrugada). `n` = -1 → las que sugiere su edad; 0..6 → las que diga el
    usuario. El tope es sanidad, no medicina: seis despertares con toma ya es
    más de lo que la tabla espera del recién nacido (3-4)."""
    try:
        miembro_id = _rut_miembro_id(request.form.get('id'), 'id')
        try:
            n = int(str(request.form.get('n') or '').strip())
        except ValueError:
            raise ValueError('n debe ser un entero (-1 = automático).')
        if n < -1 or n > 6:
            raise ValueError(f'n fuera de rango (-1..6): {n}')
        database.fijar_nocturnas_rutina(miembro_id, n)
        if _es_ajax():
            desde, hasta = _rut_parsear_rango(request.form)
            return jsonify({'ok': True, **_rut_payload(desde, hasta)})
        return redirect(url_for('rutina'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('rutina'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('rutina'))


@app.route('/api/rutina/miembro/borrar', methods=['POST'])
def api_rutina_miembro_borrar():
    """Baja definitiva. Se lleva puestas sus actividades y todos los ajustes
    de horario de sus ítems (ver borrar_miembro_rutina en database.py)."""
    try:
        miembro_id = _rut_miembro_id(request.form.get('id'), 'id')
        database.borrar_miembro_rutina(miembro_id)
        if _es_ajax():
            desde, hasta = _rut_parsear_rango(request.form)
            return jsonify({'ok': True, **_rut_payload(desde, hasta)})
        return redirect(url_for('rutina'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('rutina'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('rutina'))


# --- Actividades con frecuencia ---------------------------------------------
# POST /api/rutina/actividad/crear  → alta (miembro, título, horario, días, meses,
#                                     participantes = con quién se comparte…)
# POST /api/rutina/actividad/editar → edición completa (pide id)
# POST /api/rutina/actividad/borrar → baja definitiva + limpieza de su ítem 'a<id>'
# POST /api/rutina/pausa/crear      → receso de una actividad (vacaciones)
# POST /api/rutina/pausa/borrar     → saca un receso suelto (pide id)
# Mismo contrato AJAX que el resto del módulo. Los recesos van por rutas aparte
# porque necesitan el id de la actividad, que no existe hasta guardarla.

@app.route('/api/rutina/actividad/crear', methods=['POST'])
def api_rutina_actividad_crear():
    try:
        # ⚠ El rango de la VISTA se valida ANTES de escribir. Las rutas viejas
        # del módulo lo hacen después, y eso significa que un rango inválido
        # devuelve 400 con el alta YA hecha: el usuario ve un error y la fila
        # igual quedó. Pasó de verdad mientras se armaba este editor.
        rango = _rut_parsear_rango(request.form)
        datos = _rut_leer_form_actividad(request.form)
        database.crear_actividad_rutina(*datos)
        if _es_ajax():
            return jsonify({'ok': True, **_rut_payload(*rango)})
        return redirect(url_for('rutina'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('rutina'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('rutina'))


@app.route('/api/rutina/actividad/editar', methods=['POST'])
def api_rutina_actividad_editar():
    try:
        try:
            actividad_id = int(str(request.form.get('id') or '').strip())
        except ValueError:
            raise ValueError("id debe ser el id de una actividad.")
        if not database.actividad_rutina_existe(actividad_id):
            raise ValueError(f"No existe una actividad con id {actividad_id}.")
        rango = _rut_parsear_rango(request.form)   # antes de escribir, ver /crear
        datos = _rut_leer_form_actividad(request.form)
        activo = 0 if (request.form.get('activo') or '1').strip() == '0' else 1
        database.editar_actividad_rutina(actividad_id, *datos, activo)
        if _es_ajax():
            return jsonify({'ok': True, **_rut_payload(*rango)})
        return redirect(url_for('rutina'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('rutina'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('rutina'))


@app.route('/api/rutina/actividad/borrar', methods=['POST'])
def api_rutina_actividad_borrar():
    """Baja definitiva. Se lleva sus recesos y los ajustes de horario de su
    ítem (ver borrar_actividad_rutina en database.py)."""
    try:
        try:
            actividad_id = int(str(request.form.get('id') or '').strip())
        except ValueError:
            raise ValueError("id debe ser el id de una actividad.")
        if not database.actividad_rutina_existe(actividad_id):
            raise ValueError(f"No existe una actividad con id {actividad_id}.")
        rango = _rut_parsear_rango(request.form)   # antes de escribir, ver /crear
        database.borrar_actividad_rutina(actividad_id)
        if _es_ajax():
            return jsonify({'ok': True, **_rut_payload(*rango)})
        return redirect(url_for('rutina'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('rutina'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('rutina'))


@app.route('/api/rutina/pausa/crear', methods=['POST'])
def api_rutina_pausa_crear():
    try:
        rango = _rut_parsear_rango(request.form)   # antes de escribir, ver /crear
        datos = _rut_leer_form_pausa(request.form)
        database.crear_pausa_rutina(*datos)
        if _es_ajax():
            return jsonify({'ok': True, **_rut_payload(*rango)})
        return redirect(url_for('rutina'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('rutina'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('rutina'))


@app.route('/api/rutina/pausa/borrar', methods=['POST'])
def api_rutina_pausa_borrar():
    try:
        try:
            pausa_id = int(str(request.form.get('id') or '').strip())
        except ValueError:
            raise ValueError("id debe ser el id de un receso.")
        rango = _rut_parsear_rango(request.form)   # antes de escribir, ver /crear
        database.borrar_pausa_rutina(pausa_id)
        if _es_ajax():
            return jsonify({'ok': True, **_rut_payload(*rango)})
        return redirect(url_for('rutina'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('rutina'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('rutina'))


@app.route('/api/rutina/ajustes', methods=['POST'])
def api_rutina_ajustes():
    """Preferencias de la hoja (van a config.json, no a la base): hora de
    inicio de la noche y del amanecer + interruptor de la tarjeta de cumple."""
    try:
        noche = (request.form.get('hora_noche') or '').strip()
        amanecer = (request.form.get('hora_amanecer') or '').strip()
        for etiqueta, valor in (('hora_noche', noche), ('hora_amanecer', amanecer)):
            try:
                datetime.strptime(valor, '%H:%M')
            except ValueError:
                raise ValueError(f"Hora inválida en '{etiqueta}': {valor}")
        if _rut_hora_a_min(noche, -1) <= _rut_hora_a_min(amanecer, -1):
            raise ValueError("La noche tiene que empezar después del amanecer.")
        cumple = (request.form.get('cumple_activo') or '').strip() in ('1', 'true', 'on')
        config.guardar_config({
            'rutina_hora_noche': noche,
            'rutina_hora_amanecer': amanecer,
            'rutina_cumple_activo': cumple,
        }, CONFIG_FILE)
        if _es_ajax():
            desde, hasta = _rut_parsear_rango(request.form)
            return jsonify({'ok': True, **_rut_payload(desde, hasta)})
        return redirect(url_for('rutina'))
    except ValueError as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 400
        return redirect(url_for('rutina'))
    except Exception as e:
        if _es_ajax():
            return jsonify({'ok': False, 'error': str(e)}), 500
        return redirect(url_for('rutina'))


# =============================================================================
# RUTA: Refresco manual de la cotización del dólar
# URL: POST http://localhost:5000/api/cotizacion/refresh
# =============================================================================
#
# Llama a cotizacion.refrescar_cache(CONFIG_FILE), que consulta dolarapi.com
# y actualiza config.json con el valor nuevo (o deja el anterior si la API
# falla, marcando cotizacion_ok=false).
#
# Respuesta JSON:
#   {
#     "ok":                        bool,    # True si la API respondió
#     "mensaje":                   str,     # Mensaje legible
#     "valor":                     float|null,  # Cotización vigente en config
#     "fecha":                     str|null,    # Fecha del valor (YYYY-MM-DD)
#     "cotizacion_ok":             bool,    # Mismo valor que "ok"
#     "cotizacion_ultimo_intento": str,     # Timestamp del último intento
#   }
#
@app.route('/api/cotizacion/refresh', methods=['POST'])
def api_cotizacion_refresh():
    ok, mensaje = cotizacion.refrescar_cache(CONFIG_FILE)
    cfg = config.cargar_config(CONFIG_FILE)
    return jsonify({
        'ok':                        ok,
        'mensaje':                   mensaje,
        'valor':                     cfg.get('cotizacion_valor'),
        'fecha':                     cfg.get('cotizacion_fecha'),
        'cotizacion_ok':             cfg.get('cotizacion_ok', False),
        'cotizacion_ultimo_intento': cfg.get('cotizacion_ultimo_intento'),
    })


# =============================================================================
# RUTA: Métricas del proceso
# URL: http://localhost:5000/api/metrics
# =============================================================================

@app.route('/api/metrics')
def metrics():
    proc = psutil.Process(os.getpid())
    with proc.oneshot():
        cpu = proc.cpu_percent(interval=0.1)
        mem = proc.memory_info()
        mem_mb = mem.rss / 1024 / 1024
        mem_percent = proc.memory_percent()

    host_cpu = psutil.cpu_percent(interval=0.1)
    host_mem = psutil.virtual_memory()

    return jsonify({
        "proceso": {
            "cpu_percent":     round(cpu, 1),
            "memoria_mb":      round(mem_mb, 1),
            "memoria_percent": round(mem_percent, 1),
            "pid":             os.getpid()
        },
        "host": {
            "cpu_percent":       round(host_cpu, 1),
            "memoria_total_mb":  round(host_mem.total / 1024 / 1024),
            "memoria_usada_mb":  round(host_mem.used / 1024 / 1024),
            "memoria_percent":   round(host_mem.percent, 1)
        }
    })


# =============================================================================
# RUTA: Notificaciones (campana genérica del header)
# URL: GET http://localhost:5000/api/notificaciones
# =============================================================================
#
# Agrega los ítems de TODOS los providers registrados en NOTIF_PROVIDERS (ver
# docs/CONTEXT_NOTIFICATIONS.md). Solo lectura, sin parámetros.
#
@app.route('/api/notificaciones')
def api_notificaciones():
    items = _notificaciones()
    return jsonify({'ok': True, 'total': len(items), 'items': items})


# =============================================================================
# RUTA: Página de configuración
# URL: http://localhost:5000/settings
# =============================================================================

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    cfg = config.cargar_config(CONFIG_FILE)
    if request.method == 'POST':
        accion = request.form.get('accion')

        if accion == 'marcar_configurado':
            config.guardar_config({'first_run': False}, CONFIG_FILE)
            flash('Marcado como configurado. Reiniciá la app para aplicar los cambios.')
            return redirect(url_for('settings'))

        if accion == 'agregar_fijo':
            desc = request.form.get('descripcion_fijo', '').strip()
            if desc:
                database.agregar_gasto_fijo(desc)
                flash(f'Gasto fijo "{desc}" agregado.')
            return redirect(url_for('settings') + '#gastos-fijos')

        if accion == 'eliminar_fijo':
            fijo_id = request.form.get('fijo_id', type=int)
            if fijo_id:
                database.eliminar_gasto_fijo(fijo_id)
                flash('Gasto fijo eliminado.')
            return redirect(url_for('settings') + '#gastos-fijos')

        if accion == 'editar_fijo':
            fijo_id = request.form.get('fijo_id', type=int)
            desc    = request.form.get('descripcion_fijo', '').strip()
            activo  = 1 if request.form.get('activo') == 'on' else 0
            if fijo_id and desc:
                database.editar_gasto_fijo(fijo_id, desc, activo)
                flash('Gasto fijo actualizado.')
            return redirect(url_for('settings') + '#gastos-fijos')

        if accion == 'guardar_backup_dir':
            config.guardar_config(
                {'backup_dir': request.form.get('backup_dir', '').strip()},
                CONFIG_FILE,
            )
            flash('Carpeta de backups guardada.')
            return redirect(url_for('settings') + '#backup-db')

        # Los parámetros del banco de leche NO se configuran acá: viven en el
        # panel "Ajustes" de /lactancia (POST /api/lactancia/config), que se
        # trajo entero de la app suelta. Settings ya no los toca.

        # Guardado general: solo campos visibles en la UI de Settings.
        # ngrok / OAuth / puerto se manejan fuera (config.json) y NO se tocan acá:
        # config.guardar_config hace merge parcial, así que las claves ausentes
        # conservan su valor previo.
        nuevos = {
            'app_name':      request.form.get('app_name', cfg.get('app_name', 'Gastos Casa')).strip(),
            'factor_sueldo': float(request.form.get('factor_sueldo', cfg.get('factor_sueldo', 0.7))),
        }
        config.guardar_config(nuevos, CONFIG_FILE)
        flash('Configuración guardada.')
        return redirect(url_for('settings'))

    cfg = config.cargar_config(CONFIG_FILE)
    fijos = database.obtener_gastos_fijos(solo_activos=False)
    return render_template('settings.html', cfg=cfg, fijos=fijos, paleta_meta=PALETA_META)


# =============================================================================
# RUTA: Guardar paleta de colores desde Settings
# URL: POST http://localhost:5000/api/paleta
# =============================================================================
#
# Recibe JSON:
#   {"paleta_light": {"acento": "#...", ...}, "paleta_dark": {"acento": "#...", ...}}
#
# Valida que todos los valores sean hex de 6 dígitos (#rrggbb) y que las claves
# coincidan con las definidas en PALETA_META. Guarda en config.json.
# El render de Jinja en base.html aplica los valores al recargar.
#
@app.route('/api/paleta', methods=['POST'])
def api_paleta():
    try:
        data = request.get_json(silent=True) or {}
        light = data.get('paleta_light') or {}
        dark  = data.get('paleta_dark')  or {}

        claves = {k for k, _, _ in PALETA_META}

        def _validar(d, nombre):
            if not isinstance(d, dict):
                raise ValueError(f"{nombre} no es un objeto válido")
            for k, v in d.items():
                if k not in claves:
                    raise ValueError(f"Clave desconocida en {nombre}: {k}")
                if not isinstance(v, str) or not _HEX_RE.match(v):
                    raise ValueError(f"Color inválido en {nombre}.{k}: {v}")

        _validar(light, 'paleta_light')
        _validar(dark,  'paleta_dark')

        cfg_actual = config.cargar_config(CONFIG_FILE)
        paleta_light_nueva = dict(cfg_actual.get('paleta_light', {}))
        paleta_dark_nueva  = dict(cfg_actual.get('paleta_dark', {}))
        paleta_light_nueva.update(light)
        paleta_dark_nueva.update(dark)

        config.guardar_config({
            'paleta_light': paleta_light_nueva,
            'paleta_dark':  paleta_dark_nueva,
        }, CONFIG_FILE)

        return jsonify({'ok': True, 'mensaje': 'Paleta guardada.'})
    except ValueError as e:
        return jsonify({'ok': False, 'mensaje': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'mensaje': str(e)}), 500


# =============================================================================
# RUTAS: Backups de la base de datos (desde Settings)
# =============================================================================
#
# - GET  /api/backups            → lista los backups .db de la carpeta.
# - POST /api/backups/crear      → crea un backup manual de fondo.db.
# - POST /api/backups/restaurar  → restaura un backup elegido sobre fondo.db,
#                                   guardando antes una copia de seguridad del
#                                   estado actual (fondo_<fecha>_pre-restore.db).
#
# Compat: los backups viejos, de antes del rename 2026-07 (gastos.db →
# fondo.db), tienen prefijo `gastos_` en vez de `fondo_`. Se listan, rotan y
# reconocen igual que los nuevos — ver _listar_backups/_limpiar_backups_antiguos/
# _fecha_de_backup, todos con el patrón `(?:fondo|gastos)_`.

def _listar_backups():
    """Lista los backups .db de la carpeta configurada, del más nuevo al más viejo."""
    import re
    backup_dir = _get_backup_dir()
    items = []
    try:
        for f in os.listdir(backup_dir):
            if not (f.startswith(('fondo_', 'gastos_')) and f.endswith('.db')):
                continue
            ruta = os.path.join(backup_dir, f)
            try:
                size_mb = round(os.path.getsize(ruta) / 1024 / 1024, 2)
                mtime   = os.path.getmtime(ruta)
            except OSError:
                continue
            etiqueta = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
            if '_pre-restore' in f:
                etiqueta += ' (previo a un restore)'
            else:
                # Descripción de backup manual: lo que sigue a fondo_FECHA_HORA_
                # (o gastos_FECHA_HORA_ en backups viejos pre-rename).
                m = re.match(r'^(?:fondo|gastos)_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}_(.+)\.db$', f)
                if m:
                    etiqueta += f' — {m.group(1)}'
            items.append({'archivo': f, 'etiqueta': etiqueta, 'size_mb': size_mb, '_mtime': mtime})
    except OSError:
        pass
    items.sort(key=lambda x: x['_mtime'], reverse=True)
    for it in items:
        it.pop('_mtime', None)
    return items


@app.route('/api/backups')
def api_backups():
    return jsonify({'ok': True, 'backups': _listar_backups(), 'carpeta': _get_backup_dir()})


@app.route('/api/backups/crear', methods=['POST'])
def api_backups_crear():
    descripcion = request.form.get('descripcion', '').strip()
    nombre = hacer_backup_db('backup manual', descripcion or None)
    if nombre:
        return jsonify({'ok': True, 'mensaje': f'Backup creado: {nombre}', 'backups': _listar_backups()})
    return jsonify({'ok': False, 'mensaje': 'No se pudo crear el backup. Revisá la carpeta de backups.'}), 500


@app.route('/api/backups/restaurar', methods=['POST'])
def api_backups_restaurar():
    import sqlite3
    archivo = request.form.get('archivo', '').strip()

    # Validación anti path-traversal: solo nombre de archivo, sin separadores.
    if not archivo or os.path.basename(archivo) != archivo or not archivo.endswith('.db'):
        return jsonify({'ok': False, 'mensaje': 'Nombre de backup inválido.'}), 400

    backup_dir = _get_backup_dir()
    origen     = os.path.join(backup_dir, archivo)
    if not os.path.isfile(origen):
        return jsonify({'ok': False, 'mensaje': 'El backup elegido no existe.'}), 404

    try:
        os.makedirs(backup_dir, exist_ok=True)

        # 1) Copia de seguridad del estado actual antes de pisar nada.
        if os.path.isfile(_DB_PATH):
            sello  = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            seguro = os.path.join(backup_dir, f'fondo_{sello}_pre-restore.db')
            src = sqlite3.connect(_DB_PATH)
            dst = sqlite3.connect(seguro)
            src.backup(dst)
            src.close()
            dst.close()
            log(f"OK: Backup de seguridad pre-restore: {os.path.basename(seguro)}")

        # 2) Restaurar: copiar el backup elegido sobre fondo.db (API SQLite).
        src = sqlite3.connect(origen)
        dst = sqlite3.connect(_DB_PATH)
        src.backup(dst)
        src.close()
        dst.close()
        log(f"OK: Base de datos restaurada desde {archivo}")

        return jsonify({
            'ok': True,
            'mensaje': f'Datos restaurados desde {archivo}. Se guardó una copia previa por las dudas. Recargá la página.',
            'backups': _listar_backups(),
        })
    except Exception as e:
        log(f"ERROR: Restore de DB falló: {e}")
        return jsonify({'ok': False, 'mensaje': f'No se pudo restaurar: {e}'}), 500


# =============================================================================
# BACKUP AUTOMÁTICO DE LA BASE DE DATOS
# =============================================================================
#
# - Se ejecuta una vez por día (primer chequeo del día que encuentre pendiente).
# - Solo crea archivo si los datos cambiaron desde el último backup (se compara
#   el hash del dump lógico contra el guardado en ultimo_backup.json).
# - Si el servicio estaba apagado, lo corre al arrancar.
# - Guarda los últimos 10 backups en la carpeta backups/.
# - Usa la API nativa de SQLite para copiar en caliente (sin cerrar la DB).

_BASE_DIR_BACKUP = os.path.dirname(os.path.abspath(__file__))
_DB_PATH         = database.DB_PATH
_MAX_BACKUPS     = 10


def _get_backup_dir():
    """Resuelve la carpeta de backups leyendo config en caliente."""
    cfg = config.cargar_config(CONFIG_FILE)
    raw = cfg.get('backup_dir', 'backups') or 'backups'
    if os.path.isabs(raw):
        return raw
    return os.path.join(_BASE_DIR_BACKUP, raw)


def _hash_datos_db(ruta_db):
    """SHA-256 del dump lógico de una DB SQLite.

    Se hashea el dump (no el archivo binario) porque SQLite puede tocar
    bytes internos sin que cambien los datos."""
    import sqlite3
    import hashlib
    con = sqlite3.connect(ruta_db)
    try:
        h = hashlib.sha256()
        for linea in con.iterdump():
            h.update(linea.encode('utf-8'))
        return h.hexdigest()
    finally:
        con.close()


def _leer_estado_backup():
    """Lee ultimo_backup.json (archivo, fecha y hash del último backup), o {}."""
    import json
    ruta = os.path.join(_get_backup_dir(), 'ultimo_backup.json')
    try:
        with open(ruta, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar_estado_backup(estado):
    """Persiste ultimo_backup.json junto a los backups. Falla con AVISO, no rompe."""
    import json
    ruta = os.path.join(_get_backup_dir(), 'ultimo_backup.json')
    try:
        with open(ruta, 'w', encoding='utf-8') as f:
            json.dump(estado, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"AVISO: No se pudo guardar ultimo_backup.json: {e}")


def _slug_descripcion(texto):
    """Convierte la descripción del backup en sufijo seguro para nombre de archivo."""
    import re
    slug = re.sub(r'[^\w\-]+', '-', (texto or '').strip()).strip('-')
    return slug[:40]


def hacer_backup_db(motivo='programado', descripcion=None):
    """Copia la base de datos al directorio de backups usando la API de SQLite.

    Si viene descripción (backup manual), se agrega al final del nombre:
    fondo_<fecha>_<descripcion>.db. Devuelve el nombre creado, o None si falló."""
    import sqlite3
    backup_dir = _get_backup_dir()
    try:
        os.makedirs(backup_dir, exist_ok=True)
        ahora     = datetime.now().strftime('%Y-%m-%d_%H-%M')
        slug      = _slug_descripcion(descripcion)
        dest      = os.path.join(backup_dir, f"fondo_{ahora}{('_' + slug) if slug else ''}.db")
        origen    = sqlite3.connect(_DB_PATH)
        respaldo  = sqlite3.connect(dest)
        origen.backup(respaldo)
        origen.close()
        respaldo.close()
        # El hash se calcula sobre el archivo recién copiado, no sobre la DB
        # viva: si entra un movimiento entre la copia y el hash, el hash queda
        # "viejo" y el próximo chequeo hace backup de más (nunca de menos).
        try:
            _guardar_estado_backup({
                'archivo': os.path.basename(dest),
                'creado':  datetime.now().isoformat(timespec='seconds'),
                'hash':    _hash_datos_db(dest),
            })
        except Exception as e:
            log(f"AVISO: No se pudo registrar el hash del backup: {e}")
        log(f"OK: Backup de DB ({motivo}): {os.path.basename(dest)}")
        _limpiar_backups_antiguos()
        return os.path.basename(dest)
    except Exception as e:
        log(f"ERROR: Backup de DB falló: {e}")
        return None


def _limpiar_backups_antiguos():
    """Elimina los backups fechados más viejos si hay más de _MAX_BACKUPS.

    Los archivos sin fecha en el nombre quedan fuera de la rotación.
    fondo_ y gastos_ (backups viejos pre-rename) rotan juntos por fecha.

    IMPORTANTE: NO ordenar por el nombre crudo del archivo. Con prefijos
    mixtos, 'fondo_...' es lexicográficamente MENOR que 'gastos_...' (f < g),
    así que un `sorted()` directo pone TODOS los fondo_* antes que TODOS los
    gastos_*, sin importar la fecha real — el backup más nuevo puede leerse
    como "el más viejo" y la rotación lo borra (bug real visto en vivo:
    fondo_2026-07-13_15-18_post-rename-fondo.db borrado al crearse, con 10
    gastos_* de fechas viejas todavía en la carpeta). Por eso se ordena por
    una CLAVE sin el prefijo: el resto del nombre (YYYY-MM-DD_HH-MM...) sí
    ordena cronológicamente como string, prefijo aparte."""
    import re
    backup_dir = _get_backup_dir()
    try:
        archivos = sorted(
            (f for f in os.listdir(backup_dir)
             if f.startswith(('fondo_', 'gastos_')) and f.endswith('.db') and _fecha_de_backup(f) is not None),
            key=lambda f: re.sub(r'^(?:fondo|gastos)_', '', f)
        )
        while len(archivos) > _MAX_BACKUPS:
            os.remove(os.path.join(backup_dir, archivos.pop(0)))
    except Exception as e:
        log(f"AVISO: No se pudieron limpiar backups viejos: {e}")


def _fecha_de_backup(nombre):
    """Extrae la fecha de un nombre fondo_YYYY-MM-DD*.db o gastos_YYYY-MM-DD*.db
    (compat backups viejos pre-rename 2026-07), o None si no la tiene.

    Usa regex en vez de slicing de largo fijo, porque el prefijo ya no mide
    siempre lo mismo ('fondo_' vs 'gastos_'). Archivos renombrados a mano
    (ej. gastos_PreGitHub.db) devuelven None: no cuentan como backup
    programado ni entran en la rotación."""
    import re
    m = re.match(r'^(?:fondo|gastos)_(\d{4}-\d{2}-\d{2})', nombre)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), '%Y-%m-%d').date()
    except ValueError:
        return None


def _ultimo_backup_fecha():
    """Devuelve la fecha del backup fechado más reciente, o None si no hay ninguno."""
    backup_dir = _get_backup_dir()
    try:
        fechas = [
            _fecha_de_backup(f)
            for f in os.listdir(backup_dir)
            if f.startswith(('fondo_', 'gastos_')) and f.endswith('.db')
        ]
        fechas = [f for f in fechas if f is not None]
        return max(fechas) if fechas else None
    except Exception:
        return None


_aviso_sin_cambios = None  # última fecha en que se logueó "sin cambios" (evita 24 líneas/día)


def _scheduler_backup():
    """
    Hilo de fondo: comprueba cada hora si toca hacer backup.
    Regla: si todavía no se hizo backup hoy Y los datos cambiaron desde el
    último backup → hacerlo. Si no hubo cambios, sigue chequeando cada hora:
    un movimiento cargado a la tarde genera backup ese mismo día.
    La primera vuelta corre al arrancar, así cubre días en que el servicio estuvo apagado.
    """
    global _aviso_sin_cambios
    while True:
        try:
            hoy    = datetime.now().date()
            ultimo = _ultimo_backup_fecha()
            if ultimo is None:
                # Sin backups fechados en la carpeta: backupear sí o sí,
                # aunque el json diga que los datos no cambiaron.
                hacer_backup_db('primer backup')
            elif ultimo < hoy:
                if _hash_datos_db(_DB_PATH) != _leer_estado_backup().get('hash'):
                    hacer_backup_db('diario programado')
                elif _aviso_sin_cambios != hoy:
                    log("OK: Backup omitido hoy: sin cambios en los datos desde el último backup.")
                    _aviso_sin_cambios = hoy
        except Exception as e:
            log(f"AVISO: Error en scheduler de backup: {e}")
        time.sleep(3600)  # revisar cada hora


def iniciar_scheduler_backup():
    """Arranca el hilo del backup diario (la primera vuelta corre enseguida)."""
    hilo = threading.Thread(target=_scheduler_backup, daemon=True, name='backup-scheduler')
    hilo.start()


# =============================================================================
# SCHEDULER DE COTIZACIÓN DEL DÓLAR
# =============================================================================
#
# - Al arrancar el servicio: SIEMPRE refresca la cotización (en hilo separado).
# - Durante la ejecución: refresca automáticamente todos los días a las
#   horas indicadas en HORAS_REFRESH_COTIZACION (08:00 y 17:00).
# - Si la API falla, el último valor cacheado en config.json se mantiene.
# - Se reintenta cada 15 min después de un fallo en una hora programada,
#   para cubrir el caso de que dolarapi.com esté caído justo a esa hora.
#

HORAS_REFRESH_COTIZACION = [8, 17]   # horas (0-23) en las que refrescar diariamente
REINTENTO_FALLO_SEGUNDOS = 15 * 60   # si falla en hora programada, reintentar a los 15 min


def _proximo_horario_refresh(ahora):
    """
    Dado un datetime 'ahora', devuelve el próximo datetime en el que toca
    refrescar (la próxima hora de HORAS_REFRESH_COTIZACION, hoy o mañana).
    """
    candidatos = []
    for h in HORAS_REFRESH_COTIZACION:
        candidato_hoy = ahora.replace(hour=h, minute=0, second=0, microsecond=0)
        if candidato_hoy > ahora:
            candidatos.append(candidato_hoy)
        else:
            candidatos.append(candidato_hoy + timedelta(days=1))
    return min(candidatos)


def _scheduler_cotizacion():
    """
    Hilo de fondo: duerme hasta el próximo horario programado y refresca.
    Si falla, reintenta en REINTENTO_FALLO_SEGUNDOS.
    """
    while True:
        try:
            ahora    = datetime.now()
            proximo  = _proximo_horario_refresh(ahora)
            segundos = max(1, int((proximo - ahora).total_seconds()))
            time.sleep(segundos)

            ok, mensaje = cotizacion.refrescar_cache(CONFIG_FILE)
            log(f"{'OK' if ok else 'AVISO'}: Scheduler cotización: {mensaje}")

            if not ok:
                time.sleep(REINTENTO_FALLO_SEGUNDOS)
                ok2, mensaje2 = cotizacion.refrescar_cache(CONFIG_FILE)
                log(f"{'OK' if ok2 else 'AVISO'}: Reintento cotización: {mensaje2}")
        except Exception as e:
            log(f"AVISO: Error en scheduler de cotización: {e}")
            time.sleep(REINTENTO_FALLO_SEGUNDOS)


def iniciar_scheduler_cotizacion():
    """
    Arranca el scheduler de cotización. SIEMPRE dispara un refresh inmediato
    al iniciar el servicio (en hilo separado, no bloqueante), y luego refresca
    diariamente a las horas de HORAS_REFRESH_COTIZACION.
    """
    def _refresh_inicial():
        ok, mensaje = cotizacion.refrescar_cache(CONFIG_FILE)
        log(f"{'OK' if ok else 'AVISO'}: Cotización al inicio: {mensaje}")

    threading.Thread(
        target=_refresh_inicial,
        daemon=True,
        name='cotizacion-inicial'
    ).start()

    hilo = threading.Thread(target=_scheduler_cotizacion, daemon=True, name='cotizacion-scheduler')
    hilo.start()


# =============================================================================
# INICIO DE LA APLICACIÓN
# =============================================================================

def iniciar_ngrok(port, authtoken, domain=''):
    """Intenta abrir un túnel público con ngrok al puerto indicado."""
    try:
        from pyngrok import ngrok, conf

        if not authtoken:
            log("AVISO: ngrok habilitado pero ngrok_authtoken está vacío en config.json.")
            return

        conf.get_default().auth_token = authtoken
        opciones = {}
        if domain:
            opciones['hostname'] = domain
        ngrok.connect(port, "http", **opciones)

    except ImportError:
        log(f"AVISO: pyngrok no esta instalado. La app sigue en http://localhost:{port}")
    except Exception as e:
        log(f"AVISO: ngrok no pudo iniciarse: {e}")


@app.errorhandler(404)
def pagina_no_encontrada(e):
    return render_template('404.html'), 404


@app.errorhandler(405)
def metodo_no_permitido(e):
    return render_template('405.html'), 405


def run_flask():
    """
    Inicializa la DB, lee la config y arranca el servidor Flask.
    Se usa tanto en modo normal como en modo servicio Windows.
    """
    database.inicializar_db()
    iniciar_scheduler_backup()
    iniciar_scheduler_cotizacion()

    cfg = config.cargar_config(CONFIG_FILE)
    port = cfg.get('port', 5000)

    if cfg.get('first_run', True):
        host = '127.0.0.1'
        modo = 'first_run — solo localhost, completar Settings'
    elif cfg.get('ngrok_enabled', False) and 'DEV' not in cfg.get('app_name', ''):
        host = '127.0.0.1'
        iniciar_ngrok(port, cfg.get('ngrok_authtoken', ''), cfg.get('ngrok_domain', ''))
        modo = 'producción — expuesta vía ngrok'
    elif 'DEV' in cfg.get('app_name', '') or cfg.get('auth_disabled', False):
        host = '127.0.0.1'
        modo = 'DEV / auth_disabled'
        log("AVISO: modo DEV / auth_disabled — la app solo escucha en localhost (no se expone a la red).")
    else:
        host = '0.0.0.0'
        modo = 'red local'

    horas_str = ', '.join(f"{h:02d}:00" for h in HORAS_REFRESH_COTIZACION)
    log(f"OK: App iniciada — DB {os.path.basename(database.DB_PATH)} lista; backup automático diario; "
          f"cotización al inicio + diario a {horas_str}; "
          f"servidor en http://localhost:{port} (modo {modo}).")

    app.run(debug=False, host=host, port=port, use_reloader=False)


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================
#
# En producción NSSM envuelve este mismo `python app.py` (no hay comandos de
# servicio propios). En desarrollo se corre igual, a mano. Ver CONTEXT_DEPLOY.md.

if __name__ == '__main__':
    run_flask()
