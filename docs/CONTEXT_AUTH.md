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
