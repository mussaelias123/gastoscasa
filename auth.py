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
#   5. Si el email está en la lista de permitidos, se crea la sesión.
#   6. Si no, se muestra un error de "acceso denegado".
#
# EMAILS PERMITIDOS:
#   Solo estos emails de Google pueden acceder:
#     - mussaelias123@gmail.com
#     - mossinomariana@gmail.com
#
# =============================================================================

import os
import json
import secrets
import functools
from datetime import timedelta
from flask import (
    Blueprint, session, redirect, url_for, request,
    render_template, flash, current_app
)
from authlib.integrations.flask_client import OAuth
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


def init_auth(app, config_file):
    """
    Inicializa la autenticación OAuth con Google.
    Se llama desde app.py después de crear la app Flask.

    Parámetros:
        app: la instancia de Flask
        config_file: ruta al config.json (para leer client_id y secret)
    """
    import config as cfg_module

    cfg = cfg_module.cargar_config(config_file)

    # ── Secret key persistente ───────────────────────────────────────────────
    # Flask necesita un secret_key fijo para que las sesiones (cookies)
    # sobrevivan reinicios del servidor. Si usamos os.urandom() cada vez,
    # se pierden todas las sesiones al reiniciar.
    secret_key = cfg.get('secret_key', '')
    if not secret_key:
        secret_key = secrets.token_hex(32)
        cfg_module.guardar_config({'secret_key': secret_key}, config_file)
        log("OK: Secret key generada y guardada en config.json.")

    app.secret_key = secret_key

    # ── Configuración de sesión ──────────────────────────────────────────────
    app.config['SESSION_COOKIE_NAME'] = 'gastos_session'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=90)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # ── Configurar OAuth con Google ──────────────────────────────────────────
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

    # ── Middleware: proteger TODAS las rutas ──────────────────────────────────
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

        # ── Bypass DEV con TRIPLE CERROJO ─────────────────────────────────────
        # El login se saltea SOLO si se cumplen las TRES condiciones a la vez:
        #   a. auth_disabled == True en config.json
        #   b. el request viene de localhost (127.0.0.1 / ::1)
        #   c. ngrok está apagado
        # El cerrojo (c) garantiza que no hay proxy, así que request.remote_addr
        # es confiable; por eso NO se usa X-Forwarded-For acá.
        # Si CUALQUIERA falla → sigue el flujo de login normal (PROD intacto).
        if (cfg_actual.get('auth_disabled') is True
                and request.remote_addr in ('127.0.0.1', '::1')
                and not cfg_actual.get('ngrok_enabled')):
            if not session.get('user_email'):
                session['user_email'] = 'dev@local'
                session['user_name'] = 'DEV'
            return None

        # Si no hay OAuth configurado, dejar pasar (para que puedan configurar)
        if not cfg_actual.get('google_client_id') or not cfg_actual.get('google_client_secret'):
            return None

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
    """
    if session.get('user_email') and session['user_email'] in EMAILS_PERMITIDOS:
        return redirect(url_for('index'))

    error = request.args.get('error', '')
    return render_template('login.html', error=error)


@auth_bp.route('/auth/google')
def google_login():
    """
    Inicia el flujo OAuth con Google.
    Redirige al usuario a la página de login de Google.
    """
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
    """
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

    email = user_info.get('email', '').lower().strip()
    nombre = user_info.get('name', email)
    foto = user_info.get('picture', '')

    # ── Verificar si el email está en la lista de permitidos ─────────────────
    if email not in EMAILS_PERMITIDOS:
        log(f"AVISO: ACCESO DENEGADO — {email} intentó ingresar.")
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
