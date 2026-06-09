# Contexto: Deploy y verificación

> Leer junto con `CLAUDE.md`. Para build, servicio Windows, ngrok, verificación.

## Stack
- Servicio Windows: NSSM (`build/nssm/nssm.exe`).
- Túnel público: ngrok con dominio fijo.
- Empaquetado opcional: PyInstaller (`build/gastos-casa.spec`) + Inno Setup (`build/setup_installer.iss`).
- Backups DB: hourly via scheduler interno (`app.py → _scheduler_backup`).

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

## Backups
- Carpeta configurable desde Settings → campo "Carpeta de backups" (`backup_dir` en `config.json`).
- Default: `backups/` relativo a la raíz del proyecto. Acepta rutas absolutas.
- Horario: todos los jueves (scheduler interno). Se aplica el cambio de carpeta sin reiniciar.
- Formato: `gastos_YYYY-MM-DD_HH-MM.db`. Máximo 10 archivos; los más viejos se borran.
- Backup pre-evento: `gastos_pre_<motivo>_<timestamp>.db` → manual antes de migración.

## Build (rara vez se toca)
- `build/build.bat` → ejecuta PyInstaller con `gastos-casa.spec`.
- `build/setup_installer.iss` → instalador Windows.
- `build/download_nssm.ps1` → traer NSSM si falta.
- `build/README-BUILD.md` → instrucciones detalladas.

## Reglas específicas
1. **Verificación obligatoria** post-cambio en ngrok URL (no localhost), salvo que el usuario diga lo contrario.
2. **Restart del servicio** es operación con permisos elevados. Confirmar con usuario antes.
3. **Backups antes de migrar datos** (manual, no confiar solo en hourly).
4. **No commitear** `build/dist/`, `*.exe`, `gastos.db`, `backups/`.

## Al modificar este dominio, actualizar:
- URL pública si cambia el dominio ngrok.
- Comandos del servicio si cambia el nombre o el path de Python.
