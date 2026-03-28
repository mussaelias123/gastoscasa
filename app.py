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
#   - Normal:   python app.py
#   - Servicio: python app.py install | start | stop | remove
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
import argparse
import subprocess
from datetime import datetime

_parser = argparse.ArgumentParser()
_parser.add_argument('--config', default='config.json', help='Ruta al archivo de configuración')
_args, _ = _parser.parse_known_args()
CONFIG_FILE = _args.config

# -----------------------------------------------------------------------------
# Detección PyInstaller: cuando corre como .exe, los templates/static están
# en sys._MEIPASS en lugar de junto al .py
# -----------------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from math import ceil
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
import database
import config
import psutil

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))
app.secret_key = os.urandom(24)
app.config['TEMPLATES_AUTO_RELOAD'] = True  # Recargar templates sin reiniciar


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
    return {'cfg': config.cargar_config(CONFIG_FILE)}


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

    # ── Cálculo de gauges circulares ──────────────────────────────────────────
    def _gauge(a, b):
        """Retorna (pct_a, pct_b) normalizados a 100, usando solo valores ≥ 0."""
        pa, pb = max(float(a), 0), max(float(b), 0)
        total = pa + pb
        if total <= 0:
            return 0.0, 0.0
        return round(pa / total * 100, 2), round(pb / total * 100, 2)

    usd_a_ars   = float(cfg.get('usd_a_ars', 1500))
    g_ars       = _gauge(saldos['elias_ars'], saldos['mari_ars'])
    g_usd       = _gauge(saldos['elias_usd'], saldos['mari_usd'])
    total_ars_v = saldos['elias_ars'] + saldos['mari_ars']
    total_usd_v = saldos['elias_usd'] + saldos['mari_usd']
    g_total     = _gauge(total_ars_v, total_usd_v * usd_a_ars)
    gauges = {
        'ars':   {'elias': g_ars[0],   'mari':  g_ars[1]},
        'usd':   {'elias': g_usd[0],   'mari':  g_usd[1]},
        'total': {'ars':   g_total[0], 'usd':   g_total[1]},
        'usd_a_ars': int(usd_a_ars),
    }

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

        # ── Tipo "cambio": genera 2 movimientos (salida + entrada) ──
        if tipo == 'cambio':
            persona_final = request.form['persona_final']
            moneda_final  = request.form['moneda_final']
            monto_final_str = request.form.get('monto_final', '').strip()
            monto_final = float(monto_final_str) if monto_final_str else monto

            # Movimiento 1: salida (gasto del origen)
            id1 = database.agregar_movimiento(
                fecha, descripcion, persona, moneda, 'gasto', monto,
                categoria='Cambio')

            # Movimiento 2: entrada (ingreso al destino)
            id2 = database.agregar_movimiento(
                fecha, descripcion, persona_final, moneda_final, 'ingreso', monto_final,
                categoria='Cambio')

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

        nuevo_id = database.agregar_movimiento(fecha, descripcion, persona, moneda, tipo, monto, categoria, costo_envio, factor_aplicado, cuota_numero, cuota_total)

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
        database.editar_movimiento(id, fecha, descripcion, persona, moneda, tipo, monto, categoria, costo_envio)
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
    movimientos, _total = database.obtener_movimientos()
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
        }
        for m in movimientos
    ]
    return render_template('resumen.html', saldos=saldos, movimientos_json=movimientos_json)


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

        nuevos = {
            'port':           int(request.form.get('port', 5000)),
            'app_name':       request.form.get('app_name', 'Gastos Casa').strip(),
            'ngrok_enabled':  request.form.get('ngrok_enabled') == 'on',
            'ngrok_authtoken': request.form.get('ngrok_authtoken', '').strip(),
            'ngrok_domain':   request.form.get('ngrok_domain', '').strip(),
            'factor_sueldo':  float(request.form.get('factor_sueldo', 0.7)),
            'usd_a_ars':      float(request.form.get('usd_a_ars', 1500)),
        }
        config.guardar_config(nuevos, CONFIG_FILE)
        flash('Configuración guardada. Reiniciá la app para aplicar los cambios.')
        return redirect(url_for('settings'))

    cfg = config.cargar_config(CONFIG_FILE)
    fijos = database.obtener_gastos_fijos(solo_activos=False)
    return render_template('settings.html', cfg=cfg, fijos=fijos)


# =============================================================================
# RUTA: Git commit desde la interfaz
# URL: POST /git/commit
# =============================================================================

@app.route('/git/ping')
def git_ping():
    return jsonify({'ok': True, 'version': 'v2-con-git'})


@app.route('/git/commit', methods=['POST'])
def git_commit():
    descripcion = request.form.get('descripcion', '').strip()
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M')

    if descripcion:
        mensaje = f"{ahora} — {descripcion}"
    else:
        mensaje = f"Backup automático {ahora}"

    repo_dir = os.path.dirname(os.path.abspath(__file__))

    try:
        git_opts = [
            '-c', f'safe.directory={repo_dir}',
            '-c', 'user.email=app@gastoscasa.local',
            '-c', 'user.name=Gastos Casa',
        ]

        add = subprocess.run(['git'] + git_opts + ['add', '.'], cwd=repo_dir,
                             capture_output=True, text=True, encoding='utf-8', errors='replace')
        if add.returncode != 0:
            return jsonify({'ok': False, 'mensaje': f'git add falló: {(add.stderr or add.stdout).strip()}'})

        resultado = subprocess.run(
            ['git'] + git_opts + ['commit', '-m', mensaje],
            cwd=repo_dir, capture_output=True, text=True, encoding='utf-8', errors='replace'
        )

        if resultado.returncode == 0:
            return jsonify({'ok': True, 'mensaje': f'Commit creado: "{mensaje}"'})
        elif 'nothing to commit' in resultado.stdout or 'nothing to commit' in resultado.stderr:
            return jsonify({'ok': False, 'mensaje': 'No hay cambios para guardar desde el último commit.'})
        else:
            return jsonify({'ok': False, 'mensaje': (resultado.stderr or resultado.stdout).strip()})

    except FileNotFoundError:
        return jsonify({'ok': False, 'mensaje': 'Git no está instalado o no se encuentra en el PATH.'})
    except Exception as e:
        return jsonify({'ok': False, 'mensaje': str(e)})


# =============================================================================
# INICIO DE LA APLICACIÓN
# =============================================================================

def iniciar_ngrok(port, authtoken, domain=''):
    """Intenta abrir un túnel público con ngrok al puerto indicado."""
    try:
        from pyngrok import ngrok, conf

        if not authtoken:
            print("AVISO: ngrok habilitado pero ngrok_authtoken está vacío en config.json.")
            print("   La app sigue disponible en http://localhost:{port}")
            return

        conf.get_default().auth_token = authtoken
        opciones = {}
        if domain:
            opciones['hostname'] = domain
        tunel = ngrok.connect(port, "http", **opciones)
        print(f">> App publica en: {tunel.public_url}")

    except ImportError:
        print("AVISO: pyngrok no esta instalado. La app sigue en http://localhost:{port}")
    except Exception as e:
        print(f"AVISO: ngrok no pudo iniciarse: {e}")


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
    print("OK: Base de datos inicializada (archivo: gastos.db)")
    print("-" * 50)

    cfg = config.cargar_config(CONFIG_FILE)
    port = cfg.get('port', 5000)

    if cfg.get('first_run', True):
        host = '127.0.0.1'
        print("AVISO: first_run=true — la app solo escucha en localhost.")
        print("   Abrí http://localhost:{} y completá la configuración en Settings.".format(port))
    elif cfg.get('ngrok_enabled', False) and 'DEV' not in cfg.get('app_name', ''):
        host = '127.0.0.1'
        iniciar_ngrok(port, cfg.get('ngrok_authtoken', ''), cfg.get('ngrok_domain', ''))
    else:
        host = '0.0.0.0'

    print("-" * 50)
    print("OK: Servidor iniciado. Abri tu navegador en: http://localhost:{}".format(port))
    print("  (Para detener el servidor: Ctrl+C)")
    print("-" * 50)

    app.run(debug=False, host=host, port=port, use_reloader=False)


# =============================================================================
# SOPORTE DE SERVICIO WINDOWS (pywin32)
# =============================================================================
#
# Para instalar/gestionar el servicio:
#   python app.py install   — registra el servicio en Windows
#   python app.py start     — inicia el servicio
#   python app.py stop      — detiene el servicio
#   python app.py remove    — desinstala el servicio
#
# Requiere: pip install pywin32
# Requiere ejecutar con privilegios de administrador para install/remove.
#
try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager

    class GastosCasaService(win32serviceutil.ServiceFramework):
        _svc_name_         = "GastosCasa"
        _svc_display_name_ = "Gastos Casa"
        _svc_description_  = "Aplicacion de control de gastos personales"

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            self.stop_event.set()

        def SvcDoRun(self):
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, '')
            )
            run_flask()
            win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)

    _WIN32_DISPONIBLE = True

except ImportError:
    _WIN32_DISPONIBLE = False


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

_COMANDOS_SERVICIO = ('install', 'start', 'stop', 'remove', 'restart', 'status')

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] in _COMANDOS_SERVICIO:
        if not _WIN32_DISPONIBLE:
            print("ERROR: pywin32 no está instalado. Ejecutá: pip install pywin32")
            sys.exit(1)
        win32serviceutil.HandleCommandLine(GastosCasaService)
    else:
        run_flask()
