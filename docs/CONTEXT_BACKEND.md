# Contexto: Backend (rutas Flask)

> Leer junto con `CLAUDE.md`. Este doc es para tareas que tocan `app.py`.

## Archivos del dominio
- `app.py` (1076 líneas): rutas, schedulers, formatters Jinja, ngrok, modo servicio.
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
| GET/POST | `/settings`             | `settings`            | Página de configuración (cfg.json + paleta).     |
| POST   | `/api/paleta`             | `api_paleta`          | Guarda `paleta_light` / `paleta_dark` desde Settings. |
| GET    | `/git/ping`               | `git_ping`            | Verifica que git esté disponible.                |
| POST   | `/git/commit`             | `git_commit`          | Commit + push automático.                        |
| GET    | `/git/log`                | `git_log`             | Últimos commits.                                 |
| POST   | `/git/restore`            | `git_restore`         | Restore a commit anterior.                       |
| GET    | `/login`, `/auth/google`, `/auth/google/callback`, `/logout` | (blueprint `auth`) | OAuth Google. Ver `CONTEXT_AUTH.md`. |

## Helpers internos clave
- `_calcular_monto_usd(monto, moneda, cfg)` → `(monto_usd, cotizacion_aplicada)`. Usa `cfg['cotizacion_valor']`. Si `moneda == 'usd'`, retorna `(monto, None)`.
- `inject_config()`: context_processor, expone `cfg` a todos los templates.
- Filtros Jinja: `fmt_ars`, `fmt_usd`, `fmt_fecha`, `fmt_fecha_hora`, `dias_desde_fecha`.
- `PALETA_META`: lista `(key, nombre, uso)` con las 21 variables de paleta. Se pasa al template de Settings y se usa para validar `/api/paleta`. Orden coincide con la tabla de `CONTEXT_FRONTEND.md`.
- `_HEX_RE`: regex `^#[0-9a-fA-F]{6}$` para validar hex de la paleta.

## Schedulers en hilo
- `iniciar_scheduler_backup()`: backup `gastos.db` cada hora a `backups/`.
- `iniciar_scheduler_cotizacion()`: refresh cotización USD a horarios fijos.
- Ambos se inician en `run_flask()`. NO bloquean request loop.

## Modo servicio (Windows)
`python app.py install|start|stop|remove` invoca subprocess sobre `build/nssm/nssm.exe`.

## Reglas específicas backend
1. **Toda ruta que muta DB debe responder a AJAX y a request normal** (formulario sin JS sigue funcionando).
2. **Cálculo USD**: usar `_calcular_monto_usd`. No reimplementar.
3. **Sueldo + factor**: si `tipo='ingreso'` y `categoria='sueldo'`, guardar `factor_aplicado = cfg['factor_sueldo']` (default 0.7). El cálculo de saldos lo aplica.
4. **Cuotas**: si `cuotas_checkbox` y `total_cuotas`, se crea fila en `gastos_fijos` con `es_cuota=1`. Categoría `Fijo` con `gasto_fijo` existente avanza la cuota.
5. **Cambio**: tipo `cambio` genera 2 inserts. Movimiento 1 = gasto en moneda origen. Movimiento 2 = ingreso en moneda destino. Categoría = `Cambio`.

## Al modificar este dominio, actualizar:
- Esta tabla de rutas (sección "Mapa de rutas").
- Si cambia un helper, actualizar la sección "Helpers internos clave".
- Si cambia el flujo de un tipo de movimiento, actualizar "Reglas específicas backend".
