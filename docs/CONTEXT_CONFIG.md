# Contexto: Configuración

> Leer junto con `CLAUDE.md`. Para todo lo relacionado a `config.json`.

## Archivos
- `config.py` (~610 líneas, casi todo comentario). API: `cargar_config`, `guardar_config`, `es_primer_inicio`, `ConfigIlegible`.
- `config.json` (gitignored). Fuente única de verdad runtime.
- `config.json.<azar>.tmp` (gitignored): temporal de `guardar_config`. No debería quedar ninguno suelto (tiene secretos).
- `config.example.json` (en git). Plantilla.
- `.env` (gitignored): solo si hace falta para ngrok local.
- Tests: `tests/test_config_seguro.py` (lectura/escritura segura) y `tests/test_cfg_secretos.py` (recorte al template).

## Claves del config (DEFAULTS en `config.py`)

| Clave                        | Default      | Uso                                          |
|------------------------------|--------------|----------------------------------------------|
| `port`                       | `5000`       | Puerto Flask                                 |
| `first_run`                  | `True`       | Ya no hace falta primer arranque web: poner `false` (ver "Puesta en marcha"). Con `true`: `run_flask` solo escucha en localhost, NO levanta ngrok, `gastos.html` muestra banner. No abre nada |
| `ngrok_enabled`              | `False`      | Arranca túnel ngrok. Con `first_run: false` + `app_name` sin `DEV` → también cookie de sesión `Secure` (solo viaja por https; ver `CONTEXT_AUTH.md`) |
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
| `lactancia_pedir_confirmacion`   | `True`   | Confirmar antes de cada acción que cierra partida. Antes en `localStorage` del navegador (clave `lac-confirmar`): cada dispositivo tenía la suya; ahora del servidor, vale para todos |
| `lactancia_recordatorio_activo`  | `False`  | Interruptor del recordatorio nocturno de "bajar bolsitas" (modo jardín: off hasta que el bebé arranque) |
| `lactancia_recordatorio_hora`    | `"21:00"`| `HH:MM` local a partir de la cual avisa el recordatorio. Aviso in-app (campana + banner), nunca bloquea |
| `bebe_nombre`                    | `"León"` | Nombre del bebé; se usa en los textos de la app (KPIs, confirmaciones). Vacío → la UI dice "el bebé" |
| `bebe_fecha_nacimiento`          | `""`     | `YYYY-MM-DD`. Habilita mostrar la edad y el mes de vida. A propósito NO se guarda peso/estatura ni se estima cuánta leche "debería" tomar (terreno médico). **Solo lo usa Lactancia**: desde el rework de Rutina, la fecha de nacimiento de cada miembro vive en `rutina_miembros` |
| `rutina_hora_amanecer`           | `"06:30"`| `HH:MM`. Hora a la que empieza el día en la hoja Rutina |
| `rutina_hora_noche`              | `"20:00"`| `HH:MM`. Tope del día: hasta ahí el motor encadena siestas del bebé; después arranca el sueño nocturno. Debe ser posterior al amanecer (lo valida `/api/rutina/ajustes`) |
| `rutina_cumple_activo`           | `True`   | Tarjeta de saludo el día del cumpleaños de cada miembro con fecha cargada |
| `cotizacion_valor`           | `1500.0`     | Último ARS/USD oficial **aceptado** (el 1500.0 es solo un bootstrap). Base del control de ±50%: un valor nuevo que se aleje más se RECHAZA. Para destrabar una devaluación real: editarlo a mano (se lee en caliente) — `CONTEXT_COTIZACION.md` |
| `cotizacion_fecha`           | `None`       | Fecha del valor. `None`/vacía = nunca hubo una actualización exitosa: el próximo valor válido entra sin el control de ±50% |
| `cotizacion_ultimo_intento`  | `None`       | Timestamp último intento (éxito, rechazo o falla) |
| `cotizacion_ok`              | `False`      | Resultado último intento (`False` también si se rechazó el valor; el valor y la fecha no se tocan) |
| `google_client_id`           | `""`         | OAuth. **Obligatoria**: sin las dos credenciales el login queda CERRADO (`CONTEXT_AUTH.md`). Se registran en Authlib al arrancar: cambiarlas exige reiniciar el servicio |
| `google_client_secret`       | `""`         | OAuth. Ídem. Es secreta: nunca al log ni al HTML |
| `secret_key`                 | `""`         | Flask session signing. Se genera sola en el primer arranque si falta (`init_auth`) |
| `auth_disabled`              | `False`      | Bypass login SOLO dev (cuádruple cerrojo: + pedido desde la propia PC, nombre de sitio local y ngrok apagado; ver `auth.py`, `CONTEXT_AUTH.md`) |
| `persona_dev`                | `"elias"`    | `elias` \| `mari`. Quién es el usuario con el bypass DEV activo: la sesión falsa es `dev@local`, que no está en el mapa email→persona de `auth.py`, y el módulo Personal necesita saber de quién es la cuenta. Cambiarla permite probar la vista de Mari sin OAuth. **En PROD no se lee nunca** (ahí la persona sale del email de Google) |
| `sw_enabled`                 | `False`      | Interruptor **service worker** (PWA). `False` → `/sw.js` sirve LÁPIDA (SW que borra cachés, se desregistra, suelta control); `base.html` no registra nada y barre lo que quedó. `True` → SW real + página lo registra. Desde etapa 3 el SW **hace cosas**: precachea esqueleto (~460 KiB: `style.css` y `app.js` con `?v=`, +4 fuentes) y atiende **lista blanca de `/static/`** cache-first; páginas (traen saldos) y `/api/*` no entran nunca. Detalle `CONTEXT_FRONTEND.md`. EN CALIENTE (`cargar_config()` va al disco en cada llamada): apagar = editar `config.json`, sin deploy ni reiniciar servicio. ⚠ **Dispositivo que YA lo instaló: volver a `False` no alcanza con recargar**: SW activo no usa `skipWaiting()`; lápida entra recién al cerrar TODAS las pestañas del sitio — o al toque, botón "Reparar app" de Settings. ⚠ **Booleano JSON sin comillas**: `"false"` es string no vacío y PRENDERÍA el SW (código lo lee con `is True`, igual que `auth_disabled`). No tiene UI a propósito: kill switch, no preferencia |
| `push_enabled`               | `False`      | Interruptor **avisos push automáticos**. Separado de `sw_enabled` a propósito: dos modos de falla distintos (código viejo cacheado vs. avisos repetidos), apagar uno sin el otro. Lo lee SOLO `_push_encendido()` (un test lo cuenta), **en caliente** en cada vuelta del scheduler: apagar = editar `config.json`, sin deploy ni reiniciar servicio. `False` (hoy) → motor decide igual, escribe `SECO: flanco push ...` en log, pero no manda nada ni lee tabla suscripciones. `True` → manda de verdad, con frenos (horas de silencio y topes, `CONTEXT_PUSH_MOTOR.md` §2). ⚠ **NO lo mira el botón de prueba de Settings**, a propósito: es el diagnóstico del canal. Booleano JSON sin comillas (`is True`, igual que `sw_enabled`) |
| `push_vapid_publica`         | `""`         | Clave **pública** VAPID: base64url del punto sin comprimir (65 bytes → 87 caracteres). Es la que el navegador necesita para suscribirse (`applicationServerKey`), así que **viaja al HTML a propósito**: `base.html` la pone en `<body data-push-vapid="...">` y está en todas las páginas. Es pública por definición y sola no sirve para mandar nada. Vacía (el caso de hoy) → `dataset.pushVapid === ''`, o sea "push no configurado" |
| `push_vapid_secreta`         | `""`         | Clave **privada** VAPID: base64url del escalar de 32 bytes (43 caracteres), el formato que come `pywebpush` tal cual. Nombrada "secreta" y no "privada" para que no se confunda de un vistazo con la pública — y porque así cae sola bajo `MARCADORES_SECRETOS` y **no llega nunca a un template** |
| `push_contacto_mailto`       | `""`         | El `sub` del JWT VAPID: `mailto:alguien@dominio.com`, **con el prefijo**. Es a quién le reclama el servicio de push si la app se manda una macana. Apple lo valida de verdad y es más estricto que FCM |
| `push_silencio_desde`        | `"22:30"`   | Inicio **horas de silencio** del motor push (`HH:MM`). ⚠ **Ventana CRUZA MEDIANOCHE**: 22:30–07:00 = `hora >= desde` **O** `hora < hasta`, nunca `<=` entre dos números (así no silenciaría nunca). Hora corrupta → DEFAULT, igual que `lactancia_recordatorio_hora`. **Sin UI a propósito**: se edita acá, como `sw_enabled` — menos superficie |
| `push_silencio_hasta`        | `"07:00"`   | Fin horas de silencio (`HH:MM`). **Dos horas iguales = ventana vacía**: NUNCA hay silencio. Decisión explícita para el caso ambiguo: el otro significado ("callado las 24 h") apagaría avisos enteros con un typo, sin que nadie se entere. Para no recibir nada está `push_enabled`, que se ve. ⚠ Aviso en la ventana **no se difiere en una cola: no se marca**; a la salida el motor vuelve a leer el nivel real (`CONTEXT_PUSH_MOTOR.md` §2). ⚠ **Hora se normaliza al leerla**: `"7:00"` pasa el `strptime` y, comparada como string contra `"22:30"`, invertía la ventana y dejaba la madrugada entera sin silencio |

| `backup_dir`                 | `"backups"`  | Carpeta de backups (relativa o absoluta)     |
| `paleta_light`               | dict 23 vars | Colores base en modo claro (editables). Incluye `texto-invertido` (`#ffffff`, del módulo Calendario) y `persona-leon` (turquesa pastel, del módulo Rutina). |
| `paleta_dark`                | dict 23 vars | Colores base en modo oscuro (editables). Mismas claves.                  |

### El par VAPID se genera UNA sola vez

Las tres claves se cargan a mano con `python TempScripts/generar_vapid.py` (one-shot; imprime las dos claves y hace firma de prueba para confirmar que el par sirve antes de pegarlo). **Igual que `secret_key`: se generan una vez y no se tocan nunca más.**

Regenerarlas **invalida TODAS las suscripciones** — cada navegador guardó la clave pública vieja y el servicio de push rechaza lo firmado con la nueva. Mismo trato que `secret_key` (cambiarla desloguea a todos), con agravante: **el fallo es silencioso**. La app no se rompe, no hay error en pantalla; los avisos dejan de llegar y hay que re-suscribir cada dispositivo a mano. Por eso el script **aborta** si `config.json` ya tiene `push_vapid_publica` cargada (se saltea con `--forzar`).

## API
- `cargar_config(ruta=None)` → dict DEFAULTS + overrides del archivo. **Paletas: merge por clave** — si `config.json` trae paleta con menos claves que DEFAULTS (ej. anterior a `texto-invertido`), las claves nuevas sobreviven y los overrides guardados se respetan. **Nunca lanza**: archivo inexistente → DEFAULTS; ilegible (tras reintentos) → DEFAULTS + `AVISO:`.
- `guardar_config(data, ruta=None)` → merge `data` sobre lo existente y persiste, bajo candado y atómico. Lanza `ConfigIlegible` SIN escribir nada si el archivo existe y no se puede leer.
- `ConfigIlegible` → `Exception` (no `ValueError`, a propósito: las rutas atrapan `ValueError` antes y contestarían 400).
- `es_primer_inicio()` → True si `first_run==True`.
- `LIMITES_LACTANCIA` → dict `{clave_corta: (min, max)}`, rangos válidos de los numéricos del módulo. Lo valida el servidor en `POST /api/lactancia/config`, además del `min`/`max` del HTML.
- `MARCADORES_SECRETOS` → tupla de fragmentos de nombre: `('secret', 'token', 'password', 'clave_privada')`.
- `es_clave_secreta(clave)` → True si el NOMBRE contiene alguno de esos fragmentos.
- `sin_secretos(cfg)` → copia PLANA de `cfg` sin esas claves. Es lo que `app.py → inject_config()` pasa a los templates bajo `cfg`.

## Lectura y escritura seguras (desde 2026-10-02)
`config.json` guarda lo que no se recupera (credenciales Google, `secret_key`, VAPID, ngrok) y se escribe seguido (cotización al arrancar / 08:00 / 17:00 y cada guardado de ajustes). Antes `open('w')` truncaba primero: un lector veía el archivo a medias (~18% de lecturas, medido), `cargar_config` se tragaba el error y devolvía DEFAULTS —sin credenciales— y la app quedaba abierta; y un `guardar_config` que leía a medias escribía DEFAULTS + su cambio y **borraba los secretos para siempre** (bastaban dos escritores a la vez). Porqué largo en `config.py` ("LECTURA Y ESCRITURA SEGURAS").

- **Candado** `_LOCK` (RLock, de proceso) sobre todo el leer-modificar-escribir y sobre cada lectura.
- **Escritura atómica**: temporal `config.json.<azar>.tmp` en la MISMA carpeta (`indent=2`, `ensure_ascii=False`, `fsync`) + `os.replace`. Windows falla con `PermissionError` si otro proceso (editor, antivirus) tiene abierto el destino: reintenta ~1 s. El temporal se borra en TODO camino de error (si ni así, `AVISO:` con el nombre). `.gitignore` cubre `config.json.*.tmp`.
- **`guardar_config` es estricto**: JSON roto o vacío, raíz que no es objeto o UTF-8 inválido → `ConfigIlegible` y no escribe nada (ni un temporal). Si el archivo no existe, parte de DEFAULTS y lo crea.
- **`cargar_config` reintenta** (4 × 50 ms: cubre a un humano guardando con editor) y lee UTF-8 con o sin BOM (lo guardan varios editores de Windows y PowerShell 5.1). Un `AVISO:` por minuto como mucho (se llama en cada request); nunca loguea el contenido.
- **Si `config.json` se rompe con la app andando**: login CERRADO para todos (`CONTEXT_AUTH.md`), `AVISO: config.json ilegible: ...` con tipo y línea/columna, y los guardados de ajustes fallan SIN tocar el archivo (rutas de `app.py` lo devuelven por su `except Exception`; schedulers lo loguean; `/settings` no tiene `try` y da 500). Se arregla el JSON a mano, sin reiniciar. **Arrancar** con el archivo ilegible: `init_auth` corta con `ConfigIlegible`.
- Límite: el candado es de PROCESO. Dos procesos escribiendo el mismo archivo no se frenan entre sí (`os.replace` solo protege a los lectores).

## Puesta en marcha: 100% por `config.json` (no hay primer arranque web)
Decisión del usuario: configuración inicial en `config.json`, no en la web. Sin credenciales Google la app no deja entrar a nadie (`CONTEXT_AUTH.md`), así que tampoco hay "modo configuración" por la web.
1. Crear `config.json` (copiar `config.example.json`). Sin archivo, la app lo crea con DEFAULTS + `secret_key`, pero queda cerrada.
2. Agregar `google_client_id` y `google_client_secret` (Google Cloud Console → Credenciales → ID de cliente OAuth; URI de redirección: `https://<dominio>/auth/callback`). `config.example.json` no trae esas dos claves: se escriben a mano.
3. `"first_run": false` (con DEFAULT `true`, `run_flask` no levanta ngrok).
4. PROD: `ngrok_enabled`, `ngrok_authtoken`, `ngrok_domain`, `port`. DEV sin OAuth: `auth_disabled: true` con ngrok apagado.
5. Arrancar: `secret_key` se genera y guarda sola. Cambiar credenciales después → reiniciar servicio.

## Qué de la config llega a los templates (y qué no)

`inject_config()` (app.py) es `@app.context_processor`: manda `cfg` a **todos** los templates, en **todos** los renders. Antes mandaba el dict entero (con `secret_key`, `google_client_secret` y `ngrok_authtoken` adentro); ningún template los imprimía, así que no se filtraba nada, pero estaban a un `{{ cfg }}` de salir al HTML. Desde 2026-09-22 va recortado con `sin_secretos()`.

- **Criterio = NOMBRE de la clave, no lista.** Una lista hay que acordarse de actualizarla y el olvido no falla: filtra. El criterio cubre sola a la clave secreta que se agregue mañana. Hoy se lleva `secret_key`, `google_client_secret`, `ngrok_authtoken` y `push_vapid_secreta`.
- **Regla al agregar clave secreta**: el nombre tiene que contener uno de los fragmentos de `MARCADORES_SECRETOS`. Congelado en `tests/test_cfg_secretos.py` (si aparece o desaparece una clave secreta, ese test se pone rojo y obliga a mirarlo).
- **El precio**: una clave que NO sea secreta pero se llame con uno de esos fragmentos tampoco llega al template. En Jinja no explota, renderiza vacío. Es el lado correcto del que fallar.
- **Rutas NO pasan `cfg=` a mano.** `render_template('x.html', cfg=cfg)` pisa el del context processor con el dict completo y saltea el recorte sin que nada avise. `/gastos` y `/settings` lo hacían; se les sacó. `cfg` entra a los templates por un solo lugar.
- **Costo**: comprensión de dict sobre ~45 claves por render, pegada a un `cargar_config()` que en ese render abre y parsea `config.json`. Al lado del disco no se mide; cachearlo agregaría un invalidador nuevo (y los kill switches dependen justo de que NO haya caché) a cambio de nada.

## Dónde se edita cada cosa
- **Settings (`POST /settings`)**: `app_name`, `factor_sueldo`, cotización, paletas, backups, gastos fijos.
- **Panel "Ajustes" de `/lactancia`**: TODOS los `lactancia_*` y los `bebe_*`. Se trajo entero de la app suelta de banco de leche, que configura el módulo desde adentro del propio módulo. Settings ya **no** tiene sección "Banco de leche".
  - `POST /api/lactancia/config` — los tiempos, avisos, mínimo para combinar, bolsitas y confirmaciones. Guarda solo los campos que lleguen, así cada grupo de la pantalla se guarda por su cuenta.
  - `POST /api/lactancia/bebe` — nombre y fecha de nacimiento.
  - `POST /api/lactancia/recordatorio` — interruptor y hora del recordatorio nocturno.
- **A mano en `config.json`**: ngrok, OAuth, puerto, `auth_disabled`, `sw_enabled`, `push_enabled`, las dos `push_silencio_*` y las tres `push_vapid_*` / `push_contacto_mailto` (no tienen UI). Los dos flags son kill switches: en caliente, aplican en la siguiente carga de página. Lo que SÍ tiene UI es el rescate del cliente: botón **"Reparar app"** de Settings (`window.SW.barrer()`), desregistra el SW y borra cachés de ESE dispositivo.

## Reglas
1. Para agregar clave: definir en `DEFAULTS` (con valor seguro), luego usar en código.
2. Validar tipos en `app.py`. Para los `lactancia_*` numéricos, agregar además el rango en `LIMITES_LACTANCIA`.
3. **Nunca commitear `config.json`** real (tiene secrets).
4. Clave nueva **secreta**: nombre con uno de los fragmentos de `MARCADORES_SECRETOS` (el recorte a templates la cubre sola) y valor SOLO en `config.json`, **nunca** en `config.example.json`.
   Placeholder vacío en el example: solo si la clave es parte del **setup inicial guiado**. `config.example.json` tiene 6 claves; una es `ngrok_authtoken` (placeholder vacío, heredado del túnel), pero NO están `secret_key` ni `google_client_secret`. Las `push_vapid_*` tampoco van: no se escriben a mano en el arranque, se generan con `TempScripts/generar_vapid.py` y se pegan después.
5. **No hay CLI flag `--config`.** `app.py` no parsea `sys.argv`: cada clon
   (`E:\FondoDev` y `E:\Fondo`) usa el `config.json` de su propia carpeta, y
   eso es lo que mantiene DEV y PROD separados. Los tests no tocan el archivo:
   parchean `config.cargar_config` (ver `tests/test_cfg_secretos.py`).
   *(Esta línea decía lo contrario hasta 2026-09-22; el flag nunca existió.)*

## Al modificar este dominio, actualizar:
- Tabla "Claves del config" si se agrega/quita clave.
