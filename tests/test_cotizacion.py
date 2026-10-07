# =============================================================================
# ARCHIVO: tests/test_cotizacion.py
# =============================================================================
#
# Tests del módulo cotizacion.py. Mockean urllib.request.urlopen para no
# depender de internet ni de las APIs externas durante el testeo.
#
# QUÉ CUBREN:
#   - El parseo de siempre (valor, fecha, retroceso de días, fallback).
#   - El BLINDAJE del dato (desde 2026-10): una cotización mala no entra nunca a
#     config.json. Rechazo de 0 / negativos / NaN / infinito / booleanos / texto /
#     ausente / absurdo, el tope de ±50% contra el último valor aceptado (y su
#     excepción de arranque), el tope de 5 MB por respuesta, la fecha de la API
#     solo si es una fecha real, el histórico que ignora filas basura y
#     config.json ilegible (no se escribe nada).
#
# SIN INTERNET: las clases nuevas bloquean urlopen en el setUp con una excepción
# que NO es Exception (refrescar_cache atrapa todas las Exception y un test mal
# armado pasaría "por error" sin que nadie se entere). Cada test que necesita una
# respuesta la pone a propósito con self.api(...). Y todo corre sobre una config
# TEMPORAL: nunca se toca el config.json real.
#
# CÓMO CORRER:
#   Desde la raíz del proyecto:
#       python -m unittest tests.test_cotizacion -v
#       python -m pytest tests/test_cotizacion.py -v
#
# =============================================================================

import http.client
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock
from urllib.error import HTTPError, URLError

# Agregamos la raíz del proyecto al path para poder importar 'cotizacion'.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config  # noqa: E402
import cotizacion  # noqa: E402


def _mock_urlopen_response(payload):
    """
    Crea un context manager simulando la respuesta de urlopen.
    'payload' es un string o unos bytes (lo que se devolvería al hacer .read()).
    """
    datos = payload if isinstance(payload, bytes) else payload.encode('utf-8')
    fake_resp = mock.MagicMock()
    fake_resp.read.return_value = datos
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


# =============================================================================
# BLINDAJE DEL DATO — de acá para abajo, los tests nuevos (2026-10)
# =============================================================================

# Lo que NO puede ser una cotización, tal como lo mandaría la API (JSON).
# NaN e infinito: json.dumps los escribe como NaN / Infinity y json.loads de
# Python los vuelve a leer como float.
VENTAS_QUE_NO_SIRVEN = [
    0, 0.0, -1500, -0.5,
    float('nan'), float('inf'), float('-inf'),
    True, False, None,
    'abc', 'mil quinientos', '', '1.415,50',
    [], [1500], {},
    1e12,            # absurdo
    10_000_000,      # el tope es exclusivo: justo el tope ya no sirve
    10 ** 400,       # un entero que ni cabe en un float
]

# Config "previa" de los tests de refrescar_cache.
PREVIO_VALOR = 1000.0
PREVIO_FECHA = '2024-01-01'
PREVIO_INTENTO = '2024-01-01 00:00:00'


def _payload(venta, fecha='2026-04-18T10:00:00.000Z'):
    """El JSON que mandaría dolarapi.com con ese 'venta'."""
    return json.dumps({'venta': venta, 'fechaActualizacion': fecha})


class _InternetProhibido(BaseException):
    """
    Un test intentó salir a internet. BaseException a propósito: refrescar_cache
    atrapa todas las Exception, y con una Exception el test seguiría "pasando"
    sin haber mockeado nada.
    """


class _BaseSinInternet(unittest.TestCase):
    """urlopen bloqueado por defecto; el cache histórico limpio antes y después."""

    def setUp(self):
        cotizacion._cache_historicas = None
        self.addCleanup(setattr, cotizacion, '_cache_historicas', None)
        bloqueo = mock.patch('cotizacion.urllib.request.urlopen',
                             side_effect=_InternetProhibido('un test intentó salir a internet'))
        bloqueo.start()
        self.addCleanup(bloqueo.stop)

    def api(self, payload):
        """La API contesta `payload` (str o bytes)."""
        return mock.patch('cotizacion.urllib.request.urlopen',
                          return_value=_mock_urlopen_response(payload))

    def api_falla(self, error):
        """La API levanta `error` (una excepción de red, por ejemplo)."""
        return mock.patch('cotizacion.urllib.request.urlopen', side_effect=error)


class _BaseConfig(_BaseSinInternet):
    """Además: un config.json TEMPORAL por test (carpeta propia, para ver si quedan restos)."""

    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.carpeta = tmp.name
        self.config_path = os.path.join(self.carpeta, 'config.json')
        self.escribir_config()

    def escribir_config(self, **cambios):
        """(Re)escribe la config previa: valor 1000.0, del 2024-01-01, ok. Los `cambios` pisan claves."""
        cfg = {
            'cotizacion_valor': PREVIO_VALOR,
            'cotizacion_fecha': PREVIO_FECHA,
            'cotizacion_ultimo_intento': PREVIO_INTENTO,
            'cotizacion_ok': True,
        }
        cfg.update(cambios)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f)

    def leer_config(self):
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def refrescar(self, payload, **config_previa):
        """Config previa (la de siempre, con `config_previa` encima), la API contesta `payload`, refresca."""
        self.escribir_config(**config_previa)
        with self.api(payload):
            return cotizacion.refrescar_cache(self.config_path)

    def refrescar_con_error(self, error, **config_previa):
        """Igual que refrescar(), pero la API levanta `error`."""
        self.escribir_config(**config_previa)
        with self.api_falla(error):
            return cotizacion.refrescar_cache(self.config_path)

    def assertSinTocar(self, ok, mensaje, valor=PREVIO_VALOR, fecha=PREVIO_FECHA):
        """Un rechazo o una falla: (False, ...), valor y fecha intactos, intento anotado, ok=False."""
        self.assertFalse(ok, mensaje)
        cfg = self.leer_config()
        self.assertEqual(cfg['cotizacion_valor'], valor, mensaje)
        self.assertEqual(cfg['cotizacion_fecha'], fecha, mensaje)
        self.assertIs(cfg['cotizacion_ok'], False, mensaje)
        self.assertNotEqual(cfg['cotizacion_ultimo_intento'], PREVIO_INTENTO, mensaje)
        self.assertRegex(cfg['cotizacion_ultimo_intento'], r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$')

    def assertAceptada(self, ok, mensaje, valor, fecha='2026-04-18'):
        """Una cotización aceptada: (True, ...) y valor, fecha, intento y ok escritos."""
        self.assertTrue(ok, mensaje)
        cfg = self.leer_config()
        self.assertEqual(cfg['cotizacion_valor'], valor, mensaje)
        self.assertIsInstance(cfg['cotizacion_valor'], float)
        self.assertEqual(cfg['cotizacion_fecha'], fecha, mensaje)
        self.assertIs(cfg['cotizacion_ok'], True, mensaje)
        self.assertNotEqual(cfg['cotizacion_ultimo_intento'], PREVIO_INTENTO, mensaje)


# -----------------------------------------------------------------------------
# Los validadores solos (funciones puras)
# -----------------------------------------------------------------------------

class TestValorValido(unittest.TestCase):
    """_valor_valido(): qué es una cotización creíble."""

    def test_acepta_numeros_creibles(self):
        casos = [(1, 1.0), (1500, 1500.0), (1500.5, 1500.5), (0.0001, 0.0001),
                 (9_999_999.99, 9_999_999.99),
                 ('1450.5', 1450.5)]   # texto que es un número: se acepta, como antes
        for crudo, esperado in casos:
            with self.subTest(crudo=crudo):
                valor = cotizacion._valor_valido(crudo)
                self.assertEqual(valor, esperado)
                self.assertIsInstance(valor, float)

    def test_rechaza_lo_que_no_sirve(self):
        for crudo in VENTAS_QUE_NO_SIRVEN + [-0.0, '   ', 'nan', 'inf', 1e308]:
            with self.subTest(crudo=repr(crudo)[:30]):
                self.assertIsNone(cotizacion._valor_valido(crudo))

    def test_el_tope_de_cordura_es_exclusivo(self):
        self.assertIsNone(cotizacion._valor_valido(cotizacion.COTIZACION_MAXIMA))
        self.assertIsNotNone(cotizacion._valor_valido(cotizacion.COTIZACION_MAXIMA - 1))
        self.assertEqual(cotizacion.COTIZACION_MAXIMA, 10_000_000)


class TestFechaValida(unittest.TestCase):
    """_fecha_valida(): solo entra una fecha real de calendario."""

    def test_acepta_fechas_reales_y_se_queda_con_el_dia(self):
        casos = [('2026-04-18', '2026-04-18'),
                 ('2026-04-18T15:30:00.000Z', '2026-04-18'),
                 ('2026-04-18 15:30:00', '2026-04-18'),
                 ('2024-02-29', '2024-02-29')]          # bisiesto
        for crudo, esperado in casos:
            with self.subTest(crudo=crudo):
                self.assertEqual(cotizacion._fecha_valida(crudo), esperado)

    def test_rechaza_lo_que_no_es_una_fecha(self):
        malas = [None, '', 'ayer', '2026-13-45', '2026-02-30', '2025-02-29',
                 '0000-01-01', '18/04/2026', '2026-4-8', 20260418, ['2026-04-18'],
                 '<script>alert(1)</script>',
                 '٢٠٢٦-٠٤-١٨']   # dígitos de otro alfabeto: no es ASCII, no entra
        for crudo in malas:
            with self.subTest(crudo=repr(crudo)[:30]):
                self.assertIsNone(cotizacion._fecha_valida(crudo))

    def test_una_fecha_futura_no_entra_y_la_de_hoy_si(self):
        """Una fechaActualizacion del futuro dejaría "Al día" prendido para
        siempre. También cae acá el día UTC que ya es "mañana" después de las
        21 h de Argentina: el que llama usa la fecha local de hoy."""
        hoy = datetime.now().date()
        self.assertEqual(cotizacion._fecha_valida(hoy.isoformat()), hoy.isoformat())
        for futura in ((hoy + timedelta(days=1)).isoformat() + 'T01:00:00.000Z',
                       '2099-01-01'):
            with self.subTest(futura=futura):
                self.assertIsNone(cotizacion._fecha_valida(futura))


class TestSaltoExcesivo(unittest.TestCase):
    """_salto_excesivo() y _porcentaje(): la cuenta del ±50%."""

    def test_el_borde_exacto_se_acepta_y_un_poco_mas_se_rechaza(self):
        # (anterior, nuevo, debe_rechazarse)
        casos = [(1000.0, 1500.0, False), (1000.0, 500.0, False),
                 (1000.0, 1500.01, True), (1000.0, 499.99, True),
                 (1500.0, 2250.0, False), (1500.0, 750.0, False),
                 (1000.0, 1000.0, False)]
        for anterior, nuevo, rechaza in casos:
            with self.subTest(anterior=anterior, nuevo=nuevo):
                self.assertEqual(cotizacion._salto_excesivo(nuevo, anterior), rechaza)

    def test_el_borde_exacto_con_valores_no_redondos(self):
        """
        Con floats, 2429.76 contra 1619.84 daría 0.5000000000000001 y se
        rechazaría un +50% que es exacto. La cuenta va en Decimal.
        """
        self.assertGreater(abs(2429.76 - 1619.84) / 1619.84, 0.5)   # la trampa de los floats
        casos = [(1619.84, 2429.76, False), (1619.84, 2429.77, True),
                 (755.1, 1132.65, False), (755.1, 1132.66, True),
                 (1234.56, 617.28, False), (1234.56, 617.27, True)]
        for anterior, nuevo, rechaza in casos:
            with self.subTest(anterior=anterior, nuevo=nuevo):
                self.assertEqual(cotizacion._salto_excesivo(nuevo, anterior), rechaza)

    def test_porcentaje_con_signo_y_decimales_justos(self):
        self.assertEqual(cotizacion._porcentaje(1600.0, 1000.0), '+60.0%')
        self.assertEqual(cotizacion._porcentaje(400.0, 1000.0), '-60.0%')
        # En el borde agrega decimales para no decir "+50.0%" junto a "más del ±50%".
        self.assertEqual(cotizacion._porcentaje(1500.01, 1000.0), '+50.001%')
        self.assertEqual(cotizacion._porcentaje(1500.4, 1000.0), '+50.04%')


# -----------------------------------------------------------------------------
# obtener_cotizacion_actual(): el valor y la fecha se validan en el origen
# -----------------------------------------------------------------------------

class TestObtenerCotizacionActualBlindada(_BaseSinInternet):

    def test_rechaza_valores_que_no_sirven(self):
        for venta in VENTAS_QUE_NO_SIRVEN:
            with self.subTest(venta=repr(venta)[:30]):
                with self.api(_payload(venta)):
                    with self.assertRaises(cotizacion.CotizacionRechazada) as ctx:
                        cotizacion.obtener_cotizacion_actual()
                self.assertIsInstance(ctx.exception, ValueError)
                self.assertTrue(str(ctx.exception).startswith('Cotización rechazada:'))

    def test_rechaza_respuesta_sin_venta_o_que_no_es_un_objeto(self):
        for cuerpo in [{'compra': 1380.0, 'casa': 'oficial'}, {}, [], [1500], 'venta', 1500, None]:
            with self.subTest(cuerpo=repr(cuerpo)[:30]):
                with self.api(json.dumps(cuerpo)):
                    with self.assertRaises(cotizacion.CotizacionRechazada):
                        cotizacion.obtener_cotizacion_actual()

    def test_acepta_entero_y_texto_numerico_como_float(self):
        for venta, esperado in [(1415, 1415.0), ('1450.5', 1450.5), (9_999_999.99, 9_999_999.99)]:
            with self.subTest(venta=venta):
                with self.api(_payload(venta)):
                    resultado = cotizacion.obtener_cotizacion_actual()
                self.assertEqual(resultado['valor'], esperado)
                self.assertIsInstance(resultado['valor'], float)

    def test_fecha_invalida_de_la_api_se_reemplaza_por_hoy(self):
        malas = ['ayer', '2026-13-45', '2026-02-30T10:00:00Z', '<script>alert(1)</script>',
                 20260418, None, '', ['2026-04-18'], {'dia': '2026-04-18'}]
        for fecha in malas:
            with self.subTest(fecha=repr(fecha)[:30]):
                with self.api(_payload(1450.0, fecha)):
                    resultado = cotizacion.obtener_cotizacion_actual()
                hoy = datetime.now().strftime('%Y-%m-%d')
                self.assertEqual(resultado['fecha'], hoy)
                self.assertEqual(resultado['valor'], 1450.0)

    def test_fecha_valida_de_la_api_se_usa(self):
        with self.api(_payload(1450.0, '2026-04-18T23:59:59.000Z')):
            self.assertEqual(cotizacion.obtener_cotizacion_actual()['fecha'], '2026-04-18')


# -----------------------------------------------------------------------------
# refrescar_cache(): qué se escribe (y qué NO) en config.json
# -----------------------------------------------------------------------------

class TestRefrescarCacheValoresInvalidos(_BaseConfig):

    def test_un_valor_que_no_sirve_no_toca_la_config(self):
        for venta in VENTAS_QUE_NO_SIRVEN:
            with self.subTest(venta=repr(venta)[:30]):
                ok, mensaje = self.refrescar(_payload(venta))
                self.assertSinTocar(ok, mensaje)
                self.assertTrue(mensaje.startswith('Cotización rechazada:'), mensaje)
                self.assertIn('valor inválido', mensaje)

    def test_el_mensaje_dice_que_valor_se_rechazo(self):
        ok, mensaje = self.refrescar(_payload(0))
        self.assertIn('(0)', mensaje)
        self.assertIn('dolarapi.com', mensaje)
        self.assertIn('10.000.000', mensaje)
        ok, mensaje = self.refrescar(_payload('abc'))
        self.assertIn("('abc')", mensaje)

    def test_sin_venta_o_con_otro_formato_no_toca_la_config(self):
        for cuerpo in [{'compra': 1380.0}, [], 'texto', None]:
            with self.subTest(cuerpo=repr(cuerpo)):
                ok, mensaje = self.refrescar(json.dumps(cuerpo))
                self.assertSinTocar(ok, mensaje)
                self.assertTrue(mensaje.startswith('Cotización rechazada:'), mensaje)

    def test_el_mensaje_no_copia_texto_largo_ni_saltos_de_linea_de_la_api(self):
        """Lo que dice la API va al log y a la pantalla: se acota y no puede falsificar otra línea."""
        hostil = 'x' * 10_000 + '\n26/10/05-03:00:00 | OK: falso'
        ok, mensaje = self.refrescar(_payload(hostil))
        self.assertSinTocar(ok, mensaje)
        self.assertNotIn('\n', mensaje)
        self.assertLess(len(mensaje), 300)

    def test_un_valor_valido_con_fecha_basura_se_acepta_con_la_fecha_de_hoy(self):
        ok, mensaje = self.refrescar(_payload(1100.0, '<script>alert(1)</script>'))
        self.assertAceptada(ok, mensaje, 1100.0, fecha=datetime.now().strftime('%Y-%m-%d'))

    def test_exito_guarda_un_float_aunque_la_api_mande_entero_o_texto(self):
        for venta in [1100, '1100']:
            with self.subTest(venta=venta):
                ok, mensaje = self.refrescar(_payload(venta))
                self.assertAceptada(ok, mensaje, 1100.0)
                self.assertIn('AR$ 1100.00', mensaje)


class TestRefrescarCacheSalto(_BaseConfig):
    """El tope de ±50% contra el último valor aceptado (previo: 1000.0 del 2024-01-01)."""

    def test_mas_de_50_por_ciento_se_rechaza(self):
        for venta in [1600, 400, 1500.01, 499.99, 3000, 100, 1_000_000]:
            with self.subTest(venta=venta):
                ok, mensaje = self.refrescar(_payload(venta))
                self.assertSinTocar(ok, mensaje)
                self.assertTrue(mensaje.startswith('Cotización rechazada:'), mensaje)

    def test_hasta_50_por_ciento_inclusive_se_acepta(self):
        for venta in [1400, 600, 1500, 500, 1000, 1001, 999]:
            with self.subTest(venta=venta):
                ok, mensaje = self.refrescar(_payload(venta))
                self.assertAceptada(ok, mensaje, float(venta))

    def test_el_borde_exacto_con_valores_no_redondos(self):
        """Un +50% exacto de 1619.84 es 2429.76: se acepta; un centavo más, no."""
        casos = [(1619.84, 2429.76, True), (1619.84, 2429.77, False),
                 (755.1, 1132.65, True), (755.1, 1132.66, False),
                 (1234.56, 617.28, True), (1234.56, 617.27, False)]
        for previo, venta, se_acepta in casos:
            with self.subTest(previo=previo, venta=venta):
                ok, mensaje = self.refrescar(_payload(venta), cotizacion_valor=previo)
                if se_acepta:
                    self.assertAceptada(ok, mensaje, venta)
                else:
                    self.assertSinTocar(ok, mensaje, valor=previo)

    def test_el_mensaje_del_rechazo_dice_que_paso_y_como_destrabar(self):
        ok, mensaje = self.refrescar(_payload(1600))
        self.assertEqual(
            mensaje,
            'Cotización rechazada: dolarapi.com dio AR$ 1600.00, un cambio de +60.0% '
            'respecto de AR$ 1000.00 (más del ±50%). Si el salto es real, actualizá '
            'cotizacion_valor a mano en config.json.')
        ok, mensaje = self.refrescar(_payload(400))
        self.assertIn('AR$ 400.00', mensaje)
        self.assertIn('-60.0%', mensaje)

    def test_un_rechazo_por_salto_se_destraba_editando_cotizacion_valor(self):
        """Devaluación real de más del 50%: se edita el valor a mano y el próximo refresh ya entra."""
        ok, mensaje = self.refrescar(_payload(3000))
        self.assertSinTocar(ok, mensaje)
        # El usuario edita config.json (se lee en caliente, sin reiniciar nada).
        cfg = self.leer_config()
        cfg['cotizacion_valor'] = 2900.0
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f)
        with self.api(_payload(3000)):
            ok, mensaje = cotizacion.refrescar_cache(self.config_path)
        self.assertAceptada(ok, mensaje, 3000.0)

    def test_dos_rechazos_seguidos_no_cambian_nada(self):
        for _ in range(2):
            with self.api(_payload(3000)):
                ok, mensaje = cotizacion.refrescar_cache(self.config_path)
            self.assertSinTocar(ok, mensaje)


class TestRefrescarCacheArranque(_BaseConfig):
    """La excepción de arranque: sin una actualización exitosa previa no hay contra qué comparar."""

    def test_sin_fecha_el_primer_valor_valido_entra_sin_comparar(self):
        # El caso real de un config nuevo: DEFAULTS trae 1500.0 y fecha None.
        for fecha in [None, '']:
            for venta in [10, 3000, 9_999_999.99]:
                with self.subTest(fecha=fecha, venta=venta):
                    ok, mensaje = self.refrescar(_payload(venta), cotizacion_valor=1500.0,
                                                 cotizacion_fecha=fecha)
                    self.assertAceptada(ok, mensaje, float(venta))

    def test_sin_fecha_igual_se_exige_que_el_valor_nuevo_sirva(self):
        """La excepción saltea el control del salto, NO la validación del valor."""
        for venta in [0, -1, float('nan'), float('inf'), 'abc', 1e12]:
            with self.subTest(venta=repr(venta)):
                ok, mensaje = self.refrescar(_payload(venta), cotizacion_valor=1500.0,
                                             cotizacion_fecha=None)
                self.assertSinTocar(ok, mensaje, valor=1500.0, fecha=None)

    def test_valor_anterior_que_no_sirve_se_repara_con_el_primer_valor_valido(self):
        for previo in [0, -5, 'abc', None, float('nan'), 1e9, True, [1500]]:
            with self.subTest(previo=repr(previo)):
                ok, mensaje = self.refrescar(_payload(5000), cotizacion_valor=previo)
                self.assertAceptada(ok, mensaje, 5000.0)

    def test_despues_del_primer_exito_el_control_ya_rige(self):
        ok, mensaje = self.refrescar(_payload(1000), cotizacion_valor=1500.0, cotizacion_fecha=None)
        self.assertAceptada(ok, mensaje, 1000.0)
        with self.api(_payload(3000)):
            ok, mensaje = cotizacion.refrescar_cache(self.config_path)
        self.assertFalse(ok, mensaje)
        self.assertTrue(mensaje.startswith('Cotización rechazada:'), mensaje)
        self.assertEqual(self.leer_config()['cotizacion_valor'], 1000.0)


class TestRefrescarCacheUltimaPuerta(_BaseConfig):
    """
    refrescar_cache vuelve a validar lo que le devuelve obtener_cotizacion_actual:
    lo que entra a config.json no depende de que el origen haya validado bien.
    Sobre todo en el ARRANQUE, donde no hay ±50% que frene a un NaN o a un 0.
    """

    def _con_resultado(self, resultado, **config_previa):
        """Config previa; obtener_cotizacion_actual devuelve `resultado` (aunque sea basura); refresca."""
        self.escribir_config(**config_previa)
        with mock.patch('cotizacion.obtener_cotizacion_actual', return_value=resultado):
            return cotizacion.refrescar_cache(self.config_path)

    def test_un_resultado_invalido_del_origen_no_entra_ni_en_el_arranque(self):
        arranque = dict(cotizacion_valor=1500.0, cotizacion_fecha=None)
        for valor in [0, -1, float('nan'), float('inf'), True, None, 'abc', 1e12]:
            for previa in [dict(), arranque]:
                with self.subTest(valor=repr(valor), arranque=bool(previa)):
                    ok, mensaje = self._con_resultado({'valor': valor, 'fecha': '2026-04-18'}, **previa)
                    self.assertSinTocar(ok, mensaje,
                                        valor=previa.get('cotizacion_valor', PREVIO_VALOR),
                                        fecha=previa.get('cotizacion_fecha', PREVIO_FECHA))
                    self.assertTrue(mensaje.startswith('Cotización rechazada:'), mensaje)

    def test_una_fecha_basura_del_origen_se_reemplaza_por_hoy(self):
        hoy = datetime.now().strftime('%Y-%m-%d')
        for fecha in ['<script>alert(1)</script>', None, 20260418, '2026-13-45', '']:
            with self.subTest(fecha=repr(fecha)):
                ok, mensaje = self._con_resultado({'valor': 1100.0, 'fecha': fecha})
                self.assertAceptada(ok, mensaje, 1100.0, fecha=hoy)

    def test_el_salto_se_controla_aunque_el_valor_venga_de_otro_origen(self):
        ok, mensaje = self._con_resultado({'valor': 3000.0, 'fecha': '2026-04-18'})
        self.assertSinTocar(ok, mensaje)
        self.assertIn('+200.0%', mensaje)

    def test_un_resultado_sano_pasa_igual(self):
        ok, mensaje = self._con_resultado({'valor': 1100.0, 'fecha': '2026-04-18'})
        self.assertAceptada(ok, mensaje, 1100.0)

    def test_un_resultado_mal_armado_no_levanta(self):
        for resultado in [{'fecha': '2026-04-18'}, {}, None, 'texto']:
            with self.subTest(resultado=repr(resultado)):
                ok, mensaje = self._con_resultado(resultado)
                self.assertSinTocar(ok, mensaje)


class TestRefrescarCacheFallasDeConexion(_BaseConfig):
    """Timeout, error HTTP, JSON roto: el valor no se toca, el mensaje se entiende."""

    def test_errores_de_red_no_tocan_el_valor(self):
        errores = [
            (URLError('timeout'), 'no hubo conexión con dolarapi.com (timeout)'),
            (TimeoutError('timed out'), 'no hubo conexión con dolarapi.com (timed out)'),
            (ConnectionResetError('reset'), 'no hubo conexión con dolarapi.com'),
            (http.client.IncompleteRead(b''), 'no hubo conexión con dolarapi.com'),
            (HTTPError('https://dolarapi.com/v1/dolares/oficial', 503, 'Service Unavailable', {}, None),
             'dolarapi.com respondió con error HTTP 503'),
        ]
        for error, esperado in errores:
            with self.subTest(error=type(error).__name__):
                ok, mensaje = self.refrescar_con_error(error)
                self.assertSinTocar(ok, mensaje)
                self.assertTrue(mensaje.startswith('No se pudo actualizar la cotización:'), mensaje)
                self.assertIn(esperado, mensaje)
                self.assertIn('Se mantiene la cotización anterior', mensaje)

    def test_json_roto_o_bytes_invalidos_no_tocan_el_valor(self):
        for cuerpo in ['esto no es json', '', '{"venta": ', b'\xff\xfe\x00', '[' * 100_000]:
            with self.subTest(cuerpo=repr(cuerpo)[:20]):
                ok, mensaje = self.refrescar(cuerpo)
                self.assertSinTocar(ok, mensaje)
                self.assertTrue(mensaje.startswith('No se pudo actualizar la cotización:'), mensaje)

    def test_una_falla_inesperada_tampoco_sale_como_excepcion(self):
        ok, mensaje = self.refrescar_con_error(RuntimeError('algo raro'))
        self.assertSinTocar(ok, mensaje)
        self.assertIn('RuntimeError: algo raro', mensaje)

    def test_la_falla_no_cambia_cotizacion_valor_aunque_ya_hubiera_fallado_antes(self):
        for _ in range(3):
            ok, mensaje = self.refrescar_con_error(URLError('sin red'))
            self.assertSinTocar(ok, mensaje)


class TestRefrescarCacheTamanoDeRespuesta(_BaseConfig):
    """Se lee como mucho 5 MB: más que eso es un error y no se toca el valor."""

    TOPE = 5 * 1024 * 1024

    def _cuerpo_de(self, bytes_totales):
        """Un JSON válido ({"venta": 1450}) rellenado con espacios hasta pesar `bytes_totales`."""
        base = b'{"venta": 1450}'
        return base + b' ' * (bytes_totales - len(base))

    def test_el_tope_es_de_5_mb(self):
        self.assertEqual(cotizacion.MAX_RESPUESTA_BYTES, self.TOPE)

    def test_una_respuesta_de_mas_de_5_mb_se_rechaza(self):
        ok, mensaje = self.refrescar(self._cuerpo_de(self.TOPE + 1))
        self.assertSinTocar(ok, mensaje)
        self.assertIn('pesa más de 5 MB', mensaje)
        self.assertTrue(mensaje.startswith('No se pudo actualizar la cotización:'), mensaje)

    def test_una_respuesta_de_exactamente_5_mb_se_acepta(self):
        ok, mensaje = self.refrescar(self._cuerpo_de(self.TOPE))
        self.assertAceptada(ok, mensaje, 1450.0, fecha=datetime.now().strftime('%Y-%m-%d'))

    def test_no_se_leen_mas_de_5_mb_aunque_la_respuesta_sea_enorme(self):
        """El tope se aplica AL LEER (read(n)), no después de haber bajado todo a memoria."""

        class RespuestaMedida(io.BytesIO):
            """Respeta read(n) como el urlopen real y cuenta cuántos bytes entregó."""
            entregados = 0

            def read(self, n=-1):
                trozo = super().read(n)
                self.entregados += len(trozo)
                return trozo

        respuesta = RespuestaMedida(self._cuerpo_de(self.TOPE * 3))
        with mock.patch('cotizacion.urllib.request.urlopen', return_value=respuesta):
            with self.assertRaises(cotizacion.RespuestaDemasiadoGrande):
                cotizacion._http_get_json(cotizacion.URL_COTIZACION_ACTUAL)
        self.assertLessEqual(respuesta.entregados, self.TOPE + 1)
        self.assertGreater(respuesta.entregados, self.TOPE)   # sí leyó el byte de más que lo delata


class TestRefrescarCacheConfigIlegible(_BaseConfig):
    """config.guardar_config lanza ConfigIlegible (sin escribir) cuando config.json no se puede leer."""

    def setUp(self):
        super().setUp()
        # Sin esperas entre los reintentos de lectura: el archivo roto es de verdad.
        espera = mock.patch.object(config, '_LECTURA_ESPERA', 0)
        espera.start()
        self.addCleanup(espera.stop)

    def _romper_config(self):
        roto = b'{"cotizacion_valor": 1000.0, "cotizacion_fecha": "2024-01-0'   # cortado a la mitad
        with open(self.config_path, 'wb') as f:
            f.write(roto)
        return roto

    def assertNadaEscrito(self, roto):
        with open(self.config_path, 'rb') as f:
            self.assertEqual(f.read(), roto)
        self.assertEqual(os.listdir(self.carpeta), ['config.json'])   # ni un temporal suelto

    def test_con_la_api_bien_no_escribe_nada_y_avisa(self):
        roto = self._romper_config()
        with self.api(_payload(1100)):
            ok, mensaje = cotizacion.refrescar_cache(self.config_path)
        self.assertFalse(ok)
        self.assertIn('ilegible', mensaje)
        self.assertIn('config.json', mensaje)
        self.assertIn('No se escribió nada', mensaje)
        self.assertNadaEscrito(roto)

    def test_con_la_api_caida_no_escribe_nada_y_avisa(self):
        roto = self._romper_config()
        with self.api_falla(URLError('timeout')):
            ok, mensaje = cotizacion.refrescar_cache(self.config_path)
        self.assertFalse(ok)
        self.assertTrue(mensaje.startswith('No se pudo actualizar la cotización:'), mensaje)
        self.assertIn('config.json está ilegible', mensaje)
        self.assertNadaEscrito(roto)

    def test_con_un_valor_rechazado_no_escribe_nada_y_conserva_el_motivo(self):
        roto = self._romper_config()
        with self.api(_payload(0)):
            ok, mensaje = cotizacion.refrescar_cache(self.config_path)
        self.assertFalse(ok)
        self.assertTrue(mensaje.startswith('Cotización rechazada:'), mensaje)   # el motivo del rechazo sigue
        self.assertIn('config.json está ilegible', mensaje)
        self.assertNadaEscrito(roto)

    def test_un_archivo_que_no_es_un_objeto_json_tampoco_se_pisa(self):
        with open(self.config_path, 'wb') as f:
            f.write(b'[1, 2, 3]')
        with self.api(_payload(1100)):
            ok, mensaje = cotizacion.refrescar_cache(self.config_path)
        self.assertFalse(ok)
        self.assertIn('ilegible', mensaje)
        self.assertNadaEscrito(b'[1, 2, 3]')

    def test_guardar_config_ilegible_con_exito_de_la_api_se_intenta_una_sola_vez(self):
        """Ya se sabe que el archivo no se puede tocar: no se insiste (cada intento loguea un AVISO)."""
        error = config.ConfigIlegible('config.json ilegible: JSONDecodeError: simulado')
        with self.api(_payload(1100)), \
                mock.patch('config.guardar_config', side_effect=error) as guardar:
            ok, mensaje = cotizacion.refrescar_cache(self.config_path)
        self.assertFalse(ok)
        self.assertEqual(guardar.call_count, 1)
        self.assertIn('simulado', mensaje)

    def test_otro_error_al_escribir_no_es_una_falta_de_conexion_y_no_levanta(self):
        with self.api(_payload(1100)), \
                mock.patch('config.guardar_config', side_effect=PermissionError('bloqueado')) as guardar:
            ok, mensaje = cotizacion.refrescar_cache(self.config_path)
        self.assertFalse(ok)
        self.assertEqual(guardar.call_count, 2)   # la cotización, y el intento de anotar la falla
        self.assertIn('No se pudo guardar la cotización en config.json', mensaje)
        self.assertIn('PermissionError: bloqueado', mensaje)
        self.assertNotIn('conexión', mensaje)


# -----------------------------------------------------------------------------
# Histórico (argentinadatos.com)
# -----------------------------------------------------------------------------

class TestHistoricasBlindadas(_BaseSinInternet):

    def test_ignora_las_entradas_basura_y_se_queda_con_las_buenas(self):
        lista = [
            {'fecha': '2024-03-14', 'venta': 845.0},                  # buena
            {'fecha': '2024-03-15', 'venta': 0},                      # cero
            {'fecha': '2024-03-16', 'venta': -3},                     # negativa
            {'fecha': '2024-03-17', 'venta': float('nan')},           # NaN
            {'fecha': '2024-03-18', 'venta': float('inf')},           # infinito
            {'fecha': '2024-03-19', 'venta': 'abc'},                  # texto
            {'fecha': '2024-03-20', 'venta': True},                   # booleano
            {'fecha': '2024-03-21', 'venta': None},                   # null
            {'fecha': '2024-03-22'},                                  # sin venta
            {'fecha': '2024-03-23', 'venta': 1e12},                   # absurda
            {'venta': 900.0},                                         # sin fecha
            {'fecha': 'basura', 'venta': 900.0},                      # fecha que no es fecha
            {'fecha': '2024-13-45', 'venta': 900.0},                  # fecha imposible
            {'fecha': None, 'venta': 900.0},
            'una cadena', 42, None, [1, 2],                           # ni siquiera son objetos
            {'fecha': '2024-03-25T00:00:00', 'venta': '850.5'},       # buena: con hora y texto numérico
            {'fecha': '2024-03-26', 'venta': 860},                    # buena: entero
        ]
        with self.api(json.dumps(lista)):
            historicas = cotizacion.obtener_cotizaciones_historicas()
        self.assertEqual(historicas, {'2024-03-14': 845.0, '2024-03-25': 850.5, '2024-03-26': 860.0})

    def test_las_filas_basura_hacen_retroceder_la_busqueda_a_la_ultima_buena(self):
        lista = [{'fecha': '2024-03-14', 'venta': 845.0}, {'fecha': '2024-03-15', 'venta': 0}]
        with self.api(json.dumps(lista)):
            historicas = cotizacion.obtener_cotizaciones_historicas()
        self.assertEqual(cotizacion.cotizacion_para_fecha('2024-03-15', historicas), 845.0)

    def test_en_el_historico_no_rige_el_tope_de_50_por_ciento(self):
        """Hubo saltos reales de más de 50% de un día para otro (dic 2023: de ~366 a 800)."""
        lista = [{'fecha': '2023-12-12', 'venta': 366.5}, {'fecha': '2023-12-13', 'venta': 800.0}]
        with self.api(json.dumps(lista)):
            historicas = cotizacion.obtener_cotizaciones_historicas()
        self.assertEqual(historicas, {'2023-12-12': 366.5, '2023-12-13': 800.0})

    def test_cache_en_memoria_y_forzar_refresh(self):
        primera = json.dumps([{'fecha': '2024-03-14', 'venta': 845.0}])
        segunda = json.dumps([{'fecha': '2024-03-14', 'venta': 999.0}])
        with self.api(primera) as urlopen:
            primero = cotizacion.obtener_cotizaciones_historicas()
            repetido = cotizacion.obtener_cotizaciones_historicas()   # del cache: no vuelve a la red
            self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(primero, repetido)
        with self.api(segunda) as urlopen:
            sin_forzar = cotizacion.obtener_cotizaciones_historicas()
            self.assertEqual(urlopen.call_count, 0)
            self.assertEqual(sin_forzar['2024-03-14'], 845.0)
            forzado = cotizacion.obtener_cotizaciones_historicas(forzar_refresh=True)
            self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(forzado['2024-03-14'], 999.0)

    def test_si_la_raiz_no_es_una_lista_levanta_valueerror(self):
        with self.api(json.dumps({'fecha': '2024-03-14', 'venta': 845.0})):
            with self.assertRaises(ValueError):
                cotizacion.obtener_cotizaciones_historicas()

    def test_una_respuesta_de_mas_de_5_mb_se_rechaza(self):
        enorme = b'[' + b' ' * cotizacion.MAX_RESPUESTA_BYTES + b']'
        with self.api(enorme):
            with self.assertRaises(cotizacion.RespuestaDemasiadoGrande):
                cotizacion.obtener_cotizaciones_historicas()
        self.assertIsNone(cotizacion._cache_historicas)   # nada quedó cacheado


if __name__ == '__main__':
    unittest.main()
