# Contexto: Push — el motor automático (`_push_ciclo`)

> Leer junto con `CLAUDE.md` y `CONTEXT_PUSH.md` (el payload, el envío y el
> service worker viven allá). Acá está lo que decide **cuándo** avisar.
>
> **Estado hoy**: el motor está conectado al envío pero `push_enabled` sigue en
> `False`, así que no manda: decide y escribe `SECO: flanco push ...`. Cómo se
> lee ese ensayo, y qué mirar una vez encendido, en `CONTEXT_DEPLOY.md`.

**LA FRASE DE LA QUE SALE TODO: un push no se puede desavisar.** El que se
quema con dos noches de pitidos apaga los avisos para siempre, y ahí no se
pierde un aviso: se pierde el canal. El otro lado: **un push que no llegó NO es
información perdida** — el dato sigue en la campana, que es donde vive. Todo lo
de abajo elige el mismo error: perder un aviso antes que mandar uno de más.

Hilo `push-scheduler` (`_scheduler_push`, una vuelta cada `_PUSH_INTERVALO =
600` s, el `sleep` **al final** para que la primera corra al arrancar). La
decisión entera vive en `_push_ciclo(ahora)`, que acepta la hora para poder
testearla con el reloj congelado.

## 1. QUÉ se avisaría — igual encendido que apagado

- **La campana es un NIVEL, el push es un FLANCO.** Los providers contestan
  "¿hay algo?" cada vez que alguien mira, y mientras la partida siga vencida
  contestan que sí para siempre: mandar eso sería un pitido cada 10 minutos. Se
  anuncia el **flanco ascendente**; cuando la señal se va no suena nada pero
  queda **rearmada**. Es flanco de PLC, con la marca de memoria en un archivo.
- **Registry propio `PUSH_AVISOS`** (`(clave, provider)`), **separado de
  `NOTIF_PROVIDERS` a propósito**: no todo lo que merece un puntito en la
  campana merece despertar a alguien. La `clave` prefija la de dedup para que
  dos providers con el mismo título no se pisen, y para arrastrar lo suyo.
- **Un aviso es un GRUPO**: `(provider, severidad, título)` →
  `"lactancia|peligro|Partida vencida"`; tres partidas vencidas son UN aviso.
  `cuerpo` = `modulo_nombre` o `"Lactancia · 3 avisos"`. Se arma **siempre con
  `_push_payload()`**, aun apagado, para validar las 3 claves y la url.
- ⚠ **`detalle` NO entra ni en la clave ni en el cuerpo.** En la clave no,
  porque hoy dice "vence en 3 días" y mañana "en 2": flanco ascendente falso
  por día, para la misma bolsita. En el cuerpo no, porque ahí viaja el volumen
  en ml. El conteo `n` sí puede ir.
- ⚠ **"No contestó" NO es "ya no hay nada".** Si un provider falla (`database
  is locked` mientras alguien guarda un movimiento o `hacer_backup_db()` copia
  la base), sus claves se **arrastran** del estado anterior: borrarlas haría
  que al recuperarse las MISMAS cosas fueran flanco otra vez. Igual con un
  payload que no se pudo armar — de ahí `(avisos, sin_payload, fallados)`.
- **Estado en `push_estado.json`**, dentro de `_get_backup_dir()` y **no en
  `fondo.db` a propósito**: el detector de backups compara el hash del dump
  lógico, y un estado en una tabla haría un backup diario falso todos los días.
  Forma: `{"avisadas", "actualizado", "dia", "enviados_hoy", "ultima_tanda",
  "diferidas"}`, escritura **atómica** y solo si algo cambió. ⚠ Tolera un
  archivo al que le falte cualquiera de las últimas cuatro (el del ensayo): se
  leen como "otro día" / "hace mucho" / "nada diferido", que es el default que
  deja andar.
- ⚠ **Primero se guarda, después se anuncia.** Al revés, un guardado que falla
  deja el estado viejo en disco y el mismo flanco se re-anuncia cada 10 min.
- **Siembra**: sin estado previo (ausente, corrupto o sin `avisadas`) se guarda
  el set actual y **no se anuncia nada** — el bit de primer scan. Si no, cada
  reinicio trataría semanas de pendientes como recién aparecidas.
- Se marca **aunque el flag esté apagado** (si no, la misma clave se reportaría
  cada 10 min), y se guardan las claves **vigentes ahora**, nunca la unión con
  las viejas: la unión sería una señal que se enclava y no se suelta más.

## 2. SI sale — los frenos (solo con `push_enabled` en `True`)

- **El interruptor se lee EN CALIENTE** en cada vuelta, y por UNA sola puerta
  (`_push_encendido()`, el único lugar del programa que mira el flag).
  Apagado, el camino es **idéntico** hasta el último metro: solo no se manda —
  si fueran dos caminos, el que se probó 72 h no sería el que se enciende. ⚠
  **Apagado los frenos NO actúan**: el ensayo mide la frecuencia **bruta**.
- **Horas de silencio** (`push_silencio_desde`/`_hasta`, 22:30–07:00). ⚠ **La
  ventana cruza la medianoche**: es `hora >= desde` **O** `hora < hasta`.
  Escrita como un `<=` entre dos números no silencia nunca, y el bug se nota
  recién la primera noche. Las dos horas iguales = **ventana vacía** (nunca hay
  silencio); para no recibir nada está `push_enabled`, que se ve.
  ⚠ **La hora se NORMALIZA al leerla**: `strptime("7:00", "%H:%M")` no falla
  (`%H` acepta un dígito), y la comparación es de strings — sin normalizar,
  `"7:00"` daba `'22:30' < '7:00'` y la madrugada entera quedaba sin silencio.
- **Topes**: `_PUSH_TOPE_VUELTA = 3` y `_PUSH_TOPE_DIA = 8` (contador
  `enviados_hoy`, se resetea al cambiar `dia`). ⚠ El de la vuelta es **por
  llamada, no por tiempo**, y `_push_ciclo()` corre una vez por ARRANQUE de
  proceso: un servicio que reinicia en loop mandaba 3+3+2 en sesenta segundos.
  Por eso está `ultima_tanda` — si la última tanda salió hace menos de
  `_PUSH_INTERVALO`, se retiene. La marca dice cuándo **sonó un teléfono**, no
  cuándo corrió el hilo (si no, el motor se traba detrás de sus vueltas vacías).
- ⚠ **EL DIFERIMIENTO NO ES UNA COLA, y es lo mejor del diseño**: lo retenido
  **no se marca**, así que sigue siendo flanco y la vuelta siguiente lo evalúa
  contra el nivel **real**. No hay pendientes que se puedan corromper.
  Consecuencia: **si la condición se fue durante la noche, el aviso nunca
  sale**. Lo guardado pasa a ser `vigentes - retenidas`.
- ⚠ **La trampa del diferimiento crónico.** Un aviso cuya condición SOLO es
  cierta adentro del silencio no sale **nunca**. Caso real: si
  `lactancia_recordatorio_hora` (un campo de Settings) se pone en 23:00, ese
  recordatorio es cierto de 23:00 a medianoche, se retiene, y a las 07:00 ya no
  existe. Cero envíos, para siempre. Por eso el estado guarda `diferidas`
  (**puro diagnóstico**, de ahí no se manda nada): una clave retenida en dos
  días distintos saca un `AVISO:` que dice desde cuándo y qué mirar.
- **VAPID rotas o ausentes** → no se manda y **no se marca**; por eso se
  pregunta ANTES de guardar. Si se marcaran, el estado consumiría en silencio
  los flancos mientras la config está rota y el día que se arregle el motor
  diría "ya avisé todo" sin que nunca hubiera sonado nada. Igual si no hay
  ningún dispositivo suscripto.
- **El TTL se recorta contra el arranque del silencio** (`_push_ttl_efectivo`):
  el freno actúa sobre el ENVÍO y el envío no es la entrega. Un aviso que sale
  22:29 con 2 h de TTL y encuentra el teléfono apagado lo entregaría FCM a las
  00:29, adentro de la ventana que existe para eso.
- **Se le manda a TODAS las suscripciones**, sin filtrar por persona: es una
  **decisión**, no un descuido — es una casa de dos y lo de hoy (leche que
  vence, bolsitas para bajar) le importa a los dos. El día que haya un aviso de
  uno solo, se filtra ahí.
- ⚠ **Ningún tope es silencioso**: si se retiene algo el log lo dice, **con las
  claves**, en UNA línea después de todos los frenos (adentro de cada uno
  mentía: decía "salen 3" y después un gate vaciaba la tanda). El token de
  `_push_seco_decir()` lleva las claves, así que un set nuevo de retenidas
  vuelve a hablar el mismo día y el mismo set repetido 144 veces no.
- **Log**: las vueltas sin novedad no loguean; queda un latido de UNA línea por
  día con la salud de los providers (y no dice "sin flancos nuevos" si hubo
  retenidos). Apagado sale `SECO: flanco push ...`; encendido,
  `PUSH: aviso mandado ...` — o `PUSH: aviso SIN ENTREGAR ...` si no entró en
  ningún dispositivo, porque "mandado (entregado en 0)" se contradice solo.
- Tests: `test_push_scheduler.py` (el flanco) y `test_push_encendido.py` (el
  encendido y los frenos). Sin esperar 72 h:
  `python TempScripts/simular_flancos_push.py` (seco por construcción: tiene
  `_push_enviar` parcheado, así que no manda ni con el flag prendido).

## Al modificar este dominio, actualizar:
- Sección 1 si cambia `PUSH_AVISOS`, la clave de dedup, la siembra o la forma
  del estado.
- Sección 2 si se toca un freno — y el día que `push_enabled` pase a `True`,
  corregir el "Estado hoy" del encabezado y el de `CONTEXT_PUSH.md`.
