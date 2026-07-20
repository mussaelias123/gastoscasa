# Contexto: Base de datos

> Leer junto con `CLAUDE.md`. Para cambios de esquema, queries o saldos.

## Archivo
- `database.py` (~1090 líneas). Capa de datos pura. SQLite vía `sqlite3` stdlib.
- Archivo físico: `fondo.db` en raíz (gitignored). Backups en `backups/` (gitignored).
- **Rename 2026-07** (`gastos.db` → `fondo.db`): `DB_PATH` apunta a `fondo.db`. Red de
  seguridad `_migrar_nombre_db_si_hace_falta()` (corre a nivel módulo, antes de cualquier
  `conectar()`): si un entorno todavía tiene `gastos.db` y NO `fondo.db`, lo renombra solo
  y loguea `OK:`. Si existen los dos a la vez, no toca nada y loguea `AVISO:` (hay que
  resolverlo a mano). En el flujo normal (rename ya hecho a mano) es no-op. Los backups
  viejos con prefijo `gastos_*` siguen siendo válidos — ver `docs/CONTEXT_BACKEND.md`.

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

### Tabla `actividades` (módulo Calendario — tareas del hogar recurrentes)
| Columna          | Tipo    | Notas                                                     |
|------------------|---------|------------------------------------------------------------|
| `id`             | INTEGER | PK autoincremental                                        |
| `nombre`         | TEXT    | Libre                                                      |
| `area`           | TEXT    | `auto\|casa\|salud\|documentos\|mascotas\|finanzas\|hogar` |
| `responsable`    | TEXT    | `familia\|elias\|mari`. Default `familia`                 |
| `recurrente`     | INTEGER | 1 \| 0. Default 1                                          |
| `intervalo_n`    | INTEGER | NULL si única                                              |
| `intervalo_u`    | TEXT    | `dias\|semanas\|meses\|anios` (ASCII, sin ñ)               |
| `ultima`         | TEXT    | `YYYY-MM-DD`, última vez hecha. NULL permitido             |
| `proxima_manual` | TEXT    | `YYYY-MM-DD`, para únicas o 1ra vez sin historial. NULL ok |
| `avisar`         | INTEGER | 1 \| 0. Default 1                                          |
| `lead_dias`      | INTEGER | Días de anticipación del aviso. Default 14                |
| `uso_nota`       | TEXT    | Texto libre informativo (ej. "o cada 50.000 km")           |
| `terminada`      | INTEGER | 1 = archivada. Default 0                                   |
| `creado`         | TEXT    | Timestamp ISO al insertar                                  |
| `actualizado`    | TEXT    | Timestamp ISO al modificar                                 |

Nota: capa de datos PURA. `database.py` NO calcula próximas fechas ni estados
(vencida/próxima/al día) — esa lógica vive en `app.py`.

### Tabla `actividades_historial` (registro de completadas)
| Columna        | Tipo    | Notas                          |
|----------------|---------|---------------------------------|
| `id`           | INTEGER | PK autoincremental              |
| `actividad_id` | INTEGER | FK lógica a `actividades.id`     |
| `fecha_hecha`  | TEXT    | `YYYY-MM-DD`                     |
| `registrado`   | TEXT    | Timestamp ISO al insertar        |

### Tabla `lactancia_partidas` (módulo Lactancia — banco de leche)
| Columna            | Tipo    | Notas                                                        |
|--------------------|---------|--------------------------------------------------------------|
| `id`               | INTEGER | PK autoincremental                                           |
| `ubicacion`        | TEXT    | `freezer` \| `heladera`                                      |
| `cargada`          | TEXT    | Timestamp ISO del servidor al insertar, **INMUTABLE**. Solo auditoría — el vencimiento se calcula desde la extracción (issue #48) |
| `fecha_extraccion` | TEXT    | `YYYY-MM-DD` — con `hora_extraccion`, base del vencimiento en ambas ubicaciones |
| `hora_extraccion`  | TEXT    | `HH:MM`, solo freezer (NULL en heladera; desempata FIFO)     |
| `volumen_ml`       | INTEGER | 1..2000 (validado en app.py)                                 |
| `motivo_cierre`    | TEXT    | NULL (abierta) \| `usada` \| `descartada` \| `trasladada`    |
| `fecha_cierre`     | TEXT    | `YYYY-MM-DD`. NULL si abierta                                |
| `notas`            | TEXT    | Libre. Default `''`                                          |
| `origen_id`        | INTEGER | En heladeras cerradas `trasladada`: id de la partida de freezer nacida de la combinación (N heladeras → 1 freezer). NULL ok |
| `actualizado`      | TEXT    | Timestamp ISO al modificar                                   |

Nota: capa PURA — vencimiento/estado se calculan en `app.py` (`_lac_*`), nunca se almacenan. Cerradas (`motivo_cierre` no NULL) = historial, misma tabla.

### Tabla `rutina_ajustes` (módulo Rutina — ajustes de horario)
| Columna       | Tipo    | Notas                                                        |
|---------------|---------|--------------------------------------------------------------|
| `id`          | INTEGER | PK autoincremental                                           |
| `fecha`       | TEXT    | `YYYY-MM-DD` **local del cliente** (el teléfono define la fecha-clave) |
| `etapa`       | TEXT    | `actual` \| `tres` \| `guarderia`                            |
| `item_id`     | TEXT    | Id del ítem editable (`siesta2`, `t-noct1`, `gm-ext`, ...). Los ids derivados de adultos vinculados a León (prefijos `mama-`/`papa-`) NO son editables y nunca se persisten |
| `inicio_min`  | INTEGER | Minutos desde 00:00, rango 0..2879 (las tomas nocturnas cruzan la medianoche) |
| `actualizado` | TEXT    | Timestamp ISO al insertar/pisar                              |

`UNIQUE (fecha, etapa, item_id)` → habilita el upsert (último ajuste gana).
Nota: capa PURA — la cascada de horarios (re-encadenar los ítems que siguen a
un ajuste) se calcula en el FRONT (`static/rutina.js`); las definiciones de
rutina por etapa son constantes JS, no viven en la DB.

### Tabla `rutina_dur` (módulo Rutina — duraciones estiradas)
Espejo de `rutina_ajustes` pero para la DURACIÓN (drag estilo Teams: estirar un
ítem desde su manija inferior). Columnas: `id`, `fecha` (`YYYY-MM-DD` local del
cliente), `etapa`, `item_id`, `dur_min` (5..720), `actualizado`; `UNIQUE (fecha,
etapa, item_id)` para el upsert. "↺ Plan original" (`borrar_ajustes_rutina`)
borra TAMBIÉN estas filas.

### Tabla `rutina_tareas` (módulo Rutina — tareas añadidas por el usuario)
| Columna      | Tipo    | Notas                                                        |
|--------------|---------|--------------------------------------------------------------|
| `id`         | INTEGER | PK autoincremental. En el front el ítem es `c-<id>`          |
| `etapa`      | TEXT    | `actual` \| `tres` \| `guarderia`                            |
| `usuario`    | TEXT    | `leon` \| `mama` \| `papa`                                   |
| `titulo`     | TEXT    | 1..60 chars                                                  |
| `emoji`      | TEXT    | Opcional (`''` → el front muestra 📌)                        |
| `inicio_min` | INTEGER | Minutos desde 00:00 (0..1439). Horario FIJO: NO entra en la cascada |
| `dur`        | INTEGER | Duración en minutos (5..720)                                 |
| `fecha`      | TEXT    | `''` = permanente (todos los días de la etapa) \| `YYYY-MM-DD` = solo ese día |
| `creado`     | TEXT    | Timestamp ISO                                                |

### Tabla `rutina_ocultos` (módulo Rutina — ítems quitados)
| Columna   | Tipo    | Notas                                                        |
|-----------|---------|--------------------------------------------------------------|
| `id`      | INTEGER | PK autoincremental                                           |
| `etapa`   | TEXT    | Como arriba                                                  |
| `item_id` | TEXT    | Id del plan base (`siesta2`), derivado (`mama-siesta1`) o tarea añadida (`c-12`) |
| `fecha`   | TEXT    | `''` = quitado siempre \| `YYYY-MM-DD` = solo ese día        |
| `creado`  | TEXT    | Timestamp ISO                                                |

`UNIQUE (etapa, item_id, fecha)` con sentinela `''` (no NULL) para que el
insert-idempotente (`DO NOTHING`) funcione. Un ítem de León quitado sale de
la cadena ANTES de la cascada (los siguientes se re-encadenan, en el front).

### Migraciones
`inicializar_db()` ejecuta `ALTER TABLE ADD COLUMN` en bucle silencioso (try/except). **Nunca borrar columnas**, solo agregar. Migración manual de datos → `TempScripts/`.

## Funciones públicas

| Función                          | Retorna                            | Notas                              |
|----------------------------------|------------------------------------|------------------------------------|
| `conectar()`                     | `Connection` (row_factory=Row)     | Caller debe cerrar                 |
| `inicializar_db()`               | None                               | Idempotente. Llamar al boot        |
| `calcular_saldos(hasta=None)`    | `dict` con 8 claves                | `hasta='YYYY-MM-DD'` → saldos ≤ esa fecha (inclusive). `None` = toda la DB |
| `obtener_movimientos(...)`       | `(filas, total)`                   | Filtros: persona, moneda, mes      |
| `agregar_movimiento(...)`        | `id` nuevo                         | 13 parámetros — ver firma          |
| `eliminar_movimiento(id)`        | None                               |                                    |
| `obtener_movimiento(id)`         | `Row` o None                       |                                    |
| `editar_movimiento(...)`         | None                               |                                    |
| `obtener_gastos_fijos(solo_activos=True)` | `list[Row]`              |                                    |
| `agregar_gasto_fijo(desc)`       | id                                 |                                    |
| `editar_gasto_fijo(id, ...)`     | None                               |                                    |
| `eliminar_gasto_fijo(id)`        | None                               |                                    |
| `agregar_gasto_fijo_cuotas(d, n)`| id                                 | Marca `es_cuota=1`                 |
| `obtener_gasto_fijo_por_descripcion(desc)` | `Row` o None             |                                    |
| `avanzar_cuota(fijo_id)`         | None                               | Incrementa `cuota_actual`          |
| `verificar_gastos_fijos(mes)`    | `list`                             | Pendientes para el mes             |
| `obtener_actividades(incluir_terminadas=True)` | `list[Row]`           | Orden por `nombre`                 |
| `obtener_actividad(id)`          | `Row` o None                       |                                    |
| `agregar_actividad(...)`         | id nuevo                           | Setea `creado`/`actualizado`       |
| `editar_actividad(id, ...)`      | None                               | Actualiza `actualizado`            |
| `completar_actividad(id, fecha_hecha, repetir, intervalo_n=None, intervalo_u=None)` | None | Ver lógica abajo |
| `reactivar_actividad(id)`        | None                               | `terminada=0`                      |
| `eliminar_actividad(id)`         | None                               | Borra actividad Y su historial     |
| `obtener_historial(actividad_id=None)` | `list[Row]`                  | `None`=todo. Orden `fecha_hecha` DESC |
| `obtener_partidas_lactancia(ubicacion=None)` | `list[Row]`             | Orden crudo `fecha_extraccion, id`; FIFO final en app.py |
| `obtener_partida_lactancia(id)`  | `Row` o None                       |                                    |
| `agregar_partida_lactancia(ubicacion, fecha, hora, volumen_ml, notas='', origen_id=None)` | id | `cargada` se setea SIEMPRE acá (timestamp servidor) |
| `editar_partida_lactancia(id, fecha, hora, volumen_ml, notas)` | None  | NO toca `ubicacion` ni `cargada`   |
| `cerrar_partida_lactancia(id, motivo, fecha_cierre, notas=None)` | None | Solo `usada`\|`descartada`         |
| `combinar_partidas_lactancia(ids, fecha, hora, volumen_ml, fecha_cierre)` | id nuevo | Atómica: inserta 1 freezer combinada + cierra N heladeras como `trasladada` con `origen_id`=hija |
| `reabrir_partida_lactancia(id)`  | None                               | Atómica. Freezada: borra la hija y reabre TODA la combinación; ValueError si la hija ya se cerró |
| `eliminar_partida_lactancia(id)` | None                               | DELETE definitivo                  |
| `obtener_ajustes_rutina(desde, hasta)` | `list[Row]`                  | Ajustes con `fecha` en `[desde, hasta]` (strings ISO) |
| `guardar_ajuste_rutina(fecha, etapa, item_id, inicio_min)` | None       | Upsert (`ON CONFLICT ... DO UPDATE`), refresca `actualizado` |
| `borrar_ajustes_rutina(fecha, etapa)` | None                           | DELETE de ajustes de inicio Y duraciones de esa fecha+etapa ("↺ Plan original") |
| `obtener_duraciones_rutina(desde, hasta)` | `list[Row]`                | Duraciones estiradas con `fecha` en rango |
| `guardar_duracion_rutina(fecha, etapa, item_id, dur_min)` | None        | Upsert (última gana) |
| `obtener_tareas_rutina(desde, hasta)` | `list[Row]`                    | Tareas añadidas: permanentes (`fecha=''`) + fechadas en rango |
| `crear_tarea_rutina(etapa, usuario, titulo, emoji, inicio_min, dur, fecha)` | id nuevo | `fecha=''` = permanente |
| `borrar_tarea_rutina(id)`        | None                               | Borra la tarea Y sus ocultos/ajustes `c-<id>` |
| `obtener_ocultos_rutina(desde, hasta)` | `list[Row]`                   | Quitados: permanentes + fechados en rango |
| `ocultar_item_rutina(etapa, item_id, fecha)` | None                     | Insert idempotente (`DO NOTHING`) |
| `restaurar_item_rutina(etapa, item_id)` | None                          | Borra TODOS los ocultos del ítem (permanente y fechados) |

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
- `hasta` (opcional): si matchea `YYYY-MM-DD` agrega `WHERE fecha <= ?` a ambas queries (filtro inclusive). `fecha` es TEXT ISO → comparación de strings ordena cronológicamente. El SQL interpola un literal fijo; el valor viaja parametrizado (`?`).

## `completar_actividad()` — lógica de completar/repetir
1. Inserta fila en `actividades_historial` (acumula, nunca sobreescribe).
2. `ultima = fecha_hecha`, `proxima_manual = NULL`, refresca `actualizado`.
3. `repetir=True` → `terminada=0`, `recurrente=1`. Si vienen `intervalo_n`/`intervalo_u`, los pisa (permite cambiar frecuencia al completar); si no vienen, conserva los existentes.
4. `repetir=False` → `terminada=1` (se archiva).
Cálculo de próxima fecha y estado (vencida/próxima/al día) vive en `app.py`, no acá.

## Reglas específicas DB
1. **Saldos NUNCA almacenados**, siempre derivados.
2. **Migraciones** = `ALTER TABLE ADD COLUMN` en `inicializar_db()`. Cada nueva columna agregar también al diccionario de la sección "Esquema" arriba.
3. **Backfill** de datos viejos → script en `TempScripts/`. Ejemplo: `TempScripts/backfill_monto_usd.py`.
4. **Cierre de conexiones**: cada función abre y cierra. No reusar.
5. **Antes de cualquier migración** que modifique datos, hacer backup manual: `cp fondo.db backups/fondo_pre_<motivo>_<fecha>.db`.

## Al modificar este dominio, actualizar:
- Sección "Esquema" si cambia tabla.
- Tabla "Funciones públicas" si cambia firma.
- "Reglas específicas DB" si cambia convención.
