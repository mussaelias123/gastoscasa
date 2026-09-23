# Contexto: Push (aviso al teléfono con la app cerrada)

> Leer junto con `CLAUDE.md`. Canal **aparte** de la campana: la campana es
> *pull* (se evalúa cuando alguien la mira), el push es *report by exception*
> (el servidor empuja). Para la campana, ver `CONTEXT_NOTIFICATIONS.md`.
>
> **Estado hoy**: lo único que **manda** un push es un **botón**. Ya hay un
> scheduler corriendo solo, pero está **en seco**: decide cuándo avisaría y lo
> escribe en el log. `push_enabled` sigue apagado.

## 1. El payload — tres claves y ni una más

`_PUSH_PAYLOAD_CLAVES` en `app.py`: `titulo`, `cuerpo`, `url`.

⚠ **REGLA: el payload NUNCA lleva montos, saldos ni nombres de banco.** Un aviso
se lee en la **pantalla bloqueada**, sin desbloquear el teléfono, y lo ve
cualquiera que lo tenga en la mano. El número va adentro de la app; el aviso
dice que hay algo para mirar.

⚠ **La `url` va RELATIVA** (`/lactancia`, `/settings`), y `_push_payload()` lo
rechaza si no empieza con `/`. El servidor no sabe su propia dirección pública:
`cfg['ngrok_domain']` es un hostname pelado, sin esquema, y en DEV está vacío.
Armar la absoluta sería adivinar, y el aviso quedaría clavado al dominio que
había el día que se escribió. El service worker sí sabe de dónde salió.

## 2. El envío (`app.py`)

`_push_payload()` arma el JSON; `_push_enviar(filas, payload)` lo manda con
`pywebpush` y devuelve `(enviados, borradas)`.

- **`_PUSH_TIMEOUT = 3` va sí o sí.** `pywebpush` sin `timeout` explícito se lo
  pasa a `requests` como `None`, o sea **sin límite**: un FCM que no contesta
  dejaba el worker de Flask colgado para siempre.
- **`_PUSH_TOPE_TANDA = 10`** es el techo de la tanda entera (el timeout es POR
  teléfono, y los envíos van de a uno: cuatro dispositivos mudos eran 20 s con
  el botón clavado en "Mandando...").
- **Un envío que falla no frena a los demás**: son teléfonos distintos.
- **404 / 410 = suscripción muerta** (app desinstalada, datos del navegador
  limpiados, buzón caducado). Esa fila **se borra ahí mismo**: no va a funcionar
  nunca más, y dejarla hace que cada envío futuro la reintente, pague el timeout
  y ensucie el log para siempre. Cualquier otro error se loguea y la fila queda
  quieta — eso puede andar la próxima.
- **Faltan las claves VAPID (o están rotas)** → `_PushSinClaves` → **503 con
  un mensaje que dice qué hacer**: es una config a medio hacer, no una falla.
  Se valida UNA vez antes del bucle; adentro caía en el except de cada teléfono
  y mandaba a re-suscribir el celular por un problema del server.
- ⚠ **Nunca se loguea el endpoint ni la excepción cruda.** Un endpoint es el
  buzón de un teléfono: quien lo tiene le puede mandar avisos a ese aparato. Y
  `requests` mete la URL completa adentro del texto de sus errores, así que un
  `{e}` pelado filtraba el endpoint justo en el caso más común (la red caída).
  Va `type(e).__name__`.

**El botón "Mandarme un aviso de prueba"** (`POST /api/push/prueba`) **no mira
`push_enabled`, a propósito**: ese flag apaga los avisos *automáticos*, y esto
es el diagnóstico del canal. Si lo respetara, para probarlo habría que encender
antes la cosa que uno todavía no sabe si funciona. Es lo único que separa "el
canal no anda" de "no hay nada que avisar".

## 3. Service worker (`templates/sw.js`, mitad ACTIVO)

- `push` → **SIEMPRE llama a `showNotification()`**, sin excepción. Si no,
  Chrome muestra *"Este sitio se actualizó en segundo plano"* y Safari da de
  baja la suscripción si se abusa del silencio. Con el payload roto o vacío,
  muestra un texto genérico igual.
- `notificationclick` → `clients.matchAll()` para enfocar una ventana del sitio
  que ya esté abierta; si no hay ninguna, `clients.openWindow(url)`.

## 4. Frontend (`window.Push` en `app.js`)

`estado()`, `activar()`, `desactivar()`, `prueba()`, `bajaYSeguir()`, `esIOS()`,
`standalone()`. Mismo estilo que `window.Notif`.

- **Nada pide permiso al cargar la página.** Chrome degrada a "prompt
  silencioso" a los sitios que lo piden sin interacción, y en iOS
  `requestPermission()` fuera de un gesto real falla. Solo desde el click del
  botón de Settings, y con un **modal explicativo antes** — en iOS el permiso
  se pide **una sola vez por instalación**, y revertir un "No permitir" ahí es
  borrar el ícono de la pantalla de inicio y volver a agregarlo.
- La UI vive en la tarjeta de Settings (`CONTEXT_FRONTEND.md`). **El Inicio no
  se toca** (regla 7).

## 5. El scheduler EN SECO (detector de flancos)

Hilo `push-scheduler` (`_scheduler_push`, una vuelta cada
`_PUSH_INTERVALO = 600` s, el `sleep` **al final** para que la primera corra al
arrancar). **No manda nada**: no llama a `_push_enviar()` ni lee la tabla de
suscripciones. Loguea `SECO: flanco push ...` lo que mandaría, para medir la
frecuencia real antes de que un teléfono suene (el ensayo: `CONTEXT_DEPLOY.md`).

- **La campana es un NIVEL, el push es un FLANCO.** Los providers contestan
  "¿hay algo?" cada vez que alguien mira: mientras la partida siga vencida
  contestan que sí para siempre, y mandar eso sería un pitido cada 10 minutos.
  Se anuncia el **flanco ascendente** (una clave que la vuelta anterior no
  estaba). Cuando la señal se va no suena nada, pero queda **rearmada**.
  Detección de flanco de PLC con la marca de memoria en un archivo.
- **Registry propio `PUSH_AVISOS`** (lista de `(clave, provider)`), **separado
  de `NOTIF_PROVIDERS` a propósito**: no todo lo que merece un puntito en la
  campana merece despertar a alguien. Un provider entra con una línea
  explícita. La `clave` prefija la clave de dedup para que dos providers con
  el mismo título y severidad no se pisen — **y para poder arrastrar lo suyo
  cuando falla** (ver abajo).
- **Un aviso es un GRUPO**, no un ítem: se agrupan por
  `(provider, severidad, título)` → clave `"lactancia|peligro|Partida vencida"`.
  Tres partidas vencidas son UN aviso (el payload no lleva detalle: tres pushes
  iguales con el mismo link no agregan nada). `cuerpo` = `modulo_nombre`, o
  `"Lactancia · 3 avisos"`. El aviso se arma **siempre con `_push_payload()`**,
  aun en seco, para que se validen las 3 claves y la url relativa.
- ⚠ **`detalle` NO entra ni en la clave ni en el cuerpo.** En la clave no,
  porque dice "vence en 3 días" y mañana "vence en 2 días": sería un flanco
  ascendente falso por día, para la misma bolsita. En el cuerpo no, porque
  ahí viaja el volumen en ml y el cuerpo se lee en la pantalla bloqueada. El
  conteo `n` sí puede ir en el cuerpo (no es plata, y el cuerpo no forma parte
  de la clave).
- ⚠ **"No contestó" NO es "ya no hay nada".** Si un provider falla (`database
  is locked` mientras alguien guarda un movimiento o mientras
  `hacer_backup_db()` copia la base), sus claves se **arrastran** del estado
  anterior en vez de caerse. Si se borraran, al recuperarse las MISMAS cosas
  volverían a ser flanco ascendente: en seco infla el número que se va a leer
  para decidir si esto se enciende; encendido, es un teléfono sonando por algo
  de lo que ya avisó. Lo mismo con un aviso cuyo payload no se pudo armar: el
  nivel está alto igual. `_push_avisos_ahora()` devuelve
  `(avisos, sin_payload, fallados)` justo para esto.
- **Estado en `push_estado.json`** (`_push_estado_leer/_guardar`), dentro de
  `_get_backup_dir()`. **No va en `fondo.db` a propósito**: el detector de
  backups compara el hash del dump lógico, así que un estado en una tabla haría
  un backup diario falso todos los días. Forma:
  `{"avisadas": [claves...], "actualizado": ISO}`. Escritura **atómica**
  (`.tmp` + `os.replace`) y solo si el set cambió.
- ⚠ **Primero se guarda, después se anuncia.** Al revés, un guardado que falla
  deja el estado viejo en disco y el mismo flanco se re-anuncia cada 10 minutos
  para siempre — y un push no se puede desavisar. En este orden lo peor que
  pasa es perder un aviso, que es el lado barato: el dato sigue estando en la
  campana. **Un push que no llegó no es información perdida.**
- **Siembra**: sin estado previo (archivo ausente, corrupto o sin `avisadas`)
  se guarda el set actual y **no se anuncia nada**. Es el bit de primer scan:
  si no, cada reinicio trataría semanas de pendientes como recién aparecidos.
- Se marcan como avisadas **aunque estemos en seco** (si no, la misma clave se
  reportaría cada 10 min y el log no diría nada), y se guardan las claves
  **vigentes ahora**, nunca la unión con las viejas (la unión sería una señal
  que se enclava y no se suelta más).
- **Volumen del log**: 144 vueltas por día. Las vueltas sin novedad no loguean;
  queda un latido de UNA línea por día con la salud de los providers. Todo lo
  que se repite (provider roto, estado que no se puede guardar) pasa por
  `_push_seco_decir(token, ...)`, que dice cada cosa una vez por día.
- Tests: `tests/test_push_scheduler.py`. Para verlo andar sin esperar 72 h:
  `python TempScripts/simular_flancos_push.py`.

## Al modificar este dominio, actualizar:
- Sección 1 si cambian las claves del payload o la regla de que no viajan montos.
- Sección 2 si cambia el manejo del 410, los timeouts o `_PushSinClaves`.
- Sección 5 si cambia el registry `PUSH_AVISOS`, la clave de dedup, la siembra
  o dónde vive el estado — y **el día que se encienda de verdad** (ahí deja de
  ser "en seco" y empieza a leer `push_enabled`).
