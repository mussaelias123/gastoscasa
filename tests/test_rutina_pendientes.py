# =============================================================================
# ARCHIVO: tests/test_rutina_pendientes.py
# =============================================================================
#
# Tests de las TAREAS del módulo Rutina (tabla rutina_pendientes): cuándo vence
# una tarea y cuándo se da por realizada sola.
#
# POR QUÉ ESTE TEST EXISTE
#   La regla de ocurrencia está escrita DOS veces: pendienteDebe() en
#   static/rutina.js (la que decide qué se ve en pantalla, porque el que sabe
#   qué día está mirando el usuario es el cliente) y _pendiente_vence() acá en
#   Python (la que usa el barrido, que escribe y no puede esperar a que alguien
#   abra el navegador). Este test congela la versión de Python: si alguien
#   cambia una de las dos y se olvida de la otra, acá salta.
#
# LA REGLA
#   La tarea del día D se ve D y D+1. Si al llegar a D+2 sigue sin tildar, se
#   da por realizada sola (fila con auto = 1) y deja de arrastrarse.
#
# CÓMO CORRER:
#   Desde la raíz del proyecto:
#       python -m unittest tests.test_rutina_pendientes -v
#
# =============================================================================

import os
import sys
import unittest
from datetime import date, timedelta

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from database import _pendiente_vence  # noqa: E402


def _tarea(**campos):
    """Una fila de rutina_pendientes con los defaults del esquema."""
    base = {'id': 1, 'titulo': 'Ir a la verdulería', 'dibujo': '',
            'repite': False, 'dias': '0000000', 'fecha': '',
            'desde': '', 'hasta': '', 'activo': True, 'responsables': []}
    base.update(campos)
    return base


# 2026-09-14 es LUNES; la semana corre hasta el domingo 2026-09-20.
LUNES = '2026-09-14'
MARTES = '2026-09-15'
VIERNES = '2026-09-18'
SABADO = '2026-09-19'
DOMINGO = '2026-09-20'


class TestVencimientoSuelta(unittest.TestCase):
    """Tarea sin repetición: vale su `fecha` y nada más."""

    def test_vence_solo_su_fecha(self):
        t = _tarea(fecha=MARTES)
        self.assertTrue(_pendiente_vence(t, MARTES))
        self.assertFalse(_pendiente_vence(t, LUNES))
        self.assertFalse(_pendiente_vence(t, VIERNES))

    def test_desde_no_le_aplica(self):
        # `desde` (la fecha de alta) acota a las repetitivas. Una suelta tiene
        # UNA fecha explícita y manda ella, aunque sea anterior al alta.
        t = _tarea(fecha=LUNES, desde=VIERNES)
        self.assertTrue(_pendiente_vence(t, LUNES))

    def test_inactiva_no_vence(self):
        t = _tarea(fecha=MARTES, activo=False)
        self.assertFalse(_pendiente_vence(t, MARTES))


class TestVencimientoRepetitiva(unittest.TestCase):
    """Tarea con repetición: 7 bits, LUNES primero (igual que las actividades)."""

    def test_lunes_a_viernes(self):
        t = _tarea(repite=True, dias='1111100', desde=LUNES)
        self.assertTrue(_pendiente_vence(t, LUNES))
        self.assertTrue(_pendiente_vence(t, VIERNES))
        self.assertFalse(_pendiente_vence(t, SABADO))
        self.assertFalse(_pendiente_vence(t, DOMINGO))

    def test_solo_finde(self):
        t = _tarea(repite=True, dias='0000011', desde=LUNES)
        self.assertFalse(_pendiente_vence(t, LUNES))
        self.assertTrue(_pendiente_vence(t, SABADO))
        self.assertTrue(_pendiente_vence(t, DOMINGO))

    def test_no_vence_antes_del_alta(self):
        # Sin esto, una tarea cargada el viernes figuraría como "no hecha" el
        # lunes de la misma semana (el selector L-D deja mirar atrás) y el
        # barrido le inventaría ocurrencias que nunca existieron.
        t = _tarea(repite=True, dias='1111111', desde=VIERNES)
        self.assertFalse(_pendiente_vence(t, LUNES))
        self.assertTrue(_pendiente_vence(t, VIERNES))

    def test_no_vence_despues_del_hasta(self):
        t = _tarea(repite=True, dias='1111111', desde=LUNES, hasta=MARTES)
        self.assertTrue(_pendiente_vence(t, MARTES))
        self.assertFalse(_pendiente_vence(t, VIERNES))

    def test_dias_mal_formado_no_vence(self):
        self.assertFalse(_pendiente_vence(
            _tarea(repite=True, dias='111', desde=LUNES), LUNES))


class TestVentanaDeArrastre(unittest.TestCase):
    """El barrido cierra lo de hace 2 días o más; lo de ayer y hoy lo deja."""

    def setUp(self):
        self.hoy = date.today()
        self.tope = (self.hoy - timedelta(days=2))

    def _dias_que_cierra(self, tarea, desde_dias, hasta_dias):
        """Los días del rango en los que el barrido SÍ actuaría."""
        cerrados = []
        for n in range(desde_dias, hasta_dias - 1, -1):
            f = (self.hoy - timedelta(days=n))
            if f <= self.tope and _pendiente_vence(tarea, f.isoformat()):
                cerrados.append(f.isoformat())
        return cerrados

    def test_ayer_y_hoy_quedan_abiertos(self):
        alta = (self.hoy - timedelta(days=10)).isoformat()
        t = _tarea(repite=True, dias='1111111', desde=alta)
        cerrados = self._dias_que_cierra(t, 3, 0)
        self.assertIn((self.hoy - timedelta(days=2)).isoformat(), cerrados)
        self.assertIn((self.hoy - timedelta(days=3)).isoformat(), cerrados)
        self.assertNotIn((self.hoy - timedelta(days=1)).isoformat(), cerrados)
        self.assertNotIn(self.hoy.isoformat(), cerrados)


if __name__ == '__main__':
    unittest.main()
