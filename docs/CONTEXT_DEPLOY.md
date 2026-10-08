# Contexto: Deploy y verificación

> Leer con `CLAUDE.md`. NSSM, ngrok, logs, verificación.

## Stack
- **No se compila.** App = `python app.py`; PROD: NSSM envuelve ese mismo comando (sin PyInstaller, instalador ni comandos de servicio en `app.py`).
- **Dependencias**: `requirements.txt`. PROD: `git pull` NO alcanza si cambió la lista → `pip install -r requirements.txt` ANTES de reiniciar; si no, el proceso NO arranca (`ModuleNotFoundError`) y NSSM lo deja caído.
  Última alta: `pywebpush` (2026-09-22, push/VAPID). **La que más arrastra: 11 paquetes**: `aiohttp` y familia (`multidict`, `yarl`, `frozenlist`, `aiosignal`, `propcache`, `aiohappyeyeballs`, `attrs`), `cryptography` (+ `cffi`, `pycparser`), `py-vapid`, `http-ece`. Wheel precompilado Windows + Python 3.13: no compila, pero instalación larga. Reinicio sin `pip install` previo → `ModuleNotFoundError: pywebpush`.
  Anterior: `flask-compress` (2026-09-21, compresión; arrastra `brotli`, `backports.zstd`, wheels Windows + Python 3.13, no compilan).
- **Pisos de seguridad (2026-10)**: `authlib>=1.6.12`, `urllib3>=2.8.0`, `idna>=3.15` corrigen fallas publicadas (comentario en `requirements.txt`). Probado con authlib 1.8.0 / urllib3 2.8.0 / idna 3.20: suite verde, login arma redirección a Google igual. **Al deployar**: `pip install -r requirements.txt` ANTES de reiniciar.
- ⚠ **DEV y PROD comparten MISMO Python** (`C:/Users/elias/AppData/Local/Programs/Python/Python313`, sin venv): `pip install` en DEV cambia lo que PROD usa en su próximo reinicio. Probar versiones sin tocar PROD: venv aparte `python -m venv --system-site-packages <carpeta-fuera-del-repo>` + `pip install` ahí + tests con ese python. Futuro: venv por entorno (ver `docs/CONTEXT_SEGURIDAD.md`).
- **Revisar dependencias con fallas conocidas** (cada tanto, y antes de cada deploy grande): PyPI informa fallas en `https://pypi.org/pypi/<paquete>/<versión>/json` (campo `vulnerabilities`). O `pip-audit` en venv aparte: `pip-audit -r requirements.txt`.
- Servicio Windows: NSSM (`E:\Fondo\nssm.exe`, raíz clon PROD, binario fuera de git; no existe en DEV).
- Túnel público: ngrok, dominio fijo.
- Backups DB: diario vía scheduler interno (`app.py → _scheduler_backup`) + manual desde Settings. Archivos sin fecha en nombre (ej. `gastos_PreGitHub.db`) NO cuentan como backup ni entran en rotación.
- **Hilos de fondo: TRES** (daemon, arrancados en `run_flask()`): `backup-scheduler` (cada hora), `cotizacion-scheduler` (horarios fijos), `push-scheduler` (cada 10 min, **en seco**, ver abajo).
- **Rename 2026-07**: base `gastos.db` → `fondo.db` (ver `docs/CONTEXT_DB.md`). Backups nuevos prefijo `fondo_`; viejos `gastos_` se mantienen para siempre y SIGUEN contando (listado, rotación y fecha-de-backup reconocen ambos; no hace falta migrar).

## Entornos dev / prod
- **Prod**: `E:\Fondo` → servicio `GastosCasa` vía NSSM (arranca solo).
- **Dev**: `E:\FondoDev` → `python app.py` a mano (puerto propio, login bypasseado, NO expuesto a red).

## URLs de verificación (regla 2026-07)
- **DEV** (cambios en `E:\FondoDev`): `http://localhost:5050/` (= `port` en `config.json` de dev). Túnel ngrok NO sirve dev.
- **PROD**: `https://miller-unventured-courtly.ngrok-free.dev/` — SOLO verificar producción. NO probar cambios de dev acá.

**Cómo verificar**: conector `Claude in Chrome` → `tabs_create_mcp` → `navigate` a URL del entorno correcto → screenshot → confirmar app no rota y cambio visible. Dev no responde → pedir al usuario arrancar `python app.py` (cambios de rutas requieren reinicio).

Si pide login: **detenerse y avisar al usuario**. Sesión iniciada normal.

## Servicio Windows
- Nombre: `GastosCasa`.
- Ejecutable: `C:/Users/elias/AppData/Local/Programs/Python/Python313/python.exe`.
- Working dir: carpeta del repo.
- Comandos:
  - Restart: requiere admin. `Start-Process E:\Fondo\nssm.exe -ArgumentList 'restart','GastosCasa' -Verb RunAs`.
  - Status: `E:\Fondo\nssm.exe status GastosCasa` (NO requiere admin).

## Modo desarrollo local
- `python app.py` levanta Flask + scheduler + ngrok según config.
- Cada entorno (DEV / PROD) tiene su `config.json` en la carpeta del clon. NO existe `--config`.
- `config.json` gitignored: DEV y PROD con valores propios, sin interferencia.
- Banner naranja "MODO DESARROLLO" si `app_name` contiene `DEV`.
- **Reiniciar DEV** (cambios de rutas no aplican hasta reiniciar; proceso manual, NO relanza solo): matar el `python.exe` que escucha 5050 (`Get-NetTCPConnection -LocalPort 5050`) y relanzar `python app.py` desde `E:\FondoDev`.
- **Gotcha: server DEV en background (Windows)**: `Start-Process python app.py -WindowStyle Hidden` SIN `-RedirectStandardOutput/-RedirectStandardError` cuelga POST AJAX del navegador para siempre (curl responde normal: buffer stdout sin destino bloquea werkzeug). SIEMPRE redirigir ambos streams a archivo. Además: si carpeta destino de redirects no existe (`logs/` gitignoreada, puede faltar en DEV), `Start-Process` devuelve PID pero python muere al instante sin error → crearla antes y confirmar con request al puerto. Pestaña Chrome con fetches colgados de server matado queda "zombie": usar pestaña nueva.

## ngrok
- Túnel se inicia en `iniciar_ngrok(port, authtoken, domain)` desde `app.py`.
- API local: `http://localhost:4040/api/tunnels` (inspección).
- `ngrok_enabled=False` o falta token → no levanta (solo localhost).

## Backups (de la base de datos)
- Copias de `fondo.db`, NO de código. Gestión: Settings → "Backup de la base de datos".
- Carpeta: campo "Ruta de guardado" (`backup_dir` en `config.json`). Default `backups/` relativo; acepta absolutas. Se aplica sin reiniciar.
- **Solo carpetas de disco local** (2026-10): se rechazan rutas de red (`\\servidor\carpeta`, unidades mapeadas). Con ruta de red, backup diario (base entera) iba a otra máquina y Windows entregaba la credencial de red del servicio. Carpeta OneDrive en disco local (la de PROD) SÍ vale: la sincroniza OneDrive, no la app. Ruta inválida en `config.json` → usa `backups/` + `AVISO:` en log.
- Automático: uno por día (`_scheduler_backup`, chequea cada hora). Primera vuelta al arrancar: cubre días con servicio apagado.
- Solo si cambió algo: antes compara SHA-256 del dump lógico vs `ultimo_backup.json` (junto a backups: archivo, fecha, hash). Sin cambios → NO crea archivo (loguea "Backup omitido hoy" 1 vez/día). Manual desde Settings SIEMPRE crea archivo.
- Manual: campo "Descripción" (opcional) + "Crear backup" → `POST /api/backups/crear` (form `descripcion`). Siempre crea archivo, aunque no haya cambios.
- Restore: elegir en desplegable → `POST /api/backups/restaurar`. Antes guarda `fondo_<fecha>_pre-restore.db` (deshacer posible).
- Formato: `fondo_YYYY-MM-DD_HH-MM[_descripcion].db` (descripción saneada a `[\w-]`, máx 40 chars; se muestra en etiqueta del desplegable). Máximo 10 fechados; los más viejos se borran solos (los descriptos también rotan: para conservar uno para siempre, renombrar sin fecha, ej. `gastos_PreGitHub.db`).
- **Compat backups viejos**: `.db` con prefijo `gastos_` (antes del rename 2026-07) se listan, rotan y reconocen igual que `fondo_` — mismo formato de fecha, mismo desplegable, misma rotación de 10.
- **Importante**: rutas `/git/*` eliminadas. El "restore" anterior revertía código, NO datos.

## Convención de logs
- NSSM redirige salida a `logs/`:
  - `AppStdout` → `logs/` (stdout).
  - `AppStderr` → `logs/` (stderr).
- Rotación NSSM: `AppRotateFiles 1`, `AppRotateOnline 1`, `AppRotateBytes 1048576` (1 MB).
- `logs/` en `.gitignore` (no se versiona). DEV: sin archivo; logs a consola de `python app.py`.
- NO introducir módulo `logging` de Python salvo decisión explícita del usuario: `logutil.log()` simple es la convención.
- En código: `log()` de `logutil.py` (NO `print()` directo). Formato: `AA/MM/DD-HH:MM:SS | OK:/AVISO:/ERROR: mensaje`. Timestamp lo agrega `log()`; mensaje SIN fecha/hora propia. Ej: `26/06/11-14:30:55 | OK: Login exitoso — Elías (...)`.
  **Excepción temporal: `SECO:`**, cuarto prefijo, exclusivo del ensayo en seco del push (ver abajo). Existe para ser grepeable y contable; se retira el día que el push se encienda. NO usarlo para nada más, ni "normalizarlo" a `OK:`. Reemplazo con flag prendido: **`PUSH:`**, quinto prefijo, mismo criterio: token distinto para que conteo del ensayo y de lo mandado de verdad NUNCA se mezclen.
- Arranque: **una sola línea** `OK: App iniciada — ...` (DB, schedulers, puerto, modo). Sin separadores ni texto decorativo.
- Se loguea: login/logout/acceso denegado, backups y restores, refrescos de cotización (incl. el del arranque), fallos de ngrok, modo DEV.
- NO se loguea: URL pública de ngrok, aviso de first_run (el modo va en "App iniciada").
- Decisión 2026-06: evaluado Event Viewer de Windows, descartado — archivos de texto en `logs/` grepeables por agentes IA.

## Cómo se lee el ENSAYO EN SECO del push

⚠ **El ensayo es el estado de HOY, no etapa pasada.** Motor de push conectado al envío y con frenos, pero `push_enabled` sigue en `False` en `config.json` de PROD: hilo `push-scheduler` hace lo de siempre: **NO manda ningún aviso**, escribe en log el push que mandaría. **Prender ese flag termina el ensayo**, y es lo único que falta; código ya está. Qué mirar encendido: al final de esta sección.

Entregable del ensayo = log, se lee con grep:

```powershell
(Select-String -Path E:\Fondo\logs\*.log -Pattern 'SECO: flanco push').Count
```

⚠ Patrón completo, **NO `'SECO:'` a secas**: `Select-String` ignora mayúsculas; `'SECO:'` pelado engancharía "en seco:" y el conteo saldría multiplicado. Por eso ninguna otra línea de este bloque lleva "seco": el token contable es uno solo.

- Formato de línea:
  `SECO: flanco push [lactancia|peligro|Partida vencida] -> titulo="Partida vencida" cuerpo="Lactancia · 3 avisos" url=/lactancia (vigentes ahora: 4)`
  (clave de dedup entre corchetes; después campos con nombre: el `|` ya está ocupado adentro de la clave).
- **Mirar FRECUENCIA**: líneas por día. Un par → el canal se puede encender; diez → agrupar o silenciar antes de que suene un teléfono de verdad. `(vigentes ahora: N)` dice si tres flancos fueron una tanda o tres eventos separados.
- Vueltas sin novedad **NO loguean**. Queda latido de UNA línea por día: `OK: Motor de push (en ensayo): sin flancos nuevos; N aviso(s) vigente(s); providers OK x/y`. Si tampoco aparece, el hilo se murió. Si dice `providers OK 0/2`, el hilo vive pero **ciego**: no es lo mismo que "no pasa nada".
- Al arrancar por primera vez sale línea de siembra (`OK: Motor de push: sin estado previo...`): esa vuelta nunca anuncia. Si aparece **todos los días**, el estado no se guarda: mirar el `AVISO:` que la acompaña y revisar `backup_dir`.
- Lo repetido (provider roto, estado no guardable) sale **1 vez por día**, no 144. Que aparezca ya significa que viene pasando hace rato.
- Ver andar sin esperar días: `python TempScripts/simular_flancos_push.py`. **Seco por construcción** (`_push_enviar` parcheado para reventar): no manda nada ni con el flag prendido.

### Y una vez ENCENDIDO (`push_enabled: true`)

Cambia el token contable: `SECO: flanco push` deja de salir y sale **una línea por aviso**. A propósito: así el conteo del ensayo y el de lo que sonó de verdad nunca se suman.

```powershell
(Select-String -Path E:\Fondo\logs\*.log -Pattern 'PUSH: aviso mandado').Count
```

- Formato:
  `PUSH: aviso mandado [lactancia|peligro|Partida vencida] -> titulo="Partida vencida" cuerpo="Lactancia · 3 avisos" url=/lactancia (entregado en 2 dispositivo(s), 3/8 hoy)`
- ⚠ **`PUSH: aviso SIN ENTREGAR`** es el mismo formato con otro token, y es el que hay que cazar: el aviso salió, quedó marcado como avisado y no entró en ningún dispositivo. Grepear `'PUSH: aviso'` cuenta los dos juntos. Si SIN ENTREGAR se repite, el canal está roto: probar el botón "Mandarme un aviso de prueba" de Settings (es el diagnóstico, NO mira el flag).
- **`N/8 hoy`** = contador diario. Si llega a 8 seguido, la frecuencia es demasiado alta para los topes: el problema NO es el tope, es cuántos flancos hay.
- Los frenos **nunca son silenciosos**, y todo lo que dura horas sale **1 vez por día**. Si falta un aviso esperado, buscar por ese día: `horas de silencio` (quedó para la mañana), `tope de` (quedó para mañana), `esperan el intervalo` (el servicio reinició hace menos de 10 min), `VAPID` (config a medio hacer: NO se marcó, sale cuando se arregle) o `no hay ningún dispositivo suscripto`. Todas nombran **las claves** retenidas.
- ⚠ **`vienen de días anteriores sin poder salir`** es el más difícil de ver solo: un aviso cuya condición es cierta **únicamente** adentro de las horas de silencio NO sale nunca. Pasa, por ejemplo, si el recordatorio nocturno de Lactancia se configura a hora posterior a `push_silencio_desde`. El motor lo detecta y lo dice a partir del segundo día.
- ⚠ **Un aviso retenido NO está en ninguna cola**: se vuelve a evaluar contra lo que pase en ese momento. Si la condición se resolvió durante la noche, ese aviso NO sale nunca, y está bien: el dato sigue en la campana.
- Para volver atrás: `push_enabled: false` en `config.json`. **En caliente**, sin deploy ni reinicio del servicio; la vuelta siguiente (≤ 10 min) ya no manda.

## codebase-memory-mcp (opcional, herramienta local)

Indexa el código en un grafo consultable por agentes IA, con visor web. **NO es dependencia de la app**: FondoDev corre igual sin esto. Instalado por máquina, no viaja en el repo (nada suyo se commitea).

- **Versión: 0.8.1 — NO actualizar.** La 0.9.0 crashea al indexar en Windows 11 (worker muere con log de 0 bytes; [issue #1267](https://github.com/DeusData/codebase-memory-mcp/issues/1267), abierto). Verificado acá: 0.8.1 indexa bien, 0.9.0 no. **NO correr `codebase-memory-mcp update`** hasta que salga 0.9.1+ y se pruebe.
- **Binario**: `%LOCALAPPDATA%\Programs\codebase-memory-mcp\codebase-memory-mcp.exe` (variante UI, 270 MB). Índices en `~/.cache/codebase-memory-mcp/`.
- **Abrir el grafo**: con Claude Code abierto (levanta el MCP server solo), ir a **`http://localhost:9749`**. No choca con el 5050 de la app. Si no responde, el server no corre: arrancarlo con el binario sin argumentos.
- **Sin watcher de archivos**: 0.8.1 no lo trae (feature de la 0.9.0 rota). Decisión 2026-07-26: tarea programada de Windows evaluada y descartada; el índice se refresca a mano (punto siguiente).
- **`auto_index` NO refresca**: solo indexa proyectos que todavía no están indexados (el setting dice "new projects"); uno ya indexado NO se toca. Verificado 2026-09-24: FondoDev seguía en 754 nodos / 45 archivos mientras el repo llegó a 88. (Esta doc decía antes que reindexaba al abrir sesión: era falso.) Un índice viejo responde igual, sin avisar que está viejo.
- **Reindexar a mano = lo corre el agente, no el usuario** (al empezar tarea de código, antes de confiar en el grafo): `codebase-memory-mcp cli index_repository '{"repo_path":"E:/FondoDev"}'` o la tool MCP `index_repository`. Incremental, ~0,5 s. Respeta `.gitignore` (deja afuera `fondo.db`, `backupsdev/`, `logs/`, `__pycache__/`).
- **Cómo lo usan los agentes** (cuándo sí, cuándo no, qué tool): `docs/METODOLOGIA.md` §3c.
- **Desinstalar**: `codebase-memory-mcp uninstall -y`. Ojo: deja colgados el binario, `~/.cache/codebase-memory-mcp/`, `~/.profile` y los scripts `~/.claude/hooks/cbm-*`: borrarlos a mano.

## Reglas específicas
1. **Verificación obligatoria** post-cambio en la URL del entorno correcto (ver "URLs de verificación": dev → `http://localhost:5050/`, prod → ngrok), salvo que el usuario diga lo contrario.
2. **Restart del servicio** = operación con permisos elevados. Confirmar con usuario antes.
3. **Backups antes de migrar datos** (manual desde Settings con descripción; NO confiar solo en el automático diario).
4. **NO commitear** `build/dist/`, `*.exe`, `fondo.db` (ni el legacy `gastos.db`), `backups/`.

## Al modificar este dominio, actualizar:
- URL pública si cambia el dominio ngrok.
- Comandos del servicio si cambia el nombre o el path de Python.
