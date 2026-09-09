# =============================================================================
# ARCHIVO: tests/test_lactancia_tablero.py
# =============================================================================
#
# Tests del TABLERO que arma _lac_payload(), y en particular de los dos KPIs que
# miran la ventana de los últimos 7 dias: el consumo de la semana y, derivado de
# el, para cuantos dias alcanza el stock.
#
# POR QUE EXISTE ESTE ARCHIVO: el 2026-09-09 produccion se cayo entera —todas
# las paginas, no solo Lactancia, porque el Resumen pide este payload— por un
# renombre a medias en esa cuenta del consumo semanal. Nada la cubria. Y no se
# vio en desarrollo por una razon incomoda: esa suma es un generador con filtro,
# asi que la linea SOLO se ejecuta si hay alguna bolsita usada dentro de la
# ventana. La base de dev no tenia ninguna reciente; la de casa si.
#
# De ahi la forma de estos tests: las fechas se calculan a partir de HOY, nunca
# escritas a mano. Una fecha fija envejece y en pocos dias se sale de la ventana
# —el test seguiria pasando en verde sin ejecutar la linea que cuida—, que es
# exactamente como se escapo el bug la primera vez.
#
# COMO CORRER:
#   Desde la raiz del proyecto:
#       python -m unittest tests.test_lactancia_tablero -v
#
# =============================================================================

import os
import sys
import unittest
from datetime import date, timedelta
from unittest.mock import patch

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import app  # noqa: E402


def hace(dias):
    """Fecha ISO de hace N dias. Siempre relativa a hoy: ver cabecera."""
    return (date.today() - timedelta(days=dias)).isoformat()


def partida(id, ubicacion='freezer', ml=100, cierre=None, fecha_cierre=None,
            consumido=None, jardin=0, tipo='fresca', dias_atras=1):
    """Una fila de lactancia_partidas como la devuelve la base."""
    return {'id': id, 'ubicacion': ubicacion, 'cargada': None,
            'fecha_extraccion': hace(dias_atras), 'hora_extraccion': '08:00',
            'volumen_ml': ml, 'motivo_cierre': cierre,
            'fecha_cierre': fecha_cierre, 'notas': '', 'origen_id': None,
            'actualizado': None, 'tipo': tipo, 'consumido_ml': consumido,
            'en_jardin': jardin}


def tablero(partidas):
    """El tablero que sale de _lac_payload() con estas partidas y nada mas.

    Se aisla de la base y de config.json: `cargar_config` devuelve {} y todos
    los parametros (conservacion, recordatorio, bebe) caen a sus DEFAULTS, que
    es lo que hace el modulo cuando una clave falta."""
    with patch.object(app.database, 'obtener_partidas_lactancia',
                      lambda ubicacion=None: partidas), \
         patch.object(app.config, 'cargar_config', lambda *a, **k: {}):
        return app._lac_payload()['tablero']


class TestConsumoDeLaSemana(unittest.TestCase):
    """`dias_stock` = stock usable / consumo diario promedio de los ultimos 7
    dias. Que devuelva un numero es la prueba de que la cuenta del consumo
    semanal se ejecuto de verdad: sin consumo en la ventana el KPI vale None y
    esa linea nunca corre."""

    def test_con_una_bolsita_usada_esta_semana_el_kpi_sale(self):
        # 700 ml en el freezer; ayer tomo 100 ml → 100/7 por dia → 49 dias.
        t = tablero([partida(1, ml=700),
                     partida(2, ml=100, cierre='usada', fecha_cierre=hace(1),
                             consumido=100)])
        self.assertEqual(t['dias_stock'], 49)

    def test_sin_consumo_en_la_ventana_el_kpi_queda_en_none(self):
        # Lo mismo, pero lo tomado fue hace un mes: fuera de los 7 dias.
        t = tablero([partida(1, ml=700),
                     partida(2, ml=100, cierre='usada', fecha_cierre=hace(30),
                             consumido=100)])
        self.assertIsNone(t['dias_stock'])

    def test_la_semana_usa_la_misma_regla_que_el_resto(self):
        # Sin anotar cuanto tomo, cuenta la bolsita entera (_lac_consumido).
        # 1400 ml de stock y 200 ml tomados ayer → 200/7 por dia → 49 dias.
        t = tablero([partida(1, ml=1400),
                     partida(2, ml=200, cierre='usada', fecha_cierre=hace(1),
                             consumido=None)])
        self.assertEqual(t['dias_stock'], 49)
        self.assertEqual(t['consumida_ml'], 200)

    def test_el_borde_de_la_ventana_entra(self):
        # La ventana son 7 dias contando hoy: hoy y los 6 anteriores.
        adentro = tablero([partida(1, ml=700),
                           partida(2, ml=100, cierre='usada',
                                   fecha_cierre=hace(6), consumido=100)])
        afuera = tablero([partida(1, ml=700),
                          partida(2, ml=100, cierre='usada',
                                  fecha_cierre=hace(7), consumido=100)])
        self.assertEqual(adentro['dias_stock'], 49)
        self.assertIsNone(afuera['dias_stock'])

    def test_la_heladera_tambien_cuenta_para_los_dias_de_stock(self):
        # El stock de este KPI es toda la leche que hay para tomar: freezer +
        # heladera (la del jardin ya viene contada adentro de esas dos).
        t = tablero([partida(1, ml=400),
                     partida(2, ml=300, ubicacion='heladera', dias_atras=0),
                     partida(3, ml=100, cierre='usada', fecha_cierre=hace(1),
                             consumido=100)])
        self.assertEqual(t['stock_total_ml'], 700)
        self.assertEqual(t['dias_stock'], 49)


class TestElTableroSeArmaSinDatos(unittest.TestCase):
    """Una base vacia no debe romper ninguna pagina: el Resumen pide este mismo
    payload y el primer dia de uso no hay una sola bolsita cargada."""

    def test_sin_partidas_los_kpis_van_en_cero_o_none(self):
        t = tablero([])
        self.assertEqual(t['stock_total_ml'], 0)
        self.assertEqual(t['consumida_ml'], 0)
        self.assertIsNone(t['dias_stock'])
        self.assertIsNone(t['bolsa_sugerida_ml'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
