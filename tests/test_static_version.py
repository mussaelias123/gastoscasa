# =============================================================================
# ARCHIVO: tests/test_static_version.py
# =============================================================================
#
# Tests de _static_version() (app.py): el número que va en el `?v=` de
# base.html y que decide cuándo el navegador se re-baja style.css y los .js.
#
# POR QUÉ ESTE TEST EXISTE
#   Esta función no la mira nadie. No tiene pantalla propia: si se rompe, la
#   app sigue levantando y todas las páginas siguen dando 200 — lo único que
#   pasa es que el navegador sirve archivos viejos, o se los re-baja todos a
#   cada rato. Se descubre tarde y desde el teléfono de otro.
#
#   Y va a empeorar: este mismo número va a ser el nombre del caché del
#   service worker. Ahí un valor que no se mueve deja a los clientes pegados a
#   una versión vieja SIN forma de destrabarlos desde el servidor. Por eso se
#   congela acá la conducta antes de que el service worker exista.
#
# LO QUE SE CONGELA
#   1. Devuelve un str de dígitos, igual al mtime más nuevo de static/.
#   2. Memo de 10 s: adentro de la ventana no se mueve; vencida, sí.
#   3. Si falla el disco devuelve la HORA, nunca un valor fijo como '0'.
#   4. Un archivo que se rompe no se lleva puestos a los demás.
#   5. Lo que no se sirve al navegador (desktop.ini, .swp) no mueve la versión.
#   6. templates/sw.js suma si está y se ignora si no.
#
# CÓMO CORRER:
#   Desde la raíz del proyecto:
#       python -m unittest tests.test_static_version -v
#
# =============================================================================

import os
import sys
import time
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import app as app_module  # noqa: E402
from app import _static_version, _STATIC_VER_TTL  # noqa: E402


def _limpiar_memo():
    """Borra el memo entre casos: si no, un test le pasa el valor al otro."""
    if hasattr(_static_version, '_memo'):
        del _static_version._memo


class TestStaticVersion(unittest.TestCase):

    def setUp(self):
        _limpiar_memo()
        self.static_original = app_module.app.static_folder
        self.base_dir_original = app_module.BASE_DIR
        self.temporales = []
        self.mtimes_tocados = {}

    def tearDown(self):
        app_module.app.static_folder = self.static_original
        app_module.BASE_DIR = self.base_dir_original
        for ruta in self.temporales:
            if os.path.exists(ruta):
                os.remove(ruta)
        for ruta, valor in self.mtimes_tocados.items():
            if os.path.exists(ruta):
                os.utime(ruta, (valor, valor))
        _limpiar_memo()

    def _crear(self, ruta, mtime=None):
        """Archivo temporal que tearDown se encarga de borrar."""
        with open(ruta, 'w', encoding='utf-8') as f:
            f.write('temporal de test')
        self.temporales.append(ruta)
        if mtime is not None:
            os.utime(ruta, (mtime, mtime))
        return ruta

    def _sin_nada_que_mirar(self):
        """
        Deja a `_static_version()` sin NINGUNA fuente: ni static/ ni
        templates/sw.js.

        POR QUE HACE FALTA TAPAR LAS DOS (cambio de la etapa 2): la función
        suma el mtime del service worker aparte del paseo por static/. Desde
        que `templates/sw.js` existe de verdad, esconder solo static/ ya no
        llega al fallback — queda el mtime del sw.js, que es un número
        perfectamente válido. Los tests del fallback tienen que sacar las dos.
        """
        inexistente = os.path.join(ROOT_DIR, 'no_existe_nada')
        app_module.app.static_folder = inexistente
        app_module.BASE_DIR = inexistente

    def _tocar(self, ruta, mtime):
        """Mueve el mtime de un archivo del repo y anota el original."""
        if ruta not in self.mtimes_tocados:
            self.mtimes_tocados[ruta] = os.path.getmtime(ruta)
        os.utime(ruta, (mtime, mtime))

    # ── 1. Valor ─────────────────────────────────────────────────────────────

    def test_devuelve_str_de_digitos(self):
        v = _static_version()
        self.assertIsInstance(v, str)
        self.assertTrue(v.isdigit(), f'no es un número: {v!r}')

    def test_coincide_con_el_mtime_mas_nuevo_de_static(self):
        """
        POR QUE ESTE TEST: la versión vieja miraba una lista de 11 archivos
        escrita a mano y no veía static/fonts/ ni static/img/. Cambiar una
        fuente no movía la versión y el navegador servía la vieja.
        """
        esperado = 0
        for carpeta, subs, archivos in os.walk(app_module.app.static_folder):
            subs[:] = [d for d in subs
                       if d != '__pycache__' and not d.startswith('.')]
            for nombre in archivos:
                if (nombre.startswith('.')
                        or nombre.lower() in ('desktop.ini', 'thumbs.db')
                        or nombre.endswith(('~', '.swp', '.bak', '.tmp'))):
                    continue
                esperado = max(esperado,
                               os.path.getmtime(os.path.join(carpeta, nombre)))

        # `templates/sw.js` cuenta aunque viva fuera de static/: editar el
        # service worker mueve el ?v= de TODOS los estáticos. Sin esta línea el
        # test falla apenas alguien toca el sw.js, que es justo lo que pasó la
        # primera vez que se lo editó después de crearlo.
        sw = os.path.join(ROOT_DIR, 'templates', 'sw.js')
        if os.path.exists(sw):
            esperado = max(esperado, os.path.getmtime(sw))

        self.assertEqual(_static_version(), str(int(esperado)))

    def test_una_fuente_mueve_la_version(self):
        """La lista vieja no miraba static/fonts/: esto no pasaba."""
        fuente = os.path.join(app_module.app.static_folder, 'fonts',
                              'parisienne-400.woff2')
        if not os.path.exists(fuente):
            self.skipTest('no está la fuente en este clon')
        base = _static_version()
        _limpiar_memo()
        self._tocar(fuente, time.time() + 5000)
        self.assertNotEqual(_static_version(), base)

    # ── 2. Memo ──────────────────────────────────────────────────────────────

    def test_dentro_de_la_ventana_no_se_mueve(self):
        base = _static_version()
        nuevo = self._crear(
            os.path.join(app_module.app.static_folder, 'zz_test.js'),
            mtime=time.time() + 9000)
        self.assertEqual(_static_version(), base,
                         'el memo no está frenando la relectura del disco')
        self.assertTrue(os.path.exists(nuevo))

    def test_vencida_la_ventana_si_se_mueve(self):
        base = _static_version()
        self._crear(os.path.join(app_module.app.static_folder, 'zz_test.js'),
                    mtime=time.time() + 9000)
        _limpiar_memo()   # equivale a que hayan pasado los 10 s
        self.assertNotEqual(_static_version(), base)

    def test_dos_llamadas_seguidas_dan_lo_mismo(self):
        """
        POR QUE ESTE TEST: si dos llamadas del mismo render difirieran, el ?v=
        de style.css y el de app.js saldrían distintos en la misma página.
        """
        self.assertEqual(_static_version(), _static_version())

    def test_el_ttl_es_un_numero_de_segundos(self):
        self.assertIsInstance(_STATIC_VER_TTL, (int, float))
        self.assertGreater(_STATIC_VER_TTL, 0)

    # ── 3. Fallback ──────────────────────────────────────────────────────────

    def test_sin_carpeta_static_devuelve_la_hora_y_nunca_cero(self):
        """
        POR QUE ESTE TEST: el fallback era '0'. Con el service worker, un '0'
        fijo deja a todos los clientes pegados a la misma versión para siempre
        y sin forma de destrabarlos desde el servidor.
        """
        self._sin_nada_que_mirar()
        v = _static_version()
        self.assertNotEqual(v, '0')
        self.assertTrue(v.isdigit())
        self.assertAlmostEqual(int(v), int(time.time()), delta=5)

    def test_el_fallback_tambien_se_memoiza(self):
        """
        POR QUE ESTE TEST: si el fallback no se memoizara, mientras durara la
        falla cada render devolvería un número distinto y el navegador se
        re-bajaría todo a cada paso. El daño no es que todos reciban la misma
        versión inventada: es que cada uno reciba una distinta.
        """
        self._sin_nada_que_mirar()
        self.assertEqual(_static_version(), _static_version())

    def test_el_fallback_avanza_al_vencer_la_ventana(self):
        """Memoizar el fallback no puede reintroducir el '0' clavado."""
        self._sin_nada_que_mirar()
        primero = _static_version()
        _limpiar_memo()
        time.sleep(1.1)
        self.assertGreater(int(_static_version()), int(primero))

    # ── 4. Un archivo roto no arrastra a los demás ───────────────────────────

    def test_un_getmtime_que_falla_no_tira_toda_la_version(self):
        """
        POR QUE ESTE TEST: un editor que guarda escribiendo un temporal y
        renombrando deja una ventana en la que el archivo se listó pero ya no
        se puede leer. Abortar el cálculo entero por uno mandaría la versión al
        fallback de la hora, y con el service worker eso es que todos los
        clientes se re-bajen el caché completo de gusto.
        """
        base = _static_version()
        _limpiar_memo()

        real = os.path.getmtime
        fantasma = os.path.join(app_module.app.static_folder, 'style.css')

        def getmtime_roto(ruta):
            if os.path.abspath(ruta) == os.path.abspath(fantasma):
                raise FileNotFoundError(ruta)
            return real(ruta)

        # El esperado se calcula, no se adivina: el mtime más nuevo del árbol
        # SALTEANDO el archivo que falla. Comparar contra el reloj sería
        # frágil — alcanza con que alguien acabe de editar un archivo para que
        # su mtime sea "ahora" y el test no distinga un mtime legítimo del
        # fallback.
        esperado = 0
        for carpeta, subs, archivos in os.walk(app_module.app.static_folder):
            subs[:] = [d for d in subs
                       if d != '__pycache__' and not d.startswith('.')]
            for nombre in archivos:
                ruta = os.path.join(carpeta, nombre)
                if os.path.abspath(ruta) == os.path.abspath(fantasma):
                    continue
                if (nombre.startswith('.')
                        or nombre.lower() in ('desktop.ini', 'thumbs.db')
                        or nombre.endswith(('~', '.swp', '.bak', '.tmp'))):
                    continue
                esperado = max(esperado, real(ruta))
        sw = os.path.join(ROOT_DIR, 'templates', 'sw.js')
        if os.path.exists(sw):
            esperado = max(esperado, real(sw))

        os.path.getmtime = getmtime_roto
        try:
            v = _static_version()
        finally:
            os.path.getmtime = real

        # No se fue al fallback: devolvió el mtime del resto del árbol.
        self.assertEqual(v, str(int(esperado)),
                         f'se fue al fallback en vez de saltear el archivo roto: {v}')
        self.assertLessEqual(int(v), int(base))

    # ── 5. Lo que no se sirve, no cuenta ─────────────────────────────────────

    def test_desktop_ini_no_mueve_la_version(self):
        """
        POR QUE ESTE TEST: corre en Windows. El Explorer deja desktop.ini en
        cualquier carpeta que se mire, y static/img/ es candidata. Cambiar la
        vista de una carpeta no puede romperle el caché a los dos teléfonos.
        """
        base = _static_version()
        _limpiar_memo()
        self._crear(os.path.join(app_module.app.static_folder, 'desktop.ini'),
                    mtime=time.time() + 9000)
        self.assertEqual(_static_version(), base)

    def test_temporal_de_editor_no_mueve_la_version(self):
        base = _static_version()
        _limpiar_memo()
        self._crear(
            os.path.join(app_module.app.static_folder, '.style.css.swp'),
            mtime=time.time() + 9000)
        self.assertEqual(_static_version(), base)

    # ── 6. templates/sw.js ───────────────────────────────────────────────────

    def test_sw_js_mueve_la_version(self):
        """
        POR QUE ESTE TEST: este mismo número es la versión que ve el service
        worker. Si editar `templates/sw.js` no moviera la versión, un service
        worker nuevo podría anunciarse con el número viejo.

        Nació en la etapa 1, cuando el archivo todavía no existía y el test lo
        creaba para probar el gancho. Desde la etapa 2 el sw.js es real: se le
        mueve el mtime al futuro y `tearDown` lo devuelve a donde estaba.
        """
        sw = os.path.join(ROOT_DIR, 'templates', 'sw.js')
        base = _static_version()
        _limpiar_memo()

        if os.path.exists(sw):
            self._tocar(sw, time.time() + 9000)
        else:
            self._crear(sw, mtime=time.time() + 9000)

        self.assertNotEqual(_static_version(), base,
                            'sw.js no se está tomando en cuenta')


if __name__ == '__main__':
    unittest.main(verbosity=2)
