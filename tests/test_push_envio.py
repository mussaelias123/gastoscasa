# =============================================================================
# ARCHIVO: tests/test_push_envio.py
# =============================================================================
#
# Tests del ENVIO de un push: la ruta POST /api/push/prueba, el payload que
# viaja al telefono, y el logout que ahora apaga SOLO el navegador que se va.
#
# El alta, la baja y la tabla estan en tests/test_push_suscripciones.py; los
# handlers del service worker, en tests/test_sw.py (clase TestPushEnElSW).
#
# POR QUE EXISTE ESTE ARCHIVO
#
#   1. EL PAYLOAD NO LLEVA PLATA. Un push se lee en la PANTALLA BLOQUEADA:
#      sin desbloquear el telefono, sin sesion, y lo ve cualquiera que este
#      cerca. Un aviso que diga "entraron $50.000" publica el saldo de la casa
#      en la mesa del cafe. La regla se cumple con una lista cerrada de tres
#      claves (`_PUSH_PAYLOAD_CLAVES`), y se congela aca porque es de esas
#      cosas que nadie nota que se rompieron: el aviso llega igual, mas
#      "completo", y recien se entiende el problema el dia que alguien lee la
#      pantalla de otro.
#
#   2. QUE FALTE LA CONFIG NO ES UN ERROR DE PROGRAMA. Sin las claves VAPID la
#      ruta tiene que decir QUE FALTA, no tirar un 500. La diferencia es entre
#      pegar tres lineas en config.json y salir a buscar un bug que no existe.
#
#   3. EL BOTON ES UN DIAGNOSTICO, Y TIENE QUE ANDAR CUANDO TODO LO DEMAS
#      ESTA APAGADO. Por eso NO mira `push_enabled`: si lo mirara, para probar
#      si el canal funciona habria que prender antes los avisos automaticos —
#      encender lo que todavia no se sabe si anda.
#
#   4. EL LOGOUT YA NO SE LLEVA TODO PUESTO. Antes borraba TODAS las filas del
#      email: salir en la notebook apagaba los avisos del telefono, y un link
#      cross-site a /logout (GET y publico, y `SameSite=Lax` no tapa la
#      navegacion) se llevaba las suscripciones de todos los dispositivos.
#      Ahora, si el pedido trae el endpoint del navegador que se va, se borra
#      esa fila sola.
#
# COMO CORRER:
#   Desde la raiz del proyecto:
#       python -m unittest tests.test_push_envio -v
#
# =============================================================================

import os
import re
import sys
import json
import shutil
import tempfile
import unittest
import unittest.mock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import app as app_module  # noqa: E402
import config  # noqa: E402
import database  # noqa: E402
import pywebpush  # noqa: E402


ENDPOINT = 'https://fcm.googleapis.com/fcm/send/cJfG8hQ:APA91bH-ejemplo-de-endpoint'
ENDPOINT2 = 'https://web.push.apple.com/abcdefg-el-iphone-de-mari'
P256DH = 'B' + 'a' * 86
AUTH = 'c' * 22

ELIAS = 'mussaelias123@gmail.com'
MARI = 'mossinomariana@gmail.com'

# Un par VAPID CUALQUIERA con el formato correcto. No se usa para firmar nada
# (webpush esta mockeado en todos los tests menos donde se dice): solo tiene
# que pasar el chequeo de "hay claves cargadas".
VAPID_PUB = 'B' + 'q' * 86
VAPID_SEC = 'z' * 43
VAPID_MAIL = 'mailto:nadie@ejemplo.com'


def _cfg_con(**cambios):
    """La config de verdad con las claves que se pidan pisadas. Se parchea la
    funcion y no el archivo, para no tocar el config.json de la maquina."""
    real = config.cargar_config

    def falso(ruta=None):
        cfg = real(ruta)
        cfg.update(cambios)
        return cfg

    return falso


def _cfg_con_claves(**extra):
    return _cfg_con(push_vapid_publica=VAPID_PUB,
                    push_vapid_secreta=VAPID_SEC,
                    push_contacto_mailto=VAPID_MAIL,
                    **extra)


def _cfg_sin_claves(**extra):
    return _cfg_con(push_vapid_publica='',
                    push_vapid_secreta='',
                    push_contacto_mailto='',
                    **extra)


class BaseEnvio(unittest.TestCase):
    """Base temporal vacia + cliente, igual que test_push_suscripciones."""

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix='fondo-push-envio-')
        self._db_original = database.DB_PATH
        database.DB_PATH = os.path.join(self._dir, 'fondo.db')
        database.inicializar_db()
        self.client = app_module.app.test_client()

    def tearDown(self):
        database.DB_PATH = self._db_original
        shutil.rmtree(self._dir, ignore_errors=True)

    # -- Atajos -------------------------------------------------------------

    def login(self, email=ELIAS, nombre='Elias'):
        with self.client.session_transaction() as sesion:
            sesion['user_email'] = email
            sesion['user_name'] = nombre

    def suscribir(self, endpoint=ENDPOINT, email=ELIAS, persona='elias'):
        database.guardar_suscripcion_push(endpoint, P256DH, AUTH, persona, email, 'UA')

    def prueba(self):
        return self.client.post('/api/push/prueba',
                                headers={'X-Requested-With': 'XMLHttpRequest'})

    def filas(self):
        return [dict(f) for f in database.obtener_suscripciones_push()]


# ── 1. El payload: QUE viaja al telefono ─────────────────────────────────────

class TestPayloadSinPlata(unittest.TestCase):

    def test_solo_tres_claves(self):
        """
        Lista CERRADA. Una cuarta clave no se agrega de paso: se agrega con
        esta lista delante, pensando si eso se puede leer en una pantalla
        bloqueada.
        """
        self.assertEqual(app_module._PUSH_PAYLOAD_CLAVES,
                         ('titulo', 'cuerpo', 'url'))

    def test_el_payload_armado_no_tiene_nada_mas(self):
        p = app_module._push_payload('T', 'C', '/gastos')
        self.assertEqual(sorted(p.keys()), sorted(app_module._PUSH_PAYLOAD_CLAVES))

    def test_la_url_es_relativa(self):
        """
        LA URL DEL PAYLOAD ES RELATIVA Y LA RESUELVE EL SERVICE WORKER contra
        su propio origen. El servidor no sabe su direccion publica:
        `ngrok_domain` es un hostname pelado, sin esquema, y en DEV esta vacio.
        Una absoluta armada aca queda pegada al dominio del dia que se
        escribio.
        """
        p = app_module._push_payload('T', 'C', '/lactancia')
        self.assertTrue(p['url'].startswith('/'))
        self.assertNotIn(':', p['url'])

    def test_una_url_absoluta_no_pasa(self):
        for mala in ('https://ejemplo.com/x', 'http://192.168.1.1/admin',
                     'lactancia', 'javascript:alert(1)'):
            with self.subTest(url=mala):
                with self.assertRaises(ValueError):
                    app_module._push_payload('T', 'C', mala)

    def test_el_aviso_de_prueba_no_dice_plata(self):
        """
        El texto que manda la ruta, mirado de verdad: ni simbolos de moneda, ni
        digitos (un saldo siempre tiene alguno), ni las palabras del dominio
        que no pueden salir del login.
        """
        fuente = _fuente('app.py')
        bloque = _bloque_funcion(fuente, 'def api_push_prueba')
        m = re.search(r"_push_payload\((.*?)\)", bloque, re.S)
        self.assertIsNotNone(m, 'la ruta de prueba tiene que armar el payload')
        texto = m.group(1)
        for prohibido in ('$', 'USD', 'saldo', 'monto', 'banco'):
            self.assertNotIn(prohibido.lower(), texto.lower())
        self.assertFalse(re.search(r'\d', texto), texto)


# ── 2. La ruta de prueba ─────────────────────────────────────────────────────

class TestRutaPrueba(BaseEnvio):

    def test_esta_protegida(self):
        """Hace sonar un telefono: sin sesion no se puede."""
        with unittest.mock.patch.object(
                config, 'cargar_config',
                _cfg_con_claves(auth_disabled=False, ngrok_enabled=False,
                                google_client_id='id', google_client_secret='s')):
            r = self.prueba()
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login', r.headers['Location'])

    def test_no_esta_en_rutas_publicas(self):
        self.assertNotIn('api_push_prueba', _fuente('auth.py'))

    def test_sin_claves_vapid_avisa_y_no_es_un_500(self):
        """
        EL TEST DE LA CONFIG A MEDIO HACER. Sin claves, la ruta tiene que
        decir que faltan — no reventar. Un 500 manda a buscar un bug adentro
        del codigo cuando lo que falta es pegar tres lineas en config.json.
        """
        self.login()
        self.suscribir()
        with unittest.mock.patch.object(config, 'cargar_config', _cfg_sin_claves()):
            r = self.prueba()
        self.assertNotEqual(r.status_code, 500)
        self.assertEqual(r.status_code, 503)
        datos = r.get_json()
        self.assertFalse(datos['ok'])
        self.assertIn('VAPID', datos['error'])

    def test_sin_suscripciones_lo_dice(self):
        self.login()
        with unittest.mock.patch.object(config, 'cargar_config', _cfg_con_claves()):
            r = self.prueba()
        self.assertEqual(r.status_code, 409)
        self.assertFalse(r.get_json()['ok'])

    def test_el_camino_feliz(self):
        self.login()
        self.suscribir()
        with unittest.mock.patch.object(config, 'cargar_config', _cfg_con_claves()), \
             unittest.mock.patch.object(pywebpush, 'webpush') as mandar:
            r = self.prueba()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()['ok'])
        self.assertEqual(r.get_json()['enviados'], 1)
        self.assertEqual(mandar.call_count, 1)

    def test_lo_que_se_le_pasa_a_pywebpush(self):
        """
        Tres cosas en un solo lugar: el JSON que viaja, el TIMEOUT (sin el
        cual `pywebpush` se lo pasa a `requests` como None, o sea SIN limite:
        un FCM que no contesta dejaba el worker de Flask colgado para siempre)
        y que la clave que firma es la SECRETA.
        """
        self.login()
        self.suscribir()
        with unittest.mock.patch.object(config, 'cargar_config', _cfg_con_claves()), \
             unittest.mock.patch.object(pywebpush, 'webpush') as mandar:
            self.prueba()

        kwargs = mandar.call_args.kwargs
        self.assertEqual(kwargs['vapid_private_key'], VAPID_SEC)
        self.assertEqual(kwargs['vapid_claims'], {'sub': VAPID_MAIL})
        self.assertIsInstance(kwargs['timeout'], (int, float))
        self.assertGreater(kwargs['timeout'], 0)
        self.assertLessEqual(kwargs['timeout'], 30)

        payload = json.loads(kwargs['data'])
        self.assertEqual(sorted(payload.keys()),
                         sorted(app_module._PUSH_PAYLOAD_CLAVES))
        self.assertTrue(payload['url'].startswith('/'))
        # La suscripcion va tal cual salio de la base, con las claves
        # anidadas como las quiere pywebpush.
        self.assertEqual(kwargs['subscription_info']['endpoint'], ENDPOINT)
        self.assertEqual(kwargs['subscription_info']['keys'],
                         {'p256dh': P256DH, 'auth': AUTH})

    def test_no_le_suena_el_telefono_al_otro(self):
        """
        Se manda SOLO a las suscripciones del email de la sesion. Ni siquiera
        con sesion valida se le puede hacer sonar el telefono al otro.
        """
        self.login(ELIAS)
        self.suscribir(ENDPOINT, ELIAS, 'elias')
        self.suscribir(ENDPOINT2, MARI, 'mari')
        with unittest.mock.patch.object(config, 'cargar_config', _cfg_con_claves()), \
             unittest.mock.patch.object(pywebpush, 'webpush') as mandar:
            r = self.prueba()
        self.assertEqual(r.get_json()['enviados'], 1)
        destinos = [c.kwargs['subscription_info']['endpoint']
                    for c in mandar.call_args_list]
        self.assertEqual(destinos, [ENDPOINT])

    def test_no_mira_push_enabled(self):
        """
        DECISION, no olvido: el boton de prueba es el DIAGNOSTICO del canal, no
        un aviso automatico. Si respetara el flag, para saber si el canal anda
        habria que prender antes los avisos automaticos — justo al reves.
        """
        self.login()
        self.suscribir()
        with unittest.mock.patch.object(
                config, 'cargar_config', _cfg_con_claves(push_enabled=False)), \
             unittest.mock.patch.object(pywebpush, 'webpush') as mandar:
            r = self.prueba()
        self.assertTrue(r.get_json()['ok'])
        self.assertEqual(mandar.call_count, 1)


# ── 3. Suscripciones muertas ─────────────────────────────────────────────────

class TestSuscripcionMuerta(BaseEnvio):

    def _fallar(self, estado):
        respuesta = unittest.mock.Mock()
        respuesta.status_code = estado
        respuesta.text = 'chau'
        return pywebpush.WebPushException('muerta', response=respuesta)

    def test_un_410_borra_la_fila(self):
        """
        404/410 = el servicio de push diciendo que ese buzon no existe mas (la
        app se desinstalo, se limpiaron los datos). Esa fila no va a funcionar
        NUNCA MAS: si no se borra, cada envio futuro la reintenta, paga el
        timeout y ensucia el log para siempre.
        """
        self.login()
        self.suscribir()
        with unittest.mock.patch.object(config, 'cargar_config', _cfg_con_claves()), \
             unittest.mock.patch.object(pywebpush, 'webpush',
                                        side_effect=self._fallar(410)):
            r = self.prueba()
        self.assertEqual(self.filas(), [])
        self.assertEqual(r.get_json()['borradas'], 1)
        self.assertFalse(r.get_json()['ok'])

    def test_otro_error_no_borra_nada(self):
        """Un 500 del servicio o la red caida pueden andar la proxima."""
        self.login()
        self.suscribir()
        with unittest.mock.patch.object(config, 'cargar_config', _cfg_con_claves()), \
             unittest.mock.patch.object(pywebpush, 'webpush',
                                        side_effect=self._fallar(500)):
            r = self.prueba()
        self.assertEqual(len(self.filas()), 1)
        self.assertFalse(r.get_json()['ok'])
        self.assertNotEqual(r.status_code, 500)

    def test_un_telefono_roto_no_deja_sin_aviso_al_otro(self):
        """Son dispositivos distintos: el de Mari no se queda sin aviso porque
        el de Elias se rompio."""
        self.login()
        self.suscribir(ENDPOINT, ELIAS, 'elias')
        self.suscribir(ENDPOINT2, ELIAS, 'elias')

        def a_veces(**kwargs):
            if kwargs['subscription_info']['endpoint'] == ENDPOINT:
                raise self._fallar(500)
            return None

        with unittest.mock.patch.object(config, 'cargar_config', _cfg_con_claves()), \
             unittest.mock.patch.object(pywebpush, 'webpush', side_effect=a_veces):
            r = self.prueba()
        self.assertTrue(r.get_json()['ok'])
        self.assertEqual(r.get_json()['enviados'], 1)

    def test_el_endpoint_no_va_al_log(self):
        """
        El log se lee, se copia y se manda por chat. El endpoint es el buzon de
        un telefono: alcanza con el estado del error.
        """
        self.login()
        self.suscribir()
        with unittest.mock.patch.object(config, 'cargar_config', _cfg_con_claves()), \
             unittest.mock.patch.object(pywebpush, 'webpush',
                                        side_effect=self._fallar(500)), \
             unittest.mock.patch.object(app_module, 'log') as loguear:
            self.prueba()
        for llamada in loguear.call_args_list:
            self.assertNotIn(ENDPOINT, str(llamada))

    def test_el_endpoint_tampoco_va_al_log_cuando_se_cae_la_red(self):
        """
        POR QUE ESTE TEST APARTE: el de arriba solo cubre la rama de
        WebPushException, y el agujero estaba en la otra. `requests` mete la
        URL COMPLETA en el texto de sus errores de red — "Max retries exceeded
        with url: /fcm/send/<endpoint>" —, asi que un `{e}` pelado en el except
        generico filtraba el buzon justo en el caso mas comun: el DNS que se
        cayo un segundo.

        Pasaba desapercibido porque depende del TIPO de falla: con un
        ReadTimeout el endpoint no aparece, con un ConnectionError si.
        """
        import requests

        self.login()
        self.suscribir()
        explota = requests.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='fcm.googleapis.com', port=443): "
            "Max retries exceeded with url: " + ENDPOINT)

        with unittest.mock.patch.object(config, 'cargar_config', _cfg_con_claves()), \
             unittest.mock.patch.object(pywebpush, 'webpush', side_effect=explota), \
             unittest.mock.patch.object(app_module, 'log') as loguear:
            self.prueba()

        self.assertTrue(loguear.call_args_list, 'no se logueo nada: el test no prueba nada')
        for llamada in loguear.call_args_list:
            self.assertNotIn(ENDPOINT, str(llamada))


# ── 4. El logout apaga solo el navegador que se va ───────────────────────────

class TestLogoutConEndpoint(BaseEnvio):

    def test_con_endpoint_borra_solo_esa_fila(self):
        """
        LA DEUDA QUE CIERRA ESTA ETAPA. Antes se borraban TODAS las filas del
        email: salir en la notebook apagaba los avisos del telefono.
        """
        self.login(ELIAS)
        self.suscribir(ENDPOINT, ELIAS, 'elias')
        self.suscribir(ENDPOINT2, ELIAS, 'elias')
        r = self.client.post('/logout', data={'endpoint': ENDPOINT})
        self.assertEqual(r.status_code, 302)
        quedan = [f['endpoint'] for f in self.filas()]
        self.assertEqual(quedan, [ENDPOINT2])

    def test_sin_endpoint_sigue_el_comportamiento_de_siempre(self):
        """Sin JavaScript, sin push o con un link pegado a mano: se borra todo
        lo de esa cuenta, como antes. Salir nunca depende de JavaScript."""
        self.login(ELIAS)
        self.suscribir(ENDPOINT, ELIAS, 'elias')
        self.suscribir(ENDPOINT2, ELIAS, 'elias')
        r = self.client.get('/logout')
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.filas(), [])

    def test_el_endpoint_tambien_se_acota_al_email(self):
        """No alcanza con conocer el endpoint del otro."""
        self.login(ELIAS)
        self.suscribir(ENDPOINT2, MARI, 'mari')
        self.client.post('/logout', data={'endpoint': ENDPOINT2})
        self.assertEqual(len(self.filas()), 1)

    def test_sin_sesion_no_borra_nada(self):
        """
        /logout es publico. Sin el `email and` de auth.py, un pedido sin sesion
        con el endpoint de otro le borraba la fila: `borrar_suscripcion_push`
        con email vacio borra por endpoint SOLO, sin dueño.
        """
        self.suscribir(ENDPOINT, ELIAS, 'elias')
        with unittest.mock.patch.object(
                config, 'cargar_config',
                _cfg_con_claves(auth_disabled=False, ngrok_enabled=False,
                                google_client_id='id', google_client_secret='s')):
            self.client.post('/logout', data={'endpoint': ENDPOINT})
        self.assertEqual(len(self.filas()), 1)

    def test_un_endpoint_kilometrico_no_llega_al_driver(self):
        self.login(ELIAS)
        self.suscribir(ENDPOINT, ELIAS, 'elias')
        r = self.client.post('/logout', data={'endpoint': 'x' * 5000})
        self.assertEqual(r.status_code, 302)
        # Cayo al camino de siempre (borrar todo lo del email), no exploto.
        self.assertEqual(self.filas(), [])

    def test_el_get_sigue_andando(self):
        """El <a href="/logout"> tiene que funcionar sin JavaScript."""
        self.login(ELIAS)
        r = self.client.get('/logout')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login', r.headers['Location'])


# ── 5. El front: window.Push y la tarjeta de Settings ────────────────────────

def _fuente(relativo):
    with open(os.path.join(ROOT_DIR, relativo), encoding='utf-8') as f:
        return f.read()


def _sin_comentarios(js):
    """
    El JavaScript SIN comentarios (`/* */` y `//`). Todo lo que se cuenta o se
    busca como CODIGO se busca contra esto: este proyecto comenta largo y
    nombra justo las cosas que estos tests buscan (`requestPermission`,
    `standalone === false`), asi que sin esta pasada media clase pasaria por
    leer la documentacion en vez del codigo.
    """
    js = re.sub(r'/\*.*?\*/', '', js, flags=re.S)
    # Y los `{# #}` de Jinja, para los templates.
    js = re.sub(r'\{#.*?#\}', '', js, flags=re.S)
    limpias = []
    for linea in js.splitlines():
        corte = linea.find('//')
        limpias.append(linea if corte == -1 else linea[:corte])
    return '\n'.join(limpias)


def _bloque_funcion(fuente, firma):
    """Del `firma` hasta el siguiente `def ` en la columna 0 (o el final)."""
    ini = fuente.index(firma)
    m = re.search(r'\n(?:@app\.route|def )', fuente[ini + len(firma):])
    return fuente[ini:ini + len(firma) + (m.start() if m else len(fuente))]


class TestFrontPush(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.appjs = _fuente('static/app.js')
        cls.settings = _fuente('templates/settings.html')
        cls.base = _fuente('templates/base.html')
        cls.css = _fuente('static/style.css')
        ini = cls.appjs.index('window.Push = (function')
        cls.push = cls.appjs[ini:cls.appjs.index('\n})();', ini)]
        # Las versiones sin comentarios, para lo que se cuenta como CODIGO.
        cls.appjs_cod = _sin_comentarios(cls.appjs)
        cls.push_cod = _sin_comentarios(cls.push)
        cls.settings_cod = _sin_comentarios(cls.settings)

    def test_existe_window_push(self):
        for metodo in ('estado:', 'activar:', 'desactivar:', 'prueba:', 'bajaYSeguir:'):
            self.assertIn(metodo, self.push)

    def test_nada_se_dispara_al_cargar(self):
        """
        Chrome degrada a "prompt silencioso" a los sitios que piden permiso sin
        interaccion, y en iOS `requestPermission()` fuera de un gesto falla. El
        permiso sale del click del boton, nunca de la carga de la pagina.
        """
        # El unico `requestPermission` del proyecto vive adentro de
        # `pedirPermiso()`, que solo se llama desde `activar()`.
        self.assertEqual(self.appjs_cod.count('requestPermission'), 1)
        self.assertEqual(self.settings_cod.count('requestPermission'), 0)
        self.assertNotIn('Push.activar()', self.base)

    def test_el_estado_inicial_solo_mira(self):
        """Lo que corre solo al abrir Settings es `pintarEstado()`, que llama a
        `Push.estado()` — que no pide permiso ni suscribe."""
        self.assertIn('pintarEstado();', self.settings)
        self.assertIn('window.Push.estado()', self.settings)

    def test_convierte_la_clave_a_bytes(self):
        """
        `applicationServerKey` quiere un Uint8Array, no el string base64url.
        Es donde falla la mitad de las primeras integraciones: base64url usa
        '-' y '_' donde base64 usa '+' y la barra, y viaja sin relleno.
        """
        self.assertIn('Uint8Array', self.push)
        self.assertIn('atob', self.push)
        self.assertIn("replace(/-/g, '+')", self.push)
        self.assertIn("replace(/_/g, '/')", self.push)
        self.assertIn('applicationServerKey: bytes', self.push)

    def test_userVisibleOnly(self):
        self.assertIn('userVisibleOnly: true', self.push)

    def test_no_espera_a_un_service_worker_que_no_existe(self):
        """
        `navigator.serviceWorker.ready` con NINGUN service worker registrado
        —el caso de hoy, con `sw_enabled` apagado— no resuelve nunca. Hay que
        preguntar antes con `getRegistration()`, que si contesta que no hay
        nada, y correr el `ready` contra un reloj.
        """
        self.assertIn('getRegistration()', self.push)
        self.assertIn('Promise.race([sw.ready', self.push)

    def test_nunca_innerhtml(self):
        """Estandar de la casa: createElement + textContent, jamas innerHTML
        con datos que vienen de afuera."""
        self.assertNotIn('innerHTML', self.push)

    def test_las_instrucciones_de_ios_no_usan_standalone_false(self):
        """
        ⚠ LA TRAMPA. `navigator.standalone` existe SOLO en Safari; en iOS
        Chrome vale `undefined`. Preguntar `=== false` esconderia las
        instrucciones justo en el navegador donde mas falta hacen. Se pregunta
        por la NEGACION de "esta en standalone".
        """
        self.assertNotIn('standalone === false', self.appjs_cod)
        self.assertNotIn('standalone === false', self.settings_cod)
        self.assertIn('e.ios && !e.standalone', self.settings_cod)

    def test_el_boton_se_esconde_sin_pushmanager(self):
        self.assertIn('PushManager', self.push)
        self.assertIn('mostrar(btnActivar, false)', self.settings)

    def test_la_tarjeta_esta_en_settings_y_no_en_el_inicio(self):
        """Regla 7 de CLAUDE.md: el Inicio no se toca."""
        self.assertIn('id="avisos-push"', self.settings)
        self.assertIn('id="btn-push-activar"', self.settings)
        self.assertIn('id="btn-push-prueba"', self.settings)
        self.assertNotIn('push', _fuente('templates/index.html').lower())

    def test_el_modal_explicativo_va_antes_del_permiso(self):
        """
        El permiso se pide UNA vez (en iOS, una por instalacion). El cartel del
        sistema no explica nada: esta es la unica frase de margen que hay antes
        de quemar el unico tiro.
        """
        self.assertIn('id="modal-push"', self.settings)
        # El boton abre el modal; el permiso sale del "Continuar".
        self.assertIn('abrirModal()', self.settings)
        bloque = self.settings[self.settings.index("modalSi.addEventListener"):]
        self.assertIn('activarDeVerdad()', bloque[:400])

    def test_el_modal_dice_que_no_van_montos(self):
        modal = self.settings[self.settings.index('id="modal-push"'):
                              self.settings.index('id="modal-push-no"')]
        self.assertIn('Nunca van montos', modal)

    def test_dice_como_revertir_un_no_permitir(self):
        ayuda = self.settings[self.settings.index('id="push-revertir"'):]
        self.assertIn('Android', ayuda[:800])
        self.assertIn('iPhone', ayuda[:800])

    def test_cero_css_nuevo(self):
        """
        Regla 1 de CLAUDE.md: la tarjeta reusa clases que ya existian (la de
        "Reparar app" es el molde). Si alguna de estas no esta en style.css,
        es que se invento CSS en vez de reusar.
        """
        for clase in ('.settings-card', '.settings-ayuda',
                      '.settings-cotizacion-acciones', '.settings-cotizacion-msg',
                      '.modal-fondo', '.modal-caja', '.modal-texto',
                      '.modal-botones'):
            with self.subTest(clase=clase):
                self.assertIn(clase + ' {', self.css)

    def test_el_logout_manda_el_endpoint_por_post(self):
        """
        Y no por querystring: el endpoint es el buzon de ese telefono y no
        tiene por que quedar en el log de accesos ni en el historial.
        """
        self.assertIn('id="modal-salir-si"', self.base)
        self.assertIn("form.method = 'POST'", self.appjs)
        self.assertIn("campo.name = 'endpoint'", self.appjs)

    def test_salir_no_puede_quedar_colgado(self):
        """`bajaYSeguir()` corre contra un reloj y nunca rechaza."""
        self.assertIn('Promise.race([trabajo, esperar(', self.push)

    def test_apple_touch_icon(self):
        """
        iOS NO lee el manifest para el icono de "Agregar a inicio": sin esta
        etiqueta se guarda una CAPTURA de la pagina. Y el icono no es
        cosmetica: en iOS el push SOLO funciona abriendo la app desde ahi.
        """
        self.assertIn('rel="apple-touch-icon"', self.base)
        self.assertIn('icon-192.png', self.base)


if __name__ == '__main__':
    unittest.main()
