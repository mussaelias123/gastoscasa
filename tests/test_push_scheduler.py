# =============================================================================
# ARCHIVO: tests/test_push_scheduler.py
# =============================================================================
#
# Tests del MOTOR DE FLANCOS del push: el que decide CUANDO habria que mandar
# un aviso. Mientras dure el ensayo EN SECO no manda nada — escribe en el log
# lo que mandaria — pero la decision de cuando ya es esta, y es la que hay que
# congelar antes de que un telefono empiece a sonar.
#
# El envio en si esta en tests/test_push_envio.py; el alta/baja y la tabla, en
# tests/test_push_suscripciones.py; el service worker, en tests/test_sw.py.
#
# POR QUE EXISTE ESTE ARCHIVO
#
#   1. LA CAMPANA ES UN NIVEL, EL PUSH ES UN FLANCO. Los providers contestan
#      "hay algo?" cada vez que alguien mira: mientras la partida siga vencida
#      contestan que si para siempre. Mandar eso seria un pitido cada 10
#      minutos diciendo lo mismo. Se manda el FLANCO ASCENDENTE: cuando
#      aparece algo que antes no estaba. Cuando se va no suena nada, pero la
#      senal queda REARMADA. Es un deteccion de flanco de PLC con la marca de
#      memoria en un archivo.
#
#   2. EL CAMPO `detalle` NO ENTRA EN LA CLAVE, Y ES LA DECISION MAS FRAGIL DE
#      TODAS. `detalle` dice "vence en 3 dias", y manana dice "vence en 2
#      dias". Si formara parte de la clave, cada dia habria una clave "nueva"
#      para la MISMA bolsita: flanco ascendente falso, y el telefono sonando
#      todas las mananas por algo de lo que ya aviso. Nadie lo notaria leyendo
#      el codigo: se nota a la tercera manana. De ahi el test.
#
#   3. LA SIEMBRA. La primera vuelta no anuncia NADA: guarda lo que hay y
#      calla. Sin eso, el primer arranque despues de un deploy trataria todo
#      lo que ya estaba pendiente —semanas de cosas— como recien aparecido, y
#      seria una tanda de avisos de golpe cada vez que se reinicia el servicio.
#
#   4. EN SECO ES EN SECO. El scheduler no llama a `_push_enviar()` ni lee la
#      tabla de suscripciones. Eso se verifica explicitamente aca.
#
# COMO CORRER:
#   Desde la raiz del proyecto:
#       python -m unittest tests.test_push_scheduler -v
#
# =============================================================================

import io
import os
import sys
import json
import shutil
import inspect
import tempfile
import unittest
import unittest.mock
from datetime import date

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import app as app_module  # noqa: E402
import database  # noqa: E402


def item(titulo='Partida vencida', severidad='peligro',
         detalle='Freezer · 180 ml · vence en 3 días',
         url='/lactancia', modulo='lactancia', modulo_nombre='Lactancia',
         icono='\U0001f37c'):
    """Un item con el contrato CERRADO de 7 claves (CONTEXT_NOTIFICATIONS.md
    seccion 2). El scheduler LEE esto, no lo modifica."""
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


class BaseSeco(unittest.TestCase):
    """
    Directorio de estado TEMPORAL y log capturado.

    El directorio se pisa parcheando `_get_backup_dir()`: push_estado.json
    vive junto a los backups (ver el comentario del bloque en app.py), asi que
    sin este parche los tests escribirian en la carpeta de backups de verdad
    de la maquina.
    """

    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix='fondo-push-seco-')
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

    def tearDown(self):
        self._p_log.stop()
        self._p_dir.stop()
        shutil.rmtree(self._dir, ignore_errors=True)

    # -- Atajos ---------------------------------------------------------------

    def avisos(self, *pares):
        """Pisa PUSH_AVISOS con los pares (clave, provider) que se pasen."""
        return unittest.mock.patch.object(app_module, 'PUSH_AVISOS', list(pares))

    def ciclo(self, *pares):
        """Una vuelta del motor con esos providers. Devuelve las claves nuevas."""
        with self.avisos(*pares):
            return app_module._push_ciclo()

    def estado(self):
        ruta = os.path.join(self._dir, 'push_estado.json')
        with io.open(ruta, encoding='utf-8') as f:
            return json.load(f)

    def secas(self):
        """Las lineas de log del ensayo ('esto se mandaria')."""
        return [l for l in self.logs if l.startswith('SECO:')]


# -- 1. La siembra: la primera vuelta no despierta a nadie --------------------

class TestSiembra(BaseSeco):

    def test_la_primera_vuelta_no_anuncia_nada(self):
        """
        Aunque haya tres cosas vencidas hace semanas. Es el bit de primer scan
        del PLC: sin esto, cada reinicio del servicio seria una tanda de
        avisos de golpe.
        """
        nuevas = self.ciclo(('lactancia', provider(item(), item(titulo='Otra'))))
        self.assertEqual(nuevas, [])
        self.assertEqual(self.secas(), [])

    def test_la_siembra_deja_el_estado_escrito(self):
        self.ciclo(('lactancia', provider(item())))
        estado = self.estado()
        self.assertEqual(estado['avisadas'],
                         ['lactancia|peligro|Partida vencida'])
        self.assertIn('actualizado', estado)

    def test_la_siembra_se_loguea_una_vez_y_dice_cuantos(self):
        """Tiene que poder leerse suelta meses despues: si el log no dice que
        se sembro, el silencio del primer dia parece un hilo muerto."""
        self.ciclo(('lactancia', provider(item(), item(titulo='Otra'))))
        sembrado = [l for l in self.logs if 'sembr' in l]
        self.assertEqual(len(sembrado), 1)
        self.assertIn('2', sembrado[0])

    def test_estado_corrupto_se_comporta_como_primera_vuelta(self):
        """
        Un json roto (o vaciado a mano, o de otra version) NO puede tumbar el
        hilo ni, peor, tratarse como "no habia nada avisado" y disparar todo
        junto. Se vuelve a sembrar en silencio: perder un aviso es mucho mas
        barato que inventar una tanda.
        """
        with io.open(os.path.join(self._dir, 'push_estado.json'),
                     'w', encoding='utf-8') as f:
            f.write('{esto no es json, ')
        nuevas = self.ciclo(('lactancia', provider(item())))
        self.assertEqual(nuevas, [])
        self.assertEqual(self.secas(), [])
        self.assertEqual(self.estado()['avisadas'],
                         ['lactancia|peligro|Partida vencida'])

    def test_estado_con_json_valido_pero_sin_avisadas(self):
        """Mismo caso: un dict sin la clave es un estado que no sirve."""
        with io.open(os.path.join(self._dir, 'push_estado.json'),
                     'w', encoding='utf-8') as f:
            f.write('{"actualizado": "2026-09-23T10:00:00"}')
        self.assertEqual(self.ciclo(('lactancia', provider(item()))), [])
        self.assertEqual(self.secas(), [])


# -- 2. El flanco ------------------------------------------------------------

class TestFlanco(BaseSeco):

    def test_flanco_ascendente_anuncia_una_vez(self):
        self.ciclo(('lactancia', provider()))          # siembra, sin nada
        nuevas = self.ciclo(('lactancia', provider(item())))
        self.assertEqual(nuevas, ['lactancia|peligro|Partida vencida'])
        self.assertEqual(len(self.secas()), 1)

    def test_nivel_sostenido_no_vuelve_a_anunciar(self):
        """
        La partida sigue vencida en la vuelta siguiente. Si esto fallara, el
        telefono sonaria cada 10 minutos hasta que alguien la tire.
        """
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item())))
        nuevas = self.ciclo(('lactancia', provider(item())))
        self.assertEqual(nuevas, [])
        self.assertEqual(len(self.secas()), 1)

    def test_flanco_descendente_rearma(self):
        """
        Desaparece (se uso la bolsita) y vuelve a aparecer un mes despues:
        tiene que volver a avisar. Por eso el estado guarda las claves
        VIGENTES y no la union con las viejas — la union seria una senal que
        se enclava y no se suelta nunca.
        """
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item())))
        self.ciclo(('lactancia', provider()))                  # se va
        self.assertEqual(self.estado()['avisadas'], [])
        nuevas = self.ciclo(('lactancia', provider(item())))   # vuelve
        self.assertEqual(nuevas, ['lactancia|peligro|Partida vencida'])
        self.assertEqual(len(self.secas()), 2)

    def test_el_estado_guarda_las_vigentes_no_la_union(self):
        self.ciclo(('lactancia', provider(item(titulo='A'))))
        self.ciclo(('lactancia', provider(item(titulo='B'))))
        self.assertEqual(self.estado()['avisadas'], ['lactancia|peligro|B'])

    def test_el_detalle_que_cambia_no_dispara_flanco(self):
        """
        EL TEST QUE PROTEGE LA DECISION MAS FRAGIL. Mismo titulo, misma
        severidad, `detalle` que pasa de "vence en 3 dias" a "vence en 2
        dias": es LA MISMA bolsita, un dia despues. No es un aviso nuevo.
        """
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item(detalle='Freezer · 180 ml · vence en 3 días'))))
        nuevas = self.ciclo(('lactancia', provider(item(detalle='Freezer · 180 ml · vence en 2 días'))))
        self.assertEqual(nuevas, [])
        self.assertEqual(len(self.secas()), 1)

    def test_la_severidad_si_cambia_la_clave(self):
        """Una partida que pasa de "por vencer" a "vencida" es otra cosa, y
        merece su propio aviso: cambia el titulo Y la severidad."""
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item(titulo='Partida por vencer',
                                               severidad='alerta'))))
        nuevas = self.ciclo(('lactancia', provider(item())))
        self.assertEqual(nuevas, ['lactancia|peligro|Partida vencida'])


# -- 3. La agrupacion: un aviso es un grupo, no un item ----------------------

class TestAgrupacion(BaseSeco):

    def test_tres_items_iguales_son_un_solo_aviso(self):
        """
        Tres partidas vencidas = UN aviso. El payload no lleva plata ni
        detalle, asi que tres pushes que dicen "Partida vencida" y linkean
        todos a /lactancia son tres veces el mismo aviso.
        """
        with self.avisos(('lactancia', provider(item(), item(), item()))):
            avisos, _sin_payload, _fallados = app_module._push_avisos_ahora()
        self.assertEqual(len(avisos), 1)
        self.assertEqual(avisos['lactancia|peligro|Partida vencida']['cuerpo'],
                         'Lactancia · 3 avisos')

    def test_un_solo_item_no_lleva_conteo(self):
        with self.avisos(('lactancia', provider(item()))):
            avisos, _sin_payload, _fallados = app_module._push_avisos_ahora()
        self.assertEqual(avisos['lactancia|peligro|Partida vencida']['cuerpo'],
                         'Lactancia')

    def test_el_conteo_que_cambia_no_dispara_flanco(self):
        """El conteo va en el CUERPO, no en la clave: que aparezca una cuarta
        bolsita vencida no es un aviso nuevo, es el mismo aviso mas grande."""
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item(), item())))
        nuevas = self.ciclo(('lactancia', provider(item(), item(), item())))
        self.assertEqual(nuevas, [])

    def test_dos_providers_con_el_mismo_titulo_no_se_pisan(self):
        """
        Sin el prefijo de provider en la clave, uno de los dos no avisaria
        NUNCA — y seria invisible: el log mostraria un aviso donde hay dos.
        """
        mismo = item(titulo='Hay algo', severidad='alerta')
        with self.avisos(('lactancia', provider(mismo)),
                         ('recordatorio_bajar', provider(dict(mismo)))):
            avisos, _sin_payload, _fallados = app_module._push_avisos_ahora()
        self.assertEqual(sorted(avisos), ['lactancia|alerta|Hay algo',
                                          'recordatorio_bajar|alerta|Hay algo'])


# -- 4. Un provider roto no tumba el canal -----------------------------------

class TestProviderRoto(BaseSeco):

    def test_un_provider_que_explota_no_frena_a_los_demas(self):
        """Misma regla que `_notificaciones()`: se loguea AVISO y se sigue."""
        def roto():
            raise RuntimeError('la base no contesta')

        with self.avisos(('lactancia', roto),
                         ('recordatorio_bajar', provider(item(titulo='Bajá bolsitas',
                                                              severidad='alerta')))):
            avisos, _sin_payload, _fallados = app_module._push_avisos_ahora()
        self.assertEqual(list(avisos), ['recordatorio_bajar|alerta|Bajá bolsitas'])
        self.assertTrue(any(l.startswith('AVISO:') and 'lactancia' in l
                            for l in self.logs))

    def test_un_provider_roto_no_tumba_el_ciclo(self):
        def roto():
            raise RuntimeError('boom')

        self.ciclo(('lactancia', roto))                 # siembra
        nuevas = self.ciclo(('lactancia', roto))
        self.assertEqual(nuevas, [])

    def test_una_url_rara_se_saltea_ese_aviso_y_nada_mas(self):
        """
        `_push_payload()` rechaza una url absoluta. Ese aviso se descarta con
        un AVISO en el log; los demas salen igual.
        """
        with self.avisos(('lactancia', provider(item(url='https://ejemplo.com/x'),
                                                item(titulo='Sana', url='/lactancia')))):
            avisos, _sin_payload, _fallados = app_module._push_avisos_ahora()
        self.assertEqual(list(avisos), ['lactancia|peligro|Sana'])
        self.assertTrue(any(l.startswith('AVISO:') and 'descartado' in l
                            for l in self.logs))


# -- 4b. "No contesto" NO es "ya no hay nada" --------------------------------

class TestNivelDesconocido(BaseSeco):
    """
    El agujero mas caro que puede tener este motor, y no se ve leyendo el
    codigo: se ve a la tercera vuelta.

    Un provider que falla NO esta diciendo "ya no hay nada". Si sus claves se
    borraran del estado, al recuperarse las MISMAS cosas volverian a ser
    flanco ascendente. Y `_notif_lactancia` falla de verdad y en transitorio:
    `database is locked` mientras alguien guarda un movimiento o mientras
    `hacer_backup_db()` copia la base.

    El test de "un provider roto no tumba el ciclo" NO agarra esto, porque
    ahi el provider esta roto en TODAS las vueltas. El bug solo aparece con
    falla TRANSITORIA y recuperacion.
    """

    def roto(self):
        def _f():
            raise RuntimeError('database is locked')
        return _f

    def test_falla_transitoria_no_rearma_el_flanco(self):
        sano = ('lactancia', provider(item()))
        self.ciclo(sano)                                 # siembra
        del self.logs[:]
        self.ciclo(('lactancia', self.roto()))           # la vuelta ciega
        nuevas = self.ciclo(sano)                        # y vuelve en si
        self.assertEqual(nuevas, [])
        self.assertEqual(self.secas(), [])

    def test_la_vuelta_ciega_conserva_las_claves_del_provider_caido(self):
        self.ciclo(('lactancia', provider(item())))
        self.ciclo(('lactancia', self.roto()))
        self.assertEqual(self.estado()['avisadas'],
                         ['lactancia|peligro|Partida vencida'])

    def test_solo_arrastra_lo_del_provider_caido(self):
        """Un provider sano que deja de tener algo SI baja: el flanco
        descendente tiene que seguir rearmando, o la senal se enclava."""
        sanos = (('lactancia', provider(item())),
                 ('recordatorio_bajar', provider(item(titulo='Bajá bolsitas',
                                                      severidad='alerta'))))
        self.ciclo(*sanos)                               # siembra con los dos
        self.ciclo(('lactancia', self.roto()),
                   ('recordatorio_bajar', provider()))   # uno ciego, otro vacio
        self.assertEqual(self.estado()['avisadas'],
                         ['lactancia|peligro|Partida vencida'])

    def test_si_fallan_todos_no_se_borra_la_memoria_entera(self):
        """El peor caso: todos ciegos una vuelta. Si el estado quedara vacio,
        la vuelta siguiente re-anunciaria TODO de golpe."""
        sanos = (('lactancia', provider(item())),
                 ('recordatorio_bajar', provider(item(titulo='Bajá bolsitas',
                                                      severidad='alerta'))))
        self.ciclo(*sanos)
        self.ciclo(('lactancia', self.roto()),
                   ('recordatorio_bajar', self.roto()))
        self.assertEqual(len(self.estado()['avisadas']), 2)
        del self.logs[:]
        self.assertEqual(self.ciclo(*sanos), [])

    def test_un_aviso_sin_payload_no_rearma_al_arreglarse(self):
        """Mismo criterio: el nivel esta ALTO (el item existe), solo que no se
        puede armar el aviso. Si se dejara caer, arreglar la url seria un
        flanco de algo que nunca dejo de estar pasando."""
        self.ciclo(('lactancia', provider(item(url='https://ejemplo.com/x'))))
        self.assertEqual(self.estado()['avisadas'],
                         ['lactancia|peligro|Partida vencida'])
        nuevas = self.ciclo(('lactancia', provider(item(url='/lactancia'))))
        self.assertEqual(nuevas, [])

    def test_el_provider_roto_se_loguea_una_vez_por_dia(self):
        """144 vueltas por dia. Un modulo roto una semana serian 1000 lineas
        identicas tapando justo el log que el ensayo vino a producir."""
        self.ciclo(('lactancia', provider(item())))
        del self.logs[:]
        for _ in range(4):
            self.ciclo(('lactancia', self.roto()))
        rotos = [l for l in self.logs if l.startswith('AVISO:')]
        self.assertEqual(len(rotos), 1)
        # Y el latido del dia SI tiene que decir que esta ciego: "0 avisos
        # vigentes" dice exactamente lo mismo estando todo tranquilo.
        self.assertTrue(any('providers OK 0/1' in l for l in self.logs))

    def test_el_log_del_provider_roto_no_lleva_el_texto_de_la_excepcion(self):
        """Un error de sqlite puede arrastrar valores de la fila que lo rompio.
        Va el TIPO, que es lo unico que sirve para diagnosticar."""
        def revienta():
            raise RuntimeError('no such column: partidas.volumen_ml = 180')

        self.ciclo(('lactancia', revienta))
        texto = ' '.join(self.logs)
        self.assertNotIn('180', texto)
        self.assertNotIn('volumen_ml', texto)
        self.assertIn('RuntimeError', texto)


# -- 4c. Primero se guarda, despues se anuncia -------------------------------

class TestGuardadoPrimero(BaseSeco):
    """
    Al reves —anunciar y despues guardar— un guardado que falla deja el estado
    VIEJO en disco, y el mismo flanco se re-anuncia cada 10 minutos para
    siempre. Encendido eso es un telefono sonando cada 10 minutos por la misma
    bolsita, y un push no se puede desavisar.

    En este orden lo peor que pasa es perder un aviso, que es el lado barato:
    el dato sigue estando en la campana. Un push que no llego no es
    informacion perdida.
    """

    def sin_disco(self):
        return unittest.mock.patch.object(
            app_module, '_push_estado_guardar', lambda estado: False)

    def test_si_no_se_puede_guardar_no_se_anuncia(self):
        self.ciclo(('lactancia', provider()))            # siembra
        del self.logs[:]
        with self.sin_disco():
            nuevas = self.ciclo(('lactancia', provider(item())))
        self.assertEqual(nuevas, [])
        self.assertEqual(self.secas(), [])

    def test_si_no_se_puede_guardar_lo_dice_una_vez_por_dia(self):
        """Con backup_dir en un disco desenchufado son 288 lineas/dia, y con
        NSSM rotando el log a 1 MB eso empuja afuera lo que el ensayo junto."""
        self.ciclo(('lactancia', provider()))
        del self.logs[:]
        with self.sin_disco():
            for _ in range(4):
                self.ciclo(('lactancia', provider(item())))
        avisos = [l for l in self.logs if l.startswith('AVISO:')]
        self.assertEqual(len(avisos), 1)

    def test_la_siembra_no_dice_que_sembro_si_no_sembro(self):
        """"primera vuelta, se sembro" leido suelto tres dias despues dice
        "se reinicio el servicio". Afirmarlo sin haber escrito nada manda a
        diagnosticar un hilo muerto que esta vivo."""
        with self.sin_disco():
            self.ciclo(('lactancia', provider(item())))
        self.assertEqual([l for l in self.logs if 'sembrado' in l], [])

    def test_no_reescribe_el_archivo_si_no_cambio_nada(self):
        """144 escrituras por dia del mismo contenido. backup_dir puede
        apuntar a una carpeta sincronizada, que es un destino razonable."""
        self.ciclo(('lactancia', provider(item())))      # siembra
        with unittest.mock.patch.object(
                app_module, '_push_estado_guardar',
                side_effect=app_module._push_estado_guardar) as guardar:
            self.ciclo(('lactancia', provider(item())))
            self.ciclo(('lactancia', provider(item())))
        self.assertFalse(guardar.called)

    def test_la_escritura_es_atomica(self):
        """`open('w')` trunca ANTES de escribir: un corte en ese milisegundo
        deja el json partido, que se lee como "no hay estado" y re-siembra."""
        codigo = inspect.getsource(app_module._push_estado_guardar)
        self.assertIn('os.replace(', codigo)
        self.assertNotIn(".tmp'", codigo.split('os.replace(')[1])

    def test_no_queda_el_tmp_dando_vueltas(self):
        self.ciclo(('lactancia', provider(item())))
        self.assertEqual(
            [f for f in os.listdir(self._dir) if f.endswith('.tmp')], [])


# -- 5. El payload: las mismas tres claves de siempre ------------------------

class TestPayload(BaseSeco):

    def test_el_aviso_pasa_por_push_payload(self):
        """
        Tres claves y ninguna mas, y la url relativa. En seco no se manda,
        pero si el aviso no pasara por `_push_payload()` ahora, el dia que se
        encienda saldria sin haber pasado nunca por esas dos reglas.
        """
        with self.avisos(('lactancia', provider(item()))):
            avisos, _sin_payload, _fallados = app_module._push_avisos_ahora()
        payload = avisos['lactancia|peligro|Partida vencida']
        self.assertEqual(tuple(sorted(payload)),
                         tuple(sorted(app_module._PUSH_PAYLOAD_CLAVES)))
        self.assertTrue(payload['url'].startswith('/'))

    def test_el_detalle_no_viaja_en_el_payload(self):
        """El `detalle` lleva el volumen en ml, y el cuerpo se lee en la
        PANTALLA BLOQUEADA. La regla del payload no se negocia."""
        with self.avisos(('lactancia', provider(item(detalle='Freezer · 180 ml')))):
            avisos, _sin_payload, _fallados = app_module._push_avisos_ahora()
        texto = json.dumps(avisos, ensure_ascii=False)
        self.assertNotIn('180', texto)
        self.assertNotIn('ml', texto)


# -- 6. El log: el entregable real de la etapa -------------------------------

class TestLog(BaseSeco):

    def test_la_linea_en_seco_es_grepeable_y_se_entiende_sola(self):
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item())))
        linea = self.secas()[0]
        self.assertTrue(linea.startswith('SECO:'))
        self.assertIn('lactancia|peligro|Partida vencida', linea)
        self.assertIn('Partida vencida', linea)
        self.assertIn('/lactancia', linea)

    def test_las_vueltas_sin_novedad_no_loguean(self):
        """
        6 vueltas/hora x 72 h = 432 vueltas. Un "no hay nada nuevo" por vuelta
        son 432 lineas de ruido que tapan las que importan.
        """
        self.ciclo(('lactancia', provider(item())))     # siembra
        app_module._push_seco_dicho['latido'] = date.today()   # el latido del dia ya salio
        del self.logs[:]
        for _ in range(5):
            self.ciclo(('lactancia', provider(item())))
        self.assertEqual(self.logs, [])

    def test_hay_un_resumen_por_dia_para_saber_que_el_hilo_vive(self):
        """Mismo criterio que `_aviso_sin_cambios` del backup: una linea por
        dia, no una por vuelta."""
        self.ciclo(('lactancia', provider(item())))     # siembra
        del self.logs[:]
        self.ciclo(('lactancia', provider(item())))
        self.ciclo(('lactancia', provider(item())))
        resumenes = [l for l in self.logs if 'sin flancos' in l]
        self.assertEqual(len(resumenes), 1)

    def test_el_log_no_lleva_el_detalle_del_item(self):
        self.ciclo(('lactancia', provider()))
        self.ciclo(('lactancia', provider(item(detalle='Freezer · 180 ml'))))
        self.assertNotIn('180', ' '.join(self.logs))


# -- 7. EN SECO ES EN SECO ---------------------------------------------------

class TestNoSeMandaNada(BaseSeco):

    def test_el_ciclo_no_llama_a_push_enviar(self):
        with unittest.mock.patch.object(app_module, '_push_enviar') as enviar:
            self.ciclo(('lactancia', provider()))
            self.ciclo(('lactancia', provider(item())))
        self.assertFalse(enviar.called)

    def test_el_ciclo_no_lee_la_tabla_de_suscripciones(self):
        """No se leen ni para contarlas. Un endpoint es el buzon de un
        telefono: lo mas seguro que se puede hacer con la tabla en esta etapa
        es no abrirla."""
        with unittest.mock.patch.object(database, 'obtener_suscripciones_push') as leer:
            self.ciclo(('lactancia', provider()))
            self.ciclo(('lactancia', provider(item())))
        self.assertFalse(leer.called)

    def test_el_registro_de_push_es_una_lista_aparte(self):
        """
        PUSH_AVISOS no es NOTIF_PROVIDERS: no todo lo que merece un puntito en
        la campana merece hacerle sonar el celular a alguien. Si algun dia se
        "simplifica" esto reusando la lista de la campana, un provider nuevo
        empieza a despertar telefonos sin que nadie lo haya decidido.
        """
        self.assertIsNot(app_module.PUSH_AVISOS, app_module.NOTIF_PROVIDERS)
        for clave, fn in app_module.PUSH_AVISOS:
            with self.subTest(clave=clave):
                self.assertIsInstance(clave, str)
                self.assertTrue(callable(fn))

    def test_la_primera_vuelta_corre_al_arrancar(self):
        """El `sleep` va AL FINAL del loop, nunca al principio: si no, la
        primera vuelta despues de un reinicio llegaria 10 minutos tarde."""
        codigo = inspect.getsource(app_module._scheduler_push)
        cuerpo = codigo.split('while True:')[1]
        self.assertLess(cuerpo.index('_push_ciclo()'),
                        cuerpo.index('time.sleep('))

    def test_el_intervalo_tiene_nombre(self):
        self.assertEqual(app_module._PUSH_INTERVALO, 600)


if __name__ == '__main__':
    unittest.main()
