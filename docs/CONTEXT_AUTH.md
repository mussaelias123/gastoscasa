# Contexto: Autenticación (Google OAuth)

> Leer junto con `CLAUDE.md`. Para login, sesión, control de acceso.

## Archivos del dominio
- `auth.py` (~750 líneas). Blueprint `auth_bp` con prefix `/`.
- `templates/login.html` (~210 líneas).
- Persistencia secret: `config.json` (`secret_key`, `google_client_id`, `google_client_secret`).
- Tests: `tests/test_auth_cerrado.py` (falla cerrado), `tests/test_auth_endurecido.py` (chequeo de origen, cuarto
  cerrojo del bypass, `email_verified`, cookie `Secure`) y `tests/test_config_seguro.py` (lectura/escritura de `config.json`).

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
3. Se registran DOS `before_request`, **en este orden**: primero `_exigir_origen_propio` (los POST solo desde la
   propia app: un pedido ajeno muere con 403 sin mirar el login, ver su sección) y después `require_login`, que
   redirige a `/login` si:
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
  la cookie es `SameSite=Lax` — que tapa el POST cross-site (que además ya
  frena el chequeo de origen) pero **no** la navegación GET. Un link desde
  cualquier lado a `<dominio>/logout` sigue
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

## Los POST solo desde la propia app (chequeo de origen)
Segunda defensa contra CSRF: que una página de OTRO sitio, abierta en el mismo navegador, mande un POST con la
sesión de quien la tiene abierta. La primera es `SameSite=Lax`, que tiene filos: **no mira el puerto** (en
localhost, `localhost:8080` y `localhost:5050` son el mismo sitio), por el túnel depende de que `ngrok-free.dev`
esté en la lista de sufijos públicos del navegador, y un navegador viejo la ignora.

En DEV es la **única** barrera: el bypass autentica por IP, no por cookie, así que `SameSite` no protege nada y
un sitio cualquiera podría mandar un POST ciego a `localhost:5050` desde el navegador del desarrollador.

`_exigir_origen_propio` corre para **POST / PUT / PATCH / DELETE** en **todas** las rutas, las públicas incluidas
(`/logout` acepta POST). Un GET nunca se frena. Si viene `Origin`, el `Referer` ni se mira.

| Viene | Se acepta si |
|-------|--------------|
| `Origin` | su host:puerto es el de `request.host` (mayúsculas no importan). `null`, vacío o ilegible → **403** |
| solo `Referer` | lo mismo, con el host:puerto del Referer |
| ninguno | pasa (navegador viejo, cliente de pruebas, curl): queda sola la cookie SameSite |

- **El esquema NO se compara**: detrás de ngrok Flask ve `http` y el navegador manda `Origin: https://...`;
  compararlo rechazaría todos los POST de PROD. El **puerto sí**. No hay lista de sitios para configurar: se
  compara con el Host con el que el navegador llegó (en PROD el dominio público de ngrok, el mismo que usa el
  login para armar la `redirect_uri`).
- **Rechazo**: 403 — JSON `{'ok': False, 'error': ...}` si trae `X-Requested-With: XMLHttpRequest`, texto plano
  si no — y `AVISO:` en el log (1 por minuto) con el motivo y el Host **saneados** (solo `[a-z0-9.:_[]-]`, tope
  de 60 caracteres). Nunca la ruta pedida ni valores crudos.
- **Va ANTES de `require_login`** (orden de registro en `init_auth`; un test cuida el orden): un POST ajeno se
  frena aun sin sesión, en las rutas públicas y con el bypass DEV.
- **No frena el DNS rebinding**: ahí Origin y Host coinciden. Lo cierra el cuarto cerrojo del bypass (abajo).
- ⚠ **Trampa**: con `Referrer-Policy: no-referrer` en una página, los navegadores pueden mandar `Origin: null`
  en los formularios del propio sitio, y este chequeo los rechaza. Si se agrega la cabecera, usar `same-origin`
  o `strict-origin-when-cross-origin`.
- ⚠ Si de golpe **todos los POST dan 403**: leer el `AVISO:` (dice el motivo y el Host que vio). Casi seguro algo
  (proxy, túnel) reescribe el `Host`.

## Bypass DEV (`auth_disabled`) — CUÁDRUPLE CERROJO
Permite que el entorno DEV no pida login de Google, sin debilitar PROD.

- Clave de config: `auth_disabled` (en `config.py → DEFAULTS`, default **`False`**).
- En `require_login()` (después de `rutas_publicas`) el login se saltea **SOLO si
  se cumplen las CUATRO condiciones a la vez**:
  1. `cfg.get('auth_disabled') is True`
  2. `request.remote_addr in ('127.0.0.1', '::1')` (localhost)
  3. `not cfg.get('ngrok_enabled')` (ngrok apagado)
  4. `_host_es_local(request.host)`: el sitio pedido es `localhost`, `127.0.0.1` o `[::1]`/`::1`
     (con o sin puerto, mayúsculas no importan)
- Si las cuatro se cumplen y no hay sesión → inyecta usuario falso
  (`user_email='dev@local'`, `user_name='DEV'`) y `return None`.
- Si **cualquiera** falla → flujo de login normal, sin tocar nada. PROD idéntico.
- El cerrojo (3) garantiza que no hay proxy ⇒ `remote_addr` es confiable;
  por eso **NO** se usa `X-Forwarded-For` en este chequeo.
- **Cerrojo (4), por qué**: (1)–(3) miran *de dónde* viene el pedido, no *a qué sitio* lo mandó el navegador.
  Con "DNS rebinding" una página maliciosa abierta en la PC de desarrollo usa un dominio suyo que, ya cargada,
  pasa a resolver a `127.0.0.1`: para el navegador es el mismo sitio, y su JavaScript podía pedir y **leer** la
  app DEV (que no pide login). Venía de `127.0.0.1`, y hasta el chequeo de origen coincide con el Host. Lo único
  que lo delata es el nombre (`Host: evil.example`).
- **Lista cerrada, texto ENTERO y sin recortar** (`fullmatch`, sin `strip`): `localhost.evil.example`,
  `evil.example@localhost`, `localhost:5050@evil.example` y `localhost\n` no pasan.
- **Consecuencia**: entrar a DEV por un alias (archivo `hosts`) o por cualquier otro nombre que no sea esos tres
  ya no saltea el login. Si el nombre es lo ÚNICO que lo frena, sale `AVISO: bypass DEV NO aplicado — el sitio
  pedido (...)` en el log (1 por minuto, Host saneado): es la pista para quien no entiende por qué le pide login.
- `app.py → run_flask()`: si `app_name` contiene `'DEV'` **o** `auth_disabled=True`
  → bind a `127.0.0.1` (solo local, no se expone a la red). PROD con ngrok ya
  usaba `127.0.0.1`; ese caso no cambia.
- **Regla**: en PROD `auth_disabled` debe quedar SIEMPRE en `False`.

## El email tiene que estar confirmado por Google (`email_verified`)
Además de estar en `EMAILS_PERMITIDOS`, el `callback` exige `email_verified` **verdadero** en la info de Google: el
booleano `True` o el string `'true'` (algunos endpoints, como tokeninfo, lo mandan como texto). Falso, `'false'`,
`null`, cualquier otro valor y la clave **ausente** se rechazan con el mismo `error=no_permitido` que un email no
permitido (`login.html` no cambia); el `AVISO:` del log dice la razón (`email_verified falso o ausente`). Vale
también para la info que el callback pide aparte con `userinfo()` cuando el token no la trae.

Por qué: con una cuenta de Google creada con un email ajeno a `@gmail.com` y nunca confirmado, el `email` del
token es el que su titular *dijo* tener. Con las dos cuentas de hoy (`@gmail.com`) Google manda siempre `True`.
Un test que simule el callback tiene que incluir `email_verified: True` o el login se rechaza.

## Configuración de cookie de sesión
- Nombre: `gastos_session`
- Lifetime: 90 días
- HttpOnly: True
- SameSite: Lax
- **Secure: `_cookie_secure_para(cfg)`** — `True` solo cuando la app sale por el túnel de ngrok (HTTPS): `first_run`
  apagado, `ngrok_enabled` prendido y `'DEV'` fuera de `app_name`. **Es la misma condición con la que `run_flask`
  (app.py) levanta ngrok**: si cambia una, cambiar la otra (auth.py no puede importar app.py). En DEV y en red
  local (http, a veces por IP) queda en **False**: con Secure el navegador no guarda la cookie y el login deja de
  andar. Se decide **una vez, al arrancar** (igual que el túnel): cambiar `ngrok_enabled` o `app_name` pide
  reiniciar. Prendida, el arranque deja `OK: Cookie de sesión Secure — la app sale por ngrok (HTTPS).`
  Si PROD se abre por `http://localhost:<puerto>` en la misma PC, los navegadores de escritorio suelen aceptar igual
  la cookie (tratan localhost como seguro; **no verificado en este equipo**); por la IP de la red no, pero con
  ngrok la app escucha solo en `127.0.0.1`.

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
7. **Lo que cambia datos es POST/PUT/PATCH/DELETE, nunca GET**: el chequeo de origen no mira los GET. Y un
   `before_request` nuevo que decida algo sobre el pedido se registra DESPUÉS de `_exigir_origen_propio`.
8. `email_verified` ausente = no verificado. No relajar ese chequeo "para que ande".
9. No poner `Referrer-Policy: no-referrer` (ver "Los POST solo desde la propia app").

## Al modificar este dominio, actualizar:
- Whitelist en este doc si se agrega/quita email.
- Tabla de rutas si se agrega ruta nueva.
- Sección "Reglas" si cambia política.
