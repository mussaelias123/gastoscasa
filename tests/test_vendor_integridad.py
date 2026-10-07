# =============================================================================
# ARCHIVO: tests/test_vendor_integridad.py
# =============================================================================
#
# Las librerías de terceros (flatpickr, Chart.js) se sirven desde
# static/vendor/, NUNCA desde un CDN. Este test congela que las copias sean
# exactamente las oficiales.
#
# POR QUÉ ESTE TEST EXISTE
#   Antes se cargaban de cdn.jsdelivr.net, y flatpickr encima SIN versión
#   ("la última que haya"), en TODAS las páginas. Si alguien publicaba una
#   versión maliciosa en npm —pasó varias veces en 2025—, ese código corría
#   adentro de la app, con los saldos a la vista y la sesión abierta. Ahora
#   viven en el repo, con versión fija, y este test avisa si alguien las
#   reemplaza, las "arregla" a mano o git les cambia los fines de línea.
#
# DE DÓNDE SALEN LAS HUELLAS
#   SHA-256 (en base64, el mismo formato que el atributo `integrity` de HTML)
#   de los archivos del paquete de npm, según el índice de jsDelivr
#   (data.jsdelivr.com/v1/packages/npm/<paquete>@<versión>). Al bajarlas se
#   verificó que jsDelivr y unpkg sirvieran exactamente esos bytes.
#
# CÓMO ACTUALIZAR UNA LIBRERÍA (procedimiento en docs/CONTEXT_SEGURIDAD.md):
#   carpeta nueva con la versión en el nombre, huellas nuevas acá, y recién
#   ahí cambiar las rutas en los templates. Nunca pisar la carpeta vieja.
#
# SEGUNDA MITAD DEL ARCHIVO (clase TestSinOrigenesExternos): que el CDN no
#   vuelva por la puerta de atrás. Congela que ningún template cargue un
#   <script src> ni una hoja de estilo desde un origen externo, y que todo lo
#   que se pida de static/vendor/ exista y tenga huella registrada. Sin
#   infraestructura para correr JavaScript en el repo, es la red de seguridad.
#
# CÓMO CORRER:
#   python -m unittest tests.test_vendor_integridad -v
#
# =============================================================================

import base64
import glob
import hashlib
import os
import re
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(ROOT_DIR, 'static')
VENDOR_DIR = os.path.join(STATIC_DIR, 'vendor')
TEMPLATES_DIR = os.path.join(ROOT_DIR, 'templates')

# Ruta relativa a static/vendor/ → sha256 en base64 del archivo oficial.
HUELLAS = {
    'flatpickr-4.6.13/flatpickr.min.js':  'Huqxy3eUcaCwqqk92RwusapTfWlvAasF6p2rxV6FJaE=',
    'flatpickr-4.6.13/flatpickr.min.css': 'GzSkJVLJbxDk36qko2cnawOGiqz/Y8GsQv/jMTUrx1Q=',
    'flatpickr-4.6.13/l10n/es.js':        'G5b/9Xk32jhqv0GG6ZcNalPQ+lh/ANEGLHYV6BLksIw=',
    'flatpickr-4.6.13/LICENSE.md':        'X9V6/DkFZRF1lHrkSBjpH/z1tgXkyI+sQtlwAkO9kJU=',
    'chartjs-4.4.4/chart.umd.js':         '/tanOfjQ8GhxdN5s0UdF/A/HgJFEqxE9IpCKJr8Nf+o=',
    'chartjs-4.4.4/LICENSE.md':           'QahKosq6ZF+WahjZwgVrc+bTqB2AvABGvAARomNNTM4=',
}


def _huella(ruta):
    with open(ruta, 'rb') as f:
        return base64.b64encode(hashlib.sha256(f.read()).digest()).decode('ascii')


class TestVendorIntegridad(unittest.TestCase):

    def test_cada_archivo_coincide_con_el_oficial(self):
        for relativa, esperada in HUELLAS.items():
            with self.subTest(archivo=relativa):
                ruta = os.path.join(VENDOR_DIR, *relativa.split('/'))
                self.assertTrue(os.path.isfile(ruta), f'falta static/vendor/{relativa}')
                self.assertEqual(
                    _huella(ruta), esperada,
                    f'static/vendor/{relativa} no es el archivo oficial. Si se '
                    f'actualizó la librería, seguir el procedimiento de '
                    f'docs/CONTEXT_SEGURIDAD.md; si no, alguien la modificó.')

    def test_no_hay_archivos_sin_huella(self):
        """Un archivo nuevo en vendor/ sin huella registrada es código de
        terceros que nadie verificó: el test obliga a anotarlo acá."""
        encontrados = set()
        for carpeta, _subcarpetas, archivos in os.walk(VENDOR_DIR):
            for nombre in archivos:
                relativa = os.path.relpath(os.path.join(carpeta, nombre), VENDOR_DIR)
                encontrados.add(relativa.replace(os.sep, '/'))
        self.assertEqual(encontrados, set(HUELLAS))


# =============================================================================
# SIN ORÍGENES EXTERNOS: ningún template baja código ni estilos de afuera
# =============================================================================
#
# El detector trabaja sobre el TEXTO de los templates (sin Jinja, sin levantar
# la app): busca etiquetas <script src> y <link rel=stylesheet|preload|...> cuyo
# origen sea externo. Una excepción legítima NO entra acá: el <img> del avatar
# de Google (`user_photo`) no es código ni estilo, y por eso no se mira.

# Origen externo: un esquema de red (http:, https:, ws:...) o `//host`, el
# "protocolo relativo", que hereda el esquema de la página pero igual sale del
# dominio. `data:` y `blob:` no son orígenes y quedan afuera de la regla.
_ORIGEN_EXTERNO = re.compile(r'^\s*(?:(?:https?|ftp|wss?):|//)', re.IGNORECASE)

# Los `rel` de un <link> que BAJAN algo para usarlo en la página. (icon,
# manifest y apple-touch-icon los pide el navegador o el sistema, no la página.)
_REL_QUE_CARGA = {'stylesheet', 'preload', 'modulepreload'}

# CSS que importa o referencia algo de afuera: `@import "https://..."`,
# `@import url(//...)`, `url(https://...)`. Exige el origen PEGADO a `url(` o a
# `@import`, así que un data: URI con un xmlns de w3.org adentro no lo dispara.
_CSS_EXTERNO = re.compile(
    r'(?:@import\s+(?:url\(\s*)?|url\(\s*)["\']?\s*(?:https?:|ftp:)?//', re.IGNORECASE)

# `url_for('static', filename='vendor/...')` dentro de un template.
_VENDOR_EN_TEMPLATE = re.compile(
    r"""url_for\(\s*['"]static['"]\s*,\s*filename\s*=\s*['"](vendor/[^'"]+)['"]""")


def _etiquetas(html, nombre):
    """Las etiquetas <nombre ...> enteras. Aguanta un `>` adentro de un
    atributo entre comillas (el favicon de base.html es un data: URI que
    lleva un <svg> adentro)."""
    patron = r'<' + nombre + r'\b(?:[^>"\']|"[^"]*"|\'[^\']*\')*>'
    return re.findall(patron, html, re.IGNORECASE)


def _atributo(etiqueta, nombre):
    """Valor del atributo `nombre` de una etiqueta, o None si no lo tiene.
    Acepta comillas dobles, simples o ningunas, y no confunde `src` con
    `data-src`."""
    m = re.search(
        r'(?<![\w:-])' + nombre + r'\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))',
        etiqueta, re.IGNORECASE)
    if m is None:
        return None
    return next(g for g in m.groups() if g is not None)


def cargas_externas(html):
    """Etiquetas <script src> y <link rel=stylesheet|preload|modulepreload>
    cuyo destino es un origen externo. Lista vacía = el HTML está limpio."""
    halladas = []
    for etiqueta in _etiquetas(html, 'script'):
        src = _atributo(etiqueta, 'src')
        if src is not None and _ORIGEN_EXTERNO.match(src):
            halladas.append(etiqueta)
    for etiqueta in _etiquetas(html, 'link'):
        rels = set((_atributo(etiqueta, 'rel') or '').lower().split())
        href = _atributo(etiqueta, 'href')
        if (rels & _REL_QUE_CARGA) and href is not None and _ORIGEN_EXTERNO.match(href):
            halladas.append(etiqueta)
    return halladas


def _leer(ruta):
    with open(ruta, encoding='utf-8') as f:
        return f.read()


def _templates():
    rutas = sorted(glob.glob(os.path.join(TEMPLATES_DIR, '*.html')))
    assert rutas, f'no hay templates en {TEMPLATES_DIR}: ¿cambió la carpeta?'
    return rutas


class TestSinOrigenesExternos(unittest.TestCase):

    def test_ningun_template_carga_scripts_ni_estilos_de_afuera(self):
        """
        EL test. Antes base.html bajaba flatpickr de cdn.jsdelivr.net SIN
        versión, y resumen.html / personal.html bajaban Chart.js. Ese código
        corría dentro de la app, con los saldos a la vista. Si falla: la
        librería va en static/vendor/<lib>-<versión>/ con su huella
        (docs/CONTEXT_SEGURIDAD.md), no en un <script src="https://...">.
        """
        for ruta in _templates():
            with self.subTest(template=os.path.basename(ruta)):
                self.assertEqual(
                    cargas_externas(_leer(ruta)), [],
                    f'{os.path.basename(ruta)} carga código o estilos desde un '
                    f'origen externo. Las librerías de terceros se copian a '
                    f'static/vendor/ (ver docs/CONTEXT_SEGURIDAD.md).')

    def test_ningun_css_importa_nada_de_afuera(self):
        """La otra puerta de entrada típica: Google Fonts por `@import` o
        `url(https://...)`, ya sea en style.css o en un <style> de un
        template. Las fuentes son propias, en static/fonts/."""
        rutas = sorted(glob.glob(os.path.join(STATIC_DIR, '*.css'))) + _templates()
        for ruta in rutas:
            with self.subTest(archivo=os.path.basename(ruta)):
                m = _CSS_EXTERNO.search(_leer(ruta))
                self.assertIsNone(
                    m, f'{os.path.basename(ruta)} referencia un origen externo '
                       f'desde CSS: {m.group(0) if m else ""}')

    def test_el_detector_reconoce_lo_malo_y_deja_pasar_lo_bueno(self):
        """Sin esto, una regex rota dejaría pasar el CDN y el test de arriba
        seguiría en verde para siempre."""
        malos = [
            '<script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>',
            "<script src='http://example.com/x.js'></script>",
            '<script src=//cdn.example.com/x.js></script>',
            '<SCRIPT SRC="HTTPS://CDN.EXAMPLE.COM/X.JS"></SCRIPT>',
            '<script defer\n   src="https://a.example/c.js"></script>',
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css">',
            '<link href="//fonts.googleapis.com/css2?family=Archivo" rel="stylesheet">',
            '<link rel="preload" as="script" href="https://a.example/c.js">',
        ]
        for html in malos:
            with self.subTest(html=html):
                self.assertTrue(cargas_externas(html), 'el detector no lo vio')

        buenos = [
            "<script src=\"{{ url_for('static', filename='app.js') }}?v={{ static_version }}\"></script>",
            '<script src="/static/app.js"></script>',
            '<script>var u = "https://example.com";</script>',   # inline: no baja nada
            '<script data-src="https://a.example/c.js" src="/static/x.js"></script>',
            '<link rel="stylesheet" href="/static/style.css">',
            '<link rel="manifest" href="/manifest.json">',
            '<link rel="icon" href="data:image/svg+xml,<svg xmlns=\'http://www.w3.org/2000/svg\'/>">',
            '<img src="https://lh3.googleusercontent.com/a/foto.jpg">',   # avatar: no es código
        ]
        for html in buenos:
            with self.subTest(html=html):
                self.assertEqual(cargas_externas(html), [])

        self.assertIsNotNone(_CSS_EXTERNO.search('@import url("https://fonts.googleapis.com/css2");'))
        self.assertIsNotNone(_CSS_EXTERNO.search("@import 'https://a.example/x.css';"))
        self.assertIsNotNone(_CSS_EXTERNO.search('src: url(//cdn.example.com/f.woff2);'))
        self.assertIsNone(_CSS_EXTERNO.search("src: url('fonts/archivo.woff2');"))
        self.assertIsNone(_CSS_EXTERNO.search("@import 'otro.css';"))

    def test_lo_que_los_templates_piden_de_vendor_existe_y_tiene_huella(self):
        """
        Sin JavaScript corriendo en los tests, un typo en la ruta de vendor
        (`flatpickr-4.6.13/flatpickr.min.jss`) daría un 404 silencioso: la app
        carga, pero los selectores de fecha o los gráficos no. Acá se cruza
        cada referencia con el disco y con la tabla de huellas: lo que se
        pide existe, y es una copia verificada.
        """
        referencias = {}
        for ruta in _templates():
            for relativa in _VENDOR_EN_TEMPLATE.findall(_leer(ruta)):
                referencias.setdefault(relativa, []).append(os.path.basename(ruta))

        self.assertTrue(referencias, 'ningún template pide nada de static/vendor/: '
                                     '¿volvió el CDN?')
        for relativa, donde in sorted(referencias.items()):
            with self.subTest(archivo=relativa):
                self.assertTrue(
                    os.path.isfile(os.path.join(STATIC_DIR, *relativa.split('/'))),
                    f'{donde} pide static/{relativa}, que no existe')
                self.assertIn(
                    relativa[len('vendor/'):], HUELLAS,
                    f'{donde} pide static/{relativa}, pero no tiene huella '
                    f'registrada en HUELLAS: es código de terceros sin verificar')


if __name__ == '__main__':
    unittest.main()
