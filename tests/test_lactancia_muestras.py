# =============================================================================
# ARCHIVO: tests/test_lactancia_muestras.py
# =============================================================================
#
# Tests de _lac_muestras(): la lista de extracciones que alimenta el gráfico
# "Explorar mis datos" del Resumen.
#
# QUÉ SE JUEGA ACÁ: la honestidad del gráfico. En la base hay filas que NO son
# extracciones nuevas — cuando se juntan bolsitas de heladera y se freezan nace
# una fila con la MISMA leche (tipo 'congelada'), y cuando se baja una del
# freezer a descongelar, otra (tipo 'descongelada'). Si esas filas contaran como
# extracciones, los mismos mililitros aparecerían dos y tres veces y el gráfico
# mostraría una producción que nunca existió.
#
# La regla que fijan estos tests: una muestra = una vez que se sacó leche.
# Es el mismo criterio de _lac_dia_a_dia (la tabla que se descarga).
#
# CÓMO CORRER:
#   Desde la raíz del proyecto:
#       python -m unittest tests.test_lactancia_muestras -v
#
# =============================================================================

import os
import sys
import unittest
from datetime import date, timedelta

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import _lac_muestras  # noqa: E402

SIN_BEBE = {'fecha_nacimiento': ''}


def partida(id, fecha, hora='08:00', ml=100, tipo='fresca', cierre=None):
    """Una fila de lactancia_partidas como la devuelve la base."""
    return {'id': id, 'fecha_extraccion': fecha, 'hora_extraccion': hora,
            'volumen_ml': ml, 'tipo': tipo, 'motivo_cierre': cierre}


class TestUnaMuestraEsUnaExtraccion(unittest.TestCase):

    def test_una_extraccion_trae_su_hora_y_sus_ml(self):
        ms = _lac_muestras([partida(1, '2026-08-05', '07:30', 120)], SIN_BEBE)
        self.assertEqual(len(ms), 1)
        self.assertEqual(ms[0]['hora'], '07:30')
        self.assertEqual(ms[0]['ml'], 120)
        self.assertEqual(ms[0]['fecha'], '2026-08-05')

    def test_la_bolsa_freezada_no_es_una_extraccion_nueva(self):
        """Combinar dos de heladera en una de freezer es la misma leche
        cambiando de lugar: la hija ('congelada') no cuenta."""
        filas = [
            partida(1, '2026-08-05', ml=100, cierre='trasladada'),
            partida(2, '2026-08-05', ml=60, cierre='trasladada'),
            partida(3, '2026-08-05', ml=160, tipo='congelada'),   # la hija
        ]
        ms = _lac_muestras(filas, SIN_BEBE)
        self.assertEqual(len(ms), 2)
        self.assertEqual(sum(m['ml'] for m in ms), 160,
                         'los mismos ml se contaron dos veces')

    def test_la_bolsa_bajada_a_descongelar_tampoco(self):
        filas = [
            partida(1, '2026-08-05', ml=90, cierre='trasladada'),
            partida(2, '2026-08-05', ml=90, tipo='descongelada'),
        ]
        ms = _lac_muestras(filas, SIN_BEBE)
        self.assertEqual(len(ms), 1)
        self.assertEqual(ms[0]['ml'], 90)

    def test_una_bolsita_usada_o_descartada_sigue_contando(self):
        """Se mira lo que se produjo, no lo que queda guardado."""
        filas = [partida(1, '2026-08-05', ml=80, cierre='usada'),
                 partida(2, '2026-08-05', ml=50, cierre='descartada')]
        ms = _lac_muestras(filas, SIN_BEBE)
        self.assertEqual(len(ms), 2)
        self.assertEqual(sum(m['ml'] for m in ms), 130)

    def test_una_fila_sin_tipo_cuenta_como_fresca(self):
        """Las bolsitas cargadas antes de que existiera la columna `tipo` la
        tienen vacía: si no contaran, esa producción desaparecería."""
        ms = _lac_muestras([partida(1, '2026-08-05', ml=110, tipo=None)], SIN_BEBE)
        self.assertEqual(len(ms), 1)
        self.assertEqual(ms[0]['ml'], 110)

    def test_sin_ninguna_partida_la_lista_viene_vacia(self):
        self.assertEqual(_lac_muestras([], SIN_BEBE), [])


class TestEdadDelBebeEnCadaMuestra(unittest.TestCase):

    def test_sin_fecha_de_nacimiento_la_edad_queda_vacia(self):
        m = _lac_muestras([partida(1, '2026-08-05')], SIN_BEBE)[0]
        self.assertIsNone(m['dia_vida'])
        self.assertIsNone(m['mes_vida'])

    def test_el_dia_del_parto_es_el_dia_1_y_el_mes_1(self):
        """Así se cuenta en pediatría, y es lo que ya hace la tabla día a día."""
        m = _lac_muestras([partida(1, '2026-05-14')],
                          {'fecha_nacimiento': '2026-05-14'})[0]
        self.assertEqual(m['dia_vida'], 1)
        self.assertEqual(m['mes_vida'], 1)

    def test_diez_dias_despues_del_parto_es_el_dia_11(self):
        m = _lac_muestras([partida(1, '2026-05-24')],
                          {'fecha_nacimiento': '2026-05-14'})[0]
        self.assertEqual(m['dia_vida'], 11)
        self.assertEqual(m['mes_vida'], 1)

    def test_el_mes_cambia_el_mismo_numero_de_dia(self):
        m = _lac_muestras([partida(1, '2026-06-14')],
                          {'fecha_nacimiento': '2026-05-14'})[0]
        self.assertEqual(m['mes_vida'], 2)


class TestDatosQueElGraficoNecesita(unittest.TestCase):

    def test_el_dia_de_la_semana_va_de_lunes_cero_a_domingo_seis(self):
        """El gráfico ordena los días con este número: si cambiara, el eje
        quedaría con los días en cualquier orden."""
        # 2026-08-05 es miércoles
        m = _lac_muestras([partida(1, '2026-08-05')], SIN_BEBE)[0]
        self.assertEqual(m['dia_semana'], 2)

    def test_una_extraccion_sin_hora_no_rompe_nada(self):
        """La app la pide siempre, pero en la base puede faltar: la muestra
        existe igual, sin hora (el gráfico por hora la deja afuera sola)."""
        m = _lac_muestras([partida(1, '2026-08-05', hora=None)], SIN_BEBE)[0]
        self.assertIsNone(m['hora'])
        self.assertEqual(m['ml'], 100)

    def test_una_fecha_invalida_se_saltea_sin_reventar(self):
        filas = [partida(1, 'no-es-una-fecha'), partida(2, '2026-08-05')]
        ms = _lac_muestras(filas, SIN_BEBE)
        self.assertEqual(len(ms), 1)
        self.assertEqual(ms[0]['id'], 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
