# Contexto: Backend (rutas Flask)

> Leer junto con `CLAUDE.md`. Este doc es para tareas que tocan `app.py`.

## Archivos del dominio
- `app.py` (~2500 líneas): rutas, schedulers, formatters Jinja, ngrok, backups, módulos Calendario, Lactancia, Rutina y Notificaciones.
- Imports clave: `database`, `auth`, `cotizacion`, `config`.

## Patrón general de ruta
1. Leer parámetros de `request.form` / `request.args`.
2. Si AJAX (`X-Requested-With: XMLHttpRequest`) → retornar `jsonify(...)`.
3. Si no → `redirect(url_for('gastos', mes=...))`.
4. Validar excepciones → en AJAX retornar `{'ok': False, 'error': str(e)}`, status 500.
## Mapa de rutas (actualizar al agregar/eliminar)

| Método | URL                       | Función               | Propósito                                        |
|--------|---------------------------|-----------------------|--------------------------------------------------|
| GET    | `/`                       | `index`               | Página Inicio (home): tarjeta Gastos (saldos + form movimiento, partials compartidos con /gastos) + tarjeta Lactancia (`lac_home=_home_lactancia_payload()`, form compartido `_form_lactancia.html`) + tarjeta Calendario (`cal_home=_home_calendario_payload()`, 100% server-render) + tarjeta Rutina (`rut_home=_rut_payload(hoy, hoy)` — mismo helper que /rutina, rango de 1 día; el template lo inyecta como `window.RUT_DATOS` y lo renderiza home.js vía `window.Rutina.hoyAhora()`). |
| GET    | `/gastos`                 | `gastos`              | Pantalla del módulo Gastos: saldos, formulario, tabla (ex `/`). |
| POST   | `/agregar`                | `agregar`             | Inserta movimiento (ingreso/gasto/cambio).       |
| POST   | `/eliminar/<id>`          | `eliminar`            | Borra movimiento por id.                         |
| GET/POST | `/editar/<id>`          | `editar`              | Edición completa de movimiento.                  |
| GET    | `/resumen`                | `resumen`             | Dashboard con métricas mensuales.                |
| POST   | `/api/cotizacion/refresh` | `api_cotizacion_refresh` | Forzar refresh cotización USD.               |
| GET    | `/api/metrics`            | `metrics`             | JSON con métricas (CPU, RAM, etc.).              |
| GET    | `/api/notificaciones`     | `api_notificaciones`  | JSON `{ok, total, items}`. Agrega todos los `NOTIF_PROVIDERS`. Ver `docs/CONTEXT_NOTIFICATIONS.md`. |
| GET    | `/api/saldos`             | `api_saldos`          | JSON `{saldos, gauges, historico, fecha}`. `?hasta=YYYY-MM-DD` = saldos a esa fecha; sin `hasta` = toda la DB. |
| GET/POST | `/settings`             | `settings`            | Ajustes. POST general guarda **solo** `app_name` y `factor_sueldo` (merge parcial; NO toca ngrok/OAuth/puerto). Otras acciones (form `accion`): `agregar_fijo`, `editar_fijo`, `eliminar_fijo`, `guardar_backup_dir`, `marcar_configurado`. |
| POST   | `/api/paleta`             | `api_paleta`          | Guarda `paleta_light` / `paleta_dark` desde Settings. |
| GET    | `/api/backups`            | `api_backups`         | JSON `{backups:[{archivo,etiqueta,size_mb}], carpeta}`. Lista backups `.db`. |
| POST   | `/api/backups/crear`      | `api_backups_crear`   | Crea backup manual de `fondo.db`. Form `descripcion` (opcional) → sufijo en el nombre. Devuelve `{ok,mensaje,backups}`. |
| POST   | `/api/backups/restaurar`  | `api_backups_restaurar` | Restaura `fondo.db` desde `archivo` (form). Hace copia `..._pre-restore.db` antes. |
| GET    | `/login`, `/auth/google`, `/auth/google/callback`, `/logout` | (blueprint `auth`) | OAuth Google. Ver `CONTEXT_AUTH.md`. |
| GET    | `/calendario`             | `calendario`          | Página del módulo Calendario (tareas del hogar). Context: `datos=_act_payload()`, `cal_areas=CAL_AREAS`, `cal_responsables=CAL_RESPONSABLES`. |
| GET    | `/api/actividades`        | `api_actividades`     | JSON `{'ok': True, **_act_payload()}`. |
| POST   | `/api/actividades/crear`  | `api_actividades_crear` | Alta. Valida con `_act_leer_form_comun`. |
| POST   | `/api/actividades/<id>/editar` | `api_actividades_editar` | Edición completa. Mismo validador que crear. |
| POST   | `/api/actividades/<id>/completar` | `api_actividades_completar` | Marca hecha (`fecha_hecha`); `repetir` decide si se archiva o repite. |
| POST   | `/api/actividades/<id>/reactivar` | `api_actividades_reactivar` | Reactiva una archivada. |
| POST   | `/api/actividades/<id>/eliminar` | `api_actividades_eliminar` | Borra la actividad y su historial. |
| GET    | `/lactancia`              | `lactancia`           | Página del módulo Lactancia (banco de leche). Context: `datos=_lac_payload()`. |
| GET    | `/api/lactancia`          | `api_lactancia`       | JSON `{'ok': True, **_lac_payload()}`. |
| POST   | `/api/lactancia/crear`    | `api_lactancia_crear` | Alta de partida (flujo estándar: heladera, con fecha/hora de extracción). Valida con `_lac_leer_form_alta`. |
| POST   | `/api/lactancia/<id>/cerrar` | `api_lactancia_cerrar` | Marca `usada` \| `descartada` (form `motivo`). `fecha_cierre` vacía → hoy. |
| POST   | `/api/lactancia/freezar`  | `api_lactancia_freezar` | Combina las heladeras tildadas (form `ids` CSV) en 1 partida de freezer: volumen sumado, extracción más vieja. Rechaza (400) si alguna no es freezable (`_lac_freezable`: vencida). Sin tope de horas — `freezar_hasta_horas` solo define el tildado por defecto del checkbox (`_lac_freezar_reciente`), no bloquea. |
| POST   | `/api/lactancia/<id>/reabrir` | `api_lactancia_reabrir` | Deshace un cierre. En una freezada, deshace la combinación COMPLETA (falla si la hija ya se cerró). |
| POST   | `/api/lactancia/<id>/editar` | `api_lactancia_editar` | Corrige volumen/notas/fecha/hora (ambas ubicaciones). |
| POST   | `/api/lactancia/<id>/eliminar` | `api_lactancia_eliminar` | Borrado definitivo. |
| GET    | `/rutina`                 | `rutina`              | Página del módulo Rutina. Context: `datos=_rut_payload(semana del server)`. |
| GET    | `/api/rutina`             | `api_rutina`          | JSON `{'ok': True, **_rut_payload(desde, hasta)}`. Query `desde`/`hasta` (fechas locales del CLIENTE; default semana del server). |
| POST   | `/api/rutina/ajustar`     | `api_rutina_ajustar`  | Upsert de un ajuste de horario. Form `fecha`, `etapa`, `item_id`, `inicio_min` (+ `desde`/`hasta` para la respuesta). Valida con `_rut_leer_form_ajuste`. |
| POST   | `/api/rutina/duracion`    | `api_rutina_duracion` | Estirar/encoger un ítem (drag estilo Teams). Form `fecha`, `etapa`, `item_id`, `dur_min` (5..720). Misma validación de ítems editables que `/ajustar`. |
| POST   | `/api/rutina/reset`       | `api_rutina_reset`    | Borra TODOS los ajustes de inicio Y duraciones de `fecha`+`etapa` ("↺ Plan original"). |
| POST   | `/api/rutina/tarea/crear` | `api_rutina_tarea_crear` | Alta de tarea añadida (modo edición). Form `etapa`, `usuario`, `titulo`, `emoji`, `inicio_min` (0..1439), `dur` (5..720), `fecha` (`''` = permanente). Valida con `_rut_leer_form_tarea`. |
| POST   | `/api/rutina/tarea/borrar` | `api_rutina_tarea_borrar` | Baja definitiva de una tarea añadida (form `id`); limpia también sus ocultos/ajustes `c-<id>`. |
| POST   | `/api/rutina/ocultar`     | `api_rutina_ocultar`  | Quita un ítem de la rutina. Form `etapa`, `item_id`, `fecha` (`''` = siempre). A diferencia de `/ajustar`, acá SÍ se aceptan ids derivados `mama-*`/`papa-*`. |
| POST   | `/api/rutina/restaurar`   | `api_rutina_restaurar` | Deshace TODOS los quitados de un ítem (permanente y fechados). Form `etapa`, `item_id`. |

> **Nota**: las viejas rutas `/git/*` (commit/log/restore como "backup") fueron eliminadas. Restauraban **código**, no datos. El backup/restore ahora es a nivel base de datos.

## Helpers internos clave
- `_calcular_monto_usd(monto, moneda, cfg)` → `(monto_usd, cotizacion_aplicada)`. Usa `cfg['cotizacion_valor']`. Si `moneda == 'usd'`, retorna `(monto, None)`.
- `_calcular_gauges(saldos, cotizacion_valor, historico=False)` → dict de los 3 gauges (ARS, USD, Total). Compartido por `gastos` y `api_saldos`. Con `historico=True` el gauge Total usa `ars_total_usd`/`usd_total_usd` (monto_usd congelado) en vez de valuar a la cotización vigente.
- `_gastos_fijos_json()` → JSON (string) con los gastos fijos activos (`descripcion`, `es_cuota`, `cuota_actual`, `total_cuotas`) para `window.GASTOS_FIJOS` del form rápido. Compartido por `gastos` e `index`.
- `inject_config()`: context_processor, expone `cfg` a todos los templates.
- Filtros Jinja: `fmt_ars`, `fmt_usd`, `fmt_fecha`, `fmt_fecha_hora`, `dias_desde_fecha`.
- `PALETA_META`: lista `(key, nombre, uso)` con las 23 variables de paleta (incluye `texto-invertido` y `persona-leon`). Se pasa al template de Settings y se usa para validar `/api/paleta`. Orden coincide con la tabla de `CONTEXT_FRONTEND.md`.
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
- `_home_calendario_payload()` → `{'mes_nombre', 'hoy' (día int), 'semanas' (monthdayscalendar lunes-primero, 0 = celda vacía), 'dias' {dia: [estados]} con prioridad/dedup/tope-3 espejo de dotsDelDia() de calendario.js, 'pendientes' (vencida|proxima, vencidas primero + fecha asc, cap 6)}`. Proyección de `_act_payload()` para la tarjeta Calendario del Inicio — JAMÁS recalcula estado/próxima fecha. La consume `index()` (`cal_home`, render 100% Jinja sin JS).
- `_act_leer_form_comun(form)`: valida y arma kwargs para `database.agregar_actividad` / `editar_actividad`. Compartido por crear/editar.
- `_act_parsear_fecha_opcional(valor, campo)`: valida `''` o `YYYY-MM-DD`; lanza `ValueError` si es inválida.
- `_es_ajax()`: `request.headers.get('X-Requested-With') == 'XMLHttpRequest'`.

## Módulo Lactancia — constantes y helpers
Banco de leche materna (partidas de freezer y heladera). Vencimiento y estado se
calculan acá (NUNCA se almacenan: cambiar un parámetro en Settings recalcula todo
al refrescar). Capa de datos pura en `database.py` (tabla `lactancia_partidas`).
Timestamps naive locales (`datetime.now()`), consistentes con `_ahora_iso()`.
**Camino estándar de la leche**: toda extracción entra por HELADERA; al freezer
solo se pasa la combinación de heladeras tildadas (`/api/lactancia/freezar`).
Sin alta directa a freezer en la UI ni traspaso individual.
- `LAC_UBICACIONES = ('freezer', 'heladera')`; `LAC_MOTIVOS_CIERRE = ('usada', 'descartada', 'trasladada')`.
- `_lac_params(cfg=None)` → dict con los 5 parámetros de config casteados a int (claves cortas: `freezer_meses`, `heladera_horas`, `aviso_freezer_dias`, `aviso_heladera_horas`, `freezar_hasta_horas`); fallback a DEFAULTS si vienen corruptos.
- `_lac_vencimiento(p, params)` → `datetime`. Freezer: extracción + N meses (reusa `_act_sumar_intervalo`, clamp fin de mes) al fin del día 23:59:59 (usable el día que vence, igual que el Excel). Heladera: `cargada` (timestamp inmutable) + N horas — cruza medianoche sin caso especial.
- `_lac_estado(p, params, ahora)` → cascada: `motivo_cierre` → ese estado > `vencida` > `vence_pronto` (ventana: freezer en días, heladera en horas) > `disponible` | `en_heladera`.
- `_lac_horas_en_heladera(p, ahora)` / `_lac_freezable(p, params, ahora)` / `_lac_freezar_reciente(p, params, ahora)` → antigüedad en heladera (desde `cargada`); si la partida TODAVÍA puede pasar al freezer (abierta, no vencida — sin tope de horas, el usuario decide); y si lleva menos de `freezar_hasta_horas` (solo define el tildado por defecto del checkbox, no bloquea nada). `_lac_freezable` espera dict (no `sqlite3.Row`).
- `_lac_enriquecer(row, params, ahora)` → dict + `vencimiento` (ISO), `estado`, `dias_restantes` (freezer) / `horas_restantes` + `horas_en_heladera` + `freezable` + `freezar_reciente` (heladera).
- `_lac_payload()` → `{'freezer': [FIFO], 'heladera': [FIFO], 'historial': [cerradas DESC], 'tablero': {...}, 'params': {...}, 'badge': int}`. FIFO = vencimiento asc, desempate por hora de extracción y luego id. Tablero: usables = disponible+vence_pronto (vencidas NO suman); trasladadas no cuentan como usadas ni descartadas; heladera separada del freezer. Fuente de TODAS las respuestas AJAX del módulo.
- `_home_lactancia_payload()` → `{'heladera': [...], 'freezer_primera': dict|None}`. Proyección de `_lac_payload()` para la tarjeta Lactancia del Inicio (todas las de heladera + la primera del freezer, FIFO). Solo recorta — JAMÁS reimplementa vencimientos/estados. La consume `index()` (`lac_home` → `window.LAC_HOME`).
- Badge de nav propio (`_lac_badge_count()` / `inject_lactancia_badge` / `lac_badge`) **eliminado**: lo reemplaza el sistema genérico de notificaciones (`NOTIF_PROVIDERS`, `_notificaciones()`, `inject_notif_badge` → `notif_badge`). Ver `docs/CONTEXT_NOTIFICATIONS.md`. Provider de este módulo: `_notif_lactancia()`, definido junto a los demás helpers `_lac_*`.
- `_lac_parsear_volumen(valor)` / `_lac_parsear_extraccion(form)` / `_lac_parsear_fecha_cierre(valor)` / `_lac_leer_form_alta(form)`: validaciones (ValueError). Volumen int 1..2000; fechas no futuras; ambas ubicaciones exigen fecha/hora de extracción (el momento real de carga lo pone el server en `cargada`, base del vencimiento de heladera).

## Módulo Rutina — helpers
Rutina diaria de León + agendas de mamá/papá con horarios en cascada. Las
DEFINICIONES de rutina por etapa y las actividades de estimulación son
constantes JS (`static/rutina.js`, `static/rutina-actividades.js`): el backend
persiste los AJUSTES de horario por `(fecha, etapa, item_id)` (tabla
`rutina_ajustes`), las TAREAS añadidas por el usuario (`rutina_tareas`) y los
ítems QUITADOS (`rutina_ocultos`) para sincronizar ambos teléfonos. La cascada
se calcula en el front. **La fecha-clave la define SIEMPRE el cliente** (su
fecha local): el server solo filtra por rango y hace upsert/delete — así no
hay ambigüedad de timezone. Convención `fecha = ''` en tareas/ocultos =
permanente (todos los días). Sin badge de nav ni parámetros de Settings (v1).
- `_RUT_ETAPAS = ('actual', 'tres', 'guarderia')`; `_RUT_USUARIOS = ('leon', 'mama', 'papa')`; `_RUT_ITEM_RE = ^[a-z0-9-]{1,40}$`.
- `_rut_semana_servidor()` → `(desde, hasta)` ISO, domingo..sábado de la semana de hoy. Solo fallback cuando el cliente no manda rango.
- `_rut_parsear_fecha(valor, campo)` → valida `YYYY-MM-DD` real (strptime); ValueError. `_rut_parsear_fecha_opcional` acepta además `''` (= permanente).
- `_rut_parsear_rango(fuente)` → lee `desde`/`hasta` de form o query; default semana del server; rechaza rango invertido o >31 días.
- `_rut_payload(desde, hasta)` → `{'ajustes': {fecha: {etapa: {item_id: min}}}, 'duraciones': {misma forma, dur_min}, 'hoy', 'desde', 'hasta', 'tareas': [...], 'ocultos': [...], 'calendario': [...]}`. Fuente de TODAS las respuestas AJAX del módulo. `calendario` = actividades del módulo Calendario (no terminadas) cuya `_act_proxima_fecha()` es HOY, como `{id, nombre, responsable}` — alimenta la tarjeta "Hoy por calendario" de /rutina (ofrece añadirlas a la rutina; NO toca el estado del Calendario).
- `_rut_leer_form_ajuste(form)` → `(fecha, etapa, item_id, inicio_min)`. Rechaza ids con prefijo `mama-`/`papa-` (derivados de `expandir()` en el front: heredan horario de León, NO editables) e `inicio_min` fuera de 0..2879 (las tomas nocturnas cruzan la medianoche).
- `_rut_leer_form_tarea(form)` → `(etapa, usuario, titulo, emoji, inicio_min, dur, fecha)`. Título 1..60 chars, emoji ≤8 chars, inicio 0..1439, dur 5..720.

## Schedulers en hilo
- `iniciar_scheduler_backup()`: chequea cada hora; backup de `fondo.db` 1 vez/día y solo si cambiaron los datos (hash vs `ultimo_backup.json`). Detalle en `CONTEXT_DEPLOY.md`.
- `iniciar_scheduler_cotizacion()`: refresh cotización USD a horarios fijos.
- Ambos se inician en `run_flask()`. NO bloquean request loop.

## Helpers de backup
- `_DB_PATH = database.DB_PATH` (fuente única; ya no hay join hardcodeado a `gastos.db` en `app.py`).
- `_get_backup_dir()`: lee `backup_dir` de config en caliente (sin reiniciar). Si es ruta relativa, la resuelve contra la carpeta del proyecto. Si es vacía, usa `backups/`.
- `hacer_backup_db(motivo, descripcion=None)`: copia `fondo.db` → `fondo_<fecha>[_descripcion].db` y registra hash en `ultimo_backup.json`. Devuelve el nombre del archivo o `None` si falló.
- `_hash_datos_db(ruta)` / `_leer_estado_backup()` / `_guardar_estado_backup()`: detección de cambios (SHA-256 del dump lógico + json de estado).
- `_listar_backups()`: lista los `.db` de la carpeta (más nuevo primero) con `archivo`, `etiqueta` (incluye descripción si la hay), `size_mb`.
- Restore (`api_backups_restaurar`): valida nombre (anti path-traversal), guarda `fondo_<fecha>_pre-restore.db`, luego copia el backup elegido sobre `fondo.db` (API SQLite).
- Carpeta de backups editable desde Settings vía `accion='guardar_backup_dir'` (POST `/settings`).
- **Compat rename 2026-07** (`gastos.db` → `fondo.db`): `_listar_backups`, `_limpiar_backups_antiguos` y `_ultimo_backup_fecha` filtran por `('fondo_', 'gastos_')` (los dos prefijos rotan juntos por fecha). `_fecha_de_backup` usa regex `^(?:fondo|gastos)_(\d{4}-\d{2}-\d{2})` (ya no slicing de largo fijo, porque el prefijo cambió de longitud) — mismo contrato: `None` si el nombre no matchea.

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
