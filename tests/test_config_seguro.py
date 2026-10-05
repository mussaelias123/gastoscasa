# =============================================================================
# ARCHIVO: tests/test_config_seguro.py
# =============================================================================
#
# Tests de la lectura y la escritura de config.json (config.py): candado,
# escritura atomica y lectura estricta al guardar.
#
# POR QUE EXISTE ESTE ARCHIVO
#
#   config.json guarda lo que NO se recupera: credenciales de Google,
#   secret_key, claves VAPID, token de ngrok. Antes se escribia con open(..,'w')
#   (trunca y despues escribe) y sin candado, y eso rompia DOS cosas, las dos
#   medidas con una prueba aislada:
#
#     1. UN LECTOR VEIA EL ARCHIVO A MEDIAS. ~18% de las lecturas, con
#        escrituras seguidas, veian "sin credenciales de Google" — y auth.py
#        dejaba pasar a cualquiera por eso. Ver test_auth_cerrado.py.
#
#     2. UN GUARDADO BORRABA LOS SECRETOS PARA SIEMPRE. guardar_config leia,
#        cambiaba una clave y escribia todo; si lo que leyo era un archivo a
#        medias, escribia DEFAULTS + su cambio. Dos escritores a la vez lo
#        disparaban.
#
#   Las dos fallas son SILENCIOSAS: la app anda, ninguna pagina da error, y el
#   dia que aparece el sintoma las credenciales ya no estan. Por eso se miden
#   con hilos de verdad (clase TestConcurrencia) y no solo mirando el codigo.
#
#   Todo corre sobre un config TEMPORAL: nunca se toca el config.json real de
#   la maquina donde corren los tests.
#
# COMO CORRER:
#   Desde la raiz del proyecto:
#       python -m unittest tests.test_config_seguro -v
#
# =============================================================================

import fnmatch
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config  # noqa: E402


# Lo que el config de prueba tiene que conservar SIEMPRE. Son valores
# inconfundibles: si alguno aparece vacio o cambiado, se perdio algo.
SECRETOS = {
    'google_client_id': 'id-canario',
    'google_client_secret': 'secreto-canario',
    'secret_key': 'clave-canario',
}

# Contenidos que existen en disco pero NO sirven como config. Cada uno es una
# forma real de llegar ahi: el corte a mitad de una escritura vieja, un editor
# que guardo vacio, alguien que escribio una lista en vez de un objeto, un
# archivo guardado en cp1252 con una enie.
ILEGIBLES = {
    'json cortado a la mitad':
        b'{"google_client_id": "id-canario", "google_client_secret": "secr',
    'archivo vacio': b'',
    'raiz lista': b'[1, 2, 3]',
    'raiz null': b'null',
    'raiz texto': b'"hola"',
    'utf8 invalido': b'{"app_name": "Gastos \xf1"}',
    'no es json': b'esto no es json',
}


class BaseConfig(unittest.TestCase):
    """Cada test arranca con un config.json temporal que ya trae los secretos."""

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix='fondo-cfg-')
        self.ruta = os.path.join(self._dir, 'config.json')
        self.escribir_json(dict(SECRETOS))
        # Los reintentos de lectura duermen 50 ms entre intento e intento. La
        # logica de reintentar se prueba igual sin dormir de verdad.
        parche = unittest.mock.patch.object(config, '_LECTURA_ESPERA', 0)
        parche.start()
        self.addCleanup(parche.stop)

    def tearDown(self):
        shutil.rmtree(self._dir, ignore_errors=True)

    # -- Atajos -------------------------------------------------------------

    def escribir_json(self, datos):
        with open(self.ruta, 'w', encoding='utf-8') as f:
            json.dump(datos, f)

    def escribir_bytes(self, crudo):
        with open(self.ruta, 'wb') as f:
            f.write(crudo)

    def bytes_actuales(self):
        with open(self.ruta, 'rb') as f:
            return f.read()

    def leer_crudo(self):
        """El JSON tal cual esta en el disco (sin pasar por cargar_config)."""
        with open(self.ruta, 'r', encoding='utf-8') as f:
            return json.load(f)

    def archivos(self):
        return sorted(os.listdir(self._dir))

    def assert_secretos_intactos(self, cfg):
        for clave, valor in SECRETOS.items():
            self.assertEqual(cfg[clave], valor, f'{clave} se perdio o cambio')


# ── 1. Concurrencia: hilos de verdad ─────────────────────────────────────────

class TestConcurrencia(BaseConfig):

    def test_ninguna_lectura_ve_el_archivo_a_medias(self):
        """
        Escritores y lectores en hilos, ~1 s, sobre el mismo archivo. Con la
        escritura vieja, ~18% de las lecturas veian "sin credenciales". Ahora
        ninguna: el archivo cambia de un contenido completo a otro completo.
        """
        fin = time.monotonic() + 1.0
        lecturas, escrituras = [], []
        malas, fallas = [], []

        def escritor():
            try:
                i = 0
                while time.monotonic() < fin:
                    i += 1
                    config.guardar_config(
                        {'factor_sueldo': 0.5 + (i % 20) / 100}, self.ruta)
                    escrituras.append(1)
                    # Que el lector tenga turno: sin esto el escritor vuelve a
                    # tomar el candado antes de que otro hilo despierte.
                    time.sleep(0.001)
            except Exception as e:  # noqa: BLE001 — se reporta abajo
                fallas.append(('escritor', repr(e)))

        def lector():
            try:
                while time.monotonic() < fin:
                    cfg = config.cargar_config(self.ruta)
                    lecturas.append(1)
                    for clave, valor in SECRETOS.items():
                        if cfg[clave] != valor:
                            malas.append((clave, cfg[clave]))
            except Exception as e:  # noqa: BLE001
                fallas.append(('lector', repr(e)))

        hilos = ([threading.Thread(target=escritor) for _ in range(2)]
                 + [threading.Thread(target=lector) for _ in range(3)])
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        self.assertEqual(fallas, [])
        self.assertEqual(malas, [], 'una lectura vio la config sin sus secretos')
        # Que el test no sea vacuo: de verdad hubo trafico en los dos sentidos.
        self.assertGreater(len(escrituras), 10)
        self.assertGreater(len(lecturas), 10)
        self.assert_secretos_intactos(self.leer_crudo())

    def test_dos_escritores_a_la_vez_no_se_pisan(self):
        """
        Cada escritor guarda SU clave 100 veces. Sin candado, el leer-modificar-
        escribir de uno pisa al del otro (lee 'a' viejo, el otro escribe 'a'
        nuevo, el primero escribe 'a' viejo de vuelta) y la ultima 'a' o 'b'
        del disco no es la ultima que se guardo. Con candado quedan las dos, y
        los secretos tambien.
        """
        vueltas = 100
        fallas = []

        def escritor(clave):
            try:
                for i in range(1, vueltas + 1):
                    config.guardar_config({clave: i}, self.ruta)
            except Exception as e:  # noqa: BLE001
                fallas.append((clave, repr(e)))

        hilos = [threading.Thread(target=escritor, args=('zz_escritor_a',)),
                 threading.Thread(target=escritor, args=('zz_escritor_b',))]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        self.assertEqual(fallas, [])
        crudo = self.leer_crudo()
        self.assert_secretos_intactos(crudo)
        self.assertEqual(crudo['zz_escritor_a'], vueltas)
        self.assertEqual(crudo['zz_escritor_b'], vueltas)
        self.assertEqual(self.archivos(), ['config.json'])

    def test_un_lector_de_otro_proceso_nunca_ve_el_archivo_a_medias(self):
        """
        El candado es de PROCESO: no frena a un editor, al antivirus ni a un
        script que lea config.json por su cuenta. A esos los cubre la escritura
        ATOMICA. Se los simula con lectores CRUDOS —sin pasar por config.py, sin
        candado— mientras otro hilo guarda sin parar: tienen que ver siempre un
        JSON completo (el viejo o el nuevo), nunca uno cortado. Con el
        open(..,'w') de antes, la mayoria de estas lecturas caia en el hueco.

        (Los tests de arriba no distinguen una escritura atomica de una
        in-place: entre hilos del mismo proceso el candado ya las serializa.)
        """
        fin = time.monotonic() + 1.0
        lecturas, escrituras = [], []
        malas, fallas = [], []

        def escritor():
            try:
                i = 0
                while time.monotonic() < fin:
                    i += 1
                    config.guardar_config(
                        {'factor_sueldo': 0.5 + (i % 20) / 100}, self.ruta)
                    escrituras.append(1)
                    time.sleep(0.001)
            except Exception as e:  # noqa: BLE001
                fallas.append(('escritor', repr(e)))

        def lector_crudo():
            try:
                while time.monotonic() < fin:
                    try:
                        with open(self.ruta, 'r', encoding='utf-8') as f:
                            texto = f.read()
                    except (PermissionError, FileNotFoundError):
                        # En Windows, abrir justo durante el reemplazo puede dar
                        # esto. No es un archivo a medias: es un "ahora no".
                        continue
                    lecturas.append(1)
                    try:
                        crudo = json.loads(texto)
                    except ValueError as e:
                        malas.append(('json cortado', repr(e)))
                        continue
                    for clave, valor in SECRETOS.items():
                        if crudo.get(clave) != valor:
                            malas.append((clave, crudo.get(clave)))
                    time.sleep(0.0005)  # lector educado: no tapa al escritor
            except Exception as e:  # noqa: BLE001
                fallas.append(('lector', repr(e)))

        hilos = ([threading.Thread(target=escritor)]
                 + [threading.Thread(target=lector_crudo) for _ in range(3)])
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        self.assertEqual(fallas, [])
        self.assertEqual(malas, [], 'un lector sin candado vio el archivo a medias')
        self.assertGreater(len(escrituras), 10)
        self.assertGreater(len(lecturas), 10)
        self.assert_secretos_intactos(self.leer_crudo())

    def test_el_leer_modificar_escribir_va_bajo_el_candado(self):
        """
        Lo de arriba es estadistico; esto es determinista. Mientras
        guardar_config escribe, el candado tiene que estar tomado: se lo pide
        desde OTRO hilo (un RLock deja pasar al hilo que ya lo tiene, por eso
        no sirve probarlo desde el mismo).
        """
        visto = {}
        real = config._escribir_atomico

        def espia(ruta, cfg):
            def probar():
                visto['libre'] = config._LOCK.acquire(blocking=False)
                if visto['libre']:
                    config._LOCK.release()
            hilo = threading.Thread(target=probar)
            hilo.start()
            hilo.join()
            return real(ruta, cfg)

        with unittest.mock.patch.object(config, '_escribir_atomico', espia):
            config.guardar_config({'app_name': 'X'}, self.ruta)
        self.assertIn('libre', visto)
        self.assertFalse(visto['libre'], 'se escribio sin tener el candado')

    def test_la_lectura_tambien_va_bajo_el_candado(self):
        """
        Por eso un lector del mismo proceso nunca tiene el archivo abierto
        mientras otro hilo lo reemplaza (en Windows eso es un PermissionError).
        """
        visto = {}
        real = config._leer_una_vez

        def espia(ruta):
            def probar():
                visto['libre'] = config._LOCK.acquire(blocking=False)
                if visto['libre']:
                    config._LOCK.release()
            hilo = threading.Thread(target=probar)
            hilo.start()
            hilo.join()
            return real(ruta)

        with unittest.mock.patch.object(config, '_leer_una_vez', espia):
            config.cargar_config(self.ruta)
        self.assertIn('libre', visto)
        self.assertFalse(visto['libre'], 'se leyo sin tener el candado')


# ── 2. guardar_config no pisa un archivo ilegible ────────────────────────────

class TestGuardarNoPisaIlegible(BaseConfig):

    def test_se_niega_y_deja_el_archivo_intacto(self):
        """
        El corazon del arreglo. Pisar un config ilegible con DEFAULTS + el
        cambio es lo que borraba las credenciales para siempre. Ahora se niega,
        no escribe NADA (ni el archivo ni un temporal) y el archivo queda
        byte por byte como estaba, para que alguien lo arregle a mano.
        """
        for nombre, crudo in ILEGIBLES.items():
            with self.subTest(nombre):
                self.escribir_bytes(crudo)
                with unittest.mock.patch.object(config, 'log'):
                    with self.assertRaises(config.ConfigIlegible):
                        config.guardar_config({'app_name': 'Nuevo'}, self.ruta)
                self.assertEqual(self.bytes_actuales(), crudo)
                self.assertEqual(self.archivos(), ['config.json'])

    def test_la_negativa_queda_en_el_log(self):
        """
        Las rutas de app.py atrapan la excepcion y la devuelven como JSON, asi
        que sin una linea de log el detalle (que linea del JSON esta rota) no
        quedaria en ningun lado.
        """
        self.escribir_bytes(ILEGIBLES['json cortado a la mitad'])
        with unittest.mock.patch.object(config, 'log') as log:
            with self.assertRaises(config.ConfigIlegible):
                config.guardar_config({'app_name': 'Nuevo'}, self.ruta)
        self.assertEqual(log.call_count, 1)
        mensaje = log.call_args[0][0]
        self.assertTrue(mensaje.startswith('AVISO:'))
        self.assertIn('NO escribi', mensaje)

    def test_config_ilegible_no_es_un_value_error(self):
        """
        Las rutas de app.py atrapan `ValueError` ANTES que `Exception` y
        contestan 400 ("error tuyo"). Un config roto es un problema del
        servidor: tiene que salir como 500. Si alguien le hace heredar de
        ValueError "por prolijidad", este test avisa.
        """
        self.assertTrue(issubclass(config.ConfigIlegible, Exception))
        self.assertFalse(issubclass(config.ConfigIlegible, ValueError))

    def test_el_archivo_legible_se_guarda_y_conserva_los_secretos(self):
        config.guardar_config({'app_name': 'Nuevo'}, self.ruta)
        crudo = self.leer_crudo()
        self.assertEqual(crudo['app_name'], 'Nuevo')
        self.assert_secretos_intactos(crudo)

    def test_las_paletas_se_mergean_por_clave_como_siempre(self):
        """El merge de paletas es de antes; el refactor no tiene que cambiarlo."""
        self.escribir_json({**SECRETOS, 'paleta_light': {'acento': '#000000'}})
        config.guardar_config({'app_name': 'Nuevo'}, self.ruta)
        crudo = self.leer_crudo()
        self.assertEqual(crudo['paleta_light']['acento'], '#000000')
        # Las claves que el archivo no traia vuelven desde DEFAULTS.
        self.assertEqual(set(crudo['paleta_light']),
                         set(config.DEFAULTS['paleta_light']))
        self.assertEqual(crudo['paleta_dark'], config.DEFAULTS['paleta_dark'])

    def test_una_paleta_que_no_es_un_objeto_no_rompe_la_carga(self):
        """
        JSON valido pero con la paleta mal escrita a mano. `cargar_config` no
        puede lanzar (se llama en cada request, tambien desde el login): la
        paleta mala se ignora y vale la de DEFAULTS. Y guardar la repara.
        """
        self.escribir_json({**SECRETOS, 'paleta_light': 'rojo', 'paleta_dark': [1, 2]})
        cfg = config.cargar_config(self.ruta)
        self.assert_secretos_intactos(cfg)
        self.assertEqual(cfg['paleta_light'], config.DEFAULTS['paleta_light'])
        self.assertEqual(cfg['paleta_dark'], config.DEFAULTS['paleta_dark'])

        config.guardar_config({'app_name': 'Nuevo'}, self.ruta)
        crudo = self.leer_crudo()
        self.assertEqual(crudo['paleta_light'], config.DEFAULTS['paleta_light'])
        self.assert_secretos_intactos(crudo)

    def test_si_no_existe_parte_de_defaults_y_lo_crea(self):
        os.remove(self.ruta)
        config.guardar_config({'app_name': 'Recien creado'}, self.ruta)
        crudo = self.leer_crudo()
        self.assertEqual(crudo['app_name'], 'Recien creado')
        for clave in config.DEFAULTS:
            self.assertIn(clave, crudo)
        self.assertEqual(self.archivos(), ['config.json'])

    def test_bom_se_lee_y_se_reescribe_sin_bom(self):
        """
        Varios editores de Windows (el Bloc de notas viejo, PowerShell 5.1 con
        -Encoding UTF8) guardan UTF-8 CON BOM. Como arreglar config.json a mano
        es la forma de configurar la app, un byte invisible no puede dejarla
        ilegible (y con el login cerrado).
        """
        self.escribir_bytes(b'\xef\xbb\xbf' + json.dumps(SECRETOS).encode('utf-8'))
        with unittest.mock.patch.object(config, 'log') as log:
            cfg = config.cargar_config(self.ruta)
        self.assert_secretos_intactos(cfg)
        log.assert_not_called()

        config.guardar_config({'app_name': 'Nuevo'}, self.ruta)
        self.assertFalse(self.bytes_actuales().startswith(b'\xef\xbb\xbf'))
        self.assert_secretos_intactos(self.leer_crudo())


# ── 3. cargar_config con archivo ilegible ────────────────────────────────────

class TestCargarIlegible(BaseConfig):

    def test_ilegible_devuelve_defaults_sin_credenciales(self):
        """
        Devuelve DEFAULTS —que NO traen credenciales de Google— y no explota:
        se llama en cada request y desde los hilos de fondo. Que no traiga
        credenciales es lo que hace que auth.py cierre el login.
        """
        for nombre, crudo in ILEGIBLES.items():
            with self.subTest(nombre):
                self.escribir_bytes(crudo)
                with unittest.mock.patch.object(config, 'log'):
                    cfg = config.cargar_config(self.ruta)
                self.assertEqual(cfg['google_client_id'], '')
                self.assertEqual(cfg['google_client_secret'], '')
                self.assertEqual(cfg['secret_key'], '')
                self.assertEqual(cfg, config.DEFAULTS)

    def test_ilegible_no_modifica_el_archivo(self):
        """Leer nunca arregla ni reescribe nada."""
        for nombre, crudo in ILEGIBLES.items():
            with self.subTest(nombre):
                self.escribir_bytes(crudo)
                with unittest.mock.patch.object(config, 'log'):
                    config.cargar_config(self.ruta)
                self.assertEqual(self.bytes_actuales(), crudo)

    def test_inexistente_devuelve_defaults_sin_aviso(self):
        os.remove(self.ruta)
        with unittest.mock.patch.object(config, 'log') as log:
            cfg = config.cargar_config(self.ruta)
        self.assertEqual(cfg, config.DEFAULTS)
        log.assert_not_called()

    def test_el_aviso_sale_una_vez_por_minuto(self):
        """
        cargar_config corre en CADA request: con el archivo roto, un AVISO por
        llamada llenaria el log. Como mucho uno por minuto.
        """
        self.escribir_bytes(ILEGIBLES['json cortado a la mitad'])
        with unittest.mock.patch.object(config, 'log') as log:
            for _ in range(20):
                config.cargar_config(self.ruta)
        self.assertEqual(log.call_count, 1)
        mensaje = log.call_args[0][0]
        self.assertTrue(mensaje.startswith('AVISO:'))
        self.assertIn('CERRADO', mensaje)

        # Pasado el minuto, vuelve a avisar: si no, un archivo que sigue roto
        # a la manana siguiente no dejaria ni una linea.
        config._ultimo_aviso_ilegible[os.path.abspath(self.ruta)] -= (
            config._AVISO_ILEGIBLE_CADA + 1)
        with unittest.mock.patch.object(config, 'log') as log:
            config.cargar_config(self.ruta)
        self.assertEqual(log.call_count, 1)

    def test_el_aviso_no_loguea_el_contenido_del_archivo(self):
        """
        El archivo trae secretos. El mensaje del decoder de JSON dice tipo y
        posicion del error, nunca el contenido; este test congela que ninguna
        linea de log lo copie.
        """
        self.escribir_bytes(ILEGIBLES['json cortado a la mitad'])
        with unittest.mock.patch.object(config, 'log') as log:
            config.cargar_config(self.ruta)
            with self.assertRaises(config.ConfigIlegible):
                config.guardar_config({'app_name': 'Nuevo'}, self.ruta)
        # Una linea del lector (AVISO de ilegible) y una del escritor (se nego).
        self.assertEqual(log.call_count, 2)
        for llamada in log.call_args_list:
            mensaje = llamada[0][0]
            for secreto in SECRETOS.values():
                self.assertNotIn(secreto, mensaje)

    def test_un_fallo_pasajero_se_cubre_con_reintentos(self):
        """
        Un humano guardando con un editor deja el archivo ilegible unos
        milisegundos. Dos fallos y despues la lectura buena: se devuelve la
        config de verdad y no se avisa nada.
        """
        bueno = {**SECRETOS, 'app_name': 'Lectura buena'}
        fallos = [config.ConfigIlegible('pasajero')] * 2
        with unittest.mock.patch.object(
                config, '_leer_una_vez', side_effect=fallos + [bueno]) as leer, \
                unittest.mock.patch.object(config, 'log') as log:
            cfg = config.cargar_config(self.ruta)
        self.assertEqual(leer.call_count, 3)
        self.assertEqual(cfg['app_name'], 'Lectura buena')
        self.assert_secretos_intactos(cfg)
        log.assert_not_called()

    def test_si_los_reintentos_no_alcanzan_devuelve_defaults(self):
        fallos = [config.ConfigIlegible('persistente')] * config._LECTURA_INTENTOS
        with unittest.mock.patch.object(
                config, '_leer_una_vez', side_effect=fallos) as leer, \
                unittest.mock.patch.object(config, 'log') as log:
            cfg = config.cargar_config(self.ruta)
        self.assertEqual(leer.call_count, config._LECTURA_INTENTOS)
        self.assertEqual(cfg['google_client_id'], '')
        self.assertEqual(log.call_count, 1)


# ── 4. Escritura atomica y temporales ────────────────────────────────────────

class TestEscrituraAtomica(BaseConfig):

    def test_no_queda_ningun_temporal(self):
        config.guardar_config({'app_name': 'Nuevo'}, self.ruta)
        self.assertEqual(self.archivos(), ['config.json'])

    def test_el_formato_es_el_de_siempre(self):
        """indent=2 y ensure_ascii=False: el archivo se sigue pudiendo leer y
        editar a mano, y una enie se guarda como enie y no como \\u00f1."""
        self.escribir_json({**SECRETOS, 'app_name': 'Ñandú'})
        config.guardar_config({'factor_sueldo': 0.9}, self.ruta)
        with open(self.ruta, 'r', encoding='utf-8') as f:
            texto = f.read()
        self.assertTrue(texto.startswith('{\n  "'))
        self.assertIn('Ñandú', texto)
        self.assertNotIn('\\u00f1', texto)
        self.assertEqual(json.loads(texto)['factor_sueldo'], 0.9)

    def test_el_temporal_va_en_la_misma_carpeta_y_git_lo_ignora(self):
        """
        Misma carpeta: un os.replace entre discos no es atomico. Y el nombre
        tiene que estar cubierto por .gitignore: un corte de luz que deje un
        temporal lo deja con una copia completa de la config (secretos
        incluidos), y no puede colarse en un `git add -A`.
        """
        visto = {}
        real = os.replace

        def espia(origen, destino):
            visto['origen'], visto['destino'] = origen, destino
            return real(origen, destino)

        with unittest.mock.patch.object(os, 'replace', espia):
            config.guardar_config({'app_name': 'Nuevo'}, self.ruta)

        self.assertEqual(os.path.dirname(visto['origen']), os.path.dirname(visto['destino']))
        self.assertEqual(os.path.abspath(visto['destino']), os.path.abspath(self.ruta))
        nombre = os.path.basename(visto['origen'])
        with open(os.path.join(ROOT_DIR, '.gitignore'), encoding='utf-8') as f:
            patrones = [l.strip() for l in f if l.strip() and not l.startswith('#')]
        self.assertTrue(any(fnmatch.fnmatch(nombre, p) for p in patrones),
                        f'.gitignore no cubre el temporal {nombre}')

    def test_reintenta_si_os_replace_falla_con_permission_error(self):
        """
        En Windows os.replace tira PermissionError si OTRO proceso (un editor,
        el antivirus) tiene abierto el destino. Falla 3 veces y despues anda:
        el guardado se completa igual.
        """
        real = os.replace
        llamadas = []

        def inestable(origen, destino):
            llamadas.append(1)
            if len(llamadas) <= 3:
                raise PermissionError(13, 'Acceso denegado (simulado)')
            return real(origen, destino)

        with unittest.mock.patch.object(os, 'replace', inestable):
            config.guardar_config({'app_name': 'Despues de reintentar'}, self.ruta)

        self.assertEqual(len(llamadas), 4)
        crudo = self.leer_crudo()
        self.assertEqual(crudo['app_name'], 'Despues de reintentar')
        self.assert_secretos_intactos(crudo)
        self.assertEqual(self.archivos(), ['config.json'])

    def test_si_os_replace_falla_siempre_se_rinde_y_limpia(self):
        """
        Pasado el tiempo de espera relanza el error, borra el temporal (tiene
        una copia con secretos) y deja el config bueno como estaba.
        """
        antes = self.bytes_actuales()

        def siempre_denegado(origen, destino):
            raise PermissionError(13, 'Acceso denegado (simulado)')

        with unittest.mock.patch.object(config, '_REEMPLAZO_ESPERA_TOTAL', 0.15), \
                unittest.mock.patch.object(os, 'replace', siempre_denegado):
            with self.assertRaises(PermissionError):
                config.guardar_config({'app_name': 'Nunca se guarda'}, self.ruta)

        self.assertEqual(self.bytes_actuales(), antes)
        self.assertEqual(self.archivos(), ['config.json'])

    def test_si_falla_el_fsync_no_queda_el_temporal(self):
        antes = self.bytes_actuales()
        with unittest.mock.patch.object(
                os, 'fsync', side_effect=OSError(5, 'Disco lleno (simulado)')):
            with self.assertRaises(OSError):
                config.guardar_config({'app_name': 'Nunca se guarda'}, self.ruta)
        self.assertEqual(self.bytes_actuales(), antes)
        self.assertEqual(self.archivos(), ['config.json'])

    def test_un_valor_que_json_no_serializa_no_toca_el_disco(self):
        """El texto se arma ANTES de crear nada: ni el archivo ni un temporal."""
        antes = self.bytes_actuales()
        with self.assertRaises(TypeError):
            config.guardar_config({'raro': object()}, self.ruta)
        self.assertEqual(self.bytes_actuales(), antes)
        self.assertEqual(self.archivos(), ['config.json'])

    def test_si_no_se_puede_borrar_el_temporal_se_avisa_con_el_nombre(self):
        """
        El temporal tiene secretos: si ni reintentando se lo puede borrar, no
        puede ser en silencio. El AVISO dice cual es para borrarlo a mano.
        """
        tmp = os.path.join(self._dir, 'config.json.zzzz.tmp')
        with open(tmp, 'w') as f:
            f.write('{}')
        with unittest.mock.patch.object(config, '_REEMPLAZO_PASO', 0), \
                unittest.mock.patch.object(
                    os, 'remove', side_effect=PermissionError(13, 'tomado (simulado)')), \
                unittest.mock.patch.object(config, 'log') as log:
            config._borrar_temporal(tmp)
        self.assertEqual(log.call_count, 1)
        self.assertIn('AVISO', log.call_args[0][0])
        self.assertIn(tmp, log.call_args[0][0])


if __name__ == '__main__':
    unittest.main()
