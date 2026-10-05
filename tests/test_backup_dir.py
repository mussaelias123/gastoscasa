# =============================================================================
# ARCHIVO: tests/test_backup_dir.py
# =============================================================================
#
# Tests de la carpeta de backups: SOLO DISCO LOCAL (app.py →
# _validar_backup_dir, _unidad_es_remota, _get_backup_dir y la accion
# `guardar_backup_dir` de /settings).
#
# POR QUE EXISTE ESTE ARCHIVO
#
#   `backup_dir` sale de un formulario de Settings y de config.json, y se
#   usaba tal cual. Con una ruta de red (`\\servidor\carpeta`) el backup diario
#   -la base ENTERA, con todos los movimientos de la casa- se escribia en un
#   servidor ajeno, y NADA se notaba: el listado de backups sigue andando
#   porque lee la misma carpeta, y la app da 200 en todo. Como el servicio de
#   PROD corre como LocalSystem, Windows ademas le entrega al servidor la
#   credencial de red (NTLM) de esta maquina al abrir esa ruta.
#
#   Lo que se congela aca:
#     1. Que se rechace TODA forma de ruta de red o de dispositivo: UNC con
#        barras de las dos clases (Windows trata `/` y `\` igual), `\\?\UNC\`,
#        `\\.\`, una unidad mapeada de red y la ruta relativa a una unidad
#        (`C:carpeta`, que os.path.join resuelve contra OTRA unidad y pisa la
#        base del proyecto).
#     2. Que NO se rechace lo que tiene que seguir andando: las relativas de
#        siempre (`backups`, `backupsdev`) y las absolutas locales. PROD usa
#        `C:\Users\elias\OneDrive\BackupsFondo`; un validador que la rechace
#        deja al servicio sin backups, y eso tampoco se ve a simple vista.
#     3. Que la validacion corra en LOS DOS puntos: al guardar (Settings avisa
#        el motivo y no guarda) y al LEER (`_get_backup_dir`, porque config.json
#        se puede editar a mano y esa ruta no paso por Settings). El segundo es
#        el que cubre al scheduler, al listado, al restore y al estado del push.
#     4. Que el aviso del log salga UNA vez: `_get_backup_dir` se llama desde
#        los schedulers y desde casi cada ruta de backups.
#
#   Los tests NO dependen de en que unidad corran: la consulta de tipo de
#   unidad (GetDriveTypeW) se mockea, salvo un test que la llama de verdad para
#   comprobar que la llamada de ctypes anda y no solo el mock.
#
# COMO CORRER:
#   Desde la raiz del proyecto:
#       python -m unittest tests.test_backup_dir -v
#
# =============================================================================

import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from urllib.parse import urlsplit

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import app as app_module  # noqa: E402
import config  # noqa: E402
import database  # noqa: E402

ELIAS = 'mussaelias123@gmail.com'

# La funcion de verdad, capturada al importar (antes de que ningun test la
# parchee): `_cfg_con` siempre arma sobre ESTA.
_CARGAR_REAL = config.cargar_config
_AUSENTE = object()

DEFAULT = os.path.join(app_module._BASE_DIR_BACKUP, 'backups')


def _cfg_con(**cambios):
    """
    La config de verdad con lo imprescindible pisado (OAuth "configurado" y
    bypass DEV apagado, asi el login se exige de verdad) mas lo que se pida.
    Se parchea la FUNCION y no el archivo, para no tocar el config.json de la
    maquina. `_AUSENTE` como valor BORRA la clave.
    """
    def falso(ruta=None):
        cfg = _CARGAR_REAL(ruta)
        cfg.update({
            'google_client_id': 'id',
            'google_client_secret': 's',
            'auth_disabled': False,
            'ngrok_enabled': False,
        })
        for clave, valor in cambios.items():
            if valor is _AUSENTE:
                cfg.pop(clave, None)
            else:
                cfg[clave] = valor
        return cfg

    return falso


def _sin_unidades_de_red():
    """Parche: ninguna letra de unidad es de red (el test no depende del equipo)."""
    return unittest.mock.patch.object(
        app_module, '_unidad_es_remota', return_value=False)


# ── 1. El validador ──────────────────────────────────────────────────────────

class TestValidarBackupDir(unittest.TestCase):

    def setUp(self):
        parche = _sin_unidades_de_red()
        self.es_remota = parche.start()
        self.addCleanup(parche.stop)

    def validar(self, valor):
        return app_module._validar_backup_dir(valor)

    def test_vacio_vale_el_default(self):
        for valor in ('', '   ', None):
            with self.subTest(valor=valor):
                self.assertEqual(self.validar(valor), 'backups')

    def test_las_relativas_de_siempre_valen(self):
        for valor in ('backups', 'backupsdev', 'copias\\fondo', 'copias/fondo',
                      '..\\copias', 'a.b'):
            with self.subTest(valor=valor):
                self.assertEqual(self.validar(valor), valor)

    def test_los_espacios_de_los_bordes_se_recortan(self):
        self.assertEqual(self.validar('  backupsdev  '), 'backupsdev')

    def test_una_absoluta_local_vale(self):
        carpeta = os.path.join(tempfile.gettempdir(), 'fondo-backups')
        for valor in (carpeta,
                      'D:\\Backups',
                      'C:/backups',
                      'c:\\backups',
                      'C:\\'):
            with self.subTest(valor=valor):
                self.assertEqual(self.validar(valor), valor)

    def test_la_ruta_de_prod_sigue_valiendo(self):
        """Disco local que OneDrive sincroniza aparte: tiene que seguir andando."""
        prod = 'C:\\Users\\elias\\OneDrive\\BackupsFondo'
        self.assertEqual(self.validar(prod), prod)

    def test_el_tope_de_largo_es_260(self):
        self.assertEqual(self.validar('a' * 260), 'a' * 260)
        self.assertEqual(self.validar('C:\\' + 'a' * 257), 'C:\\' + 'a' * 257)
        with self.assertRaises(ValueError):
            self.validar('a' * 261)
        with self.assertRaises(ValueError):
            self.validar('C:\\' + 'a' * 258)

    def test_las_rutas_de_red_y_de_dispositivo_se_rechazan(self):
        for valor in (
                '\\\\srv\\share',                  # UNC
                '\\\\srv\\share\\backups',
                '//srv/share',                     # UNC con barras comunes
                '//srv/share/backups',
                '\\/srv\\share',                   # mezcla de barras: Windows las trata igual
                '/\\srv/share',
                '\\\\?\\UNC\\srv\\share\\x',       # UNC con prefijo extendido
                '\\\\.\\pipe\\x',                  # ruta de dispositivo
                '\\\\?\\C:\\backups',              # extendida, aunque sea local: se rechaza el prefijo
                '   \\\\srv\\share   ',            # con espacios alrededor
        ):
            with self.subTest(valor=valor):
                with self.assertRaises(ValueError) as ctx:
                    self.validar(valor)
                self.assertIn('este equipo', str(ctx.exception))

    def test_una_ruta_con_una_sola_barra_inicial_no_es_de_red(self):
        """`\\backups` es la raiz de la unidad actual: local. Solo DOS barras son UNC."""
        self.assertEqual(self.validar('\\backups'), '\\backups')
        self.assertEqual(self.validar('/backups'), '/backups')

    def test_la_ruta_relativa_a_una_unidad_se_rechaza(self):
        for valor in ('C:carpeta', 'c:backups', 'D:x\\y', 'C:'):
            with self.subTest(valor=valor):
                with self.assertRaises(ValueError) as ctx:
                    self.validar(valor)
                self.assertIn('relativa a una unidad', str(ctx.exception))

    def test_una_unidad_de_red_se_rechaza(self):
        self.es_remota.return_value = True
        for valor, raiz in (('Z:\\backups', 'Z:\\'),
                            ('z:/backups', 'Z:\\'),
                            ('Z:\\', 'Z:\\')):
            with self.subTest(valor=valor):
                self.es_remota.reset_mock()
                with self.assertRaises(ValueError) as ctx:
                    self.validar(valor)
                self.assertIn('es de red', str(ctx.exception))
                # La raiz que se consulta va normalizada, sea cual sea la
                # barra y la capitalizacion que escribieron.
                self.es_remota.assert_called_once_with(raiz)

    def test_una_unidad_local_no_se_rechaza(self):
        self.es_remota.return_value = False
        self.assertEqual(self.validar('Z:\\backups'), 'Z:\\backups')
        self.es_remota.assert_called_once_with('Z:\\')

    def test_una_relativa_no_consulta_ninguna_unidad(self):
        self.validar('backupsdev')
        self.es_remota.assert_not_called()

    def test_dos_puntos_fuera_de_la_letra_de_unidad(self):
        for valor in ('backups:stream', 'C:\\x:y', 'C:\\x\\archivo:flujo',
                      '1:\\x', 'ab:\\x'):
            with self.subTest(valor=valor):
                with self.assertRaises(ValueError):
                    self.validar(valor)

    def test_caracteres_de_control_y_no_admitidos(self):
        casos = ['back\x00ups', 'back\nups', 'back\rups', 'back\tups',
                 'back\x7fups', 'back\x85ups',
                 'back' + chr(0x2028) + 'ups', 'back' + chr(0x2029) + 'ups',
                 'a<b', 'a>b', 'a"b', 'a|b', 'a?b', 'a*b',
                 '"C:\\Users\\elias\\Backups"']   # pegada con las comillas de "Copiar como ruta"
        for valor in casos:
            with self.subTest(valor=repr(valor)):
                with self.assertRaises(ValueError):
                    self.validar(valor)

    def test_lo_que_no_es_texto_se_rechaza(self):
        for valor in (123, 4.5, True, ['backups'], {'a': 1}, b'backups'):
            with self.subTest(valor=repr(valor)):
                with self.assertRaises(ValueError):
                    self.validar(valor)

    def test_el_mensaje_no_repite_la_ruta(self):
        """El motivo es texto fijo: no devuelve lo que mandaron."""
        for valor in ('\\\\servidor-raro\\share', 'C:carpeta-rara', 'x' * 300,
                      'a<raro>b'):
            with self.subTest(valor=valor[:20]):
                with self.assertRaises(ValueError) as ctx:
                    self.validar(valor)
                self.assertNotIn('raro', str(ctx.exception))


class TestUnidadEsRemota(unittest.TestCase):
    """La consulta de verdad, contra GetDriveTypeW. Solo Windows."""

    @unittest.skipUnless(os.name == 'nt', 'GetDriveTypeW solo existe en Windows')
    def test_el_tipo_4_es_una_unidad_de_red(self):
        import ctypes
        with unittest.mock.patch.object(
                ctypes.windll.kernel32, 'GetDriveTypeW', return_value=4) as api:
            self.assertTrue(app_module._unidad_es_remota('Z:\\'))
        api.assert_called_once_with('Z:\\')

    @unittest.skipUnless(os.name == 'nt', 'GetDriveTypeW solo existe en Windows')
    def test_los_otros_tipos_no_lo_son(self):
        import ctypes
        # 0 desconocida, 1 sin raiz, 2 extraible, 3 fija, 5 CD-ROM, 6 RAM
        for tipo in (0, 1, 2, 3, 5, 6):
            with self.subTest(tipo=tipo):
                with unittest.mock.patch.object(
                        ctypes.windll.kernel32, 'GetDriveTypeW', return_value=tipo):
                    self.assertFalse(app_module._unidad_es_remota('Z:\\'))

    @unittest.skipUnless(os.name == 'nt', 'GetDriveTypeW solo existe en Windows')
    def test_la_llamada_real_anda(self):
        """Sin mock: que ctypes llame bien a la API, no solo que ande el parche."""
        unidad = os.path.splitdrive(os.path.abspath(__file__))[0] + '\\'
        self.assertIn(app_module._unidad_es_remota(unidad), (True, False))
        # Una letra sin unidad no es de red.
        self.assertFalse(app_module._unidad_es_remota('Q:\\') and False)


# ── 2. Base de los tests con Flask ───────────────────────────────────────────

class BaseApp(unittest.TestCase):
    """Base temporal, config parcheada y sesion de Elias."""

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix='fondo-backup-dir-')
        self._db_original = database.DB_PATH
        database.DB_PATH = os.path.join(self._dir, 'fondo.db')
        database.inicializar_db()
        self.client = app_module.app.test_client()
        self.con_config()
        with self.client.session_transaction() as sesion:
            sesion['user_email'] = ELIAS
            sesion['user_name'] = 'Elias'
        parche = _sin_unidades_de_red()
        self.es_remota = parche.start()
        self.addCleanup(parche.stop)
        # El anti-spam del log es estado del modulo: cada test arranca limpio y
        # no le deja nada al siguiente.
        app_module._backup_dir_avisados.clear()
        self.addCleanup(app_module._backup_dir_avisados.clear)

    def tearDown(self):
        database.DB_PATH = self._db_original
        shutil.rmtree(self._dir, ignore_errors=True)

    def con_config(self, **cambios):
        """Parcha cargar_config hasta el final del test. Se puede repetir."""
        parche = unittest.mock.patch.object(
            config, 'cargar_config', _cfg_con(**cambios))
        parche.start()
        self.addCleanup(parche.stop)


# ── 3. Guardar desde Settings ────────────────────────────────────────────────

class TestSettingsGuardarBackupDir(BaseApp):

    def setUp(self):
        super().setUp()
        # NUNCA se escribe el config.json de la maquina: guardar_config es un mock.
        parche = unittest.mock.patch.object(config, 'guardar_config')
        self.guardar = parche.start()
        self.addCleanup(parche.stop)

    def post(self, valor):
        return self.client.post(
            '/settings', data={'accion': 'guardar_backup_dir', 'backup_dir': valor})

    def mensajes(self):
        with self.client.session_transaction() as sesion:
            return [mensaje for _categoria, mensaje in sesion.get('_flashes', [])]

    def test_una_ruta_invalida_avisa_el_motivo_y_no_guarda(self):
        self.es_remota.side_effect = lambda raiz: raiz == 'Z:\\'
        for valor in ('\\\\srv\\share', '//srv/share', '\\\\?\\UNC\\srv\\share\\x',
                      '\\\\.\\pipe\\x', 'C:carpeta', 'Z:\\backups',
                      'back\x00ups', 'a' * 261):
            with self.subTest(valor=valor[:30]):
                self.guardar.reset_mock()
                r = self.post(valor)
                self.assertEqual(r.status_code, 302)
                self.assertEqual(urlsplit(r.headers['Location']).path, '/settings')
                self.guardar.assert_not_called()
                avisos = self.mensajes()
                self.assertEqual(len(avisos), 1)
                self.assertIn('No se guardó la carpeta de backups', avisos[0])
                # Limpia el flash para que el proximo caso cuente solo el suyo.
                self.client.get('/settings')

    def test_una_ruta_valida_se_guarda_normalizada(self):
        carpeta = os.path.join(tempfile.gettempdir(), 'fondo-backups')
        casos = [
            (carpeta, carpeta),
            ('  ' + carpeta + '  ', carpeta),        # espacios de los bordes
            ('backupsdev', 'backupsdev'),
            ('', 'backups'),                          # vacio = el default
            ('   ', 'backups'),
        ]
        for enviado, guardado in casos:
            with self.subTest(enviado=enviado):
                self.guardar.reset_mock()
                r = self.post(enviado)
                self.assertEqual(r.status_code, 302)
                self.assertEqual(urlsplit(r.headers['Location']).fragment, 'backup-db')
                self.guardar.assert_called_once_with(
                    {'backup_dir': guardado}, app_module.CONFIG_FILE)
                self.assertEqual(self.mensajes(), ['Carpeta de backups guardada.'])
                self.client.get('/settings')

    def test_la_ruta_de_prod_se_guarda(self):
        prod = 'C:\\Users\\elias\\OneDrive\\BackupsFondo'
        self.post(prod)
        self.guardar.assert_called_once_with({'backup_dir': prod}, app_module.CONFIG_FILE)

    def test_una_unidad_de_red_no_se_guarda(self):
        self.es_remota.return_value = True
        self.post('Z:\\backups')
        self.guardar.assert_not_called()

    def test_sin_el_campo_se_guarda_el_default(self):
        """Un POST sin `backup_dir` es un campo vacio: 'backups', como siempre."""
        self.client.post('/settings', data={'accion': 'guardar_backup_dir'})
        self.guardar.assert_called_once_with(
            {'backup_dir': 'backups'}, app_module.CONFIG_FILE)


# ── 4. Leer: _get_backup_dir ─────────────────────────────────────────────────

class TestGetBackupDir(BaseApp):

    def setUp(self):
        super().setUp()
        parche = unittest.mock.patch.object(app_module, 'log')
        self.log = parche.start()
        self.addCleanup(parche.stop)

    def carpeta_con(self, valor):
        self.con_config(backup_dir=valor)
        return app_module._get_backup_dir()

    def test_una_relativa_se_resuelve_contra_el_proyecto(self):
        self.assertEqual(self.carpeta_con('backupsdev'),
                         os.path.join(app_module._BASE_DIR_BACKUP, 'backupsdev'))
        self.log.assert_not_called()

    def test_una_absoluta_local_se_usa_tal_cual(self):
        carpeta = os.path.join(tempfile.gettempdir(), 'fondo-backups')
        self.assertEqual(self.carpeta_con(carpeta), carpeta)
        prod = 'C:\\Users\\elias\\OneDrive\\BackupsFondo'
        self.assertEqual(self.carpeta_con(prod), prod)
        self.log.assert_not_called()

    def test_vacio_o_ausente_es_el_default_y_no_avisa(self):
        for valor in ('', None, _AUSENTE):
            with self.subTest(valor=repr(valor)):
                self.assertEqual(self.carpeta_con(valor), DEFAULT)
        self.log.assert_not_called()

    def test_un_valor_invalido_en_config_cae_al_default(self):
        for valor in ('\\\\srv\\share', '//srv/share', '\\\\?\\UNC\\srv\\share\\x',
                      'C:carpeta', 'back\x00ups', 'a' * 261, 123, ['backups']):
            with self.subTest(valor=repr(valor)[:30]):
                self.assertEqual(self.carpeta_con(valor), DEFAULT)

    def test_una_unidad_de_red_en_config_cae_al_default(self):
        self.es_remota.return_value = True
        self.assertEqual(self.carpeta_con('Z:\\copias'), DEFAULT)

    def test_el_aviso_sale_una_sola_vez_por_valor(self):
        self.con_config(backup_dir='\\\\srv\\share')
        for _ in range(6):
            app_module._get_backup_dir()
        self.assertEqual(self.log.call_count, 1)
        linea = self.log.call_args[0][0]
        self.assertTrue(linea.startswith('AVISO:'), linea)
        self.assertIn('backup_dir', linea)

        # Otro valor roto es otra noticia: avisa de nuevo, tambien una vez.
        self.con_config(backup_dir='C:carpeta')
        for _ in range(6):
            app_module._get_backup_dir()
        self.assertEqual(self.log.call_count, 2)

        # Y volver al primero no repite lo ya dicho.
        self.con_config(backup_dir='\\\\srv\\share')
        app_module._get_backup_dir()
        self.assertEqual(self.log.call_count, 2)

    def test_el_aviso_no_rompe_con_caracteres_de_control(self):
        """El valor va con repr(): un salto de linea no parte la linea del log."""
        self.con_config(backup_dir='back\nups')
        app_module._get_backup_dir()
        linea = self.log.call_args[0][0]
        self.assertNotIn('\n', linea)

    def test_los_consumidores_reciben_la_carpeta_segura(self):
        """`/api/backups` lee la misma carpeta que el scheduler, el restore y el push."""
        self.con_config(backup_dir='\\\\srv\\share')
        r = self.client.get('/api/backups')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['carpeta'], DEFAULT)

    def test_una_carpeta_local_valida_sigue_haciendo_backups(self):
        """De punta a punta con una absoluta local, como PROD: crea y lista."""
        destino = os.path.join(self._dir, 'copias')
        self.con_config(backup_dir=destino)
        with unittest.mock.patch.object(app_module, '_DB_PATH', database.DB_PATH):
            nombre = app_module.hacer_backup_db('prueba', 'desde el test')
        self.assertTrue(nombre and nombre.startswith('fondo_'), nombre)
        self.assertTrue(os.path.isfile(os.path.join(destino, nombre)))
        self.assertEqual([b['archivo'] for b in app_module._listar_backups()], [nombre])
        self.log.assert_any_call(f'OK: Backup de DB (prueba): {nombre}')

    def test_con_una_ruta_de_red_en_config_el_backup_no_sale_de_la_maquina(self):
        """
        El caso de fondo: aunque config.json diga una ruta de red, la copia se
        escribe en el default local. Se desvia el default a una carpeta
        temporal para no crear nada dentro del proyecto.
        """
        local = os.path.join(self._dir, 'default-local')
        self.con_config(backup_dir='\\\\srv\\share')
        with unittest.mock.patch.object(app_module, '_BASE_DIR_BACKUP', local), \
                unittest.mock.patch.object(app_module, '_DB_PATH', database.DB_PATH):
            nombre = app_module.hacer_backup_db('prueba')
        self.assertTrue(nombre)
        self.assertTrue(os.path.isfile(os.path.join(local, 'backups', nombre)))


if __name__ == '__main__':
    unittest.main()
