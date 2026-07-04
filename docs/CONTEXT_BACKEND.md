# Contexto: Backend (rutas Flask)

> Leer junto con `CLAUDE.md`. Este doc es para tareas que tocan `app.py`.

## Archivos del dominio
- `app.py` (~1600 líneas): rutas, schedulers, formatters Jinja, ngrok, backups, módulo Calendario.
- Imports clave: `database`, `auth`, `cotizacion`, `config`.

## Patrón general de ruta
1. Leer parámetros de `request.form` / `request.args`.
2. Si AJAX (`X-Requested-With: XMLHttpRequest`) → retornar `jsonify(...)`.
3. Si no → `redirect(url_for('index', mes=...))`.
4. Validar excepciones → en AJAX retornar `{'ok': False, 'error': str(e)}`, status 500.

## Mapa de rutas (actualizar al agregar/eliminar)

| Método | URL                       | Función               | Propósito                                        |
|--------|---------------------------|-----------------------|--------------------------------------------------|
| GET    | `/`                       | `index`               | Pantalla principal: saldos, formulario, tabla.   |
| POST   | `/agregar`                | `agregar`             | Inserta movimiento (ingreso/gasto/cambio).       |
| POST   | `/eliminar/<id>`          | `eliminar`            | Borra movimiento por id.                         |
| GET/POST | `/editar/<id>`          | `editar`              | Edición completa de movimiento.                  |
| GET    | `/resumen`                | `resumen`             | Dashboard con métricas mensuales.                |
| POST   | `/api/cotizacion/refresh` | `api_cotizacion_refresh` | Forzar refresh cotización USD.               |
| GET    | `/api/metrics`            | `metrics`             | JSON con métricas (CPU, RAM, etc.).              |
| GET    | `/api/saldos`             | `api_saldos`          | JSON `{saldos, gauges, historico, fecha}`. `?hasta=YYYY-MM-DD` = saldos a esa fecha; sin `hasta` = toda la DB. |
| GET/POST | `/settings`             | `settings`            | Ajustes. POST general guarda **solo** `app_name` y `factor_sueldo` (merge parcial; NO toca ngrok/OAuth/puerto). Otras acciones (form `accion`): `agregar_fijo`, `editar_fijo`, `eliminar_fijo`, `guardar_backup_dir`, `marcar_configurado`. |
| POST   | `/api/paleta`             | `api_paleta`          | Guarda `paleta_light` / `paleta_dark` desde Settings. |
| GET    | `/api/backups`            | `api_backups`         | JSON `{backups:[{archivo,etiqueta,size_mb}], carpeta}`. Lista backups `.db`. |
| POST   | `/api/backups/crear`      | `api_backups_crear`   | Crea backup manual de `gastos.db`. Form `descripcion` (opcional) → sufijo en el nombre. Devuelve `{ok,mensaje,backups}`. |
| POST   | `/api/backups/restaurar`  | `api_backups_restaurar` | Restaura `gastos.db` desde `archivo` (form). Hace copia `..._pre-restore.db` antes. |
| GET    | `/login`, `/auth/google`, `/auth/google/callback`, `/logout` | (blueprint `auth`) | OAuth Google. Ver `CONTEXT_AUTH.md`. |
| GET    | `/calendario`             | `calendario`          | Página del módulo Calendario (tareas del hogar). Context: `datos=_act_payload()`, `cal_areas=CAL_AREAS`, `cal_responsables=CAL_RESPONSABLES`. |
| GET    | `/api/actividades`        | `api_actividades`     | JSON `{'ok': True, **_act_payload()}`. |
| POST   | `/api/actividades/crear`  | `api_actividades_crear` | Alta. Valida con `_act_leer_form_comun`. |
| POST   | `/api/actividades/<id>/editar` | `api_actividades_editar` | Edición completa. Mismo validador que crear. |
| POST   | `/api/actividades/<id>/completar` | `api_actividades_completar` | Marca hecha (`fecha_hecha`); `repetir` decide si se archiva o repite. |
| POST   | `/api/actividades/<id>/reactivar` | `api_actividades_reactivar` | Reactiva una archivada. |
| POST   | `/api/actividades/<id>/eliminar` | `api_actividades_eliminar` | Borra la actividad y su historial. |

> **Nota**: las viejas rutas `/git/*` (commit/log/restore como "backup") fueron eliminadas. Restauraban **código**, no datos. El backup/restore ahora es a nivel base de datos.

## Helpers internos clave
- `_calcular_monto_usd(monto, moneda, cfg)` → `(monto_usd, cotizacion_aplicada)`. Usa `cfg['cotizacion_valor']`. Si `moneda == 'usd'`, retorna `(monto, None)`.
- `_calcular_gauges(saldos, cotizacion_valor, historico=False)` → dict de los 3 gauges (ARS, USD, Total). Compartido por `index` y `api_saldos`. Con `historico=True` el gauge Total usa `ars_total_usd`/`usd_total_usd` (monto_usd congelado) en vez de valuar a la cotización vigente.
- `inject_config()`: context_processor, expone `cfg` a todos los templates.
- Filtros Jinja: `fmt_ars`, `fmt_usd`, `fmt_fecha`, `fmt_fecha_hora`, `dias_desde_fecha`.
- `PALETA_META`: lista `(key, nombre, uso)` con las 22 variables de paleta (incluye `texto-invertido`). Se pasa al template de Settings y se usa para validar `/api/paleta`. Orden coincide con la tabla de `CONTEXT_FRONTEND.md`.
- `_HEX_RE`: regex `^#[0-9a-fA-F]{6}$` para validar hex de la paleta.

## Módulo Calendario — constantes y helpers
Convención de datos: `intervalo_u` ∈ `dias|semanas|meses|anios`. Fechas TEXT `YYYY-MM-DD`. Cálculo de próxima fecha/estado vive acá a propósito, NO en `database.py` (capa de datos pura).
- `CAL_AREAS`: dict `{clave: (nombre, emoji)}` — `auto`, `casa`, `salud`, `documentos`, `mascotas`, `finanzas`, `hogar`.
- `CAL_RESPONSABLES`: dict `{clave: nombre}` — `familia`, `elias`, `mari`.
- `CAL_UNIDADES`: tupla `('dias', 'semanas', 'meses', 'anios')`.
- `_act_sumar_intervalo(fecha, n, unidad)` → `date`. Suma n unidades. Meses/años: clampea al último día del mes destino si el día no existe (31-ene +1 mes → 28/29-feb).
- `_act_proxima_fecha(act)` → `date | None`. Prioridad: `proxima_manual` > (`recurrente` y `ultima` → `ultima+intervalo`) > `ultima` > `None`.
- `_act_estado(act)` → `str`. `terminada` > sin próxima → `aldia` > `dias<0` → `vencida` > (`avisar` y `dias<=lead_dias`) → `proxima` > `aldia`.
- `_act_enriquecer(row)` → dict JSON-serializable: todos los campos de la fila + `proxima_fecha` (ISO/None) + `estado` + `dias_restantes` (int/None).
- `_act_payload()` → `{'actividades': [...enriquecidas], 'historial': [{'actividad_id','fecha_hecha'}...]}`. Fuente de TODAS las respuestas AJAX del módulo (fresco tras cada mutación).
- `_act_leer_form_comun(form)`: valida y arma kwargs para `database.agregar_actividad` / `editar_actividad`. Compartido por crear/editar.
- `_act_parsear_fecha_opcional(valor, campo)`: valida `''` o `YYYY-MM-DD`; lanza `ValueError` si es inválida.
- `_es_ajax()`: `request.headers.get('X-Requested-With') == 'XMLHttpRequest'`.

## Schedulers en hilo
- `iniciar_scheduler_backup()`: chequea cada hora; backup de `gastos.db` 1 vez/día y solo si cambiaron los datos (hash vs `ultimo_backup.json`). Detalle en `CONTEXT_DEPLOY.md`.
- `iniciar_scheduler_cotizacion()`: refresh cotización USD a horarios fijos.
- Ambos se inician en `run_flask()`. NO bloquean request loop.

## Helpers de backup
- `_get_backup_dir()`: lee `backup_dir` de config en caliente (sin reiniciar). Si es ruta relativa, la resuelve contra la carpeta del proyecto. Si es vacía, usa `backups/`.
- `hacer_backup_db(motivo, descripcion=None)`: copia `gastos.db` → `gastos_<fecha>[_descripcion].db` y registra hash en `ultimo_backup.json`. Devuelve el nombre del archivo o `None` si falló.
- `_hash_datos_db(ruta)` / `_leer_estado_backup()` / `_guardar_estado_backup()`: detección de cambios (SHA-256 del dump lógico + json de estado).
- `_listar_backups()`: lista los `.db` de la carpeta (más nuevo primero) con `archivo`, `etiqueta` (incluye descripción si la hay), `size_mb`.
- Restore (`api_backups_restaurar`): valida nombre (anti path-traversal), guarda `gastos_<fecha>_pre-restore.db`, luego copia el backup elegido sobre `gastos.db` (API SQLite).
- Carpeta de backups editable desde Settings vía `accion='guardar_backup_dir'` (POST `/settings`).

## Modo servicio (Windows)
`app.py` no tiene comandos de servicio propios. En producción NSSM envuelve
`python app.py` (mismo entry point que dev). Ver `docs/CONTEXT_DEPLOY.md`.

## Reglas específicas backend
1. **Toda ruta que muta DB debe responder a AJAX y a request normal** (formulario sin JS sigue funcionando).
2. **Cálculo USD**: usar `_calcular_monto_usd`. No reimplementar.
3. **Sueldo + factor**: si `tipo='ingreso'` y `categoria='sueldo'`, guardar `factor_aplicado = cfg['factor_sueldo']` (default 0.7). El cálculo de saldos lo aplica.
4. **Cuotas**: si `cuotas_checkbox` y `total_cuotas`, se crea fila en `gastos_fijos` con `es_cuota=1`. Categoría `Fijo` con `gasto_fijo` existente avanza la cuota.
5. **Cambio**: tipo `cambio` genera 2 inserts. Movimiento 1 = gasto en moneda origen. Movimiento 2 = ingreso en moneda destino. Categoría = `Cambio`.
6. **backup_dir**: clave de config editable desde Settings. Default `"backups"` (relativo). `_get_backup_dir()` lo resuelve en caliente; un cambio aplica sin reiniciar.

## Al modificar este dominio, actualizar:
- Esta tabla de rutas (sección "Mapa de rutas").
- Si cambia un helper, actualizar la sección "Helpers internos clave".
- Si cambia el flujo de un tipo de movimiento, actualizar "Reglas específicas backend".
