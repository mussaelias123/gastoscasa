# Contexto: Autenticación (Google OAuth)

> Leer junto con `CLAUDE.md`. Para login, sesión, control de acceso.

## Archivos del dominio
- `auth.py` (228 líneas). Blueprint `auth_bp` con prefix `/`.
- `templates/login.html` (216 líneas).
- Persistencia secret: `config.json` (`secret_key`, `google_client_id`, `google_client_secret`).

## Whitelist de emails
Hardcoded en `auth.py → EMAILS_PERMITIDOS`:
- `mussaelias123@gmail.com`
- `mossinomariana@gmail.com`

Para agregar usuario: editar la lista en `auth.py`. **No hay UI para esto** (decisión deliberada).

## Email → persona (módulo Personal)
`auth.py → PERSONAS_POR_EMAIL` traduce la cuenta de Google al valor de
`movimientos.persona`: `mussaelias123@gmail.com → elias`,
`mossinomariana@gmail.com → mari`. Helper `persona_de_email(email, defecto=None)`
(case-insensitive). Lo consume `_persona_actual()` de `app.py`: en el módulo
Personal la persona NO se elige en un desplegable, sale de la sesión, y cada uno
ve solo su propia cuenta.

Vive junto a `EMAILS_PERMITIDOS` a propósito: son la misma decisión (quién entra
y quién es). **Sumar un tercero obliga a tocar las dos listas.**

Con el bypass DEV la sesión es `dev@local`, que no está mapeado: ahí decide la
clave `persona_dev` de `config.json` (ver `CONTEXT_CONFIG.md`).

## Rutas
| Método | URL                       | Función         |
|--------|---------------------------|-----------------|
| GET    | `/login`                  | `login`         |
| GET    | `/auth/google`            | `google_login`  |
| GET    | `/auth/google/callback`   | `callback`      |
| GET    | `/logout`                 | `logout`        |

## Flujo
1. `init_auth(app, config_file)` se llama desde `app.py` antes de registrar rutas.
2. Se genera `secret_key` persistente si no existe (fix: sesiones sobreviven reinicios).
3. Se registra `before_request` middleware → redirige a `/login` si:
   - Endpoint NO está en `rutas_publicas` (`auth.*`, `static`, `manifest`,
     `service_worker`). **Van los nombres de ENDPOINT de Flask, no las URLs.**
     `manifest` = `/manifest.json` (PWA, agregado 2026-08-26): el navegador lo
     pide ANTES de que haya sesión; si cayera en el redirect al login leería el
     HTML del login como manifest y no aparecería el botón de instalar. No filtra
     nada: solo nombre, colores de la paleta e íconos, que ya eran públicos vía
     `static`. Ver la ruta en `CONTEXT_BACKEND.md`.
     `service_worker` = `/sw.js` (PWA, agregado 2026-09-22): mismo problema que
     el manifest pero peor, porque **se repite**: el navegador re-pide `/sw.js`
     en CADA navegación para chequear si hay versión nueva. Si cayera en el
     login recibiría el HTML del login donde espera JavaScript y el registro
     muere con "unsupported MIME type (text/html)" — y con él se rompería el
     apagado de emergencia (la lápida nunca llegaría al dispositivo). No expone
     datos: es código, y el cuerpo lo decide `sw_enabled` de `config.json`.
   - Y `session['user_email']` falta o no está en whitelist.
4. Si `google_client_id` o `google_client_secret` faltan en config → middleware deja pasar (modo bootstrap para configurar).

## Bypass DEV (`auth_disabled`) — TRIPLE CERROJO
Permite que el entorno DEV no pida login de Google, sin debilitar PROD.

- Clave de config: `auth_disabled` (en `config.py → DEFAULTS`, default **`False`**).
- En `require_login()` (después de `rutas_publicas`) el login se saltea **SOLO si
  se cumplen las TRES condiciones a la vez**:
  1. `cfg.get('auth_disabled') is True`
  2. `request.remote_addr in ('127.0.0.1', '::1')` (localhost)
  3. `not cfg.get('ngrok_enabled')` (ngrok apagado)
- Si las tres se cumplen y no hay sesión → inyecta usuario falso
  (`user_email='dev@local'`, `user_name='DEV'`) y `return None`.
- Si **cualquiera** falla → flujo de login normal, sin tocar nada. PROD idéntico.
- El cerrojo (3) garantiza que no hay proxy ⇒ `remote_addr` es confiable;
  por eso **NO** se usa `X-Forwarded-For` en este chequeo.
- `app.py → run_flask()`: si `app_name` contiene `'DEV'` **o** `auth_disabled=True`
  → bind a `127.0.0.1` (solo local, no se expone a la red). PROD con ngrok ya
  usaba `127.0.0.1`; ese caso no cambia.
- **Regla**: en PROD `auth_disabled` debe quedar SIEMPRE en `False`.

## Configuración de cookie de sesión
- Nombre: `gastos_session`
- Lifetime: 90 días
- HttpOnly: True
- SameSite: Lax

## Reglas específicas
1. **Nunca exponer `client_secret`** en logs ni respuestas.
2. **Whitelist es hardcode intencional** — se busca control estricto, no escala.
3. Cambiar `secret_key` invalida todas las sesiones (logout forzado).
4. OAuth scope: `openid email profile` (mínimo necesario).
5. La ruta `/auth/google/callback` debe estar configurada **igual** en Google Cloud Console.

## Al modificar este dominio, actualizar:
- Whitelist en este doc si se agrega/quita email.
- Tabla de rutas si se agrega ruta nueva.
- Sección "Reglas" si cambia política.
