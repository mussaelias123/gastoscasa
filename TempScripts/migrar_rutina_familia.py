# =============================================================================
# SCRIPT ONE-SHOT: migrar_rutina_familia.py
# =============================================================================
#
# Siembra la familia y las actividades de la hoja Rutina, que hasta el rework
# estaban escritas a mano en static/rutina.js (constante ETAPAS).
#
# Qué hace:
#   1. Backup de fondo.db en backups/ antes de tocar nada.
#   2. Crea los miembros: el bebé (leyendo bebe_nombre / bebe_fecha_nacimiento
#      de config.json), Mamá y Papá.
#   3. Convierte las agendas de adultos de la etapa "actual" en filas de
#      rutina_actividades, con los días de la semana que correspondan
#      (las de finde van solo sábado y domingo; las de semana, de lunes a
#      viernes). Las que involucraban al bebé se cargan como compartidas.
#   4. Convierte las filas viejas de rutina_tareas (si hubiera) al nuevo
#      vocabulario: la columna `usuario` pasa de 'leon'|'mama'|'papa' al id
#      del miembro, y la `etapa` a 'plan'.
#
# Es IDEMPOTENTE: si los miembros ya existen, no los duplica, y las
# actividades se identifican por (miembro, título) antes de insertarlas.
#
# Uso, desde la raíz del proyecto y con la app DETENIDA:
#     python TempScripts/migrar_rutina_familia.py
#     python TempScripts/migrar_rutina_familia.py --dry-run
#
# =============================================================================

import os
import shutil
import sqlite3
import sys
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import config      # noqa: E402
import database    # noqa: E402

DRY_RUN = '--dry-run' in sys.argv

# Los ítems `clock` de las agendas de mamá y papá en ETAPAS.actual, tal como
# estaban en static/rutina.js antes del rework. (hora, duración, título, emoji)
LMV = '1111100'    # lunes a viernes
FINDE = '0000011'  # sábado y domingo
TODOS = '1111111'

AGENDA_MAMA = [
    # (titulo, emoji, inicio_min, dur_min, dias, nota)
    ('Desayuno y tareas', '🍳', 420, 60, TODOS, 'mientras el bebé duerme'),
    ('Gimnasia', '🏋️', 600, 60, LMV, 'mientras el bebé duerme'),
    ('Almuerzo + descanso', '🍽️', 780, 60, TODOS, 'mientras el bebé duerme'),
    ('Estudio / proyecto', '📚', 900, 60, LMV, 'mientras el bebé duerme'),
    ('Extracción (banco de leche)', '🍼', 1020, 30, TODOS, 'mientras el bebé duerme'),
    ('Cena', '🍽️', 1230, 45, TODOS, ''),
    ('Ducha', '🚿', 1290, 20, TODOS, 'con el bebé ya dormido'),
    ('A dormir', '😴', 1350, 30, TODOS, ''),
]

AGENDA_PAPA = [
    ('Despertar', '🌅', 405, 45, LMV, ''),
    ('Salir al trabajo', '🚗', 450, 30, LMV, ''),
    ('Trabajo (Villa María)', '💼', 480, 300, LMV, ''),
    ('Almuerzo', '🍽️', 780, 60, LMV, ''),
    ('Trabajo', '💼', 840, 180, LMV, ''),
    ('Tareas de la casa', '🧺', 780, 90, FINDE, ''),
    ('Cocinar y cenar', '🍳', 1230, 60, FINDE, ''),
    ('Cena', '🍽️', 1230, 45, LMV, ''),
    ('Ducha', '🚿', 1290, 20, TODOS, 'con el bebé dormido'),
    ('A dormir', '😴', 1380, 30, TODOS, ''),
]

# Actividades del adulto que pasan CON el bebé. Se cargan a nombre del adulto
# y NO se marcan como compartidas a propósito: el día del bebé ya está descrito
# entero por el motor de ventanas de sueño, así que sumarle estas encima lo
# duplicaría y —como dos actividades de la misma persona nunca se pisan— le
# correría la noche hacia adelante.
# Compartir una actividad con un bebé (que su rutina generada la absorba en vez
# de apilarse) es parte del editor de actividades, no de esta migración.
CON_BEBE_MAMA = [
    ('Paseo con el bebé', '🚶', 540, 50, TODOS, ''),
    ('Upa y movimiento', '🫂', 1140, 50, TODOS, 'la hora más sensible del día'),
]
CON_BEBE_PAPA = [
    ('Upa con el bebé', '🫂', 1140, 50, FINDE, 'refuerzo: mamá descansa'),
]


def backup_db():
    """Copia fondo.db a backups/ antes de cualquier escritura."""
    origen = database.DB_PATH
    if not os.path.exists(origen):
        print('AVISO: no existe', origen, '— se creará al arrancar la app.')
        return None
    cfg = config.cargar_config(os.path.join(ROOT_DIR, 'config.json'))
    destino_dir = cfg.get('backup_dir', 'backups')
    if not os.path.isabs(destino_dir):
        destino_dir = os.path.join(ROOT_DIR, destino_dir)
    os.makedirs(destino_dir, exist_ok=True)
    sello = datetime.now().strftime('%Y%m%d_%H%M%S')
    destino = os.path.join(destino_dir, f'fondo_pre_rutina_familia_{sello}.db')
    if DRY_RUN:
        print('[dry-run] backup ->', destino)
        return destino
    shutil.copy2(origen, destino)
    print('OK: backup en', destino)
    return destino


def miembro_por_rol(conn, rol, es_bebe=None):
    sql = 'SELECT id, nombre FROM rutina_miembros WHERE rol = ?'
    params = [rol]
    if es_bebe is not None:
        sql += ' AND es_bebe = ?'
        params.append(1 if es_bebe else 0)
    return conn.execute(sql, params).fetchone()


def crear_miembro(conn, nombre, rol, es_bebe, fnac, color, ancla, orden):
    ya = miembro_por_rol(conn, rol, es_bebe if rol == 'hijo' else None)
    if ya:
        print(f'  = {rol}: ya existe ({ya["nombre"]}, id {ya["id"]})')
        return ya['id']
    if DRY_RUN:
        print(f'  [dry-run] crear {rol}: {nombre} (bebé={bool(es_bebe)}, nac={fnac or "—"})')
        return -1
    ahora = datetime.now().strftime('%y/%m/%d-%H:%M:%S')
    cur = conn.execute('''
        INSERT INTO rutina_miembros
            (nombre, rol, es_bebe, fecha_nacimiento, dibujo, color_token,
             ancla_min, orden, activo, creado, actualizado)
        VALUES (?, ?, ?, ?, '', ?, ?, ?, 1, ?, ?)
    ''', (nombre, rol, es_bebe, fnac, color, ancla, orden, ahora, ahora))
    print(f'  + {rol}: {nombre} (id {cur.lastrowid})')
    return cur.lastrowid


def crear_actividad(conn, miembro_id, datos, participantes=()):
    titulo, emoji, inicio, dur, dias, nota = datos
    ya = conn.execute(
        'SELECT id FROM rutina_actividades WHERE miembro_id = ? AND titulo = ?',
        (miembro_id, titulo)
    ).fetchone()
    if ya:
        print(f'    = "{titulo}": ya existe (id {ya["id"]})')
        return ya['id']
    if DRY_RUN:
        print(f'    [dry-run] crear "{titulo}" {inicio // 60:02d}:{inicio % 60:02d} '
              f'({dur} min, días {dias})')
        return -1
    ahora = datetime.now().strftime('%y/%m/%d-%H:%M:%S')
    cur = conn.execute('''
        INSERT INTO rutina_actividades
            (miembro_id, titulo, dibujo, inicio_min, dur_min, dias, meses,
             desde, hasta, anual, nota, activo, creado, actualizado)
        VALUES (?, ?, ?, ?, ?, ?, '111111111111', '', '', 0, ?, 1, ?, ?)
    ''', (miembro_id, titulo, emoji, inicio, dur, dias, nota, ahora, ahora))
    act_id = cur.lastrowid
    for p in participantes:
        conn.execute('''
            INSERT INTO rutina_actividad_miembros (actividad_id, miembro_id)
            VALUES (?, ?) ON CONFLICT (actividad_id, miembro_id) DO NOTHING
        ''', (act_id, p))
    extra = f' + participantes {list(participantes)}' if participantes else ''
    print(f'    + "{titulo}" (id {act_id}){extra}')
    return act_id


def migrar_tareas_viejas(conn, mapa_usuarios):
    """rutina_tareas.usuario: 'leon'|'mama'|'papa' → id del miembro.
    rutina_tareas.etapa: la que fuera → 'plan'."""
    filas = conn.execute(
        "SELECT id, usuario, etapa, titulo FROM rutina_tareas"
    ).fetchall()
    if not filas:
        print('  (no hay tareas viejas que migrar)')
        return
    for fila in filas:
        nuevo = mapa_usuarios.get(fila['usuario'])
        if nuevo is None:
            print(f'  ! tarea {fila["id"]} "{fila["titulo"]}": usuario '
                  f'"{fila["usuario"]}" desconocido, se deja como está')
            continue
        if DRY_RUN:
            print(f'  [dry-run] tarea {fila["id"]}: usuario {fila["usuario"]} -> {nuevo}')
            continue
        conn.execute(
            "UPDATE rutina_tareas SET usuario = ?, etapa = 'plan' WHERE id = ?",
            (str(nuevo), fila['id'])
        )
        print(f'  ~ tarea {fila["id"]} "{fila["titulo"]}": '
              f'{fila["usuario"]} -> miembro {nuevo}')


def main():
    print('=' * 70)
    print('Migración: familia y actividades del módulo Rutina')
    if DRY_RUN:
        print('MODO DRY-RUN: no se escribe nada.')
    print('=' * 70)

    backup_db()

    # Asegura que las tablas nuevas existan (inicializar_db es idempotente).
    database.inicializar_db()

    cfg = config.cargar_config(os.path.join(ROOT_DIR, 'config.json'))
    bebe_nombre = (str(cfg.get('bebe_nombre') or '').strip() or 'Bebé')
    bebe_fnac = str(cfg.get('bebe_fecha_nacimiento') or '').strip()
    if not bebe_fnac:
        print('\nAVISO: config.json no tiene bebe_fecha_nacimiento. El miembro '
              'se crea igual pero SIN marcar como bebé: sin fecha no hay edad '
              'y sin edad no hay ventana de sueño. Cargale la fecha desde '
              '/rutina → Familia y marcá la casilla.')

    conn = database.conectar()
    try:
        print('\nMiembros:')
        id_bebe = crear_miembro(conn, bebe_nombre, 'hijo', 1 if bebe_fnac else 0,
                                bebe_fnac, 'persona-leon', 390, 0)
        id_mama = crear_miembro(conn, 'Mamá', 'mama', 0, '', 'persona-mari', 390, 1)
        id_papa = crear_miembro(conn, 'Papá', 'papa', 0, '', 'persona-elias', 390, 2)

        print('\nActividades de mamá:')
        for datos in AGENDA_MAMA + CON_BEBE_MAMA:
            crear_actividad(conn, id_mama, datos)

        print('\nActividades de papá:')
        for datos in AGENDA_PAPA + CON_BEBE_PAPA:
            crear_actividad(conn, id_papa, datos)

        print('\nTareas añadidas de la versión anterior:')
        migrar_tareas_viejas(conn, {
            'leon': id_bebe, 'mama': id_mama, 'papa': id_papa,
        })

        if DRY_RUN:
            conn.rollback()
        else:
            conn.commit()
    finally:
        conn.close()

    print('\n' + '=' * 70)
    print('Listo.' if not DRY_RUN else 'Dry-run terminado (no se escribió nada).')
    print('Arrancá la app y entrá a http://localhost:5050/rutina')
    print('=' * 70)


if __name__ == '__main__':
    main()
