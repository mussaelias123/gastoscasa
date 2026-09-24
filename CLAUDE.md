# Gastos Casa — Guía maestra para agentes IA

> **Este archivo es el ÍNDICE.** No contiene detalle de código.
> Para profundizar en un dominio, leer el `docs/CONTEXT_*.md` correspondiente.
> Para tareas especializadas, invocar el sub-agente apropiado en `agents/`.

---

## 1. Modelo de negocio (mínimo indispensable)

- App personal de finanzas para 2 personas: **Elías** y **Mari**.
- 2 monedas: **AR$** (pesos argentinos) y **USD** (dólares).
- 4 saldos primarios: `elias_ars`, `elias_usd`, `mari_ars`, `mari_usd`.
- Saldos **calculados dinámicamente** desde tabla `movimientos` (no almacenados).
- Movimiento = `ingreso | gasto | cambio` (cambio genera 2 filas: salida + entrada).
- Cada movimiento guarda equivalente en USD (`monto_usd`) usando cotización oficial vigente al insertar.

---

## 2. Mapa de archivos por dominio

| Dominio       | Archivos principales                                  | Doc de contexto                  |
|---------------|--------------------------------------------------------|----------------------------------|
| Backend rutas | `app.py`                                               | `docs/CONTEXT_BACKEND.md`        |
| Base de datos | `database.py`, `fondo.db` (legacy: `gastos.db`)        | `docs/CONTEXT_DB.md`             |
| Cotización    | `cotizacion.py`, `tests/test_cotizacion.py`            | `docs/CONTEXT_COTIZACION.md`     |
| Auth Google   | `auth.py`, `templates/login.html`                      | `docs/CONTEXT_AUTH.md`           |
| Config        | `config.py`, `config.json`, `config.example.json`      | `docs/CONTEXT_CONFIG.md`         |
| Personal      | `app.py` (ruta `/personal` + helpers `_persona_actual`, `_leer_personal_form`, `_personal_*`), `database.py` (columna `movimientos.personal`, `calcular_saldos_personales`, `obtener_sueldos_resto`), `auth.py` (`PERSONAS_POR_EMAIL`), `templates/personal.html`, `tests/test_personal.py` | `docs/CONTEXT_DB.md` + `docs/CONTEXT_BACKEND.md` |
| Dashboard     | `static/resumen.js`, `templates/_dashboard_resumen.html` (compartidos por `/resumen` y `/personal`), `templates/resumen.html` | `docs/CONTEXT_FRONTEND.md`        |
| Frontend      | `static/style.css`, `static/app.js`, `static/calendario.js`, `static/lactancia.js`, `static/grafico.js`, `static/rutina.js`, `static/rutina-sueno.js`, `static/rutina-dibujos.js`, `static/rutina-actividades.js`, `static/home.js`, `templates/*.html`| `docs/CONTEXT_FRONTEND.md`       |
| PWA (instalar) | `app.py` (ruta `/manifest.json`), `templates/base.html` (`<link rel="manifest">` + meta `theme-color`), `static/img/icon-192.png`, `icon-512.png`, `icon-512-maskable.png`, `TempScripts/generar_iconos_pwa.py` | `docs/CONTEXT_BACKEND.md` (ruta) + `docs/CONTEXT_FRONTEND.md` (head) |
| PWA (service worker) | `templates/sw.js` (⚠ **no es un template Jinja**: es el JS del service worker, con dos mitades — lápida y activo), `app.py` (ruta `/sw.js` + `_sw_seccion` + `_SW_LAPIDA_EMERGENCIA`), `auth.py` (`service_worker` en `rutas_publicas`), `config.py` (flags `sw_enabled` / `push_enabled`, apagados), `templates/base.html` (registrar o barrer), `static/app.js` (`window.SW.barrer()`), `templates/settings.html` (botón "Reparar app"), `tests/test_sw.py` (la ruta y el apagado), `tests/test_static_version.py` (el `?v=` que comparte con el caché) | `docs/CONTEXT_BACKEND.md` + `docs/CONTEXT_CONFIG.md` (los flags) + `docs/CONTEXT_AUTH.md` (`rutas_publicas`) + `docs/CONTEXT_FRONTEND.md` |
| Push (VAPID)  | `config.py` (claves `push_vapid_publica` / `push_vapid_secreta` / `push_contacto_mailto`, y `MARCADORES_SECRETOS` + `sin_secretos`), `app.py` (`inject_config` manda el `cfg` RECORTADO), `templates/base.html` (`<body data-push-vapid>`), `TempScripts/generar_vapid.py`, `tests/test_cfg_secretos.py` | `docs/CONTEXT_PUSH.md` + `docs/CONTEXT_CONFIG.md` (claves + recorte) + `docs/CONTEXT_AUTH.md` (el `cfg` de los templates) |
| Push (suscripciones) | `database.py` (tabla `push_suscripciones` + `guardar_suscripcion_push` / `borrar_suscripcion_push` / `borrar_suscripciones_push_de_email` / `obtener_suscripciones_push`), `app.py` (`/api/push/alta`, `/api/push/baja`, `_push_leer_suscripcion`), `auth.py` (el `logout` que limpia), `tests/test_push_suscripciones.py`. ⚠ Acá solo se GUARDA a quién avisarle | `docs/CONTEXT_PUSH.md` + `docs/CONTEXT_DB.md` (la tabla y el porqué del `WHERE` del upsert) + `docs/CONTEXT_BACKEND.md` (las dos rutas) + `docs/CONTEXT_AUTH.md` (el logout) |
| Push (envío) | `app.py` (`/api/push/prueba` + `_push_payload` / `_push_claves_vapid` / `_push_enviar` / `_PUSH_TIMEOUT` / `_PUSH_TTL` / `_PushSinClaves`), `templates/sw.js` (listeners `push` y `notificationclick` en la mitad ACTIVO, + `pushAvisarVentanas` que refresca la campana por `postMessage`), `static/app.js` (`window.Push` y el listener de `serviceWorker` → `message`), `templates/settings.html` (tarjeta "Avisos en el teléfono"), `auth.py` (el logout que ahora borra SOLO el navegador que se va), `tests/test_push_envio.py`. ⚠ **El payload nunca lleva montos ni saldos** (se lee en la pantalla bloqueada) y la `url` va RELATIVA. Hay **DOS** llamadores de `_push_enviar` y ni uno más: el BOTÓN de Settings (no mira el flag, es el diagnóstico) y el MOTOR (`_push_ciclo`, sí lo mira). `push_enabled` sigue apagado. ⚠ `showNotification()` se llama SIEMPRE: el `postMessage` va colgado al final y no puede taparla | `docs/CONTEXT_PUSH.md` (envío) + `docs/CONTEXT_BACKEND.md` (la ruta) + `docs/CONTEXT_FRONTEND.md` (la tarjeta y el listener) |
| Push (motor automático) | `app.py` (registry `PUSH_AVISOS` justo después de `NOTIF_PROVIDERS`, + `_push_encendido` / `_push_avisos_ahora` / `_push_horas_silencio` / `_push_en_silencio` / `_push_estado_leer` / `_push_estado_guardar` / `_push_ciclo` / `_scheduler_push` / `iniciar_scheduler_push` / `_PUSH_INTERVALO` / `_PUSH_TOPE_VUELTA` / `_PUSH_TOPE_DIA` / `_PUSH_TTL_AVISO`), `config.py` (`push_enabled`, `push_silencio_desde` / `_hasta`), `tests/test_push_scheduler.py` (el flanco) + `tests/test_push_encendido.py` (el encendido y los frenos), `TempScripts/simular_flancos_push.py`. Estado en `push_estado.json` (dentro de `backup_dir`, **no en la DB**). ⚠ **El hilo corre solo y YA está conectado al envío**, pero `push_enabled` está en `False`: hace lo de siempre y loguea `SECO: ...` lo que mandaría. Prendido manda, con frenos — horas de silencio (⚠ la ventana CRUZA la medianoche, y la hora se NORMALIZA porque `"7:00"` pasaba el `strptime` y la invertía), tope por vuelta y por día, y el intervalo entre tandas (un servicio que reinicia en loop mandaba 8 avisos en un minuto). ⚠ **Lo retenido NO se marca: el diferimiento no es una cola**, se re-evalúa contra el nivel real — con la trampa de que un aviso cierto SOLO de noche no sale nunca (por eso el estado lleva `diferidas`, que es diagnóstico). El `detalle` del ítem NO entra en la clave de dedup ni en el cuerpo | `docs/CONTEXT_PUSH_MOTOR.md` (**todo el motor**) + `docs/CONTEXT_CONFIG.md` (el flag y las horas) + `docs/CONTEXT_BACKEND.md` (helpers y schedulers) + `docs/CONTEXT_DEPLOY.md` (cómo se lee el ensayo, y qué mirar encendido) |
| Notificaciones (**estándar de Núcleo**) | `app.py` (bloque "NOTIFICACIONES — EL ESTÁNDAR DE NÚCLEO PARA AVISAR": providers `_notif_*` + registries `NOTIF_PROVIDERS` / `PUSH_AVISOS` + `_notificaciones()` + `inject_notif_badge` + `/api/notificaciones`), `static/app.js` (`window.Notif`), `templates/base.html` (campana/panel), `static/style.css` (sección PANEL NOTIFICACIONES). ⚠ **Es de NÚCLEO, no de un módulo**: que hoy los providers sean de Lactancia es circunstancial. Cualquier módulo avisa por acá, con el MISMO contrato de 7 claves y el MISMO canal — ninguno escribe su propia campana ni su propio badge | `docs/CONTEXT_NOTIFICATIONS.md` (**el estándar; §3 es el procedimiento para agregar una**) |
| Deploy/serv   | NSSM (`E:\Fondo\nssm.exe`, fuera de git), ngrok, `logs/`, `logutil.py` | `docs/CONTEXT_DEPLOY.md` |
| Scripts ad-hoc| `TempScripts/`                                         | (one-shot, no producción)        |

> **Dev / Prod**: `E:\Fondo` = producción (servicio Windows `GastosCasa` vía NSSM,
> arranca solo). `E:\FondoDev` = desarrollo, se corre a mano con `python app.py`.
> El proyecto **no se compila**: NSSM solo envuelve `python app.py`.

---

## 3. Tabla "tarea → contexto a leer"

| Tipo de tarea                          | Leer obligatorio                                              | Sub-agente sugerido     |
|----------------------------------------|---------------------------------------------------------------|-------------------------|
| Cambio visual (color, layout, badge)   | `CLAUDE.md` + `CONTEXT_FRONTEND.md`                           | `frontend-dev`          |
| Nueva ruta o endpoint Flask            | `CLAUDE.md` + `CONTEXT_BACKEND.md` + `CONTEXT_DB.md`          | `backend-dev`           |
| Cambio de esquema, query o saldo       | `CLAUDE.md` + `CONTEXT_DB.md`                                 | `db-engineer`           |
| Bug en cotización USD                  | `CLAUDE.md` + `CONTEXT_COTIZACION.md`                         | `cotizacion-maintainer` |
| Login, OAuth, sesión                   | `CLAUDE.md` + `CONTEXT_AUTH.md`                               | `auth-maintainer`       |
| Build, instalación, servicio Windows   | `CLAUDE.md` + `CONTEXT_DEPLOY.md`                             | (manual)                |
| Verificación final en navegador        | `CLAUDE.md` + `CONTEXT_DEPLOY.md` (sección ngrok)             | `verifier`              |
| Script one-shot (backfill, migración)  | `CLAUDE.md` + `CONTEXT_DB.md`                                 | `db-engineer`           |
| Módulo Lactancia (banco de leche)      | `CLAUDE.md` + `CONTEXT_BACKEND.md` + `CONTEXT_DB.md` + `CONTEXT_FRONTEND.md` (+ `CONTEXT_CONFIG.md` si tocás parámetros) | según capa |
| Módulo Rutina (rutina diaria de la familia) | `CLAUDE.md` + `CONTEXT_FRONTEND.md` (la lógica vive en `static/rutina.js`; el motor de ventanas de sueño en `static/rutina-sueno.js`) + `CONTEXT_DB.md` (familia y actividades) + `CONTEXT_BACKEND.md` si tocás rutas (+ `CONTEXT_CONFIG.md` para las horas de día/noche) | según capa |
| Módulo Personal (cuenta propia de cada uno) | `CLAUDE.md` + `CONTEXT_DB.md` (la columna `personal` y el filtro que no se puede olvidar) + `CONTEXT_BACKEND.md` (ruta y helpers) + `CONTEXT_FRONTEND.md` si tocás la pantalla o el form | según capa |
| **Que CUALQUIER módulo avise algo** (nuevo o existente: un vencimiento, un pendiente, algo que hay que mirar) | `CLAUDE.md` + `CONTEXT_NOTIFICATIONS.md` §3 — **ese es el procedimiento, no inventar otro**. ⚠ NO agregar badges, contadores ni banners propios del módulo: se escribe un provider `_notif_<modulo>()` y se registra. ⚠ Registrarlo en `NOTIF_PROVIDERS` **no** lo hace mandar pushes: el teléfono se decide aparte, en `PUSH_AVISOS` (leer antes `CONTEXT_PUSH_MOTOR.md`) | según capa |
| PWA (manifest, íconos, instalar en el celu/escritorio) | `CLAUDE.md` + `CONTEXT_BACKEND.md` (ruta `/manifest.json`) + `CONTEXT_FRONTEND.md` (head de `base.html`, excepción 1(e) de íconos) + `CONTEXT_AUTH.md` si tocás `rutas_publicas` | según capa |
| PWA — service worker / caché / push | `CLAUDE.md` + `CONTEXT_BACKEND.md` (ruta `/sw.js` y por qué NO va con `render_template`) + `CONTEXT_CONFIG.md` (los interruptores `sw_enabled` / `push_enabled`) + `CONTEXT_FRONTEND.md` (registro en `base.html` y `window.SW`) + `CONTEXT_AUTH.md` si tocás `rutas_publicas`. **Antes de prender nada, leer el encabezado de `templates/sw.js`**: un service worker no se apaga borrando la ruta, y por eso existe la lápida | según capa |
| PWA — push (a quién avisarle) | `CLAUDE.md` + `CONTEXT_DB.md` (tabla `push_suscripciones`; **leer sí o sí el porqué del `WHERE` del `ON CONFLICT`**: sin él el detector de backups queda inútil) + `CONTEXT_BACKEND.md` (las dos rutas) + `CONTEXT_AUTH.md` (el logout que limpia) | según capa |
| PWA — push: el CANAL (payload, envío, service worker, `window.Push`) | `CLAUDE.md` + `CONTEXT_PUSH.md` + `CONTEXT_FRONTEND.md` si tocás la tarjeta de Settings o el listener | según capa |
| PWA — push: el MOTOR (cuándo avisar, frenos, horas de silencio, topes) | `CLAUDE.md` + `CONTEXT_PUSH_MOTOR.md` + `CONTEXT_CONFIG.md` si tocás `push_enabled` o las horas + `CONTEXT_DEPLOY.md` si mirás el log. ⚠ **Antes de tocar un freno, leer la frase del encabezado**: un push no se puede desavisar, y de ahí salen todas las decisiones del bloque | según capa |

**Regla**: si la tarea entra en una sola fila, **no leer los demás `CONTEXT_*.md`**. Eso es el ahorro.

**Pantallazo barato del proyecto**: si existen las tools `mcp__codebase-memory-mcp__*`, usar ese grafo de código ANTES de Grep/Glob/Read masivo para ubicar rutas, funciones y llamadores (una consulta = decenas de líneas, no miles de tokens). Cuándo sí, cuándo no y cómo mantenerlo fresco: `docs/METODOLOGIA.md` §3c.

---

## 4. Reglas globales (NO negociables)

1. **Paleta de colores**: todos los colores se referencian con `var(--color-...)`. **Cero hardcode** (`#fff`, `rgb(...)`, nombres de color). Arquitectura:
   - **Valores runtime**: `config.json → paleta_light / paleta_dark` (23 vars c/u). `base.html` los inyecta en `<style>` en el `<head>` como `:root { ... }` y `html[data-theme="dark"] { ... }`.
   - **Fallbacks**: `static/style.css → :root` define los mismos valores por si `config.json` no carga.
   - **Excepciones documentadas** (hardcode intencional): `login.html` (página standalone sin acceso a config); el **favicon** de `base.html` y `login.html` (SVG dentro de un `data:` URI — un data-URI no puede leer `var(--color-...)`; lleva el acento y el blanco a mano, con `%23` en lugar de `#`); los **íconos PNG de la PWA** (`static/img/icon-*.png`, mismo motivo: un binario no lee `var(--color-...)`; se regeneran desde la paleta con `python TempScripts/generar_iconos_pwa.py` si cambia el acento — el `theme_color` del manifest sí sigue la paleta en caliente porque es una ruta); `.dash-toggle-btn.activo { color: #ffffff }` (blanco intencional: mejor contraste que `var(--color-superficie)` en dark mode, 4.47:1 vs 3.27:1); el tema cálido de Lactancia (bloque scoped `body.lac-body`, redefine las mismas vars con su propia paleta); el tema de Rutina (bloque scoped `body.rut-body`) redefine `--color-texto-muted` **derivándolo con `color-mix` de otras vars** — no es hardcode, es contraste sobre tarjetas translúcidas, ver `CONTEXT_FRONTEND.md`; y `--color-rut-p4`..`p8` en el bloque scoped `.rut-wrap, .home-card--rutina` (identificadores de miembro para familias de más de 3 — no son colores de marca, la paleta configurable sigue siendo de 23 vars).
   - Definición y leyenda en página Settings → Paleta.
2. **Verificación**: tras cualquier cambio en dev, ingresar a `http://localhost:5050/` y confirmar que la app no se rompe. El dominio ngrok (`https://miller-unventured-courtly.ngrok-free.dev/`) es SOLO producción — no probar cambios de dev ahí. Cambios de rutas requieren reiniciar `python app.py`. Detalle en `docs/CONTEXT_DEPLOY.md`.
3. **Scripts one-shot** (backfills, migraciones manuales, utilidades) → carpeta `TempScripts/`, nunca en raíz ni en `scripts/`.
4. **Estilo de respuesta** (preferencia del usuario): frases 3-6 palabras, sin filler, sin artículos, español básico.
5. **Higiene de git**: worktree limpio al empezar y al terminar; `git pull` de main SIEMPRE antes de abrir rama; si `origin/main` avanzó, mergearlo en la rama antes de mergear el PR. **Tras mergear, borrar la rama local Y la remota** (regla 2026-07-26) — lo más simple es `gh pr merge <N> --merge --delete-branch`, que hace las dos. **Cualquier rama (local o remota) ya mergeada a main que se encuentre suelta se borra directo, sin preguntar** (regla 2026-08-07: el pruning ya está pre-autorizado por esta misma regla) — **salvo que sea la base de un PR abierto** (regla 2026-08-16): estar mergeada NO alcanza como criterio, hay que mirar antes si algún PR cuelga de ella. Detalle y trampa de los PRs encadenados en `docs/METODOLOGIA.md` §5.
6. **Merge a main SOLO con permiso del usuario** (regla 2026-07-13): los agentes pueden crear ramas, commitear y abrir PRs, pero **NUNCA mergear un PR a main** sin que el usuario lo autorice explícitamente. Flujo: implementar → verificar en DEV → abrir PR → **avisar al usuario y esperar su OK** → recién ahí mergear. La verificación en DEV no reemplaza la aprobación del usuario.
7. **El Inicio no se toca sin pedido explícito** (regla 2026-09-21): la pantalla `/` es una vitrina de módulos y **no scrollea** (está calibrada para un iPhone SE). Ningún agente agrega, mueve ni amplía una tarjeta, barra o sección del Inicio (`templates/index.html`, `static/home.js`, bloque `.home-*` de `style.css`) por iniciativa propia: hace falta que el usuario lo pida o lo confirme. Lo nuevo va **en su módulo** (una lista de tareas es de Rutina, un saldo es de Gastos). Nació de la barra "✓ Tareas de hoy", que un agente metió en el Inicio de prestado y se quitó el 2026-09-21: las tareas viven solo en `/rutina`.

8. **Todo aviso va por el estándar de notificaciones** (regla 2026-09-23): cuando un módulo —cualquiera, nuevo o existente— tenga que avisar algo (un vencimiento, un pendiente, algo que hay que mirar), se hace con un **provider** registrado en `NOTIF_PROVIDERS`, siguiendo `docs/CONTEXT_NOTIFICATIONS.md` §3. **Ningún módulo escribe su propia campana, su propio badge, su propio contador en el nav ni su propio banner de aviso.** Las notificaciones son de **Núcleo**: que hoy los únicos providers sean los de Lactancia es circunstancial, no la arquitectura. Nació del `lac_badge` viejo, que obligaba a tocar el header cada vez que un módulo quería avisar algo. Si un aviso además tiene que sonar en el teléfono, es una decisión aparte y explícita (`PUSH_AVISOS`, ver `docs/CONTEXT_PUSH_MOTOR.md`).

---

## 5. Metodología de actualización de contexto (CRÍTICO)

> **Después de modificar el programa, actualizar el contexto correspondiente.**
> Si no se actualiza, los próximos agentes trabajarán con info obsoleta y romperán cosas.
>
> Detalle completo y tabla exhaustiva: `docs/METODOLOGIA.md`.

Checklist obligatorio post-cambio:

- ¿Modifiqué una **ruta o endpoint** en `app.py`? → actualizar `docs/CONTEXT_BACKEND.md` (sección rutas).
- ¿Modifiqué el **esquema** o agregué una columna en `database.py`? → actualizar `docs/CONTEXT_DB.md` (sección esquema).
- ¿Cambié la **paleta** o agregué variable de color? → actualizar `docs/CONTEXT_FRONTEND.md` (sección paleta) y página Settings.
- ¿Agregué un **archivo nuevo** o moví uno? → actualizar tabla del punto 2 de este `CLAUDE.md`.
- ¿Agregué una **regla nueva** acordada con el usuario? → punto 4 de este `CLAUDE.md` o el `CONTEXT_*.md` del dominio.
- ¿Agregué un **flujo o ruta del frontend**? → actualizar `docs/CONTEXT_FRONTEND.md` (sección templates).
- ¿Agregué dependencia? → actualizar `requirements.txt` y `docs/CONTEXT_DEPLOY.md`.

**Cómo actualizar**: editar el `.md` correspondiente en la sección que ya existe. Mantener cada `CONTEXT_*.md` por debajo de 150 líneas. Si crece más, partir en sub-secciones.

**Auditoría rápida**: `grep -rn "TODO contexto" docs/` debe estar vacío.

---

## 6. Sub-agentes disponibles

Ver `agents/`. Cada agente tiene:
- Lista cerrada de archivos/carpetas que puede leer.
- Misión específica.
- Instrucción de actualizar el `CONTEXT_*.md` que le corresponde al terminar.

Lista actual: `frontend-dev`, `backend-dev`, `db-engineer`, `cotizacion-maintainer`, `auth-maintainer`, `verifier`.

---

## 7. Stack técnico (resumen)

Python 3.13 + Flask + SQLite + Authlib (Google OAuth) + pyngrok + flatpickr (front).
Producción: servicio Windows vía NSSM, expuesto por túnel ngrok con dominio fijo.
