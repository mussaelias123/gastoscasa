# Contexto: Base de datos

> Leer junto con `CLAUDE.md`. Para cambios de esquema, queries o saldos.

## Archivo
- `database.py` (550 líneas). Capa de datos pura. SQLite vía `sqlite3` stdlib.
- Archivo físico: `gastos.db` en raíz (gitignored). Backups en `backups/` (gitignored).

## Esquema (actualizar al migrar)

### Tabla `movimientos`
| Columna                  | Tipo    | Notas                                                   |
|--------------------------|---------|---------------------------------------------------------|
| `id`                     | INTEGER | PK autoincremental                                      |
| `fecha`                  | TEXT    | `YYYY-MM-DD`                                            |
| `descripcion`            | TEXT    | Libre                                                   |
| `persona`                | TEXT    | `elias` \| `mari`                                       |
| `moneda`                 | TEXT    | `ars` \| `usd`                                          |
| `tipo`                   | TEXT    | `ingreso` \| `gasto` (cambio se desdobla en 2 filas)    |
| `monto`                  | REAL    | Siempre positivo                                        |
| `categoria`              | TEXT    | `Sueldo`, `Cambio`, `Fijo`, etc. NULL permitido         |
| `costo_envio`            | REAL    | Suma a `monto` para gastos. NULL = 0                    |
| `factor_aplicado`        | REAL    | Solo en sueldos. Aplica a `monto` al sumar saldo        |
| `cuota_numero`           | INTEGER | NULL si no es cuota                                     |
| `cuota_total`            | INTEGER | NULL si no es cuota                                     |
| `monto_usd`              | REAL    | Equivalente USD al insertar. NULL en filas pre-backfill |
| `cotizacion_usd_aplicada`| REAL    | Cotización ARS→USD usada. NULL si moneda='usd'          |

### Tabla `gastos_fijos`
| Columna        | Tipo    | Notas                                       |
|----------------|---------|---------------------------------------------|
| `id`           | INTEGER | PK                                          |
| `descripcion`  | TEXT    | Único de hecho                              |
| `activo`       | INTEGER | 1 \| 0                                      |
| `es_cuota`     | INTEGER | 1 si tiene cuotas. Default 0                |
| `total_cuotas` | INTEGER | Total esperado                              |
| `cuota_actual` | INTEGER | Avanza con cada inserción de cuota          |

### Migraciones
`inicializar_db()` ejecuta `ALTER TABLE ADD COLUMN` en bucle silencioso (try/except). **Nunca borrar columnas**, solo agregar. Migración manual de datos → `TempScripts/`.

## Funciones públicas

| Función                          | Retorna                            | Notas                              |
|----------------------------------|------------------------------------|------------------------------------|
| `conectar()`                     | `Connection` (row_factory=Row)     | Caller debe cerrar                 |
| `inicializar_db()`               | None                               | Idempotente. Llamar al boot        |
| `calcular_saldos()`              | `dict` con 8 claves                | Ver claves abajo                   |
| `obtener_movimientos(...)`       | `(filas, total)`                   | Filtros: persona, moneda, mes      |
| `agregar_movimiento(...)`        | `id` nuevo                         | 13 parámetros — ver firma          |
| `eliminar_movimiento(id)`        | None                               |                                    |
| `obtener_movimiento(id)`         | `Row` o None                       |                                    |
| `editar_movimiento(...)`         | None                               |                                    |
| `obtener_gastos_fijos(activos)`  | `list[Row]`                        |                                    |
| `agregar_gasto_fijo(desc)`       | id                                 |                                    |
| `editar_gasto_fijo(id, ...)`     | None                               |                                    |
| `eliminar_gasto_fijo(id)`        | None                               |                                    |
| `agregar_gasto_fijo_cuotas(d, n)`| id                                 | Marca `es_cuota=1`                 |
| `obtener_gasto_fijo_por_descripcion(desc)` | `Row` o None             |                                    |
| `avanzar_cuota(fijo_id)`         | None                               | Incrementa `cuota_actual`          |
| `verificar_gastos_fijos(mes)`    | `list`                             | Pendientes para el mes             |

## `calcular_saldos()` — 8 claves del dict
- `elias_ars`, `elias_usd`, `mari_ars`, `mari_usd` → saldos en moneda nativa.
- `elias_total_usd`, `mari_total_usd` → todo lo de la persona convertido a USD.
- `ars_total_usd` → suma USD de todo lo que es moneda `ars` (gauge "Total ARS").
- `usd_total_usd` → suma USD de todo lo que es moneda `usd` (gauge "Total USD").

Lógica clave:
- Sueldos: si `factor_aplicado` no es NULL, suman `monto * factor_aplicado`.
- Gastos: suman `monto + COALESCE(costo_envio, 0)`.
- Conversión USD usa `monto_usd` ya guardado en la fila (no recalcula).
- Costo envío en USD se prorratea: `costo_envio * (monto_usd / monto)`.

## Reglas específicas DB
1. **Saldos NUNCA almacenados**, siempre derivados.
2. **Migraciones** = `ALTER TABLE ADD COLUMN` en `inicializar_db()`. Cada nueva columna agregar también al diccionario de la sección "Esquema" arriba.
3. **Backfill** de datos viejos → script en `TempScripts/`. Ejemplo: `TempScripts/backfill_monto_usd.py`.
4. **Cierre de conexiones**: cada función abre y cierra. No reusar.
5. **Antes de cualquier migración** que modifique datos, hacer backup manual: `cp gastos.db backups/gastos_pre_<motivo>_<fecha>.db`.

## Al modificar este dominio, actualizar:
- Sección "Esquema" si cambia tabla.
- Tabla "Funciones públicas" si cambia firma.
- "Reglas específicas DB" si cambia convención.
