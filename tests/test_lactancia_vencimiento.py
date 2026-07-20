# =============================================================================
# ARCHIVO: tests/test_lactancia_vencimiento.py
# =============================================================================
#
# Tests del cálculo de vencimiento del módulo Lactancia (issue #48): el
# vencimiento se calcula SIEMPRE desde la extracción real (fecha + hora),
# nunca desde `cargada` (timestamp de carga en la app, solo auditoría).
#
# CÓMO CORRER:
#   Desde la raíz del proyecto:
#       python -m unittest tests.test_lactancia_vencimiento -v
#
# =============================================================================

import os
import sys
import unittest
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import (_lac_extraccion_dt, _lac_vencimiento, _lac_estado,  # noqa: E402
                 _lac_parsear_extraccion)

PARAMS = {
    'freezer_meses': 6,
    'heladera_horas': 48,
    'aviso_freezer_dias': 7,
    'aviso_heladera_horas': 12,
    'freezar_hasta_horas': 24,
}


def _heladera(fecha, hora, cargada, cierre=None):
    return {'ubicacion': 'heladera', 'fecha_extraccion': fecha,
            'hora_extraccion': hora, 'cargada': cargada,
            'motivo_cierre': cierre}


class TestExtraccionDt(unittest.TestCase):

    def test_con_hora(self):
        p = _heladera('2026-07-15', '21:39', '2026-07-19T10:00:00')
        self.assertEqual(_lac_extraccion_dt(p), datetime(2026, 7, 15, 21, 39))

    def test_sin_hora_cae_a_medianoche(self):
        # Fallback conservador (solo filas legacy): 00:00 del día de
        # extracción — nunca le regala vida útil a la leche.
        p = _heladera('2026-07-15', None, '2026-07-19T10:00:00')
        self.assertEqual(_lac_extraccion_dt(p), datetime(2026, 7, 15, 0, 0))

    def test_hora_vacia_cae_a_medianoche(self):
        p = _heladera('2026-07-15', '  ', '2026-07-19T10:00:00')
        self.assertEqual(_lac_extraccion_dt(p), datetime(2026, 7, 15, 0, 0))


class TestVencimientoHeladera(unittest.TestCase):

    def test_ignora_cargada(self):
        # Extraída el 15 a las 10:00, cargada en la app 3 días después:
        # vence extracción + 48 h, la demora en cargar NO suma vida útil.
        p = _heladera('2026-07-15', '10:00', '2026-07-18T22:00:00')
        self.assertEqual(_lac_vencimiento(p, PARAMS),
                         datetime(2026, 7, 17, 10, 0))

    def test_estado_vencida_aunque_recien_cargada(self):
        # El caso del issue #48: recién cargada pero extraída hace 3 días
        # → vencida (antes figuraba vigente por 48 h más).
        p = _heladera('2026-07-15', '10:00', '2026-07-18T22:00:00')
        ahora = datetime(2026, 7, 18, 22, 5)
        self.assertEqual(_lac_estado(p, PARAMS, ahora), 'vencida')

    def test_estado_vigente_dentro_de_ventana(self):
        p = _heladera('2026-07-18', '10:00', '2026-07-18T10:05:00')
        ahora = datetime(2026, 7, 18, 12, 0)
        self.assertEqual(_lac_estado(p, PARAMS, ahora), 'en_heladera')

    def test_estado_vence_pronto(self):
        # A menos de `aviso_heladera_horas` (12) del vencimiento.
        p = _heladera('2026-07-16', '20:00', '2026-07-16T20:05:00')
        ahora = datetime(2026, 7, 18, 10, 0)   # vence 18/7 20:00 → faltan 10 h
        self.assertEqual(_lac_estado(p, PARAMS, ahora), 'vence_pronto')

    def test_cruza_medianoche(self):
        p = _heladera('2026-07-15', '23:30', '2026-07-15T23:35:00')
        self.assertEqual(_lac_vencimiento(p, PARAMS),
                         datetime(2026, 7, 17, 23, 30))


class TestVencimientoFreezer(unittest.TestCase):

    def test_extraccion_mas_meses_fin_del_dia(self):
        p = {'ubicacion': 'freezer', 'fecha_extraccion': '2026-07-15',
             'hora_extraccion': '10:00', 'motivo_cierre': None}
        self.assertEqual(_lac_vencimiento(p, PARAMS),
                         datetime(2027, 1, 15, 23, 59, 59))


class TestParsearExtraccion(unittest.TestCase):

    def test_rechaza_extraccion_futura(self):
        futura = {'fecha_extraccion': '2099-01-01', 'hora_extraccion': '10:00'}
        with self.assertRaises(ValueError):
            _lac_parsear_extraccion(futura)

    def test_acepta_extraccion_pasada(self):
        pasada = {'fecha_extraccion': '2026-07-15', 'hora_extraccion': '10:00'}
        self.assertEqual(_lac_parsear_extraccion(pasada), ('2026-07-15', '10:00'))

    def test_rechaza_hora_invalida(self):
        with self.assertRaises(ValueError):
            _lac_parsear_extraccion({'fecha_extraccion': '2026-07-15',
                                     'hora_extraccion': '25:99'})
