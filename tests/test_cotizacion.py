# =============================================================================
# ARCHIVO: tests/test_cotizacion.py
# =============================================================================
#
# Tests del módulo cotizacion.py. Mockean urllib.request.urlopen para no
# depender de internet ni de las APIs externas durante el testeo.
#
# CÓMO CORRER:
#   Desde la raíz del proyecto:
#       python -m unittest tests.test_cotizacion -v
#
# =============================================================================

import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from urllib.error import URLError

# Agregamos la raíz del proyecto al path para poder importar 'cotizacion'.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import cotizacion  # noqa: E402


def _mock_urlopen_response(payload):
    """
    Crea un context manager simulando la respuesta de urlopen.
    'payload' debe ser un string (lo que se devolvería al hacer .read().decode()).
    """
    fake_resp = mock.MagicMock()
    fake_resp.read.return_value = payload.encode('utf-8')
    fake_resp.__enter__.return_value = fake_resp
    fake_resp.__exit__.return_value = False
    return fake_resp


class TestObtenerCotizacionActual(unittest.TestCase):
    """Tests de obtener_cotizacion_actual()."""

    def setUp(self):
        # Limpiamos el cache entre tests para que no haya interferencia.
        cotizacion._cache_historicas = None

    def test_parsea_respuesta_correcta(self):
        """Si la API responde 200 con JSON válido, retorna {valor, fecha}."""
        payload = json.dumps({
            'compra': 1380.0,
            'venta': 1420.5,
            'casa': 'oficial',
            'nombre': 'Oficial',
            'fechaActualizacion': '2026-04-18T15:30:00.000Z',
        })
        with mock.patch('cotizacion.urllib.request.urlopen',
                        return_value=_mock_urlopen_response(payload)):
            resultado = cotizacion.obtener_cotizacion_actual()

        self.assertEqual(resultado['valor'], 1420.5)
        self.assertEqual(resultado['fecha'], '2026-04-18')

    def test_lanza_excepcion_si_api_falla(self):
        """Si urlopen lanza URLError, la excepción se propaga."""
        with mock.patch('cotizacion.urllib.request.urlopen',
                        side_effect=URLError('conexión rechazada')):
            with self.assertRaises(URLError):
                cotizacion.obtener_cotizacion_actual()

    def test_lanza_excepcion_si_json_invalido(self):
        """Si la respuesta no es JSON válido, levanta JSONDecodeError."""
        with mock.patch('cotizacion.urllib.request.urlopen',
                        return_value=_mock_urlopen_response('esto no es json')):
            with self.assertRaises(json.JSONDecodeError):
                cotizacion.obtener_cotizacion_actual()

    def test_lanza_excepcion_si_falta_venta(self):
        """Si el JSON no tiene la clave 'venta', levanta ValueError."""
        payload = json.dumps({'compra': 1380.0, 'casa': 'oficial'})
        with mock.patch('cotizacion.urllib.request.urlopen',
                        return_value=_mock_urlopen_response(payload)):
            with self.assertRaises(ValueError):
                cotizacion.obtener_cotizacion_actual()

    def test_usa_fecha_de_hoy_si_falta_fecha_actualizacion(self):
        """Si no viene fechaActualizacion, retorna la fecha de hoy."""
        from datetime import datetime
        payload = json.dumps({'venta': 1500.0})
        with mock.patch('cotizacion.urllib.request.urlopen',
                        return_value=_mock_urlopen_response(payload)):
            resultado = cotizacion.obtener_cotizacion_actual()

        hoy = datetime.now().strftime('%Y-%m-%d')
        self.assertEqual(resultado['fecha'], hoy)
        self.assertEqual(resultado['valor'], 1500.0)


class TestCotizacionParaFecha(unittest.TestCase):
    """Tests de cotizacion_para_fecha()."""

    def test_fecha_exacta_existe(self):
        """Si la fecha está en el dict, retorna su valor."""
        historicas = {
            '2024-03-15': 850.0,
            '2024-03-14': 845.0,
        }
        valor = cotizacion.cotizacion_para_fecha('2024-03-15', historicas)
        self.assertEqual(valor, 850.0)

    def test_retrocede_dias_cuando_no_existe(self):
        """Si la fecha no está, retrocede día a día y devuelve la primera válida."""
        historicas = {
            '2024-03-12': 840.0,  # esta sí
        }
        # Pedimos 2024-03-15 (sábado): debe retroceder 3 días hasta el 12.
        valor = cotizacion.cotizacion_para_fecha('2024-03-15', historicas)
        self.assertEqual(valor, 840.0)

    def test_retrocede_solo_un_dia(self):
        """Verifica que con un solo día de diferencia funcione."""
        historicas = {'2024-06-09': 1100.0}
        valor = cotizacion.cotizacion_para_fecha('2024-06-10', historicas)
        self.assertEqual(valor, 1100.0)

    def test_retorna_none_si_pasa_limite(self):
        """Si retrocede más de 10 días sin encontrar, retorna None."""
        historicas = {'2024-01-01': 800.0}
        # Pedimos 2024-02-01: están a 31 días → fuera del límite de 10.
        valor = cotizacion.cotizacion_para_fecha('2024-02-01', historicas)
        self.assertIsNone(valor)

    def test_acepta_fecha_con_hora(self):
        """Si llega 'YYYY-MM-DD...' con sufijo extra, igual lo parsea."""
        historicas = {'2024-05-20': 950.0}
        valor = cotizacion.cotizacion_para_fecha('2024-05-20T12:00:00', historicas)
        self.assertEqual(valor, 950.0)


class TestRefrescarCache(unittest.TestCase):
    """Tests de refrescar_cache()."""

    def setUp(self):
        # Creamos un config.json temporal por test.
        self.tmp = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8'
        )
        # Estado inicial con un valor previo conocido.
        json.dump({
            'cotizacion_valor': 1000.0,
            'cotizacion_fecha': '2024-01-01',
            'cotizacion_ultimo_intento': None,
            'cotizacion_ok': True,
        }, self.tmp)
        self.tmp.close()
        self.config_path = self.tmp.name

    def tearDown(self):
        try:
            os.unlink(self.config_path)
        except OSError:
            pass

    def _leer_config(self):
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def test_actualiza_en_caso_de_exito(self):
        """En caso de éxito, escribe valor, fecha, intento y ok=True."""
        payload = json.dumps({
            'venta': 1450.0,
            'fechaActualizacion': '2026-04-18T10:00:00.000Z',
        })
        with mock.patch('cotizacion.urllib.request.urlopen',
                        return_value=_mock_urlopen_response(payload)):
            ok, mensaje = cotizacion.refrescar_cache(self.config_path)

        self.assertTrue(ok)
        cfg = self._leer_config()
        self.assertEqual(cfg['cotizacion_valor'], 1450.0)
        self.assertEqual(cfg['cotizacion_fecha'], '2026-04-18')
        self.assertTrue(cfg['cotizacion_ok'])
        self.assertIsNotNone(cfg['cotizacion_ultimo_intento'])
        self.assertIn('1450', mensaje)

    def test_mantiene_valor_anterior_en_caso_de_fallo(self):
        """En caso de fallo, NO toca cotizacion_valor; solo marca ok=False."""
        with mock.patch('cotizacion.urllib.request.urlopen',
                        side_effect=URLError('timeout')):
            ok, mensaje = cotizacion.refrescar_cache(self.config_path)

        self.assertFalse(ok)
        cfg = self._leer_config()
        # El valor previo (1000.0) se preserva como fallback.
        self.assertEqual(cfg['cotizacion_valor'], 1000.0)
        self.assertEqual(cfg['cotizacion_fecha'], '2024-01-01')
        self.assertFalse(cfg['cotizacion_ok'])
        self.assertIsNotNone(cfg['cotizacion_ultimo_intento'])
        self.assertIn('No se pudo', mensaje)


if __name__ == '__main__':
    unittest.main()
