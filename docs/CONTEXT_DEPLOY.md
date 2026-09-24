# Contexto: Deploy y verificación

> Leer junto con `CLAUDE.md`. Para servicio Windows (NSSM), ngrok, logs, verificación.

## Stack
- **No se compila.** La app corre como `python app.py`; en producción NSSM
  envuelve ese mismo comando (no hay PyInstaller, instalador ni comandos de
  servicio propios en `app.py`).
- **Dependencias**: `requirements.txt`. Al actualizar PROD no alcanza con
  `git pull` si cambió esa lista — hay que correr también
  `pip install -r requirements.txt` ANTES de reiniciar el servicio, o el
  proceso no arranca (`ModuleNotFoundError`) y NSSM lo deja caído.
  Última alta: `pywebpush` (2026-09-22, notificaciones push / VAPID). **Es la
  que más arrastra hasta hoy: 11 paquetes** — `aiohttp` y su familia
  (`multidict`, `yarl`, `frozenlist`, `aiosignal`, `propcache`,
  `aiohappyeyeballs`, `attrs`), `cryptography` (+ `cffi`, `pycparser`),
  `py-vapid` y `http-ece`. Todos con wheel precompilado para Windows +
  Python 3.13: no compila nada, pero es una instalación larga. Si se reinicia
  el servicio sin correr el `pip install` primero, NSSM lo deja caído con
  `ModuleNotFoundError: pywebpush`.
  Anterior: `flask-compress` (2026-09-21, compresión de respuestas; arrastra
  `brotli` y `backports.zstd`, los dos con wheel precompilado para Windows +
  Python 3.13, no compilan nada).
- Servicio Windows: NSSM (`E:\Fondo\nssm.exe`, raíz del clon PROD, binario fuera de git; no existe en DEV).
- Túnel público: ngrok con dominio fijo.
- Backups DB: diario via scheduler interno (`app.py → _scheduler_backup`) + manual desde Settings. Archivos sin fecha en el nombre (ej. `gastos_PreGitHub.db`) no cuentan como backup ni entran en la rotación.
- **Hilos de fondo: son TRES** (todos daemon, arrancados en `run_flask()`): `backup-scheduler` (cada hora), `cotizacion-scheduler` (horarios fijos) y `push-scheduler` (cada 10 min, **en seco** — ver abajo).
- **Rename 2026-07**: la base pasó de `gastos.db` a `fondo.db` (ver `docs/CONTEXT_DB.md`). Los backups nuevos usan prefijo `fondo_`; los viejos con prefijo `gastos_` se mantienen para siempre y siguen contando (listado, rotación y fecha-de-backup reconocen ambos prefijos — no hace falta migrarlos).

## Entornos dev / prod
- **Prod**: `E:\Fondo` → servicio Windows `GastosCasa` vía NSSM (arranca solo).
- **Dev**: `E:\FondoDev` → `python app.py` a mano (puerto propio, login bypasseado,
  no se expone a la red).

## URLs de verificación (regla 2026-07)
- **DEV** (cambios en `E:\FondoDev`): `http://localhost:5050/` (puerto = `port` en `config.json` de dev). El túnel ngrok NO sirve dev.
- **PROD**: `https://miller-unventured-courtly.ngrok-free.dev/` — SOLO para verificar producción. No probar cambios de dev acá.

**Cómo verificar**: usar conector `Claude in Chrome` → `tabs_create_mcp` → `navigate` a la URL del entorno correcto → tomar screenshot → confirmar que la app no está rota y que el cambio aplicado es visible. Si dev no responde, pedir al usuario que arranque `python app.py` (los cambios de rutas requieren reinicio del proceso).

Si la página pide login: **detenerse y avisar al usuario**. La sesión está iniciada normalmente.

## Servicio Windows
- Nombre: `GastosCasa`.
- Ejecutable apuntado a: `C:/Users/elias/AppData/Local/Programs/Python/Python313/python.exe`.
- Working dir: carpeta del repo.
- Comandos:
  - Restart: requiere admin. Vía `Start-Process E:\Fondo\nssm.exe -ArgumentList 'restart','GastosCasa' -Verb RunAs`.
  - Status: `E:\Fondo\nssm.exe status GastosCasa` (no requiere admin).

## Modo desarrollo local
- `python app.py` levanta Flask + scheduler + ngrok según config.
- Cada entorno (DEV / PROD) tiene su propio `config.json` en la carpeta del clon. No existe `--config`.
- `config.json` está gitignored: DEV y PROD usan sus propios valores sin interferencia.
- Banner naranja "MODO DESARROLLO" si `app_name` contiene `DEV`.
- **Reiniciar DEV** (los cambios de rutas no aplican hasta reiniciar; al ser proceso manual, no se relanza solo): matar el `python.exe` que escucha el puerto 5050 (`Get-NetTCPConnection -LocalPort 5050`) y relanzar `python app.py` desde `E:\FondoDev`.
- **Gotcha — server DEV en background (Windows)**: lanzarlo detached (`Start-Process python app.py -WindowStyle Hidden`) SIN `-RedirectStandardOutput/-RedirectStandardError` cuelga los POST AJAX del navegador para siempre (curl responde normal — el buffer de stdout sin destino bloquea werkzeug). SIEMPRE redirigir ambos streams a archivo. Además: si la carpeta destino de los redirects no existe (`logs/` está gitignoreada y en DEV puede faltar), `Start-Process` devuelve PID pero python muere al instante sin error — crearla antes y confirmar con un request al puerto. Una pestaña de Chrome con fetches colgados de un server matado queda "zombie": usar pestaña nueva.

## ngrok
- Túnel se inicia en `iniciar_ngrok(port, authtoken, domain)` desde `app.py`.
- API local de ngrok: `http://localhost:4040/api/tunnels` (útil para inspección).
- Si `ngrok_enabled=False` o falta token → no se levanta (solo localhost).

## Backups (de la base de datos)
- Son copias de `fondo.db`, NO de código. Gestionados desde Settings → "Backup de la base de datos".
- Carpeta configurable: campo "Ruta de guardado" (`backup_dir` en `config.json`). Default `backups/` relativo; acepta rutas absolutas. Se aplica sin reiniciar.
- Automático: uno por día (scheduler interno `_scheduler_backup`, chequea cada hora). La primera vuelta corre al arrancar, cubre días con el servicio apagado.
- Solo si cambió algo: antes de backupear compara SHA-256 del dump lógico contra `ultimo_backup.json` (vive junto a los backups: archivo, fecha, hash). Sin cambios → no crea archivo (loguea "Backup omitido hoy" 1 vez/día). El backup manual desde Settings siempre crea archivo.
- Manual: campo "Descripción" (opcional) + botón "Crear backup" → `POST /api/backups/crear` (form `descripcion`). Siempre crea archivo, aunque no haya cambios.
- Restore: elegir backup en el desplegable → `POST /api/backups/restaurar`. Antes guarda `fondo_<fecha>_pre-restore.db` (deshacer posible).
- Formato: `fondo_YYYY-MM-DD_HH-MM[_descripcion].db` (descripción saneada a `[\w-]`, máx 40 chars; se muestra en la etiqueta del desplegable). Máximo 10 archivos fechados; los más viejos se borran solos (los descriptos también rotan: para conservar uno para siempre, renombrarlo sin fecha, ej. `gastos_PreGitHub.db`).
- **Compat backups viejos**: los `.db` con prefijo `gastos_` (de antes del rename 2026-07) se listan, rotan y reconocen exactamente igual que los nuevos `fondo_` — mismo formato de fecha, mismo desplegable, misma rotación de a 10.
- **Importante**: las viejas rutas `/git/*` se eliminaron. El "restore" anterior revertía código, no datos.

## Convención de logs
- NSSM redirige la salida del proceso a `logs/`:
  - `AppStdout` → `logs/` (stdout).
  - `AppStderr` → `logs/` (stderr).
- Rotación activada en NSSM: `AppRotateFiles 1`, `AppRotateOnline 1`, `AppRotateBytes 1048576` (1 MB).
- `logs/` está en `.gitignore` (no se versiona). En DEV no hay archivo: los logs van a la consola del `python app.py`.
- NO introducir el módulo `logging` de Python salvo decisión explícita del usuario — `logutil.log()` simple es la convención.
- En código se loguea con `log()` de `logutil.py` (NO `print()` directo). Formato de línea:
  `AA/MM/DD-HH:MM:SS | OK:/AVISO:/ERROR: mensaje` — el timestamp lo agrega `log()`,
  el mensaje no debe traer fecha/hora propia. Ej: `26/06/11-14:30:55 | OK: Login exitoso — Elías (...)`.
  **Excepción temporal: `SECO:`**, cuarto prefijo, exclusivo del ensayo en seco del
  push (ver abajo). Existe para ser grepeable y contable; se retira el día que el
  push se encienda. No usarlo para nada más, ni "normalizarlo" a `OK:`. Su
  reemplazo con el flag prendido es **`PUSH:`**, quinto prefijo y mismo criterio:
  token distinto justamente para que el conteo del ensayo y el de lo mandado de
  verdad nunca se mezclen.
- Arranque: **una sola línea** `OK: App iniciada — ...` (DB, schedulers, puerto, modo). Sin separadores ni texto decorativo en la salida.
- Se loguea: login/logout/acceso denegado, backups y restores, refrescos de cotización (incluido el del arranque), fallos de ngrok, modo DEV.
- NO se loguea: URL pública de ngrok, aviso de first_run (el modo va dentro de la línea "App iniciada").
- Decisión 2026-06: se evaluó migrar a Event Viewer de Windows y se descartó — los archivos de texto en `logs/` son directamente grepeables por agentes IA.

## Cómo se lee el ENSAYO EN SECO del push

⚠ **El ensayo es el estado de HOY, no una etapa que ya pasó.** El motor de push
ya está conectado al envío y tiene sus frenos, pero `push_enabled` sigue en
`False` en el `config.json` de PROD, así que el hilo `push-scheduler` hace
exactamente lo de siempre: **no manda ningún aviso**, escribe en el log el push
que mandaría. **Prender ese flag es lo que termina el ensayo** — y es lo único
que falta; el código ya está. Qué mirar una vez encendido, al final de esta
sección.

El entregable del ensayo es justamente el log, y se lee con un grep:

```powershell
(Select-String -Path E:\Fondo\logs\*.log -Pattern 'SECO: flanco push').Count
```

⚠ El patrón va completo, **no `'SECO:'` a secas**. `Select-String` ignora
mayúsculas, así que un `'SECO:'` pelado engancharía cualquier línea que diga "en
seco:" y el conteo saldría multiplicado. Por eso ninguna otra línea de este
bloque lleva la palabra "seco": el token contable es uno solo.

- Formato de la línea:
  `SECO: flanco push [lactancia|peligro|Partida vencida] -> titulo="Partida vencida" cuerpo="Lactancia · 3 avisos" url=/lactancia (vigentes ahora: 4)`
  (clave de dedup entre corchetes; después campos con nombre — el `|` ya está
  ocupado adentro de la clave).
- **Lo que hay que mirar es la FRECUENCIA**: cuántas líneas por día. Si son un
  par, el canal se puede encender; si son diez, hay que agrupar o silenciar
  antes de que suene un teléfono de verdad. `(vigentes ahora: N)` dice si tres
  flancos fueron una tanda o tres eventos separados.
- Las vueltas sin novedad **no loguean**. Queda un latido de UNA línea por día:
  `OK: Motor de push (en ensayo): sin flancos nuevos; N aviso(s) vigente(s); providers OK x/y`.
  Si eso tampoco aparece, el hilo se murió. Si dice `providers OK 0/2`, el hilo
  está vivo pero **ciego** — que no es lo mismo que "no pasa nada".
- Al arrancar por primera vez sale una línea de siembra
  (`OK: Motor de push: sin estado previo...`): esa vuelta nunca anuncia nada. Si
  esa línea aparece **todos los días**, el estado no se está guardando: mirar el
  `AVISO:` que la acompaña y revisar `backup_dir`.
- Todo lo que se repite (provider roto, estado que no se puede guardar) sale
  **1 vez por día**, no 144. Que una de esas líneas aparezca ya significa que
  viene pasando hace rato.
- Para verlo andar sin esperar días: `python TempScripts/simular_flancos_push.py`.
  Es **seco por construcción** (tiene `_push_enviar` parcheado para reventar),
  así que no manda nada ni con el flag prendido.

### Y una vez ENCENDIDO (`push_enabled: true`)

Cambia el token contable: `SECO: flanco push` deja de salir y en su lugar sale
**una línea por aviso**. Es a propósito — así el conteo del ensayo y el de lo
que sonó de verdad nunca se suman entre sí.

```powershell
(Select-String -Path E:\Fondo\logs\*.log -Pattern 'PUSH: aviso mandado').Count
```

- Formato:
  `PUSH: aviso mandado [lactancia|peligro|Partida vencida] -> titulo="Partida vencida" cuerpo="Lactancia · 3 avisos" url=/lactancia (entregado en 2 dispositivo(s), 3/8 hoy)`
- ⚠ **`PUSH: aviso SIN ENTREGAR`** es el mismo formato con otro token, y es el
  que hay que cazar: el aviso salió, quedó marcado como avisado y no entró en
  ningún dispositivo. Grepear `'PUSH: aviso'` cuenta los dos juntos. Si SIN
  ENTREGAR se repite, el canal está roto — probar el botón "Mandarme un aviso
  de prueba" de Settings, que es el diagnóstico y no mira el flag.
- **`N/8 hoy`** es el contador diario. Si llega a 8 seguido, la frecuencia es
  demasiado alta para los topes de hoy: el problema no es el tope, es cuántos
  flancos hay.
- Los frenos **nunca son silenciosos**, y todo lo que dura horas sale **1 vez
  por día**. Si falta un aviso que se esperaba, buscar por ese día:
  `horas de silencio` (quedó para la mañana), `tope de` (quedó para mañana),
  `esperan el intervalo` (el servicio reinició hace menos de 10 min), `VAPID`
  (config a medio hacer: NO se marcó, sale cuando se arregle) o `no hay ningún
  dispositivo suscripto`. Todas nombran **las claves** retenidas.
- ⚠ **`vienen de días anteriores sin poder salir`** es el más difícil de ver
  solo: un aviso cuya condición es cierta **únicamente** adentro de las horas de
  silencio no sale NUNCA. Pasa, por ejemplo, si el recordatorio nocturno de
  Lactancia se configura a una hora posterior a `push_silencio_desde`. El motor
  lo detecta y lo dice a partir del segundo día.
- ⚠ **Un aviso retenido NO está en ninguna cola**: se vuelve a evaluar contra lo
  que pase en ese momento. Si la condición se resolvió durante la noche, ese
  aviso no sale nunca — y está bien. El dato sigue en la campana.
- Para volver atrás: `push_enabled: false` en `config.json`. **En caliente**, sin
  deploy y sin reiniciar el servicio; la vuelta siguiente (≤ 10 min) ya no manda.

## codebase-memory-mcp (opcional, herramienta local)

Indexa el código en un grafo consultable por agentes IA, con visor web. **No es
dependencia de la app**: FondoDev corre igual sin esto. Instalado por máquina,
no viaja en el repo (nada suyo se commitea).

- **Versión: 0.8.1 — NO actualizar.** La 0.9.0 crashea al indexar en Windows 11
  (worker muere con log de 0 bytes; [issue #1267](https://github.com/DeusData/codebase-memory-mcp/issues/1267),
  abierto). Verificado acá: 0.8.1 indexa bien, 0.9.0 no. **No correr
  `codebase-memory-mcp update`** hasta que salga 0.9.1+ y se pruebe.
- **Binario**: `%LOCALAPPDATA%\Programs\codebase-memory-mcp\codebase-memory-mcp.exe`
  (variante UI, 270 MB). Índices en `~/.cache/codebase-memory-mcp/`.
- **Abrir el grafo**: con Claude Code abierto (levanta el MCP server solo), ir a
  **`http://localhost:9749`**. No choca con el 5050 de la app. Si no responde,
  el server no está corriendo: arrancarlo con el binario sin argumentos.
- **Sin watcher de archivos**: 0.8.1 no lo trae (es feature de la 0.9.0 rota).
  Decisión 2026-07-26: se evaluó una tarea programada de Windows y se descartó
  — el índice se refresca a mano (punto siguiente).
- **`auto_index` NO refresca**: solo indexa proyectos que todavía no están
  indexados (el setting dice "new projects"); uno ya indexado no se toca.
  Verificado 2026-09-24: FondoDev seguía en 754 nodos / 45 archivos mientras el
  repo llegó a 88. (Esta doc decía antes que reindexaba al abrir sesión: era
  falso.) Un índice viejo responde igual, sin avisar que está viejo.
- **Reindexar a mano = lo corre el agente, no el usuario** (al empezar una tarea
  de código, antes de confiar en el grafo): `codebase-memory-mcp cli index_repository '{"repo_path":"E:/FondoDev"}'`
  o la tool MCP `index_repository`. Incremental, ~0,5 s. Respeta `.gitignore`
  (deja afuera `fondo.db`, `backupsdev/`, `logs/`, `__pycache__/`).
- **Cómo lo usan los agentes** (cuándo sí, cuándo no, qué tool): `docs/METODOLOGIA.md` §3c.
- **Desinstalar**: `codebase-memory-mcp uninstall -y`. Ojo: deja colgados el
  binario, `~/.cache/codebase-memory-mcp/`, `~/.profile` y los scripts
  `~/.claude/hooks/cbm-*` — borrarlos a mano.

## Reglas específicas
1. **Verificación obligatoria** post-cambio en la URL del entorno correcto (ver "URLs de verificación": dev → `http://localhost:5050/`, prod → ngrok), salvo que el usuario diga lo contrario.
2. **Restart del servicio** es operación con permisos elevados. Confirmar con usuario antes.
3. **Backups antes de migrar datos** (manual desde Settings con descripción, no confiar solo en el automático diario).
4. **No commitear** `build/dist/`, `*.exe`, `fondo.db` (ni el legacy `gastos.db`), `backups/`.

## Al modificar este dominio, actualizar:
- URL pública si cambia el dominio ngrok.
- Comandos del servicio si cambia el nombre o el path de Python.
