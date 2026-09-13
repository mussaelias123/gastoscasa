# =============================================================================
# ARCHIVO: tests/test_personal.py
# =============================================================================
#
# Tests de la CUENTA PERSONAL (columna movimientos.personal) y, sobre todo, de
# que el FONDO FAMILIAR haya quedado exactamente como estaba.
#
# POR QUE EXISTE ESTE ARCHIVO: el modulo Personal no agrego una tabla nueva,
# agrego una columna a `movimientos`. Eso significa que TODA query que ya
# existia sobre esa tabla tiene que filtrar `personal = 0` o el fondo empieza a
# sumar plata que no es suya. Son seis queries en tres funciones
# (calcular_saldos, obtener_movimientos, verificar_gastos_fijos) y olvidarse de
# una no rompe nada visible: los numeros quedan mal y nadie se entera.
#
# Por eso el corazon de estos tests es el mismo escenario cargado dos veces —
# una sola con movimientos del fondo, otra con los mismos mas movimientos
# personales — verificando que el fondo da IDENTICO en las dos.
#
# Se usa una base SQLite real en un archivo temporal, no mocks: lo que se esta
# probando son los WHERE del SQL, y un mock de la capa de datos no los ejecuta.
#
# COMO CORRER:
#   Desde la raiz del proyecto:
#       python -m unittest tests.test_personal -v
#
# =============================================================================

import os
import sys
import shutil
import tempfile
import unittest
import unittest.mock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import database  # noqa: E402


# ── Andamiaje: base temporal por test ────────────────────────────────────────

class BaseTemporal(unittest.TestCase):
    """Cada test arranca con una base vacia recien inicializada."""

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix='fondo-test-')
        self._db_original = database.DB_PATH
        database.DB_PATH = os.path.join(self._dir, 'fondo.db')
        database.inicializar_db()

    def tearDown(self):
        database.DB_PATH = self._db_original
        shutil.rmtree(self._dir, ignore_errors=True)

    # Atajos de alta. `monto_usd` se pasa a mano (en la app lo calcula app.py
    # con la cotizacion del dia); aca se usa 1 USD = 1000 AR$ para que las
    # cuentas se puedan seguir de cabeza.
    def alta(self, descripcion, persona, moneda, tipo, monto, **kw):
        monto_usd = monto if moneda == 'usd' else monto / 1000.0
        kw.setdefault('monto_usd', monto_usd)
        kw.setdefault('cotizacion_usd_aplicada', None if moneda == 'usd' else 1000.0)
        return database.agregar_movimiento(
            '2026-09-10', descripcion, persona, moneda, tipo, monto, **kw)

    def cargar_fondo(self):
        """El escenario del fondo familiar. Siempre el mismo."""
        self.alta('Sueldo', 'elias', 'ars', 'ingreso', 1000000.0,
                  categoria='Sueldo', factor_aplicado=0.85)
        self.alta('Sueldo', 'mari', 'ars', 'ingreso', 600000.0,
                  categoria='Sueldo', factor_aplicado=0.85)
        self.alta('Supermercado', 'elias', 'ars', 'gasto', 48000.0,
                  categoria='Comida y bebida')
        self.alta('Notebook', 'mari', 'usd', 'gasto', 300.0,
                  categoria='Hogar', costo_envio=25.0)
        self.alta('Ahorro', 'elias', 'usd', 'ingreso', 500.0, categoria='Otros')

    def cargar_personales(self):
        """Movimientos personales de los dos, encima del escenario del fondo."""
        self.alta('Cafe con Nico', 'elias', 'ars', 'gasto', 8500.0,
                  categoria='Entretenimiento', personal=1)
        self.alta('Venta bici', 'elias', 'ars', 'ingreso', 150000.0,
                  categoria='Venta', personal=1)
        self.alta('Libro', 'elias', 'usd', 'gasto', 18.0,
                  categoria='Entretenimiento', personal=1)
        self.alta('Peluqueria', 'mari', 'ars', 'gasto', 25000.0,
                  categoria='Otros', personal=1)


# ── 1. El fondo familiar no se entera de que existe lo personal ──────────────

class TestFondoIntacto(BaseTemporal):
    """La prueba de no-regresion: mismos numeros con y sin cuenta personal."""

    def test_saldos_del_fondo_identicos(self):
        self.cargar_fondo()
        antes = database.calcular_saldos()

        self.cargar_personales()
        despues = database.calcular_saldos()

        self.assertEqual(antes, despues,
                         'Los movimientos personales movieron los saldos del fondo')

    def test_saldos_del_fondo_a_una_fecha_identicos(self):
        # El filtro `hasta` se arma aparte en el SQL; se verifica que siga
        # conviviendo con el filtro de ambito y no lo pise.
        self.cargar_fondo()
        antes = database.calcular_saldos(hasta='2026-09-30')

        self.cargar_personales()
        despues = database.calcular_saldos(hasta='2026-09-30')

        self.assertEqual(antes, despues)

    def test_lista_de_movimientos_del_fondo_identica(self):
        self.cargar_fondo()
        filas_antes, total_antes = database.obtener_movimientos()

        self.cargar_personales()
        filas_despues, total_despues = database.obtener_movimientos()

        self.assertEqual(total_antes, total_despues,
                         'El contador de la tabla del fondo conto personales')
        self.assertEqual([f['id'] for f in filas_antes],
                         [f['id'] for f in filas_despues])

    def test_checklist_de_gastos_fijos_ignora_los_personales(self):
        database.agregar_gasto_fijo('Luz')

        # Un gasto PERSONAL que se llama igual y tiene categoria Fijo no debe
        # marcar el fijo del mes como pagado.
        self.alta('Luz', 'elias', 'ars', 'gasto', 74000.0,
                  categoria='Fijo', personal=1)
        fijos = database.verificar_gastos_fijos('2026-09')
        self.assertFalse(fijos[0]['encontrado'],
                         'Un gasto personal marco como pagado un fijo del fondo')

        # El mismo gasto, pero del fondo, si lo marca.
        self.alta('Luz', 'elias', 'ars', 'gasto', 74000.0, categoria='Fijo')
        fijos = database.verificar_gastos_fijos('2026-09')
        self.assertTrue(fijos[0]['encontrado'])

    def test_checklist_de_cuotas_ignora_las_personales(self):
        database.agregar_gasto_fijo_cuotas('Heladera', 12)

        self.alta('Heladera', 'mari', 'ars', 'gasto', 90000.0,
                  categoria='Fijo', cuota_numero=1, cuota_total=12, personal=1)
        fijos = database.verificar_gastos_fijos('2026-09')
        self.assertFalse(fijos[0]['encontrado'])


# ── 2. El ambito de obtener_movimientos ──────────────────────────────────────

class TestAmbito(BaseTemporal):

    def test_default_es_el_fondo(self):
        self.cargar_fondo()
        self.cargar_personales()
        filas, total = database.obtener_movimientos()
        self.assertEqual(total, 5)
        self.assertTrue(all(f['personal'] == 0 for f in filas))

    def test_personal_de_una_persona(self):
        self.cargar_fondo()
        self.cargar_personales()
        filas, total = database.obtener_movimientos(persona='elias', ambito='personal')
        self.assertEqual(total, 3)
        self.assertEqual(sorted(f['descripcion'] for f in filas),
                         ['Cafe con Nico', 'Libro', 'Venta bici'])

    def test_todos_no_filtra(self):
        self.cargar_fondo()
        self.cargar_personales()
        _filas, total = database.obtener_movimientos(ambito='todos')
        self.assertEqual(total, 9)

    def test_ambito_invalido_explota(self):
        with self.assertRaises(ValueError):
            database.obtener_movimientos(ambito='cualquiera')


# ── 3. Saldos personales ─────────────────────────────────────────────────────

class TestSaldosPersonales(BaseTemporal):

    def test_suma_movimientos_propios_y_el_resto_del_sueldo(self):
        self.cargar_fondo()
        self.cargar_personales()

        saldos = database.calcular_saldos_personales('elias')

        # ARS: resto del sueldo 1.000.000 * 0,15 = 150.000
        #      + venta bici 150.000 - cafe 8.500 = 291.500
        self.assertAlmostEqual(saldos['ars'], 291500.0, places=2)
        # USD: solo el libro, en negativo.
        self.assertAlmostEqual(saldos['usd'], -18.0, places=2)
        # Total USD: 291.500/1000 (los ARS entraron a 1000) - 18 = 273,5
        self.assertAlmostEqual(saldos['total_usd'], 273.5, places=2)

    def test_cada_uno_ve_solo_lo_suyo(self):
        self.cargar_fondo()
        self.cargar_personales()

        mari = database.calcular_saldos_personales('mari')
        # Resto del sueldo 600.000 * 0,15 = 90.000, menos peluqueria 25.000.
        self.assertAlmostEqual(mari['ars'], 65000.0, places=2)
        self.assertAlmostEqual(mari['usd'], 0.0, places=2)

    def test_el_costo_de_envio_de_un_gasto_personal_suma(self):
        self.alta('Zapatillas', 'elias', 'usd', 'gasto', 80.0,
                  categoria='Ropa', costo_envio=20.0, personal=1)
        saldos = database.calcular_saldos_personales('elias')
        self.assertAlmostEqual(saldos['usd'], -100.0, places=2)
        self.assertAlmostEqual(saldos['total_usd'], -100.0, places=2)

    def test_base_vacia_da_cero(self):
        saldos = database.calcular_saldos_personales('elias')
        self.assertEqual(saldos, {'ars': 0.0, 'usd': 0.0, 'total_usd': 0.0})

    def test_hasta_recorta(self):
        self.alta('Viejo', 'elias', 'ars', 'ingreso', 10000.0, personal=1)
        database.agregar_movimiento('2026-12-01', 'Futuro', 'elias', 'ars',
                                    'ingreso', 99000.0, monto_usd=99.0,
                                    cotizacion_usd_aplicada=1000.0, personal=1)
        saldos = database.calcular_saldos_personales('elias', hasta='2026-09-30')
        self.assertAlmostEqual(saldos['ars'], 10000.0, places=2)


# ── 4. El resto del sueldo ───────────────────────────────────────────────────

class TestRestoDelSueldo(BaseTemporal):
    """Se DERIVA del sueldo del fondo, no es una fila guardada."""

    def test_una_fila_por_sueldo_con_su_resto(self):
        self.alta('Sueldo', 'elias', 'ars', 'ingreso', 1000000.0,
                  categoria='Sueldo', factor_aplicado=0.85)
        filas = database.obtener_sueldos_resto('elias')
        self.assertEqual(len(filas), 1)
        self.assertAlmostEqual(filas[0]['resto'], 150000.0, places=2)
        self.assertAlmostEqual(filas[0]['resto_usd'], 150.0, places=2)

    def test_factor_uno_no_deja_resto(self):
        # Todo al fondo: no hay nada que mostrar en la cuenta personal.
        self.alta('Sueldo', 'elias', 'ars', 'ingreso', 1000000.0,
                  categoria='Sueldo', factor_aplicado=1.0)
        self.assertEqual(database.obtener_sueldos_resto('elias'), [])
        self.assertAlmostEqual(
            database.calcular_saldos_personales('elias')['ars'], 0.0, places=2)

    def test_sueldo_viejo_sin_factor_no_deja_resto(self):
        # Filas anteriores a que existiera el factor: factor_aplicado NULL.
        # Sin factor no se puede saber que parte era personal; se dejan afuera.
        self.alta('Sueldo', 'elias', 'ars', 'ingreso', 1000000.0,
                  categoria='Sueldo')
        self.assertEqual(database.obtener_sueldos_resto('elias'), [])

    def test_no_confunde_un_ingreso_comun_con_un_sueldo(self):
        self.alta('Venta', 'elias', 'ars', 'ingreso', 500000.0,
                  categoria='Venta', factor_aplicado=0.85)
        self.assertEqual(database.obtener_sueldos_resto('elias'), [])

    def test_filtra_por_mes(self):
        self.alta('Sueldo', 'elias', 'ars', 'ingreso', 1000000.0,
                  categoria='Sueldo', factor_aplicado=0.85)
        database.agregar_movimiento('2026-08-10', 'Sueldo', 'elias', 'ars',
                                    'ingreso', 900000.0, categoria='Sueldo',
                                    factor_aplicado=0.85, monto_usd=900.0,
                                    cotizacion_usd_aplicada=1000.0)
        self.assertEqual(len(database.obtener_sueldos_resto('elias', mes='2026-09')), 1)
        self.assertEqual(len(database.obtener_sueldos_resto('elias')), 2)


# ── 5. Editar no mueve de bolsillo sin pedirlo ───────────────────────────────

class TestEditarConserva(BaseTemporal):

    def test_sin_personal_la_columna_no_se_toca(self):
        mid = self.alta('Cafe', 'elias', 'ars', 'gasto', 8500.0, personal=1)
        database.editar_movimiento(mid, '2026-09-11', 'Cafe con leche', 'elias',
                                   'ars', 'gasto', 9000.0, categoria='Otros',
                                   monto_usd=9.0, cotizacion_usd_aplicada=1000.0)
        self.assertEqual(database.obtener_movimiento(mid)['personal'], 1)

    def test_con_personal_lo_mueve(self):
        mid = self.alta('Cafe', 'elias', 'ars', 'gasto', 8500.0, personal=1)
        database.editar_movimiento(mid, '2026-09-11', 'Cafe', 'elias', 'ars',
                                   'gasto', 8500.0, categoria='Otros',
                                   monto_usd=8.5, cotizacion_usd_aplicada=1000.0,
                                   personal=0)
        self.assertEqual(database.obtener_movimiento(mid)['personal'], 0)


# ── 6. La cuenta personal del otro no se mira ni se toca ─────────────────────

class TestGuardaDePrivacidad(unittest.TestCase):
    """`_es_ajeno` es la guarda de /editar y /eliminar, que trabajan por id.

    Por que existe: los ids son UNA sola secuencia compartida con el fondo, y
    /gastos imprime los del fondo en el HTML. Los huecos de la secuencia son
    justamente los movimientos personales, asi que alcanzaba con escribir
    /editar/102 a mano para leer el gasto personal del otro — en un modulo cuya
    pantalla promete "solo vos ves esta pantalla".
    """

    def setUp(self):
        import app as app_mod
        self.app_mod = app_mod

    def _mov(self, persona, personal):
        return {'persona': persona, 'personal': personal}

    def _con_persona(self, quien):
        """Fija quien esta mirando, sin tocar la sesion de Flask."""
        return unittest.mock.patch.object(self.app_mod, '_persona_actual',
                                          lambda *a, **k: quien)

    def test_el_personal_del_otro_es_ajeno(self):
        with self._con_persona('elias'):
            self.assertTrue(self.app_mod._es_ajeno(self._mov('mari', 1)))

    def test_el_personal_propio_no_es_ajeno(self):
        with self._con_persona('elias'):
            self.assertFalse(self.app_mod._es_ajeno(self._mov('elias', 1)))

    def test_el_fondo_nunca_es_ajeno(self):
        # El fondo es compartido: cualquiera edita cualquier cosa, es la idea.
        # Esta es la garantia de que la guarda no toca el modulo Gastos.
        with self._con_persona('elias'):
            self.assertFalse(self.app_mod._es_ajeno(self._mov('mari', 0)))
            self.assertFalse(self.app_mod._es_ajeno(self._mov('elias', 0)))

    def test_movimiento_inexistente_no_explota(self):
        # /editar y /eliminar la llaman antes de chequear None.
        with self._con_persona('elias'):
            self.assertFalse(self.app_mod._es_ajeno(None))


# ── 7. Que combina con que en un movimiento personal ─────────────────────────

class TestValidacionDelForm(unittest.TestCase):
    """_leer_personal_form es la red del servidor: el front ya saca estas
    opciones del desplegable, pero un POST sin JS tiene que fallar igual."""

    def setUp(self):
        import app as app_mod
        self.app_mod = app_mod

    def form(self, **kw):
        base = {'personal': '1'}
        base.update(kw)
        return base

    def test_sin_el_checkbox_es_del_fondo(self):
        self.assertFalse(self.app_mod._leer_personal_form({}, 'gasto', 'Otros'))

    def test_un_sueldo_personal_se_rechaza(self):
        # Siempre entra al fondo; lo que el factor deja afuera se deriva.
        with self.assertRaises(ValueError):
            self.app_mod._leer_personal_form(self.form(), 'ingreso', 'Sueldo')

    def test_un_fijo_personal_se_rechaza(self):
        with self.assertRaises(ValueError):
            self.app_mod._leer_personal_form(self.form(), 'gasto', 'Fijo')

    def test_no_le_importa_la_capitalizacion(self):
        with self.assertRaises(ValueError):
            self.app_mod._leer_personal_form(self.form(), 'ingreso', 'SUELDO')

    def test_gasto_ingreso_y_cambio_pasan(self):
        for tipo in ('gasto', 'ingreso', 'cambio'):
            self.assertTrue(
                self.app_mod._leer_personal_form(self.form(), tipo, 'Otros'),
                f'{tipo} deberia poder ser personal')


if __name__ == '__main__':
    unittest.main()
