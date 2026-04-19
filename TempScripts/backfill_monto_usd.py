# =============================================================================
# SCRIPT: scripts/backfill_monto_usd.py
# =============================================================================
#
# QUÉ HACE:
#   Recorre TODOS los movimientos donde monto_usd IS NULL y los rellena con
#   el equivalente en USD calculado a partir de la cotización HISTÓRICA real
#   del día del movimiento (consultada a api.argentinadatos.com).
#
# CUÁNDO SE USA:
#   Una sola vez, después de aplicar la migración que agregó la columna
#   monto_usd. Es idempotente: si lo corrés varias veces, las próximas no
#   procesan nada (solo trabajan con monto_usd IS NULL).
#
# CÓMO SE CORRE:
#   Desde la raíz del proyecto:
#       python scripts/backfill_monto_usd.py
#
# QUÉ HACE ANTES DE MODIFICAR:
#   Crea automáticamente un backup de la base de datos en
#   backups/gastos_pre_backfill_YYYYMMDD_HHMMSS.db
#
# REGLAS DE CONVERSIÓN:
#   - Si moneda == 'usd': monto_usd = monto, cotizacion_usd_aplicada = NULL.
#   - Si moneda == 'ars': se busca la cotización oficial del día de la fecha
#     del movimiento en api.argentinadatos.com. Si esa fecha no está
#     disponible (feriados, fin de semana), se retrocede hasta 10 días.
#     Si no se encuentra, se loggea como SKIP y se continúa.
#
# REQUISITOS:
#   Internet activo durante la ejecución para consultar la API histórica.
#
# =============================================================================

import os
import sys
import shutil
import sqlite3
from datetime import datetime

# Agregamos la raíz del proyecto al sys.path para poder importar 'cotizacion'
# cuando se ejecuta el script desde la raíz: python scripts/backfill_monto_usd.py
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import cotizacion  # noqa: E402  (import después de modificar sys.path)


DB_PATH     = os.path.join(ROOT_DIR, 'gastos.db')
BACKUP_DIR  = os.path.join(ROOT_DIR, 'backups')


def hacer_backup():
    """Copia la DB a backups/gastos_pre_backfill_YYYYMMDD_HHMMSS.db."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dest = os.path.join(BACKUP_DIR, f'gastos_pre_backfill_{timestamp}.db')
    shutil.copy2(DB_PATH, dest)
    print(f"OK: Backup creado: {os.path.relpath(dest, ROOT_DIR)}")
    return dest


def conectar():
    """Conexión a la DB con row_factory=Row, mismo patrón que database.py."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def backfill():
    """Recorre movimientos con monto_usd IS NULL y los completa."""
    if not os.path.exists(DB_PATH):
        print(f"ERROR: No se encontró la base de datos en {DB_PATH}")
        sys.exit(1)

    print(f"Base de datos: {DB_PATH}")
    hacer_backup()

    # 1) Bajamos la lista histórica una sola vez.
    print("Descargando cotizaciones históricas de api.argentinadatos.com...")
    try:
        historicas = cotizacion.obtener_cotizaciones_historicas(forzar_refresh=True)
    except Exception as e:
        print(f"ERROR: No se pudieron obtener las cotizaciones históricas: {e}")
        sys.exit(1)
    print(f"OK: {len(historicas)} cotizaciones históricas en cache.")

    # 2) Buscamos los movimientos pendientes.
    conn = conectar()
    pendientes = conn.execute(
        'SELECT id, fecha, moneda, monto FROM movimientos WHERE monto_usd IS NULL ORDER BY fecha ASC, id ASC'
    ).fetchall()

    total = len(pendientes)
    if total == 0:
        print("Nada para procesar: todos los movimientos ya tienen monto_usd.")
        conn.close()
        return

    print(f"Movimientos pendientes: {total}")
    print("-" * 60)

    procesados = 0
    skippeados = 0
    ok_count   = 0

    for i, mov in enumerate(pendientes, start=1):
        mov_id    = mov['id']
        fecha     = mov['fecha']
        moneda    = mov['moneda']
        monto     = float(mov['monto'])

        if moneda == 'usd':
            monto_usd = monto
            cot       = None
            conn.execute(
                'UPDATE movimientos SET monto_usd=?, cotizacion_usd_aplicada=? WHERE id=?',
                (monto_usd, cot, mov_id)
            )
            procesados += 1
            ok_count += 1
            print(f"[{i}/{total}] {fecha} USD {monto:.2f} -> USD {monto_usd:.2f} (sin conversión)")
            continue

        # moneda == 'ars': buscar cotización histórica
        cot = cotizacion.cotizacion_para_fecha(fecha, historicas)

        if cot is None:
            skippeados += 1
            print(f"[{i}/{total}] {fecha} ARS {monto:.2f} -> SKIP (sin cotización en +/-10 días)")
            continue

        monto_usd = monto / cot
        conn.execute(
            'UPDATE movimientos SET monto_usd=?, cotizacion_usd_aplicada=? WHERE id=?',
            (monto_usd, cot, mov_id)
        )
        procesados += 1
        ok_count += 1
        print(f"[{i}/{total}] {fecha} ARS {monto:.2f} -> USD {monto_usd:.2f} (cotización {cot:.2f})")

    conn.commit()
    conn.close()

    print("-" * 60)
    print(f"Resumen:")
    print(f"  Total procesados: {total}")
    print(f"  OK:               {ok_count}")
    print(f"  Skippeados:       {skippeados}")
    print(f"  Updates aplicados:{procesados}")


if __name__ == '__main__':
    backfill()
