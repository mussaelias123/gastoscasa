import sqlite3

conn = sqlite3.connect('gastos.db')
conn.row_factory = sqlite3.Row

print("=== TODOS LOS MOVIMIENTOS ELÍAS USD (cronológico) ===")
movs = conn.execute("""
    SELECT id, fecha, descripcion, persona, moneda, tipo, monto, categoria, factor_aplicado
    FROM movimientos
    WHERE persona='elias' AND moneda='usd'
    ORDER BY fecha, id
""").fetchall()

saldo_acum = 0
for r in movs:
    if r['tipo'] == 'ingreso':
        saldo_acum += r['monto']
        signo = '+'
    else:
        saldo_acum -= r['monto']
        signo = '-'
    print(f"  [{r['id']:3}] {r['fecha']} | {signo}{r['monto']:>10,.2f} | saldo={saldo_acum:>10,.2f} | {r['tipo']:7} | {r['descripcion']}")

print(f"\n  SALDO FINAL EN APP: {saldo_acum:,.2f}")

# Reconciliación con Excel
print()
print("=== RECONCILIACIÓN ESPERADA ===")
print("  Saldo Anterior Nov (Excel): 128.53 USD")
print("  Movimientos Nov  (Excel):  +1,486.66 USD")
print("    Saldo Final Nov (Excel):  1,615.19 USD")
print("  Movimientos Dic  (Excel):  -1,024.62 USD")
print("    Saldo Final Dic (Excel):    590.57 USD")
print()
print("  Cuotas Terreno en DB DESPUÉS de diciembre (futuras):")

post_dic = conn.execute("""
    SELECT id, fecha, monto FROM movimientos
    WHERE LOWER(descripcion) LIKE '%terreno%'
      AND persona='elias' AND moneda='usd'
      AND fecha > '2025-12-31'
    ORDER BY fecha
""").fetchall()
total_futuras = sum(r['monto'] for r in post_dic)
for r in post_dic:
    print(f"    [{r['id']}] {r['fecha']}: -{r['monto']:.2f}")
print(f"    Total cuotas futuras: -{total_futuras:.2f}")

print()
esperado_app = 590.57 - total_futuras
print(f"  Saldo esperado en app: 590.57 - {total_futuras:.2f} = {esperado_app:.2f}")
print(f"  Saldo actual en app:  {saldo_acum:.2f}")
print(f"  DIFERENCIA:           {saldo_acum - esperado_app:.2f}")

print()
print("=== CUOTAS TERRENO USD PRE-NOVIEMBRE (posible doble conteo) ===")
pre_nov = conn.execute("""
    SELECT id, fecha, monto FROM movimientos
    WHERE LOWER(descripcion) LIKE '%terreno%'
      AND persona='elias' AND moneda='usd'
      AND fecha < '2025-11-01'
    ORDER BY fecha
""").fetchall()
total_pre = sum(r['monto'] for r in pre_nov)
for r in pre_nov:
    print(f"    [{r['id']}] {r['fecha']}: -{r['monto']:.2f}")
print(f"    Total: -{total_pre:.2f}")
print()
print(f"  El Saldo Inicial cargado (ID 104) ya refleja el balance")
print(f"  DESPUÉS de esas {len(pre_nov)} cuotas (son parte del historial pre-noviembre).")
print(f"  Si también están como gastos en la DB → doble conteo de -{total_pre:.2f} USD")
print(f"  Diferencia encontrada: {saldo_acum - esperado_app:.2f} vs doble conteo esperado: {-total_pre:.2f}")
