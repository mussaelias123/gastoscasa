# =============================================================================
# ARCHIVO: tests/test_auth_cerrado.py
# =============================================================================
#
# Tests de que la app FALLA CERRADO: sin credenciales de Google en config.json
# (o con el archivo ilegible) no entra nadie.
#
# POR QUE EXISTE ESTE ARCHIVO
#
#   auth.py tenia un "si no hay OAuth configurado, dejar pasar" pensado para el
#   primer arranque. Con el tunel de ngrok eso es una puerta abierta a todo
#   internet, y bastaba un config.json roto o a medias (o escrito en el
#   momento justo) para que `cargar_config` devolviera DEFAULTS, sin
#   credenciales, y la app quedara abierta. Comprobado: con la config ilegible,
#   GET /gastos sin sesion daba 200.
#
#   Decision del usuario: la configuracion inicial se hace por config.json, no
#   por la web, asi que el modo "dejar pasar" no se necesita y se elimino. Sin
#   credenciales la app queda CERRADA para todos.
#
#   La falla que estos tests cuidan es SILENCIOSA: la app anda perfecto con la
#   puerta abierta. Nadie lo nota hasta que alguien de afuera entra. Por eso
#   cada test que dice "cerrado" tiene su contracara que dice "abierto":
#   un test de "no deja pasar" que pasaria igual con el login apagado no prueba
#   nada.
#
# HERMETICOS: no dependen de que la app este abierta ni del bypass DEV que tenga
# el config.json de la maquina (el de DEV tiene auth_disabled=True). Cada test
# fija la config con un `cargar_config` falso que parte de DEFAULTS, usa una base
# SQLite temporal y entra con una sesion explicita cuando hace falta.
#
# COMO CORRER:
#   Desde la raiz del proyecto:
#       python -m unittest tests.test_auth_cerrado -v
#
# =============================================================================

import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from urllib.parse import parse_qs, urlsplit

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from authlib.integrations.flask_client import OAuth  # noqa: E402
from flask import Flask, redirect  # noqa: E402

import app as app_module  # noqa: E402
import auth  # noqa: E402
import config  # noqa: E402
import database  # noqa: E402


EMAIL_OK = 'mussaelias123@gmail.com'

# Config "con el login puesto de verdad": credenciales, sin bypass, sin ngrok.
CON_LOGIN = dict(google_client_id='id-de-prueba',
                 google_client_secret='secreto-de-prueba',
                 auth_disabled=False, ngrok_enabled=False)
# Lo mismo pero sin credenciales (el caso que antes dejaba pasar).
SIN_CREDENCIALES = dict(CON_LOGIN, google_client_id='', google_client_secret='')

# Un movimiento valido. Si la puerta estuviera abierta, este POST insertaria una
# fila: por eso sirve para probar que NO se escribe en la base.
FORM_MOVIMIENTO = {
    'fecha': '2026-10-01', 'descripcion': 'Prueba de login cerrado',
    'persona': 'elias', 'moneda': 'ars', 'tipo': 'gasto',
    'monto': '100', 'categoria': 'Comida',
}

NO_CONFIGURADO = ('/login', {'error': ['no_configurado']})


def _cfg_falsa(**cambios):
    """
    Un `cargar_config` falso, hermetico: parte de DEFAULTS —no del config.json
    de la maquina— y pisa las claves que se pidan. Se parchea la funcion y no
    el archivo para no tocar el config.json real.
    """
    def falso(ruta=None):
        cfg = dict(config.DEFAULTS)
        cfg.update(cambios)
        return cfg
    return falso


class BaseAuth(unittest.TestCase):
    """Cada test: base temporal vacia, cliente nuevo y AVISO sin historial."""

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix='fondo-auth-')
        self._db_original = database.DB_PATH
        database.DB_PATH = os.path.join(self._dir, 'fondo.db')
        database.inicializar_db()
        self.client = app_module.app.test_client()
        # El AVISO tiene anti-spam por tiempo: sin esto, un test que corra
        # despues de otro dentro del mismo minuto no veria ningun AVISO.
        auth._aviso_cerrado['ultimo'] = None
        # Y sin esto cada test que cierra el login imprimiria su AVISO en la
        # consola (con `python -m unittest`, que no captura la salida). Los
        # tests que miran el log lo vuelven a parchear por su cuenta.
        parche = unittest.mock.patch.object(auth, 'log')
        parche.start()
        self.addCleanup(parche.stop)

    def tearDown(self):
        database.DB_PATH = self._db_original
        shutil.rmtree(self._dir, ignore_errors=True)

    # -- Atajos -------------------------------------------------------------

    def con_config(self, **cambios):
        """Context manager: la config que ve la app durante el bloque."""
        return unittest.mock.patch.object(config, 'cargar_config', _cfg_falsa(**cambios))

    def login(self, email=EMAIL_OK):
        """Deja una sesion valida en el cliente, como despues del OAuth."""
        with self.client.session_transaction() as sesion:
            sesion['user_email'] = email
            sesion['user_name'] = 'Elias'

    def destino(self, respuesta):
        """(path, query) del redirect. Compara sin depender de si la URL es absoluta."""
        self.assertEqual(respuesta.status_code, 302, respuesta.get_data(as_text=True)[:200])
        partes = urlsplit(respuesta.headers['Location'])
        return partes.path, parse_qs(partes.query)

    def cantidad_movimientos(self):
        conn = database.conectar()
        try:
            return conn.execute('SELECT COUNT(*) FROM movimientos').fetchone()[0]
        finally:
            conn.close()


# ── 1. Sin credenciales: CERRADO ─────────────────────────────────────────────

class TestSinCredencialesCierra(BaseAuth):

    def test_una_pagina_redirige_a_no_configurado(self):
        with self.con_config(**SIN_CREDENCIALES):
            r = self.client.get('/gastos')
        self.assertEqual(self.destino(r), NO_CONFIGURADO)

    def test_un_post_redirige_y_no_escribe_en_la_base(self):
        with self.con_config(**SIN_CREDENCIALES):
            r = self.client.post('/agregar', data=FORM_MOVIMIENTO)
        self.assertEqual(self.destino(r), NO_CONFIGURADO)
        self.assertEqual(self.cantidad_movimientos(), 0)

    def test_contracara_el_mismo_post_con_sesion_si_escribe(self):
        """
        La contracara del test de arriba. Sin esto, "0 filas" podria deberse a
        que el form esta mal armado y no a que la puerta esta cerrada.
        """
        with self.con_config(**CON_LOGIN):
            self.login()
            r = self.client.post('/agregar', data=FORM_MOVIMIENTO)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.cantidad_movimientos(), 1)

    def test_con_una_sola_de_las_dos_credenciales_tambien_cierra(self):
        for nombre, cambios in (
                ('solo el id', dict(CON_LOGIN, google_client_secret='')),
                ('solo el secret', dict(CON_LOGIN, google_client_id='')),
                ('id en null', dict(CON_LOGIN, google_client_id=None)),
        ):
            with self.subTest(nombre):
                with self.con_config(**cambios):
                    r = self.client.get('/gastos')
                self.assertEqual(self.destino(r), NO_CONFIGURADO)

    def test_ni_siquiera_una_sesion_valida_pasa_sin_credenciales(self):
        """
        Es a proposito: el chequeo de credenciales va ANTES de mirar la sesion.
        Una config que no se puede leer es un estado que no se puede verificar,
        y una cookie firmada de ayer no lo arregla.
        """
        with self.con_config(**SIN_CREDENCIALES):
            self.login()
            r = self.client.get('/gastos')
        self.assertEqual(self.destino(r), NO_CONFIGURADO)

    def test_el_login_no_redirige_a_si_mismo(self):
        """Si /login cayera en el redirect, el aviso seria un bucle infinito."""
        with self.con_config(**SIN_CREDENCIALES):
            r = self.client.get('/login?error=no_configurado')
        self.assertEqual(r.status_code, 200)

    def test_con_sesion_valida_el_login_muestra_el_aviso_y_no_manda_al_inicio(self):
        """
        Una cookie valida de ayer + config sin credenciales (o ilegible): /login
        tiene que MOSTRAR el aviso (200), no mandar a `/`. Si mandara a `/`, el
        middleware —que ve que faltan credenciales— lo devolveria a
        /login?error=no_configurado y asi sin fin.
        """
        with self.con_config(**SIN_CREDENCIALES):
            self.login()
            for url in ('/login', '/login?error=no_configurado'):
                with self.subTest(url):
                    r = self.client.get(url)
                    self.assertEqual(r.status_code, 200)
                    self.assertIn('Inicio de sesión no disponible',
                                  r.get_data(as_text=True))
            # Y la pagina protegida sigue cerrada.
            self.assertEqual(self.destino(self.client.get('/gastos')), NO_CONFIGURADO)

    def test_con_sesion_valida_y_sin_credenciales_no_hay_bucle_de_redirecciones(self):
        """
        El mismo caso de punta a punta, SIGUIENDO las redirecciones como lo hace
        el navegador: pedir una pagina protegida termina en el aviso, con un
        solo salto. El cliente de pruebas corta un bucle con una excepcion, y
        eso tambien hace fallar el test.
        """
        with self.con_config(**SIN_CREDENCIALES):
            self.login()
            for url in ('/', '/gastos'):
                with self.subTest(url):
                    try:
                        r = self.client.get(url, follow_redirects=True)
                    except RuntimeError as e:  # ClientRedirectError: bucle o demasiados saltos
                        self.fail(f'bucle de redirecciones al pedir {url}: {e}')
                    self.assertEqual(r.status_code, 200)
                    self.assertEqual(len(r.history), 1)
                    self.assertIn('Inicio de sesión no disponible',
                                  r.get_data(as_text=True))

    def test_contracara_con_credenciales_y_sesion_el_login_manda_al_inicio(self):
        """El chequeo de credenciales no puede romper el atajo de siempre."""
        with self.con_config(**CON_LOGIN):
            self.login()
            r = self.client.get('/login')
        self.assertEqual(self.destino(r), ('/', {}))


# ── 2. Config ilegible: tambien CERRADO ──────────────────────────────────────

class TestConfigIlegibleCierra(BaseAuth):

    def test_cargar_config_devolviendo_defaults_cierra(self):
        """
        Lo que `cargar_config` hace con un archivo ilegible es devolver
        DEFAULTS. DEFAULTS no trae credenciales: tiene que quedar cerrado.
        """
        with unittest.mock.patch.object(
                config, 'cargar_config', lambda ruta=None: dict(config.DEFAULTS)):
            r = self.client.get('/gastos')
        self.assertEqual(self.destino(r), NO_CONFIGURADO)

    def test_un_config_que_se_rompe_en_caliente_cierra_y_arreglarlo_reabre(self):
        """
        El incidente, de punta a punta y con el `cargar_config` REAL leyendo un
        archivo de verdad: la app anda, el archivo queda a medias (como lo veria
        un lector con la escritura vieja), la app se cierra; se arregla el
        archivo y vuelve a andar. Es la secuencia que antes terminaba con
        GET /gastos sin sesion dando 200.
        """
        ruta = os.path.join(self._dir, 'config.json')
        bueno = {'google_client_id': 'id-de-prueba',
                 'google_client_secret': 'secreto-de-prueba',
                 'secret_key': 'clave', 'auth_disabled': False,
                 'ngrok_enabled': False}

        def escribir(contenido):
            with open(ruta, 'wb') as f:
                f.write(contenido)

        real = config.cargar_config

        def contra_el_archivo(_ruta=None):
            return real(ruta)

        escribir(json.dumps(bueno).encode('utf-8'))
        with unittest.mock.patch.object(config, 'cargar_config', contra_el_archivo), \
                unittest.mock.patch.object(config, '_LECTURA_ESPERA', 0), \
                unittest.mock.patch.object(config, 'log'):
            # 1. Andando: sin sesion al login, con sesion adentro.
            self.assertEqual(self.destino(self.client.get('/gastos')), ('/login', {}))
            self.login()
            self.assertEqual(self.client.get('/gastos').status_code, 200)

            # 2. El archivo queda a medias: cerrado, incluso con la sesion.
            escribir(b'{"google_client_id": "id-de-prueba", "google_client_sec')
            self.assertEqual(self.destino(self.client.get('/gastos')), NO_CONFIGURADO)
            r = self.client.post('/agregar', data=FORM_MOVIMIENTO)
            self.assertEqual(self.destino(r), NO_CONFIGURADO)
            self.assertEqual(self.cantidad_movimientos(), 0)
            # Y el aviso se ve: con la cookie valida de antes, /login NO manda
            # a `/` (seria un bucle con el middleware), muestra el aviso.
            r = self.client.get('/login')
            self.assertEqual(r.status_code, 200)
            self.assertIn('Inicio de sesión no disponible', r.get_data(as_text=True))

            # 3. Se arregla el archivo: vuelve a andar sin reiniciar nada.
            escribir(json.dumps(bueno).encode('utf-8'))
            self.assertEqual(self.client.get('/gastos').status_code, 200)


# ── 3. Las rutas que hablan con Google ───────────────────────────────────────

class TestRutasDeGoogle(BaseAuth):

    def test_auth_google_sin_credenciales_no_habla_con_google(self):
        falso = unittest.mock.MagicMock()
        with self.con_config(**SIN_CREDENCIALES), \
                unittest.mock.patch.object(auth, 'oauth', falso):
            r = self.client.get('/auth/google?remember=1')
        self.assertEqual(self.destino(r), NO_CONFIGURADO)
        self.assertNotIn('google.com', r.headers['Location'])
        falso.google.authorize_redirect.assert_not_called()

    def test_contracara_con_credenciales_auth_google_si_va_a_google(self):
        falso = unittest.mock.MagicMock()
        falso.google.authorize_redirect.return_value = redirect(
            'https://accounts.google.com/o/oauth2/v2/auth?client_id=x')
        with self.con_config(**CON_LOGIN), \
                unittest.mock.patch.object(auth, 'oauth', falso):
            r = self.client.get('/auth/google?remember=1')
        self.assertEqual(r.status_code, 302)
        self.assertIn('accounts.google.com', r.headers['Location'])
        falso.google.authorize_redirect.assert_called_once()

    def test_callback_sin_credenciales_no_crea_sesion_ni_habla_con_google(self):
        """Ni siquiera con un `code` de Google en la URL."""
        falso = unittest.mock.MagicMock()
        falso.google.authorize_access_token.return_value = {
            'userinfo': {'email': EMAIL_OK, 'name': 'Elias', 'picture': ''}}
        with self.con_config(**SIN_CREDENCIALES), \
                unittest.mock.patch.object(auth, 'oauth', falso):
            r = self.client.get('/auth/callback?code=abc&state=xyz')
        self.assertEqual(self.destino(r), NO_CONFIGURADO)
        falso.google.authorize_access_token.assert_not_called()
        with self.client.session_transaction() as sesion:
            self.assertNotIn('user_email', sesion)

    def test_contracara_con_credenciales_el_callback_crea_la_sesion(self):
        falso = unittest.mock.MagicMock()
        # `email_verified` es lo que Google manda siempre para estas cuentas, y
        # desde el endurecimiento de auth.py el callback lo EXIGE (ver
        # tests/test_auth_endurecido.py): una respuesta sin el dato no es un
        # login valido.
        falso.google.authorize_access_token.return_value = {
            'userinfo': {'email': EMAIL_OK, 'email_verified': True,
                         'name': 'Elias', 'picture': ''}}
        with self.con_config(**CON_LOGIN), \
                unittest.mock.patch.object(auth, 'oauth', falso):
            r = self.client.get('/auth/callback?code=abc&state=xyz')
        self.assertEqual(r.status_code, 302)
        with self.client.session_transaction() as sesion:
            self.assertEqual(sesion.get('user_email'), EMAIL_OK)

    def test_el_callback_sigue_rechazando_emails_fuera_de_la_lista(self):
        falso = unittest.mock.MagicMock()
        falso.google.authorize_access_token.return_value = {
            'userinfo': {'email': 'intruso@example.com', 'name': 'X', 'picture': ''}}
        with self.con_config(**CON_LOGIN), \
                unittest.mock.patch.object(auth, 'oauth', falso), \
                unittest.mock.patch.object(auth, 'log'):
            r = self.client.get('/auth/callback?code=abc&state=xyz')
        self.assertEqual(self.destino(r), ('/login', {'error': ['no_permitido']}))
        with self.client.session_transaction() as sesion:
            self.assertNotIn('user_email', sesion)


# ── 4. /login ────────────────────────────────────────────────────────────────

class TestPaginaLogin(BaseAuth):

    def test_muestra_el_aviso_aunque_no_venga_en_la_url(self):
        with self.con_config(**SIN_CREDENCIALES):
            r = self.client.get('/login')
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn('Inicio de sesión no disponible', html)
        self.assertIn('config.json', html)
        self.assertIn('reiniciar', html)

    def test_el_aviso_ya_no_manda_a_settings(self):
        """
        El texto viejo decia "configurar las credenciales en Settings", que es
        falso: Settings no maneja las credenciales de Google. Mandar a alguien
        a buscar una pantalla que no existe es peor que no avisar.
        """
        with self.con_config(**SIN_CREDENCIALES):
            html = self.client.get('/login?error=no_configurado').get_data(as_text=True)
        self.assertNotIn('Settings', html)

    def test_sin_credenciales_el_aviso_gana_sobre_otros_errores(self):
        with self.con_config(**SIN_CREDENCIALES):
            html = self.client.get('/login?error=no_permitido').get_data(as_text=True)
        self.assertIn('Inicio de sesión no disponible', html)
        self.assertNotIn('Acceso denegado', html)

    def test_contracara_con_credenciales_no_muestra_el_aviso(self):
        with self.con_config(**CON_LOGIN):
            html = self.client.get('/login').get_data(as_text=True)
        self.assertNotIn('Inicio de sesión no disponible', html)
        self.assertIn('Iniciar sesión con Google', html)

    def test_con_credenciales_siguen_andando_los_otros_errores(self):
        with self.con_config(**CON_LOGIN):
            html = self.client.get('/login?error=no_permitido').get_data(as_text=True)
        self.assertIn('Acceso denegado', html)


# ── 5. Con credenciales: todo como siempre ───────────────────────────────────

class TestConCredencialesTodoIgual(BaseAuth):

    def test_sin_sesion_va_al_login_de_siempre(self):
        """Al login a secas: sin `?error=`, que seria el aviso de config rota."""
        with self.con_config(**CON_LOGIN):
            r = self.client.get('/gastos')
        self.assertEqual(self.destino(r), ('/login', {}))

    def test_con_sesion_valida_entra(self):
        with self.con_config(**CON_LOGIN):
            self.login()
            r = self.client.get('/gastos')
        self.assertEqual(r.status_code, 200)

    def test_un_email_que_ya_no_esta_en_la_lista_no_entra_y_pierde_la_sesion(self):
        with self.con_config(**CON_LOGIN):
            self.login('intruso@example.com')
            r = self.client.get('/gastos')
        self.assertEqual(self.destino(r), ('/login', {}))
        with self.client.session_transaction() as sesion:
            self.assertNotIn('user_email', sesion)


# ── 6. El bypass DEV: sin cambios ────────────────────────────────────────────

class TestBypassDev(BaseAuth):
    """
    El bypass no se toca en esta fase, y estos tests congelan que sigue igual.
    Son los que cuidan que el arreglo no rompa DEV ni, sobre todo, que PROD
    (con ngrok) lo herede por accidente.
    """

    def test_sigue_entrando_sin_credenciales(self):
        """auth_disabled + localhost + ngrok apagado: como el entorno DEV de hoy."""
        with self.con_config(**dict(SIN_CREDENCIALES, auth_disabled=True)):
            r = self.client.get('/gastos')
        self.assertEqual(r.status_code, 200)

    def test_con_ngrok_prendido_no_aplica(self):
        for nombre, base in (('sin credenciales', SIN_CREDENCIALES),
                             ('con credenciales', CON_LOGIN)):
            with self.subTest(nombre):
                with self.con_config(**dict(base, auth_disabled=True, ngrok_enabled=True)):
                    r = self.client.get('/gastos')
                self.assertEqual(r.status_code, 302)
                self.assertEqual(urlsplit(r.headers['Location']).path, '/login')

    def test_desde_otra_ip_no_aplica(self):
        with self.con_config(**dict(SIN_CREDENCIALES, auth_disabled=True)):
            r = self.client.get('/gastos', environ_overrides={'REMOTE_ADDR': '203.0.113.7'})
        self.assertEqual(self.destino(r), NO_CONFIGURADO)

    def test_solo_el_booleano_true_lo_prende(self):
        """Mismo criterio que `sw_enabled`: un "true" entre comillas es un string
        no vacio y NO puede abrir la app."""
        for valor in ('true', 'True', 'yes', 1, '1'):
            with self.subTest(valor=valor):
                with self.con_config(**dict(SIN_CREDENCIALES, auth_disabled=valor)):
                    r = self.client.get('/gastos')
                self.assertEqual(self.destino(r), NO_CONFIGURADO)


# ── 7. Lo publico sigue publico ──────────────────────────────────────────────

class TestRutasPublicas(BaseAuth):

    def test_siguen_publicas_con_y_sin_credenciales(self):
        """
        El navegador pide el manifest y el service worker ANTES de tener sesion
        (y /sw.js en cada navegacion): si cayeran en el redirect recibirian el
        HTML del login donde esperan JSON o JavaScript.
        """
        for nombre, cfg in (('sin credenciales', SIN_CREDENCIALES),
                            ('con credenciales', CON_LOGIN)):
            for url in ('/manifest.json', '/sw.js', '/static/style.css', '/login'):
                with self.subTest(f'{nombre} {url}'):
                    with self.con_config(**cfg):
                        r = self.client.get(url)
                    estado = r.status_code
                    r.close()  # /static/ responde con un archivo abierto
                    self.assertEqual(estado, 200)


# ── 8. El AVISO en el log ────────────────────────────────────────────────────

class TestAvisoDelLoginCerrado(BaseAuth):

    def _avisos(self, log):
        return [c[0][0] for c in log.call_args_list if 'CERRADO' in c[0][0]]

    def test_sale_una_vez_por_minuto_y_no_una_por_request(self):
        with self.con_config(**SIN_CREDENCIALES), \
                unittest.mock.patch.object(auth, 'log') as log:
            for _ in range(15):
                self.client.get('/gastos')
        avisos = self._avisos(log)
        self.assertEqual(len(avisos), 1)
        self.assertTrue(avisos[0].startswith('AVISO:'))

        # Pasado el minuto, vuelve a avisar.
        auth._aviso_cerrado['ultimo'] -= auth._AVISO_CERRADO_CADA + 1
        with self.con_config(**SIN_CREDENCIALES), \
                unittest.mock.patch.object(auth, 'log') as log:
            self.client.get('/gastos')
        self.assertEqual(len(self._avisos(log)), 1)

    def test_no_dice_nada_del_request_ni_de_las_credenciales(self):
        """
        Ni la ruta pedida (la escribe quien pide: no va a una linea de log) ni
        el valor de ninguna credencial, aunque falte solo una de las dos.
        """
        with self.con_config(**dict(CON_LOGIN, google_client_secret='')), \
                unittest.mock.patch.object(auth, 'log') as log:
            self.client.get('/ruta-que-escribio-un-curioso')
        avisos = self._avisos(log)
        self.assertEqual(len(avisos), 1)
        self.assertNotIn('curioso', avisos[0])
        self.assertNotIn('id-de-prueba', avisos[0])

    def test_con_credenciales_no_avisa_nada(self):
        with self.con_config(**CON_LOGIN), \
                unittest.mock.patch.object(auth, 'log') as log:
            self.client.get('/gastos')
        self.assertEqual(self._avisos(log), [])


# ── 9. init_auth: arranque ───────────────────────────────────────────────────

class TestInitAuth(unittest.TestCase):
    """
    `init_auth` corre al importar app.py. Cada test usa una app Flask
    descartable y un OAuth descartable: `oauth` es global del modulo y
    `init_app` lo re-inicializa, asi que se le pasa uno propio para no tocar el
    de la app real.
    """

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix='fondo-initauth-')
        self.ruta = os.path.join(self._dir, 'config.json')
        for parche in (
            unittest.mock.patch.object(auth, 'oauth', OAuth()),
            unittest.mock.patch.object(config, '_LECTURA_ESPERA', 0),
            unittest.mock.patch.object(config, 'log'),
            unittest.mock.patch.object(auth, 'log'),
        ):
            parche.start()
            self.addCleanup(parche.stop)

    def tearDown(self):
        shutil.rmtree(self._dir, ignore_errors=True)

    def _escribir(self, contenido):
        with open(self.ruta, 'wb') as f:
            f.write(contenido)

    def _bytes(self):
        with open(self.ruta, 'rb') as f:
            return f.read()

    def test_config_ilegible_corta_el_arranque_con_un_mensaje_claro(self):
        """
        Si el config no se puede leer, `cargar_config` devuelve DEFAULTS (sin
        secret_key) y `init_auth` iria a "generar una nueva". Inventar una clave
        sobre un archivo que ya tiene la suya —y las credenciales— es justo lo
        que no se puede hacer: se corta con un mensaje claro y NO se escribe.
        """
        crudo = b'{"google_client_id": "id-canario", "google_client_secret": "secr'
        self._escribir(crudo)
        app = Flask(__name__)
        with self.assertRaises(config.ConfigIlegible) as ctx:
            auth.init_auth(app, self.ruta)
        self.assertIn('config.json ilegible: arreglarlo antes de arrancar',
                      str(ctx.exception))
        self.assertEqual(self._bytes(), crudo)
        self.assertEqual(os.listdir(self._dir), ['config.json'])
        self.assertIsNone(app.secret_key)

    def test_sin_secret_key_la_genera_y_conserva_todo_lo_demas(self):
        self._escribir(json.dumps({
            'google_client_id': 'id-canario',
            'google_client_secret': 'secreto-canario',
            'ngrok_authtoken': 'token-canario',
        }).encode('utf-8'))
        app = Flask(__name__)
        auth.init_auth(app, self.ruta)

        with open(self.ruta, encoding='utf-8') as f:
            crudo = json.load(f)
        self.assertEqual(len(crudo['secret_key']), 64)
        self.assertEqual(app.secret_key, crudo['secret_key'])
        self.assertEqual(crudo['google_client_id'], 'id-canario')
        self.assertEqual(crudo['google_client_secret'], 'secreto-canario')
        self.assertEqual(crudo['ngrok_authtoken'], 'token-canario')

    def test_con_secret_key_no_toca_el_archivo(self):
        contenido = json.dumps({'secret_key': 'clave-canario',
                                'google_client_id': 'id',
                                'google_client_secret': 's'}).encode('utf-8')
        self._escribir(contenido)
        app = Flask(__name__)
        auth.init_auth(app, self.ruta)
        self.assertEqual(app.secret_key, 'clave-canario')
        self.assertEqual(self._bytes(), contenido)

    def test_guarda_la_ruta_para_las_rutas_del_blueprint(self):
        self._escribir(json.dumps({'secret_key': 'k'}).encode('utf-8'))
        app = Flask(__name__)
        auth.init_auth(app, self.ruta)
        self.assertEqual(app.config['AUTH_CONFIG_FILE'], self.ruta)


if __name__ == '__main__':
    unittest.main()
