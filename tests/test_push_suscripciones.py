# =============================================================================
# ARCHIVO: tests/test_push_suscripciones.py
# =============================================================================
#
# Tests de la tabla `push_suscripciones` y de las dos rutas que la escriben
# (/api/push/alta y /api/push/baja). ACA NO SE MANDA NINGUN PUSH: esta etapa
# solo guarda a quien habria que avisarle.
#
# POR QUE EXISTE ESTE ARCHIVO
#
#   1. EL NO-OP DEL UPSERT. El navegador re-manda su suscripcion en cada
#      arranque de la app, y casi siempre con los mismos datos. Si esa alta
#      repetida ESCRIBIERA igual, el dump logico de la base cambiaria todos
#      los dias; _hash_datos_db() (app.py) veria "datos nuevos" y
#      _scheduler_backup generaria un backup diario FALSO para siempre. Eso
#      inutiliza el detector, que es lo unico que hoy distingue un dia con
#      movimientos de uno sin. La falla es SILENCIOSA: la app anda perfecto y
#      la carpeta de backups se llena de copias identicas. Por eso el test
#      central de este archivo no mira la fila: mide el HASH de la base antes
#      y despues de 10 altas iguales.
#
#   2. QUIEN ES EL DUEÑO DEL BUZON. `persona` y `user_email` los decide el
#      SERVIDOR (sesion), nunca el POST — que lo escribe el navegador y puede
#      decir cualquier cosa. Si eso se invirtiera, cualquiera se anotaria para
#      recibir los avisos del otro, y no habria forma de notarlo mirando la
#      pantalla.
#
#   3. EL LOGOUT. La limpieza tiene que correr ANTES del session.clear(), que
#      es donde vive el email. Puesta despues, no borra nada y nadie se
#      entera: las filas quedan vivas y el telefono de quien se fue sigue
#      recibiendo los avisos de esa cuenta.
#
# COMO CORRER:
#   Desde la raiz del proyecto:
#       python -m unittest tests.test_push_suscripciones -v
#
# =============================================================================

import os
import sys
import shutil
import tempfile
import unittest
import unittest.mock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import app as app_module  # noqa: E402
import auth  # noqa: E402
import config  # noqa: E402
import database  # noqa: E402


# Una suscripcion con la pinta de las de verdad: endpoint https del servicio
# de push, p256dh de 87 caracteres base64url y auth de 22.
ENDPOINT = 'https://fcm.googleapis.com/fcm/send/cJfG8hQ:APA91bH-ejemplo-de-endpoint'
P256DH = 'B' + 'a' * 86
AUTH = 'c' * 22


def _cfg_con(**cambios):
    """
    Devuelve un `cargar_config` falso: la config de verdad con las claves que
    se pidan pisadas. Se parchea la funcion y no el archivo, para no tocar el
    config.json real de la maquina donde corren los tests.
    """
    real = config.cargar_config

    def falso(ruta=None):
        cfg = real(ruta)
        cfg.update(cambios)
        return cfg

    return falso


class BasePush(unittest.TestCase):
    """
    Cada test arranca con una base temporal vacia y un cliente de la app.

    Se usa una base SQLite real en archivo, no mocks: lo que se esta probando
    es el `ON CONFLICT ... WHERE` del SQL y el dump que sale de esa base. Un
    mock de la capa de datos no ejecuta ninguna de las dos cosas.
    """

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix='fondo-push-')
        self._db_original = database.DB_PATH
        database.DB_PATH = os.path.join(self._dir, 'fondo.db')
        database.inicializar_db()
        self.client = app_module.app.test_client()

    def tearDown(self):
        database.DB_PATH = self._db_original
        shutil.rmtree(self._dir, ignore_errors=True)

    # -- Atajos -------------------------------------------------------------

    def login(self, email='mussaelias123@gmail.com', nombre='Elias'):
        """Deja una sesion valida en el cliente, como despues del OAuth."""
        with self.client.session_transaction() as sesion:
            sesion['user_email'] = email
            sesion['user_name'] = nombre

    def alta(self, endpoint=ENDPOINT, p256dh=P256DH, auth_=AUTH, headers=None, **extra):
        datos = {'endpoint': endpoint, 'p256dh': p256dh, 'auth': auth_}
        datos.update(extra)
        cabeceras = {'X-Requested-With': 'XMLHttpRequest'}
        cabeceras.update(headers or {})
        return self.client.post('/api/push/alta', data=datos, headers=cabeceras)

    def baja(self, endpoint=ENDPOINT):
        return self.client.post(
            '/api/push/baja', data={'endpoint': endpoint},
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )

    def filas(self):
        return [dict(f) for f in database.obtener_suscripciones_push()]

    def hash_db(self):
        return app_module._hash_datos_db(database.DB_PATH)


# ── 1. Alta ──────────────────────────────────────────────────────────────────

class TestAlta(BasePush):

    def test_el_alta_crea_la_fila(self):
        self.login()
        r = self.alta()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()['ok'])

        filas = self.filas()
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['endpoint'], ENDPOINT)
        self.assertEqual(filas[0]['p256dh'], P256DH)
        self.assertEqual(filas[0]['auth'], AUTH)
        self.assertTrue(filas[0]['creada'])

    def test_acepta_el_json_de_pushsubscription(self):
        """
        `PushSubscription.toJSON()` trae las claves anidadas en `keys`. Se
        acepta esa forma para que el front pueda mandar la suscripcion tal
        cual se la dio el navegador, sin desarmarla.
        """
        self.login()
        r = self.client.post(
            '/api/push/alta',
            json={'endpoint': ENDPOINT, 'keys': {'p256dh': P256DH, 'auth': AUTH}},
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self.filas()), 1)

    def test_dos_navegadores_son_dos_filas(self):
        self.login()
        self.alta()
        self.alta(endpoint=ENDPOINT + '-otro-telefono')
        self.assertEqual(len(self.filas()), 2)


# ── 2. El test que importa: la idempotencia NO MUEVE EL HASH ────────────────

class TestIdempotencia(BasePush):

    def test_diez_altas_iguales_dejan_una_sola_fila(self):
        self.login()
        for _ in range(10):
            self.assertEqual(self.alta().status_code, 200)
        self.assertEqual(len(self.filas()), 1)

    def test_diez_altas_iguales_no_mueven_el_hash_de_la_db(self):
        """
        EL CORAZON DEL ARCHIVO. Si esto se pone rojo, el detector de backups
        quedo inutil: _scheduler_backup va a ver "datos nuevos" todos los dias
        y a guardar una copia identica cada 24 h, para siempre.

        LO QUE LO GARANTIZA ES QUE `creada` NO SE REFRESQUE, no el `WHERE`.
        _hash_datos_db() hashea el CONTENIDO de las filas, no las escrituras:
        un UPDATE que reescribe los mismos valores deja la fila igual y el hash
        quieto. Medido — sin el `WHERE` hay 10 UPDATE reales y el hash tampoco
        se mueve. El `WHERE` se gana el lugar por otro motivo (no escribir al
        pedo, y poder devolver si escribio), y por eso se lo verifica aparte,
        aca abajo.

        El reloj se parchea a proposito: `_ahora_iso()` tiene resolucion de
        SEGUNDOS y las 10 altas corren en milisegundos, asi que sin esto la
        mitad `creada` solo se probaria si el loop cae justo sobre un cambio de
        segundo. Un guardian que depende del reloj no es un guardian.
        """
        self.login()
        self.alta()                      # la primera SI cambia la base
        antes = self.hash_db()

        reloj = ['2030-01-01 10:00:%02d' % s for s in range(11)]
        with unittest.mock.patch.object(database, '_ahora_iso',
                                        side_effect=reloj):
            for _ in range(10):
                self.alta()

        self.assertEqual(self.hash_db(), antes,
                         "un alta repetida con los mismos datos cambio el contenido "
                         "de la fila (mira si `creada` se esta refrescando)")

    def test_diez_altas_iguales_tampoco_escriben(self):
        """
        La otra mitad, y la que SI congela el `WHERE`: el test de arriba pasa
        igual con el `WHERE` borrado (el hash mira contenido, no escrituras),
        asi que sin este nadie se entera de que alguien lo saco por
        "simplificar". Diez altas repetidas tienen que ser diez no-op.
        """
        self.assertTrue(database.guardar_suscripcion_push(
            ENDPOINT, P256DH, AUTH, 'elias', 'e@x.com', 'UA'))
        for _ in range(10):
            self.assertFalse(
                database.guardar_suscripcion_push(
                    ENDPOINT, P256DH, AUTH, 'elias', 'e@x.com', 'UA'),
                'el alta repetida escribio: se borro el WHERE del ON CONFLICT')

    def test_el_hash_si_se_mueve_cuando_algo_cambia(self):
        """
        Contraparte del anterior: sin este, un _hash_datos_db() roto (que
        devolviera siempre lo mismo) haria pasar el test de arriba sin probar
        nada.
        """
        self.login()
        self.alta()
        antes = self.hash_db()
        self.alta(endpoint=ENDPOINT + '-otro')
        self.assertNotEqual(self.hash_db(), antes)

    def test_la_capa_de_datos_avisa_si_escribio(self):
        """`guardar_suscripcion_push` devuelve si hubo escritura de verdad."""
        self.assertTrue(database.guardar_suscripcion_push(
            ENDPOINT, P256DH, AUTH, 'elias', 'e@x.com', 'UA'))
        self.assertFalse(database.guardar_suscripcion_push(
            ENDPOINT, P256DH, AUTH, 'elias', 'e@x.com', 'UA'))
        # Cambiar un solo campo SI tiene que escribir.
        self.assertTrue(database.guardar_suscripcion_push(
            ENDPOINT, P256DH, AUTH, 'mari', 'm@x.com', 'UA'))


# ── 3. Baja ──────────────────────────────────────────────────────────────────

class TestBaja(BasePush):

    def test_la_baja_borra_la_fila(self):
        self.login()
        self.alta()
        r = self.baja()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()['ok'])
        self.assertEqual(self.filas(), [])

    def test_la_baja_de_algo_inexistente_no_explota(self):
        """
        El navegador puede pedir la baja de algo que ya se borro de este lado
        (un logout desde otro lado, otra pestaña, la app reinstalada). Eso no
        es un error del usuario ni del servidor: responde ok con 0 borradas.
        """
        self.login()
        r = self.baja(endpoint='https://fcm.googleapis.com/fcm/send/no-existe')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()['ok'])
        self.assertEqual(r.get_json()['borradas'], 0)

    def test_la_baja_solo_se_lleva_ese_navegador(self):
        self.login()
        self.alta()
        self.alta(endpoint=ENDPOINT + '-otro')
        self.baja()
        self.assertEqual([f['endpoint'] for f in self.filas()], [ENDPOINT + '-otro'])


# ── 4. La persona la pone el servidor ───────────────────────────────────────

class TestPersonaDelServidor(BasePush):

    def test_el_post_no_puede_elegir_la_persona(self):
        """
        Se manda `persona=mari` y `user_email` de Mari en el POST estando
        logueado como Elias. Tienen que ignorarse los dos: el POST lo escribe
        el navegador y puede decir cualquier cosa.
        """
        self.login('mussaelias123@gmail.com')
        r = self.alta(persona='mari', user_email='mossinomariana@gmail.com')
        self.assertEqual(r.status_code, 200)

        fila = self.filas()[0]
        self.assertEqual(fila['persona'], 'elias')
        self.assertEqual(fila['user_email'], 'mussaelias123@gmail.com')

    def test_la_persona_sale_de_la_sesion(self):
        self.login('mossinomariana@gmail.com', 'Mari')
        self.alta()
        self.assertEqual(self.filas()[0]['persona'], 'mari')

    def test_el_mismo_navegador_cambia_de_dueno(self):
        """
        Una suscripcion identifica un NAVEGADOR, no una persona. Si Mari entra
        en el telefono de Elias, el endpoint es el mismo y el dueno pasa a ser
        la ultima sesion: quien mire ese telefono va a ver el aviso.
        """
        self.login('mussaelias123@gmail.com')
        self.alta()
        self.login('mossinomariana@gmail.com', 'Mari')
        self.alta()

        filas = self.filas()
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['persona'], 'mari')
        self.assertEqual(filas[0]['user_email'], 'mossinomariana@gmail.com')

    def test_en_dev_manda_persona_dev(self):
        """
        Con el bypass DEV la sesion es `dev@local`, que no esta en
        PERSONAS_POR_EMAIL: ahi decide la clave `persona_dev` de config.
        """
        self.login('dev@local', 'DEV')
        with unittest.mock.patch.object(config, 'cargar_config',
                                        _cfg_con(persona_dev='mari')):
            self.alta()
        self.assertEqual(self.filas()[0]['persona'], 'mari')


# ── 5. Validacion: un POST puede mandar cualquier cosa ──────────────────────

class TestValidacion(BasePush):

    def _rechaza(self, **campos):
        r = self.alta(**campos)
        self.assertEqual(r.status_code, 400, f"no rechazo {campos}")
        self.assertFalse(r.get_json()['ok'])
        self.assertEqual(self.filas(), [], "guardo una fila invalida")

    def setUp(self):
        super().setUp()
        self.login()

    def test_endpoint_vacio(self):
        self._rechaza(endpoint='')

    def test_endpoint_que_no_es_url(self):
        self._rechaza(endpoint='no-soy-una-url')

    def test_endpoint_http_pelado(self):
        """No existe un endpoint de push por http: los tres servicios son https."""
        self._rechaza(endpoint='http://fcm.googleapis.com/fcm/send/algo')

    def test_endpoint_kilometrico(self):
        self._rechaza(endpoint='https://fcm.googleapis.com/' + 'x' * 2000)

    def test_claves_faltantes(self):
        self._rechaza(p256dh='')
        self._rechaza(auth_='')

    def test_claves_con_largo_raro(self):
        self._rechaza(p256dh='corta')
        self._rechaza(auth_='a' * 200)

    def test_claves_que_no_son_base64url(self):
        self._rechaza(p256dh='B' + '!' * 86)

    def test_la_baja_tambien_valida_el_endpoint(self):
        r = self.client.post('/api/push/baja', data={'endpoint': 'chau'},
                             headers={'X-Requested-With': 'XMLHttpRequest'})
        self.assertEqual(r.status_code, 400)

    def test_el_user_agent_se_recorta(self):
        """
        El UA lo elige el cliente. Uno de 50 KB entraria entero a la fila, al
        dump logico y al backup diario, para cero beneficio. El recorte es
        deterministico, asi que el alta repetida sigue siendo un no-op.
        """
        self.alta(headers={'User-Agent': 'M' * 5000})
        self.assertEqual(len(self.filas()[0]['user_agent']), 300)

        antes = self.hash_db()
        self.alta(headers={'User-Agent': 'M' * 5000})
        self.assertEqual(self.hash_db(), antes)


# ── 6. Las dos rutas van PROTEGIDAS ─────────────────────────────────────────

class TestProtegidas(BasePush):

    def test_sin_sesion_no_se_puede_dar_de_alta(self):
        """
        Son justamente las rutas que atan un endpoint a una persona: sin
        sesion no hay a quien atarlo. NO entran en `rutas_publicas`.
        """
        with unittest.mock.patch.object(
                config, 'cargar_config',
                _cfg_con(auth_disabled=False, ngrok_enabled=False,
                         google_client_id='id-de-prueba',
                         google_client_secret='secreto-de-prueba')):
            r = self.alta()
            self.assertEqual(r.status_code, 302)
            self.assertIn('/login', r.headers['Location'])

            r = self.baja()
            self.assertEqual(r.status_code, 302)

        self.assertEqual(self.filas(), [])

    def test_no_estan_en_rutas_publicas(self):
        """
        Congela la decision: las publicas son las del login, `static` y las dos
        de la PWA (manifest y service worker), que el navegador pide antes de
        que exista sesion. Estas dos NO.
        """
        with open(os.path.join(ROOT_DIR, 'auth.py'), encoding='utf-8') as f:
            fuente = f.read()
        self.assertNotIn('api_push_alta', fuente)
        self.assertNotIn('api_push_baja', fuente)


# ── 7. El logout limpia ─────────────────────────────────────────────────────

class TestLogoutLimpia(BasePush):

    def test_el_logout_borra_las_filas_de_ese_email(self):
        self.login('mussaelias123@gmail.com')
        self.alta()
        self.alta(endpoint=ENDPOINT + '-tablet')
        self.assertEqual(len(self.filas()), 2)

        r = self.client.get('/logout')
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.filas(), [])

    def test_el_logout_no_toca_las_del_otro(self):
        self.login('mossinomariana@gmail.com', 'Mari')
        self.alta(endpoint=ENDPOINT + '-de-mari')
        self.login('mussaelias123@gmail.com', 'Elias')
        self.alta()

        self.client.get('/logout')

        filas = self.filas()
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]['user_email'], 'mossinomariana@gmail.com')

    def test_si_el_borrado_falla_igual_se_desloguea(self):
        """
        Una suscripcion huerfana es un aviso de mas en un telefono; no poder
        salir de la sesion es quedarse adentro de la app.
        """
        self.login()
        self.alta()

        def explota(_email):
            raise RuntimeError('base bloqueada')

        with unittest.mock.patch.object(
                database, 'borrar_suscripciones_push_de_email', explota):
            r = self.client.get('/logout')

        self.assertEqual(r.status_code, 302)
        self.assertIn('/login', r.headers['Location'])
        with self.client.session_transaction() as sesion:
            self.assertIsNone(sesion.get('user_email'))

    def test_el_borrado_por_email_no_se_lleva_todo_con_email_vacio(self):
        """
        Un logout sin sesion no puede borrar las filas que quedaron sin email.
        """
        database.guardar_suscripcion_push(ENDPOINT, P256DH, AUTH, 'elias', '', 'UA')
        self.assertEqual(database.borrar_suscripciones_push_de_email(''), 0)
        self.assertEqual(database.borrar_suscripciones_push_de_email(None), 0)
        self.assertEqual(len(self.filas()), 1)

    def test_el_borrado_por_email_ignora_mayusculas(self):
        self.login('mussaelias123@gmail.com')
        self.alta()
        self.assertEqual(
            database.borrar_suscripciones_push_de_email('MussaElias123@Gmail.com'), 1)


# ── 8. Nada de esto manda un push ───────────────────────────────────────────

class TestEndpointSoloDeServiciosDePush(BasePush):
    """
    Lista blanca de hosts. Hoy el endpoint es un dato guardado; desde la etapa
    que prenda el envio es un DESTINO al que el servidor le hace un POST, y el
    servidor corre adentro de la red de casa. Se valida cuando el dato ENTRA.
    """

    def test_acepta_los_servicios_de_verdad(self):
        for endpoint in (
            'https://fcm.googleapis.com/fcm/send/abc',          # Chrome/Android
            'https://android.googleapis.com/gcm/send/abc',      # FCM viejo
            'https://updates.push.services.mozilla.com/wpush/v2/x',  # Firefox
            'https://web.push.apple.com/QAbc123',               # Safari / iOS
            'https://sn1-1.notify.windows.com/w/?token=x',      # WNS, por sufijo
        ):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(app_module._push_endpoint_valido(endpoint), endpoint)

    def test_rechaza_lo_que_apunta_adentro_de_casa(self):
        """
        SSRF. Con el envio prendido, cada aviso a uno de estos seria un POST
        del servidor a un host de la LAN que desde afuera no se alcanza.
        """
        for endpoint in (
            'https://192.168.1.1/admin',
            'https://127.0.0.1:5050/api/backups/crear',
            'https://10.0.0.5/x',
            'https://169.254.169.254/latest/meta-data/',        # metadata de cloud
            'https://localhost/x',
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValueError):
                    app_module._push_endpoint_valido(endpoint)

    def test_rechaza_el_sufijo_tramposo(self):
        """
        Por esto se compara el HOSTNAME parseado y no un startswith sobre la
        URL: esta empieza con el host bueno y es de otro.
        """
        with self.assertRaises(ValueError):
            app_module._push_endpoint_valido('https://fcm.googleapis.com.evil.com/x')

    def test_rechaza_un_host_cualquiera_y_el_http(self):
        for endpoint in ('https://evil.example.com/recibo-los-avisos',
                         'http://fcm.googleapis.com/fcm/send/abc'):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValueError):
                    app_module._push_endpoint_valido(endpoint)

    def test_normaliza_el_esquema_y_el_host(self):
        """Sin esto, `HTTPS://FCM...` y `https://fcm...` son dos filas para el
        mismo telefono, y el upsert deja de ser no-op para ese buzon."""
        self.assertEqual(
            app_module._push_endpoint_valido('HTTPS://FCM.GOOGLEAPIS.COM/fcm/send/abc'),
            'https://fcm.googleapis.com/fcm/send/abc')

    def test_rechaza_caracteres_de_control(self):
        """Un \\r\\n termina en un cliente HTTP cuando se mande de verdad; un
        \\x00 va a la fila, al dump y a todos los backups."""
        self.login()
        for malo in (ENDPOINT + '\r\nX-Evil: 1', ENDPOINT + '\x00y'):
            with self.subTest(malo=repr(malo)):
                self.assertEqual(self.alta(endpoint=malo).status_code, 400)


class TestBajaSoloLoPropio(BasePush):

    def test_no_se_puede_dar_de_baja_el_telefono_del_otro(self):
        """
        Sin el filtro por email alcanzaba con conocer el endpoint del otro para
        dejarlo sin avisos: un POST, sin nada en pantalla que lo explique y sin
        vuelta atras salvo re-suscribir el dispositivo. Mismo criterio que
        `_es_ajeno()` en los movimientos personales.
        """
        self.login(email='mari@ejemplo.com', nombre='Mari')
        self.alta(endpoint=ENDPOINT + '-de-mari')

        self.login()   # ahora entra Elias
        r = self.client.post('/api/push/baja',
                             data={'endpoint': ENDPOINT + '-de-mari'},
                             headers={'X-Requested-With': 'XMLHttpRequest'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['borradas'], 0,
                         'Elias dio de baja la suscripcion de Mari')

    def test_la_baja_propia_sigue_andando(self):
        self.login()
        self.alta()
        r = self.client.post('/api/push/baja', data={'endpoint': ENDPOINT},
                             headers={'X-Requested-With': 'XMLHttpRequest'})
        self.assertEqual(r.get_json()['borradas'], 1)


class TestRellenoBase64(BasePush):

    def test_la_misma_clave_con_y_sin_relleno_es_un_no_op(self):
        """
        El upsert compara strings crudos: `B...a` y `B...a==` son la MISMA
        clave y dos strings distintos. Si el front la manda por un camino y el
        reintento por otro, cada alternancia seria una escritura real.
        """
        self.login()
        self.alta(p256dh=P256DH, auth_=AUTH)
        antes = self.hash_db()
        self.alta(p256dh=P256DH + '==', auth_=AUTH + '=')
        self.assertEqual(self.hash_db(), antes,
                         'la misma clave con relleno se guardo como distinta')


class TestUnSoloCaminoDeEnvio(unittest.TestCase):
    """
    Guarda de ETAPA, no de diseño. Ya se llamo `TestNoSeMandaNada` (cuando
    nadie importaba pywebpush) y despues `TestNadaCorreSolo` (cuando lo unico
    que mandaba un push era un boton). Las dos veces el nombre dejo de ser
    cierto y hubo que venir a cambiarlo A MANO, que es exactamente para lo que
    esta la clase: obligar a que encender algo sea una DECISION escrita.

    HOY SON DOS LOS CAMINOS DE ENVIO, y ninguno mas:

      1. POST /api/push/prueba — el boton de Settings. No mira `push_enabled`
         a proposito: es el diagnostico del canal.
      2. `_push_ciclo()` — el motor automatico. Ese SI mira `push_enabled`
         (hoy en False), y encima tiene frenos propios: horas de silencio,
         tope por vuelta y tope por dia. Se prueba en tests/test_push_encendido.py.

    LO QUE ESTA CLASE SIGUE VIGILANDO ES QUE NO APAREZCA UN TERCERO. Un camino
    de envio nuevo es un telefono que suena por algo que nadie decidio que
    mereciera sonar, y un push no se puede desavisar. Si este test se pone
    rojo, la pregunta no es como arreglarlo: es quien agrego el camino y por
    que no esta documentado en docs/CONTEXT_PUSH.md.
    """

    def test_push_enabled_lo_lee_el_motor_y_nadie_mas(self):
        """
        El interruptor dejo de ser decorativo en la etapa del encendido: ahora
        SE LEE, y se lee EN CALIENTE adentro de la vuelta del scheduler (si se
        leyera al importar, apagarlo pediria reiniciar el servicio y no seria
        un kill switch).

        Lo que se congela es que lo lea UN SOLO lugar, `_push_encendido()`. Un
        `push_enabled` consultado desde varios lados es un flag que apaga
        algunas cosas y otras no — el peor resultado posible para un
        interruptor de panico, que se toca justo cuando algo ya salio mal.
        """
        import inspect
        import app as app_module
        with open(os.path.join(ROOT_DIR, 'app.py'), encoding='utf-8') as f:
            fuente = f.read()
        self.assertEqual(fuente.count("cfg.get('push_enabled')"), 1)
        self.assertIn("cfg.get('push_enabled')",
                      inspect.getsource(app_module._push_encendido))
        # Y NO por las otras formas de escribir lo mismo. Contar solo la
        # variante con comillas simples dejaba pasar un
        # `if cfg["push_enabled"] is not True` en api_push_prueba() con el
        # test en VERDE: el boton de diagnostico empezaria a obedecer el flag,
        # o sea que para probar el canal habria que encender antes la cosa que
        # uno no sabe si funciona.
        for variante in ('cfg.get("push_enabled")', "cfg['push_enabled']",
                         'cfg["push_enabled"]'):
            with self.subTest(variante=variante):
                self.assertNotIn(variante, fuente)
        # Y el motor lo consulta por esa puerta, no por su cuenta.
        self.assertIn('_push_encendido(',
                      inspect.getsource(app_module._push_ciclo))

        # Ni la base ni el login tienen nada que opinar sobre esto.
        for archivo in ('database.py', 'auth.py'):
            with open(os.path.join(ROOT_DIR, archivo), encoding='utf-8') as f:
                otro = f.read()
            self.assertNotIn('push_enabled', otro)

    def test_el_envio_tiene_dos_disparadores_y_ni_uno_mas(self):
        """
        `webpush(` aparece UNA vez en toda la app: adentro de `_push_enviar`,
        que es la unica puerta a la red. Un segundo `webpush(` es, por
        definicion, alguien mandando avisos por su cuenta.

        Y `_push_enviar` se llama desde DOS lugares: la ruta de prueba y el
        motor. Un tercero es un camino que nadie reviso.

        SE CUENTA SOBRE TODO EL ARCHIVO, no sobre las funciones del motor.
        Mirar solo esas funciones no alcanza: un
        `def _push_anunciar(...): _push_enviar(...)` llamado desde
        `_push_ciclo` las deja limpias, deja `webpush(` en 1 (sigue adentro de
        `_push_enviar`) y pone el test en VERDE mientras los telefonos suenan
        solos. El conteo global es lo unico que no se puede esquivar con una
        indireccion.

        DOS CONTEOS, a proposito:
          · El textual saltea los comentarios (el `#` habla del codigo, no lo
            ejecuta) pero NO los docstrings — por eso en app.py el nombre se
            escribe sin parentesis cuando se lo menciona en prosa.
          · El del AST cuenta LLAMADAS de verdad, y es el que no se puede
            enganar ni con prosa ni con formato.
        """
        import ast
        with open(os.path.join(ROOT_DIR, 'app.py'), encoding='utf-8') as f:
            fuente = f.read()
        self.assertEqual(fuente.count('webpush('), 1)

        codigo_vivo = [l for l in fuente.split('\n') if not l.strip().startswith('#')]
        llamadas = sum(l.count('_push_enviar(') for l in codigo_vivo)
        # 3 = la `def` + las DOS llamadas: /api/push/prueba y _push_ciclo.
        self.assertEqual(llamadas, 3,
                         "Cambio la cantidad de llamadores de _push_enviar(): "
                         "o aparecio un camino de envio nuevo, o alguien lo "
                         "nombro con parentesis en un docstring.")

        arbol = ast.parse(fuente)
        sitios = [n for n in ast.walk(arbol)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Name)
                  and n.func.id == '_push_enviar']
        self.assertEqual(len(sitios), 2,
                         "Aparecio un TERCER camino de envio de push.")

    def test_decidir_que_avisar_no_toca_la_red_ni_la_tabla(self):
        """
        `_push_avisos_ahora()` decide QUE se avisaria; `_push_ciclo()` decide
        si eso sale y lo manda. Esa separacion es la que deja correr el ensayo
        en seco por el MISMO camino que el encendido, y por eso la primera no
        manda, no lee endpoints y no sabe que existe una tabla.

        El hilo tampoco: `_scheduler_push()` es un `while True` con un sleep
        al final — toda la decision vive en la vuelta, donde se la puede
        testear con el reloj congelado.
        """
        import inspect
        import app as app_module
        for fn in (app_module._push_avisos_ahora, app_module._scheduler_push):
            with self.subTest(fn=fn.__name__):
                codigo = inspect.getsource(fn)
                self.assertNotIn('_push_enviar', codigo)
                self.assertNotIn('obtener_suscripciones_push', codigo)


if __name__ == '__main__':
    unittest.main()
