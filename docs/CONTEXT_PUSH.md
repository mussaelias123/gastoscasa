# Contexto: Push (aviso al teléfono con la app cerrada)

> Leer junto con `CLAUDE.md`. Canal **aparte** de la campana: la campana es
> *pull* (se evalúa cuando alguien la mira), el push es *report by exception*.
> Para la campana, ver `CONTEXT_NOTIFICATIONS.md`.
>
> **Estado hoy**: el canal está entero y el motor (`CONTEXT_PUSH_MOTOR.md`) ya
> está conectado al envío, pero `push_enabled` sigue en `False`. Lo único que
> manda un push hoy es el **botón** de Settings.

**LA FRASE DE LA QUE SALE TODO: un push no se puede desavisar.** El que se quema
con dos noches de pitidos apaga los avisos para siempre: ahí no se pierde un
aviso, se pierde el canal. Y el otro lado: **un push que no llegó NO es
información perdida** — el dato sigue en la campana, que es donde vive; el push
es un empujón, no el registro. Todo lo de abajo elige el mismo error: perder un
aviso antes que mandar uno de más.

## 1. El payload — tres claves y ni una más

`_PUSH_PAYLOAD_CLAVES`: `titulo`, `cuerpo`, `url`.

⚠ **NUNCA lleva montos, saldos ni nombres de banco.** Se lee en la **pantalla
bloqueada**, sin desbloquear el teléfono, y lo ve cualquiera que lo tenga en la
mano. El número va adentro de la app; el aviso dice que hay algo para mirar.

⚠ **La `url` va RELATIVA** y `_push_payload()` la rechaza si no empieza con `/`:
el servidor no sabe su dirección pública (`cfg['ngrok_domain']` es un hostname
pelado, y en DEV está vacío), armarla sería adivinar y el aviso quedaría clavado
al dominio de ese día. El service worker sí sabe de dónde salió.

## 2. El envío (`app.py`)

`_push_enviar(filas, payload, cfg, ttl)` manda con `pywebpush` y devuelve
`(enviados, borradas)`. La validación de las VAPID vive **aparte**, en
`_push_claves_vapid(cfg)`, para que el motor pregunte ANTES de guardar (§5b).

- **`_PUSH_TIMEOUT = 3` va sí o sí**: `pywebpush` sin `timeout` se lo pasa a
  `requests` como `None` —**sin límite**— y un FCM mudo dejaba el worker de
  Flask colgado para siempre. **`_PUSH_TOPE_TANDA = 10`** es el techo de la
  tanda: el timeout es POR teléfono y los envíos van de a uno (cuatro
  dispositivos mudos eran 20 s con el botón clavado en "Mandando...").
- **Dos TTL a propósito.** `_PUSH_TTL = 60` es el del **botón** (un "andá a
  Settings" que llega media hora después no sirve). `_PUSH_TTL_AVISO = 7200`
  (2 h) es el de los **avisos automáticos**: aguanta el bache real —el subte,
  la notebook cerrada— sin cruzar la noche, porque con un TTL largo el servicio
  de push entregaría a las 4 de la mañana algo que cuidamos de no mandar a esa
  hora. Si vence con el teléfono apagado el aviso se perdió: ya está marcado.
- **Un envío que falla no frena a los demás**: son teléfonos distintos.
- **404 / 410 = suscripción muerta** (app desinstalada, datos limpiados, buzón
  caducado): la fila **se borra ahí mismo** — no va a andar nunca más, y
  dejarla hace que cada envío futuro la reintente y pague el timeout. Otro
  error se loguea y la fila queda quieta.
- **VAPID ausentes o rotas** → `_PushSinClaves` → **503 que dice qué hacer**: es
  config a medio hacer, no una falla. Se valida UNA vez antes del bucle; adentro
  caía en el except de cada teléfono y mandaba a re-suscribir el celular por un
  problema del server.
- ⚠ **Nunca se loguea el endpoint ni la excepción cruda.** Un endpoint es el
  buzón de un teléfono, y `requests` mete la URL completa en el texto de sus
  errores: un `{e}` pelado la filtraba en el caso más común, la red caída. Va
  `type(e).__name__`.

**El botón "Mandarme un aviso de prueba"** (`POST /api/push/prueba`) **no mira
`push_enabled`, a propósito**: ese flag apaga los avisos *automáticos*, y esto
es el diagnóstico del canal — si lo respetara, para probarlo habría que
encender antes la cosa que uno no sabe si funciona. ⚠ **Hay DOS llamadores de
`_push_enviar` y ni uno más** (el botón y `_push_ciclo()`): los cuenta
`TestUnSoloCaminoDeEnvio`, en `test_push_suscripciones.py`.

## 3. Service worker (`templates/sw.js`, mitad ACTIVO)

- `push` → **SIEMPRE llama a `showNotification()`**: si no, Chrome muestra
  *"Este sitio se actualizó en segundo plano"* y Safari da de baja la
  suscripción. Con el payload roto muestra un genérico igual.
- Recién **después**, `pushAvisarVentanas()` manda `{tipo:'push-recibido'}` a
  las ventanas abiertas (`clients.matchAll` + `postMessage`) y la campana se
  refresca sola; sin eso, quien tiene la app abierta ve el aviso del sistema y
  adentro no hay nada hasta recargar. ⚠ Va **al final de la cadena y con su
  propio catch**: un `postMessage` que falla no puede tapar la notificación.
- `notificationclick` → `clients.matchAll()` para enfocar una ventana ya
  abierta; si no hay ninguna, `clients.openWindow(url)`.

## 4. Frontend (`window.Push` en `app.js`)

`estado()`, `activar()`, `desactivar()`, `prueba()`, `bajaYSeguir()`, `esIOS()`,
`standalone()`, mismo estilo que `window.Notif`. Al lado vive el listener de
`navigator.serviceWorker` → `message`, que llama a `window.Notif.refrescar()`
(defensivo: puede no haber SW ni `Notif`). ⚠ El `tipo` se mira por
**extensibilidad, no por desconfianza**: acá solo despacha el service worker de
este mismo origen. **No agregar un chequeo de `evento.origin`** — los
`MessageEvent` de `Client.postMessage()` llegan con `origin` vacío en Chrome,
así que esa guarda no matchea nunca y deja la campana sin refrescar.

- **Nada pide permiso al cargar la página**: Chrome degrada a "prompt
  silencioso" al sitio que lo pide sin interacción, y en iOS
  `requestPermission()` fuera de un gesto real falla. Sale del click del botón
  de Settings, con un **modal explicativo antes** — en iOS el permiso se pide
  **una sola vez por instalación** y revertir un "No permitir" es borrar el
  ícono de inicio y volver a agregarlo.
- La UI vive en Settings (`CONTEXT_FRONTEND.md`); **el Inicio no se toca**
  (regla 7). **Las horas de silencio no tienen UI**: se editan en
  `config.json`, como `sw_enabled`. Menos superficie.

## 5. El motor automático — vive en su propio doc

Lo que decide **cuándo** avisar (flanco, siembra, horas de silencio, topes,
diferimiento) está en **`docs/CONTEXT_PUSH_MOTOR.md`**. Acá queda el canal:
qué viaja, cómo se manda y qué pasa del otro lado.

⚠ Hoy hay UN solo motor y UN solo botón, y los dos entran por
`_push_enviar()`. Cualquier tercer camino es, por definición, algo que manda
avisos sin pasar por los frenos.

## Al modificar este dominio, actualizar:
- Sección 1 si cambian las claves del payload o la regla de que no viajan montos.
- Sección 2 si cambia el manejo del 410, los timeouts, los TTL o `_PushSinClaves`.
- Sección 3 o 4 si cambia el service worker o `window.Push`.
- El motor tiene su propio doc: `CONTEXT_PUSH_MOTOR.md`.
