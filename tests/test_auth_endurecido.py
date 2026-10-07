# =============================================================================
# ARCHIVO: tests/test_auth_endurecido.py
# =============================================================================
#
# Tests de cuatro refuerzos de auth.py (Fase 2 del endurecimiento de seguridad).
#
# POR QUE EXISTE ESTE ARCHIVO
#
#   Los cuatro cierran puertas que nadie ve abiertas: la app anda perfecto sin
#   ellos. Por eso cada test que dice "se rechaza" tiene su contracara que dice
#   "pasa" (un test de "no deja pasar" que pasaria igual con el control apagado
#   no prueba nada), y las cosas que NO deben frenarse tienen su propio test.
#
#   1. LOS POST SOLO DESDE LA PROPIA APP. La unica proteccion contra CSRF era la
#      cookie SameSite=Lax, que depende del navegador y que ni siquiera mira el
#      puerto. Ahora un POST/PUT/PATCH/DELETE con un Origin (o, sin Origin, un
#      Referer) que no sea el sitio pedido se rechaza con 403, antes del login y
#      tambien en las rutas publicas (/logout acepta POST). El esquema NO se
#      compara: detras de ngrok Flask ve http y el navegador manda https.
#
#   2. BYPASS DEV: EL CUARTO CERROJO. auth_disabled + remote_addr local + ngrok
#      apagado no miraban A QUE SITIO apuntaba el navegador. Con "DNS rebinding"
#      una pagina ajena abierta en la PC de desarrollo podia LEER la app DEV, que
#      no pide login. Ahora ademas el Host tiene que ser localhost, 127.0.0.1 o
#      ::1. OJO: el chequeo de origen de (1) no lo frena, porque en ese ataque
#      Origin y Host coinciden (mismo origen para el navegador): lo frena (2).
#
#   3. EMAIL CONFIRMADO POR GOOGLE. El callback exige `email_verified` verdadero,
#      ademas de la lista blanca. Falso o ausente = mismo rechazo que un email
#      no permitido.
#
#   4. COOKIE DE SESION SECURE CUANDO LA APP SALE POR NGROK. Con la misma
#      condicion que usa run_flask para levantar el tunel. En DEV y en red local
#      (http) queda apagada: si no, el login dejaria de andar.
#
# HERMETICOS: no dependen del config.json de la maquina (el de DEV tiene
# auth_disabled=True y no tiene credenciales de Google). Cada test fija la config
# con un `cargar_config` falso que parte de DEFAULTS, usa una base SQLite
# temporal y entra con una sesion explicita cuando hace falta.
#
# COMO CORRER:
#   Desde la raiz del proyecto:
#       python -m unittest tests.test_auth_endurecido -v
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

from flask import Flask, session  # noqa: E402

import app as app_module  # noqa: E402
import auth  # noqa: E402
import config  # noqa: E402
import database  # noqa: E402


EMAIL_OK = 'mussaelias123@gmail.com'

# Config "con el login puesto de verdad": credenciales, sin bypass, sin ngrok.
CON_LOGIN = dict(google_client_id='id-de-prueba',
                 google_client_secret='secreto-de-prueba',
                 auth_disabled=False, ngrok_enabled=False)
# Lo mismo pero sin credenciales: el estado del config.json de DEV.
SIN_CREDENCIALES = dict(CON_LOGIN, google_client_id='', google_client_secret='')

# Un movimiento valido. Si el POST pasa, inserta una fila: por eso sirve para
# probar que un POST rechazado NO escribe en la base.
FORM_MOVIMIENTO = {
    'fecha': '2026-10-01', 'descripcion': 'Prueba de auth endurecido',
    'persona': 'elias', 'moneda': 'ars', 'tipo': 'gasto',
    'monto': '100', 'categoria': 'Comida',
}

PROPIO = 'http://localhost'         # el sitio por defecto del cliente de pruebas
AJENO = 'https://evil.example'


def _cfg_falsa(**cambios):
    """
    Un `cargar_config` falso, hermetico: parte de DEFAULTS —no del config.json
    de la maquina— y pisa las claves que se pidan.
    """
    def falso(ruta=None):
        cfg = dict(config.DEFAULTS)
        cfg.update(cambios)
        return cfg
    return falso


class BaseEndurecido(unittest.TestCase):
    """
    Cada test: base temporal vacia, cliente nuevo, AVISOs sin historial, el log
    capturado en `self.log` y la config `CON_LOGIN` (un test que necesita otra la
    pisa con `with self.con_config(...)`).
    """

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix='fondo-auth-end-')
        self._db_original = database.DB_PATH
        database.DB_PATH = os.path.join(self._dir, 'fondo.db')
        database.inicializar_db()
        self.client = app_module.app.test_client()

        # Los AVISOs tienen anti-spam por tiempo: sin esto, un test que corra
        # despues de otro dentro del mismo minuto no veria ningun AVISO.
        for estado in (auth._aviso_origen, auth._aviso_bypass, auth._aviso_cerrado):
            estado['ultimo'] = None

        parche_log = unittest.mock.patch.object(auth, 'log')
        self.log = parche_log.start()
        self.addCleanup(parche_log.stop)

        parche_cfg = unittest.mock.patch.object(
            config, 'cargar_config', _cfg_falsa(**CON_LOGIN))
        parche_cfg.start()
        self.addCleanup(parche_cfg.stop)

    def tearDown(self):
        database.DB_PATH = self._db_original
        shutil.rmtree(self._dir, ignore_errors=True)

    # -- Atajos -------------------------------------------------------------

    def con_config(self, **cambios):
        """Context manager: la config que ve la app durante el bloque."""
        return unittest.mock.patch.object(config, 'cargar_config', _cfg_falsa(**cambios))

    def login(self, email=EMAIL_OK, **kwargs):
        """Deja una sesion valida en el cliente, como despues del OAuth.
        `kwargs` (p. ej. base_url) van al `session_transaction`: la cookie queda
        atada al sitio con el que se la pide."""
        with self.client.session_transaction(**kwargs) as sesion:
            sesion['user_email'] = email
            sesion['user_name'] = 'Elias'

    def hay_sesion(self):
        with self.client.session_transaction() as sesion:
            return 'user_email' in sesion

    def destino(self, respuesta):
        """(path, query) del redirect."""
        self.assertEqual(respuesta.status_code, 302, respuesta.get_data(as_text=True)[:200])
        partes = urlsplit(respuesta.headers['Location'])
        return partes.path, parse_qs(partes.query)

    def cantidad_movimientos(self):
        conn = database.conectar()
        try:
            return conn.execute('SELECT COUNT(*) FROM movimientos').fetchone()[0]
        finally:
            conn.close()

    def avisos(self, contiene=''):
        """Los AVISO: que salieron por el log de auth.py y mencionan `contiene`."""
        mensajes = [c[0][0] for c in self.log.call_args_list]
        return [m for m in mensajes if m.startswith('AVISO:') and contiene in m]


# ── 1. Los POST solo desde la propia app ─────────────────────────────────────

class TestPostsSoloDesdeLaPropiaApp(BaseEndurecido):

    def intentar(self, **kwargs):
        """Un POST de alta. Devuelve (respuesta, filas que se agregaron)."""
        antes = self.cantidad_movimientos()
        r = self.client.post('/agregar', data=FORM_MOVIMIENTO, **kwargs)
        return r, self.cantidad_movimientos() - antes

    # -- Lo que se rechaza ----------------------------------------------------

    def test_origin_ajeno_es_403_y_no_escribe_en_la_base(self):
        self.login()
        r, nuevas = self.intentar(headers={'Origin': AJENO})
        self.assertEqual((r.status_code, nuevas), (403, 0))

    def test_contracara_origin_propio_pasa_y_escribe(self):
        """Sin esto, "0 filas" podria deberse a que el form esta mal armado."""
        self.login()
        r, nuevas = self.intentar(headers={'Origin': PROPIO})
        self.assertEqual((r.status_code, nuevas), (302, 1))

    def test_sin_origin_ni_referer_pasa(self):
        """Navegadores viejos, el cliente de pruebas, un curl: ahi queda sola la
        cookie SameSite."""
        self.login()
        r, nuevas = self.intentar()
        self.assertEqual((r.status_code, nuevas), (302, 1))

    def test_referer_ajeno_es_403(self):
        self.login()
        r, nuevas = self.intentar(headers={'Referer': AJENO + '/pagina?x=1'})
        self.assertEqual((r.status_code, nuevas), (403, 0))

    def test_contracara_referer_propio_pasa(self):
        self.login()
        r, nuevas = self.intentar(headers={'Referer': PROPIO + '/gastos?mes=10'})
        self.assertEqual((r.status_code, nuevas), (302, 1))

    def test_origin_null_es_403(self):
        """Iframes con sandbox, redirecciones entre sitios, file://."""
        self.login()
        for valor in ('null', 'NULL', ' null '):
            with self.subTest(origin=valor):
                r, nuevas = self.intentar(headers={'Origin': valor})
                self.assertEqual((r.status_code, nuevas), (403, 0))

    def test_un_origin_que_no_es_un_sitio_es_403(self):
        """Presente pero ilegible NO es lo mismo que ausente: ausente pasa."""
        self.login()
        for valor in ('', 'basura', 'localhost', '//localhost', 'file://', 'http://[::1'):
            with self.subTest(origin=valor):
                r, nuevas = self.intentar(headers={'Origin': valor})
                self.assertEqual((r.status_code, nuevas), (403, 0))

    def test_un_referer_que_no_es_un_sitio_es_403(self):
        self.login()
        for valor in ('', 'basura', 'localhost/gastos'):
            with self.subTest(referer=valor):
                r, nuevas = self.intentar(headers={'Referer': valor})
                self.assertEqual((r.status_code, nuevas), (403, 0))

    def test_un_origin_con_usuario_arroba_es_ajeno(self):
        """`https://a@b` tiene dos nombres y no hay que decidir cual "vale": no
        es igual al Host en ningun caso."""
        self.login()
        for valor in ('https://localhost@evil.example', 'https://evil.example@localhost'):
            with self.subTest(origin=valor):
                r, nuevas = self.intentar(headers={'Origin': valor})
                self.assertEqual((r.status_code, nuevas), (403, 0))

    def test_si_viene_origin_manda_el_y_el_referer_ni_se_mira(self):
        self.login()
        r, nuevas = self.intentar(headers={'Origin': PROPIO, 'Referer': AJENO + '/x'})
        self.assertEqual((r.status_code, nuevas), (302, 1))
        r, nuevas = self.intentar(headers={'Origin': AJENO, 'Referer': PROPIO + '/gastos'})
        self.assertEqual((r.status_code, nuevas), (403, 0))

    # -- Que se compara -------------------------------------------------------

    def test_el_puerto_se_compara(self):
        """Para SameSite, `localhost:8080` y `localhost:5050` son el mismo SITIO:
        cualquier otra cosa que corra en la PC pasaba ese filtro."""
        self.login()
        base = 'http://localhost:5050'
        casos = (
            ('http://localhost:5050', True),
            ('http://localhost:8080', False),
            ('http://localhost', False),
            ('http://127.0.0.1:5050', False),
            ('http://localhost:5050.evil.example', False),
        )
        for origin, pasa in casos:
            with self.subTest(origin=origin):
                r, nuevas = self.intentar(base_url=base, headers={'Origin': origin})
                self.assertEqual((r.status_code, nuevas), (302, 1) if pasa else (403, 0))

    def test_el_esquema_no_se_compara_detras_de_ngrok(self):
        """Flask ve http (el tunel termina el HTTPS) y el navegador manda
        `Origin: https://...`. Comparar el esquema rechazaria todos los POST de
        produccion."""
        host = 'miller-unventured.ngrok-free.dev'
        base = f'http://{host}'
        self.login(base_url=base)
        for origin in (f'https://{host}', f'http://{host}'):
            with self.subTest(origin=origin):
                r, nuevas = self.intentar(base_url=base, headers={'Origin': origin})
                self.assertEqual((r.status_code, nuevas), (302, 1))
        # El tunel de al lado no es esta app.
        r, nuevas = self.intentar(base_url=base,
                                  headers={'Origin': 'https://otro.ngrok-free.dev'})
        self.assertEqual((r.status_code, nuevas), (403, 0))

    def test_mayusculas_no_importan(self):
        self.login()
        for valor in ('HTTP://LOCALHOST', 'http://LocalHost'):
            with self.subTest(origin=valor):
                r, nuevas = self.intentar(headers={'Origin': valor})
                self.assertEqual((r.status_code, nuevas), (302, 1))

    def test_origin_ipv6_propio_pasa(self):
        """Un sitio con host IPv6 (`[::1]:5050`) tiene corchetes en Host y en Origin."""
        base = 'http://[::1]:5050'
        # La cookie de sesion no viaja a un host con corchetes en el cliente de
        # pruebas: se entra por el bypass DEV, que es justo lo que se usa en DEV.
        with self.con_config(**dict(SIN_CREDENCIALES, auth_disabled=True)):
            r, nuevas = self.intentar(base_url=base, headers={'Origin': base},
                                      environ_overrides={'REMOTE_ADDR': '::1'})
            self.assertEqual((r.status_code, nuevas), (302, 1))
            r, nuevas = self.intentar(base_url=base, headers={'Origin': AJENO},
                                      environ_overrides={'REMOTE_ADDR': '::1'})
            self.assertEqual((r.status_code, nuevas), (403, 0))

    def test_en_dev_con_bypass_un_sitio_ajeno_no_puede_escribir(self):
        """
        El caso donde el chequeo es la UNICA barrera: el bypass DEV autentica por
        IP, no por cookie, asi que SameSite no protege nada. Un sitio cualquiera
        podria mandar un POST ciego a `localhost:5050` desde el navegador del
        desarrollador y la app DEV lo atenderia como si fuera el.
        """
        base = 'http://localhost:5050'
        with self.con_config(**dict(SIN_CREDENCIALES, auth_disabled=True)):
            r, nuevas = self.intentar(base_url=base, headers={'Origin': AJENO})
            self.assertEqual((r.status_code, nuevas), (403, 0))
            # Contracara: la propia app DEV, por el mismo camino, escribe.
            r, nuevas = self.intentar(base_url=base, headers={'Origin': base})
            self.assertEqual((r.status_code, nuevas), (302, 1))

    # -- Lo que NO se frena ---------------------------------------------------

    def test_un_get_nunca_se_frena(self):
        self.login()
        hostiles = {'Origin': AJENO, 'Referer': AJENO + '/x'}
        for metodo in ('get', 'head', 'options'):
            with self.subTest(metodo):
                r = getattr(self.client, metodo)('/gastos', headers=hostiles)
                self.assertEqual(r.status_code, 200)
                r.close()

    # -- Metodos y rutas que alcanza -------------------------------------------

    def test_put_patch_y_delete_tambien(self):
        self.login()
        for metodo in ('put', 'patch', 'delete'):
            with self.subTest(metodo):
                ajeno = getattr(self.client, metodo)('/agregar', headers={'Origin': AJENO})
                self.assertEqual(ajeno.status_code, 403)
                # Contracara: /agregar solo acepta POST, asi que un 405 prueba
                # que el chequeo de origen dejo pasar el pedido propio.
                propio = getattr(self.client, metodo)('/agregar', headers={'Origin': PROPIO})
                self.assertEqual(propio.status_code, 405)

    def test_va_antes_del_login(self):
        """Un POST ajeno se frena sin mirar el login: 403, no un redirect."""
        r = self.client.post('/agregar', data=FORM_MOVIMIENTO, headers={'Origin': AJENO})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.cantidad_movimientos(), 0)
        # Contracara: el chequeo de origen no reemplaza al login.
        r = self.client.post('/agregar', data=FORM_MOVIMIENTO, headers={'Origin': PROPIO})
        self.assertEqual(self.destino(r), ('/login', {}))
        self.assertEqual(self.cantidad_movimientos(), 0)

    def test_esta_registrado_antes_que_require_login(self):
        """Flask corre los before_request en el orden en que se registraron. Si
        alguien invierte el orden, el bypass DEV (que fabrica una sesion) y el
        login pasarian a ir primero."""
        nombres = [f.__name__ for f in app_module.app.before_request_funcs[None]]
        self.assertIn('_exigir_origen_propio', nombres)
        self.assertIn('require_login', nombres)
        self.assertLess(nombres.index('_exigir_origen_propio'), nombres.index('require_login'))

    def test_logout_con_origin_ajeno_es_403_y_no_cierra_la_sesion(self):
        self.login()
        r = self.client.post('/logout', headers={'Origin': AJENO})
        self.assertEqual(r.status_code, 403)
        self.assertTrue(self.hay_sesion())
        # Contracara: el logout de siempre sigue andando.
        r = self.client.post('/logout', headers={'Origin': PROPIO})
        self.assertEqual(self.destino(r), ('/login', {}))
        self.assertFalse(self.hay_sesion())

    def test_las_rutas_publicas_tambien(self):
        """Estan en `rutas_publicas` (no piden login), pero el chequeo de origen
        va antes y las alcanza igual. `/logout`, la publica que SI acepta POST,
        tiene su test aparte."""
        for url in ('/login', '/auth/google', '/auth/callback',
                    '/manifest.json', '/sw.js', '/static/style.css'):
            with self.subTest(url):
                ajeno = self.client.post(url, headers={'Origin': AJENO})
                self.assertEqual(ajeno.status_code, 403)
                # Contracara: el POST propio NO es un 403 (sigue al flujo de
                # siempre). Son rutas de solo-GET: el router no las reconoce para
                # POST, `request.endpoint` queda en None y require_login, que
                # ya era asi, manda al login.
                propio = self.client.post(url, headers={'Origin': PROPIO})
                self.assertEqual(self.destino(propio)[0], '/login')

    # -- La respuesta -----------------------------------------------------------

    def test_ajax_recibe_json_y_lo_demas_texto_plano(self):
        self.login()
        r = self.client.post('/agregar', data=FORM_MOVIMIENTO,
                             headers={'Origin': AJENO, 'X-Requested-With': 'XMLHttpRequest'})
        self.assertEqual(r.status_code, 403)
        cuerpo = r.get_json()
        self.assertIs(cuerpo['ok'], False)
        self.assertTrue(cuerpo['error'])

        r = self.client.post('/agregar', data=FORM_MOVIMIENTO, headers={'Origin': AJENO})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.mimetype, 'text/plain')
        texto = r.get_data(as_text=True)
        self.assertTrue(texto)
        self.assertNotIn('<', texto)


# ── 1b. El AVISO de los pedidos rechazados ───────────────────────────────────

class TestAvisoDeLosPedidosRechazados(BaseEndurecido):

    def rechazar(self, veces=1, **kwargs):
        for _ in range(veces):
            self.client.post('/agregar', data=FORM_MOVIMIENTO,
                             headers={'Origin': AJENO}, **kwargs)

    def test_sale_una_vez_por_minuto_y_no_una_por_request(self):
        self.rechazar(veces=10)
        avisos = self.avisos('rechazado')
        self.assertEqual(len(avisos), 1)
        self.assertTrue(avisos[0].startswith('AVISO:'))

        # Pasado el minuto, vuelve a avisar.
        auth._aviso_origen['ultimo'] -= auth._AVISO_ORIGEN_CADA + 1
        self.rechazar()
        self.assertEqual(len(self.avisos('rechazado')), 2)

    def test_dice_que_paso(self):
        self.rechazar()
        (aviso,) = self.avisos('rechazado')
        for esperado in ('POST', "'agregar'", "Origin ajeno 'evil.example'", "'localhost'"):
            self.assertIn(esperado, aviso)

    def test_un_pedido_que_pasa_no_avisa(self):
        self.login()
        self.client.post('/agregar', data=FORM_MOVIMIENTO, headers={'Origin': PROPIO})
        self.assertEqual(self.avisos(), [])

    def test_no_dice_la_ruta_pedida(self):
        """La ruta la escribe quien pide: no va a una linea de log."""
        self.client.post('/ruta-que-escribio-un-curioso', headers={'Origin': AJENO})
        (aviso,) = self.avisos('rechazado')
        self.assertNotIn('curioso', aviso)

    def test_no_vuelca_texto_ajeno_sin_sanear(self):
        """
        El peor caso: un Origin y un Host con saltos de linea, secuencias de
        escape y 500 caracteres. Tiene que salir UNA linea, corta y sin
        caracteres de control (si no, quien pide fabrica lineas de log falsas).
        """
        hostil_origin = 'https://evil\x1b.example\nAVISO: linea falsa ' + 'a' * 500
        hostil_host = 'loc\x1b<b>.example'
        self.client.post('/agregar', data=FORM_MOVIMIENTO,
                         environ_overrides={'HTTP_ORIGIN': hostil_origin,
                                            'HTTP_HOST': hostil_host})
        (aviso,) = self.avisos('rechazado')
        for prohibido in ('\n', '\r', '\x1b', '<', '>'):
            self.assertNotIn(prohibido, aviso)
        self.assertLess(len(aviso), 400)
        self.assertNotIn('a' * 100, aviso)
        # Y se entiende quien era, saneado.
        self.assertIn("Origin ajeno 'evil?.exampleaviso:?linea?falsa", aviso)

    def test_un_origin_ilegible_no_se_vuelca(self):
        """Si ni se puede leer como sitio, no hay nada que mostrar: solo el motivo."""
        self.client.post('/agregar', data=FORM_MOVIMIENTO,
                         environ_overrides={'HTTP_ORIGIN': 'http://[sin-cerrar\x1b'})
        (aviso,) = self.avisos('rechazado')
        self.assertIn('Origin ilegible', aviso)
        self.assertNotIn('sin-cerrar', aviso)
        self.assertNotIn('\x1b', aviso)


# ── 2. Bypass DEV: el cuarto cerrojo ─────────────────────────────────────────

# Sitios que NO son esta PC. Todos llegan a la app (los que Werkzeug no deja ni
# armar en el cliente de pruebas, como `::1` pelado, se prueban directo contra
# `_host_es_local` mas abajo).
HOSTS_AJENOS = (
    'evil.example', 'evil.example:5050', 'fondo.local:5050',
    # Nombres que "contienen" localhost / 127.0.0.1 sin serlo.
    'localhost.evil.example', '127.0.0.1.evil.example', 'localhostx', 'xlocalhost',
    # Con usuario@: el nombre real es el de la derecha.
    'evil.example@localhost', 'localhost@evil.example', 'localhost:5050@evil.example',
    'evil.example\\@localhost',
    # Otras direcciones de esta misma PC o de la red: no son las tres de la lista.
    '127.0.0.2:5050', '0.0.0.0:5050', '192.168.1.10:5050',
    '[::2]:5050', '[::ffff:127.0.0.1]:5050',
    # Puertos rotos y vacio.
    'localhost:', '',
)
HOSTS_LOCALES = (
    'localhost', 'localhost:5050', 'LOCALHOST:5050',
    '127.0.0.1', '127.0.0.1:5050',
    '[::1]', '[::1]:5050',
)


class TestBypassDevCuartoCerrojo(BaseEndurecido):

    BYPASS_SIN_CRED = dict(SIN_CREDENCIALES, auth_disabled=True)   # el config.json de DEV
    BYPASS_CON_CRED = dict(CON_LOGIN, auth_disabled=True)

    def test_con_el_nombre_de_esta_pc_entra(self):
        """La contracara de todo lo de abajo: el DEV de siempre sigue andando."""
        for nombre, cfg in (('sin credenciales', self.BYPASS_SIN_CRED),
                            ('con credenciales', self.BYPASS_CON_CRED)):
            for host in HOSTS_LOCALES:
                with self.subTest(f'{nombre} {host}'):
                    with self.con_config(**cfg):
                        r = self.client.get('/gastos', headers={'Host': host})
                    self.assertEqual(r.status_code, 200)

    def test_con_otro_nombre_no_entra(self):
        for nombre, cfg in (('sin credenciales', self.BYPASS_SIN_CRED),
                            ('con credenciales', self.BYPASS_CON_CRED)):
            for host in HOSTS_AJENOS:
                with self.subTest(f'{nombre} {host!r}'):
                    with self.con_config(**cfg):
                        r = self.client.get('/gastos', headers={'Host': host})
                    self.assertEqual(r.status_code, 302)
                    self.assertEqual(urlsplit(r.headers['Location']).path, '/login')
                    # Ni una cookie de sesion: no se fabrico la sesion `dev@local`.
                    self.assertNotIn('gastos_session', r.headers.get('Set-Cookie', ''))

    def test_el_ipv6_literal_entra_desde_el_loopback_ipv6(self):
        with self.con_config(**self.BYPASS_SIN_CRED):
            r = self.client.get('/gastos', base_url='http://[::1]:5050',
                                environ_overrides={'REMOTE_ADDR': '::1'})
        self.assertEqual(r.status_code, 200)

    def test_el_dns_rebinding_de_punta_a_punta(self):
        """
        El ataque entero: la pagina ajena es `evil.example:5050`, que resuelve a
        127.0.0.1. Para el navegador es el MISMO origen que se pide, asi que
        Origin y Host coinciden y el chequeo de origen lo deja pasar. El pedido
        viene de 127.0.0.1, auth_disabled esta prendido y ngrok apagado. Lo unico
        que lo delata es el nombre.
        """
        sitio = 'http://evil.example:5050'
        with self.con_config(**self.BYPASS_SIN_CRED):
            r = self.client.post('/agregar', data=FORM_MOVIMIENTO,
                                 base_url=sitio, headers={'Origin': sitio})
            self.assertEqual(r.status_code, 302)
            self.assertEqual(urlsplit(r.headers['Location']).path, '/login')
            self.assertEqual(self.cantidad_movimientos(), 0)

            # Contracara: el mismo POST desde el sitio propio, por el bypass, escribe.
            propio = 'http://localhost:5050'
            r = self.client.post('/agregar', data=FORM_MOVIMIENTO,
                                 base_url=propio, headers={'Origin': propio})
            self.assertEqual(r.status_code, 302)
            self.assertEqual(self.cantidad_movimientos(), 1)

    def test_los_otros_tres_cerrojos_siguen_cerrando_aunque_el_nombre_sea_local(self):
        """El cuarto cerrojo se SUMA a los otros; no reemplaza a ninguno."""
        casos = (
            ('auth_disabled apagado', dict(SIN_CREDENCIALES, auth_disabled=False), {}),
            ('auth_disabled como texto', dict(SIN_CREDENCIALES, auth_disabled='true'), {}),
            ('ngrok prendido', dict(self.BYPASS_SIN_CRED, ngrok_enabled=True), {}),
            ('otra IP', self.BYPASS_SIN_CRED, {'REMOTE_ADDR': '203.0.113.7'}),
        )
        for nombre, cfg, entorno in casos:
            with self.subTest(nombre):
                with self.con_config(**cfg):
                    r = self.client.get('/gastos', headers={'Host': 'localhost:5050'},
                                        environ_overrides=entorno)
                self.assertEqual(r.status_code, 302)

    # -- El AVISO ---------------------------------------------------------------

    def test_avisa_una_vez_por_minuto_cuando_el_nombre_es_lo_unico_que_lo_frena(self):
        with self.con_config(**self.BYPASS_SIN_CRED):
            for _ in range(8):
                self.client.get('/gastos', headers={'Host': 'evil.example:5050'})
        avisos = self.avisos('bypass DEV NO aplicado')
        self.assertEqual(len(avisos), 1)
        self.assertIn('evil.example:5050', avisos[0])

        auth._aviso_bypass['ultimo'] -= auth._AVISO_BYPASS_CADA + 1
        with self.con_config(**self.BYPASS_SIN_CRED):
            self.client.get('/gastos', headers={'Host': 'evil.example:5050'})
        self.assertEqual(len(self.avisos('bypass DEV NO aplicado')), 2)

    def test_no_avisa_si_el_bypass_no_estaba_en_juego_o_si_entra(self):
        """Con ngrok prendido el bypass ni se plantea; con un nombre local entra.
        En ninguno de los dos hay nada que avisar por el nombre."""
        with self.con_config(**dict(self.BYPASS_SIN_CRED, ngrok_enabled=True)):
            self.client.get('/gastos', headers={'Host': 'evil.example'})
        with self.con_config(**self.BYPASS_SIN_CRED):
            self.client.get('/gastos', headers={'Host': 'localhost:5050'})
        self.assertEqual(self.avisos('bypass DEV NO aplicado'), [])

    def test_el_aviso_no_vuelca_el_host_sin_sanear(self):
        with self.con_config(**self.BYPASS_SIN_CRED):
            self.client.get('/gastos', headers={'Host': 'evil\x1b.example<b>'})
        (aviso,) = self.avisos('bypass DEV NO aplicado')
        for prohibido in ('\n', '\r', '\x1b', '<', '>'):
            self.assertNotIn(prohibido, aviso)


class TestHostEsLocal(unittest.TestCase):
    """La lista cerrada, sin pasar por HTTP: incluye lo que el cliente de pruebas
    no deja ni armar (`::1` pelado, puertos que no son numeros)."""

    def test_los_tres_nombres_de_esta_pc(self):
        for host in ('localhost', 'localhost:5050', 'LocalHost:80', '127.0.0.1',
                     '127.0.0.1:5050', '[::1]', '[::1]:5050', '::1'):
            with self.subTest(host=host):
                self.assertTrue(auth._host_es_local(host))

    def test_todo_lo_demas_es_ajeno(self):
        for host in (None, '', ' ', 'evil.example', 'localhost.evil.example',
                     '127.0.0.1.evil.example', 'evil.example@localhost',
                     'localhost:5050@evil.example', 'localhost@evil.example',
                     'localhostx', 'xlocalhost', 'localhost:', 'localhost:abc',
                     'localhost:123456', 'localhost:5050:80', '127.0.0.2', '0.0.0.0',
                     '[::2]', '[::1', '::1]', '::1:5050', '[::1]x', '[::ffff:127.0.0.1]',
                     # Nada se recorta: ni saltos de linea ni espacios (tampoco
                     # los Unicode, que str.strip() si se llevaria).
                     ' localhost', 'localhost ', 'localhost\n', 'local\nhost',
                     'localhost\xa0', 'localhost\x00.evil.example'):
            with self.subTest(host=host):
                self.assertFalse(auth._host_es_local(host))


# ── 3. Email confirmado por Google ───────────────────────────────────────────

class TestEmailVerificadoPorGoogle(BaseEndurecido):

    def callback(self, userinfo, por_userinfo=False):
        """Un login que vuelve de Google con esa info del usuario. Con
        `por_userinfo` la info no viene en el token sino del endpoint userinfo
        (el camino de respaldo del callback)."""
        falso = unittest.mock.MagicMock()
        if por_userinfo:
            falso.google.authorize_access_token.return_value = {}
            falso.google.userinfo.return_value = userinfo
        else:
            falso.google.authorize_access_token.return_value = {'userinfo': userinfo}
        with unittest.mock.patch.object(auth, 'oauth', falso):
            return self.client.get('/auth/callback?code=abc&state=xyz')

    def info(self, **extra):
        datos = {'email': EMAIL_OK, 'name': 'Elias', 'picture': ''}
        datos.update(extra)
        return datos

    def test_verificado_entra(self):
        """Las dos formas en que Google lo dice: el booleano y el texto."""
        for valor in (True, 'true'):
            with self.subTest(email_verified=valor):
                self.client = app_module.app.test_client()
                r = self.callback(self.info(email_verified=valor))
                self.assertEqual(self.destino(r), ('/', {}))
                with self.client.session_transaction() as sesion:
                    self.assertEqual(sesion.get('user_email'), EMAIL_OK)

    def test_falso_o_ausente_no_crea_sesion(self):
        casos = (
            ('falso', dict(email_verified=False)),
            ('"false"', dict(email_verified='false')),
            ('null', dict(email_verified=None)),
            ('vacio', dict(email_verified='')),
            ('0', dict(email_verified=0)),
            ('1: ni siquiera un 1 vale', dict(email_verified=1)),
            ('"yes"', dict(email_verified='yes')),
            ('ausente', {}),
        )
        for nombre, extra in casos:
            with self.subTest(nombre):
                self.client = app_module.app.test_client()
                r = self.callback(self.info(**extra))
                self.assertEqual(self.destino(r), ('/login', {'error': ['no_permitido']}))
                self.assertFalse(self.hay_sesion())

    def test_el_rechazo_deja_el_motivo_en_el_log(self):
        self.callback(self.info(email_verified=False))
        (aviso,) = self.avisos('ACCESO DENEGADO')
        self.assertIn(EMAIL_OK, aviso)
        self.assertIn('email_verified', aviso)

    def test_tambien_vale_para_la_info_que_viene_del_endpoint_userinfo(self):
        """Si el token no trae `userinfo`, el callback lo pide aparte: ese camino
        no puede ser una puerta lateral."""
        r = self.callback(self.info(email_verified=False), por_userinfo=True)
        self.assertEqual(self.destino(r), ('/login', {'error': ['no_permitido']}))
        self.assertFalse(self.hay_sesion())

        r = self.callback(self.info(email_verified=True), por_userinfo=True)
        self.assertEqual(self.destino(r), ('/', {}))
        self.assertTrue(self.hay_sesion())

    def test_un_email_fuera_de_la_lista_sigue_rechazado_aunque_este_verificado(self):
        r = self.callback(self.info(email='intruso@example.com', email_verified=True))
        self.assertEqual(self.destino(r), ('/login', {'error': ['no_permitido']}))
        self.assertFalse(self.hay_sesion())
        self.assertEqual(len(self.avisos('intruso@example.com')), 1)

    def test_un_email_nulo_no_rompe_el_callback(self):
        """`user_info.get('email', '')` devolvia None con la clave en null y el
        `.lower()` posterior reventaba en un 500."""
        r = self.callback(self.info(email=None, email_verified=True))
        self.assertEqual(self.destino(r), ('/login', {'error': ['no_permitido']}))


# ── 4. Cookie de sesion Secure cuando la app sale por ngrok ──────────────────

class TestCookieDeSesionSecure(unittest.TestCase):

    # Produccion: ya configurada, con el tunel prendido y sin DEV en el nombre.
    PROD = dict(first_run=False, ngrok_enabled=True, app_name='Gastos Casa')

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix='fondo-auth-cookie-')
        self.addCleanup(shutil.rmtree, self._dir, ignore_errors=True)

    # -- La funcion que decide -------------------------------------------------

    def test_decide_con_la_misma_condicion_que_run_flask(self):
        casos = (
            ('produccion: sale por ngrok', self.PROD, True),
            ('DEV con ngrok prendido: run_flask no levanta el tunel',
             dict(self.PROD, app_name='Gastos Casa DEV'), False),
            ('red local: ngrok apagado', dict(self.PROD, ngrok_enabled=False), False),
            ('primer arranque: run_flask no levanta el tunel',
             dict(self.PROD, first_run=True), False),
            ('sin claves', {}, False),
            ('los DEFAULTS de la config', dict(config.DEFAULTS), False),
        )
        for nombre, cfg, esperado in casos:
            with self.subTest(nombre):
                self.assertIs(auth._cookie_secure_para(cfg), esperado)

    # -- Que init_auth la aplique -----------------------------------------------

    def app_con(self, **cfg):
        """Una app DESCARTABLE con `init_auth` corrido sobre un config.json de
        verdad: asi se prueba el cableado sin reiniciar la app real. Se parchea
        `oauth` para no re-registrar el cliente de Google en el global."""
        ruta = os.path.join(self._dir, 'config.json')
        datos = {'secret_key': 'clave-de-prueba', 'google_client_id': 'id-de-prueba',
                 'google_client_secret': 'secreto-de-prueba'}
        datos.update(cfg)
        with open(ruta, 'w', encoding='utf-8') as f:
            json.dump(datos, f)

        app = Flask('app-descartable')
        with unittest.mock.patch.object(auth, 'oauth', unittest.mock.MagicMock()), \
                unittest.mock.patch.object(auth, 'log') as log:
            auth.init_auth(app, ruta)

        # Una ruta publica (el endpoint `manifest` esta en `rutas_publicas`) que
        # toca la sesion, para ver la cookie que sale de verdad.
        @app.route('/manifest.json', endpoint='manifest')
        def publica():
            session['visto'] = True
            return 'ok'

        return app, log

    def cookie_de_sesion(self, app):
        r = app.test_client().get('/manifest.json')
        cookies = [c for c in r.headers.getlist('Set-Cookie') if c.startswith('gastos_session=')]
        self.assertEqual(len(cookies), 1, r.headers.getlist('Set-Cookie'))
        return cookies[0]

    def test_init_auth_la_prende_cuando_la_app_sale_por_ngrok(self):
        app, log = self.app_con(**self.PROD)
        self.assertIs(app.config['SESSION_COOKIE_SECURE'], True)
        self.assertIn('; Secure', self.cookie_de_sesion(app))
        self.assertTrue([c for c in log.call_args_list if 'Secure' in c[0][0]])

    def test_init_auth_la_deja_apagada_en_dev_y_en_red_local(self):
        for nombre, cfg in (
                ('DEV', dict(self.PROD, app_name='Gastos Casa DEV')),
                ('red local', dict(self.PROD, ngrok_enabled=False)),
                ('primer arranque', dict(self.PROD, first_run=True)),
        ):
            with self.subTest(nombre):
                app, log = self.app_con(**cfg)
                self.assertIs(app.config['SESSION_COOKIE_SECURE'], False)
                self.assertNotIn('; Secure', self.cookie_de_sesion(app))
                self.assertFalse([c for c in log.call_args_list if 'Secure' in c[0][0]])

    def test_el_resto_de_la_cookie_no_cambio(self):
        app, _ = self.app_con(**self.PROD)
        self.assertEqual(app.config['SESSION_COOKIE_NAME'], 'gastos_session')
        self.assertIs(app.config['SESSION_COOKIE_HTTPONLY'], True)
        self.assertEqual(app.config['SESSION_COOKIE_SAMESITE'], 'Lax')
        cookie = self.cookie_de_sesion(app)
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Lax', cookie)


if __name__ == '__main__':
    unittest.main()
