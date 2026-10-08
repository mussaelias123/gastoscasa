# Contexto: Push — el motor automático (`_push_ciclo`)

> Leer junto con `CLAUDE.md` y `CONTEXT_PUSH.md` (payload, envío, service worker allá). Acá: qué decide **cuándo** avisar.
>
> **Estado hoy**: motor conectado al envío, `push_enabled` en `False` → no manda; decide y escribe `SECO: flanco push ...`. Cómo leer ese ensayo y qué mirar encendido: `CONTEXT_DEPLOY.md`.

**FRASE BASE: un push no se puede desavisar.** Quien se quema con dos noches de pitidos apaga avisos para siempre → no se pierde un aviso: se pierde el canal. Lo contrario: **push que no llegó NO es info perdida** — el dato sigue en la campana (donde vive). Todo abajo elige el mismo error: perder un aviso antes que mandar uno de más.

Hilo `push-scheduler` (`_scheduler_push`, vuelta cada `_PUSH_INTERVALO =
600` s, el `sleep` **al final** → la primera corre al arrancar). Decisión entera en `_push_ciclo(ahora)`; acepta la hora para testear con reloj congelado.

## 1. QUÉ se avisaría — igual encendido que apagado

- **Campana = NIVEL, push = FLANCO.** Providers contestan "¿hay algo?" cada vez que alguien mira; mientras la partida siga vencida contestan que sí para siempre → mandar eso = pitido cada 10 minutos. Se anuncia el **flanco ascendente**; cuando la señal se va no suena, no suena nada, queda **rearmada**. Flanco de PLC, marca de memoria en archivo.
- **Registry propio `PUSH_AVISOS`** (`(clave, provider)`), **separado de `NOTIF_PROVIDERS` a propósito**: no todo lo que merece puntito en campana merece despertar a alguien. `clave` prefija la de dedup (dos providers con mismo título no se pisan) y arrastra lo suyo.
- **Aviso = GRUPO**: `(provider, severidad, título)` → `"lactancia|peligro|Partida vencida"`; tres partidas vencidas = UN aviso. `cuerpo` = `modulo_nombre` o `"Lactancia · 3 avisos"`. Se arma **siempre con `_push_payload()`**, aun apagado → valida las 3 claves y la url.
- ⚠ **`detalle` NO entra ni en clave ni en cuerpo.** Clave no: hoy dice "vence en 3 días", mañana "en 2" → flanco ascendente falso por día, misma bolsita. Cuerpo no: ahí viaja el volumen en ml. El conteo `n` sí puede ir.
- ⚠ **"No contestó" NO es "ya no hay nada".** Si un provider falla (`database is locked` mientras alguien guarda un movimiento o `hacer_backup_db()` copia la base), sus claves se **arrastran** del estado anterior: borrarlas haría que al recuperarse las MISMAS cosas fueran flanco otra vez. Igual con payload que no se pudo armar → `(avisos, sin_payload, fallados)`.
- **Estado en `push_estado.json`**, en `_get_backup_dir()`, **no en `fondo.db` a propósito**: el detector de backups compara hash del dump lógico; estado en tabla = backup diario falso todos los días. Forma: `{"avisadas", "actualizado", "dia", "enviados_hoy", "ultima_tanda", "diferidas"}`, escritura **atómica** y solo si algo cambió. ⚠ Tolera archivo al que le falte cualquiera de las últimas cuatro (el del ensayo): se leen como "otro día" / "hace mucho" / "nada diferido" = default que deja andar.
- ⚠ **Primero se guarda, después se anuncia.** Al revés, guardado que falla deja estado viejo en disco y el mismo flanco se re-anuncia cada 10 min.
- **Siembra**: sin estado previo (ausente, corrupto o sin `avisadas`) → guardar set actual, **no anunciar nada** (bit de primer scan). Si no, cada reinicio trataría semanas de pendientes como recién aparecidas.
- Se marca **aunque el flag esté apagado** (si no, misma clave se reportaría cada 10 min). Se guardan claves **vigentes ahora**, nunca unión con las viejas: la unión = señal que se enclava y no se suelta.

## 2. SI sale — los frenos (solo con `push_enabled` en `True`)

- **Interruptor se lee EN CALIENTE** cada vuelta, por UNA puerta (`_push_encendido()`, único lugar que mira el flag). Apagado, camino **idéntico** hasta el último metro: solo no se manda (dos caminos = el probado 72 h no sería el que se enciende). ⚠ **Apagado los frenos NO actúan**: el ensayo mide frecuencia **bruta**.
- **Horas de silencio** (`push_silencio_desde`/`_hasta`, 22:30–07:00). ⚠ **Ventana CRUZA medianoche**: `hora >= desde` **O** `hora < hasta`. Escrita como `<=` entre dos números no silencia nunca; el bug se nota la primera noche. Dos horas iguales = **ventana vacía** (nunca hay silencio); para no recibir nada está `push_enabled`, que se ve.
- ⚠ **Hora se NORMALIZA al leer**: `strptime("7:00", "%H:%M")` no falla (`%H` acepta un dígito) y la comparación es de strings — sin normalizar, `"7:00"` daba `'22:30' < '7:00'` y la madrugada entera quedaba sin silencio.
- **Topes**: `_PUSH_TOPE_VUELTA = 3`, `_PUSH_TOPE_DIA = 8` (contador `enviados_hoy`, reset al cambiar `dia`). ⚠ Tope de vuelta = **por llamada, no por tiempo**; `_push_ciclo()` corre 1 vez por ARRANQUE de proceso → servicio reiniciando en loop mandaba 3+3+2 en sesenta segundos. Por eso `ultima_tanda`: si la última tanda salió hace menos de `_PUSH_INTERVALO`, se retiene. La marca dice cuándo **sonó un teléfono**, no cuándo corrió el hilo (si no, el motor se traba detrás de sus vueltas vacías).
- ⚠ **DIFERIMIENTO NO ES COLA, y es lo mejor del diseño**: lo retenido **no se marca** → sigue siendo flanco y la vuelta siguiente lo evalúa contra el nivel **real**. No hay pendientes que corromper. Consecuencia: **si la condición se fue durante la noche, el aviso nunca sale**. Lo guardado pasa a ser `vigentes - retenidas`.
- ⚠ **Trampa del diferimiento crónico.** Aviso cuya condición SOLO es cierta adentro del silencio → **nunca** sale. Caso real: `lactancia_recordatorio_hora` (campo de Settings) en 23:00 → recordatorio cierto de 23:00 a medianoche, se retiene, a las 07:00 ya no existe. Cero envíos, para siempre. Por eso el estado guarda `diferidas` (**puro diagnóstico**, no se manda nada): clave retenida en dos días distintos → `AVISO:` que dice desde cuándo y qué mirar.
- **VAPID rotas o ausentes** → no manda y **no marca**; por eso se pregunta ANTES de guardar. Si se marcaran, el estado consumiría en silencio los flancos mientras la config está rota, y el día que se arregle diría "ya avisé todo" sin que nunca hubiera sonado nada. Igual si no hay ningún dispositivo suscripto.
- **TTL se recorta contra arranque del silencio** (`_push_ttl_efectivo`): el freno actúa sobre el ENVÍO, y envío no es entrega. Aviso que sale 22:29 con 2 h de TTL y encuentra teléfono apagado → FCM lo entregaría 00:29, adentro de la ventana que existe para eso.
- **Se manda a TODAS las suscripciones**, sin filtrar por persona: es **decisión**, no descuido — casa de dos, y lo de hoy (leche que vence, bolsitas para bajar) les importa a los dos. El día que haya aviso de uno solo, se filtra ahí.
- ⚠ **Ningún tope es silencioso**: si se retiene algo, el log lo dice **con las claves**, en UNA línea después de todos los frenos (adentro de cada uno mentía: decía "salen 3" y un gate después vaciaba la tanda). Token de `_push_seco_decir()` lleva las claves → set nuevo de retenidas vuelve a hablar el mismo día; mismo set repetido 144 veces no.
- **Log**: vueltas sin novedad no loguean; queda latido de UNA línea por día con salud de providers (y no dice "sin flancos nuevos" si hubo retenidos). Apagado sale `SECO: flanco push ...`; encendido, `PUSH: aviso mandado ...` — o `PUSH: aviso SIN ENTREGAR ...` si no entró en ningún dispositivo, porque "mandado (entregado en 0)" se contradice solo.
- Tests: `test_push_scheduler.py` (flanco) y `test_push_encendido.py` (encendido y frenos). Sin esperar 72 h: `python TempScripts/simular_flancos_push.py` (seco por construcción: tiene `_push_enviar` parcheado, no manda ni con el flag prendido).

## Al modificar este dominio, actualizar:
- Sección 1 si cambia `PUSH_AVISOS`, clave de dedup, siembra o forma del estado.
- Sección 2 si se toca un freno — y el día que `push_enabled` pase a `True`, corregir "Estado hoy" del encabezado y el de `CONTEXT_PUSH.md`.
