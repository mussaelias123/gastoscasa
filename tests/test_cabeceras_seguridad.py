# =============================================================================
# ARCHIVO: tests/test_cabeceras_seguridad.py
# =============================================================================
#
# Tests de las cabeceras de seguridad, de la política de scripts (CSP con
# nonce) y del tope de 1 MB por pedido. El código está en app.py, bloque
# "CABECERAS DE SEGURIDAD + POLÍTICA DE SCRIPTS" y `MAX_CONTENT_LENGTH`.
#
# POR QUÉ EXISTE ESTE ARCHIVO
#
#   Todo lo que se prueba acá falla EN SILENCIO: la app responde 200, las
#   pantallas se ven igual en el servidor, y nadie se entera hasta que el
#   navegador —o un atacante— se comporta distinto.
#
#   1. EL NONCE QUE NO COINCIDE. Si la cabecera dice `nonce-A` y el template
#      imprime `nonce-B`, el navegador bloquea TODOS los scripts de la página:
#      botones muertos, gráficos en blanco. Ningún test de rutas lo ve (es un
#      200 con HTML). Por eso el test central mira lo que ve el template y lo
#      compara con la cabecera de ESE pedido.
#
#   2. EL NONCE QUE SE REPITE. Un nonce fijo parece funcionar igual, pero es
#      una contraseña que el atacante aprende en su primer pedido: la política
#      queda de adorno. Se mide que cambie en cada pedido.
#
#   3. LA POLÍTICA QUE SE AFLOJA. El día que un script inline se bloquee, la
#      salida fácil es agregar `'unsafe-inline'` o `'unsafe-eval'` a
#      `script-src`. La política se compara carácter por carácter contra una
#      copia escrita a mano acá, así que cualquier cambio salta.
#
#   4. HSTS EN DEV. Solo corresponde detrás del túnel (https de verdad).
#
#   5. EL TOPE. `/logout` es pública y lee `request.form`: sin tope, un POST
#      multipart gigante, sin login, se volcaba a un temporal del disco. Cada
#      test de "el tope corta" tiene su contracara que dice "sin tope, no
#      corta": un test que pasaría igual sin el límite no prueba nada.
#
# HERMÉTICOS: no dependen del config.json de la máquina (el de DEV tiene
# `auth_disabled=True`, que saltea el login). Cada test fija la config con un
# `cargar_config` falso que parte de DEFAULTS, usa una base SQLite temporal y
# entra con una sesión explícita cuando hace falta.
#
# COMO CORRER:
#   Desde la raíz del proyecto:
#       python -m unittest tests.test_cabeceras_seguridad -v
#
# =============================================================================

import contextlib
import os
import re
import shutil
import sys
import tempfile
import unittest
import unittest.mock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import werkzeug.formparser  # noqa: E402
import werkzeug.wrappers.request  # noqa: E402
from flask import Response, g, render_template_string  # noqa: E402

import app as app_module  # noqa: E402
import auth  # noqa: E402
import config  # noqa: E402
import database  # noqa: E402


EMAIL_OK = 'mussaelias123@gmail.com'

# Config "con el login puesto de verdad": credenciales, sin bypass, sin ngrok.
CON_LOGIN = dict(google_client_id='id', google_client_secret='s',
                 auth_disabled=False, ngrok_enabled=False)

UN_MB = 1024 * 1024

# La política, escrita A MANO a propósito (no se importa de app.py): si se
# importara, un cambio en la constante cambiaría el test con ella. `{NONCE}` se
# reemplaza por el nonce que vino en la cabecera.
CSP_ESPERADA = (
    "default-src 'self'; "
    "script-src 'self' 'nonce-{NONCE}'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https://*.googleusercontent.com; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "manifest-src 'self'; "
    "worker-src 'self'; "
    "frame-src 'none'; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

# Las que van en TODA respuesta, sea HTML, JSON, estático o error.
CABECERAS_SIEMPRE = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'same-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=()',
    'Cross-Origin-Opener-Policy': 'same-origin',
}

# (ruta, con sesión, status esperado, ¿es HTML?). El status esperado va para
# que el test falle si el pedido NO es el que se cree (un /gastos sin sesión es
# un 302, no la página).
PEDIDOS = {
    'página HTML':       ('/gastos',              True,  200, True),
    'JSON de /api':      ('/api/saldos',          True,  200, False),
    'estático':          ('/static/style.css',    False, 200, False),
    'login':             ('/login',               False, 200, True),
    'página 404':        ('/esta-ruta-no-existe', True,  404, True),
    'redirect al login': ('/gastos',              False, 302, True),
    'service worker':    ('/sw.js',               False, 200, False),
    'manifest':          ('/manifest.json',       False, 200, False),
}

NONCE_EN_CABECERA = re.compile(r"'nonce-([A-Za-z0-9_-]+)'")
NONCE_EN_HTML = re.compile(r'<script nonce="([^"]*)"></script>')


def _cfg_falsa(**cambios):
    """
    Un `cargar_config` falso, hermético: parte de DEFAULTS —no del config.json
    de la máquina— y pisa las claves que se pidan.
    """
    def falso(ruta=None):
        cfg = dict(config.DEFAULTS)
        cfg.update(cambios)
        return cfg
    return falso


def _render_que_usa_el_nonce(*args, **kwargs):
    """
    Reemplazo de `render_template` para los tests del contrato del nonce: en
    vez del template de verdad dibuja el <script> mínimo que lo usa. Pasa por
    `render_template_string`, que corre los MISMOS context processors que
    `render_template`: lo que ve acá es lo que vería cualquier template.
    """
    return render_template_string('<script nonce="{{ csp_nonce }}"></script>')


class BaseSeguridad(unittest.TestCase):
    """Cada test: base temporal vacía, login configurado y un cliente nuevo."""

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix='fondo-cabeceras-')
        self._db_original = database.DB_PATH
        database.DB_PATH = os.path.join(self._dir, 'fondo.db')
        database.inicializar_db()
        self.client = app_module.app.test_client()
        parche = unittest.mock.patch.object(
            config, 'cargar_config', _cfg_falsa(**CON_LOGIN))
        parche.start()
        self.addCleanup(parche.stop)
        # Sin esto cada logout de prueba imprimiría su línea de log en la
        # consola (con `python -m unittest`, que no captura la salida).
        parche_log = unittest.mock.patch.object(auth, 'log')
        parche_log.start()
        self.addCleanup(parche_log.stop)

    def tearDown(self):
        database.DB_PATH = self._db_original
        shutil.rmtree(self._dir, ignore_errors=True)

    # -- Atajos -------------------------------------------------------------

    def login(self, cliente=None):
        """Deja una sesión válida en el cliente, como después del OAuth."""
        cliente = cliente or self.client
        with cliente.session_transaction() as sesion:
            sesion['user_email'] = EMAIL_OK
            sesion['user_name'] = 'Elias'

    def pedir(self, ruta, con_sesion=False, **kwargs):
        """
        GET con un cliente nuevo cada vez: sin cookies de un pedido anterior.
        `buffered=True` lee y cierra la respuesta: un estático llega como un
        archivo abierto, y sin cerrarlo queda colgado hasta que lo junta el GC.
        """
        cliente = app_module.app.test_client()
        if con_sesion:
            self.login(cliente)
        return cliente.get(ruta, buffered=True, **kwargs)

    def nonce_de(self, respuesta):
        """El nonce que la cabecera CSP de esa respuesta declara."""
        encontrado = NONCE_EN_CABECERA.search(
            respuesta.headers.get('Content-Security-Policy', ''))
        self.assertIsNotNone(encontrado, 'la respuesta no trae nonce en la CSP')
        return encontrado.group(1)


# ── 1. Cabeceras generales ───────────────────────────────────────────────────

class TestCabecerasGenerales(BaseSeguridad):

    def test_estan_en_todo_tipo_de_respuesta(self):
        for nombre, (ruta, con_sesion, status, _html) in PEDIDOS.items():
            with self.subTest(nombre):
                r = self.pedir(ruta, con_sesion)
                self.assertEqual(r.status_code, status)
                for cabecera, valor in CABECERAS_SIEMPRE.items():
                    self.assertEqual(r.headers.get(cabecera), valor,
                                     f'{cabecera} en {nombre}')

    def test_permissions_policy_no_bloquea_notificaciones_ni_push(self):
        """La app usa Web Push: bloquearlo mataría los avisos del teléfono."""
        politica = self.pedir('/login').headers['Permissions-Policy']
        self.assertNotIn('notifications', politica)
        self.assertNotIn('push', politica)

    def test_una_cabecera_que_la_ruta_ya_puso_se_respeta(self):
        """`setdefault`: lo que pone la ruta gana, y no queda duplicado."""
        with app_module.app.test_request_context('/'):
            resp = Response('<p>x</p>', mimetype='text/html')
            resp.headers['X-Frame-Options'] = 'SAMEORIGIN'
            resp.headers['Content-Security-Policy'] = "default-src 'none'"
            salida = app_module.app.process_response(resp)
        self.assertEqual(salida.headers.getlist('X-Frame-Options'), ['SAMEORIGIN'])
        self.assertEqual(salida.headers.getlist('Content-Security-Policy'),
                         ["default-src 'none'"])
        # Y las que la ruta no puso, las completa.
        self.assertEqual(salida.headers['X-Content-Type-Options'], 'nosniff')

    def test_conviven_con_la_compresion(self):
        """Compress es otro after_request: no tiene que pisar ni perder nada."""
        r = self.pedir('/gastos', True, headers={'Accept-Encoding': 'gzip'})
        self.assertEqual(r.headers.get('Content-Encoding'), 'gzip')
        self.assertIn('Content-Security-Policy', r.headers)
        for cabecera, valor in CABECERAS_SIEMPRE.items():
            self.assertEqual(r.headers.get(cabecera), valor)


# ── 2. HSTS ──────────────────────────────────────────────────────────────────

class TestHSTS(BaseSeguridad):

    def test_sin_tunel_no_hay_hsts(self):
        """DEV (http://localhost): nunca."""
        for nombre, (ruta, con_sesion, _status, _html) in PEDIDOS.items():
            with self.subTest(nombre):
                r = self.pedir(ruta, con_sesion)
                self.assertNotIn('Strict-Transport-Security', r.headers)

    def test_con_tunel_https_hay_hsts_en_todo_tipo_de_respuesta(self):
        for nombre, (ruta, con_sesion, _status, _html) in PEDIDOS.items():
            with self.subTest(nombre):
                r = self.pedir(ruta, con_sesion,
                               headers={'X-Forwarded-Proto': 'https'})
                # Exacto: sin includeSubDomains ni preload (el dominio de
                # ngrok no es nuestro).
                self.assertEqual(r.headers.get('Strict-Transport-Security'),
                                 'max-age=31536000')

    def test_forwarded_proto_http_no_activa_hsts(self):
        r = self.pedir('/login', headers={'X-Forwarded-Proto': 'http'})
        self.assertNotIn('Strict-Transport-Security', r.headers)

    def test_la_cabecera_se_lee_sin_importar_mayusculas_ni_espacios(self):
        r = self.pedir('/login', headers={'X-Forwarded-Proto': ' HTTPS '})
        self.assertEqual(r.headers.get('Strict-Transport-Security'),
                         'max-age=31536000')

    def test_con_varios_proxies_manda_el_primero(self):
        """"https, http" = el navegador habló https; "http, https" no."""
        r = self.pedir('/login', headers={'X-Forwarded-Proto': 'https, http'})
        self.assertIn('Strict-Transport-Security', r.headers)
        r = self.pedir('/login', headers={'X-Forwarded-Proto': 'http, https'})
        self.assertNotIn('Strict-Transport-Security', r.headers)

    def test_si_flask_sirve_tls_directo_tambien_hay_hsts(self):
        cliente = app_module.app.test_client()
        r = cliente.get('/login', base_url='https://localhost')
        self.assertEqual(r.headers.get('Strict-Transport-Security'),
                         'max-age=31536000')


# ── 3. CSP ───────────────────────────────────────────────────────────────────

class TestCSP(BaseSeguridad):

    def test_la_politica_es_exactamente_la_del_contrato(self):
        """En las cuatro formas de HTML: página, login, 404 y redirect."""
        for nombre, (ruta, con_sesion, _status, es_html) in PEDIDOS.items():
            if not es_html:
                continue
            with self.subTest(nombre):
                r = self.pedir(ruta, con_sesion)
                nonce = self.nonce_de(r)
                self.assertEqual(r.headers['Content-Security-Policy'],
                                 CSP_ESPERADA.replace('{NONCE}', nonce))

    def test_solo_va_en_las_respuestas_html(self):
        """Una política es del documento: en un JSON, un .css o el SW no va."""
        for nombre, (ruta, con_sesion, _status, es_html) in PEDIDOS.items():
            if es_html:
                continue
            with self.subTest(nombre):
                r = self.pedir(ruta, con_sesion)
                self.assertNotIn('Content-Security-Policy', r.headers)

    def test_script_src_solo_deja_el_propio_origen_y_el_nonce(self):
        csp = self.pedir('/gastos', True).headers['Content-Security-Policy']
        directivas = dict(d.split(' ', 1) for d in csp.split('; '))
        fuentes = directivas['script-src'].split()
        self.assertEqual(len(fuentes), 2, fuentes)
        self.assertEqual(fuentes[0], "'self'")
        self.assertTrue(fuentes[1].startswith("'nonce-"), fuentes)
        # `'unsafe-inline'` solo en estilos; `'unsafe-eval'` en ningún lado.
        con_unsafe_inline = [k for k, v in directivas.items()
                             if "'unsafe-inline'" in v.split()]
        self.assertEqual(con_unsafe_inline, ['style-src'])
        self.assertNotIn("'unsafe-eval'", csp)
        self.assertNotIn("'strict-dynamic'", csp)

    def test_el_nonce_tiene_forma_de_token_urlsafe_de_16_bytes(self):
        nonce = self.nonce_de(self.pedir('/login'))
        self.assertRegex(nonce, r'^[A-Za-z0-9_-]{22}$')

    def test_el_nonce_cambia_en_cada_pedido(self):
        """Mismo cliente, mismas cookies, misma página: nonces distintos."""
        nonces = {self.nonce_de(self.client.get('/login')) for _ in range(20)}
        self.assertEqual(len(nonces), 20)

    def test_con_sesion_el_nonce_tambien_cambia(self):
        self.login()
        nonces = {self.nonce_de(self.client.get('/gastos')) for _ in range(5)}
        self.assertEqual(len(nonces), 5)


# ── 4. Contrato del nonce con los templates ──────────────────────────────────

class TestNonceDelTemplate(BaseSeguridad):
    """
    La variable `csp_nonce` que ven los templates y la cabecera del MISMO
    pedido tienen que ser el mismo valor. Se prueba con un template mínimo
    (`_render_que_usa_el_nonce`) en lugar de los de verdad, así el test no
    depende de qué template ya estrenó el nonce.
    """

    def test_el_template_de_una_pagina_de_la_app_ve_el_nonce_de_la_cabecera(self):
        """El 404 es una página común de la app: la dibuja `render_template`."""
        self.login()
        with unittest.mock.patch.object(
                app_module, 'render_template', _render_que_usa_el_nonce):
            r = self.client.get('/esta-ruta-no-existe')
        self.assertEqual(r.status_code, 404)
        en_html = NONCE_EN_HTML.search(r.get_data(as_text=True))
        self.assertIsNotNone(en_html, r.get_data(as_text=True)[:200])
        self.assertTrue(en_html.group(1))
        self.assertEqual(en_html.group(1), self.nonce_de(r))

    def test_login_tambien_lo_ve_aunque_no_extiende_base_html(self):
        """`login.html` lo dibuja el blueprint de auth, no la app."""
        with unittest.mock.patch.object(
                auth, 'render_template', _render_que_usa_el_nonce):
            r = self.client.get('/login')
        self.assertEqual(r.status_code, 200)
        en_html = NONCE_EN_HTML.search(r.get_data(as_text=True))
        self.assertIsNotNone(en_html, r.get_data(as_text=True)[:200])
        self.assertTrue(en_html.group(1))
        self.assertEqual(en_html.group(1), self.nonce_de(r))

    def test_dos_pedidos_dos_nonces_tambien_para_el_template(self):
        with unittest.mock.patch.object(
                auth, 'render_template', _render_que_usa_el_nonce):
            r1 = self.client.get('/login')
            r2 = self.client.get('/login')
        n1 = NONCE_EN_HTML.search(r1.get_data(as_text=True)).group(1)
        n2 = NONCE_EN_HTML.search(r2.get_data(as_text=True)).group(1)
        self.assertNotEqual(n1, n2)
        self.assertEqual(n1, self.nonce_de(r1))
        self.assertEqual(n2, self.nonce_de(r2))

    def test_dentro_de_un_pedido_el_nonce_no_cambia(self):
        """Página + partials = varios render en el mismo pedido, un solo nonce."""
        with app_module.app.test_request_context('/'):
            primero = render_template_string('{{ csp_nonce }}')
            segundo = render_template_string('{{ csp_nonce }}')
            guardado = g.csp_nonce
        self.assertEqual(primero, segundo)
        self.assertEqual(primero, guardado)
        self.assertRegex(primero, r'^[A-Za-z0-9_-]{22}$')
        # Y es perezoso por pedido: otro pedido, otro valor.
        with app_module.app.test_request_context('/'):
            otro = render_template_string('{{ csp_nonce }}')
        self.assertNotEqual(primero, otro)

    def test_html_que_nunca_uso_el_nonce_lleva_la_cabecera_igual(self):
        """
        Una respuesta HTML cuyo template no pidió el nonce igual lleva CSP, y
        el nonce queda guardado: si después alguien renderiza, lee el mismo.
        """
        with app_module.app.test_request_context('/'):
            self.assertIsNone(g.get('csp_nonce'), 'nadie lo pidió todavía')
            salida = app_module.app.process_response(
                Response('<p>hola</p>', mimetype='text/html'))
            nonce = self.nonce_de(salida)
            self.assertEqual(g.csp_nonce, nonce)
            self.assertEqual(render_template_string('{{ csp_nonce }}'), nonce)


# ── 5. Contenido que no se tiene que romper ──────────────────────────────────

class TestLoQueNoCambia(BaseSeguridad):
    """El service worker y el manifest siguen siendo lo que eran."""

    def test_sw_js_sigue_siendo_javascript_y_sin_cache(self):
        r = self.pedir('/sw.js')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, 'application/javascript')
        self.assertEqual(r.headers.get('Cache-Control'), 'no-cache')
        self.assertIn('addEventListener', r.get_data(as_text=True))

    def test_manifest_sigue_siendo_manifest_json(self):
        r = self.pedir('/manifest.json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, 'application/manifest+json')
        self.assertIn('icons', r.get_json(force=True))

    def test_json_y_estaticos_conservan_su_content_type(self):
        self.assertEqual(self.pedir('/api/saldos', True).mimetype, 'application/json')
        self.assertEqual(self.pedir('/static/style.css').mimetype, 'text/css')

    def test_los_js_y_css_estaticos_tienen_un_mime_que_nosniff_acepta(self):
        """
        Con `nosniff` el navegador SOLO ejecuta un <script src> (o aplica una
        hoja) si el servidor lo declara como JavaScript (o CSS). El
        Content-Type de un estático sale de `mimetypes`, que en Windows lee el
        registro: una máquina con el registro raro serviría los .js como
        `application/octet-stream` y, ahora, todos los scripts morirían sin
        que el servidor se entere. Este test corre en la máquina donde se
        corre, que es justo lo que hace falta mirar.
        """
        validos = {'.js': {'text/javascript', 'application/javascript'},
                   '.css': {'text/css'}}
        base = os.path.join(ROOT_DIR, 'static')
        vistos = 0
        for carpeta, _subcarpetas, archivos in os.walk(base):
            for nombre in sorted(archivos):
                ext = os.path.splitext(nombre)[1].lower()
                if ext not in validos:
                    continue
                relativa = os.path.relpath(os.path.join(carpeta, nombre), base)
                ruta = '/static/' + relativa.replace(os.sep, '/')
                with self.subTest(ruta):
                    r = self.pedir(ruta)
                    self.assertEqual(r.status_code, 200)
                    self.assertIn(r.mimetype, validos[ext])
                vistos += 1
        self.assertGreater(vistos, 0, 'no se encontró ningún .js/.css en static/')


# ── 6. Tope de 1 MB por pedido ───────────────────────────────────────────────

@contextlib.contextmanager
def _contar_temporales():
    """
    Cuenta cuántas veces Werkzeug pide un archivo temporal para guardar una
    parte "archivo" de un multipart (`default_stream_factory`). Delega en la
    de verdad: lo único que agrega es el conteo.

    Se parchea en los DOS módulos donde vive el nombre: `Request` lo busca en
    `werkzeug.wrappers.request`, y `FormDataParser` en `werkzeug.formparser`.
    """
    pedidos = []
    with contextlib.ExitStack() as pila:
        for modulo in (werkzeug.wrappers.request, werkzeug.formparser):
            original = modulo.default_stream_factory

            def vigilante(*args, _original=original, **kwargs):
                pedidos.append(1)
                return _original(*args, **kwargs)

            pila.enter_context(unittest.mock.patch.object(
                modulo, 'default_stream_factory', vigilante))
        yield pedidos


class TestTopePorPedido(BaseSeguridad):

    def post_multipart(self, tamano):
        """
        POST a /logout con una parte "archivo" de `tamano` bytes. El cuerpo se
        arma a mano y no pasándole el archivo al cliente de pruebas: ese vuelca
        todo multipart de más de 500 KB a un temporal DE SU LADO, y lo que se
        mide acá es el temporal del servidor.
        """
        frontera = 'frontera-de-prueba'
        cuerpo = (
            f'--{frontera}\r\n'
            'Content-Disposition: form-data; name="archivo"; filename="relleno.bin"\r\n'
            'Content-Type: application/octet-stream\r\n\r\n'
        ).encode() + b'x' * tamano + f'\r\n--{frontera}--\r\n'.encode()
        return self.client.post(
            '/logout', data=cuerpo,
            content_type=f'multipart/form-data; boundary={frontera}')

    def test_el_tope_es_de_un_mb(self):
        self.assertEqual(app_module.app.config['MAX_CONTENT_LENGTH'], UN_MB)

    def test_multipart_gigante_a_logout_es_413_y_no_toca_el_disco(self):
        """
        El ataque: `/logout` es pública, sin login, y lee `request.form`. El
        413 sale ANTES de armar ningún archivo temporal.
        """
        with _contar_temporales() as temporales:
            r = self.post_multipart(UN_MB + 4096)
        self.assertEqual(r.status_code, 413)
        self.assertEqual(temporales, [], 'se pidió un archivo temporal')

    def test_contracara_sin_tope_el_mismo_pedido_si_arma_el_temporal(self):
        """
        Sin esto el test de arriba podría pasar por una razón equivocada (un
        parche apuntando a un nombre que nadie usa). Sacando el tope, el mismo
        pedido SÍ pide el temporal y /logout responde su redirect de siempre.
        """
        with unittest.mock.patch.dict(
                app_module.app.config, {'MAX_CONTENT_LENGTH': None}):
            with _contar_temporales() as temporales:
                r = self.post_multipart(UN_MB + 4096)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(temporales, 'sin tope, el parser debía pedir el temporal')

    def test_form_gigante_a_logout_tambien_es_413(self):
        r = self.client.post('/logout', data={'endpoint': 'x' * (UN_MB + 1)})
        self.assertEqual(r.status_code, 413)

    def test_el_limite_es_exacto(self):
        """Un cuerpo de 1 MB justo pasa; un byte más, no."""
        justo = self.client.post('/logout', data=b'x' * UN_MB,
                                 content_type='application/octet-stream')
        self.assertEqual(justo.status_code, 302)
        de_mas = self.client.post('/logout', data=b'x' * (UN_MB + 1),
                                  content_type='application/octet-stream')
        self.assertEqual(de_mas.status_code, 413)

    def test_un_archivo_grande_pero_dentro_del_tope_pasa(self):
        """El tope es 1 MB, no más chico: 900 KB de archivo no molestan."""
        r = self.post_multipart(900 * 1024)
        self.assertEqual(r.status_code, 302)

    def test_logout_normal_sigue_andando(self):
        self.login()
        r = self.client.post('/logout', data={'endpoint': 'https://x.example/p'})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers['Location'].endswith('/login'))
        with self.client.session_transaction() as sesion:
            self.assertNotIn('user_email', sesion)

    def test_el_413_no_tiene_efectos(self):
        """Rechazado antes de ejecutar nada: ni borra suscripciones ni desloguea."""
        database.guardar_suscripcion_push(
            'https://fcm.googleapis.com/fcm/send/abc', 'B' + 'a' * 86, 'c' * 22,
            'elias', EMAIL_OK)
        self.login()
        r = self.client.post('/logout', data={'endpoint': 'x' * (UN_MB + 1)})
        self.assertEqual(r.status_code, 413)
        self.assertEqual(len(database.obtener_suscripciones_push()), 1)
        with self.client.session_transaction() as sesion:
            self.assertEqual(sesion.get('user_email'), EMAIL_OK)

    def test_el_413_tambien_lleva_las_cabeceras_de_seguridad(self):
        r = self.client.post('/logout', data=b'x' * (UN_MB + 1),
                             content_type='application/octet-stream')
        self.assertEqual(r.status_code, 413)
        for cabecera, valor in CABECERAS_SIEMPRE.items():
            self.assertEqual(r.headers.get(cabecera), valor)
        self.assertIn('Content-Security-Policy', r.headers)


if __name__ == '__main__':
    unittest.main()
