# =============================================================================
# ARCHIVO: tests/test_sw.py
# =============================================================================
#
# Tests de la ruta /sw.js (app.py): el service worker y su interruptor de
# apagado.
#
# POR QUE EXISTE ESTE ARCHIVO
#   Un service worker no se des-despliega. Borrar la ruta no alcanza: el que
#   ya quedo instalado en el telefono sigue vivo, sirviendo codigo viejo, para
#   siempre. La UNICA desactivacion que llega de verdad es servir un SW que se
#   mate solo — la LAPIDA. O sea que el camino de apagado es codigo, y como
#   todo codigo se puede romper sin que nadie se entere: la app sigue dando
#   200 en todas las paginas y el problema aparece semanas despues, desde el
#   celular de otro y sin DevTools a mano.
#
#   Por eso se congelan aca las cuatro cosas de las que depende el apagado:
#     1. Con el flag apagado (el default) se sirve la lapida, y ninguna de las
#        dos mitades tiene fetch handler todavia (si lo tuviera, la app
#        dejaria de estar identica).
#     2. Con el flag prendido se sirve la OTRA mitad del archivo.
#     3. Si templates/sw.js no se puede leer, se sirve la lapida IGUAL —
#        incluso con el flag prendido. Se falla del lado seguro.
#     4. /sw.js esta fuera del login. Si cayera en el redirect, el navegador
#        recibiria el HTML del login donde espera JavaScript: no registraria
#        nada y, peor, tampoco podria llegarle nunca la lapida.
#
# COMO CORRER:
#   Desde la raiz del proyecto:
#       python -m unittest tests.test_sw -v
#
# =============================================================================

import io
import os
import sys
import unittest
import unittest.mock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import app as app_module  # noqa: E402
import config  # noqa: E402


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


class TestRutaServiceWorker(unittest.TestCase):

    def setUp(self):
        self.client = app_module.app.test_client()

    def _get(self, **flags):
        with unittest.mock.patch.object(config, 'cargar_config', _cfg_con(**flags)):
            return self.client.get('/sw.js')

    # -- 1. Apagado: la lapida, y la app identica -----------------------------

    def test_apagado_sirve_la_lapida(self):
        r = self._get(sw_enabled=False)
        cuerpo = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn('unregister', cuerpo)
        self.assertIn('caches.keys', cuerpo)

    def test_la_lapida_no_intercepta_nada(self):
        """
        EL criterio de aceptacion de la etapa 2: con el flag apagado la app
        tiene que quedar 100% igual. Un SW sin fetch handler no intercepta ni
        una request; con uno, empieza a decidir que se baja y que no.
        """
        cuerpo = self._get(sw_enabled=False).get_data(as_text=True)
        self.assertNotIn("addEventListener('fetch'", cuerpo)

    def test_el_sw_activo_todavia_no_intercepta_nada(self):
        """La otra mitad tambien esta vacia en esta etapa: el cache viene despues."""
        cuerpo = self._get(sw_enabled=True).get_data(as_text=True)
        self.assertNotIn("addEventListener('fetch'", cuerpo)

    # -- 2. Prendido: la otra mitad -------------------------------------------

    def test_prendido_sirve_la_otra_mitad(self):
        apagado = self._get(sw_enabled=False).get_data(as_text=True)
        prendido = self._get(sw_enabled=True).get_data(as_text=True)
        self.assertNotEqual(apagado, prendido)
        self.assertNotIn('unregister', prendido,
                         'el SW activo no se puede estar suicidando')

    # -- 3. Cabeceras: de esto depende que el navegador lo acepte -------------

    def test_mimetype_de_javascript(self):
        """
        Servido como text/html (o como json) el navegador rechaza el registro
        con "unsupported MIME type" y no hay service worker ni lapida.
        """
        r = self._get(sw_enabled=False)
        self.assertIn('javascript', r.headers.get('Content-Type', ''))

    def test_cache_control_sin_cachear(self):
        """
        Es la contracara del `updateViaCache: 'none'` del registro. Si el
        archivo quedara cacheado por HTTP, el chequeo de version compararia
        contra la copia vieja y el apagado podria tardar hasta 24 h.
        """
        r = self._get(sw_enabled=False)
        self.assertEqual(r.headers.get('Cache-Control'), 'no-cache')

    # -- 4. La version se reemplaza a mano, nunca con Jinja -------------------

    def test_el_marcador_de_version_se_reemplaza(self):
        for flag in (False, True):
            with self.subTest(sw_enabled=flag):
                cuerpo = self._get(sw_enabled=flag).get_data(as_text=True)
                self.assertNotIn('__VERSION__', cuerpo)
                self.assertIn(app_module._static_version(), cuerpo)

    def test_no_pasa_por_jinja(self):
        """
        `render_template` dispararia TODOS los context processors —incluido el
        de notificaciones, que son varias queries mas leer config.json— y el
        navegador re-pide /sw.js en CADA navegacion. Se prueba por el efecto:
        pedir el service worker no puede evaluar las notificaciones.
        """
        with unittest.mock.patch.object(app_module, '_notificaciones') as espia:
            self._get(sw_enabled=False)
        espia.assert_not_called()

    # -- 5. Falla segura: sin archivo, lapida igual ---------------------------

    def test_sin_archivo_sirve_la_lapida_aunque_el_flag_pida_el_sw(self):
        real_open = open

        def open_roto(archivo, *a, **k):
            if isinstance(archivo, str) and archivo.endswith('sw.js'):
                raise OSError('simulado: no se puede leer')
            return real_open(archivo, *a, **k)

        with unittest.mock.patch('builtins.open', open_roto):
            r = self._get(sw_enabled=True)

        cuerpo = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn('unregister', cuerpo,
                      'sin archivo tiene que salir la lapida, no el SW activo')

    def test_sin_marcadores_no_hay_seccion(self):
        self.assertIsNone(app_module._sw_seccion('un archivo sin marcadores', 'ACTIVO'))

    def test_archivo_mal_codificado_sirve_la_lapida_y_no_un_500(self):
        """
        POR QUE ESTE TEST: `templates/sw.js` tiene acentos y esto corre en
        Windows, donde `Set-Content` sin `-Encoding utf8` guarda en el codepage
        del sistema. Un `open(..., encoding='utf-8')` ahi tira UnicodeDecodeError,
        que NO es OSError y se escapaba del except: la ruta salia 500.

        Un 500 es PEOR que la lapida. El navegador da el chequeo de
        actualizacion por fallido y deja vivo el service worker que ya tenia
        instalado, que es justo el telefono clavado del que hay que rescatar.
        """
        real_open = open

        def open_ansi(archivo, *a, **k):
            if isinstance(archivo, str) and archivo.endswith('sw.js'):
                return io.BytesIO('// LÁPIDA en ANSI'.encode('cp1252'))
            return real_open(archivo, *a, **k)

        with unittest.mock.patch('builtins.open', open_ansi):
            r = self._get(sw_enabled=True)

        self.assertEqual(r.status_code, 200, 'un archivo mal codificado no puede dar 500')
        self.assertIn('unregister', r.get_data(as_text=True))

    def test_la_lapida_vaciada_con_los_marcadores_puestos_cae_en_la_de_emergencia(self):
        """
        POR QUE ESTE TEST: si alguien borra el cuerpo de la mitad LAPIDA pero
        deja las dos lineas de marcador (un merge mal resuelto, un editor que se
        come un bloque), `_sw_seccion` devuelve el marcador solo — un string NO
        vacio — y la guarda vieja (`if cuerpo is None`) no se disparaba.

        Resultado: se servia un /sw.js que es un comentario y nada mas. El
        navegador lo acepta, reinstala, y no pasa nada: el apagado queda roto
        EN SILENCIO, que es exactamente contra lo que se escribio la lapida.
        """
        vacia = ('// ==== INICIO LAPIDA ====\n'
                 '// ==== FIN LAPIDA ====\n')
        real_open = open

        def open_vacio(archivo, *a, **k):
            if isinstance(archivo, str) and archivo.endswith('sw.js'):
                return io.BytesIO(vacia.encode('utf-8'))
            return real_open(archivo, *a, **k)

        with unittest.mock.patch('builtins.open', open_vacio):
            r = self._get(sw_enabled=False)

        self.assertEqual(r.status_code, 200)
        self.assertIn('unregister', r.get_data(as_text=True),
                      'una lapida vaciada tiene que caer en la de emergencia')

    # -- 5b. El flag se lee con identidad estricta ----------------------------

    def test_el_flag_como_string_no_prende_el_service_worker(self):
        """
        POR QUE ESTE TEST: `sw_enabled` no tiene UI a proposito — se edita a
        mano en config.json, apurado y con la app rota. Todos los valores de
        alrededor son strings, asi que el reflejo es escribir `"false"` entre
        comillas. Un string no vacio es verdadero en Python y en Jinja, o sea
        que PRENDERIA el service worker que se queria apagar, sin ningun error
        que lo explique.

        Cualquier cosa que no sea el booleano JSON `true` tiene que caer en la
        lapida, que es el lado seguro. Mismo criterio que `auth_disabled is
        True` en auth.py.
        """
        for valor in ('false', 'False', 'off', 'no', '0', 0, None, 1, 'true'):
            with self.subTest(valor=valor):
                cuerpo = self._get(sw_enabled=valor).get_data(as_text=True)
                self.assertIn('unregister', cuerpo,
                              f'sw_enabled={valor!r} tendria que dar lapida')

    def test_solo_el_booleano_true_prende_el_service_worker(self):
        cuerpo = self._get(sw_enabled=True).get_data(as_text=True)
        self.assertNotIn('unregister', cuerpo)

    # -- 6. Fuera del login ---------------------------------------------------

    def test_el_endpoint_se_llama_service_worker(self):
        """
        En `rutas_publicas` (auth.py) van nombres de ENDPOINT, no URLs: si el
        endpoint se renombrara, la lista dejaria de cubrirlo en silencio.
        """
        nombres = [r.endpoint for r in app_module.app.url_map.iter_rules()
                   if str(r) == '/sw.js']
        self.assertEqual(nombres, ['service_worker'])

    def test_sw_js_no_pide_login_pero_el_resto_si(self):
        """
        Con el login puesto de verdad (sin bypass DEV y con OAuth configurado),
        /sw.js tiene que contestar y una pagina cualquiera tiene que redirigir.
        Las dos mitades importan: sin la segunda, el test pasaria igual si el
        login estuviera apagado y no probaria nada.
        """
        con_login = _cfg_con(auth_disabled=False,
                             google_client_id='x', google_client_secret='y')
        with unittest.mock.patch.object(config, 'cargar_config', con_login):
            sw = self.client.get('/sw.js')
            pagina = self.client.get('/gastos')

        self.assertEqual(sw.status_code, 200)
        self.assertIn('javascript', sw.headers.get('Content-Type', ''))
        self.assertEqual(pagina.status_code, 302)


if __name__ == '__main__':
    unittest.main(verbosity=2)
