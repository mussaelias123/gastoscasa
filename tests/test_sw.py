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
#     5. (etapa 3) LA LISTA BLANCA del fetch handler y el precache — ver la
#        clase TestListaBlanca, que tiene su propio porque.
#
# COMO CORRER:
#   Desde la raiz del proyecto:
#       python -m unittest tests.test_sw -v
#
# =============================================================================

import io
import os
import re
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

    def test_el_activo_si_intercepta(self):
        """
        La contracara del test de arriba. Desde la etapa 3 la mitad ACTIVO SI
        tiene fetch handler — con la lista blanca que congela la clase
        TestListaBlanca de mas abajo. Se afirma aca para que quede claro que el
        `assertNotIn` de la lapida es una decision sobre la lapida, y no una
        propiedad de todo el archivo que alguien pueda copiar sin pensar.
        """
        cuerpo = self._get(sw_enabled=True).get_data(as_text=True)
        self.assertIn("addEventListener('fetch'", cuerpo)

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


# =============================================================================
# LA LISTA BLANCA (etapa 3)
# =============================================================================
#
# POR QUE ESTOS TESTS SON DE TEXTO
#   Lo que hay que proteger no es un valor que devuelve Python: es la FORMA del
#   JavaScript que se le manda al navegador. Correrlo de verdad pediria un
#   navegador con service workers, y eso no entra en una suite de unittest.
#
#   Asi que se congela el texto servido. Suena pobre y no lo es: lo que estos
#   tests impiden es que alguien convierta la LISTA BLANCA en lista negra sin
#   que nadie se entere. Esa es LA falla que importa, porque es silenciosa:
#
#     · Lista blanca ("solo /static/"): el endpoint que se escriba manana nace
#       afuera del cache sin que nadie se acuerde de excluirlo.
#     · Lista negra ("todo menos /api/"): protege solo lo que alguien se
#       acordo de escribir. El dia que se agregue una ruta nueva, las paginas
#       —que se renderizan EN EL SERVIDOR con los saldos adentro— se pueden
#       terminar cacheando. Y un saldo viejo SE VE EXACTAMENTE IGUAL que uno
#       fresco: no hay error, no hay aviso, nadie se entera. Es lo peor que
#       puede pasar en esta app.
#
#   Si uno de estos tests falla, la pregunta NO es "como lo hago pasar": es
#   "que estoy metiendo en el cache y se puede ver la plata de ayer".
# =============================================================================


def _sin_comentarios(cuerpo):
    """
    El cuerpo servido SIN los comentarios `//`. Todo lo que este archivo
    verifica se verifica contra ESTO y no contra el texto crudo: una guarda
    escrita en un comentario no filtra nada, y este archivo tiene comentarios
    largos que nombran justo las cosas que se estan buscando (`skipWaiting`,
    `/static/`, `respondWith`). Sin esta pasada, media suite pasaria por leer
    la documentacion en vez del codigo.

    Corta en el primer `//` de cada renglon. Alcanza porque en este archivo no
    hay ningun `//` adentro de un string (las URLs son todas absolutas de un
    solo tramo, `/static/...`); si algun dia lo hubiera, hay que hacerlo mejor.
    """
    limpias = []
    for linea in cuerpo.splitlines():
        corte = linea.find('//')
        limpias.append(linea if corte == -1 else linea[:corte])
    return '\n'.join(limpias)


def _bloque_precache(cuerpo, version):
    """
    Saca la lista `PRECACHE` del sw.js YA SERVIDO y resuelve las URLs como las
    va a armar el navegador: el `'...' + VERSION` de cada renglon se concatena
    aca con la misma version que la ruta dejo en el archivo.
    """
    bloque = re.search(r'var PRECACHE = \[(.*?)\];', cuerpo, re.S)
    assert bloque, 'no se encontro la lista PRECACHE en el sw.js servido'
    urls = []
    for linea in bloque.group(1).splitlines():
        m = re.search(r"'([^']+)'(\s*\+\s*VERSION)?", linea)
        if m:
            urls.append(m.group(1) + (version if m.group(2) else ''))
    return urls


class TestListaBlanca(unittest.TestCase):

    def setUp(self):
        self.client = app_module.app.test_client()
        with unittest.mock.patch.object(config, 'cargar_config',
                                        _cfg_con(sw_enabled=True)):
            crudo = self.client.get('/sw.js').get_data(as_text=True)
        # Se mira el CODIGO, nunca los comentarios (ver `_sin_comentarios`).
        self.cuerpo = _sin_comentarios(crudo)
        version = re.search(r"var VERSION = '([^']*)'", self.cuerpo)
        self.assertIsNotNone(version, 'el SW activo tiene que declarar VERSION')
        self.version = version.group(1)

    def _pos(self, patron, que):
        m = re.search(patron, self.cuerpo)
        self.assertIsNotNone(
            m, f'FALTA LA GUARDA DE {que} en el fetch handler del SW activo. '
               f'Leer el encabezado de este bloque antes de "arreglar" el test.')
        return m.start()

    # -- 7. Las tres guardas, en el fetch handler -----------------------------

    def test_guarda_solo_get(self):
        """
        Sin esta guarda se rompe el alta de gastos, que es la funcion principal
        de la app: /agregar, /eliminar/<id> y unas 40 rutas /api/* son POST, y
        el Cache API tira excepcion con un pedido que no sea GET.
        """
        self._pos(r"\.method\s*!==\s*'GET'\s*\)\s*return\s*;", 'METODO (solo GET)')

    def test_guarda_solo_mismo_origen(self):
        """Deja afuera el CDN (flatpickr, chart.js) y el avatar de Google."""
        self._pos(r"\.origin\s*!==\s*self\.location\.origin\s*\)\s*return\s*;",
                  'ORIGEN (solo el propio)')

    def test_guarda_solo_static(self):
        """
        LA guarda. Es la que deja afuera POR CONSTRUCCION las 13 paginas (que
        llevan los saldos adentro del HTML), las 49 rutas /api/*, el manifest,
        /sw.js, el login y el CSV.
        """
        self._pos(r"\.pathname\.indexOf\('/static/'\)\s*!==\s*0\s*\)\s*return\s*;",
                  'RUTA (solo /static/)')

    def test_guarda_ninguna_navegacion(self):
        """
        Redundante hoy (una navegacion no cae bajo /static/) y a proposito: es
        la regla escrita en un renglon, por si alguien alguna vez afloja la
        guarda de la ruta.
        """
        self._pos(r"\.mode\s*===\s*'navigate'\s*\)\s*return\s*;", 'NAVEGACION')

    def test_las_guardas_van_antes_de_contestar(self):
        """
        No alcanza con que las guardas existan: tienen que correr ANTES del
        unico `respondWith`. Una guarda escrita despues no filtra nada.
        """
        respond = self.cuerpo.find('respondWith')
        self.assertNotEqual(respond, -1, 'el SW activo no contesta nada')
        for patron, que in (
                (r"\.method\s*!==\s*'GET'\s*\)\s*return\s*;", 'metodo'),
                (r"\.origin\s*!==\s*self\.location\.origin\s*\)\s*return\s*;", 'origen'),
                (r"\.pathname\.indexOf\('/static/'\)\s*!==\s*0\s*\)\s*return\s*;", 'ruta'),
                (r"\.mode\s*===\s*'navigate'\s*\)\s*return\s*;", 'navegacion')):
            with self.subTest(guarda=que):
                self.assertLess(self._pos(patron, que), respond)

    def test_un_solo_punto_de_entrada(self):
        """
        Un `respondWith` y nada mas. Con dos, las guardas de arriba dejarian de
        ser una garantia: habria un segundo camino al cache que nadie miro.
        """
        self.assertEqual(self.cuerpo.count('respondWith'), 1)

    # -- 8. El precache ------------------------------------------------------

    def test_el_precache_es_solo_de_static(self):
        """La lista blanca tambien vale para lo que se baja de entrada."""
        urls = _bloque_precache(self.cuerpo, self.version)
        self.assertTrue(urls, 'el precache no puede quedar vacio')
        for url in urls:
            with self.subTest(url=url):
                self.assertTrue(url.startswith('/static/'),
                                f'{url} no cuelga de /static/')

    def test_el_precache_matchea_letra_por_letra_lo_que_pide_la_pagina(self):
        """
        EL test que justifica el precache. La clave del cache es la URL
        COMPLETA, con query string: si el `?v=` del service worker no es
        IDENTICO al que emite base.html, el cache queda lleno de URLs que nadie
        pide y no sirve para nada — sin error, sin aviso, solo no funciona.
        """
        urls = _bloque_precache(self.cuerpo, self.version)
        html = self.client.get('/gastos').get_data(as_text=True)
        con_version = [u for u in urls if '?v=' in u]
        self.assertEqual(len(con_version), 2,
                         'tendrian que ser style.css y app.js')
        for url in con_version:
            with self.subTest(url=url):
                self.assertIn('"%s"' % url, html,
                              f'la pagina no pide {url} — el precache no matchea')

    def test_las_fuentes_van_sin_query(self):
        """
        `style.css` las pide relativas y SIN `?v=`, y un service worker no
        parsea CSS. Listadas con el `?v=` pegado serian 4 entradas de peso
        muerto: el navegador pediria otra clave.
        """
        urls = _bloque_precache(self.cuerpo, self.version)
        fuentes = [u for u in urls if '/fonts/' in u]
        self.assertEqual(len(fuentes), 4)
        for url in fuentes:
            with self.subTest(url=url):
                self.assertNotIn('?', url)

    def test_todo_lo_precacheado_existe_en_el_disco(self):
        """
        Una URL con un typo da 404 y se cae SOLO esa entrada (el install va de a
        uno, no con `addAll`), asi que la app sigue andando y nadie se entera de
        que ese archivo nunca se cachea. Este test es el unico que lo nota.
        """
        for url in _bloque_precache(self.cuerpo, self.version):
            with self.subTest(url=url):
                relativa = url.split('?')[0][len('/static/'):]
                ruta = os.path.join(ROOT_DIR, 'static', *relativa.split('/'))
                self.assertTrue(os.path.isfile(ruta), f'no existe: {ruta}')

    # -- 9. El nombre del cache y la activacion -------------------------------

    def test_el_nombre_del_cache_lleva_la_version(self):
        """
        De esto depende la frescura de todo lo que se guarda SIN `?v=` (las
        fuentes, el fondo de Lactancia): cambia cualquier archivo de static/ →
        cambia la version → cambia el nombre del cache → se tira el viejo
        entero.
        """
        self.assertIn("'nucleo-v' + VERSION", self.cuerpo)

    def test_activate_borra_los_caches_de_otras_versiones(self):
        self.assertIn('caches.delete', self.cuerpo)
        self.assertIn('clients.claim', self.cuerpo)

    def test_el_activo_no_hace_skip_waiting(self):
        """
        Decision de disenio, no olvido: con formularios de plata a medio
        llenar, activar CSS nuevo abajo de JS viejo es riesgo real, y no hace
        falta — una version nueva es cache miss y sale a la red sola. La lapida
        SI usa `skipWaiting()`, porque ahi el apuro es justo lo que se busca.
        """
        self.assertNotIn('skipWaiting', self.cuerpo)

    # -- 9. Lo que se GUARDA (la otra mitad, la que decide que entra) ---------

    def test_solo_se_guardan_respuestas_200(self):
        """
        Un 404 o un 500 guardado se serviria desde el cache hasta el proximo
        cambio de version: el archivo quedaria roto en el telefono aunque el
        servidor ya lo este sirviendo bien. Y nadie se entera, porque la app da
        200 en todas las paginas.
        """
        self.assertIn('status !== 200', self.cuerpo)

    def test_solo_se_guardan_respuestas_del_propio_origen(self):
        """`type === 'basic'` deja afuera las opacas (status 0, no se sabe si
        salieron bien) y los redirects a otro dominio, que llegan como cors."""
        self.assertIn("type !== 'basic'", self.cuerpo)

    def test_no_se_guarda_lo_que_vino_de_un_redirect(self):
        """
        POR QUE ESTE TEST: `cache.put()` usa como clave el pedido ORIGINAL. Con
        `redirect: 'follow'` (el default) un 302 al MISMO origen devuelve la
        respuesta final —status 200, type basic, pasa los dos filtros de
        arriba— y el cuerpo del DESTINO queda guardado bajo la clave /static/.

        No es teorico: sin sesion, `GET /static/` (barra final, filename vacio)
        no matchea la regla de Flask, cae en el before_request de auth y
        redirige a /login. El HTML del login quedaba cacheado como estatico.
        """
        self.assertIn('redirected', self.cuerpo)

    def test_no_se_atienden_pedidos_con_range(self):
        """
        `cache.match()` ignora el header Range: si el archivo ya esta guardado
        entero como 200, un pedido parcial recibe el 200 completo sin
        Content-Range, y un <video> se rompe al buscar. Hoy no hay media bajo
        static/, pero todo estatico nuevo entra al cache de runtime SOLO.
        """
        self.assertIn("get('range')", self.cuerpo)

    # -- 10. Invariantes de los que cuelga todo el esquema --------------------

    def test_el_activate_no_se_come_su_propio_precache(self):
        """
        POR QUE ESTE TEST: sin la exencion del cache actual, el `activate`
        borra TAMBIEN el que el `install` acaba de llenar. La app sigue andando
        —todo se recachea de a poco por runtime— y la suite sigue en verde, asi
        que el precache deja de existir EN SILENCIO: un precache muerto se ve
        igual que uno vivo, solo que todo va a la red.
        """
        self.assertRegex(self.cuerpo, r'nombre\s*===\s*CACHE')

    def test_el_match_no_ignora_el_query_string(self):
        """
        POR QUE ESTE TEST: toda la frescura cuelga de esto. Con
        `{ ignoreSearch: true }` —un cambio de una linea que suena a mejora— la
        pagina pide `style.css?v=NUEVA` y el cache le devuelve lo guardado bajo
        `?v=VIEJA`. CSS y JS viejos servidos como buenos, sin error en consola.

        Y no se destraba solo: el cache se tira recien en `activate`, que sin
        `skipWaiting()` corre cuando no queda NINGUN cliente controlado, o sea
        cerrando TODAS las pestañas del sitio.
        """
        self.assertNotIn('ignoreSearch', self.cuerpo)


if __name__ == '__main__':
    unittest.main(verbosity=2)
