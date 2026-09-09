# =============================================================================
# ARCHIVO: tests/test_lactancia_consumos.py
# =============================================================================
#
# Tests de _lac_consumos(): la lista de lo que TOMÓ León, la segunda fuente del
# gráfico "Explorar mis datos" del Resumen. Es la hermana de _lac_muestras: una
# mira el extremo en que la leche entra, esta el extremo en que se toma.
#
# QUÉ SE JUEGA ACÁ: dos cosas que son fáciles de equivocar y difíciles de ver.
#
#   1. LA FECHA. La que importa es la del CIERRE — el día en que se marcó la
#      bolsita como usada —, no la de extracción. Una bolsita sacada en enero y
#      tomada en marzo es leche que León tomó EN MARZO; imputarla a enero
#      dibujaría en el gráfico un consumo que ese día no existió.
#
#   2. QUÉ CUENTA. Solo las 'usada'. Una descartada se tiró y una trasladada
#      apenas cambió de lugar (de heladera a freezer, o de freezer a heladera):
#      ninguna de las dos se la tomó nadie.
#
# Y la marca del jardín, que es lo que separa lo que tomó allá de lo que tomó en
# casa. Se congela al cerrar la bolsita: después ya no se puede tocar.
#
# CÓMO CORRER:
#   Desde la raíz del proyecto:
#       python -m unittest tests.test_lactancia_consumos -v
#
# =============================================================================

import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import _lac_consumido, _lac_consumos  # noqa: E402

SIN_BEBE = {'fecha_nacimiento': ''}
CON_BEBE = {'fecha_nacimiento': '2026-05-14'}


def partida(id, fecha='2026-08-01', ml=100, cierre='usada',
            fecha_cierre='2026-08-05', consumido=None, jardin=0):
    """Una fila de lactancia_partidas como la devuelve la base."""
    return {'id': id, 'fecha_extraccion': fecha, 'hora_extraccion': '08:00',
            'volumen_ml': ml, 'tipo': 'fresca', 'motivo_cierre': cierre,
            'fecha_cierre': fecha_cierre, 'consumido_ml': consumido,
            'en_jardin': jardin}


class TestLaReglaDeCuantoTomo(unittest.TestCase):
    """_lac_consumido es la regla compartida: la usan el KPI del tablero, esta
    lista y la tabla día a día. Estaba escrita tres veces; ahora vive en un solo
    lugar, y estos tests fijan lo que dice."""

    def test_si_se_anoto_cuanto_tomo_va_ese_numero(self):
        self.assertEqual(_lac_consumido({'consumido_ml': 80, 'volumen_ml': 120}), 80)

    def test_sin_anotar_se_asume_la_bolsita_entera(self):
        self.assertEqual(_lac_consumido({'consumido_ml': None, 'volumen_ml': 120}), 120)

    def test_cero_anotado_es_cero_y_no_la_bolsita_entera(self):
        """Anotar 0 es un dato: no la tomó. Confundirlo con "no se anotó" sumaría
        120 ml que nadie tomó."""
        self.assertEqual(_lac_consumido({'consumido_ml': 0, 'volumen_ml': 120}), 0)


class TestQueCuentaComoConsumo(unittest.TestCase):

    def test_una_bolsita_usada_trae_los_ml_que_tomo(self):
        cs = _lac_consumos([partida(1, ml=120, consumido=90)], SIN_BEBE)
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs[0]['ml'], 90)

    def test_sin_anotar_los_ml_cuenta_la_bolsita_entera(self):
        """Mismo criterio que la tarjeta "Consumida por" del Resumen. Si acá
        contara cero, el gráfico mostraría días sin consumo en los que sí
        hubo."""
        cs = _lac_consumos([partida(1, ml=120, consumido=None)], SIN_BEBE)
        self.assertEqual(cs[0]['ml'], 120)

    def test_una_descartada_no_es_un_consumo(self):
        cs = _lac_consumos([partida(1, cierre='descartada')], SIN_BEBE)
        self.assertEqual(cs, [])

    def test_una_trasladada_no_es_un_consumo(self):
        """Freezar o descongelar mueve la leche de lugar, no se la toma
        nadie."""
        cs = _lac_consumos([partida(1, cierre='trasladada')], SIN_BEBE)
        self.assertEqual(cs, [])

    def test_una_bolsita_abierta_todavia_no_es_un_consumo(self):
        cs = _lac_consumos([partida(1, cierre=None, fecha_cierre=None)], SIN_BEBE)
        self.assertEqual(cs, [])


class TestLaFechaEsLaDelCierre(unittest.TestCase):

    def test_cuenta_el_dia_en_que_se_tomo_y_no_el_dia_en_que_se_saco(self):
        cs = _lac_consumos([partida(1, fecha='2026-01-10',
                                    fecha_cierre='2026-03-20')], SIN_BEBE)
        self.assertEqual(cs[0]['fecha'], '2026-03-20')

    def test_el_dia_de_la_semana_sale_de_la_fecha_de_cierre(self):
        # 2026-03-20 cae viernes → 4 (0 = lunes)
        cs = _lac_consumos([partida(1, fecha_cierre='2026-03-20')], SIN_BEBE)
        self.assertEqual(cs[0]['dia_semana'], 4)

    def test_la_edad_del_bebe_tambien_sale_de_la_fecha_de_cierre(self):
        # Nació el 14/05; el 15/05 es su día 2 de vida.
        cs = _lac_consumos([partida(1, fecha='2026-05-14',
                                    fecha_cierre='2026-05-15')], CON_BEBE)
        self.assertEqual(cs[0]['dia_vida'], 2)

    def test_sin_fecha_de_cierre_la_fila_se_saltea(self):
        """No se puede ubicar en ningún eje: mejor afuera que en una fecha
        inventada."""
        cs = _lac_consumos([partida(1, fecha_cierre=None)], SIN_BEBE)
        self.assertEqual(cs, [])


class TestLaMarcaDelJardin(unittest.TestCase):

    def test_la_bolsita_del_jardin_llega_marcada(self):
        cs = _lac_consumos([partida(1, jardin=1)], SIN_BEBE)
        self.assertIs(cs[0]['en_jardin'], True)

    def test_la_bolsita_de_casa_llega_sin_marcar(self):
        cs = _lac_consumos([partida(1, jardin=0)], SIN_BEBE)
        self.assertIs(cs[0]['en_jardin'], False)

    def test_una_bolsita_vieja_sin_la_columna_cuenta_como_de_casa(self):
        """Todo lo que se usó antes de que existiera la marca tiene la columna
        en NULL. Es el único dato que hay, y es lo más parecido a la verdad."""
        cs = _lac_consumos([partida(1, jardin=None)], SIN_BEBE)
        self.assertIs(cs[0]['en_jardin'], False)


class TestLaFormaDeCadaFila(unittest.TestCase):

    def test_trae_los_mismos_campos_que_una_muestra_mas_el_jardin(self):
        """De esto depende que los ejes horizontales del gráfico sirvan para las
        dos listas sin una línea extra."""
        cs = _lac_consumos([partida(1)], CON_BEBE)
        self.assertEqual(set(cs[0]),
                         {'id', 'fecha', 'hora', 'ml', 'en_jardin',
                          'dia_vida', 'mes_vida', 'dia_semana'})

    def test_la_hora_viaja_vacia_porque_el_cierre_no_la_guarda(self):
        """La pantalla lo usa para apagar los ejes por hora cuando se mira lo
        tomado: sin esto se elegiría una combinación que dibuja un gráfico
        vacío."""
        cs = _lac_consumos([partida(1)], SIN_BEBE)
        self.assertIsNone(cs[0]['hora'])

    def test_sin_fecha_de_nacimiento_la_edad_queda_vacia(self):
        cs = _lac_consumos([partida(1)], SIN_BEBE)
        self.assertIsNone(cs[0]['dia_vida'])
        self.assertIsNone(cs[0]['mes_vida'])


if __name__ == '__main__':
    unittest.main()
