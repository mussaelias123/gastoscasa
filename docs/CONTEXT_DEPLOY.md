# Contexto: Deploy y verificación

> Leer junto con `CLAUDE.md`. Para servicio Windows (NSSM), ngrok, logs, verificación.

## Stack
- **No se compila.** La app corre como `python app.py`; en producción NSSM
  envuelve ese mismo comando (no hay PyInstaller, instalador ni comandos de
  servicio propios en `app.py`).
- Servicio Windows: NSSM (`E:\Fondo\nssm.exe`, raíz del clon PROD, binario fuera de git; no existe en DEV).
- Túnel público: ngrok con dominio fijo.
- Backups DB: diario via scheduler interno (`app.py → _scheduler_backup`) + manual desde Settings. Archivos sin fecha en el nombre (ej. `gastos_PreGitHub.db`) no cuentan como backup ni entran en la rotación.
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
- Rotación activada en NSSM: `AppRotateFiles 1`, `AppRotateBytes 1048576` (1 MB).
- `logs/` está en `.gitignore` (no se versiona).
- En código se loguea con `log()` de `logutil.py` (NO `print()` directo). Formato de línea:
  `AA/MM/DD-HH:MM:SS | OK:/AVISO:/ERROR: mensaje` — el timestamp lo agrega `log()`,
  el mensaje no debe traer fecha/hora propia. Ej: `26/06/11-14:30:55 | OK: Login exitoso — Elías (...)`.
- Arranque: **una sola línea** `OK: App iniciada — ...` (DB, schedulers, puerto, modo). Sin separadores ni texto decorativo en la salida.
- Se loguea: login/logout/acceso denegado, backups y restores, refrescos de cotización (incluido el del arranque), fallos de ngrok, modo DEV.
- NO se loguea: URL pública de ngrok, aviso de first_run (el modo va dentro de la línea "App iniciada").
- Decisión 2026-06: se evaluó migrar a Event Viewer de Windows y se descartó — los archivos de texto en `logs/` son directamente grepeables por agentes IA.

## Reglas específicas
1. **Verificación obligatoria** post-cambio en la URL del entorno correcto (ver "URLs de verificación": dev → `http://localhost:5050/`, prod → ngrok), salvo que el usuario diga lo contrario.
2. **Restart del servicio** es operación con permisos elevados. Confirmar con usuario antes.
3. **Backups antes de migrar datos** (manual desde Settings con descripción, no confiar solo en el automático diario).
4. **No commitear** `build/dist/`, `*.exe`, `fondo.db` (ni el legacy `gastos.db`), `backups/`.

## Al modificar este dominio, actualizar:
- URL pública si cambia el dominio ngrok.
- Comandos del servicio si cambia el nombre o el path de Python.
