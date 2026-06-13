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
from datetime import datetime, timedelta

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

# -----------------------------------------------------------------------------
# Carpeta base del proyecto: templates/ y static/ viven junto a este .py.
# -----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

import re as _re
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
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
    ("borde",          "Borde",             "Bordes, separadores"),
    ("exito",          "Éxito",             "Ingresos, OK, semáforo verde"),
    ("alerta",         "Alerta",            "Pendiente, advertencia"),
    ("peligro",        "Peligro",           "Eliminar, error, saldo negativo"),
    ("exito-suave",    "Éxito suave",       "Fondo badge OK"),
    ("alerta-suave",   "Alerta suave",      "Fondo badge alerta"),
    ("peligro-suave",  "Peligro suave",     "Fondo badge error"),
    ("persona-elias",  "Persona — Elías",   "Identificador visual Elías"),
    ("persona-mari",   "Persona — Mari",    "Identificador visual Mari"),
    ("moneda-ars",     "Moneda — AR$",      "Badge AR$, gauge total ARS"),
    ("moneda-usd",     "Moneda — USD",      "Badge USD, gauge total USD"),
    ("deco-1",         "Deco 1",            "Barra de título (header)"),
    ("deco-2",         "Deco 2",            "Barra de navegación"),
    ("deco-3",         "Deco 3",            "Separadores, iconos secundarios"),
    ("deco-4",         "Deco 4",            "Hover backgrounds, divisores ligeros"),
]

_HEX_RE = _re.compile(r'^#[0-9a-fA-F]{6}$')


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


def _static_version():
    """Devuelve el mtime más reciente de los archivos estáticos principales."""
    try:
        paths = [
            os.path.join(app.static_folder, 'style.css'),
            os.path.join(app.static_folder, 'app.js'),
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
#   Compartido por la ruta '/' y por la API '/api/saldos'.
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
# RUTA: Página principal — Saldos + formulario + tabla de movimientos
# URL: http://localhost:5000/
# =============================================================================

@app.route('/')
def index():
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

    fijos_activos = database.obtener_gastos_fijos(solo_activos=True)
    import json
    gastos_fijos_json = json.dumps([
        {
            'descripcion': f['descripcion'],
            'es_cuota':    f['es_cuota'] or 0,
            'cuota_actual': f['cuota_actual'] or 0,
            'total_cuotas': f['total_cuotas'],
        }
        for f in fijos_activos
    ])

    return render_template('index.html',
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
            return redirect(url_for('index', mes=mes) if mes else url_for('index'))

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
        return redirect(url_for('index', mes=mes) if mes else url_for('index'))

    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'ok': False, 'error': str(e)}), 500
        mes = request.form.get('mes', '')
        return redirect(url_for('index', mes=mes) if mes else url_for('index'))


# =============================================================================
# RUTA: Eliminar un movimiento
# URL: http://localhost:5000/eliminar/3
# Método: POST
# =============================================================================

@app.route('/eliminar/<int:id>', methods=['POST'])
def eliminar(id):
    database.eliminar_movimiento(id)
    mes = request.args.get('mes', '')
    return redirect(url_for('index', mes=mes) if mes else url_for('index'))


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
        return redirect(url_for('index', mes=mes) if mes else url_for('index'))
    else:
        mov = database.obtener_movimiento(id)
        if mov is None:
            return redirect(url_for('index'))
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

        nuevos = {
            'port':           int(request.form.get('port', 5000)),
            'app_name':       request.form.get('app_name', 'Gastos Casa').strip(),
            'ngrok_enabled':  request.form.get('ngrok_enabled') == 'on',
            'ngrok_authtoken': request.form.get('ngrok_authtoken', '').strip(),
            'ngrok_domain':   request.form.get('ngrok_domain', '').strip(),
            'factor_sueldo':  float(request.form.get('factor_sueldo', 0.7)),
            'google_client_id':     request.form.get('google_client_id', '').strip(),
            'google_client_secret': request.form.get('google_client_secret', '').strip(),
        }
        config.guardar_config(nuevos, CONFIG_FILE)
        flash('Configuración guardada. Reiniciá la app para aplicar los cambios.')
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
# - POST /api/backups/crear      → crea un backup manual de gastos.db.
# - POST /api/backups/restaurar  → restaura un backup elegido sobre gastos.db,
#                                   guardando antes una copia de seguridad del
#                                   estado actual (gastos_<fecha>_pre-restore.db).

def _listar_backups():
    """Lista los backups .db de la carpeta configurada, del más nuevo al más viejo."""
    import re
    backup_dir = _get_backup_dir()
    items = []
    try:
        for f in os.listdir(backup_dir):
            if not (f.startswith('gastos_') and f.endswith('.db')):
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
                # Descripción de backup manual: lo que sigue a gastos_FECHA_HORA_
                m = re.match(r'^gastos_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}_(.+)\.db$', f)
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
            seguro = os.path.join(backup_dir, f'gastos_{sello}_pre-restore.db')
            src = sqlite3.connect(_DB_PATH)
            dst = sqlite3.connect(seguro)
            src.backup(dst)
            src.close()
            dst.close()
            log(f"OK: Backup de seguridad pre-restore: {os.path.basename(seguro)}")

        # 2) Restaurar: copiar el backup elegido sobre gastos.db (API SQLite).
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
_DB_PATH         = os.path.join(_BASE_DIR_BACKUP, 'gastos.db')
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
    gastos_<fecha>_<descripcion>.db. Devuelve el nombre creado, o None si falló."""
    import sqlite3
    backup_dir = _get_backup_dir()
    try:
        os.makedirs(backup_dir, exist_ok=True)
        ahora     = datetime.now().strftime('%Y-%m-%d_%H-%M')
        slug      = _slug_descripcion(descripcion)
        dest      = os.path.join(backup_dir, f"gastos_{ahora}{('_' + slug) if slug else ''}.db")
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

    Los archivos sin fecha en el nombre quedan fuera de la rotación."""
    backup_dir = _get_backup_dir()
    try:
        archivos = sorted(
            f for f in os.listdir(backup_dir)
            if f.startswith('gastos_') and f.endswith('.db') and _fecha_de_backup(f) is not None
        )
        while len(archivos) > _MAX_BACKUPS:
            os.remove(os.path.join(backup_dir, archivos.pop(0)))
    except Exception as e:
        log(f"AVISO: No se pudieron limpiar backups viejos: {e}")


def _fecha_de_backup(nombre):
    """Extrae la fecha de un nombre gastos_YYYY-MM-DD*.db, o None si no la tiene.

    Archivos renombrados a mano (ej. gastos_PreGitHub.db) devuelven None:
    no cuentan como backup programado ni entran en la rotación."""
    try:
        return datetime.strptime(nombre[len('gastos_'):len('gastos_') + 10], '%Y-%m-%d').date()
    except ValueError:
        return None


def _ultimo_backup_fecha():
    """Devuelve la fecha del backup fechado más reciente, o None si no hay ninguno."""
    backup_dir = _get_backup_dir()
    try:
        fechas = [
            _fecha_de_backup(f)
            for f in os.listdir(backup_dir)
            if f.startswith('gastos_') and f.endswith('.db')
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
    log(f"OK: App iniciada — DB gastos.db lista; backup automático diario; "
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
