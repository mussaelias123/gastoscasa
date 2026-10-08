# Contexto: Seguridad (modelo, reglas, mantenimiento)

> Leer con `CLAUDE.md` ante CUALQUIER cambio en: login/sesión, `config.json`, datos de un form, HTML armado con datos, scripts inline, librerías de terceros, cabeceras, backups, despliegue.
> Origen: auditoría integral 2026-10, rama `seguridad/endurecimiento-integral`.

## Qué se protege, de quién
- App expuesta a internet (túnel ngrok). Protege: datos (saldos, movimientos, lactancia, rutina), cuenta **Personal** de cada uno frente al otro, PC que la sirve.
- Atacantes: cualquiera en internet (sin sesión), sesión robada, web maliciosa en navegador logueado, librería de terceros comprometida, programa malicioso en la PC.

## Reglas (no negociables)
1. **No hay app web sin login.** Sin credenciales Google o `config.json` ilegible → falla CERRADA (`auth.py → require_login`). Nada nuevo "deja pasar" ante la duda. Puesta en marcha: solo `config.json` + reinicio. Ver `CONTEXT_AUTH.md`.
2. **`config.json` se escribe SOLO con `config.guardar_config`** (candado + temporal + `os.replace`; nunca pisa archivo ilegible). Prohibido `open('config.json','w')`. Ver `CONTEXT_CONFIG.md`.
3. **Entrada validada en servidor:** enumerados por lista blanca, números finitos con rango, fechas reales, largos máx. `ValueError` → 400 ANTES de escribir. Front valida por comodidad; servidor, por seguridad.
4. **Salida escapada:** Jinja escapa solo. Datos → `<script>` con `| tojson` (NUNCA `json.dumps(...)` + `| safe`: no escapa `</script>`). JS: todo dato → `innerHTML` pasa por `escHtml()` (app.js) o `esc()` del módulo; o `createElement` + `textContent`.
5. **Política CSP estricta:** todo `<script>` inline lleva `nonce="{{ csp_nonce }}"`. Prohibidos `onclick=`, todo `on*=` inline (también en HTML armado en JS), `javascript:`, `eval`, `new Function`. Eventos → `addEventListener` / `data-accion`. ⚠ Romperlo = navegador bloquea EN SILENCIO (solo error en consola). Ver `CONTEXT_BACKEND.md` (cabeceras) y `CONTEXT_FRONTEND.md` (regla 11).
6. **Librerías de terceros solo locales:** `static/vendor/<lib>-<versión>/` + huella en `tests/test_vendor_integridad.py`. Nunca CDN: paquete npm envenenado → código ajeno con saldos a la vista.
7. **Backups solo en disco local** (`_validar_backup_dir`). Ruta de red → base entera a otra máquina + credencial de red del servicio (LocalSystem). Ver `CONTEXT_BACKEND.md`.
8. **Cotización:** se rechaza 0, inválida, sin conexión, salto > ±50%; valor anterior queda. Devaluación REAL > 50% → destrabar a mano: editar `cotizacion_valor` en `config.json`. Ver `CONTEXT_COTIZACION.md` § "Blindaje del dato".
9. **POST solo desde la propia app** (`Origin`/`Referer` vs `request.host`) + cookie `SameSite=Lax`. ⚠ NO poner `Referrer-Policy: no-referrer` global: algunos navegadores mandan `Origin: null` → se rechazarían forms propios. Ver `CONTEXT_AUTH.md`.
10. **Secretos:** nunca al HTML (`config.sin_secretos`) ni al log. Clave secreta nueva → nombre con `secret` / `token` / `password`.
11. **Aviso push nunca lleva montos**; solo a servicios de push conocidos. Ver `CONTEXT_PUSH.md`.

## Mapa defensa → dónde → test
| Defensa | Dónde | Test |
|---|---|---|
| Login cerrado (sin credenciales / config ilegible) | `auth.py` | `test_auth_cerrado.py` |
| Escritura atómica de config | `config.py` | `test_config_seguro.py` |
| Origen de POST, DEV solo local (4 cerrojos), email verificado, cookie `Secure` | `auth.py` | `test_auth_endurecido.py` |
| Validación de movimientos, `tojson` en gastos fijos | `app.py` | `test_validacion_movimientos.py` |
| Carpeta de backups local | `app.py` | `test_backup_dir.py` |
| Cabeceras + CSP con nonce + tope 1 MB | `app.py` | `test_cabeceras_seguridad.py` |
| Scripts inline con nonce, sin `on*=` | `templates/`, `static/*.js` | `test_csp_templates.py` |
| Librerías locales con huella, sin CDN | `static/vendor/` | `test_vendor_integridad.py` |
| Cotización con controles | `cotizacion.py` | `test_cotizacion.py` |
| Secretos fuera del HTML | `config.py`, `app.py` | `test_cfg_secretos.py` |
| Push: destinos y contenido | `app.py`, `templates/sw.js` | `test_push_*.py`, `test_sw.py` |

## Actualizar una librería de terceros
1. Versión exacta. Bajar de `https://cdn.jsdelivr.net/npm/<paquete>@<versión>/...` y de `https://unpkg.com/<paquete>@<versión>/...`; comparar huellas (`openssl dgst -sha256 -binary <archivo> | openssl base64`) entre sí y con `https://data.jsdelivr.com/v1/packages/npm/<paquete>@<versión>?structure=flat`.
2. Carpeta NUEVA `static/vendor/<lib>-<versión>/` (+ LICENSE). Nunca pisar la vieja.
3. Huellas → `HUELLAS` de `tests/test_vendor_integridad.py`.
4. Rutas en templates; borrar carpeta vieja + sus huellas.
5. DEV: consola sin errores de CSP + suite verde.
- `.gitattributes` (`static/vendor/** -text`): git no toca fines de línea. Sin eso, `autocrlf` cambia bytes → huella no coincide.

## Pendientes FUERA del código (quien administra la PC)
Por impacto. Ninguno urgente con lo de arriba aplicado; cierran lo que el código no puede.
1. **Verificación en 2 pasos:** 2 cuentas Google (el login ES Google) + cuenta Microsoft (backups en OneDrive).
2. **Permisos de `E:\Fondo`:** hoy "Usuarios autenticados" puede MODIFICAR (código, `config.json` con secretos, `fondo.db`) → cualquier programa, con cualquier usuario, cambia `app.py` (corre como LocalSystem). PowerShell como admin (SIDs → anda en cualquier idioma): `icacls E:\Fondo /inheritance:d` → `icacls E:\Fondo /remove:g *S-1-5-11` (Usuarios autenticados) → `icacls E:\Fondo /remove:g *S-1-5-32-545` (Usuarios) → `icacls E:\Fondo /grant "<tu-usuario>:(OI)(CI)F"`. Ídem `E:\FondoDev`.
3. **Servicio sin LocalSystem** (más trabajo; probar con calma): usuario local sin privilegios; Modificar sobre `E:\Fondo` + carpeta de backups; Lectura/Ejecución sobre Python (hoy en perfil de elias → conviene Python "para todos los usuarios"); `nssm set GastosCasa ObjectName .\<usuario> <clave>`. ⚠ pyngrok guarda ngrok en el perfil del usuario del servicio (lo baja de nuevo la 1ª vez).
4. **ngrok:** evaluar login Google en el borde (Traffic Policy, solo los 2 emails) → un desconocido ni llega a Flask. Apagar inspector (guarda pedidos completos, cookies incluidas, en `localhost:4040`).
5. **Repo público:** expone URL de PROD, los 2 emails, datos de la familia. Decisión 2026-10: sigue público. Privatizar: GitHub → Settings → Danger Zone → Change visibility.
6. **Un venv por entorno:** DEV y PROD comparten Python (ver `CONTEXT_DEPLOY.md`). A futuro: servidor de producción (`waitress`) en vez del de desarrollo de Flask.

## Rutina (cada 2-3 meses / antes de deploy grande)
- Fallas conocidas en dependencias: procedimiento en `CONTEXT_DEPLOY.md`.
- Grep del log de PROD (cada uno = defensa que actuó): `AVISO: login CERRADO` (faltan credenciales / config ilegible) · `ilegible` (config.json roto) · `rechazado en` (POST de otro origen) · `ACCESO DENEGADO` (cuenta no permitida o email sin verificar) · `bypass DEV NO aplicado` (DEV pedido con nombre de sitio raro) · `backup_dir inválido` · `Cotización rechazada` / `No se pudo actualizar la cotización`.
- `tests/` verde: cada regla tiene su test.
- Revocar TODAS las sesiones (p.ej. teléfono perdido): cambiar `secret_key` en `config.json` + reiniciar → desloguea a todos.
