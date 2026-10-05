# =============================================================================
# ARCHIVO: tests/test_validacion_movimientos.py
# =============================================================================
#
# Tests de lo que ACEPTAN /agregar y /editar (app.py → _leer_movimiento_form),
# de la red de seguridad de la cotizacion (_calcular_monto_usd) y del
# serializado de los gastos fijos en /gastos y en el Inicio.
#
# POR QUE EXISTE ESTE ARCHIVO
#
#   1. LA ENTRADA SE GUARDABA TAL CUAL. Las dos rutas no validaban nada:
#      `monto=1e999` es un infinito valido para float() y se guardaba; despues
#      `fmt_ars` tiraba OverflowError y el Inicio y /gastos quedaban en 500
#      hasta borrar esa fila a mano desde la base. Tambien entraban personas,
#      monedas y tipos inventados, montos negativos, una fecha con comillas y
#      HTML, y una categoria con etiquetas. La falla es de las que no se ven
#      mirando la pantalla hasta que un dia no abre.
#      Cada regla tiene su caso aca, y TODOS comprueban lo mismo: 400 con
#      mensaje y NADA escrito en la base. Que el mensaje salga y que la base
#      quede intacta son dos cosas distintas: una ruta que valida despues de
#      insertar pasaria el primer chequeo y dejaria la fila mala igual.
#
#   2. LA COTIZACION AUSENTE NO PUEDE GUARDAR UN USD FALSO. Antes, una
#      cotizacion 0 o ausente usaba 1.0 en silencio y el movimiento quedaba con
#      un monto_usd mentiroso para siempre (AR$ 1.500.000 como USD 1.500.000).
#      Ahora lanza ValueError, y los tests miran los CAMINOS: /agregar, un
#      cambio (donde la segunda conversion falla DESPUES de la primera y no
#      puede quedar medio cambio escrito) y /editar (donde la llamada estaba
#      fuera del try y un ValueError terminaba en 500).
#
#   3. `</script>` EN UN GASTO FIJO. `_gastos_fijos_json()` devolvia un string
#      de json.dumps y el template lo imprimia con `| safe` dentro de un
#      <script>: un gasto fijo llamado `</script><script>alert(1)</script>`
#      cerraba el script y ejecutaba codigo en /gastos y en el Inicio. Aca se
#      mira el HTML SERVIDO, no el camino: si el texto crudo llega al
#      navegador, el test se pone rojo sin importar por donde se colo.
#
#   Todos los tests son HERMETICOS: base temporal, config parcheada (nunca se
#   toca el config.json de la maquina) y login explicito por sesion. No
#   dependen del bypass DEV ni de que la app este abierta.
#
# COMO CORRER:
#   Desde la raiz del proyecto:
#       python -m unittest tests.test_validacion_movimientos -v
#
# =============================================================================

import json
import math
import os
import re
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from urllib.parse import urlsplit

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import app as app_module  # noqa: E402
import config  # noqa: E402
import database  # noqa: E402

ELIAS = 'mussaelias123@gmail.com'
AJAX = {'X-Requested-With': 'XMLHttpRequest'}

# La funcion de verdad, capturada al importar (antes de que ningun test la
# parchee). `_cfg_con` siempre arma sobre ESTA y no sobre la que este parchada
# en ese momento: asi se puede re-parchear dentro de un test sin encadenar.
_CARGAR_REAL = config.cargar_config
_AUSENTE = object()


def _cfg_con(**cambios):
    """
    La config de verdad con lo imprescindible pisado, mas lo que se pida.

    Se parchea la FUNCION y no el archivo, para no tocar el config.json de la
    maquina. Lo fijo: OAuth "configurado" y bypass DEV apagado (asi el login
    se exige de verdad), una cotizacion y un factor conocidos (asi los montos
    en USD son predecibles). `_AUSENTE` como valor BORRA la clave.
    """
    def falso(ruta=None):
        cfg = _CARGAR_REAL(ruta)
        cfg.update({
            'google_client_id': 'id',
            'google_client_secret': 's',
            'auth_disabled': False,
            'ngrok_enabled': False,
            'cotizacion_valor': 1000.0,
            'factor_sueldo': 0.7,
        })
        for clave, valor in cambios.items():
            if valor is _AUSENTE:
                cfg.pop(clave, None)
            else:
                cfg[clave] = valor
        return cfg

    return falso


def _form(**cambios):
    """
    Un alta valida de gasto en pesos. Cada argumento pisa un campo; `None`
    BORRA el campo (asi se prueba el "campo ausente", que no es lo mismo que
    el campo vacio).
    """
    datos = {
        'fecha': '2026-09-15',
        'descripcion': 'Supermercado',
        'persona': 'elias',
        'moneda': 'ars',
        'tipo': 'gasto',
        'monto': '15000',
        'categoria': 'Comida y bebida',
    }
    for campo, valor in cambios.items():
        if valor is None:
            datos.pop(campo, None)
        else:
            datos[campo] = valor
    return datos


def _form_cambio(**cambios):
    """Un cambio valido: AR$ 150.000 -> USD 100, de Elias a Mari."""
    base = dict(tipo='cambio', categoria=None, monto='150000',
                persona_final='mari', moneda_final='usd', monto_final='100')
    base.update(cambios)
    return _form(**base)


class BaseMovimientos(unittest.TestCase):
    """
    Cada test arranca con una base temporal vacia, la config parcheada y una
    sesion de Elias. Es una base SQLite real en archivo, no mocks: lo que se
    prueba es que la fila NO queda escrita, y un mock de la capa de datos no
    puede decir eso.
    """

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix='fondo-movimientos-')
        self._db_original = database.DB_PATH
        database.DB_PATH = os.path.join(self._dir, 'fondo.db')
        database.inicializar_db()
        self.client = app_module.app.test_client()
        self.con_config()
        self.login()

    def tearDown(self):
        database.DB_PATH = self._db_original
        shutil.rmtree(self._dir, ignore_errors=True)

    # -- Atajos -------------------------------------------------------------

    def con_config(self, **cambios):
        """Parcha cargar_config hasta el final del test. Se puede repetir."""
        parche = unittest.mock.patch.object(
            config, 'cargar_config', _cfg_con(**cambios))
        parche.start()
        self.addCleanup(parche.stop)

    def login(self, email=ELIAS):
        with self.client.session_transaction() as sesion:
            sesion['user_email'] = email
            sesion['user_name'] = 'Elias'

    def post_agregar(self, ajax=True, datos=None, **cambios):
        datos = _form(**cambios) if datos is None else datos
        return self.client.post('/agregar', data=datos,
                                headers=AJAX if ajax else {})

    def post_editar(self, mov_id, **cambios):
        return self.client.post(f'/editar/{mov_id}', data=_form(**cambios))

    def filas(self, tabla='movimientos'):
        con = database.conectar()
        try:
            return [dict(f) for f in
                    con.execute(f'SELECT * FROM {tabla} ORDER BY id')]
        finally:
            con.close()

    def sembrar(self, **extra):
        """Un movimiento previo, para editar. Devuelve su id."""
        datos = dict(fecha='2026-09-01', descripcion='Original', persona='elias',
                     moneda='ars', tipo='gasto', monto=1000.0, categoria='Hogar',
                     monto_usd=1.0, cotizacion_usd_aplicada=1000.0)
        datos.update(extra)
        return database.agregar_movimiento(**datos)

    def ruta_de(self, respuesta):
        return urlsplit(respuesta.headers['Location']).path


# ── 1. Lo que se rechaza ─────────────────────────────────────────────────────
#
# (campo, valor, fragmento del mensaje). `None` = el campo ni se manda. Un
# campo OBLIGATORIO ausente tiene que dar el mismo 400 con mensaje que uno
# invalido: antes era un KeyError y salia 500 (o el 400 pelado de Werkzeug).

INVALIDOS = [
    # fecha: obligatoria, YYYY-MM-DD de un dia real, anios 2000-2100
    ('fecha', None, 'Falta la fecha'),
    ('fecha', '', 'Falta la fecha'),
    ('fecha', 'x" onfocus="alert(1)', 'La fecha no es válida'),
    ('fecha', '2026-09-15"><img src=x>', 'La fecha no es válida'),
    ('fecha', '2026-13-01', 'La fecha no es válida'),
    ('fecha', '2026-02-30', 'La fecha no es válida'),
    ('fecha', '0000-01-01', 'La fecha no es válida'),
    ('fecha', '2026-9-5', 'La fecha no es válida'),            # strptime la acepta; la base no la tolera
    ('fecha', '26-09-15', 'La fecha no es válida'),
    ('fecha', '2026-09-15\n', 'La fecha no es válida'),        # `$` dejaria pasar el salto de linea
    ('fecha', ' 2026-09-15', 'La fecha no es válida'),
    ('fecha', '1999-12-31', 'entre los años'),
    ('fecha', '2101-01-01', 'entre los años'),
    # descripcion: obligatoria, <= 200, sin caracteres de control
    ('descripcion', None, 'Falta la descripción'),
    ('descripcion', '', 'Falta la descripción'),
    ('descripcion', '     ', 'Falta la descripción'),
    ('descripcion', 'x' * 201, 'más de 200 caracteres'),
    ('descripcion', 'a\x00b', 'La descripción tiene caracteres no permitidos'),
    ('descripcion', 'a\x07b', 'La descripción tiene caracteres no permitidos'),
    ('descripcion', 'a\nb', 'La descripción tiene caracteres no permitidos'),
    ('descripcion', 'a\x7fb', 'La descripción tiene caracteres no permitidos'),
    ('descripcion', 'a\u2028b', 'La descripción tiene caracteres no permitidos'),
    ('descripcion', 'Super\n', 'La descripción tiene caracteres no permitidos'),  # el \n final NO es un espacio sobrante
    # persona / moneda / tipo: exactamente uno de los valores del desplegable
    ('persona', None, 'persona válida'),
    ('persona', '', 'persona válida'),
    ('persona', 'pedro', 'persona válida'),
    ('persona', 'ELIAS', 'persona válida'),
    ('persona', 'elias ', 'persona válida'),
    ('moneda', None, 'moneda válida'),
    ('moneda', 'eur', 'moneda válida'),
    ('moneda', 'ARS', 'moneda válida'),
    ('tipo', None, 'tipo válido'),
    ('tipo', 'transferencia', 'tipo válido'),
    ('tipo', 'GASTO', 'tipo válido'),
    # monto: obligatorio, finito, 0 <= monto <= 1e12
    ('monto', None, 'Falta el monto'),
    ('monto', '', 'Falta el monto'),
    ('monto', 'abc', 'El monto no es un número válido'),
    ('monto', '12,5', 'El monto no es un número válido'),
    ('monto', 'nan', 'El monto no es un número válido'),
    ('monto', 'NaN', 'El monto no es un número válido'),
    ('monto', 'inf', 'El monto no es un número válido'),
    ('monto', '-inf', 'El monto no es un número válido'),
    ('monto', 'Infinity', 'El monto no es un número válido'),
    ('monto', '1e999', 'El monto no es un número válido'),    # float() lo lee como infinito: el caso que tumbaba la app
    ('monto', '-1', 'El monto no puede ser negativo'),
    ('monto', '-0.01', 'El monto no puede ser negativo'),
    ('monto', '1000000000001', 'El monto es demasiado grande'),
    ('monto', '1e13', 'El monto es demasiado grande'),
    # costo_envio: opcional; si viene, finito y 0 <= x <= 1e12
    ('costo_envio', 'abc', 'El costo de envío no es un número válido'),
    ('costo_envio', 'nan', 'El costo de envío no es un número válido'),
    ('costo_envio', 'inf', 'El costo de envío no es un número válido'),
    ('costo_envio', '1e999', 'El costo de envío no es un número válido'),
    ('costo_envio', '-5', 'El costo de envío no puede ser negativo'),
    ('costo_envio', '1e13', 'El costo de envío es demasiado grande'),
    # total_cuotas: opcional; si viene, entero 1..120
    ('total_cuotas', '0', 'cuotas'),
    ('total_cuotas', '121', 'cuotas'),
    ('total_cuotas', '-3', 'cuotas'),
    ('total_cuotas', 'abc', 'cuotas'),
    ('total_cuotas', '2.5', 'cuotas'),
    ('total_cuotas', '1e1', 'cuotas'),
    ('total_cuotas', '1_0', 'cuotas'),
    ('total_cuotas', '9999', 'cuotas'),
    # categoria: opcional; <= 40, sin control ni < > "  (SIN lista blanca)
    ('categoria', 'x' * 41, 'más de 40 caracteres'),
    ('categoria', 'a<b', 'La categoría tiene caracteres no permitidos'),
    ('categoria', 'a>b', 'La categoría tiene caracteres no permitidos'),
    ('categoria', 'a"b', 'La categoría tiene caracteres no permitidos'),
    ('categoria', '<script>alert(1)</script>', 'La categoría tiene caracteres no permitidos'),
    ('categoria', 'a\x01b', 'La categoría tiene caracteres no permitidos'),
    ('categoria', 'a\nb', 'La categoría tiene caracteres no permitidos'),
]

# Los campos propios del cambio (la "entrada" del cambio es el destino).
INVALIDOS_CAMBIO = [
    ('persona_final', None, 'persona final válida'),
    ('persona_final', '', 'persona final válida'),
    ('persona_final', 'pedro', 'persona final válida'),
    ('moneda_final', None, 'moneda final válida'),
    ('moneda_final', 'eur', 'moneda final válida'),
    ('monto_final', 'abc', 'El monto final no es un número válido'),
    ('monto_final', 'nan', 'El monto final no es un número válido'),
    ('monto_final', 'inf', 'El monto final no es un número válido'),
    ('monto_final', '1e999', 'El monto final no es un número válido'),
    ('monto_final', '-5', 'El monto final no puede ser negativo'),
    ('monto_final', '1e13', 'El monto final es demasiado grande'),
    # y los de siempre tambien valen para un cambio
    ('monto', 'nan', 'El monto no es un número válido'),
    ('monto', '-1', 'El monto no puede ser negativo'),
    ('persona', 'pedro', 'persona válida'),
    ('fecha', 'x" onfocus="alert(1)', 'La fecha no es válida'),
    ('descripcion', '', 'Falta la descripción'),
]


class TestAgregarRechaza(BaseMovimientos):

    def test_ajax_da_400_con_mensaje_y_no_escribe(self):
        for campo, valor, fragmento in INVALIDOS:
            with self.subTest(campo=campo, valor=valor):
                r = self.post_agregar(**{campo: valor})
                self.assertEqual(r.status_code, 400)
                cuerpo = r.get_json()
                self.assertFalse(cuerpo['ok'])
                self.assertIn(fragmento, cuerpo['error'])
                self.assertEqual(self.filas(), [])

    def test_sin_ajax_redirige_como_siempre_y_no_escribe(self):
        for campo, valor, _ in INVALIDOS:
            with self.subTest(campo=campo, valor=valor):
                r = self.post_agregar(ajax=False, **{campo: valor})
                self.assertEqual(r.status_code, 302)
                self.assertEqual(self.ruta_de(r), '/gastos')
                self.assertEqual(self.filas(), [])

    def test_un_cambio_ajax_rechaza_sus_campos_y_no_escribe(self):
        for campo, valor, fragmento in INVALIDOS_CAMBIO:
            with self.subTest(campo=campo, valor=valor):
                r = self.post_agregar(datos=_form_cambio(**{campo: valor}))
                self.assertEqual(r.status_code, 400)
                self.assertIn(fragmento, r.get_json()['error'])
                # Un cambio son DOS filas: ni la primera puede haber quedado.
                self.assertEqual(self.filas(), [])

    def test_un_cambio_sin_ajax_redirige_y_no_escribe(self):
        for campo, valor, _ in INVALIDOS_CAMBIO:
            with self.subTest(campo=campo, valor=valor):
                r = self.post_agregar(
                    ajax=False, datos=_form_cambio(**{campo: valor}))
                self.assertEqual(r.status_code, 302)
                self.assertEqual(self.filas(), [])

    def test_un_form_vacio_no_es_un_500(self):
        r = self.post_agregar(datos={})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json()['ok'])
        self.assertTrue(r.get_json()['error'])

    def test_el_tipo_cambio_no_vale_en_un_alta_sin_sus_campos(self):
        """Un cambio sin destino no es un gasto con otro nombre: se rechaza."""
        r = self.post_agregar(tipo='cambio')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.filas(), [])

    def test_el_infinito_no_deja_la_app_en_500(self):
        """
        El caso que lo origino todo: monto=1e999 se guardaba y despues el
        Inicio y /gastos daban 500 hasta borrar la fila a mano.
        """
        r = self.post_agregar(monto='1e999')
        self.assertEqual(r.status_code, 400)
        for ruta in ('/', '/gastos'):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 200)

    def test_el_rechazo_vale_tambien_para_lo_personal(self):
        r = self.post_agregar(monto='nan', personal='1')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.filas(), [])

    def test_lo_personal_que_ya_se_rechazaba_se_sigue_rechazando(self):
        """Un sueldo personal no existe: la validacion nueva no pisa esa regla."""
        r = self.post_agregar(tipo='ingreso', categoria='Sueldo', personal='1')
        self.assertEqual(r.status_code, 400)
        self.assertIn('sueldo', r.get_json()['error'].lower())
        self.assertEqual(self.filas(), [])


# ── 2. Lo que sigue andando ──────────────────────────────────────────────────

class TestAgregaAcepta(BaseMovimientos):

    def test_un_gasto_en_pesos(self):
        r = self.post_agregar()
        self.assertEqual(r.status_code, 200)
        cuerpo = r.get_json()
        self.assertTrue(cuerpo['ok'])
        self.assertFalse(cuerpo['personal'])
        self.assertEqual(cuerpo['movimiento']['categoria'], 'Comida y bebida')

        fila, = self.filas()
        self.assertEqual(fila['fecha'], '2026-09-15')
        self.assertEqual(fila['descripcion'], 'Supermercado')
        self.assertEqual((fila['persona'], fila['moneda'], fila['tipo']),
                         ('elias', 'ars', 'gasto'))
        self.assertEqual(fila['monto'], 15000.0)
        self.assertEqual(fila['categoria'], 'Comida y bebida')
        self.assertEqual(fila['personal'], 0)
        # 15.000 pesos a 1.000 por dolar
        self.assertAlmostEqual(fila['monto_usd'], 15.0)
        self.assertEqual(fila['cotizacion_usd_aplicada'], 1000.0)

    def test_un_gasto_en_dolares_no_usa_la_cotizacion(self):
        self.post_agregar(moneda='usd', monto='42.5')
        fila, = self.filas()
        self.assertEqual(fila['monto_usd'], 42.5)
        self.assertIsNone(fila['cotizacion_usd_aplicada'])

    def test_sin_ajax_inserta_y_redirige(self):
        r = self.post_agregar(ajax=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.ruta_de(r), '/gastos')
        self.assertEqual(len(self.filas()), 1)

    def test_un_sueldo_lleva_el_factor(self):
        self.post_agregar(tipo='ingreso', categoria='Sueldo',
                          descripcion='Sueldo septiembre', monto='1000000')
        fila, = self.filas()
        self.assertEqual(fila['tipo'], 'ingreso')
        self.assertEqual(fila['factor_aplicado'], 0.7)

    def test_un_gasto_personal_va_a_la_cuenta_personal(self):
        r = self.post_agregar(personal='1')
        cuerpo = r.get_json()
        self.assertTrue(cuerpo['personal'])
        fila, = self.filas()
        self.assertEqual(fila['personal'], 1)
        self.assertIsNone(fila['factor_aplicado'])

    def test_un_cambio_son_dos_filas(self):
        r = self.post_agregar(datos=_form_cambio())
        self.assertEqual(r.status_code, 200)
        cuerpo = r.get_json()
        self.assertEqual(cuerpo['movimiento']['tipo'], 'cambio')
        self.assertEqual(cuerpo['movimiento2']['moneda'], 'usd')
        self.assertEqual(cuerpo['movimiento2']['monto'], 100.0)

        salida, entrada = self.filas()
        self.assertEqual((salida['tipo'], salida['persona'], salida['moneda'],
                          salida['monto']), ('gasto', 'elias', 'ars', 150000.0))
        self.assertEqual((entrada['tipo'], entrada['persona'], entrada['moneda'],
                          entrada['monto']), ('ingreso', 'mari', 'usd', 100.0))
        self.assertEqual((salida['categoria'], entrada['categoria']),
                         ('Cambio', 'Cambio'))
        # Cada pata se convierte con SU moneda: 150.000 pesos son USD 150
        # a 1.000, y los USD 100 de la entrada no se convierten.
        self.assertAlmostEqual(salida['monto_usd'], 150.0)
        self.assertEqual(entrada['monto_usd'], 100.0)
        self.assertIsNone(entrada['cotizacion_usd_aplicada'])

    def test_un_cambio_sin_monto_final_usa_el_mismo_monto(self):
        """Misma moneda: el form esconde el campo y no lo manda."""
        self.post_agregar(datos=_form_cambio(
            moneda='ars', moneda_final='ars', monto='5000', monto_final=None))
        salida, entrada = self.filas()
        self.assertEqual(entrada['monto'], salida['monto'])
        self.assertEqual(entrada['monto'], 5000.0)

    def test_un_cambio_ignora_categoria_envio_y_cuotas(self):
        """
        En un cambio la categoria la fija el server y envio/cuotas no se usan:
        lo que mande el form ahi ni se guarda ni se valida.
        """
        r = self.post_agregar(datos=_form_cambio(
            categoria='<b>', costo_envio='abc', total_cuotas='999'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual({f['categoria'] for f in self.filas()}, {'Cambio'})

    def test_un_cambio_personal_marca_las_dos_filas(self):
        self.post_agregar(datos=_form_cambio(personal='1', persona_final='elias'))
        self.assertEqual([f['personal'] for f in self.filas()], [1, 1])

    def test_las_cuotas_crean_el_gasto_fijo(self):
        self.post_agregar(categoria='Servicios', descripcion='Heladera',
                          cuotas_checkbox='1', total_cuotas='3')
        fila, = self.filas()
        self.assertEqual((fila['cuota_numero'], fila['cuota_total']), (1, 3))
        fijo, = self.filas('gastos_fijos')
        self.assertEqual((fijo['descripcion'], fijo['es_cuota'],
                          fijo['total_cuotas'], fijo['cuota_actual']),
                         ('Heladera', 1, 3, 1))

    def test_un_fijo_en_cuotas_avanza_la_cuota(self):
        database.agregar_gasto_fijo_cuotas('Heladera', 3)
        self.post_agregar(categoria='Fijo', descripcion='Heladera')
        fila, = self.filas()
        self.assertEqual((fila['cuota_numero'], fila['cuota_total']), (2, 3))
        fijo, = self.filas('gastos_fijos')
        self.assertEqual(fijo['cuota_actual'], 2)

    def test_el_monto_cero_vale(self):
        """Hay gastos fijos de monto 0: no se puede exigir > 0."""
        r = self.post_agregar(monto='0')
        self.assertEqual(r.status_code, 200)
        fila, = self.filas()
        self.assertEqual(fila['monto'], 0.0)
        self.assertEqual(fila['monto_usd'], 0.0)

    def test_menos_cero_se_guarda_como_cero(self):
        self.post_agregar(monto='-0')
        fila, = self.filas()
        self.assertEqual(fila['monto'], 0.0)
        self.assertEqual(math.copysign(1.0, fila['monto']), 1.0)

    def test_una_categoria_vieja_fuera_del_desplegable_vale(self):
        """Hay filas de 'Laser' (sin tilde) en la base: no hay lista blanca."""
        r = self.post_agregar(categoria='Laser', tipo='ingreso')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.filas()[0]['categoria'], 'Laser')

    def test_la_descripcion_es_texto_libre(self):
        """
        Comillas, `<` y `&` son legitimos en una descripcion: el escape es
        cosa de la SALIDA. Rechazarlos romperia un "Cuota <Zara>" de verdad.
        """
        texto = 'Cuota "1" <Zara> & co \'x\' 🛒'
        self.post_agregar(descripcion=texto)
        self.assertEqual(self.filas()[0]['descripcion'], texto)

    def test_los_espacios_de_los_bordes_se_recortan(self):
        self.post_agregar(descripcion='   Super   ', categoria='  Hogar  ')
        fila, = self.filas()
        self.assertEqual(fila['descripcion'], 'Super')
        self.assertEqual(fila['categoria'], 'Hogar')

    def test_una_categoria_en_blanco_es_sin_categoria(self):
        r = self.post_agregar(categoria='   ')
        self.assertEqual(self.filas()[0]['categoria'], None)
        self.assertEqual(r.get_json()['movimiento']['categoria'], 'No Definido')

    def test_el_envio_vacio_o_en_cero(self):
        self.post_agregar(costo_envio='')
        self.post_agregar(costo_envio='0')
        self.post_agregar(costo_envio='350.5')
        self.assertEqual([f['costo_envio'] for f in self.filas()],
                         [None, 0.0, 350.5])

    def test_los_bordes_valen(self):
        casos = [
            ('descripcion', 'x' * 200),
            ('categoria', 'x' * 40),
            ('monto', '1000000000000'),          # 1e12
            ('fecha', '2000-01-01'),
            ('fecha', '2100-12-31'),
            ('total_cuotas', '1'),
            ('total_cuotas', '120'),
        ]
        for campo, valor in casos:
            with self.subTest(campo=campo, valor=valor[:20]):
                r = self.post_agregar(**{campo: valor})
                self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self.filas()), len(casos))


# ── 3. /editar ───────────────────────────────────────────────────────────────

class TestEditar(BaseMovimientos):

    def test_rechaza_lo_invalido_con_el_motivo_y_no_toca_la_fila(self):
        mov_id = self.sembrar()
        antes = self.filas()
        for campo, valor, fragmento in INVALIDOS:
            with self.subTest(campo=campo, valor=valor):
                r = self.post_editar(mov_id, **{campo: valor})
                self.assertEqual(r.status_code, 400)
                # Vuelve al formulario con el motivo adentro.
                html = r.get_data(as_text=True)
                self.assertIn(fragmento, html)
                self.assertEqual(self.filas(), antes)

    def test_el_tipo_cambio_no_se_edita(self):
        """El form de edicion solo ofrece ingreso y gasto."""
        mov_id = self.sembrar()
        antes = self.filas()
        r = self.post_editar(mov_id, tipo='cambio')
        self.assertEqual(r.status_code, 400)
        self.assertIn('tipo válido', r.get_data(as_text=True))
        self.assertEqual(self.filas(), antes)

    def test_un_campo_ausente_da_el_mensaje_y_no_el_400_pelado(self):
        mov_id = self.sembrar()
        r = self.post_editar(mov_id, fecha=None)
        self.assertEqual(r.status_code, 400)
        self.assertIn('Falta la fecha', r.get_data(as_text=True))

    def test_lo_invalido_sobre_un_id_que_no_existe_vuelve_a_gastos(self):
        r = self.post_editar(99999, monto='nan')
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.ruta_de(r), '/gastos')

    def test_una_edicion_valida_guarda_y_recalcula_el_usd(self):
        mov_id = self.sembrar()
        r = self.post_editar(mov_id, descripcion='  Verduleria ',
                             monto='2500', categoria='', costo_envio='')
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.ruta_de(r), '/gastos')
        fila, = self.filas()
        self.assertEqual(fila['descripcion'], 'Verduleria')
        self.assertEqual(fila['monto'], 2500.0)
        self.assertIsNone(fila['categoria'])
        self.assertIsNone(fila['costo_envio'])
        self.assertAlmostEqual(fila['monto_usd'], 2.5)
        self.assertEqual(fila['cotizacion_usd_aplicada'], 1000.0)

    def test_una_edicion_a_dolares_deja_sin_cotizacion(self):
        mov_id = self.sembrar()
        self.post_editar(mov_id, moneda='usd', monto='30')
        fila, = self.filas()
        self.assertEqual(fila['monto_usd'], 30.0)
        self.assertIsNone(fila['cotizacion_usd_aplicada'])

    def test_el_monto_cero_y_la_categoria_vieja_se_pueden_editar(self):
        mov_id = self.sembrar(categoria='Laser')
        r = self.post_editar(mov_id, monto='0', categoria='Laser')
        self.assertEqual(r.status_code, 302)
        fila, = self.filas()
        self.assertEqual((fila['monto'], fila['categoria']), (0.0, 'Laser'))

    def test_mover_a_personal_sigue_andando(self):
        mov_id = self.sembrar()
        r = self.client.post(f'/editar/{mov_id}',
                             data=_form(ambito_presente='1', personal='1'))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.ruta_de(r), '/personal')
        self.assertEqual(self.filas()[0]['personal'], 1)

    def test_un_sueldo_personal_se_sigue_rechazando(self):
        mov_id = self.sembrar()
        r = self.client.post(
            f'/editar/{mov_id}',
            data=_form(tipo='ingreso', categoria='Sueldo',
                       ambito_presente='1', personal='1'))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.filas()[0]['personal'], 0)

    def test_la_edicion_comparte_las_reglas_de_los_numeros(self):
        """Mismo helper que /agregar: un `1e999` no entra por ninguna de las dos."""
        mov_id = self.sembrar()
        for campo, valor in (('monto', '1e999'), ('costo_envio', 'inf'),
                             ('total_cuotas', '999')):
            with self.subTest(campo=campo):
                r = self.post_editar(mov_id, **{campo: valor})
                self.assertEqual(r.status_code, 400)
        self.assertEqual(self.filas()[0]['monto'], 1000.0)


# ── 4. La cotizacion: la red de seguridad ────────────────────────────────────

class TestCalcularMontoUsd(unittest.TestCase):
    """La funcion sola, sin Flask ni base."""

    SIN_COTIZACION = [
        ('cero', {'cotizacion_valor': 0}),
        ('cero float', {'cotizacion_valor': 0.0}),
        ('menos cero', {'cotizacion_valor': -0.0}),
        ('negativa', {'cotizacion_valor': -1500.0}),
        ('None', {'cotizacion_valor': None}),
        ('ausente', {}),
        ('vacia', {'cotizacion_valor': ''}),
        ('texto', {'cotizacion_valor': 'abc'}),
        ('texto cero', {'cotizacion_valor': '0'}),
        ('NaN', {'cotizacion_valor': float('nan')}),
        ('NaN en texto', {'cotizacion_valor': 'nan'}),
        ('infinito', {'cotizacion_valor': float('inf')}),
        ('menos infinito', {'cotizacion_valor': float('-inf')}),
        ('diminuta', {'cotizacion_valor': 1e-320}),   # el cociente desborda a infinito
        ('lista', {'cotizacion_valor': [1500]}),
    ]

    def test_sin_cotizacion_valida_lanza(self):
        for nombre, cfg in self.SIN_COTIZACION:
            with self.subTest(cotizacion=nombre):
                with self.assertRaises(ValueError) as ctx:
                    app_module._calcular_monto_usd(1000.0, 'ars', cfg)
                self.assertEqual(str(ctx.exception),
                                 app_module._MSG_SIN_COTIZACION)

    def test_el_mensaje_habla_en_cristiano(self):
        self.assertIn('cotización', app_module._MSG_SIN_COTIZACION)

    def test_en_dolares_no_hace_falta_cotizacion(self):
        """Un movimiento en USD no se convierte: no depende de la cotizacion."""
        for nombre, cfg in self.SIN_COTIZACION:
            with self.subTest(cotizacion=nombre):
                self.assertEqual(
                    app_module._calcular_monto_usd(50, 'usd', cfg), (50.0, None))

    def test_con_cotizacion_valida_convierte(self):
        usd, cot = app_module._calcular_monto_usd(
            1500000, 'ars', {'cotizacion_valor': 1500.0})
        self.assertAlmostEqual(usd, 1000.0)
        self.assertEqual(cot, 1500.0)

    def test_una_cotizacion_guardada_como_texto_numerico_sirve(self):
        usd, cot = app_module._calcular_monto_usd(
            3000, 'ars', {'cotizacion_valor': '1500'})
        self.assertAlmostEqual(usd, 2.0)
        self.assertEqual(cot, 1500.0)


class TestSinCotizacionEnLasRutas(BaseMovimientos):
    """
    Los CAMINOS que llaman a _calcular_monto_usd manejan el ValueError: es lo
    que convierte "lanza" en "no se guarda y se avisa" en vez de un 500.
    """

    CASOS = [('cero', 0), ('ausente', _AUSENTE), ('NaN', 'nan'), ('None', None)]

    def test_agregar_en_pesos_da_400_y_no_guarda(self):
        for nombre, valor in self.CASOS:
            with self.subTest(cotizacion=nombre):
                self.con_config(cotizacion_valor=valor)
                r = self.post_agregar()
                self.assertEqual(r.status_code, 400)
                self.assertEqual(r.get_json()['error'],
                                 app_module._MSG_SIN_COTIZACION)
                self.assertEqual(self.filas(), [])

    def test_agregar_sin_ajax_redirige_y_no_guarda(self):
        self.con_config(cotizacion_valor=0)
        r = self.post_agregar(ajax=False)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.filas(), [])

    def test_agregar_en_dolares_sigue_andando(self):
        self.con_config(cotizacion_valor=0)
        r = self.post_agregar(moneda='usd')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self.filas()), 1)

    def test_un_cambio_no_deja_medio_cambio(self):
        """
        USD -> AR$: la primera conversion (USD) no necesita cotizacion y la
        segunda (AR$) si. Si las dos conversiones no fueran antes de los dos
        INSERT, quedaria la salida escrita y la entrada no.
        """
        self.con_config(cotizacion_valor=0)
        r = self.post_agregar(datos=_form_cambio(
            moneda='usd', monto='100', moneda_final='ars', monto_final='150000'))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()['error'], app_module._MSG_SIN_COTIZACION)
        self.assertEqual(self.filas(), [])

    def test_un_cambio_en_dolares_en_las_dos_patas_no_necesita_cotizacion(self):
        self.con_config(cotizacion_valor=0)
        r = self.post_agregar(datos=_form_cambio(
            moneda='usd', monto='100', moneda_final='usd', monto_final='100',
            persona_final='mari'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self.filas()), 2)

    def test_editar_da_400_con_el_motivo_y_no_toca_la_fila(self):
        """La llamada estaba FUERA del try: un ValueError terminaba en 500."""
        mov_id = self.sembrar()
        antes = self.filas()
        for nombre, valor in self.CASOS:
            with self.subTest(cotizacion=nombre):
                self.con_config(cotizacion_valor=valor)
                r = self.post_editar(mov_id, monto='9999')
                self.assertEqual(r.status_code, 400)
                self.assertIn('cotización', r.get_data(as_text=True))
                self.assertEqual(self.filas(), antes)


# ── 5. Gastos fijos: `</script>` ─────────────────────────────────────────────

def _gastos_fijos_de(html):
    """Lo que el navegador va a leer en `var GASTOS_FIJOS = ...;`."""
    m = re.search(r'^\s*var GASTOS_FIJOS = (.*);\s*$', html, re.MULTILINE)
    assert m, 'la pagina no define GASTOS_FIJOS'
    return json.loads(m.group(1))


class TestGastosFijosEnLaPagina(BaseMovimientos):

    PELIGROSO = '</script><script>alert(1)</script>'
    RUTAS = ('/gastos', '/')

    def test_el_helper_devuelve_la_lista_y_no_un_string(self):
        database.agregar_gasto_fijo('Alquiler')
        database.agregar_gasto_fijo_cuotas('Heladera', 6)
        lista = app_module._gastos_fijos_json()
        self.assertIsInstance(lista, list)
        self.assertEqual(lista, [
            {'descripcion': 'Alquiler', 'es_cuota': 0, 'cuota_actual': 0,
             'total_cuotas': None},
            {'descripcion': 'Heladera', 'es_cuota': 1, 'cuota_actual': 1,
             'total_cuotas': 6},
        ])

    def test_sin_gastos_fijos_es_una_lista_vacia(self):
        self.assertEqual(app_module._gastos_fijos_json(), [])
        for ruta in self.RUTAS:
            with self.subTest(ruta=ruta):
                html = self.client.get(ruta).get_data(as_text=True)
                self.assertEqual(_gastos_fijos_de(html), [])

    def test_un_gasto_fijo_con_script_no_cierra_el_script_de_la_pagina(self):
        # La cantidad de <script> y </script> de cada pagina ANTES de cargar el
        # fijo peligroso: si la inyeccion funcionara, sumaria etiquetas.
        antes = {}
        for ruta in self.RUTAS:
            html = self.client.get(ruta).get_data(as_text=True)
            antes[ruta] = (html.count('<script'), html.count('</script>'))

        database.agregar_gasto_fijo(self.PELIGROSO)
        database.agregar_gasto_fijo('Alquiler')

        for ruta in self.RUTAS:
            with self.subTest(ruta=ruta):
                r = self.client.get(ruta)
                self.assertEqual(r.status_code, 200)
                html = r.get_data(as_text=True)
                # El texto crudo no llega al navegador.
                self.assertNotIn('</script><script>alert(1)', html)
                self.assertNotIn('<script>alert(1)', html)
                self.assertEqual(
                    (html.count('<script'), html.count('</script>')), antes[ruta])
                # Y el dato llega entero: el navegador lo lee como texto. Sin
                # mirar el orden (lo decide el ORDER BY de la base, y el '<'
                # ordena antes que la 'A').
                descripciones = [f['descripcion'] for f in _gastos_fijos_de(html)]
                self.assertCountEqual(descripciones, ['Alquiler', self.PELIGROSO])

    def test_comillas_ampersand_y_apostrofe_tambien_viajan_enteros(self):
        raro = 'Cuota "1" & \'2\' <b>3</b>'
        database.agregar_gasto_fijo_cuotas(raro, 6)
        for ruta in self.RUTAS:
            with self.subTest(ruta=ruta):
                html = self.client.get(ruta).get_data(as_text=True)
                fijo, = _gastos_fijos_de(html)
                self.assertEqual(
                    fijo, {'descripcion': raro, 'es_cuota': 1,
                           'cuota_actual': 1, 'total_cuotas': 6})
                self.assertNotIn('<b>3</b>', html)


class TestFormatoMontosNoFinitos(unittest.TestCase):
    """
    La entrada ya rechaza infinitos y NaN, pero un backup viejo restaurado
    puede traer una fila así. Antes `fmt_ars` hacía `round(inf)` → OverflowError
    y UNA fila rota dejaba el Inicio y /gastos en 500 para todos.
    """

    def test_infinito_y_nan_no_revientan_el_formato(self):
        for valor in (math.inf, -math.inf, math.nan):
            with self.subTest(valor=valor):
                self.assertEqual(app_module.fmt_ars(valor), '$ —')
                self.assertEqual(app_module.fmt_usd(valor), 'USD —')

    def test_los_valores_normales_no_cambian(self):
        self.assertEqual(app_module.fmt_ars(1250000.0), '$ 1.250.000')
        self.assertEqual(app_module.fmt_ars(-50000.0), '$ -50.000')
        self.assertEqual(app_module.fmt_usd(1250.5), 'USD 1.250,50')
        self.assertEqual(app_module.fmt_usd(-300.0), 'USD -300,00')


if __name__ == '__main__':
    unittest.main()
