# Contexto: Autenticación (Google OAuth)

> Leer junto con `CLAUDE.md`. Login, sesión, control de acceso.

## Archivos del dominio
- `auth.py` (~750 líneas). Blueprint `auth_bp` prefix `/`.
- `templates/login.html` (~210 líneas).
- Persistencia secret: `config.json` (`secret_key`, `google_client_id`, `google_client_secret`).
- Tests: `tests/test_auth_cerrado.py` (falla cerrado), `tests/test_auth_endurecido.py` (chequeo origen, cuarto cerrojo bypass, `email_verified`, cookie `Secure`), `tests/test_config_seguro.py` (lectura/escritura `config.json`).

## Whitelist de emails
Hardcoded `auth.py → EMAILS_PERMITIDOS`:
- `mussaelias123@gmail.com`
- `mossinomariana@gmail.com`

Agregar usuario: editar lista en `auth.py`. **NO hay UI** (decisión deliberada).

## Email → persona (módulo Personal)
`auth.py → PERSONAS_POR_EMAIL` traduce cuenta Google → `movimientos.persona`: `mussaelias123@gmail.com → elias`, `mossinomariana@gmail.com → mari`. Helper `persona_de_email(email, defecto=None)` (case-insensitive). Lo usa `_persona_actual()` de `app.py`: en Personal la persona NO se elige en desplegable, sale de la sesión; cada uno ve solo su cuenta.

Vive junto a `EMAILS_PERMITIDOS` a propósito: misma decisión (quién entra y quién es). **Sumar tercero = tocar las dos listas.**

Bypass DEV: sesión `dev@local`, no mapeado → decide clave `persona_dev` de `config.json` (ver `CONTEXT_CONFIG.md`).

## Rutas
| Método | URL | Función |
|-|-|-|
| GET | `/login` | `login` |
| GET | `/auth/google` | `google_login` |
| GET | `/auth/callback` | `callback` |
| GET | `/logout` | `logout` |

⚠ Callback = **`/auth/callback`**, no `/auth/google/callback` (doc decía eso hasta 2026-10-02; esa URL no existe). Es la URI de redirección en Google Cloud Console. `/login`, `/auth/google`, `/auth/callback` cierran si faltan credenciales (ver "La app falla CERRADO").

## Flujo
1. `init_auth(app, config_file)` desde `app.py`, antes de registrar rutas.
2. `secret_key` persistente si no existe (fix: sesiones sobreviven reinicios).
3. Dos `before_request`, **en este orden**: 1º `_exigir_origen_propio` (POST solo desde la propia app; pedido ajeno → 403 sin mirar login, ver sección) · 2º `require_login` → redirige a `/login` si:
   - Endpoint NO en `rutas_publicas` (`auth.*`, `static`, `manifest`, `service_worker`). **Nombres de ENDPOINT Flask, no URLs.**
     - `manifest` = `/manifest.json` (PWA, 2026-08-26): navegador lo pide ANTES de sesión; si cae en login lee HTML como manifest → no aparecería botón instalar. No filtra nada (solo nombre, colores, íconos, ya públicos vía `static`). Ver `CONTEXT_BACKEND.md`.
     - `service_worker` = `/sw.js` (PWA, 2026-09-22): mismo problema, peor porque **se repite**: navegador re-pide `/sw.js` en CADA navegación para chequear versión nueva. En login recibe HTML donde espera JS → registro muere "unsupported MIME type (text/html)" → se rompe apagado de emergencia (lápida nunca llega al dispositivo). No expone datos: es código; el cuerpo lo decide `sw_enabled` de `config.json`.
   - Y `session['user_email']` falta o no está en whitelist.
4. **Sin credenciales Google → CERRADO** (hasta 2026-10-02 decía "deja pasar, modo bootstrap"). Si `google_client_id` o `google_client_secret` faltan EN CALIENTE, o `config.json` ilegible → redirige todo a `/login?error=no_configurado`. Orden: `rutas_publicas` → bypass DEV → **credenciales** → sesión → whitelist. Detalle abajo.

## La app falla CERRADO (sin credenciales de Google no entra nadie)
Antes, sin credenciales el middleware "dejaba pasar para configurar". Por el túnel ngrok = **todo internet**; no hacía falta ningún descuido: `config.json` roto, a medias o leído mientras se escribía → `cargar_config()` devolvía DEFAULTS (sin credenciales) → app abierta (comprobado: `GET /gastos` sin sesión daba 200). Modo bootstrap **eliminado**: puesta en marcha 100% por `config.json` (`CONTEXT_CONFIG.md`); no hay primer arranque por web.

- **Qué cierra**: toda ruta fuera de `rutas_publicas` y bypass DEV, páginas y POST, **incluso con sesión válida** (config que no se puede verificar no se arregla con cookie de ayer). Config ilegible = sin credenciales.
- **Rutas del blueprint**: `/login` muestra aviso `no_configurado` aunque no venga en URL. Chequeo ANTES de mirar sesión: al revés, con cookie válida mandaría a `/`, middleware lo devolvería a `/login` → **bucle de redirecciones**. `/auth/google` y `/auth/callback` NO hablan con Google: redirigen al aviso.
- **Qué ve el usuario**: "Inicio de sesión no disponible: el servidor no tiene las credenciales de Google en su `config.json`, o no puede leerlo; quien administra tiene que revisarlo y reiniciar el servicio" (`login.html`).
- **Log**: `AVISO: login CERRADO — ...` (1 por minuto, sin datos del request) y, si archivo roto, `AVISO: config.json ilegible: ...` con tipo y posición del error (de `config.py`).
- **Recuperación**: mirar log → cargar/arreglar `config.json` → **reiniciar servicio**. Credenciales se registran en Authlib UNA vez, en `init_auth`: cargarlas con app andando destraba middleware, pero cliente Authlib sigue con placeholder `no-configurado` y Google las rechaza. JSON roto que se arregla sí se nota solo.
- **Arrancar con archivo ilegible**: `init_auth` NO inventa `secret_key` sobre config que no puede leer; corta con `ConfigIlegible` ("config.json ilegible: arreglarlo antes de arrancar").
- DEV sin OAuth: bypass (abajo). Congelado en `tests/test_auth_cerrado.py`: cada test "cerrado" tiene contracara "abierto".

## El logout limpia las suscripciones push
`logout()` borra filas de `push_suscripciones` de ese `user_email` (vía `database.borrar_suscripciones_push_de_email`) **antes** del `session.clear()`. Quien se va de un navegador deja de recibir ahí avisos de su cuenta.

Dos detalles que parecen estilo y no lo son:

- **Orden**: email vive en sesión; tras `clear()` no habría a quién borrar nada → fila viva para siempre, nadie se entera. Mismo motivo por el que `user_name` se lee arriba.
- **`try/except`**: si borrado falla (base bloqueada, disco lleno) → `AVISO:` en log y logout sigue. Suscripción huérfana = aviso de más en teléfono; no poder salir = quedarse adentro de la app.

**Se borra SOLO el navegador que se va, si dice cuál es** (deuda etapa anterior, cerrada acá). Front (`initSalir()` en `app.js`) desuscribe este navegador y manda su `endpoint` por POST antes de navegar; con ese dato el borrado se acota a **una fila**.

Sin ese dato —sin JavaScript, link pegado a mano, navegador sin push— cae al comportamiento viejo: borra TODAS las filas de esa cuenta. Fallback a propósito; qué tapa y qué no:

- **Arregla**: desloguearse en notebook ya no apaga avisos del teléfono.
- **NO arregla del todo**: `/logout` sigue **GET y público**; cookie `SameSite=Lax` tapa POST cross-site (y ya frena chequeo de origen) pero **no** navegación GET. Link desde cualquier lado a `<dominio>/logout` entra por camino sin endpoint y se lleva suscripciones de todos los dispositivos de la cuenta. Se recupera re-suscribiendo cada uno. Cerrarlo del todo = pasar logout a POST con token (cambio de otro tamaño).

Efecto esperable (no investigar como bug): ciclo **logout → login → alta** regenera fila con `creada` nueva → mueve hash de la base → puede disparar backup en día sin movimientos. No es el detector mintiendo: conjunto de suscripciones efectivamente se borró y recreó.

Las dos rutas que escriben esa tabla (`/api/push/alta`, `/api/push/baja`) **NO** van en `rutas_publicas`: atan endpoint a persona. Ver `CONTEXT_BACKEND.md` y `CONTEXT_DB.md`. Congelado en `tests/test_push_suscripciones.py`.

## Los POST solo desde la propia app (chequeo de origen)
2da defensa CSRF: página de OTRO sitio, abierta en mismo navegador, no manda POST con sesión de quien la tiene abierta. Primera = `SameSite=Lax`, con filos: **no mira puerto** (`localhost:8080` y `localhost:5050` = mismo sitio); por túnel depende de que `ngrok-free.dev` esté en lista de sufijos públicos del navegador; navegador viejo la ignora.

En DEV es la **única** barrera: bypass autentica por IP, no por cookie → `SameSite` no protege nada; un sitio cualquiera podría mandar POST ciego a `localhost:5050` desde el navegador del dev.

`_exigir_origen_propio` corre para **POST / PUT / PATCH / DELETE** en **todas** las rutas, públicas incluidas (`/logout` acepta POST). GET nunca se frena. Si viene `Origin`, `Referer` ni se mira.

| Viene | Se acepta si |
|-|-|
| `Origin` | host:puerto = `request.host` (mayúsculas no importan). `null`, vacío o ilegible → **403** |
| solo `Referer` | igual, con host:puerto del Referer |
| ninguno | pasa (navegador viejo, cliente de pruebas, curl): queda sola la cookie SameSite |

- **Esquema NO se compara**: detrás de ngrok Flask ve `http`, navegador manda `Origin: https://...`; compararlo rechazaría todos los POST de PROD. **Puerto sí**. Sin lista de sitios: se compara con el Host con que llegó el navegador (PROD: dominio público ngrok, el mismo que usa login para `redirect_uri`).
- **Rechazo**: 403 — JSON `{'ok': False, 'error': ...}` si trae `X-Requested-With: XMLHttpRequest`, texto plano si no — y `AVISO:` en log (1 por minuto) con motivo y Host **saneados** (solo `[a-z0-9.:_[]-]`, tope 60 caracteres). NUNCA ruta pedida ni valores crudos.
- **Va ANTES de `require_login`** (orden en `init_auth`; test cuida el orden): POST ajeno frenado aun sin sesión, en rutas públicas y con bypass DEV.
- **NO frena DNS rebinding**: ahí Origin y Host coinciden. Lo cierra el cuarto cerrojo del bypass (abajo).
- ⚠ **Trampa**: con `Referrer-Policy: no-referrer`, navegadores pueden mandar `Origin: null` en forms del propio sitio, y este chequeo los rechaza. Si se agrega la cabecera, usar `same-origin` o `strict-origin-when-cross-origin`.
- ⚠ Si de golpe **todos los POST dan 403**: leer `AVISO:` (motivo y Host que vio). Casi seguro algo (proxy, túnel) reescribe `Host`.

## Bypass DEV (`auth_disabled`) — CUÁDRUPLE CERROJO
Permite que DEV no pida login Google, sin debilitar PROD.

- Clave config: `auth_disabled` (`config.py → DEFAULTS`, default **`False`**).
- En `require_login()` (después de `rutas_publicas`) login se saltea **SOLO si se cumplen las CUATRO condiciones a la vez**:
  1. `cfg.get('auth_disabled') is True`
  2. `request.remote_addr in ('127.0.0.1', '::1')` (localhost)
  3. `not cfg.get('ngrok_enabled')` (ngrok apagado)
  4. `_host_es_local(request.host)`: sitio pedido es `localhost`, `127.0.0.1` o `[::1]`/`::1` (con o sin puerto, mayúsculas no importan)
- Las cuatro + sin sesión → inyecta usuario falso (`user_email='dev@local'`, `user_name='DEV'`) y `return None`.
- **Cualquiera** falla → flujo login normal, sin tocar nada. PROD idéntico.
- Cerrojo (3) garantiza no hay proxy ⇒ `remote_addr` confiable; por eso **NO** se usa `X-Forwarded-For` acá.
- **Cerrojo (4), por qué**: (1)–(3) miran *de dónde* viene el pedido, no *a qué sitio* lo mandó el navegador. Con "DNS rebinding" una página maliciosa abierta en PC de desarrollo usa dominio suyo que, ya cargada, pasa a resolver a `127.0.0.1`: para el navegador es mismo sitio; su JS podía pedir y **leer** app DEV (no pide login). Venía de `127.0.0.1`, y hasta chequeo de origen coincide con Host. Lo único que lo delata es el nombre (`Host: evil.example`).
- **Lista cerrada, texto ENTERO sin recortar** (`fullmatch`, sin `strip`): `localhost.evil.example`, `evil.example@localhost`, `localhost:5050@evil.example` y `localhost\n` NO pasan.
- **Consecuencia**: entrar a DEV por alias (archivo `hosts`) o cualquier otro nombre que no sea esos tres → NO saltea login. Si el nombre es lo ÚNICO que lo frena, sale `AVISO: bypass DEV NO aplicado — el sitio pedido (...)` en log (1 por minuto, Host saneado): pista para quien no entiende por qué le pide login.
- `app.py → run_flask()`: si `app_name` contiene `'DEV'` **o** `auth_disabled=True` → bind `127.0.0.1` (solo local, no se expone a la red). PROD con ngrok ya usaba `127.0.0.1`; no cambia.
- **Regla**: en PROD `auth_disabled` SIEMPRE `False`.

## El email tiene que estar confirmado por Google (`email_verified`)
Además de estar en `EMAILS_PERMITIDOS`, `callback` exige `email_verified` **verdadero**: booleano `True` o string `'true'` (tokeninfo lo manda como texto). Falso, `'false'`, `null`, otro valor y clave **ausente** → rechazo con mismo `error=no_permitido` que email no permitido (`login.html` no cambia); `AVISO:` en log dice razón (`email_verified falso o ausente`). Vale también para info que callback pide aparte con `userinfo()` cuando token no la trae.

Por qué: cuenta Google creada con email ajeno a `@gmail.com` nunca confirmado → `email` del token es el que su titular *dijo* tener. Con las dos cuentas de hoy (`@gmail.com`) Google manda siempre `True`. Test que simule callback DEBE incluir `email_verified: True` o login se rechaza.

## Configuración de cookie de sesión
- Nombre: `gastos_session`
- Lifetime: 90 días
- HttpOnly: True
- SameSite: Lax
- **Secure: `_cookie_secure_para(cfg)`** — `True` SOLO cuando app sale por túnel ngrok (HTTPS): `first_run` apagado, `ngrok_enabled` prendido y `'DEV'` fuera de `app_name`. **Misma condición con la que `run_flask` (app.py) levanta ngrok**: si cambia una, cambiar la otra (auth.py no puede importar app.py). En DEV y red local (http, a veces por IP) queda **False**: con Secure el navegador NO guarda la cookie y el login deja de andar. Se decide **una vez, al arrancar** (igual que túnel): cambiar `ngrok_enabled` o `app_name` pide reiniciar. Prendida, arranque deja `OK: Cookie de sesión Secure — la app sale por ngrok (HTTPS).`
  Si PROD se abre por `http://localhost:<puerto>` en la misma PC, navegadores de escritorio suelen aceptar igual la cookie (tratan localhost como seguro; **no verificado en este equipo**); por IP de red NO, pero con ngrok la app escucha solo en `127.0.0.1`.

## Lo que viaja a los templates (`cfg`)
`app.py → inject_config()` pasa config a TODOS los templates bajo `cfg`. Pasaba dict **entero**: `secret_key`, `google_client_secret`, `ngrok_authtoken` incluidos. Ningún template los imprimía (no había fuga), pero estaban a un `{{ cfg }}` de aparecer en HTML (se lee con click derecho).

Desde 2026-09-22 `cfg` a Jinja va **recortado** (`config.sin_secretos`): fuera claves cuyo nombre las marca secretas. Criterio y regla para nombrar clave nueva: `CONTEXT_CONFIG.md`. Acá importa:

- `secret_key` y `google_client_secret` **NO llegan al template**; ningún template puede imprimirlos aunque quiera (clave ausente en Jinja = `Undefined`: renderiza vacío, no explota).
- Rutas **NO** pasan `cfg=` a `render_template` — pisaría el recortado con dict completo. `cfg` entra por un solo lugar.
- Congelado en `tests/test_cfg_secretos.py`, incl. test que revisa que **HTML servido** no contenga ningún valor secreto.

## Reglas específicas
1. **NUNCA exponer `client_secret`** en logs ni respuestas — ni en HTML: `cfg` de templates va recortado (ver arriba).
2. **Whitelist = hardcode intencional** — control estricto, no escala.
3. Cambiar `secret_key` invalida todas las sesiones (logout forzado).
4. OAuth scope: `openid email profile` (mínimo necesario).
5. `/auth/callback` debe estar configurada **igual** en Google Cloud Console (URI de redirección autorizada).
6. **Fallar cerrado**: ningún código nuevo "deja pasar" por faltar credenciales, config ilegible o error al leerla. Ante la duda, redirigir a `/login?error=no_configurado`.
7. **Lo que cambia datos = POST/PUT/PATCH/DELETE, NUNCA GET**: el chequeo de origen no mira GET. `before_request` nuevo que decida algo sobre el pedido se registra DESPUÉS de `_exigir_origen_propio`.
8. `email_verified` ausente = no verificado. NO relajar ese chequeo "para que ande".
9. NO poner `Referrer-Policy: no-referrer` (ver "Los POST solo desde la propia app").

## Al modificar este dominio, actualizar:
- Whitelist en este doc si se agrega/quita email.
- Tabla de rutas si se agrega ruta nueva.
- Sección "Reglas" si cambia política.
