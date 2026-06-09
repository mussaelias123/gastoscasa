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
   - Endpoint NO está en `rutas_publicas` (`auth.*`, `static`).
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
