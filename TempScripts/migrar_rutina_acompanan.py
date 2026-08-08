# =============================================================================
# SCRIPT ONE-SHOT: migrar_rutina_acompanan.py
# =============================================================================
#
# Pasa a la base la regla que hasta ahora estaba escrita a mano en
# static/rutina.js: "las tomas del bebé le ocupan la agenda a mamá".
#
# Esa regla vivía en tomasQueOcupanAMama(), buscaba al miembro con rol 'mama'
# y valía solo para esta familia (y solo mientras mamá no trabajara). Ahora es
# un dato de la ficha del bebé: rutina_miembros.acompanan, ids separados por
# coma. Este script escribe el valor que reproduce EXACTAMENTE lo que se veía
# antes, así el cambio no mueve nada en pantalla el día que se mergea.
#
# Qué hace:
#   1. Backup de fondo.db en backups/ antes de tocar nada.
#   2. Para cada bebé activo con acompanan vacío, le pone el id de la mamá
#      activa (rol = 'mama', es_bebe = 0). Si no hay mamá cargada, avisa y
#      sigue: la rutina del bebé no cambia, solo no se comparten las tomas.
#
# Es IDEMPOTENTE: un bebé que ya tiene algo cargado no se toca (correrlo dos
# veces no pisa lo que el usuario haya elegido desde la app).
#
# Uso, desde la raíz del proyecto y con la app DETENIDA:
#     python TempScripts/migrar_rutina_acompanan.py --dry-run
#     python TempScripts/migrar_rutina_acompanan.py
#
# =============================================================================

import os
import shutil
import sys
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import config      # noqa: E402
import database    # noqa: E402

DRY_RUN = '--dry-run' in sys.argv


def backup_db():
    """Copia fondo.db a backups/ antes de cualquier escritura."""
    origen = database.DB_PATH
    if not os.path.exists(origen):
        print('AVISO: no existe', origen, '— no hay nada que migrar.')
        return None
    cfg = config.cargar_config(os.path.join(ROOT_DIR, 'config.json'))
    destino_dir = cfg.get('backup_dir', 'backups')
    if not os.path.isabs(destino_dir):
        destino_dir = os.path.join(ROOT_DIR, destino_dir)
    os.makedirs(destino_dir, exist_ok=True)
    sello = datetime.now().strftime('%Y%m%d_%H%M%S')
    destino = os.path.join(destino_dir, f'fondo_pre_rutina_acompanan_{sello}.db')
    if DRY_RUN:
        print('[dry-run] backup ->', destino)
        return destino
    shutil.copy2(origen, destino)
    print('OK: backup en', destino)
    return destino


def main():
    print('=' * 70)
    print('Migración: quién acompaña al bebé en las tomas (rutina_miembros)')
    if DRY_RUN:
        print('MODO DRY-RUN: no se escribe nada.')
    print('=' * 70)

    backup_db()

    # Asegura que la columna exista (inicializar_db es idempotente y hace el
    # ALTER TABLE en try/except).
    database.inicializar_db()

    conn = database.conectar()
    try:
        mama = conn.execute('''
            SELECT id, nombre FROM rutina_miembros
            WHERE rol = 'mama' AND es_bebe = 0 AND activo = 1
            ORDER BY orden, id
        ''').fetchone()

        bebes = conn.execute('''
            SELECT id, nombre, acompanan FROM rutina_miembros
            WHERE es_bebe = 1 AND activo = 1
            ORDER BY orden, id
        ''').fetchall()

        if not bebes:
            print('\n(no hay bebés cargados: nada que migrar)')
        elif not mama:
            print('\n! No hay ninguna mamá activa cargada. Los bebés quedan sin '
                  'acompañante — cargalo desde /rutina → Familia → ✎ del bebé.')

        print()
        for bebe in bebes:
            if (bebe['acompanan'] or '').strip():
                print(f'  = {bebe["nombre"]}: ya tiene acompañantes '
                      f'({bebe["acompanan"]}), no se toca')
                continue
            if not mama:
                print(f'  ! {bebe["nombre"]}: sin mamá que asignar')
                continue
            if DRY_RUN:
                print(f'  [dry-run] {bebe["nombre"]}: acompanan -> '
                      f'{mama["id"]} ({mama["nombre"]})')
                continue
            ahora = datetime.now().isoformat(timespec='seconds')
            conn.execute(
                'UPDATE rutina_miembros SET acompanan = ?, actualizado = ? WHERE id = ?',
                (str(mama['id']), ahora, bebe['id'])
            )
            print(f'  + {bebe["nombre"]}: las tomas ahora acompañan a '
                  f'{mama["nombre"]} (id {mama["id"]})')

        if DRY_RUN:
            conn.rollback()
        else:
            conn.commit()
    finally:
        conn.close()

    print('\n' + '=' * 70)
    print('Listo.' if not DRY_RUN else 'Dry-run terminado (no se escribió nada).')
    print('Arrancá la app y entrá a http://127.0.0.1:5050/rutina — las tomas del')
    print('bebé tienen que seguir apareciendo en la columna de mamá igual que antes.')
    print('=' * 70)


if __name__ == '__main__':
    main()
