# Contexto: Push (aviso al teléfono con la app cerrada)

> Leer con `CLAUDE.md`. Canal **aparte** de la campana: campana = *pull* (se evalúa al mirarla), push = *report by exception*. Campana: `CONTEXT_NOTIFICATIONS.md`.
>
> **Estado hoy**: canal entero; motor (`CONTEXT_PUSH_MOTOR.md`) conectado al envío, pero `push_enabled` sigue en `False`. Lo único que manda un push hoy: **botón** de Settings.

**LA FRASE DE LA QUE SALE TODO: un push no se puede desavisar.** Quien se quema con dos noches de pitidos apaga los avisos para siempre: ahí no se pierde un aviso, se pierde el canal. Otro lado: **un push que no llegó NO es información perdida** — el dato sigue en la campana, donde vive; el push es un empujón, no el registro. Todo abajo elige el mismo error: perder un aviso antes que mandar uno de más.

## 1. El payload — tres claves y ni una más

`_PUSH_PAYLOAD_CLAVES`: `titulo`, `cuerpo`, `url`.

⚠ **NUNCA lleva montos, saldos ni nombres de banco**: se lee en la **pantalla bloqueada**, sin desbloquear, y lo ve cualquiera con el teléfono en la mano. El número va en la app; el aviso dice que hay algo para mirar.

⚠ **`url` va RELATIVA**: `_push_payload()` la rechaza si no empieza con `/`. El servidor no sabe su dirección pública (`cfg['ngrok_domain']` es hostname pelado; en DEV vacío); armarla sería adivinar y el aviso quedaría clavado al dominio de ese día. El service worker sí sabe de dónde salió.

## 2. El envío (`app.py`)

`_push_enviar(filas, payload, cfg, ttl)` manda con `pywebpush` → `(enviados, borradas)`. Validación VAPID **aparte**, en `_push_claves_vapid(cfg)`: el motor pregunta ANTES de guardar (§5b).

- **`_PUSH_TIMEOUT = 3` sí o sí**: sin `timeout`, `pywebpush` pasa `None` a `requests` (**sin límite**) y un FCM mudo dejaba el worker de Flask colgado para siempre. **`_PUSH_TOPE_TANDA = 10`** = techo de la tanda: timeout es POR teléfono, envíos de a uno (cuatro mudos = 20 s con el botón clavado en "Mandando...").
- **Dos TTL a propósito.** `_PUSH_TTL = 60` = **botón** (un "andá a Settings" que llega media hora después no sirve). `_PUSH_TTL_AVISO = 7200` (2 h) = **avisos automáticos**: aguanta el bache real (subte, notebook cerrada) sin cruzar la noche; con TTL largo el servicio de push entregaría a las 4 de la mañana algo que cuidamos de no mandar a esa hora. Vence con teléfono apagado → aviso perdido: ya marcado.
- **Un envío que falla no frena a los demás**: son teléfonos distintos.
- **404 / 410 = suscripción muerta** (app desinstalada, datos limpiados, buzón caducado): fila **se borra ahí mismo** — no va a andar nunca más, y dejarla hace que cada envío la reintente y pague el timeout. Otro error: se loguea, fila queda quieta.
- **VAPID ausentes o rotas** → `_PushSinClaves` → **503 que dice qué hacer**: config a medio hacer, no falla. Se valida UNA vez antes del bucle; adentro caía en el except de cada teléfono y mandaba a re-suscribir el celular por un problema del server.
- ⚠ **Nunca se loguea el endpoint ni la excepción cruda.** Endpoint = buzón de un teléfono; `requests` mete la URL completa en sus errores: un `{e}` pelado la filtraba en el caso más común, la red caída. Va `type(e).__name__`.

**Botón "Mandarme un aviso de prueba"** (`POST /api/push/prueba`) **no mira `push_enabled`, a propósito**: ese flag apaga los avisos *automáticos*; esto es el diagnóstico del canal — si lo respetara, para probarlo habría que encender antes lo que no se sabe si funciona. ⚠ **Hay DOS llamadores de `_push_enviar` y ni uno más** (botón y `_push_ciclo()`): los cuenta `TestUnSoloCaminoDeEnvio`, en `test_push_suscripciones.py`.

## 3. Service worker (`templates/sw.js`, mitad ACTIVO)

- `push` → **SIEMPRE llama a `showNotification()`**: si no, Chrome muestra *"Este sitio se actualizó en segundo plano"* y Safari da de baja la suscripción. Payload roto → muestra genérico igual.
- Recién **después**, `pushAvisarVentanas()` manda `{tipo:'push-recibido'}` a ventanas abiertas (`clients.matchAll` + `postMessage`); la campana se refresca sola. Sin eso, quien tiene la app abierta ve el aviso del sistema y adentro no hay nada hasta recargar. ⚠ Va **al final de la cadena, con su propio catch**: un `postMessage` que falla no puede tapar la notificación.
- `notificationclick` → `clients.matchAll()` enfoca ventana ya abierta; si no hay ninguna → `clients.openWindow(url)`.

## 4. Frontend (`window.Push` en `app.js`)

`estado()`, `activar()`, `desactivar()`, `prueba()`, `bajaYSeguir()`, `esIOS()`, `standalone()`; estilo de `window.Notif`. Al lado: listener de `navigator.serviceWorker` → `message` → `window.Notif.refrescar()` (defensivo: puede no haber SW ni `Notif`). ⚠ `tipo` se mira por **extensibilidad, no por desconfianza**: acá solo despacha el SW de este mismo origen. **No agregar chequeo de `evento.origin`**: los `MessageEvent` de `Client.postMessage()` llegan con `origin` vacío en Chrome; esa guarda no matchea nunca y deja la campana sin refrescar.

- **Nada pide permiso al cargar la página**: Chrome degrada a "prompt silencioso" al sitio que lo pide sin interacción, y en iOS `requestPermission()` fuera de un gesto real falla. Sale del click del botón de Settings, con **modal explicativo antes**: en iOS el permiso se pide **una sola vez por instalación**; revertir un "No permitir" = borrar el ícono de inicio y volver a agregarlo.
- UI en Settings (`CONTEXT_FRONTEND.md`); **el Inicio no se toca** (regla 7). **Las horas de silencio no tienen UI**: se editan en `config.json`, como `sw_enabled`. Menos superficie.

## 5. El motor automático — vive en su propio doc

Qué decide **cuándo** avisar (flanco, siembra, horas de silencio, topes, diferimiento): **`docs/CONTEXT_PUSH_MOTOR.md`**. Acá: el canal (qué viaja, cómo se manda, qué pasa del otro lado).

⚠ Hoy UN solo motor y UN solo botón; ambos entran por `_push_enviar()`. Cualquier tercer camino = por definición, avisos sin pasar por los frenos.

## Al modificar este dominio, actualizar:
- Sección 1 si cambian las claves del payload o la regla de que no viajan montos.
- Sección 2 si cambia el manejo del 410, los timeouts, los TTL o `_PushSinClaves`.
- Sección 3 o 4 si cambia el service worker o `window.Push`.
- El motor tiene su propio doc: `CONTEXT_PUSH_MOTOR.md`.
