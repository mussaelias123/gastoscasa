# Contexto: Deploy y verificación

> Leer junto con `CLAUDE.md`. Para servicio Windows (NSSM), ngrok, logs, verificación.

## Stack
- **No se compila.** La app corre como `python app.py`; en producción NSSM
  envuelve ese mismo comando (no hay PyInstaller, instalador ni comandos de
  servicio propios en `app.py`).
- Servicio Windows: NSSM (`build/nssm/nssm.exe`, binario fuera de git).
- Túnel público: ngrok con dominio fijo.
- Backups DB: semanal (jueves) via scheduler interno (`app.py → _scheduler_backup`) + manual desde Settings.

## Entornos dev / prod
- **Prod**: `E:\Fondo` → servicio Windows `GastosCasa` vía NSSM (arranca solo).
- **Dev**: `E:\FondoDev` → `python app.py` a mano (puerto propio, login bypasseado,
  no se expone a la red).

## URL pública (verificación)
```
https://miller-unventured-courtly.ngrok-free.dev/
```

**Cómo verificar**: usar conector `Claude in Chrome` → `tabs_create_mcp` → `navigate` a la URL → tomar screenshot → confirmar que la app no está rota y que el cambio aplicado es visible.

Si la página pide login: **detenerse y avisar al usuario**. La sesión está iniciada normalmente.

## Servicio Windows
- Nombre: `GastosCasa`.
- Ejecutable apuntado a: `C:/Users/elias/AppData/Local/Programs/Python/Python313/python.exe`.
- Working dir: carpeta del repo.
- Comandos:
  - Restart: requiere admin. Vía `powershell Start-Process ... -Verb RunAs`.
  - Status: `build/nssm/nssm.exe status GastosCasa`.

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
- Son copias de `gastos.db`, NO de código. Gestionados desde Settings → "Backup de la base de datos".
- Carpeta configurable: campo "Ruta de guardado" (`backup_dir` en `config.json`). Default `backups/` relativo; acepta rutas absolutas. Se aplica sin reiniciar.
- Automático: todos los jueves (scheduler interno `_scheduler_backup`). Si estuvo apagado >7 días, corre al arrancar.
- Manual: botón "Crear backup" → `POST /api/backups/crear`.
- Restore: elegir backup en el desplegable → `POST /api/backups/restaurar`. Antes guarda `gastos_<fecha>_pre-restore.db` (deshacer posible).
- Formato: `gastos_YYYY-MM-DD_HH-MM.db`. Máximo 10 archivos; los más viejos se borran solos.
- **Importante**: las viejas rutas `/git/*` se eliminaron. El "restore" anterior revertía código, no datos.

## Convención de logs
- NSSM redirige la salida del proceso a `logs/`:
  - `AppStdout` → `logs/` (stdout).
  - `AppStderr` → `logs/` (stderr).
- Rotación activada en NSSM: `AppRotateFiles 1`, `AppRotateBytes 1048576` (1 MB).
- `logs/` está en `.gitignore` (no se versiona).
- En código se loguea con `print()` usando prefijos: `OK:` / `AVISO:` / `ERROR:`.
- Arranque: **una sola línea** `OK: App iniciada — ...` (DB, schedulers, puerto, modo). Sin separadores ni texto decorativo en la salida.
- Se loguea: login/logout/acceso denegado, backups y restores, refrescos de cotización (incluido el del arranque), fallos de ngrok, modo DEV.
- NO se loguea: URL pública de ngrok, aviso de first_run (el modo va dentro de la línea "App iniciada").
- Decisión 2026-06: se evaluó migrar a Event Viewer de Windows y se descartó — los archivos de texto en `logs/` son directamente grepeables por agentes IA.

## Reglas específicas
1. **Verificación obligatoria** post-cambio en ngrok URL (no localhost), salvo que el usuario diga lo contrario.
2. **Restart del servicio** es operación con permisos elevados. Confirmar con usuario antes.
3. **Backups antes de migrar datos** (manual desde Settings, no confiar solo en el automático semanal).
4. **No commitear** `build/dist/`, `*.exe`, `gastos.db`, `backups/`.

## Al modificar este dominio, actualizar:
- URL pública si cambia el dominio ngrok.
- Comandos del servicio si cambia el nombre o el path de Python.
