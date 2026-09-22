# Contexto: Configuración

> Leer junto con `CLAUDE.md`. Para todo lo relacionado a `config.json`.

## Archivos
- `config.py` (~130 líneas). API mínima: `cargar_config`, `guardar_config`, `es_primer_inicio`.
- `config.json` (gitignored). Fuente única de verdad runtime.
- `config.example.json` (en git). Plantilla.
- `.env` (gitignored): solo si hace falta para ngrok local.

## Claves del config (DEFAULTS en `config.py`)

| Clave                        | Default      | Uso                                          |
|------------------------------|--------------|----------------------------------------------|
| `port`                       | `5000`       | Puerto Flask                                 |
| `first_run`                  | `True`       | Banner de primer inicio                      |
| `ngrok_enabled`              | `False`      | Si arranca túnel ngrok                       |
| `ngrok_authtoken`            | `""`         | Token ngrok                                  |
| `ngrok_domain`               | `""`         | Dominio fijo (ej: miller-...)                |
| `app_name`                   | `Gastos Casa`| Título. Si contiene `DEV` muestra banner     |
| `factor_sueldo`              | `0.7`        | Multiplicador para ingresos tipo sueldo      |
| `lactancia_freezer_meses`    | `6`          | Vida útil freezer (meses desde extracción)   |
| `lactancia_heladera_horas`   | `48`         | Vida útil heladera (horas desde extracción)  |
| `lactancia_aviso_freezer_dias` | `14`       | Ventana "vence pronto" freezer (días)        |
| `lactancia_aviso_heladera_horas` | `12`     | Ventana "vence pronto" heladera (horas)      |
| `lactancia_freezar_hasta_horas`  | `24`     | Antigüedad en heladera hasta la que el checkbox de freezar arranca tildado por defecto. Pasado el umbral nace destildado, pero no bloquea: se puede tildar igual |
| `lactancia_descongelada_horas`   | `24`     | Vida en heladera de una bolsa BAJADA del freezer (leche que ya estuvo congelada). Corre desde que se baja (`cargada`), no desde la extracción |
| `lactancia_aviso_descongelada_horas` | `6`  | Ventana "vence pronto" de la leche descongelada (horas) |
| `lactancia_combinar_min_horas`   | `3`      | Horas mínimas en heladera que necesita cada extracción para poder juntarse con otra en la misma bolsita (tienen que estar a la misma temperatura). `0` = no verificar. Con una sola partida no aplica |
| `lactancia_bolsa_capacidad_activa` | `False`| Si está en `True`, no se deja cargar ni combinar más ml que la capacidad de bolsita declarada |
| `lactancia_bolsa_capacidad_ml`   | `150`    | La capacidad, en ml (solo se usa con el anterior en `True`) |
| `lactancia_pedir_confirmacion`   | `True`   | Pedir confirmación antes de cada acción que cierra una partida. Vivía en el `localStorage` del navegador (clave `lac-confirmar`), o sea que cada dispositivo tenía la suya; ahora es del servidor y vale para todos |
| `lactancia_recordatorio_activo`  | `False`  | Interruptor del recordatorio nocturno de "bajar bolsitas" (modo jardín: off hasta que el bebé arranque) |
| `lactancia_recordatorio_hora`    | `"21:00"`| `HH:MM` local a partir de la cual avisa el recordatorio. Aviso in-app (campana + banner), nunca bloquea |
| `bebe_nombre`                    | `"León"` | Nombre del bebé; se usa en los textos de la app (KPIs, confirmaciones). Vacío → la UI dice "el bebé" |
| `bebe_fecha_nacimiento`          | `""`     | `YYYY-MM-DD`. Habilita mostrar la edad y el mes de vida. A propósito NO se guarda peso/estatura ni se estima cuánta leche "debería" tomar (terreno médico). **Solo lo usa Lactancia**: desde el rework de Rutina, la fecha de nacimiento de cada miembro vive en `rutina_miembros` |
| `rutina_hora_amanecer`           | `"06:30"`| `HH:MM`. Hora a la que empieza el día en la hoja Rutina |
| `rutina_hora_noche`              | `"20:00"`| `HH:MM`. Tope del día: hasta ahí el motor encadena siestas del bebé; después arranca el sueño nocturno. Debe ser posterior al amanecer (lo valida `/api/rutina/ajustes`) |
| `rutina_cumple_activo`           | `True`   | Tarjeta de saludo el día del cumpleaños de cada miembro con fecha cargada |
| `cotizacion_valor`           | `1500.0`     | Último ARS/USD oficial conocido              |
| `cotizacion_fecha`           | `None`       | Fecha del valor                              |
| `cotizacion_ultimo_intento`  | `None`       | Timestamp último intento                     |
| `cotizacion_ok`              | `False`      | Resultado último intento                     |
| `google_client_id`           | `""`         | OAuth                                        |
| `google_client_secret`       | `""`         | OAuth                                        |
| `secret_key`                 | `""`         | Flask session signing                        |
| `auth_disabled`              | `False`      | Bypass login SOLO dev (triple cerrojo, ver `auth.py`) |
| `persona_dev`                | `"elias"`    | `elias` \| `mari`. Quién es el usuario con el bypass DEV activo: la sesión falsa es `dev@local`, que no está en el mapa email→persona de `auth.py`, y el módulo Personal necesita saber de quién es la cuenta. Cambiarla permite probar la vista de Mari sin OAuth. **En PROD no se lee nunca** (ahí la persona sale del email de Google) |
| `sw_enabled`                 | `False`      | Interruptor del **service worker** (PWA). `False` → la ruta `/sw.js` sirve la LÁPIDA (un SW que borra todas las cachés, se desregistra y suelta el control) y `base.html` no registra nada: además barre lo que haya quedado. `True` → sirve el SW real y la página lo registra. Desde la etapa 3 ese SW **hace cosas**: precachea el esqueleto (~460 KiB: `style.css` y `app.js` con `?v=`, más las 4 fuentes) y atiende una **lista blanca de `/static/`** con cache-first — las páginas, que vienen con los saldos adentro, y las rutas `/api/*` no entran nunca. Detalle en `CONTEXT_FRONTEND.md`. Se lee EN CALIENTE (`cargar_config()` va al disco en cada llamada): apagarlo es editar `config.json`, sin deploy ni reiniciar el servicio. ⚠ **En un dispositivo que YA lo instaló, volver el flag a `False` no alcanza con recargar**: el SW activo no usa `skipWaiting()`, así que la lápida entra recién cuando se cierran TODAS las pestañas del sitio — o al toque, con el botón "Reparar app" de Settings. **Se escribe como booleano JSON sin comillas**: un `"false"` entre comillas es un string no vacío y PRENDERÍA el service worker (por eso el código lo lee con `is True`, igual que `auth_disabled`). **No tiene UI a propósito**: es un kill switch, no una preferencia |
| `push_enabled`               | `False`      | Interruptor de las **notificaciones push** del sistema. Separado de `sw_enabled` a propósito: son dos modos de falla distintos (código viejo cacheado vs. avisos repetidos) y hay que poder apagar uno sin el otro. Todavía no lo lee nadie: se define ahora para que el apagado exista antes que la función |
| `push_vapid_publica`         | `""`         | Clave **pública** VAPID: base64url del punto sin comprimir (65 bytes → 87 caracteres). Es la que el navegador necesita para suscribirse (`applicationServerKey`), así que **viaja al HTML a propósito**: `base.html` la pone en `<body data-push-vapid="...">` y está en todas las páginas. Es pública por definición y sola no sirve para mandar nada. Vacía (el caso de hoy) → `dataset.pushVapid === ''`, o sea "push no configurado" |
| `push_vapid_secreta`         | `""`         | Clave **privada** VAPID: base64url del escalar de 32 bytes (43 caracteres), el formato que come `pywebpush` tal cual. Nombrada "secreta" y no "privada" para que no se confunda de un vistazo con la pública — y porque así cae sola bajo `MARCADORES_SECRETOS` y **no llega nunca a un template** |
| `push_contacto_mailto`       | `""`         | El `sub` del JWT VAPID: `mailto:alguien@dominio.com`, **con el prefijo**. Es a quién le reclama el servicio de push si la app se manda una macana. Apple lo valida de verdad y es más estricto que FCM |

| `backup_dir`                 | `"backups"`  | Carpeta de backups (relativa o absoluta)     |
| `paleta_light`               | dict 23 vars | Colores base en modo claro (editables). Incluye `texto-invertido` (`#ffffff`, del módulo Calendario) y `persona-leon` (turquesa pastel, del módulo Rutina). |
| `paleta_dark`                | dict 23 vars | Colores base en modo oscuro (editables). Mismas claves.                  |

### El par VAPID se genera UNA sola vez

Las tres claves de arriba se cargan a mano, corriendo
`python TempScripts/generar_vapid.py` (one-shot; imprime las dos claves en el
formato exacto y hace una firma de prueba en la misma corrida para confirmar
que el par sirve antes de pegarlo). **Se tratan igual que `secret_key`: se
generan una vez y no se tocan nunca más.**

Regenerarlas **invalida TODAS las suscripciones existentes** — cada navegador
guardó la clave pública vieja al suscribirse y el servicio de push rechaza lo
firmado con la nueva. Es el mismo trato que `secret_key` (cambiarla desloguea a
todos), con un agravante: **el fallo es silencioso**. La app no se rompe, no
hay error en pantalla; los avisos simplemente dejan de llegar y hay que
re-suscribir cada dispositivo a mano. Por eso el script **aborta** si
`config.json` ya tiene `push_vapid_publica` cargada (se saltea con `--forzar`).

## API
- `cargar_config(ruta=None)` → dict con DEFAULTS + overrides del archivo. **Paletas: merge por clave** — si `config.json` trae una paleta guardada con menos claves que DEFAULTS (ej. anterior a `texto-invertido`), las claves nuevas de DEFAULTS sobreviven y los overrides guardados se respetan.
- `guardar_config(data, ruta=None)` → merge `data` sobre lo existente y persiste.
- `es_primer_inicio()` → True si `first_run==True`.
- `LIMITES_LACTANCIA` → dict `{clave_corta: (min, max)}` con los rangos válidos de los parámetros numéricos del módulo. Lo valida el servidor en `POST /api/lactancia/config`, además del `min`/`max` del HTML.
- `MARCADORES_SECRETOS` → tupla de fragmentos de nombre: `('secret', 'token', 'password', 'clave_privada')`.
- `es_clave_secreta(clave)` → True si el NOMBRE contiene alguno de esos fragmentos.
- `sin_secretos(cfg)` → copia PLANA de `cfg` sin esas claves. Es lo que
  `app.py → inject_config()` le pasa a los templates bajo `cfg`.

## Qué de la config llega a los templates (y qué no)

`inject_config()` (app.py) es un `@app.context_processor`: manda `cfg` a
**todos** los templates, en **todos** los renders. Mandaba el dict entero —con
`secret_key`, `google_client_secret` y `ngrok_authtoken` adentro—; ningún
template los imprimía, así que no se filtraba nada, pero estaban a un
`{{ cfg }}` de salir al HTML. Desde 2026-09-22 va recortado con `sin_secretos()`.

- **El criterio es el NOMBRE de la clave, no una lista.** Una lista hay que
  acordarse de actualizarla y el olvido no falla: filtra. El criterio cubre
  sola a la clave secreta que se agregue mañana. Hoy se lleva `secret_key`,
  `google_client_secret`, `ngrok_authtoken` y `push_vapid_secreta`.
- **Regla al agregar una clave secreta**: el nombre tiene que contener uno de
  los fragmentos de `MARCADORES_SECRETOS`. Está congelado en
  `tests/test_cfg_secretos.py` (si aparece o desaparece una clave secreta, ese
  test se pone rojo y obliga a mirarlo).
- **El precio**: una clave que NO sea secreta pero se llame con uno de esos
  fragmentos tampoco llega al template. En Jinja eso no explota, renderiza
  vacío. Es el lado correcto del que fallar.
- **Las rutas NO pasan `cfg=` a mano.** Un `render_template('x.html', cfg=cfg)`
  pisa el del context processor con el dict completo y saltea el recorte sin
  que nada avise. `/gastos` y `/settings` lo hacían; se les sacó. `cfg` entra a
  los templates por un solo lugar.
- **Costo**: una comprensión de dict sobre ~45 claves por render, pegada a un
  `cargar_config()` que en ese mismo render abre y parsea `config.json`. Al
  lado del disco no se mide; cachearlo agregaría un invalidador nuevo (y los
  kill switches dependen justo de que NO haya caché) a cambio de nada.

## Dónde se edita cada cosa
- **Settings (`POST /settings`)**: `app_name`, `factor_sueldo`, cotización, paletas, backups, gastos fijos.
- **Panel "Ajustes" de `/lactancia`**: TODOS los `lactancia_*` y los `bebe_*`. Se trajo entero de la app suelta de banco de leche, que configura el módulo desde adentro del propio módulo. Settings ya **no** tiene sección "Banco de leche".
  - `POST /api/lactancia/config` — los tiempos, avisos, mínimo para combinar, bolsitas y confirmaciones. Guarda solo los campos que lleguen, así cada grupo de la pantalla se guarda por su cuenta.
  - `POST /api/lactancia/bebe` — nombre y fecha de nacimiento.
  - `POST /api/lactancia/recordatorio` — interruptor y hora del recordatorio nocturno.
- **A mano en `config.json`**: ngrok, OAuth, puerto, `auth_disabled`, `sw_enabled`, `push_enabled` y las tres `push_vapid_*` / `push_contacto_mailto` (no tienen UI). Los dos últimos son kill switches: se cambian en caliente y aplican en la siguiente carga de página. Lo que SÍ tiene UI es el rescate del lado del cliente: el botón **"Reparar app"** de Settings (`window.SW.barrer()`), que desregistra el service worker y borra las cachés de ESE dispositivo.

## Reglas
1. Para agregar clave: definir en `DEFAULTS` (con valor seguro), luego usar en código.
2. Validar tipos en `app.py`. Para los `lactancia_*` numéricos, agregar además el rango en `LIMITES_LACTANCIA`.
3. **Nunca commitear `config.json`** real (tiene secrets).
4. Si la clave nueva **es un secreto**: el nombre tiene que contener uno de los
   fragmentos de `MARCADORES_SECRETOS` (así el recorte a los templates la cubre
   sola) y el valor va SOLO en `config.json`, **nunca** en
   `config.example.json`.
   El criterio para poner un placeholder vacío ahí: solo si la clave es parte
   del **setup inicial guiado**. `config.example.json` tiene 6 claves y una es
   `ngrok_authtoken` (placeholder vacío, heredado de cuando se configura el
   túnel), pero NO están `secret_key` ni `google_client_secret`. Las
   `push_vapid_*` tampoco van: no se escriben a mano en el arranque, se generan
   con `TempScripts/generar_vapid.py` y se pegan después.
5. **No hay CLI flag `--config`.** `app.py` no parsea `sys.argv`: cada clon
   (`E:\FondoDev` y `E:\Fondo`) usa el `config.json` de su propia carpeta, y
   eso es lo que mantiene DEV y PROD separados. Los tests no tocan el archivo:
   parchean `config.cargar_config` (ver `tests/test_cfg_secretos.py`).
   *(Esta línea decía lo contrario hasta 2026-09-22; el flag nunca existió.)*

## Al modificar este dominio, actualizar:
- Tabla "Claves del config" si se agrega/quita clave.
