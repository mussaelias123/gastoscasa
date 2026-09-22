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
| `personal`               | INTEGER | `0` = fondo familiar (todo lo previo a 2026-09; el `DEFAULT 0` evitó backfill), `1` = cuenta personal de `persona`. Ver "Cuenta personal" abajo |

### La columna `personal` — el filtro que no se puede olvidar
El módulo Personal NO agregó una tabla: agregó esta columna. **Toda query sobre
`movimientos` tiene que declarar de qué bolsillo lee**, o el fondo empieza a
sumar plata que no es suya. Hoy son seis queries en tres funciones:
`calcular_saldos` (2, filtro fijo `personal = 0`), `obtener_movimientos` (2, vía
el parámetro `ambito`) y `verificar_gastos_fijos` (2, filtro fijo). Cubierto por
`tests/test_personal.py`, que corre el mismo escenario con y sin movimientos
personales y exige que el fondo dé idéntico.

Un movimiento `personal = 1` **nunca lleva `factor_aplicado`, `cuota_numero` ni
`cuota_total`**: no existe el sueldo personal (siempre entra al fondo) y las
cuotas cuelgan de `gastos_fijos`, que no tiene persona ni ámbito.

**El resto del sueldo no es una fila.** El fondo se queda con
`monto * factor_aplicado`; lo que sobra es plata de esa persona y se DERIVA
(`calcular_saldos_personales`, `obtener_sueldos_resto`), no se guarda. Coherente
con la regla 1 de este doc (saldos siempre derivados): editar el sueldo actualiza
las dos cuentas solo, borrarlo lo saca de las dos, y el `factor_aplicado`
congelado por fila hace que cambiar el factor en Settings no reescriba la
historia. Se ignoran los factores fuera de `[0, 1)`: con factor 1 el resto es
cero, y una fila vieja sin factor no permite saber qué parte era personal.

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
| `origen_id`        | INTEGER | En heladeras cerradas `trasladada`: id de la partida de freezer nacida de la combinación (N heladeras → 1 freezer). En una FREEZER cerrada `trasladada` (bajada a descongelar): id de la heladera `descongelada` que nació de ella (1 → 1). NULL ok |
| `tipo`             | TEXT    | `fresca` (extracción directa a heladera) \| `congelada` (agregado de freezer, nace de combinar) \| `descongelada` (bajada del freezer a la heladera). Base de los KPIs y del vencimiento |
| `consumido_ml`     | INTEGER | ml que el bebé realmente tomó de la bolsa (solo `usada`). NULL = no se anotó → se asume que se consumió todo. Base del desperdicio |
| `en_jardin`        | INTEGER | 0/1 — la bolsita está de back up en el jardín (vale en freezer Y en heladera). NO es un cierre: sigue abierta y contando como stock, por eso es columna propia. Viaja con la leche al descongelar. Al cerrar la bolsita queda congelada: es lo que separa `consumida_jardin_ml` de `consumida_fuera_ml` |
| `actualizado`      | TEXT    | Timestamp ISO al modificar                                   |

Nota: capa PURA — vencimiento/estado se calculan en `app.py` (`_lac_*`), nunca se almacenan. Cerradas (`motivo_cierre` no NULL) = historial, misma tabla.

Migración `tipo`/`consumido_ml`/`en_jardin`: `ALTER TABLE ... ADD COLUMN` en try/except (mismo patrón que `movimientos`), + backfill de `tipo` en filas viejas (`freezer`→`congelada`, `heladera`→`fresca`). `en_jardin` no necesita backfill: el `DEFAULT 0` alcanza, y las filas viejas con NULL se normalizan a `False` en `_lac_enriquecer`.

Por qué `tipo` importa para los KPIs: la producción total cuenta SOLO las `fresca` — cada extracción entra una vez como fresca; `congelada` y `descongelada` son la MISMA leche movida de lugar (si no, se contaría 2-3 veces al freezar y descongelar).

### Tabla `rutina_miembros` (módulo Rutina — la familia)
| Columna            | Tipo    | Notas                                                   |
|--------------------|---------|---------------------------------------------------------|
| `id`               | INTEGER | PK autoincremental. En el front el "usuario" es `String(id)` |
| `nombre`           | TEXT    | 1..40 chars                                             |
| `rol`              | TEXT    | `mama` \| `papa` \| `hijo` \| `otro`                    |
| `es_bebe`          | INTEGER | 1 → su rutina se GENERA con las ventanas de sueño. Solo válido con `rol='hijo'` |
| `fecha_nacimiento` | TEXT    | `YYYY-MM-DD`; `''` = sin cargar. Obligatoria si `es_bebe` |
| `dibujo`           | TEXT    | Clave de la librería de dibujos; `''` → emoji por rol   |
| `color_token`      | TEXT    | Var CSS sin el prefijo `--color-`: `persona-leon\|mari\|elias`, `rut-p4`..`rut-p8` (validado contra `_RUT_COLORES` en `app.py`) |
| `ancla_min`        | INTEGER | SOLO bebés: minutos de la primera toma del día (0..1439). 390 = 06:30 |
| `acompanan`        | TEXT    | SOLO bebés: ids separados por coma de quienes lo acompañan en las tomas (`'2'`, `'2,3'`); `''` = nadie. Se fuerza `''` si `es_bebe=0`. Máximo 3 |
| `noct_n`           | INTEGER | SOLO bebés: cuántas tomas de madrugada mostrarle. `-1` (default) = las que sugiere la tabla de ventanas de sueño para su edad; `0..6` = las que fijó el usuario con el "− 2 +" de la franja Madrugada. Existe porque lo esperable a cada edad es un RANGO (a los 3 meses, 1-2) y hay bebés que piden una más. Se escribe por su propia función (`fijar_nocturnas_rutina`), NO desde el form de Familia |
| `orden`            | INTEGER | Orden de la familia en chips y columnas                 |
| `activo`           | INTEGER | 0 = archivado (no se muestra)                           |
| `creado` / `actualizado` | TEXT | Timestamps ISO                                       |

Reemplaza a los tres strings fijos (`leon`/`mama`/`papa`) que estaban
hardcodeados en `app.py` y `static/rutina.js`. Borrar un miembro limpia a mano
sus actividades, todos los ajustes/duraciones/ocultos de sus ítems y su id
dentro del `acompanan` de los demás: no hay foreign keys declaradas en este
esquema.

**Por qué `acompanan` es una columna y no una tabla puente**: es un atributo del
bebé (cardinalidad 0-3, siempre se lee junto al resto de la fila, nunca se
consulta sola), viaja gratis en `_rut_payload` sin query extra y tiene
precedente en el mismo esquema (`dias`/`meses` ya son strings empaquetados).
`rutina_actividad_miembros` **no sirve acá**: esa tabla es para actividades
CARGADAS, y las tomas son ítems GENERADOS (`b<id>-toma2`) que no tienen fila en
ninguna tabla. Agregada con `ALTER TABLE` (08/08/2026) para reemplazar la regla
"las tomas de León le ocupan la agenda a mamá", que estaba escrita a mano en
`static/rutina.js`; los datos existentes los sembró
`TempScripts/migrar_rutina_acompanan.py`.

### Tabla `rutina_actividades` (módulo Rutina — actividades con frecuencia)
| Columna      | Tipo    | Notas                                                        |
|--------------|---------|--------------------------------------------------------------|
| `id`         | INTEGER | PK autoincremental. En el front el ítem es `a<id>`           |
| `miembro_id` | INTEGER | Dueño (da el color y la columna principal)                   |
| `titulo`     | TEXT    | 1..60 chars                                                  |
| `dibujo`     | TEXT    | Clave de dibujo / emoji; `''` → 📌                           |
| `inicio_min` | INTEGER | Minutos desde 00:00 (0..1439). Horario FIJO: NO entra en la cascada |
| `dur_min`    | INTEGER | 5..720                                                       |
| `dias`       | TEXT    | 7 chars `0`/`1`, **lunes primero**: L M X J V S D. `1111100` = L a V |
| `meses`      | TEXT    | 12 chars `0`/`1`, enero primero                              |
| `desde` / `hasta` | TEXT | `YYYY-MM-DD`; `''` = sin límite por ese lado                |
| `anual`      | INTEGER | 1 → de `desde`/`hasta` se comparan SOLO día y mes (la escuela revive sola cada marzo) |
| `nota`       | TEXT    | Texto libre que se muestra como subtítulo                    |
| `activo`     | INTEGER | 0 = no se muestra                                            |
| `creado` / `actualizado` | TEXT | Timestamps ISO                                   |

Qué día cae cada actividad NO se resuelve en la DB: la regla combinada (días →
meses → rango/anual → recesos) vive en `actividadAplica()` de
`static/rutina.js`, porque el que sabe qué día está mirando es el cliente.

### Tabla `rutina_actividad_miembros` (participantes extra)
`id`, `actividad_id`, `miembro_id`, `UNIQUE (actividad_id, miembro_id)`. Una
actividad compartida ("teta" involucra al bebé y a mamá) aparece en la línea de
tiempo de todos sus participantes, pero es UN solo ítem `a<id>`: moverla desde
cualquiera la mueve en todas. El dueño NO se repite acá.

### Tabla `rutina_pausas` (recesos de una actividad)
`id`, `actividad_id`, `desde`, `hasta`, `anual`, `motivo`. Sub-rangos donde la
actividad NO va: las vacaciones de invierno dentro del ciclo lectivo. Para
faltar UN día suelto (un feriado) se usa `rutina_ocultos` con fecha.

`obtener_actividades_rutina()` devuelve cada receso **con su `id`** — es lo que
le permite al editor borrar uno suelto sin tocar los demás de la misma
actividad. En la UI los recesos se cargan por rutas aparte (`/api/rutina/pausa/*`)
y solo al EDITAR: una pausa necesita el `actividad_id`, que no existe hasta que
la actividad está guardada.

### Tabla `rutina_ajustes` (módulo Rutina — ajustes de horario)
| Columna       | Tipo    | Notas                                                        |
|---------------|---------|--------------------------------------------------------------|
| `id`          | INTEGER | PK autoincremental                                           |
| `fecha`       | TEXT    | `YYYY-MM-DD` **local del cliente** (el teléfono define la fecha-clave) |
| `etapa`       | TEXT    | `plan` (todo lo nuevo). Los valores viejos `actual`/`tres`/`guarderia` se siguen aceptando solo por las filas históricas |
| `item_id`     | TEXT    | `b<miembro>-siesta1` (generado del bebé), `a<actividad>` (actividad cargada), `c-<rowid>` (tarea añadida) |
| `inicio_min`  | INTEGER | Minutos desde 00:00, rango 0..2879 (las tomas nocturnas cruzan la medianoche) |
| `actualizado` | TEXT    | Timestamp ISO al insertar/pisar                              |

`UNIQUE (fecha, etapa, item_id)` → habilita el upsert (último ajuste gana).
Nota: capa PURA — la cascada de horarios (re-encadenar los ítems que siguen a
un ajuste) se calcula en el FRONT (`static/rutina.js`), igual que la generación
de la rutina del bebé (`static/rutina-sueno.js`). En la DB se guardan solo las
DESVIACIONES del plan generado.

### Tabla `rutina_dur` (módulo Rutina — duraciones estiradas)
Espejo de `rutina_ajustes` pero para la DURACIÓN (drag estilo Teams: estirar un
ítem desde su manija inferior). Columnas: `id`, `fecha` (`YYYY-MM-DD` local del
cliente), `etapa`, `item_id`, `dur_min` (5..720), `actualizado`; `UNIQUE (fecha,
etapa, item_id)` para el upsert. "↺ Plan original" (`borrar_ajustes_rutina`)
borra TAMBIÉN estas filas.

### Tabla `rutina_tareas` (módulo Rutina — tareas añadidas por el usuario)
⚠ **No es la lista de Tareas que ve el usuario**: esa es `rutina_pendientes`
(más abajo). Esta tabla son las tareas sueltas **con horario** que se agregan a
la línea de tiempo desde `✎ Editar`. Dos cosas distintas con el mismo nombre en
castellano; en el código la nueva se llama `pendientes` en todas las capas.

| Columna      | Tipo    | Notas                                                        |
|--------------|---------|--------------------------------------------------------------|
| `id`         | INTEGER | PK autoincremental. En el front el ítem es `c-<id>`          |
| `etapa`      | TEXT    | `plan` (las filas viejas pueden tener `actual`/`tres`/`guarderia`) |
| `usuario`    | TEXT    | Id del miembro guardado como string (antes: `leon`/`mama`/`papa`) |
| `titulo`     | TEXT    | 1..60 chars                                                  |
| `emoji`      | TEXT    | Opcional (`''` → el front muestra 📌)                        |
| `inicio_min` | INTEGER | Minutos desde 00:00 (0..1439). Horario FIJO: NO entra en la cascada |
| `dur`        | INTEGER | Duración en minutos (5..720)                                 |
| `fecha`      | TEXT    | `''` = permanente (todos los días de la etapa) \| `YYYY-MM-DD` = solo ese día |
| `creado`     | TEXT    | Timestamp ISO                                                |

### Tabla `rutina_pendientes` (módulo Rutina — la lista de TAREAS)
⚠ **No confundir con `rutina_tareas`** (arriba), que sigue viva y es otra cosa.
Esta es la lista que el usuario ve como **Tareas**: los mandados del día. No
tienen hora, no se dibujan en la línea de tiempo y se tildan cuando están hechas.

| Columna      | Tipo    | Notas                                                        |
|--------------|---------|--------------------------------------------------------------|
| `id`         | INTEGER | PK autoincremental                                           |
| `titulo`     | TEXT    | 1..60 chars                                                  |
| `dibujo`     | TEXT    | Clave de `RutinaDibujos` (`''` → el front muestra `checklist`) |
| `repite`     | INTEGER | 0 = tarea suelta (vale `fecha`) \| 1 = repetitiva (vale `dias`) |
| `dias`       | TEXT    | 7 chars `'0'/'1'`, **LUNES primero**, igual que `rutina_actividades`. Con `repite=0` queda `'0000000'` |
| `fecha`      | TEXT    | `YYYY-MM-DD`, solo con `repite=0`                            |
| `desde`      | TEXT    | Fecha de ALTA. **No es opcional**: sin ella una tarea cargada el jueves figuraría como "no hecha" el lunes de la misma semana (el selector L-D deja mirar atrás) |
| `hasta`      | TEXT    | `''` = abierta. Sin UI todavía; existe para archivar sin borrar |
| `activo`     | INTEGER | 0 = no se muestra                                            |
| `creado` / `actualizado` | TEXT | Timestamps ISO                                   |

**Sin `miembro_id`**: a diferencia de una actividad, una tarea no tiene dueño —
tiene cero o más responsables. Cero responsables = tarea de la casa: se ve
siempre, aunque el filtro de la familia tenga miembros apagados.

### Tabla `rutina_pendiente_miembros` (responsables de una tarea)
`id`, `pendiente_id`, `miembro_id`, `UNIQUE (pendiente_id, miembro_id)`.

### Tabla `rutina_pendientes_hechas` (ocurrencias cerradas)
`id`, `pendiente_id`, `fecha`, `auto`, `hecha_en`, `UNIQUE (pendiente_id, fecha)`.

`fecha` es el día que la tarea **vencía**, no el día en que se tildó (eso va en
`hecha_en`): así el arrastre y el barrido hablan el mismo idioma. El `UNIQUE` es
lo que hace idempotente el tildado. `auto = 1` → la cerró el barrido por
vencimiento, no una persona.

**La regla de arrastre**: la tarea del día D se ve D y D+1. Si al llegar a D+2
sigue sin tildar, se da por realizada sola (`auto = 1`) y deja de aparecer.

⚠ **Acá se rompe el principio de "la regla de ocurrencia vive en JS"** (ver
`rutina_actividades`), y a propósito: `pendienteDebe()` en `static/rutina.js`
decide qué se ve en pantalla (el que sabe qué día se está mirando es el
cliente), pero `_pendiente_vence()` + `cerrar_pendientes_vencidas()` en
`database.py` **escriben**, y no pueden esperar a que alguien abra el navegador
el día justo. La regla está escrita dos veces: si tocás una, tocá la otra.
`tests/test_rutina_pendientes.py` congela la de Python.

### Tabla `rutina_ocultos` (módulo Rutina — ítems quitados)
| Columna   | Tipo    | Notas                                                        |
|-----------|---------|--------------------------------------------------------------|
| `id`      | INTEGER | PK autoincremental                                           |
| `etapa`   | TEXT    | Como arriba                                                  |
| `item_id` | TEXT    | Generado del bebé (`b1-siesta2`), actividad (`a17`) o tarea añadida (`c-12`) |
| `fecha`   | TEXT    | `''` = quitado siempre \| `YYYY-MM-DD` = solo ese día        |
| `creado`  | TEXT    | Timestamp ISO                                                |

`UNIQUE (etapa, item_id, fecha)` con sentinela `''` (no NULL) para que el
insert-idempotente (`DO NOTHING`) funcione. Un ítem del bebé quitado sale de
la cadena ANTES de la cascada (los siguientes se re-encadenan, en el front).
Es también la 4ª capa de la frecuencia: faltar UN día suelto (feriado).

### Tabla `push_suscripciones` (PWA — a qué navegadores avisarle)
| Columna      | Tipo | Notas                                                             |
|--------------|------|-------------------------------------------------------------------|
| `endpoint`   | TEXT | **PRIMARY KEY**. URL https del buzón que el servicio de push (FCM / Mozilla / Apple) le abrió a ESE navegador en ESE dispositivo |
| `p256dh`     | TEXT | Clave pública del navegador (base64url, 87-88 chars). Sin ella el aviso no se puede cifrar |
| `auth`       | TEXT | Secreto de 16 bytes (base64url, 22-24 chars)                      |
| `persona`    | TEXT | `elias` \| `mari`. **La pone el servidor** (`_persona_actual()`), nunca el POST |
| `user_email` | TEXT | El de la sesión. Es por lo que el logout sabe qué filas borrar    |
| `user_agent` | TEXT | Recortado a **300 chars** al guardar (`_PUSH_UA_MAX`). Para distinguir un teléfono de otro cuando haya que mirar por qué uno dejó de recibir avisos |
| `creada`     | TEXT | Timestamp ISO de la PRIMERA vez que se vio ese buzón. **No se refresca nunca** |

**Una fila = un NAVEGADOR, no una persona.** Por eso el `endpoint` es la PK: si
Mari entra en el Android de Elías, el endpoint es el mismo y el alta PISA
`persona`/`user_email` — el dueño del buzón pasa a ser la última sesión. Es lo
correcto: quien mire ese teléfono va a ver la notificación.

**No hay `ultimo_ok` ni contador de fallos, y no es un olvido.** Esta tabla
entra en el dump lógico que hashea `_hash_datos_db()` (app.py) para decidir si
el día tuvo algo que backupear. Un campo que se reescriba en cada envío haría
cambiar el hash todos los días y el detector de backups quedaría inútil
(backup diario FALSO, para siempre).

⚠ **Lo que protege el hash es que `creada` NO esté en el `SET` del upsert**, y
conviene tenerlo claro porque no es lo que parece. `_hash_datos_db()` hashea el
**contenido** de las filas, no las escrituras: un UPDATE que reescribe los
mismos valores deja la fila idéntica y el hash quieto. Medido — sin el `WHERE`
hay 10 UPDATE reales por 10 altas repetidas y el hash **igual no se mueve**. El
que lo movería es `creada`, porque sería un valor nuevo cada vez.

**Consecuencia para quien venga a sumar `ultimo_ok`**: el `WHERE` de este
`ON CONFLICT` NO lo cubre. Ese refresh sería un UPDATE aparte, con un valor
nuevo cada envío, y ahí sí el hash se mueve todos los días. El criterio para
dar de baja un buzón muerto es el 404/410 del servicio de push, y tiene que ser
un `DELETE` de la fila, no un campo que se reescriba.

El upsert lleva **`WHERE`** igual, por otra razón — evita escrituras inútiles y
permite devolver si escribió de verdad:

```sql
ON CONFLICT (endpoint) DO UPDATE SET ...
WHERE push_suscripciones.p256dh IS NOT excluded.p256dh OR ...   -- los 5 campos
```

Las dos cosas están congeladas en `tests/test_push_suscripciones.py`: el hash
antes y después de 10 altas iguales, y que esas 10 no escriban.

### Migraciones
`inicializar_db()` ejecuta `ALTER TABLE ADD COLUMN` en bucle silencioso (try/except). **Nunca borrar columnas**, solo agregar. Migración manual de datos → `TempScripts/`.

## Funciones públicas

| Función                          | Retorna                            | Notas                              |
|----------------------------------|------------------------------------|------------------------------------|
| `conectar()`                     | `Connection` (row_factory=Row)     | Caller debe cerrar                 |
| `inicializar_db()`               | None                               | Idempotente. Llamar al boot        |
| `calcular_saldos(hasta=None)`    | `dict` con 8 claves                | **Solo el fondo** (`personal = 0`, filtro fijo). `hasta='YYYY-MM-DD'` → saldos ≤ esa fecha (inclusive). `None` = toda la DB |
| `obtener_movimientos(..., ambito='fondo')` | `(filas, total)`         | Filtros: persona, moneda, mes. `ambito`: `fondo` (default, `personal=0`) \| `personal` \| `todos`; otro valor → ValueError. El SELECT devuelve también `personal` |
| `agregar_movimiento(..., personal=0)` | `id` nuevo                    | 14 parámetros — ver firma          |
| `eliminar_movimiento(id)`        | None                               |                                    |
| `obtener_movimiento(id)`         | `Row` o None                       | Sin filtro de ámbito: es por id    |
| `editar_movimiento(..., personal=None)` | None                        | `personal=None` **no toca la columna** (un form viejo no mueve el movimiento de bolsillo); `0`/`1` lo mueve |
| `calcular_saldos_personales(persona, hasta=None)` | `{'ars','usd','total_usd'}` | Cuenta personal de UNA persona: lo cargado como `personal=1` **+ el resto del sueldo derivado**. `total_usd` usa el `monto_usd` congelado (no revalúa a hoy) |
| `obtener_sueldos_resto(persona, mes=None, limite=None)` | `list[Row]` | Los sueldos del FONDO que dejaron resto personal, con `resto` y `resto_usd` ya calculados por fila. Materia prima de las filas sintéticas del módulo Personal (`id` = el del sueldo real). Excluye factor NULL, `<0` o `>=1` |
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
| `agregar_partida_lactancia(ubicacion, fecha, hora, volumen_ml, notas='', origen_id=None, tipo='fresca')` | id | `cargada` se setea SIEMPRE acá (timestamp servidor). `tipo` default `fresca` porque toda alta es extracción directa |
| `editar_partida_lactancia(id, fecha, hora, volumen_ml, notas)` | None  | NO toca `ubicacion` ni `cargada`   |
| `cerrar_partida_lactancia(id, motivo, fecha_cierre, notas=None, consumido_ml=None)` | None | Solo `usada`\|`descartada`. `consumido_ml` se setea SIEMPRE (NULL si no viene) para que un re-cierre no arrastre un valor viejo |
| `combinar_partidas_lactancia(ids, fecha, hora, volumen_ml, fecha_cierre)` | id nuevo | Atómica: inserta 1 freezer combinada (`tipo='congelada'`) + cierra N heladeras como `trasladada` con `origen_id`=hija |
| `bajar_partida_lactancia(freezer_id, fecha_cierre)` | id nuevo | Atómica, inversa de combinar (1 → 1): inserta 1 heladera `tipo='descongelada'` (mismo volumen y datos de extracción; su `cargada`=ahora es la base del vencimiento) + cierra la de freezer como `trasladada` con `origen_id`=hija. Compatible con `reabrir` (deshace la bajada) |
| `reabrir_partida_lactancia(id)`  | None                               | Atómica. Freezada: borra la hija y reabre TODA la combinación; ValueError si la hija ya se cerró |
| `eliminar_partida_lactancia(id)` | None                               | DELETE definitivo                  |
| `obtener_ajustes_rutina(desde, hasta)` | `list[Row]`                  | Ajustes con `fecha` en `[desde, hasta]` (strings ISO) |
| `guardar_ajuste_rutina(fecha, etapa, item_id, inicio_min)` | None       | Upsert (`ON CONFLICT ... DO UPDATE`), refresca `actualizado` |
| `borrar_ajustes_rutina(fecha, etapa)` | None                           | DELETE de ajustes de inicio Y duraciones de esa fecha+etapa ("↺ Plan original") |
| `borrar_ajuste_rutina(fecha, etapa, item_id)` | None                    | DELETE del ajuste de UN ítem ("Soltar" del popover). NO toca `rutina_dur` |
| `obtener_duraciones_rutina(desde, hasta)` | `list[Row]`                | Duraciones estiradas con `fecha` en rango |
| `guardar_duracion_rutina(fecha, etapa, item_id, dur_min)` | None        | Upsert (última gana) |
| `obtener_tareas_rutina(desde, hasta)` | `list[Row]`                    | Tareas añadidas: permanentes (`fecha=''`) + fechadas en rango |
| `crear_tarea_rutina(etapa, usuario, titulo, emoji, inicio_min, dur, fecha)` | id nuevo | `fecha=''` = permanente |
| `borrar_tarea_rutina(id)`        | None                               | Borra la tarea Y sus ocultos/ajustes `c-<id>` |
| `obtener_ocultos_rutina(desde, hasta)` | `list[Row]`                   | Quitados: permanentes + fechados en rango |
| `ocultar_item_rutina(etapa, item_id, fecha)` | None                     | Insert idempotente (`DO NOTHING`) |
| `restaurar_item_rutina(etapa, item_id)` | None                          | Borra TODOS los ocultos del ítem (permanente y fechados) |
| `obtener_miembros_rutina(incluir_inactivos=False)` | `list[Row]`        | La familia ordenada por `orden`, `id` |
| `crear_miembro_rutina(nombre, rol, es_bebe, fecha_nacimiento, dibujo, color_token, ancla_min, acompanan='')` | id nuevo | Se ubica al final (`orden` = máx + 1) |
| `editar_miembro_rutina(id, nombre, rol, es_bebe, fecha_nacimiento, dibujo, color_token, ancla_min, acompanan, activo)` | None | Pisa todos los campos editables |
| `fijar_nocturnas_rutina(id, noct_n)` | None                           | Cuántas tomas de madrugada mostrarle a un bebé (`-1` = las que sugiere su edad). Aparte de `editar_miembro_rutina` a propósito: se toca desde la franja Madrugada, no desde el form de Familia, así el form no la pisa |
| `borrar_miembro_rutina(id)`      | None                               | Baja definitiva + cascada manual: sus actividades, sus participaciones, los ajustes/duraciones/ocultos de `b<id>-*` y `a<actividad>`, **y su id dentro del `acompanan` de los demás** |
| `obtener_actividades_rutina()`   | `list[dict]`                       | Actividades activas con `participantes` y `pausas` anidados (por eso dicts y no Rows). Cada pausa trae su `id` |
| `crear_actividad_rutina(miembro_id, titulo, dibujo, inicio_min, dur_min, dias, meses, desde, hasta, anual, nota, participantes=())` | id nuevo | **Devuelve el id**: el editor lo necesita para colgarle recesos sin recargar |
| `editar_actividad_rutina(id, …los mismos…, participantes, activo)` | None | Pisa todos los campos editables. `participantes` reescribe la tabla puente (DELETE + INSERT) en la misma conexión |
| `borrar_actividad_rutina(id)`    | None                               | Baja definitiva + cascada manual: sus recesos, sus participantes y los ajustes/duraciones/ocultos de `a<id>` |
| `actividad_rutina_existe(id)`    | `bool`                             | Valida el id antes de escribir (activa o no). Lo usan las rutas |
| `crear_pausa_rutina(actividad_id, desde, hasta, anual, motivo)` | id nuevo | Receso de una actividad |
| `borrar_pausa_rutina(id)`        | None                               | Saca un receso suelto; no toca la actividad |
| `obtener_pendientes_rutina()`    | `list[dict]`                       | **Tareas** activas con `responsables` anidados (por eso dicts y no Rows) |
| `obtener_pendientes_hechas(desde, hasta)` | `list[Row]`               | Ocurrencias cerradas por rango de VENCIMIENTO. Quien llama pide un día antes del primero visible (lo hace `_rut_payload`) |
| `crear_pendiente_rutina(titulo, dibujo, repite, dias, fecha, desde, responsables=())` | id nuevo | `desde` = fecha de alta, la pone el servidor |
| `editar_pendiente_rutina(id, titulo, dibujo, repite, dias, fecha, responsables, activo)` | None | **No toca `desde`**: la fecha de alta es histórica |
| `borrar_pendiente_rutina(id)`    | None                               | Baja definitiva + cascada manual: responsables y todo el historial de tildados |
| `pendiente_rutina_existe(id)`    | `bool`                             | Valida el id antes de escribir |
| `marcar_pendiente_rutina(id, fechas, hecha)` | None                   | Tilda/destilda. `fechas` es LISTA: un toque puede cerrar la ocurrencia de ayer (arrastrada) y la de hoy. Idempotente |
| `cerrar_pendientes_vencidas(hoy, lookback_dias=45)` | `int`            | El barrido: cierra con `auto=1` lo que venció hace 2 días o más. Idempotente; el `lookback` evita miles de INSERT la primera vez |
| `guardar_suscripcion_push(endpoint, p256dh, auth, persona, user_email, user_agent='')` | `bool` | Upsert de UN navegador. Devuelve si **escribió de verdad**: con los mismos datos es un no-op REAL (ver el `WHERE` arriba). Recorta el `user_agent` a 300 chars. NO refresca `creada` |
| `borrar_suscripcion_push(endpoint)` | `int`                          | Filas borradas. `0` = no estaba, y **no es un error** (el navegador puede pedir la baja de algo ya borrado) |
| `borrar_suscripciones_push_de_email(user_email)` | `int`             | Todas las de una cuenta. La usa el logout (`auth.py`). Email vacío → `0`, no borra nada. Case-insensitive |
| `obtener_suscripciones_push(persona=None)` | `list[Row]`             | Todas o las de una persona, orden estable (`creada, endpoint`) |

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
