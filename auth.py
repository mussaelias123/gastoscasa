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
        rutas_publicas = [
            'auth.login',
            'auth.google_login',
            'auth.callback',
            'auth.logout',
            'static',
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


@auth_bp.route('/logout')
def logout():
    """Cierra la sesión y redirige al login."""
    nombre = session.get('user_name', 'Usuario')
    session.clear()
    log(f"OK: Logout — {nombre}")
    return redirect(url_for('auth.login'))
