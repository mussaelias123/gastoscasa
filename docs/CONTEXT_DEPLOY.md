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
- `python app.py --config config.dev.json` para entorno paralelo.
- Banner naranja "MODO DESARROLLO" si `app_name` contiene `DEV`.

## ngrok
- Túnel se inicia en `iniciar_ngrok(port, authtoken, domain)` desde `app.py`.
- API local de ngrok: `http://localhost:4040/api/tunnels` (útil para inspección).
- Si `ngrok_enabled=False` o falta token → no se levanta (solo localhost).

## Backups
- Cada hora en `backups/gastos_YYYY-MM-DD_HH-MM.db`.
- Limpieza automática de antiguos.
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
