# =============================================================================
# ARCHIVO: tests/test_push_encendido.py
# =============================================================================
#
# Tests del ENCENDIDO del push: el motor de flancos conectado al envio, con
# sus frenos. Es la etapa en la que `_push_ciclo()` deja de escribir en el log
# lo que mandaria y empieza a poder mandarlo de verdad.
#
# El envio en si esta en tests/test_push_envio.py; la deteccion de flancos, en
# tests/test_push_scheduler.py; el alta/baja y la tabla, en
# tests/test_push_suscripciones.py; el service worker, en tests/test_sw.py.
#
# POR QUE EXISTE ESTE ARCHIVO — TODO SALE DE UNA FRASE:
#
#   UN PUSH NO SE PUEDE DESAVISAR.
#
# Un mail de mas se borra, un puntito de mas en la campana se ignora. Un
# telefono que sono a las 3 de la manana ya sono, y el que se quema con dos
# noches de pitidos apaga los avisos para siempre — y ahi no se pierde un
# aviso, se pierde el canal entero. Cada test de este archivo congela una
# decision que frena hacia el mismo lado: hacia NO mandar.
#
#   1. EL INTERRUPTOR. `push_enabled` apagado tiene que seguir siendo
#      EXACTAMENTE el ensayo en seco, linea `SECO:` incluida. El ensayo corre
#      en produccion y no se puede romper al mergear esto.
#
#   2. EL DIFERIMIENTO NO ES UNA COLA, y es lo mejor del diseno. Un flanco que
#      cae en horas de silencio simplemente NO SE MARCA: sigue siendo flanco
#      ascendente, y a las 07:00 el motor vuelve a mirar el nivel REAL. Si la
#      condicion se resolvio de madrugada, ese aviso nunca sale. Nadie se
#      despierta con la novedad de algo que ya no pasa. Lo mismo con los
#      topes: lo que no entra gotea, no se descarta.
#
#   3. LA VENTANA CRUZA LA MEDIANOCHE. 22:30-07:00 escrito como un `<=` entre
#      dos numeros no silencia NUNCA — ninguna hora es a la vez mayor que
#      22:30 y menor que 07:00 — y el bug seria invisible leyendo el codigo:
#      se nota la primera noche. De ahi el test parametrizado.
#
#   4. LAS VAPID ROTAS NO CONSUMEN FLANCOS. Si se marcaran, el estado se
#      comeria en silencio todo lo que pasa mientras la config esta a medias,
#      y el dia que se arregle el motor diria "ya avise todo" sin que nunca
#      hubiera sonado nada.
#
# COMO CORRER:
#   Desde la raiz del proyecto:
#       python -m unittest tests.test_push_encendido -v
#
# =============================================================================

import io
import os
import sys
import json
import shutil
import tempfile
import unittest
import unittest.mock
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import app as app_module  # noqa: E402
import config  # noqa: E402
import database  # noqa: E402


# Un par VAPID CUALQUIERA con el formato correcto, el mismo de
# tests/test_push_envio.py. No firma nada (el envio esta mockeado): solo tiene
# que pasar la validacion de `_push_claves_vapid`.
VAPID_PUB = 'B' + 'q' * 86
VAPID_SEC = 'z' * 43
VAPID_MAIL = 'mailto:nadie@ejemplo.com'

# Dos dispositivos, uno de cada uno. Los avisos van a los dos (ver
# TestAQuienSeLeManda).
FILAS = [
    {'endpoint': 'https://fcm.googleapis.com/fcm/send/el-celu-de-elias',
     'p256dh': 'B' + 'a' * 86, 'auth': 'c' * 22,
     'persona': 'elias', 'user_email': 'mussaelias123@gmail.com'},
    {'endpoint': 'https://web.push.apple.com/el-iphone-de-mari',
     'p256dh': 'B' + 'b' * 86, 'auth': 'd' * 22,
     'persona': 'mari', 'user_email': 'mossinomariana@gmail.com'},
]

# Reloj congelado. NUNCA `datetime.now()`: un test que depende de la hora a la
# que corre pasa todo el dia y falla de madrugada, que es justo cuando nadie
# lo esta mirando.
DIA = datetime(2026, 9, 23, 10, 0)          # media manana, fuera del silencio
DIA_10 = datetime(2026, 9, 23, 10, 10)      # la vuelta siguiente (intervalo cumplido)
DIA_20 = datetime(2026, 9, 23, 10, 20)      # y la que le sigue
NOCHE = datetime(2026, 9, 23, 23, 0)        # adentro de las horas de silencio
MANANA = datetime(2026, 9, 24, 7, 30)       # despues del silencio


def item(titulo='Partida vencida', severidad='peligro',
         detalle='Freezer · 180 ml · vence en 3 días',
         url='/lactancia', modulo='lactancia', modulo_nombre='Lactancia',
         icono='\U0001f37c'):
    """Un item con el contrato CERRADO de 7 claves (CONTEXT_NOTIFICATIONS.md
    seccion 2). El motor LEE esto, no lo modifica."""
    return {
        'modulo': modulo,
        'modulo_nombre': modulo_nombre,
        'icono': icono,
        'titulo': titulo,
        'detalle': detalle,
        'url': url,
        'severidad': severidad,
    }


def provider(*items):
    """Un provider falso que devuelve siempre los mismos items."""
    return lambda: list(items)


class BaseEncendido(unittest.TestCase):
    """
    Motor encendido, envio MOCKEADO, disco temporal y reloj a mano.

    NADA DE RED: se mockea `_push_enviar` (no `webpush`) y se lo hace siempre
    igual en todo el archivo. Lo que estos tests miran es la DECISION —quien
    sale, cuando y con que payload—; que el envio sepa hablar con FCM ya esta
    probado en tests/test_push_envio.py.

    `_get_backup_dir` apunta a un tmp: push_estado.json vive junto a los
    backups, asi que sin el parche estos tests escribirian en la carpeta de
    backups de verdad de la maquina.
    """

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix='fondo-push-on-')
        self._p_dir = unittest.mock.patch.object(
            app_module, '_get_backup_dir', lambda: self._dir)
        self._p_dir.start()

        self.logs = []
        self._p_log = unittest.mock.patch.object(
            app_module, 'log', self.logs.append)
        self._p_log.start()

        # Lo ya dicho hoy es un global: sin esto, un test le deja la fecha
        # puesta al siguiente y la linea no aparece donde se la espera.
        app_module._push_seco_dicho.clear()

        # La config se parchea entera y se puede editar EN CALIENTE desde cada
        # test (`self.cfg[...] = ...`), que es como se lee en produccion.
        self.cfg = dict(config.DEFAULTS)
        self.cfg.update({
            'push_enabled': True,
            'push_vapid_publica': VAPID_PUB,
            'push_vapid_secreta': VAPID_SEC,
            'push_contacto_mailto': VAPID_MAIL,
        })
        self._p_cfg = unittest.mock.patch.object(
            config, 'cargar_config', lambda ruta=None: dict(self.cfg))
        self._p_cfg.start()

        self.suscripciones = list(FILAS)
        self._p_subs = unittest.mock.patch.object(
            database, 'obtener_suscripciones_push',
            lambda: list(self.suscripciones))
        self._p_subs.start()

        self.mandados = []      # (filas, payload, cfg, ttl) por llamada
        self.explota = None     # una excepcion para el proximo envio
        self._p_env = unittest.mock.patch.object(
            app_module, '_push_enviar', self._enviar)
        self._p_env.start()

    def tearDown(self):
        self._p_env.stop()
        self._p_subs.stop()
        self._p_cfg.stop()
        self._p_log.stop()
        self._p_dir.stop()
        shutil.rmtree(self._dir, ignore_errors=True)

    # -- El envio falso -------------------------------------------------------

    def _enviar(self, filas, payload, cfg=None, ttl=None):
        if self.explota is not None:
            raise self.explota
        self.mandados.append({'filas': list(filas), 'payload': payload,
                              'cfg': cfg, 'ttl': ttl})
        return len(filas), 0

    # -- Atajos ---------------------------------------------------------------

    def ciclo(self, *pares, **kw):
        """Una vuelta del motor con esos providers, a la hora que se pida."""
        hora = kw.pop('hora', DIA)
        with unittest.mock.patch.object(app_module, 'PUSH_AVISOS', list(pares)):
            return app_module._push_ciclo(hora)

    def estado(self):
        with io.open(os.path.join(self._dir, 'push_estado.json'),
                     encoding='utf-8') as f:
            return json.load(f)

    def escribir_estado(self, contenido):
        with io.open(os.path.join(self._dir, 'push_estado.json'),
                     'w', encoding='utf-8') as f:
            f.write(json.dumps(contenido, ensure_ascii=False))

    def secas(self):
        """Las lineas del ensayo en seco ('esto se mandaria')."""
        return [l for l in self.logs if l.startswith('SECO:')]

    def mandadas(self):
        """Las lineas del motor encendido ('esto se mando')."""
        return [l for l in self.logs if l.startswith('PUSH:')]

    def avisadas(self):
        return self.estado()['avisadas']


CLAVE = 'lactancia|peligro|Partida vencida'


# -- 1. El interruptor -------------------------------------------------------

class TestElInterruptor(BaseEncendido):
    """
    `push_enabled` es un kill switch, y un kill switch tiene dos requisitos:
    que apagado NO pase nada, y que se pueda apagar SIN reiniciar el servicio.
    Los dos se congelan aca.
    """

    def test_apagado_no_manda_nada_y_la_linea_seco_sale_igual(self):
        """
        Esto NO es negociable: el ensayo en seco corre en produccion y tiene
        que seguir corriendo tal cual despues de esta etapa. Si la linea
        `SECO:` cambia o deja de salir, el conteo de 72 h que decide si esto
        se enciende queda sin datos.
        """
        self.cfg['push_enabled'] = False
        self.ciclo(('lactancia', provider()))              # siembra
        nuevas = self.ciclo(('lactancia', provider(item())))

        self.assertEqual(nuevas, [CLAVE])
        self.assertEqual(self.mandados, [])
        self.assertEqual(len(self.secas()), 1)
        self.assertIn(CLAVE, self.secas()[0])

    def test_apagado_marca_el_estado_igual_que_antes(self):
        """Si no marcara, la misma clave se reportaria cada 10 minutos y el
        log del ensayo no diria nada util."""
        self.cfg['push_enabled'] = False
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item())))
        self.assertEqual(self.avisadas(), [CLAVE])
        # En seco no se gasta cupo: el ensayo no manda nada.
        self.assertEqual(self.estado()['enviados_hoy'], 0)

    def test_encendido_manda_una_vez_con_el_payload_del_flanco(self):
        self.ciclo(('lactancia', provider()))              # siembra
        nuevas = self.ciclo(('lactancia', provider(item())))

        self.assertEqual(nuevas, [CLAVE])
        self.assertEqual(len(self.mandados), 1)
        payload = self.mandados[0]['payload']
        self.assertEqual(payload['titulo'], 'Partida vencida')
        self.assertEqual(payload['cuerpo'], 'Lactancia')
        self.assertEqual(payload['url'], '/lactancia')
        # Encendido la linea cambia de token: las dos etapas no se mezclan al
        # contar en el log.
        self.assertEqual(self.secas(), [])
        self.assertEqual(len(self.mandadas()), 1)

    def test_el_nivel_sostenido_no_vuelve_a_sonar(self):
        """La partida sigue vencida dentro de 10 minutos, y dentro de una
        semana. La campana es un NIVEL; el push es un FLANCO."""
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item())))
        self.ciclo(('lactancia', provider(item())))
        self.ciclo(('lactancia', provider(item())))
        self.assertEqual(len(self.mandados), 1)

    def test_un_false_entre_comillas_NO_prende_nada(self):
        """
        `"false"` es un string no vacío, y con un `bool()` prendería los avisos
        — el peor resultado posible para un interruptor de pánico. Se lee con
        `is True`, igual que `sw_enabled` y `auth_disabled`.
        """
        for valor in ('false', 'true', 1, 'sí', None, ''):
            with self.subTest(valor=valor):
                self.assertFalse(
                    app_module._push_encendido({'push_enabled': valor}))
        self.assertTrue(app_module._push_encendido({'push_enabled': True}))

    def test_el_flag_se_lee_en_caliente(self):
        """Apagarlo es editar config.json, sin deploy y sin reiniciar el
        servicio. Un flag leido al importar no es un kill switch."""
        self.ciclo(('lactancia', provider()))              # siembra
        self.cfg['push_enabled'] = False
        self.ciclo(('lactancia', provider(item())))
        self.assertEqual(self.mandados, [])

        self.cfg['push_enabled'] = True
        self.ciclo(('lactancia', provider(item(titulo='Otra'))))
        self.assertEqual(len(self.mandados), 1)


# -- 2. Las horas de silencio ------------------------------------------------

class TestVentanaQueCruzaLaMedianoche(unittest.TestCase):
    """
    El unico bug posible de `_push_en_silencio`, y no se ve leyendo el codigo:
    se ve la primera noche. 22:30-07:00 escrito como `desde <= hora <= hasta`
    no silencia NUNCA, porque no hay ninguna hora que sea a la vez mayor que
    22:30 y menor que 07:00.
    """

    def cfg(self, desde='22:30', hasta='07:00'):
        return {'push_silencio_desde': desde, 'push_silencio_hasta': hasta}

    def hora(self, hhmm):
        hh, mm = hhmm.split(':')
        return datetime(2026, 9, 23, int(hh), int(mm))

    def test_las_horas_de_la_noche_estan_calladas(self):
        for hhmm in ('22:30', '23:00', '00:00', '02:00', '06:59'):
            with self.subTest(hora=hhmm):
                self.assertTrue(
                    app_module._push_en_silencio(self.hora(hhmm), self.cfg()))

    def test_las_horas_del_dia_no(self):
        """07:00 y 22:29 son los bordes: el minuto de adentro y el de afuera."""
        for hhmm in ('07:00', '07:01', '12:00', '21:00', '22:29'):
            with self.subTest(hora=hhmm):
                self.assertFalse(
                    app_module._push_en_silencio(self.hora(hhmm), self.cfg()))

    def test_una_ventana_que_NO_cruza_tambien_anda(self):
        """El dia que alguien configure 13:00-15:00 tiene que funcionar sin
        que nadie se acuerde de que existe la otra rama."""
        ventana = self.cfg('13:00', '15:00')
        self.assertTrue(app_module._push_en_silencio(self.hora('14:00'), ventana))
        self.assertFalse(app_module._push_en_silencio(self.hora('12:59'), ventana))
        self.assertFalse(app_module._push_en_silencio(self.hora('15:00'), ventana))
        self.assertFalse(app_module._push_en_silencio(self.hora('23:00'), ventana))

    def test_las_dos_horas_iguales_es_ventana_vacia(self):
        """
        Caso ambiguo decidido A MANO: iguales = NUNCA hay silencio. El otro
        significado posible ("silencio las 24 horas") apagaria los avisos
        enteros con un typo, en silencio y sin que nadie se entere. Para no
        recibir nada esta `push_enabled`, que se ve.
        """
        ventana = self.cfg('08:00', '08:00')
        for hhmm in ('07:59', '08:00', '08:01', '23:00'):
            with self.subTest(hora=hhmm):
                self.assertFalse(
                    app_module._push_en_silencio(self.hora(hhmm), ventana))

    def test_una_hora_corrupta_cae_al_default(self):
        """Un typo en config.json no puede dejar la noche sin proteccion."""
        roto = {'push_silencio_desde': 'veintidos y media',
                'push_silencio_hasta': ''}
        self.assertEqual(app_module._push_horas_silencio(roto),
                         (config.DEFAULTS['push_silencio_desde'],
                          config.DEFAULTS['push_silencio_hasta']))
        self.assertTrue(app_module._push_en_silencio(self.hora('03:00'), roto))


class TestSilencio(BaseEncendido):

    def test_un_flanco_de_noche_no_se_manda_NI_SE_MARCA(self):
        """
        Lo segundo importa mas que lo primero: si se marcara, el aviso
        quedaria consumido y a las 07:00 no saldria nunca. NO HAY COLA en
        ningun lado — lo que difiere el aviso es justamente que el estado no
        lo vio pasar.
        """
        self.ciclo(('lactancia', provider()), hora=DIA)          # siembra
        nuevas = self.ciclo(('lactancia', provider(item())), hora=NOCHE)

        self.assertEqual(nuevas, [])
        self.assertEqual(self.mandados, [])
        self.assertEqual(self.avisadas(), [])

    def test_el_mismo_flanco_a_la_manana_si_sale(self):
        self.ciclo(('lactancia', provider()), hora=DIA)
        self.ciclo(('lactancia', provider(item())), hora=NOCHE)
        nuevas = self.ciclo(('lactancia', provider(item())), hora=MANANA)

        self.assertEqual(nuevas, [CLAVE])
        self.assertEqual(len(self.mandados), 1)
        self.assertEqual(self.avisadas(), [CLAVE])

    def test_la_condicion_que_se_va_de_noche_no_suena_NUNCA(self):
        """
        LA CONSECUENCIA MAS LINDA DEL DISENO, y por eso tiene test propio: a
        las 07:00 el motor no destapa una cola, vuelve a leer el nivel REAL.
        Si la bolsita se uso a las 2 de la manana, el aviso de las 23:00 no
        existe mas. Nadie se despierta con la novedad de algo ya resuelto.
        """
        self.ciclo(('lactancia', provider()), hora=DIA)
        self.ciclo(('lactancia', provider(item())), hora=NOCHE)
        self.ciclo(('lactancia', provider()), hora=MANANA)   # ya no pasa nada

        self.assertEqual(self.mandados, [])
        self.assertEqual(self.avisadas(), [])

    def test_el_silencio_no_es_silencioso_en_el_log(self):
        """Retener algo y no decirlo es como no tener el freno: cuando falte
        un aviso no hay forma de saber si fue esto o un bug."""
        self.ciclo(('lactancia', provider()), hora=DIA)
        self.ciclo(('lactancia', provider(item())), hora=NOCHE)
        dichas = [l for l in self.logs if 'silencio' in l]
        self.assertEqual(len(dichas), 1)
        self.assertIn('22:30', dichas[0])

    def test_en_seco_el_silencio_no_se_aplica(self):
        """El ensayo mide la frecuencia BRUTA: uno que ya viene recortado no
        contesta la pregunta que se le hace."""
        self.cfg['push_enabled'] = False
        self.ciclo(('lactancia', provider()), hora=DIA)
        nuevas = self.ciclo(('lactancia', provider(item())), hora=NOCHE)
        self.assertEqual(nuevas, [CLAVE])
        self.assertEqual(len(self.secas()), 1)


# -- 3. Los topes ------------------------------------------------------------

def cinco():
    """Cinco avisos distintos que aparecen todos en la misma vuelta. Pasa de
    verdad: un provider que se desbloquea despues de una semana roto, o varias
    partidas que vencen el mismo dia."""
    return provider(*[item(titulo='Aviso %d' % n) for n in range(1, 6)])


class TestTopes(BaseEncendido):

    def claves(self, *numeros):
        return ['lactancia|peligro|Aviso %d' % n for n in numeros]

    def test_tope_por_vuelta(self):
        self.ciclo(('lactancia', provider()))              # siembra
        nuevas = self.ciclo(('lactancia', cinco()))

        self.assertEqual(len(self.mandados), app_module._PUSH_TOPE_VUELTA)
        self.assertEqual(nuevas, self.claves(1, 2, 3))
        # Los dos que no entraron NO se marcan: siguen siendo flanco.
        self.assertEqual(self.avisadas(), self.claves(1, 2, 3))

    def test_lo_retenido_sale_en_la_vuelta_siguiente(self):
        """Es un goteo, no un descarte. Las vueltas van separadas 10 min de
        verdad: pegadas las frena el intervalo (ver TestNoDeGolpe)."""
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', cinco()), hora=DIA_10)
        nuevas = self.ciclo(('lactancia', cinco()), hora=DIA_20)

        self.assertEqual(nuevas, self.claves(4, 5))
        self.assertEqual(len(self.mandados), 5)
        self.assertEqual(self.avisadas(), self.claves(1, 2, 3, 4, 5))

    def test_el_tope_de_vuelta_lo_dice_en_el_log(self):
        self.ciclo(('lactancia', provider()))
        del self.logs[:]
        self.ciclo(('lactancia', cinco()))
        retencion = [l for l in self.logs
                     if l.startswith('AVISO:') and 'vuelta' in l]
        self.assertEqual(len(retencion), 1)

    def test_llegado_al_tope_del_dia_no_se_manda_mas(self):
        self.escribir_estado({'avisadas': [], 'actualizado': DIA.isoformat(),
                              'dia': DIA.date().isoformat(),
                              'enviados_hoy': app_module._PUSH_TOPE_DIA})
        nuevas = self.ciclo(('lactancia', provider(item())))

        self.assertEqual(nuevas, [])
        self.assertEqual(self.mandados, [])
        self.assertEqual(self.avisadas(), [])

    def test_el_tope_del_dia_se_dice_una_vez_por_dia(self):
        """Dura horas y el scheduler corre 144 veces: sin `_push_seco_decir`
        serian 100 lineas identicas tapando el resto del log."""
        self.escribir_estado({'avisadas': [], 'actualizado': DIA.isoformat(),
                              'dia': DIA.date().isoformat(),
                              'enviados_hoy': app_module._PUSH_TOPE_DIA})
        for _ in range(4):
            self.ciclo(('lactancia', provider(item())))
        dichas = [l for l in self.logs if 'tope de' in l]
        self.assertEqual(len(dichas), 1)

    def test_al_cambiar_el_dia_se_resetea(self):
        self.escribir_estado({'avisadas': [], 'actualizado': '2026-09-22T23:59:00',
                              'dia': '2026-09-22',
                              'enviados_hoy': app_module._PUSH_TOPE_DIA})
        nuevas = self.ciclo(('lactancia', provider(item())), hora=DIA)

        self.assertEqual(nuevas, [CLAVE])
        self.assertEqual(len(self.mandados), 1)
        self.assertEqual(self.estado()['dia'], '2026-09-23')
        self.assertEqual(self.estado()['enviados_hoy'], 1)

    def test_el_cupo_del_dia_le_gana_al_de_la_vuelta(self):
        """Con 6 mandados hoy quedan 2, no 3."""
        self.escribir_estado({'avisadas': [], 'actualizado': DIA.isoformat(),
                              'dia': DIA.date().isoformat(),
                              'enviados_hoy': app_module._PUSH_TOPE_DIA - 2})
        nuevas = self.ciclo(('lactancia', cinco()))
        self.assertEqual(len(nuevas), 2)
        self.assertEqual(self.estado()['enviados_hoy'],
                         app_module._PUSH_TOPE_DIA)


# -- 4. El archivo de estado de la etapa anterior ----------------------------

class TestEstadoDeLaEtapaAnterior(BaseEncendido):
    """
    En produccion push_estado.json YA EXISTE, escrito por el ensayo en seco,
    con la forma vieja: `avisadas` y `actualizado`, sin `dia` ni
    `enviados_hoy`. Un motor que explota la primera vuelta despues de un
    deploy es un motor que no arranca nunca — y encima lo hace en el hilo de
    fondo, que se muere sin avisarle a nadie.
    """

    def test_un_estado_viejo_no_rompe_y_no_re_anuncia(self):
        self.escribir_estado({'avisadas': [CLAVE],
                              'actualizado': '2026-09-22T10:00:00'})
        nuevas = self.ciclo(('lactancia', provider(item())))

        self.assertEqual(nuevas, [])
        self.assertEqual(self.mandados, [])
        self.assertEqual(self.avisadas(), [CLAVE])

    def test_un_estado_viejo_arranca_el_conteo_en_cero(self):
        """Sin `dia` se lo trata como un dia distinto: el tope diario nace
        entero, no a medias. Es el default seguro."""
        self.escribir_estado({'avisadas': [],
                              'actualizado': '2026-09-22T10:00:00'})
        self.ciclo(('lactancia', provider(item())))
        self.assertEqual(self.estado()['enviados_hoy'], 1)
        self.assertEqual(self.estado()['dia'], '2026-09-23')

    def test_el_estado_nuevo_tiene_sus_claves(self):
        self.ciclo(('lactancia', provider(item())))        # siembra
        self.assertEqual(sorted(self.estado()),
                         ['actualizado', 'avisadas', 'dia', 'diferidas',
                          'enviados_hoy', 'ultima_tanda'])

    def test_un_estado_sin_ultima_tanda_no_frena_nada(self):
        """El archivo de la etapa anterior no la tiene. Ausente = "hace
        mucho": el default seguro aca es DEJAR mandar, porque lo contrario es
        un motor que despues de un deploy no arranca nunca."""
        self.escribir_estado({'avisadas': [], 'dia': '2026-09-23',
                              'enviados_hoy': 0,
                              'actualizado': '2026-09-23T09:00:00'})
        self.ciclo(('lactancia', provider(item())))
        self.assertEqual(len(self.mandados), 1)


# -- 5. Las claves VAPID rotas o ausentes ------------------------------------

class TestSinClaves(BaseEncendido):
    """
    SI SE MARCARAN, el estado consumiria en silencio todos los flancos
    mientras la config esta rota, y el dia que se arregle el motor diria "ya
    avise todo" — sin que nunca hubiera sonado nada, y sin forma de darse
    cuenta. Dejando el flanco pendiente, lo primero que pasa despues de
    arreglar la config es un aviso de verdad, que es tambien la prueba de que
    el canal anda.
    """

    def sin_claves(self):
        self.cfg['push_vapid_secreta'] = ''
        self.cfg['push_vapid_publica'] = ''
        self.cfg['push_contacto_mailto'] = ''

    def test_no_se_manda_y_no_se_marca(self):
        self.ciclo(('lactancia', provider()))              # siembra
        self.sin_claves()
        nuevas = self.ciclo(('lactancia', provider(item())))

        self.assertEqual(nuevas, [])
        self.assertEqual(self.mandados, [])
        self.assertEqual(self.avisadas(), [])

    def test_lo_dice_una_vez_por_dia(self):
        self.ciclo(('lactancia', provider()))
        self.sin_claves()
        del self.logs[:]
        for _ in range(5):
            self.ciclo(('lactancia', provider(item())))
        avisos = [l for l in self.logs if 'VAPID' in l]
        self.assertEqual(len(avisos), 1)

    def test_cuando_se_arregla_la_config_el_flanco_sale(self):
        self.ciclo(('lactancia', provider()))
        self.sin_claves()
        self.ciclo(('lactancia', provider(item())))
        self.assertEqual(self.mandados, [])

        self.cfg.update({'push_vapid_publica': VAPID_PUB,
                         'push_vapid_secreta': VAPID_SEC,
                         'push_contacto_mailto': VAPID_MAIL})
        nuevas = self.ciclo(('lactancia', provider(item())))
        self.assertEqual(nuevas, [CLAVE])
        self.assertEqual(len(self.mandados), 1)

    def test_una_clave_rota_se_trata_igual_que_una_ausente(self):
        """Que la clave ESTE no quiere decir que SIRVA: una mal copiada o
        truncada revienta al deserializarla."""
        self.ciclo(('lactancia', provider()))
        self.cfg['push_vapid_secreta'] = 'esto-no-es-una-clave'
        nuevas = self.ciclo(('lactancia', provider(item())))
        self.assertEqual(nuevas, [])
        self.assertEqual(self.avisadas(), [])


# -- 6. A quien se le manda --------------------------------------------------

class TestAQuienSeLeManda(BaseEncendido):

    def test_a_todas_las_suscripciones(self):
        """
        ES UNA DECISION, NO UN DESCUIDO: es una casa de dos, y lo que se avisa
        hoy —leche que se vence, bolsitas para bajar— le importa a los dos por
        igual. El dia que aparezca un aviso que sea de UNO SOLO, este test es
        el que hay que venir a cambiar.
        """
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item())))
        enviadas = self.mandados[0]['filas']
        self.assertEqual(len(enviadas), len(FILAS))
        self.assertEqual(sorted(f['persona'] for f in enviadas),
                         ['elias', 'mari'])

    def test_sin_dispositivos_no_se_marca_nada(self):
        """Nadie activo los avisos todavia: no sono en ningun lado, asi que el
        nivel sigue siendo una novedad para el primero que se suscriba."""
        self.suscripciones = []
        self.ciclo(('lactancia', provider()))
        nuevas = self.ciclo(('lactancia', provider(item())))

        self.assertEqual(nuevas, [])
        self.assertEqual(self.avisadas(), [])
        self.assertTrue(any('dispositivo' in l for l in self.logs))


# -- 7. Lo que viaja ---------------------------------------------------------

class TestLoQueViaja(BaseEncendido):

    def test_el_ttl_es_el_de_los_avisos_y_no_el_del_boton(self):
        """
        El del boton son 60 s a proposito: un "anda a Settings" que llega
        media hora despues no le sirve a nadie. Un aviso automatico tiene que
        aguantar el subte y la notebook cerrada, pero sin cruzar la noche
        entera — si no, el servicio de push se saltearia las horas de silencio
        por nosotros.
        """
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item())))
        self.assertEqual(self.mandados[0]['ttl'], app_module._PUSH_TTL_AVISO)
        self.assertNotEqual(app_module._PUSH_TTL_AVISO, app_module._PUSH_TTL)
        self.assertGreater(app_module._PUSH_TTL_AVISO, app_module._PUSH_TTL)

    def test_el_payload_no_lleva_el_detalle_del_item(self):
        """El `detalle` lleva el volumen en ml, y el cuerpo se lee en la
        PANTALLA BLOQUEADA. La regla del payload no se negocia."""
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item(detalle='Freezer · 180 ml'))))
        texto = json.dumps(self.mandados[0]['payload'], ensure_ascii=False)
        self.assertNotIn('180', texto)
        self.assertNotIn('ml', texto)

    def test_tres_claves_y_la_url_relativa(self):
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item())))
        payload = self.mandados[0]['payload']
        self.assertEqual(tuple(sorted(payload)),
                         tuple(sorted(app_module._PUSH_PAYLOAD_CLAVES)))
        self.assertTrue(payload['url'].startswith('/'))

    def test_el_log_del_envio_tampoco_lleva_el_detalle(self):
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item(detalle='Freezer · 180 ml'))))
        self.assertNotIn('180', ' '.join(self.logs))

    def test_un_envio_que_falla_no_tumba_la_vuelta(self):
        """
        Ya quedo marcado y no se deshace: reintentar es el camino a mandar dos
        veces lo mismo. El dato sigue estando en la campana — un push que no
        llego NO es informacion perdida.
        """
        self.ciclo(('lactancia', provider()))
        self.explota = RuntimeError('la red se cayo')
        nuevas = self.ciclo(('lactancia', provider(item())))

        self.assertEqual(nuevas, [CLAVE])
        self.assertEqual(self.avisadas(), [CLAVE])
        self.assertTrue(any(l.startswith('AVISO:') and 'RuntimeError' in l
                            for l in self.logs))


# -- 9. La hora mal escrita (el bug que invierte la ventana) -----------------

class TestHoraMalEscrita(BaseEncendido):
    """
    `strptime("7:00", "%H:%M")` NO tira: `%H` acepta un solo digito. Asi que
    validar sin NORMALIZAR dejaba pasar "7:00" tal cual, y como
    `_push_en_silencio` compara STRINGS de largo fijo, `'22:30' < '7:00'` da
    True: la ventana se lee como si no cruzara la medianoche y la madrugada
    entera queda sin silencio. El telefono suena a las 3 AM con un config.json
    que se ve perfecto y sin una linea en el log.

    Escribir "7:00" en vez de "07:00" es la forma NATURAL de escribir las
    siete, y este archivo se edita a mano porque las horas de silencio no
    tienen UI. Por eso el test.
    """

    def hora(self, hhmm):
        hh, mm = hhmm.split(':')
        return datetime(2026, 9, 23, int(hh), int(mm))

    def test_la_hora_se_normaliza(self):
        for crudo, esperado in (('7:00', '07:00'), ('07:0', '07:00'),
                                (' 07:00 ', '07:00'), ('7:5', '07:05'),
                                ('22:30', '22:30')):
            with self.subTest(crudo=crudo):
                _, hasta = app_module._push_horas_silencio(
                    {'push_silencio_desde': '22:30',
                     'push_silencio_hasta': crudo})
                self.assertEqual(hasta, esperado)

    def test_la_madrugada_sigue_callada_con_la_hora_sin_cero(self):
        ventana = {'push_silencio_desde': '22:30', 'push_silencio_hasta': '7:00'}
        for hhmm in ('23:00', '00:00', '02:00', '06:59'):
            with self.subTest(hora=hhmm):
                self.assertTrue(app_module._push_en_silencio(
                    self.hora(hhmm), ventana))
        self.assertFalse(app_module._push_en_silencio(
            self.hora('07:00'), ventana))

    def test_de_punta_a_punta_no_suena_a_las_tres(self):
        self.cfg['push_silencio_hasta'] = '7:00'
        self.ciclo(('lactancia', provider()), hora=DIA)
        self.ciclo(('lactancia', provider(item())),
                   hora=datetime(2026, 9, 24, 3, 0))
        self.assertEqual(self.mandados, [])

    def test_una_hora_de_verdad_corrupta_sigue_cayendo_al_default(self):
        for basura in ('mediodia', '25:00', '', '12:99'):
            with self.subTest(basura=basura):
                desde, _ = app_module._push_horas_silencio(
                    {'push_silencio_desde': basura,
                     'push_silencio_hasta': '07:00'})
                self.assertEqual(desde, config.DEFAULTS['push_silencio_desde'])


# -- 10. Ocho avisos en un minuto: el servicio que reinicia en loop ----------

class TestNoDeGolpe(BaseEncendido):
    """
    El tope por vuelta es POR LLAMADA, no por tiempo, y `_push_ciclo()` corre
    una vez por ARRANQUE de proceso (el sleep va al final del loop). Un
    servicio que reinicia en loop —el puerto tomado por un python viejo, NSSM
    reintentando cada 30 s, un reboot con arranques encadenados— dispara una
    vuelta entera por reinicio. Sin este freno: 3 + 3 + 2 en SESENTA SEGUNDOS,
    que es justo el goteo que el tope existe para producir.
    """

    def test_dos_vueltas_pegadas_no_mandan_dos_veces(self):
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', cinco()), hora=DIA)
        del self.mandados[:]
        # 30 segundos despues: NSSM reintento.
        nuevas = self.ciclo(('lactancia', cinco()),
                            hora=datetime(2026, 9, 23, 10, 0, 30))
        self.assertEqual(self.mandados, [])
        self.assertEqual(nuevas, [])

    def test_lo_retenido_por_el_intervalo_no_se_marca(self):
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', cinco()), hora=DIA)
        avisadas_antes = self.avisadas()
        self.ciclo(('lactancia', cinco()),
                   hora=datetime(2026, 9, 23, 10, 0, 30))
        self.assertEqual(self.avisadas(), avisadas_antes)

    def test_cumplido_el_intervalo_sale(self):
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', cinco()), hora=DIA)
        del self.mandados[:]
        nuevas = self.ciclo(('lactancia', cinco()), hora=DIA_10)
        self.assertEqual(len(self.mandados), 2)
        self.assertEqual(len(nuevas), 2)

    def test_la_marca_es_de_cuando_SONO_no_de_cuando_corrio_el_hilo(self):
        """Una vuelta que no mando nada no puede consumir el intervalo: si no,
        el motor quedaria trabado detras de sus propias vueltas vacias."""
        self.ciclo(('lactancia', provider()))              # siembra, no manda
        self.assertIsNone(self.estado()['ultima_tanda'])
        self.ciclo(('lactancia', provider(item())), hora=DIA)
        self.assertIsNotNone(self.estado()['ultima_tanda'])


# -- 11. Lo que se retiene, se dice ------------------------------------------

class TestLoRetenidoSeDice(BaseEncendido):

    def test_un_segundo_aviso_retenido_el_mismo_dia_vuelve_a_hablar(self):
        """El token lleva las CLAVES, no solo el motivo. Con un token fijo, el
        segundo aviso retenido la misma noche no dejaba NI UNA linea: el token
        ya estaba gastado y el latido tambien. Contestar "por que no me llego
        el aviso de anoche" desde el log se volvia imposible."""
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item())), hora=NOCHE)
        del self.logs[:]
        self.ciclo(('lactancia', provider(item(), item(titulo='Otra'))),
                   hora=datetime(2026, 9, 23, 23, 30))
        self.assertTrue(any('Otra' in l for l in self.logs))

    def test_la_misma_retencion_repetida_se_dice_una_sola_vez(self):
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item())), hora=NOCHE)
        del self.logs[:]
        for minuto in (10, 20, 30, 40):
            self.ciclo(('lactancia', provider(item())),
                       hora=datetime(2026, 9, 23, 23, minuto))
        self.assertEqual(self.logs, [])

    def test_el_latido_no_dice_sin_flancos_si_hubo_retenidos(self):
        """Decia "sin flancos nuevos" habiendo cinco pendientes, a veces en la
        linea de al lado del aviso de que se habian retenido."""
        self.ciclo(('lactancia', provider()))
        del self.logs[:]
        self.ciclo(('lactancia', provider(item())), hora=NOCHE)
        self.assertFalse(any('sin flancos nuevos' in l for l in self.logs))

    def test_el_tope_por_vuelta_no_se_loguea_si_al_final_no_salio_nada(self):
        """La linea vivia ARRIBA de los gates de VAPID y dispositivos, que
        despues podian vaciar `a_mandar`: decia "salen 3 aviso(s)" 144 veces
        por dia con cero avisos mandados."""
        self.cfg['push_vapid_secreta'] = ''
        self.ciclo(('lactancia', provider()))
        del self.logs[:]
        self.ciclo(('lactancia', cinco()))
        self.assertFalse(any('salen 3' in l for l in self.logs))
        self.assertTrue(any('PENDIENTES' in l for l in self.logs))


# -- 12. El TTL recortado contra el silencio ---------------------------------

class TestTTLContraElSilencio(BaseEncendido):
    """
    El freno del silencio actua sobre el ENVIO, y el envio no es la entrega.
    Un aviso que sale 22:29 con TTL de 2 h y encuentra el telefono apagado se
    lo queda FCM y lo entrega a las 00:29 — dos horas adentro de la ventana
    que existe para que eso no pase.
    """

    def test_lejos_del_silencio_va_el_ttl_entero(self):
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item())), hora=DIA)
        self.assertEqual(self.mandados[0]['ttl'], app_module._PUSH_TTL_AVISO)

    def test_en_la_puerta_del_silencio_se_recorta(self):
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item())),
                   hora=datetime(2026, 9, 23, 22, 29))
        self.assertEqual(self.mandados[0]['ttl'], 60)

    def test_nunca_es_el_ttl_del_boton(self):
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item())), hora=DIA)
        self.assertNotEqual(self.mandados[0]['ttl'], app_module._PUSH_TTL)

    def test_con_la_ventana_vacia_no_hay_nada_que_recortar(self):
        self.cfg['push_silencio_hasta'] = self.cfg['push_silencio_desde']
        self.assertEqual(
            app_module._push_ttl_efectivo(datetime(2026, 9, 23, 22, 29),
                                          self.cfg),
            app_module._PUSH_TTL_AVISO)


# -- 13. Lo que no sono, no se da por avisado --------------------------------

class TestNoSeQuemaSinSonar(BaseEncendido):

    def test_un_payload_roto_no_quema_el_aviso(self):
        """Mismo criterio que las VAPID, que estaba aplicado al reves: una
        clave de `sin_payload` no era candidata, no entraba en `retenidas`, y
        por lo tanto SI entraba en `marcadas` — quemada para siempre sin haber
        sonado nunca. El dia que alguien arregle la url del provider, esa
        clave ya figura como avisada y no vuelve a ser flanco."""
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item(url='https://ejemplo.com/x'))),
                   hora=DIA)
        self.assertEqual(self.avisadas(), [])
        # Y cuando se arregla la url, SI suena.
        nuevas = self.ciclo(('lactancia', provider(item(url='/lactancia'))),
                            hora=DIA_10)
        self.assertEqual(nuevas, [CLAVE])

    def test_si_no_entro_en_ninguno_el_log_no_dice_mandado(self):
        """'aviso mandado (entregado en 0 dispositivo(s))' se contradice a si
        mismo en la misma linea, y es justo la linea que alguien va a grepear
        para contestar 'por que no me llego el aviso de anoche'."""
        self._p_env.stop()
        self._p_env = unittest.mock.patch.object(
            app_module, '_push_enviar', lambda *a, **k: (0, 0))
        self._p_env.start()
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item())), hora=DIA)
        self.assertTrue(any('SIN ENTREGAR' in l for l in self.logs))
        self.assertFalse(any('aviso mandado' in l for l in self.logs))


# -- 14. El aviso que se difiere TODAS las noches ----------------------------

class TestDiferimientoCronico(BaseEncendido):
    """
    El agujero que no deja rastro: un aviso cuya condicion SOLO es cierta
    adentro de las horas de silencio no sale nunca, y hasta ahora nadie se
    enteraba. `_lac_recordatorio_pendiente()` es cierto entre la hora
    configurada y la medianoche; esa hora es un campo de Settings. Puesta en
    23:00, con el silencio arrancando 22:30: a las 23:00 se retiene, a las
    00:00 la condicion desaparece, y a las 07:00 no queda nada que evaluar.
    Cero envios, para siempre.

    El diferimiento sigue SIN ser una cola — de `diferidas` no se manda nada,
    solo se habla.
    """

    def noche(self, dia, hora=23, minuto=0):
        return datetime(2026, 9, dia, hora, minuto)

    def test_la_primera_noche_todavia_no_se_queja(self):
        self.ciclo(('lactancia', provider()))
        del self.logs[:]
        self.ciclo(('lactancia', provider(item())), hora=self.noche(23))
        self.assertFalse(any('días anteriores' in l for l in self.logs))

    def test_la_segunda_noche_si(self):
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item())), hora=self.noche(23))
        del self.logs[:]
        self.ciclo(('lactancia', provider(item())), hora=self.noche(24))
        quejas = [l for l in self.logs if 'días anteriores' in l]
        self.assertEqual(len(quejas), 1)
        self.assertIn(CLAVE, quejas[0])
        self.assertIn('2026-09-23', quejas[0])

    def test_la_queja_dice_que_mirar(self):
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item())), hora=self.noche(23))
        self.ciclo(('lactancia', provider(item())), hora=self.noche(24))
        quejas = [l for l in self.logs if 'días anteriores' in l]
        self.assertIn('horas de silencio', quejas[0])

    def test_lo_que_sale_deja_de_figurar_como_diferido(self):
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item())), hora=self.noche(23))
        self.assertEqual(list(self.estado()['diferidas']), [CLAVE])
        # A la manana siguiente, fuera del silencio: sale.
        self.ciclo(('lactancia', provider(item())), hora=MANANA)
        self.assertEqual(self.estado()['diferidas'], {})
        self.assertEqual(len(self.mandados), 1)

    def test_en_seco_no_se_difiere_nada(self):
        """Apagado no hay frenos, asi que tampoco hay diferidas que contar."""
        self.cfg['push_enabled'] = False
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item())), hora=self.noche(23))
        self.assertEqual(self.estado()['diferidas'], {})
        self.assertEqual(len(self.secas()), 1)


if __name__ == '__main__':
    unittest.main()
