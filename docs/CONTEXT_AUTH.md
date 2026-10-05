# Contexto: Autenticación (Google OAuth)

> Leer junto con `CLAUDE.md`. Para login, sesión, control de acceso.

## Archivos del dominio
- `auth.py` (~470 líneas). Blueprint `auth_bp` con prefix `/`.
- `templates/login.html` (~210 líneas).
- Persistencia secret: `config.json` (`secret_key`, `google_client_id`, `google_client_secret`).
- Tests: `tests/test_auth_cerrado.py` (falla cerrado) y `tests/test_config_seguro.py` (lectura/escritura de `config.json`).

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
| GET    | `/auth/callback`          | `callback`      |
| GET    | `/logout`                 | `logout`        |

⚠ El callback es **`/auth/callback`**, no `/auth/google/callback` (así decía este doc hasta
2026-10-02 y esa URL no existe). Es la URI de redirección que va en Google Cloud Console.
`/login`, `/auth/google` y `/auth/callback` cierran si faltan credenciales (ver "La app falla CERRADO").

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
4. **Sin credenciales de Google → CERRADO** (hasta 2026-10-02 acá decía "deja pasar, modo bootstrap"). Si
   `google_client_id` o `google_client_secret` faltan en la config EN CALIENTE, o `config.json` está ilegible, el
   middleware redirige todo a `/login?error=no_configurado`. Orden: `rutas_publicas` → bypass DEV → **credenciales**
   → sesión → whitelist. Detalle y recuperación en la sección siguiente.

## La app falla CERRADO (sin credenciales de Google no entra nadie)
Antes, sin credenciales el middleware "dejaba pasar para poder configurar". Por el túnel de ngrok eso era **todo
internet**, y no hacía falta ningún descuido: un `config.json` roto, a medias o leído justo mientras se escribía
hacía que `cargar_config()` devolviera DEFAULTS —sin credenciales— y la app quedaba abierta (comprobado: `GET /gastos`
sin sesión daba 200). El modo bootstrap **se eliminó**: la puesta en marcha es 100% por `config.json`
(`CONTEXT_CONFIG.md`), no hay primer arranque por la web.

- **Qué cierra**: toda ruta fuera de `rutas_publicas` y del bypass DEV, páginas y POST, **incluso con sesión válida**
  (una config que no se puede verificar no se arregla con la cookie de ayer). Config ilegible = sin credenciales.
- **Las rutas del blueprint**: `/login` muestra el aviso `no_configurado` aunque no venga en la URL. Ese chequeo va
  ANTES de mirar la sesión: al revés, con una cookie válida mandaría a `/`, el middleware lo devolvería a `/login` y
  habría un **bucle de redirecciones**. `/auth/google` y `/auth/callback` NO hablan con Google: redirigen al aviso.
- **Qué ve el usuario**: "Inicio de sesión no disponible: el servidor no tiene las credenciales de Google en su
  `config.json`, o no puede leerlo; quien administra tiene que revisarlo y reiniciar el servicio" (`login.html`).
- **Log**: `AVISO: login CERRADO — ...` (1 por minuto, sin datos del request) y, si el archivo está roto, `AVISO:
  config.json ilegible: ...` con tipo y posición del error (de `config.py`).
- **Recuperación**: mirar el log → cargar/arreglar `config.json` → **reiniciar el servicio**. Las credenciales se
  registran en Authlib UNA vez, en `init_auth`: cargarlas con la app andando destraba el middleware, pero el cliente
  de Authlib sigue con el placeholder `no-configurado` y Google las rechaza. Un JSON roto que se arregla sí se nota solo.
- **Arrancar con el archivo ilegible**: `init_auth` no inventa una `secret_key` sobre un config que no puede leer;
  corta con `ConfigIlegible` ("config.json ilegible: arreglarlo antes de arrancar").
- DEV sin OAuth: el bypass (abajo). Congelado en `tests/test_auth_cerrado.py`: cada test "cerrado" tiene su contracara "abierto".

## El logout limpia las suscripciones push
`logout()` borra las filas de `push_suscripciones` de ese `user_email` (vía
`database.borrar_suscripciones_push_de_email`) **antes** del `session.clear()`.
Quien se va de un navegador deja de recibir ahí los avisos de su cuenta.

Dos detalles que parecen de estilo y no lo son:

- **El orden**: el email vive en la sesión, así que después del `clear()` no
  habría a quién borrarle nada y la fila quedaría viva para siempre, sin que
  nadie se entere. Es el mismo motivo por el que `user_name` se lee arriba.
- **El `try/except`**: si el borrado falla (base bloqueada, disco lleno), se
  loguea `AVISO:` y el logout sigue. Una suscripción huérfana es un aviso de
  más en un teléfono; no poder salir de la sesión es quedarse adentro de la
  app.

**Se borra SOLO el navegador que se va, si dice cuál es** (deuda de la etapa
anterior, cerrada acá). El front (`initSalir()` en `app.js`) desuscribe este
navegador y manda su `endpoint` por POST antes de navegar; con ese dato el
borrado se acota a **una fila**.

Sin ese dato —sin JavaScript, un link pegado a mano, un navegador sin push— se
cae al comportamiento viejo y se borran todas las filas de esa cuenta. Ese
fallback es a propósito, pero conviene saber qué tapa y qué no:

- **Lo que arregla**: desloguearse en la notebook ya no apaga los avisos del
  teléfono.
- **Lo que NO arregla del todo**: `/logout` sigue siendo **GET y público**, y
  la cookie es `SameSite=Lax` — que tapa el POST cross-site pero **no** la
  navegación GET. Un link desde cualquier lado a `<dominio>/logout` sigue
  entrando por el camino sin endpoint y se lleva las suscripciones de todos los
  dispositivos de esa cuenta. Se recupera re-suscribiendo cada uno. Cerrarlo del
  todo es pasar el logout a POST con token, que es un cambio de otro tamaño.

Otro efecto esperable del borrado, para que no se investigue como bug: el
ciclo **logout → login → alta** regenera la fila con `creada` nueva, así que
mueve el hash de la base y puede disparar un backup en un día sin movimientos.
No es el detector mintiendo — el conjunto de suscripciones efectivamente se
borró y se volvió a crear.

Las dos rutas que escriben esa tabla (`/api/push/alta`, `/api/push/baja`) **NO**
van en `rutas_publicas`: son las que atan un endpoint a una persona. Ver
`CONTEXT_BACKEND.md` y `CONTEXT_DB.md`. Congelado en
`tests/test_push_suscripciones.py`.

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

## Lo que viaja a los templates (`cfg`)
`app.py → inject_config()` le pasa la config a TODOS los templates bajo `cfg`.
Le pasaba el dict **entero**: `secret_key`, `google_client_secret` y
`ngrok_authtoken` incluidos. Ningún template los imprimía —no había fuga— pero
estaban a un `{{ cfg }}` de aparecer en el HTML, que se lee con click derecho.

Desde 2026-09-22 el `cfg` que cruza a Jinja va **recortado**
(`config.sin_secretos`): se van las claves cuyo nombre las marca como secretas.
El criterio y la regla para nombrar una clave nueva están en
`CONTEXT_CONFIG.md`; lo que importa acá:

- `secret_key` y `google_client_secret` **no llegan al template**, y no hay
  forma de que un template los imprima aunque quiera (una clave ausente en
  Jinja es `Undefined`: renderiza vacío, no explota).
- Las rutas **no** pasan `cfg=` a `render_template` — eso pisaría el recortado
  con el dict completo. `cfg` entra por un solo lugar.
- Congelado en `tests/test_cfg_secretos.py`, incluido el test que revisa que el
  **HTML servido** no contenga ningún valor secreto.

## Reglas específicas
1. **Nunca exponer `client_secret`** en logs ni respuestas — ni en el HTML: el
   `cfg` de los templates va recortado (ver arriba).
2. **Whitelist es hardcode intencional** — se busca control estricto, no escala.
3. Cambiar `secret_key` invalida todas las sesiones (logout forzado).
4. OAuth scope: `openid email profile` (mínimo necesario).
5. La ruta `/auth/callback` debe estar configurada **igual** en Google Cloud Console (URI de redirección autorizada).
6. **Fallar cerrado**: ningún código nuevo puede "dejar pasar" por faltar credenciales, estar la config ilegible o
   fallar al leerla. Ante la duda, redirigir a `/login?error=no_configurado`.

## Al modificar este dominio, actualizar:
- Whitelist en este doc si se agrega/quita email.
- Tabla de rutas si se agrega ruta nueva.
- Sección "Reglas" si cambia política.
