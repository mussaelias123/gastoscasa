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
| `lactancia_freezer_meses`    | `6`          | Vida útil freezer (meses desde extracción). Editable en Settings → Banco de leche |
| `lactancia_heladera_horas`   | `48`         | Vida útil heladera (horas desde extracción)  |
| `lactancia_aviso_freezer_dias` | `14`       | Ventana "vence pronto" freezer (días)        |
| `lactancia_aviso_heladera_horas` | `12`     | Ventana "vence pronto" heladera (horas)      |
| `lactancia_freezar_hasta_horas`  | `24`     | Antigüedad en heladera hasta la que el checkbox de freezar arranca tildado por defecto. Pasado el umbral nace destildado, pero no bloquea: se puede tildar igual |
| `lactancia_descongelada_horas`   | `24`     | Vida en heladera de una bolsa BAJADA del freezer (leche que ya estuvo congelada). Corre desde que se baja (`cargada`), no desde la extracción |
| `lactancia_aviso_descongelada_horas` | `6`  | Ventana "vence pronto" de la leche descongelada (horas) |
| `lactancia_recordatorio_activo`  | `False`  | Interruptor del recordatorio nocturno de "bajar bolsitas" (modo jardín: off hasta que el bebé arranque) |
| `lactancia_recordatorio_hora`    | `"21:00"`| `HH:MM` local a partir de la cual avisa el recordatorio. Aviso in-app (campana + banner), nunca bloquea |
| `bebe_nombre`                    | `"León"` | Nombre del bebé; se usa en los textos de la app (KPIs, confirmaciones). Vacío → la UI dice "el bebé" |
| `bebe_fecha_nacimiento`          | `""`     | `YYYY-MM-DD`. Habilita mostrar la edad y el mes de vida. A propósito NO se guarda peso/estatura ni se estima cuánta leche "debería" tomar (terreno médico) |
| `cotizacion_valor`           | `1500.0`     | Último ARS/USD oficial conocido              |
| `cotizacion_fecha`           | `None`       | Fecha del valor                              |
| `cotizacion_ultimo_intento`  | `None`       | Timestamp último intento                     |
| `cotizacion_ok`              | `False`      | Resultado último intento                     |
| `google_client_id`           | `""`         | OAuth                                        |
| `google_client_secret`       | `""`         | OAuth                                        |
| `secret_key`                 | `""`         | Flask session signing                        |
| `auth_disabled`              | `False`      | Bypass login SOLO dev (triple cerrojo, ver `auth.py`) |
| `backup_dir`                 | `"backups"`  | Carpeta de backups (relativa o absoluta)     |
| `paleta_light`               | dict 23 vars | Colores base en modo claro (editables). Incluye `texto-invertido` (`#ffffff`, del módulo Calendario) y `persona-leon` (turquesa pastel, del módulo Rutina). |
| `paleta_dark`                | dict 23 vars | Colores base en modo oscuro (editables). Mismas claves.                  |

## API
- `cargar_config(ruta=None)` → dict con DEFAULTS + overrides del archivo. **Paletas: merge por clave** — si `config.json` trae una paleta guardada con menos claves que DEFAULTS (ej. anterior a `texto-invertido`), las claves nuevas de DEFAULTS sobreviven y los overrides guardados se respetan.
- `guardar_config(data, ruta=None)` → merge `data` sobre lo existente y persiste.
- `es_primer_inicio()` → True si `first_run==True`.

## Reglas
1. Para agregar clave: definir en `DEFAULTS` (con valor seguro), luego usar en código.
2. La UI de Settings actualiza claves vía `POST /settings`. Validar tipos en `app.py`.
3. **Nunca commitear `config.json`** real (tiene secrets).
4. CLI flag `--config <ruta>` permite usar otro archivo (útil para tests / dev paralelo).

## Al modificar este dominio, actualizar:
- Tabla "Claves del config" si se agrega/quita clave.
