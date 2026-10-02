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
# CÓMO CORRER:
#   python -m unittest tests.test_vendor_integridad -v
#
# =============================================================================

import base64
import hashlib
import os
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR_DIR = os.path.join(ROOT_DIR, 'static', 'vendor')

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


if __name__ == '__main__':
    unittest.main()
