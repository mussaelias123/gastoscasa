# =============================================================================
# ARCHIVO: auth.py
# =============================================================================
#
# QUÉ ES ESTE ARCHIVO:
#   Módulo de autenticación con Google OAuth 2.0.
#   Controla quién puede acceder a la aplicación.
#
# CÓMO FUNCIONA:
#   1. El usuario entra a cualquier URL de la app.
#   2. Si no tiene sesión, se lo redirige a /login.
#   3. /login lo manda a Google para que inicie sesión.
#   4. Google devuelve al usuario a /auth/callback con sus datos.
#   5. Si el email está en la lista de permitidos Y Google lo tiene verificado
#      (email_verified), se crea la sesión.
#   6. Si no, se muestra un error de "acceso denegado".
#
# ADEMÁS, en cada request:
#   · Los POST/PUT/PATCH/DELETE solo se aceptan si vienen de la propia app (el
#     Origin o el Referer tiene que ser el sitio pedido). Va ANTES del login y
#     alcanza a las rutas públicas. Ver _exigir_origen_propio.
#   · El bypass DEV (auth_disabled) tiene CUATRO cerrojos, uno de ellos el
#     nombre del sitio. Ver require_login y _host_es_local.
#   · La cookie de sesión va Secure cuando la app sale por ngrok. Ver
#     _cookie_secure_para.
#
# FALLA CERRADO:
#   Si config.json no trae google_client_id / google_client_secret (o no se
#   puede leer), la app queda CERRADA para todos: todo redirige a
#   /login?error=no_configurado. Antes dejaba pasar a cualquiera ("para poder
#   configurar"), y por el túnel de ngrok eso era todo internet. La puesta en
#   marcha se hace editando config.json, no desde la web. Ver require_login.
#
# EMAILS PERMITIDOS:
#   Solo estos emails de Google pueden acceder:
#     - mussaelias123@gmail.com
#     - mossinomariana@gmail.com
#
# =============================================================================

import os
import re
import json
import secrets
import functools
import threading
import time
from datetime import timedelta
from urllib.parse import urlsplit
from flask import (
    Blueprint, session, redirect, url_for, request,
    render_template, flash, current_app, jsonify, Response
)
from authlib.integrations.flask_client import OAuth
import config as cfg_module
from logutil import log

# ── Blueprint de autenticación ───────────────────────────────────────────────
auth_bp = Blueprint('auth', __name__)

# ── Instancia de OAuth (se configura en init_auth) ──────────────────────────
oauth = OAuth()

# ── Emails permitidos ────────────────────────────────────────────────────────
EMAILS_PERMITIDOS = [
    'mussaelias123@gmail.com',
    'mossinomariana@gmail.com',
]

# ── De qué email es cada persona ─────────────────────────────────────────────
# Traduce la cuenta de Google con la que se entró al valor de la columna
# `movimientos.persona` ('elias' | 'mari'). Lo usa el módulo Personal para
# saber de quién es la cuenta que se está mirando: ahí la persona NO se elige
# en un desplegable, sale de acá.
#
# Vive junto a EMAILS_PERMITIDOS a propósito: las dos listas son la misma
# decisión (quién entra y quién es), y si alguna vez se suma un tercero hay
# que tocar las dos.
PERSONAS_POR_EMAIL = {
    'mussaelias123@gmail.com':  'elias',
    'mossinomariana@gmail.com': 'mari',
}


def persona_de_email(email, defecto=None):
    """
    'mussaelias123@gmail.com' → 'elias'. Case-insensitive.

    Devuelve `defecto` si el email no está mapeado — pasa con el usuario
    falso del bypass DEV (`dev@local`), donde quien decide es la clave
    `persona_dev` de config.json.
    """
    return PERSONAS_POR_EMAIL.get((email or '').strip().lower(), defecto)


# ── Login CERRADO cuando faltan las credenciales de Google ───────────────────
# Es la única decisión de este bloque: sin credenciales NO se deja pasar a nadie.
# Se aplica en el middleware y en las tres rutas que hablan con Google o
# muestran el login, siempre contra la config EN CALIENTE (la que se lee del
# disco en cada request), no contra la del arranque.
#
# Una config ilegible cae acá sola: `cargar_config` devuelve DEFAULTS, que no
# traen credenciales. Por eso un config.json roto o a medias deja la app
# cerrada y no abierta.
_AVISO_CERRADO_CADA = 60.0       # segundos entre AVISOs: el middleware corre en cada request
_aviso_cerrado = {'ultimo': None}
_lock_aviso_cerrado = threading.Lock()


def _faltan_credenciales(cfg):
    """True si la config no trae las dos credenciales de Google OAuth."""
    return not cfg.get('google_client_id') or not cfg.get('google_client_secret')


def _cfg_en_caliente():
    """La config leída del disco AHORA, desde las rutas del blueprint (que no
    ven el `config_file` de `init_auth`, así que se guarda en app.config)."""
    return cfg_module.cargar_config(current_app.config.get('AUTH_CONFIG_FILE'))


def _login_cerrado():
    """
    Respuesta para todo pedido que llega sin credenciales de Google en la
    config: AVISO en el log (como mucho uno por minuto, no uno por request) y
    redirect al login con el aviso `no_configurado`.

    El log no incluye la ruta pedida ni nada del request: la ruta la escribe
    quien pide, y una línea de log no es lugar para texto ajeno.
    """
    ahora = time.monotonic()
    with _lock_aviso_cerrado:
        ultimo = _aviso_cerrado['ultimo']
        avisar = ultimo is None or ahora - ultimo >= _AVISO_CERRADO_CADA
        if avisar:
            _aviso_cerrado['ultimo'] = ahora
    if avisar:
        log("AVISO: login CERRADO — config.json no tiene google_client_id / "
            "google_client_secret (o no se pudo leer). Nadie entra hasta "
            "cargarlas y reiniciar el servicio.")
    return redirect(url_for('auth.login', error='no_configurado'))


# ── Los POST solo desde la propia app ────────────────────────────────────────
# Segunda defensa contra CSRF: que una página de OTRO sitio, abierta en el mismo
# navegador, mande un POST a esta app aprovechando la sesión de quien la tiene
# abierta. La primera es la cookie SameSite=Lax; esta no depende de ella, y
# conviene que no dependa porque Lax tiene filos:
#   · no mira el puerto: en localhost, `localhost:8080` y `localhost:5050` son el
#     MISMO sitio, así que cualquier otra cosa que corra en la PC (un servidor
#     de pruebas, otra app) pasa el filtro de SameSite;
#   · por el túnel, que `a.ngrok-free.dev` y `b.ngrok-free.dev` sean sitios
#     distintos depende de que `ngrok-free.dev` esté en la lista de sufijos
#     públicos del navegador, y de que esa lista esté al día;
#   · es una protección del navegador, y uno viejo la ignora.
#
# Qué se exige, para POST / PUT / PATCH / DELETE (todo lo que cambia algo) y en
# TODAS las rutas, las públicas incluidas (/logout acepta POST):
#   · si viene `Origin`: su host:puerto tiene que ser el del sitio que se pidió
#     (`request.host`). `Origin: null` (iframes con sandbox, redirecciones entre
#     sitios, file://) se rechaza: no hay forma de saber de dónde viene.
#   · si no viene `Origin` pero sí `Referer`: la misma comparación, con el
#     host:puerto del Referer.
#   · si no viene ninguno de los dos —navegadores viejos, el cliente de pruebas,
#     un curl— pasa. Ahí queda, sola, la cookie SameSite.
#
# ⚠ El ESQUEMA no se compara, a propósito. Detrás de ngrok Flask ve http mientras
# el navegador manda `Origin: https://...`: compararlo rechazaría todos los POST
# de producción. Tampoco hay una lista de sitios para configurar: el único Origin
# que puede coincidir con el Host con el que el navegador llegó hasta acá es el
# del propio sitio. El PUERTO sí se compara (`localhost:8080` no es esta app).
#
# ⚠ Lo que NO frena es el "DNS rebinding": un dominio del atacante que resuelve
# a 127.0.0.1 es, para el navegador, el MISMO origen que él se pide, y Origin y
# Host coinciden. Eso lo cierra el cuarto cerrojo del bypass DEV (más abajo).
#
# ⚠ Una trampa para quien toque las cabeceras: con `Referrer-Policy: no-referrer`
# en una página, los navegadores pueden mandar `Origin: null` en los formularios
# del PROPIO sitio, y este chequeo los rechazaría. Usar `same-origin` o
# `strict-origin-when-cross-origin`.
_METODOS_QUE_CAMBIAN = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})

# Los AVISOs de abajo corren en el middleware, o sea en cada request: sin tope,
# un script que insista llenaría el log. Mismo criterio que `_login_cerrado`.
_AVISO_ORIGEN_CADA = 60.0        # segundos entre AVISOs de "pedido rechazado"
_AVISO_BYPASS_CADA = 60.0        # y entre los de "bypass DEV cerrado por el host"
_aviso_origen = {'ultimo': None}
_aviso_bypass = {'ultimo': None}
_lock_avisos = threading.Lock()

# Lo único que se deja pasar de un texto que escribió quien pide a una línea de
# log. Sin saltos de línea ni secuencias de escape: un valor ajeno no puede
# fabricar una línea de log falsa.
_RE_NO_APTO_PARA_LOG = re.compile(r'[^a-z0-9.:_\[\]-]')


def _toca_avisar(estado, cada):
    """True si ya pasaron `cada` segundos desde el último AVISO de ese `estado`
    (y anota este). Como mucho uno por minuto, no uno por request."""
    ahora = time.monotonic()
    with _lock_avisos:
        ultimo = estado['ultimo']
        if ultimo is not None and ahora - ultimo < cada:
            return False
        estado['ultimo'] = ahora
        return True


def _para_log(valor, largo=60):
    """
    Un texto que vino en el pedido (el Host, el Origin), saneado para una línea
    de log: en minúsculas, solo [a-z0-9.:_[]-] —todo lo demás pasa a '?'— y con
    tope de largo. Un log no es lugar para texto ajeno sin tratar.
    """
    limpio = _RE_NO_APTO_PARA_LOG.sub('?', str(valor or '').lower())
    return limpio if len(limpio) <= largo else limpio[:largo] + '...'


def _sitio_de_url(valor):
    """
    'HTTPS://Foo.com:8443/ruta?x=1' → 'foo.com:8443': el host:puerto en
    minúsculas y SIN esquema. None si no hay un sitio que leer ('null', vacío,
    basura, una URL sin `esquema://`).

    Se devuelve el `netloc` entero, con el usuario@ si lo trae: nunca va a ser
    igual a `request.host`, así que `https://localhost@evil.example` y
    `https://evil.example@localhost` quedan como ajenos y no hay que decidir cuál
    de los dos nombres "vale".
    """
    try:
        partes = urlsplit((valor or '').strip())
    except ValueError:        # corchetes sin cerrar, IPv6 inválido, etc.
        return None
    if not partes.scheme or not partes.netloc:
        return None
    return partes.netloc.lower()


def _motivo_de_pedido_ajeno():
    """
    None si el pedido puede seguir. Si no, el motivo en un texto corto, ya apto
    para el log. Solo se llama para los métodos de `_METODOS_QUE_CAMBIAN`.

    Si viene `Origin`, manda él y el `Referer` ni se mira: el Origin es el
    cabezal pensado para esto, y el Referer lo puede recortar o quitar una
    política de referrer. Un Origin propio con un Referer ajeno pasa; un Origin
    ajeno con un Referer propio, no.
    """
    propio = (request.host or '').strip().lower()

    origin = request.headers.get('Origin')
    if origin is not None:
        if origin.strip().lower() == 'null':
            return "Origin 'null'"
        sitio = _sitio_de_url(origin)
        if sitio is None:
            return 'Origin ilegible'
        if sitio != propio:
            return f"Origin ajeno '{_para_log(sitio)}'"
        return None

    referer = request.headers.get('Referer')
    if referer is not None:
        sitio = _sitio_de_url(referer)
        if sitio is None:
            return 'Referer ilegible'
        if sitio != propio:
            return f"Referer ajeno '{_para_log(sitio)}'"
    return None


def _exigir_origen_propio():
    """
    before_request: los pedidos que cambian algo solo se aceptan si vienen de la
    propia app. Ver el bloque de arriba.

    ⚠ Se registra en `init_auth` ANTES que `require_login` (Flask corre los
    before_request en el orden en que se registraron), y no es casual: un POST
    ajeno se frena sea cual sea el estado del login, también con el bypass DEV
    (que fabrica una sesión) y también en las rutas públicas.

    Rechazo: 403, con AVISO en el log y SIN volcar valores del pedido sin sanear.
    JSON `{'ok': False, 'error': ...}` si es AJAX (el mismo cabezal que usa
    `_es_ajax` en app.py), texto plano si no.
    """
    if request.method not in _METODOS_QUE_CAMBIAN:
        return None

    motivo = _motivo_de_pedido_ajeno()
    if motivo is None:
        return None

    if _toca_avisar(_aviso_origen, _AVISO_ORIGEN_CADA):
        # Método y endpoint son nuestros (el método es uno de los cuatro de
        # arriba y el endpoint lo pone Flask desde el mapa de rutas); el motivo y
        # el Host pasan por _para_log. La ruta que escribió quien pide, no.
        log(f"AVISO: {request.method} rechazado en '{request.endpoint or '-'}' — "
            f"{motivo}; el sitio pedido es '{_para_log(request.host)}'. Los pedidos "
            f"que cambian datos solo se aceptan si vienen de esta misma app (si fue "
            f"un uso legítimo, mirar si un proxy o el túnel cambia el Host).")

    texto = 'Pedido rechazado: no viene de esta app.'
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'ok': False, 'error': texto}), 403
    return Response(texto, status=403, mimetype='text/plain')


# ── Bypass DEV: el cuarto cerrojo, el nombre del sitio ───────────────────────
# El bypass solo vale si el sitio que se pidió es ESTA PC: `localhost`,
# `127.0.0.1` o `[::1]`/`::1`, con o sin puerto y en cualquier combinación de
# mayúsculas. Es una lista cerrada y el texto se compara ENTERO (fullmatch) y sin
# recortar nada, no un pedazo: `localhost.evil.example`, `127.0.0.1.evil.example`,
# `evil.example@localhost`, `localhost:5050@evil.example` y hasta `localhost\n`
# NO pasan (un `strip()` dejaría pasar saltos de línea y espacios Unicode). Lo
# que no se puede leer es "no es local", o sea cerrado.
#
# Consecuencia a la vista: entrar a DEV por un alias del archivo hosts, o por
# cualquier otro nombre que no sea esos tres, deja de saltear el login.
_RE_HOST_LOCAL = re.compile(r'(?:localhost|127\.0\.0\.1|\[::1\])(?::\d{1,5})?|::1')


def _host_es_local(host):
    """True si `host` (el `request.host`: nombre del sitio y, a veces, puerto)
    es esta misma PC. Ver el bloque de arriba."""
    return _RE_HOST_LOCAL.fullmatch((host or '').lower()) is not None


# ── El email tiene que estar confirmado por Google ───────────────────────────
def _google_verifico_el_email(user_info):
    """
    True solo si Google dice que ese email está VERIFICADO (`email_verified`).

    Acepta el booleano True (lo que manda Google en el id_token y en el endpoint
    de userinfo) y el string 'true' (algunos endpoints, como tokeninfo, lo
    devuelven como texto). Todo lo demás es "no verificado": False, 'false',
    None, cualquier otro valor y la clave AUSENTE. Que una respuesta sin el dato
    no cuente como verificada es lo que hace de esto un filtro y no un adorno.

    Por qué hace falta si la lista blanca ya tiene el email: con una cuenta de
    Google creada con un email ajeno que no es @gmail.com y nunca se confirmó, el
    `email` del token es el que su titular DIJO tener, no uno comprobado.
    """
    valor = user_info.get('email_verified')
    if valor is True:
        return True
    return isinstance(valor, str) and valor.strip().lower() == 'true'


# ── Cookie de sesión Secure cuando la app sale por ngrok ─────────────────────
def _cookie_secure_para(cfg):
    """
    True si la app va a salir por el túnel de ngrok, o sea por HTTPS: ahí la
    cookie de sesión tiene que viajar solo por HTTPS (Secure).

    ES LA MISMA CONDICIÓN con la que `run_flask` (app.py) decide levantar el
    túnel: `first_run` apagado, `ngrok_enabled` prendido y 'DEV' fuera de
    `app_name`. Si cambia una, hay que cambiar la otra: auth.py no puede importar
    de app.py (app.py importa auth.py), así que la condición no vive en un solo
    lugar. `first_run` va primero en `run_flask` y por eso va acá: con él
    prendido el túnel NO se levanta y la app queda en localhost por http.

    ⚠ En DEV y en modo red local (http, a veces por IP) tiene que dar False: con
    Secure prendido el navegador no guarda la cookie y el login deja de andar.
    """
    return (not cfg.get('first_run', True)
            and bool(cfg.get('ngrok_enabled', False))
            and 'DEV' not in (cfg.get('app_name') or ''))


def init_auth(app, config_file):
    """
    Inicializa la autenticación OAuth con Google.
    Se llama desde app.py después de crear la app Flask.

    Parámetros:
        app: la instancia de Flask
        config_file: ruta al config.json (para leer client_id y secret)

    Lanza `ConfigIlegible` si config.json existe pero no se puede leer: ver
    "Secret key persistente".
    """
    cfg = cfg_module.cargar_config(config_file)

    # Las rutas del blueprint (login, auth/google, auth/callback) necesitan leer
    # la config en caliente y no ven este `config_file`.
    app.config['AUTH_CONFIG_FILE'] = config_file

    # ── Secret key persistente ───────────────────────────────────────────────
    # Flask necesita un secret_key fijo para que las sesiones (cookies)
    # sobrevivan reinicios del servidor. Si usamos os.urandom() cada vez,
    # se pierden todas las sesiones al reiniciar.
    #
    # Si config.json está ilegible, `cargar_config` devolvió DEFAULTS (sin
    # secret_key) y se llega acá a "generar una nueva". NO se escribe: sería
    # inventar una clave sobre un archivo que ya tiene la suya —y las
    # credenciales— y no se puede leer. `guardar_config` se niega y acá eso
    # corta el arranque con un mensaje claro: arrancar a ciegas dejaría la app
    # sin sesiones persistentes y sin saber por qué.
    secret_key = cfg.get('secret_key', '')
    if not secret_key:
        secret_key = secrets.token_hex(32)
        try:
            cfg_module.guardar_config({'secret_key': secret_key}, config_file)
        except cfg_module.ConfigIlegible as e:
            raise cfg_module.ConfigIlegible(
                f"config.json ilegible: arreglarlo antes de arrancar (no se "
                f"genera ni se guarda nada a ciegas). Detalle: {e}") from e
        log("OK: Secret key generada y guardada en config.json.")

    app.secret_key = secret_key

    # ── Configuración de sesión ──────────────────────────────────────────────
    app.config['SESSION_COOKIE_NAME'] = 'gastos_session'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=90)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    # Secure: el navegador manda la cookie SOLO por HTTPS. Se prende cuando la
    # app sale por el túnel de ngrok (que es HTTPS) y se deja apagado en DEV y en
    # red local, que van por http: ahí el navegador no la guardaría y el login
    # dejaría de andar. Se decide UNA vez, al arrancar, igual que el túnel.
    app.config['SESSION_COOKIE_SECURE'] = _cookie_secure_para(cfg)
    if app.config['SESSION_COOKIE_SECURE']:
        log("OK: Cookie de sesión Secure — la app sale por ngrok (HTTPS).")

    # ── Configurar OAuth con Google ──────────────────────────────────────────
    # ⚠ Las credenciales se registran en Authlib UNA vez, ACÁ, al arrancar. El
    # middleware sí lee la config en caliente (para cerrar el login si faltan),
    # pero cargar credenciales en config.json con la app corriendo NO alcanza:
    # el cliente de Authlib sigue con las del arranque (o con el placeholder
    # 'no-configurado') y Google las rechaza. Después de editar config.json hay
    # que REINICIAR el servicio.
    google_client_id = cfg.get('google_client_id', '')
    google_client_secret = cfg.get('google_client_secret', '')

    if google_client_id and google_client_secret:
        app.config['GOOGLE_CLIENT_ID'] = google_client_id
        app.config['GOOGLE_CLIENT_SECRET'] = google_client_secret

    oauth.init_app(app)
    oauth.register(
        name='google',
        client_id=google_client_id or 'no-configurado',
        client_secret=google_client_secret or 'no-configurado',
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile',
        },
    )

    # ── Registrar blueprint ──────────────────────────────────────────────────
    app.register_blueprint(auth_bp)

    # ── Middleware 1: los POST solo desde la propia app ───────────────────────
    # ⚠ Va ANTES que require_login: Flask corre los before_request en el orden en
    # que se registran. Un POST ajeno se frena sin mirar el login, y eso incluye
    # las rutas públicas y el bypass DEV. Ver el bloque "Los POST solo desde la
    # propia app".
    app.before_request(_exigir_origen_propio)

    # ── Middleware 2: proteger TODAS las rutas ────────────────────────────────
    @app.before_request
    def require_login():
        """
        Se ejecuta ANTES de cada request. Si el usuario no está autenticado,
        lo redirige al login. Excepciones: las rutas de auth mismas y archivos
        estáticos.
        """
        # Rutas que NO requieren autenticación
        # 'manifest' = /manifest.json (PWA). El navegador lo pide ANTES de que
        # exista sesión; si cayera en el redirect al login leería el HTML del
        # login como manifest y no ofrecería instalar la app. No expone datos:
        # solo nombre, colores de la paleta e íconos (que ya son públicos vía
        # 'static'). Ver la ruta en app.py.
        # 'service_worker' = /sw.js (PWA). Mismo problema que el manifest pero
        # peor: si cayera en el redirect al login, el navegador recibiría el
        # HTML del login donde espera JavaScript y el registro muere con
        # "unsupported MIME type (text/html)". Y no pasa una sola vez: el
        # navegador re-pide /sw.js en CADA navegación para chequear si hay
        # versión nueva, así que también se rompería el apagado de emergencia
        # (la lápida nunca llegaría). No expone datos: es código, y encima el
        # cuerpo lo decide `sw_enabled` de config.json. Ver la ruta en app.py.
        # OJO: acá va el nombre del ENDPOINT de Flask, no la URL.
        rutas_publicas = [
            'auth.login',
            'auth.google_login',
            'auth.callback',
            'auth.logout',
            'static',
            'manifest',
            'service_worker',
        ]

        if request.endpoint in rutas_publicas:
            return None

        cfg_actual = cfg_module.cargar_config(config_file)

        # ── Bypass DEV con CUÁDRUPLE CERROJO ──────────────────────────────────
        # El login se saltea SOLO si se cumplen las CUATRO condiciones a la vez:
        #   a. auth_disabled == True en config.json
        #   b. el request viene de localhost (127.0.0.1 / ::1)
        #   c. ngrok está apagado
        #   d. el sitio que se pidió (el Host) es localhost, 127.0.0.1 o ::1
        # El cerrojo (c) garantiza que no hay proxy, así que request.remote_addr
        # es confiable; por eso NO se usa X-Forwarded-For acá.
        #
        # El cerrojo (d) es contra el "DNS rebinding". (a), (b) y (c) miran DE
        # DÓNDE viene el pedido, no A QUÉ SITIO lo mandó el navegador, y con eso
        # solo no alcanza: una página maliciosa abierta en la PC de desarrollo usa
        # un dominio suyo que, ya cargada la página, pasa a resolver a 127.0.0.1.
        # Para el navegador sigue siendo el mismo sitio, así que el JavaScript de
        # esa página puede pedir y LEER la app DEV, que no pide login. El pedido
        # viene de 127.0.0.1 (se cumplen a, b y c) y hasta el chequeo de Origin
        # coincide con el Host. Lo único que lo delata es el nombre: llega
        # `Host: evil.example` en vez de `localhost`.
        #
        # Si CUALQUIERA falla → sigue el flujo de login normal (PROD intacto).
        bypass_posible = (cfg_actual.get('auth_disabled') is True
                          and request.remote_addr in ('127.0.0.1', '::1')
                          and not cfg_actual.get('ngrok_enabled'))
        if bypass_posible and _host_es_local(request.host):
            if not session.get('user_email'):
                session['user_email'] = 'dev@local'
                session['user_name'] = 'DEV'
            return None
        if bypass_posible and _toca_avisar(_aviso_bypass, _AVISO_BYPASS_CADA):
            # Solo avisa cuando el nombre es lo ÚNICO que impide el bypass: es el
            # caso de quien entra a DEV por un alias y no entiende por qué le pide
            # login, y también el rastro de un intento de DNS rebinding.
            log(f"AVISO: bypass DEV NO aplicado — el sitio pedido "
                f"('{_para_log(request.host)}') no es localhost, 127.0.0.1 ni ::1. "
                f"Entrar a DEV por localhost; si no fuiste vos, puede ser un intento "
                f"de DNS rebinding.")

        # ── FALLAR CERRADO ────────────────────────────────────────────────────
        # Sin credenciales de Google en la config en caliente (faltan, o
        # config.json está ilegible y `cargar_config` devolvió DEFAULTS), NO se
        # deja pasar a nadie. Esto antes decía "dejar pasar, para que puedan
        # configurar": con el túnel de ngrok, un config.json roto o a medias
        # dejaba la app abierta a todo internet. La puesta en marcha ya no es
        # por la web: es editar config.json y reiniciar (ver CONTEXT_CONFIG.md).
        #
        # El orden importa: va ANTES de mirar la sesión. Una config que no se
        # puede leer es un estado que no se puede verificar, y una cookie
        # firmada de ayer no lo arregla.
        if _faltan_credenciales(cfg_actual):
            return _login_cerrado()

        # Verificar sesión
        if not session.get('user_email'):
            return redirect(url_for('auth.login'))

        # Verificar que el email sigue siendo permitido
        if session['user_email'] not in EMAILS_PERMITIDOS:
            session.clear()
            return redirect(url_for('auth.login'))

        return None


# =============================================================================
# RUTAS DE AUTENTICACIÓN
# =============================================================================

@auth_bp.route('/login')
def login():
    """
    Página de login. Muestra un botón de "Iniciar sesión con Google".
    Si ya está logueado, redirige al inicio.

    Si faltan las credenciales de Google en la config, muestra SIEMPRE el aviso
    `no_configurado`, aunque no venga en la URL: quien llega acá a mano (un
    favorito, un link viejo) tiene que enterarse de que el login no anda.

    ⚠ ESE CHEQUEO VA PRIMERO, ANTES de mirar la sesión, y no es estética: es lo
    que evita un BUCLE DE REDIRECCIONES. Con una cookie válida de ayer y la
    config sin credenciales (o ilegible), si esto mirara la sesión primero
    mandaría a `/`; el middleware, que ve que faltan credenciales, devolvería
    a `/login?error=no_configurado`; y así sin fin: el navegador mostraría
    "demasiadas redirecciones" en vez del aviso. Por eso, sin credenciales, acá
    NUNCA se redirige a `index`, aunque haya sesión.
    """
    if _faltan_credenciales(_cfg_en_caliente()):
        return render_template('login.html', error='no_configurado')

    if session.get('user_email') and session['user_email'] in EMAILS_PERMITIDOS:
        return redirect(url_for('index'))

    error = request.args.get('error', '')
    return render_template('login.html', error=error)


@auth_bp.route('/auth/google')
def google_login():
    """
    Inicia el flujo OAuth con Google.
    Redirige al usuario a la página de login de Google.

    Sin credenciales en la config NO se habla con Google: el cliente de Authlib
    estaría registrado con el placeholder 'no-configurado' y lo único que se
    lograría es mandar al usuario a un error de Google.
    """
    if _faltan_credenciales(_cfg_en_caliente()):
        return _login_cerrado()

    # Construir la redirect_uri dinámicamente para que funcione con ngrok
    redirect_uri = url_for('auth.callback', _external=True)

    # Si estamos detrás de ngrok, el _external puede dar localhost.
    # Usamos el header X-Forwarded-Proto y Host para construir la URL correcta.
    if request.headers.get('X-Forwarded-Proto'):
        proto = request.headers.get('X-Forwarded-Proto', 'https')
        host = request.headers.get('Host', 'localhost')
        redirect_uri = f"{proto}://{host}/auth/callback"

    # Guardar "remember me" en la sesión para usarlo después del callback
    remember = request.args.get('remember', '0')
    session['_remember'] = remember == '1'

    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route('/auth/callback')
def callback():
    """
    Google redirige aquí después de que el usuario se autentica.
    Verifica el email y crea (o rechaza) la sesión.

    Sin credenciales en la config no se crea ninguna sesión, ni siquiera si el
    pedido trae un `code` de Google: es el mismo cierre que en el middleware.
    """
    if _faltan_credenciales(_cfg_en_caliente()):
        return _login_cerrado()

    try:
        token = oauth.google.authorize_access_token()
    except Exception as e:
        log(f"ERROR: Auth callback falló: {e}")
        return redirect(url_for('auth.login', error='google_error'))

    # Obtener información del usuario desde el token
    user_info = token.get('userinfo')
    if not user_info:
        try:
            user_info = oauth.google.userinfo()
        except Exception:
            return redirect(url_for('auth.login', error='google_error'))

    email = (user_info.get('email') or '').lower().strip()
    nombre = user_info.get('name', email)
    foto = user_info.get('picture', '')

    # ── Verificar si el email está en la lista de permitidos ─────────────────
    if email not in EMAILS_PERMITIDOS:
        log(f"AVISO: ACCESO DENEGADO — {email} intentó ingresar.")
        return redirect(url_for('auth.login', error='no_permitido'))

    # ── ...y que Google lo tenga confirmado ──────────────────────────────────
    # Mismo rechazo que un email no permitido (error=no_permitido): a quien
    # intenta entrar no le cambia nada, y en el log queda la razón. Un
    # `email_verified` falso o AUSENTE no entra, aunque el email esté en la lista.
    if not _google_verifico_el_email(user_info):
        log(f"AVISO: ACCESO DENEGADO — {email} está permitido, pero Google no lo "
            f"tiene como verificado (email_verified falso o ausente).")
        return redirect(url_for('auth.login', error='no_permitido'))

    # ── Crear sesión ─────────────────────────────────────────────────────────
    remember = session.pop('_remember', False)
    session.clear()

    session['user_email'] = email
    session['user_name'] = nombre
    session['user_photo'] = foto

    if remember:
        session.permanent = True  # Dura 90 días (configurado arriba)

    log(f"OK: Login exitoso — {nombre} ({email})")
    return redirect(url_for('index'))


# Tope del endpoint que puede llegar en el logout. Es el mismo criterio que
# `_PUSH_ENDPOINT_MAX` de app.py y va repetido a propósito: auth.py NO importa
# app.py (app.py importa auth.py — al revés sería un import circular), y lo
# único que se hace con este string es meterlo en un `WHERE endpoint = ?`
# parametrizado. Un endpoint inventado no borra nada; uno de 2 MB no tiene por
# qué llegar hasta el driver de SQLite.
_LOGOUT_ENDPOINT_MAX = 1000


@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    """Cierra la sesión y redirige al login.

    Antes de limpiar la sesión se borran las suscripciones push de esa cuenta:
    quien se va de un navegador deja de recibir ahí los avisos de su cuenta.

    ⚠ EL ORDEN NO ES CASUAL. Tiene que ser ANTES del `session.clear()`, que es
    donde vive el email — después del clear no habría a quién borrarle nada y
    la fila quedaría viva para siempre. Es el mismo motivo por el que
    `user_name` se lee arriba.

    ⚠ Y VA EN try/except A PROPÓSITO: si el borrado falla (base bloqueada,
    disco lleno), el usuario TIENE que poder desloguearse igual. Una
    suscripción huérfana es un aviso de más en un teléfono; no poder salir de
    la sesión es quedarse adentro de la app.

    SE BORRA SOLO EL NAVEGADOR QUE SE VA, si dice cuál es. El front
    (`initSalir()` en app.js) desuscribe este navegador y manda su `endpoint`
    por POST antes de navegar; con ese dato el borrado se acota a UNA fila.
    Sin el dato —sin JavaScript, un link pegado a mano, un navegador sin push—
    se cae al comportamiento de siempre: se borran todas las filas de esa
    cuenta. Eso cierra la deuda que quedó anotada en `CONTEXT_AUTH.md`:

      · el efecto colateral molesto: desloguearse en la notebook apagaba los
        avisos del teléfono;
      · y el filo del `/logout` GET y público, que con `SameSite=Lax` acepta
        la navegación cross-site: un link desde cualquier lado se llevaba las
        suscripciones de TODOS los dispositivos. Ahora, en el peor caso, se
        lleva una sola — y solo si quien lo arma conoce ese endpoint.

    El método POST se acepta por eso: el endpoint es el buzón de un teléfono y
    no tiene por qué quedar en el log de accesos ni en el historial. GET sigue
    andando igual, que es lo que hace que salir nunca dependa de JavaScript.
    """
    nombre = session.get('user_name', 'Usuario')
    email = session.get('user_email', '')
    # SOLO del form, nunca del querystring. El endpoint es el buzón de un
    # teléfono: en la URL quedaría en el historial del navegador y, en
    # producción, en el inspector de ngrok, que registra la URL entera. El
    # front lo manda por POST; aceptar `request.values` dejaba abierta por
    # querystring la misma puerta que el POST venía a cerrar, y encima sin que
    # nadie la usara.
    endpoint = (request.form.get('endpoint') or '').strip()

    try:
        import database
        if email and endpoint and len(endpoint) <= _LOGOUT_ENDPOINT_MAX:
            # ⚠ EL `email and` NO SOBRA. `borrar_suscripcion_push()` con
            # `user_email` vacío borra por endpoint SOLO, sin dueño — y
            # /logout es público, así que sin esa condición un pedido sin
            # sesión con el endpoint de otro le borraría la fila. Con sesión,
            # el DELETE va acotado al email, igual que /api/push/baja.
            borradas = database.borrar_suscripcion_push(endpoint, email)
            cuantas = f"{borradas} suscripción(es) push de este navegador"
        else:
            borradas = database.borrar_suscripciones_push_de_email(email)
            cuantas = f"{borradas} suscripción(es) push (todas las de la cuenta)"
        if borradas:
            log(f"OK: Logout — se borraron {cuantas} de {email}.")
    except Exception as e:
        log(f"AVISO: No se pudieron borrar las suscripciones push de {email}: {e}")

    session.clear()
    log(f"OK: Logout — {nombre}")
    return redirect(url_for('auth.login'))
