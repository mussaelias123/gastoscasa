# -*- coding: utf-8 -*-
"""
SIMULADOR DEL MOTOR DE FLANCOS DEL PUSH (script one-shot, no producción).

PARA QUÉ: el ensayo en seco de la etapa 7 tarda 48-72 h en decir algo, porque
el motor da una vuelta cada 10 minutos y las partidas de leche vencen en días.
Este script comprime eso en dos segundos: inventa providers falsos, corre
varias vueltas de `_push_ciclo()` contra un directorio de estado TEMPORAL, y
muestra la secuencia NIVEL → FLANCO en una escalera, como se mira una señal.

SECO POR CONSTRUCCIÓN, no por suerte: `_push_enviar` se parchea para reventar,
así que este script NO manda un push ni con `push_enabled` prendido. El estado
va a una carpeta temporal que se borra al terminar; no se toca la carpeta de
backups de verdad, ni la base, ni una sola suscripción.

CORRER:
    python TempScripts/simular_flancos_push.py
"""

import os
import sys
import shutil
import tempfile
import unittest.mock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import app  # noqa: E402


def _item(titulo, severidad='peligro', detalle='', url='/lactancia',
          modulo='lactancia', modulo_nombre='Lactancia'):
    """Un ítem con el contrato cerrado de 7 claves."""
    return {'modulo': modulo, 'modulo_nombre': modulo_nombre, 'icono': '*',
            'titulo': titulo, 'detalle': detalle, 'url': url,
            'severidad': severidad}


# Sentinela: en esa vuelta el provider NO contesta (explota). No es lo mismo
# que devolver una lista vacía, y esa diferencia es el bug más caro que puede
# tener este motor — ver las vueltas 3 y 4.
CIEGO = object()


# El guion de la simulación: una lista de (rótulo, items que devuelve el
# provider en esa vuelta). Cada entrada es una vuelta del scheduler.
GUION = [
    ("arranque del servicio: ya había una partida vencida",
     [_item('Partida vencida', detalle='venció hace 2 días')]),

    ("10 min después: sigue vencida (mismo nivel)",
     [_item('Partida vencida', detalle='venció hace 2 días')]),

    ("la base estaba tomada: el provider NO contestó (no dijo 'no hay nada')",
     CIEGO),

    ("se recupera: la MISMA partida sigue vencida (no tiene que sonar)",
     [_item('Partida vencida', detalle='venció hace 2 días')]),

    ("al otro día: MISMA bolsita, el detalle cambió",
     [_item('Partida vencida', detalle='venció hace 3 días')]),

    ("aparecen dos más vencidas (el grupo crece)",
     [_item('Partida vencida', detalle='venció hace 3 días'),
      _item('Partida vencida', detalle='venció hace 1 día'),
      _item('Partida vencida', detalle='venció hoy')]),

    ("se suma el recordatorio de las 21:00 (otro aviso)",
     [_item('Partida vencida', detalle='venció hace 3 días'),
      _item('Bajá bolsitas para mañana', severidad='alerta',
            detalle='recordatorio de las 21:00')]),

    ("se tiraron las vencidas: queda solo el recordatorio",
     [_item('Bajá bolsitas para mañana', severidad='alerta',
            detalle='recordatorio de las 21:00')]),

    ("se bajaron las bolsitas: no queda nada",
     []),

    ("un mes después vuelve a vencer una (la señal rearmó)",
     [_item('Partida vencida', detalle='venció hoy')]),
]


def main():
    carpeta = tempfile.mkdtemp(prefix='simular-flancos-push-')
    lineas = []

    def _log_falso(texto):
        lineas.append(texto)

    print()
    print('SIMULADOR DE FLANCOS DEL PUSH')
    print('Seco por construcción: `_push_enviar` está parcheado para reventar,')
    print('así que no manda nada ni con push_enabled prendido.')
    print(f'Estado temporal en: {carpeta}')
    print()
    print('  NIVEL  = lo que contestan los providers en esa vuelta.')
    print('  FLANCO = lo que el motor anunciaría (solo lo que ANTES no estaba).')
    print()

    try:
        # ⚠ `_push_enviar` SE PARCHEA SÍ O SÍ, y no es cinturón y tirantes.
        # Desde la etapa que encendió el motor, `_push_ciclo()` lee
        # `push_enabled` EN CALIENTE del config.json de verdad. El día que
        # alguien lo prenda en producción y corra este script —que es
        # justamente lo que CONTEXT_DEPLOY.md le dice que haga para verlo
        # andar— los teléfonos de Elías y Mari sonarían con las partidas
        # vencidas INVENTADAS del GUION. Y un push no se puede desavisar.
        # Los topes tampoco lo frenarían: el estado va a una carpeta temporal,
        # así que `enviados_hoy` arranca en cero en cada corrida.
        #
        # Revienta en vez de devolver (0, 0): que el simulador llegue hasta
        # acá es un bug del simulador, y un bug se grita, no se traga.
        def _no_manda(*a, **k):
            raise AssertionError(
                'El simulador intentó mandar un push de verdad. '
                'Es un bug del simulador, no del motor.')

        with unittest.mock.patch.object(app, '_get_backup_dir', lambda: carpeta), \
             unittest.mock.patch.object(app, '_push_enviar', _no_manda), \
             unittest.mock.patch.object(app, 'log', _log_falso):
            app._push_seco_dicho.clear()
            for i, (rotulo, items) in enumerate(GUION, start=1):
                del lineas[:]
                if items is CIEGO:
                    def _provider():
                        raise RuntimeError('database is locked')
                else:
                    def _provider(items=items):
                        return list(items)
                with unittest.mock.patch.object(
                        app, 'PUSH_AVISOS', [('lactancia', _provider)]):
                    nuevas = app._push_ciclo()

                # El NIVEL se muestra YA AGRUPADO (que es como lo ve el motor):
                # 3 partidas vencidas son un solo escalón, no tres.
                grupos = {}
                for it in ([] if items is CIEGO else items):
                    k = f"{it['severidad']}|{it['titulo']}"
                    grupos[k] = grupos.get(k, 0) + 1
                nivel = ' + '.join(
                    f"{k.split('|')[1]}" + (f" (x{n})" if n > 1 else '')
                    for k, n in grupos.items()) or '(nada)'

                print(f'VUELTA {i:>2}  {rotulo}')
                if items is CIEGO:
                    print('      NIVEL   ?????  (desconocido: no contestó)')
                else:
                    print(f'      NIVEL   {"ALTO" if grupos else "bajo"}  {nivel}')
                if nuevas:
                    for clave in nuevas:
                        print(f'      FLANCO  _|‾   SONARÍA -> {clave}')
                elif i == 1:
                    print('      FLANCO  ----  (siembra: la primera vuelta nunca suena)')
                else:
                    print('      FLANCO  ----  silencio')
                for linea in lineas:
                    print(f'         log: {linea}')
                print()
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)

    print('LO QUE HAY QUE MIRAR:')
    print('  - La vuelta 1 no suena aunque hubiera algo vencido (siembra).')
    print('  - La vuelta 4 no suena aunque el provider acabe de volver en sí:')
    print('    no contestar NO es decir "ya no hay nada", así que sus claves')
    print('    se arrastran. Si se borraran, la misma bolsita sonaría de nuevo.')
    print('  - La vuelta 5 no suena: cambió el `detalle`, no la bolsita.')
    print('  - La vuelta 6 no suena: 3 partidas son UN aviso, no tres.')
    print('  - La última SÍ suena: la señal se fue y volvió (rearme).')
    print()


if __name__ == '__main__':
    main()
