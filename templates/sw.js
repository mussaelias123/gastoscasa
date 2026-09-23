/* ============================================================================
ARCHIVO: templates/sw.js  —  Service Worker de Núcleo
============================================================================

OJO: ESTO NO ES UN TEMPLATE JINJA. Vive en templates/ pero la ruta `/sw.js`
de app.py lo lee como TEXTO PLANO (`open().read()`) y le reemplaza el marcador
`__VERSION__` a mano. NUNCA servirlo con `render_template()`:

  a. `render_template` dispara TODOS los context processors, incluido
     `inject_notif_badge`, que llama a `_notificaciones()` → los dos providers
     → varias queries + leer config.json. El navegador re-pide /sw.js en CADA
     navegación para ver si cambió, así que cada carga de página pagaría dos
     veces la cuenta de notificaciones.
  b. Jinja interpretaría cualquier `{{ }}` o `{# #}` que aparezca adentro del
     JavaScript. Hoy no hay ninguno; el día que alguien escriba un comentario
     con llaves, el archivo sale roto y el service worker no registra.

POR QUÉ VIVE EN templates/ Y NO EN static/: un service worker solo controla
las URLs que cuelgan de su propio path. Desde /static/sw.js el alcance máximo
sería /static/ y no controlaría NINGUNA página. Tiene que colgar de la raíz,
igual que el manifest, y por eso lo sirve una ruta. En templates/ además queda
afuera del `os.walk` de static/ que hace `_static_version()`... que igual lo
mira aparte, a propósito: si cambia este archivo, la versión se mueve.

EL ARCHIVO TIENE DOS MITADES y la ruta sirve UNA SOLA, según `sw_enabled` de
config.json (se cambia en caliente, sin reiniciar el servicio):

  * LÁPIDA (sw_enabled = False, el default de hoy): un service worker suicida.
    Borra TODAS las cachés, se desregistra y suelta el control. Existe porque
    un service worker NO se apaga borrando la ruta: el que ya quedó instalado
    en el teléfono sigue vivo, sirviendo código viejo, para siempre. La única
    desactivación que llega de verdad es servir un SW que se mate solo. Por eso
    la lápida se escribe ANTES de que exista algo peligroso que apagar.

  * ACTIVO (sw_enabled = True): el service worker de verdad. Precachea el
    esqueleto de la app (CSS, JS global y fuentes) y atiende UNA lista blanca:
    solo GET, solo de este origen, solo bajo /static/. Todo lo demás —las 13
    páginas, las 49 rutas /api/*, el manifest, el CSV— ni lo mira. El porqué
    de esa lista blanca está escrito adentro de la mitad ACTIVO: leerlo ANTES
    de tocar el fetch handler.

Las líneas `// ==== INICIO X ====` / `// ==== FIN X ====` son los marcadores
que corta `_sw_seccion()` en app.py. No borrarlas ni cambiarles el texto.
Este encabezado no se sirve nunca: queda afuera de los dos marcadores.
============================================================================ */


// ==== INICIO LAPIDA ====
// LÁPIDA — service worker suicida (sw_enabled = False).
// Versión de los estáticos: __VERSION__
//
// El número de versión va comentado acá adentro a propósito: el navegador solo
// vuelve a correr install/activate si los BYTES del archivo cambiaron. Sin él,
// un cambio de modo podría pasar desapercibido.

self.addEventListener('install', function () {
    // Sin `skipWaiting()` la lápida se quedaría esperando a que se cierren
    // todas las pestañas que controla el SW viejo — justo lo que no se puede
    // pedir cuando el SW viejo es el que está rompiendo la app.
    self.skipWaiting();
});

self.addEventListener('activate', function (evento) {
    evento.waitUntil(
        Promise.resolve()
            .then(function () {
                // `caches` no existe en navegadores viejos. Se pregunta con
                // `typeof` y no con `in`: acá adentro no hay `window`.
                if (typeof caches === 'undefined') return null;
                return caches.keys();
            })
            .then(function (nombres) {
                return Promise.all((nombres || []).map(function (nombre) {
                    return caches.delete(nombre);
                }));
            })
            // Una caché que no se deja borrar no puede frenar el desregistro:
            // desregistrarse es lo importante de las tres cosas.
            .catch(function () { })
            .then(function () { return self.registration.unregister(); })
            // `claim()` acá es cinturón y tirantes, no el que libera. Después
            // de `unregister()` el registro queda marcado como uninstalling y
            // reclamar clientes es no-op por spec. Lo que entrega de verdad las
            // pestañas es el `skipWaiting()` del install. Se deja porque es
            // inofensivo, pero que nadie construya encima suponiendo que hace
            // algo.
            .then(function () { return self.clients.claim(); })
            // Si `unregister()` rechaza, la lápida queda a medio morir: las
            // cachés ya se borraron pero el service worker sigue registrado, y
            // `activate` corre UNA sola vez por versión, así que no reintenta.
            // El respaldo de ese caso es `window.SW.barrer()`, que base.html
            // ejecuta en CADA carga mientras el flag está apagado. Si alguna
            // vez se saca ese barrido automático, este camino se queda sin red.
            .catch(function () { })
    );
});

// SIN fetch handler A PROPÓSITO. Un service worker sin fetch handler no
// intercepta ni una sola request: el navegador va derecho a la red, como si no
// existiera. Eso es lo que deja la app IDÉNTICA mientras el flag está apagado.
// ==== FIN LAPIDA ====


// ==== INICIO ACTIVO ====
// SERVICE WORKER REAL (sw_enabled = True).
//
// ┌──────────────────────────────────────────────────────────────────────────┐
// │ LA REGLA QUE MANDA:  SE CACHEA CÓDIGO, JAMÁS PLATA.                      │
// └──────────────────────────────────────────────────────────────────────────┘
//
// Las 13 páginas de esta app se arman EN EL SERVIDOR con los saldos YA ADENTRO
// del HTML (mirá `index()` y `gastos()` en app.py). O sea que un HTML cacheado
// ES un saldo cacheado. Y un saldo viejo se ve EXACTAMENTE IGUAL que uno
// fresco: no hay spinner, no hay fecha, no hay nada que le avise a nadie que
// está mirando la plata de ayer. Es lo peor que puede pasar en esta app.
//
// Por eso el fetch handler de abajo es una LISTA BLANCA y no una lista de
// excepciones: solo GET, solo de este origen, solo bajo /static/. Las páginas,
// las 49 rutas /api/*, /manifest.json (que lee la paleta en caliente), este
// mismo /sw.js, /login, /logout, /auth/* y el CSV de dia-a-dia quedan afuera
// POR CONSTRUCCIÓN — nadie tuvo que acordarse de excluirlos, y el endpoint 50
// que se escriba mañana nace protegido solo. Esa es la diferencia entre un
// cuidado y una garantía.
//
// ⚠ NO CONVERTIR ESTO EN LISTA NEGRA. Una lista negra ("todo menos /api/")
// protege lo que alguien se acordó de escribir; esta lista blanca protege lo
// que todavía no existe. Los tests de tests/test_sw.py congelan las tres
// guardas justamente para que el cambio no pueda pasar desapercibido.

var VERSION = '__VERSION__';

// EL NOMBRE DEL CACHÉ LLEVA LA VERSIÓN ADENTRO, y `activate` borra todo lo que
// no se llame así. Cambia un byte de cualquier archivo de static/ (o de este
// mismo archivo) → `_static_version()` se mueve → caché nuevo, y el viejo se
// tira ENTERO. Eso es lo que hace segura la parte de runtime: ahí se guardan
// cosas que se piden SIN `?v=` (las fuentes, el fondo de Lactancia), así que la
// frescura no la da la URL — la da el nombre del caché.
var CACHE = 'nucleo-v' + VERSION;

// PRECACHE — el esqueleto que usa TODA la app, bajado de entrada en `install`.
// Son ~460 KB y es lo que hace que la segunda carga no espere a la red.
//
// El CSS y el JS van CON `?v=`, y tiene que ser el MISMO string que emite
// base.html (`url_for('static', ...) ~ '?v=' ~ static_version`). Si no matchea
// letra por letra, el precache queda lleno de URLs que nadie pide y no sirve
// para NADA: la página pide otra clave y sale a la red igual. El test
// `test_el_precache_matchea_letra_por_letra` compara contra el HTML de verdad.
//
// Las fuentes van SIN query: las pide `style.css` con rutas relativas y sin
// `?v=`, y un service worker no parsea CSS. Van a mano y con la URL tal cual la
// pide el navegador; listadas con `?v=` pegado serían 4 entradas de peso muerto.
//
// LO QUE NO ESTÁ ACÁ, A PROPÓSITO:
//   · Los 3 PNG de static/img/ — no los pide la página, los pide el sistema
//     operativo al instalar la PWA, y a esa altura ya están instalados.
//   · El bundle de Rutina (rutina.js + los 3 rutina-*.js, ~255 KB),
//     lactancia.js, grafico.js, calendario.js, home.js, resumen.js y el
//     fondo-lactancia.jpg — entran solos al caché de runtime la primera vez
//     que se usan. Meterlos acá sería bajar 600 KB de módulos que capaz esa
//     persona no abre nunca.
var PRECACHE = [
    '/static/style.css?v=' + VERSION,
    '/static/app.js?v=' + VERSION,
    '/static/fonts/archivo-narrow-400.woff2',
    '/static/fonts/archivo-narrow-500.woff2',
    '/static/fonts/archivo-narrow-700.woff2',
    '/static/fonts/parisienne-400.woff2'
];


// ---------------------------------------------------------------------------
// Ayudantes. Los tres devuelven SIEMPRE una promesa y no tiran nunca.
//
// `caches` se pregunta con `typeof` y adentro de un `try`, igual que en
// `window.SW.barrer()` de app.js y por el mismo motivo: con el storage
// bloqueado (Chrome sin cookies, política de empresa) la propiedad existe pero
// LEERLA tira `SecurityError` sincrónico, que ningún `.catch` de promesa
// agarra. Sin caché disponible, todo esto se vuelve no-op y la app anda por
// red, exactamente como si no hubiera service worker.
// ---------------------------------------------------------------------------

function abrirCache() {
    try {
        if (typeof caches === 'undefined') return Promise.resolve(null);
        return caches.open(CACHE).catch(function () { return null; });
    } catch (e) {
        return Promise.resolve(null);
    }
}

function buscarEnCache(pedido) {
    return abrirCache().then(function (cache) {
        if (!cache) return null;
        // `match()` por defecto NO ignora el query string (`ignoreSearch` es
        // false por spec), y de eso depende TODO el esquema: `style.css?v=8` y
        // `style.css?v=9` son dos claves distintas, así que una versión nueva
        // es cache miss y sale a la red sola. Si alguien le pasa
        // `{ ignoreSearch: true }`, el `?v=` deja de servir para algo y la app
        // se queda pegada al CSS viejo hasta que cambie el nombre del caché.
        return cache.match(pedido).catch(function () { return null; });
    });
}

function guardar(evento, respuesta) {
    // Qué se guarda y qué no:
    //   · status 200 y nada más. Un 404 o un 500 guardado se serviría desde el
    //     caché para siempre (bueno: hasta el próximo cambio de versión), y el
    //     archivo quedaría roto aunque el servidor ya lo esté sirviendo bien.
    //     El 200 también deja afuera al 206 (Range), que `cache.put()` rechaza.
    //   · `type === 'basic'` = respuesta de nuestro propio origen. Deja afuera
    //     las opacas (`type === 'opaque'`, status 0: no se puede saber si
    //     salieron bien) y los `opaqueredirect`. Eso cubre un redirect a OTRO
    //     dominio metido en /static/, que llegaría como `cors`.
    //   · `redirected` cubre el caso que `basic` NO agarra: un 302 al MISMO
    //     origen. Con `redirect: 'follow'` (el default) el fetch sigue el salto
    //     y devuelve la respuesta final —status 200, type basic, pasa los dos
    //     filtros de arriba—, pero `cache.put()` usa como clave el pedido
    //     ORIGINAL. O sea: cuerpo del destino guardado bajo la clave /static/.
    //     Hoy es alcanzable: sin sesión, `GET /static/` (barra final, filename
    //     vacío) no matchea la regla de Flask, cae en el before_request de auth
    //     y redirige a /login — y el HTML del login quedaba cacheado como si
    //     fuera un estático. No filtraba plata, pero el mecanismo estaba vivo.
    if (!respuesta || respuesta.redirected
            || respuesta.status !== 200 || respuesta.type !== 'basic') return;
    try {
        // El clon se saca ANTES de devolver la respuesta: el cuerpo se puede
        // leer UNA sola vez, y el que la lee de verdad es el navegador.
        var copia = respuesta.clone();
        // `waitUntil` para que el navegador no mate el service worker en el
        // medio de la escritura: el `fetch` ya se contestó, y sin esto la
        // guardada se pierde justo en la primera visita, que es la que importa.
        evento.waitUntil(abrirCache().then(function (cache) {
            if (!cache) return null;
            return cache.put(evento.request, copia);
        }).catch(function () { }));
    } catch (e) { }
}


// ---------------------------------------------------------------------------
// install — precache
// ---------------------------------------------------------------------------

self.addEventListener('install', function (evento) {
    evento.waitUntil(abrirCache().then(function (cache) {
        if (!cache) return null;
        // DE A UNO Y TOLERANDO FALLAS, y NO `cache.addAll()`, que es
        // TODO-O-NADA: una sola URL que dé 404 —una fuente renombrada, un typo
        // en esta lista— tira abajo el install entero y NO QUEDA NADA
        // cacheado. Peor: el install fallido se reintenta en cada carga de
        // página, así que el error se repite para siempre y en silencio.
        // Así, si una entrada falla, las otras cinco quedan igual y la que
        // falta simplemente se pide por red cada vez, como hoy.
        return Promise.all(PRECACHE.map(function (url) {
            return cache.add(url).catch(function () { return null; });
        }));
    }).catch(function () { }));

    // SIN `skipWaiting()`, A PROPÓSITO — y esto NO es un olvido:
    //
    // Con formularios de plata a medio llenar, activar el service worker nuevo
    // abajo de una pestaña abierta significa mezclar CSS nuevo con JS viejo. Y
    // acá no hace falta: como el handler solo toca /static/ con `?v=`, una
    // versión nueva ya es cache miss y sale a la red sola. La pestaña abierta
    // recibe los archivos nuevos sin que el SW nuevo tome el control.
    //
    // ⚠ LA EXPECTATIVA, que es lo que se malinterpreta: el service worker
    // nuevo NO entra "en la próxima navegación". Se queda esperando hasta que
    // no quede NINGÚN cliente controlado — o sea, hasta cerrar TODAS las
    // pestañas del sitio (recargar no alcanza: la pestaña vieja sigue viva
    // mientras carga la nueva). Si ves que "el SW no se actualiza", es esto y
    // está bien. NO metas `skipWaiting()` por las apuradas. Para apagar YA hay
    // otro camino, que es el que se escribió para eso: `sw_enabled = false` en
    // config.json (la lápida) o el botón "Reparar app" de Settings.
});


// ---------------------------------------------------------------------------
// activate — tirar los cachés de versiones anteriores
// ---------------------------------------------------------------------------

self.addEventListener('activate', function (evento) {
    evento.waitUntil(
        Promise.resolve()
            .then(function () {
                if (typeof caches === 'undefined') return [];
                return caches.keys();
            })
            .then(function (nombres) {
                return Promise.all((nombres || []).map(function (nombre) {
                    // Se van MIS versiones viejas, y solo las mías. Sin esto,
                    // cada cambio de un archivo de static/ dejaría otro caché
                    // de ~460 KB tirado en el teléfono para siempre.
                    //
                    // El `indexOf` acota el barrido a los cachés de esta app: el
                    // Cache Storage es POR ORIGEN, no por service worker, así
                    // que sin ese filtro este activate le vaciaría el caché a
                    // cualquier otra cosa que algún día conviva en el mismo
                    // origen. Hoy no hay nada más, y justamente por eso conviene
                    // que la intención quede escrita antes de que la haya.
                    // (En la LÁPIDA es al revés: ahí se borra todo a propósito.)
                    if (nombre === CACHE || nombre.indexOf('nucleo-v') !== 0) return null;
                    return caches.delete(nombre);
                }));
            })
            .catch(function () { })
            // `claim()` toma las pestañas que ya estaban abiertas sin que haya
            // que recargarlas. No se pisa con lo de arriba: esto recién corre
            // cuando el SW nuevo YA está activo (o sea, cuando se cerraron
            // todas las pestañas), no adelanta esa activación.
            .then(function () { return self.clients.claim(); })
            .catch(function () { })
    );
});


// ---------------------------------------------------------------------------
// fetch — LISTA BLANCA (leer el bloque del principio antes de tocar esto)
// ---------------------------------------------------------------------------

self.addEventListener('fetch', function (evento) {
    var pedido = evento.request;

    // (a) SOLO GET. El alta de gastos, el borrado y unas 40 rutas
    //     /api/*/crear|editar|borrar son POST, y el Cache API TIRA EXCEPCIÓN
    //     con un pedido que no sea GET. Sin esta línea se rompe cargar un
    //     gasto, que es la función principal de la app.
    if (pedido.method !== 'GET') return;

    var url;
    try {
        url = new URL(pedido.url);
    } catch (e) {
        // Una URL que no se puede parsear no se toca: que la resuelva el
        // navegador como si el service worker no existiera.
        return;
    }

    // (b) SOLO NUESTRO ORIGEN. Mata de una el problema del CDN (flatpickr y
    //     chart.js vienen de jsdelivr, sin versión fija en la URL y con
    //     respuestas opacas que no se puede saber si salieron bien) y el
    //     avatar de Google del header.
    if (url.origin !== self.location.origin) return;

    // (c) SOLO /static/. Punto. Acá es donde quedan afuera las 13 páginas con
    //     los saldos adentro, las 49 rutas /api/*, /manifest.json, /sw.js,
    //     /login, /logout, /auth/* y el CSV. No hay lista de excepciones que
    //     mantener: lo que no cuelga de /static/ no entra.
    if (url.pathname.indexOf('/static/') !== 0) return;

    // (d) NINGUNA NAVEGACIÓN, nunca. Hoy esto es redundante —una navegación a
    //     una página no cae bajo /static/ y ya se fue en (c)—, y se deja igual
    //     porque es la regla escrita en un renglón: si alguien alguna vez
    //     aflojara la guarda de arriba, las páginas con la plata adentro
    //     siguen sin poder entrar al caché.
    if (pedido.mode === 'navigate') return;

    // (e) NADA CON `Range`. `cache.match()` ignora ese header: si el archivo ya
    //     está guardado entero como 200, un pedido parcial recibiría el 200
    //     completo, sin `Content-Range`, y un <video> o <audio> se rompe al
    //     buscar. Hoy no hay media bajo /static/, pero la regla de
    //     mantenimiento dice que todo estático nuevo entra a runtime SOLO: el
    //     día que alguien suba un .mp4 no tiene que acordarse de esto.
    if (pedido.headers && pedido.headers.get && pedido.headers.get('range')) return;

    evento.respondWith(responder(evento));
});


// CACHE-FIRST contra la URL COMPLETA (con query string). Es la estrategia
// correcta para esto y solo para esto: todo lo que llega acá es /static/ y se
// pide con `?v=` (o está congelado, como las fuentes), así que lo que está en
// el caché es, por definición, la versión que la página está pidiendo.
function responder(evento) {
    return buscarEnCache(evento.request).then(function (guardada) {
        if (guardada) return guardada;
        return fetch(evento.request).then(function (respuesta) {
            guardar(evento, respuesta);
            return respuesta;
        });
    });
    // SIN `.catch` final a propósito: si no hay nada en el caché y el `fetch`
    // falla (sin conexión), la promesa rechaza y el navegador muestra el mismo
    // error de red que mostraría sin service worker. Inventar acá una
    // respuesta de error sería PEOR: la página la tomaría por buena y
    // guardaría, por ejemplo, un style.css vacío.
}
// ---------------------------------------------------------------------------
// push — el aviso que llega con la app CERRADA
// ---------------------------------------------------------------------------
//
// ┌───────────────────────────────────────────────────────────────────────┐
// │ LA REGLA DE ESTE BLOQUE:  EL AVISO NUNCA LLEVA PLATA.                    │
// └───────────────────────────────────────────────────────────────────────┘
//
// Es la misma regla que la del caché, un paso más afuera. Un push se lee en la
// PANTALLA BLOQUEADA: sin desbloquear el teléfono, sin sesión, y lo ve
// cualquiera que esté cerca. Así que el payload no lleva montos, ni saldos, ni
// nombres de banco, ni de quién es la cuenta. Lleva el QUÉ y un LINK; la plata
// se mira adentro de la app, con sesión. Del lado del servidor eso lo arma
// `_push_payload()` (app.py), que solo deja pasar tres claves — y se escribe
// también acá, que es donde el texto termina en la pantalla de alguien.
//
// ⚠ SIEMPRE SE MUESTRA ALGO. `showNotification()` no es opcional ni "si el
// payload vino bien":
//   · Chrome: si el handler termina sin mostrar nada, la muestra ÉL, con el
//     texto "Este sitio se actualizó en segundo plano". Un aviso que no
//     escribimos, que no dice nada, y que encima parece un bug.
//   · Safari / iOS: abusar del push silencioso hace que el navegador DÉ DE
//     BAJA la suscripción. O sea que el olvido se paga con el canal entero,
//     y en el teléfono que más cuesta volver a suscribir.
// Por eso el parseo va adentro de un try y el catch NO corta: si el payload
// viene vacío, roto o no es JSON, se cae al texto genérico y se muestra igual.

var PUSH_TITULO = 'Núcleo';
var PUSH_CUERPO = 'Tenés un aviso.';


// El payload del evento, con default para CADA campo. Nunca tira.
function pushDatos(evento) {
    var datos = { titulo: PUSH_TITULO, cuerpo: PUSH_CUERPO, url: '/' };
    try {
        if (!evento || !evento.data) return datos;
        // `.json()` tira si el cuerpo no es JSON (un texto suelto, un byte
        // perdido). Cae en el catch y se muestra el genérico.
        var crudo = evento.data.json();
        if (!crudo || typeof crudo !== 'object') return datos;
        if (typeof crudo.titulo === 'string' && crudo.titulo) datos.titulo = crudo.titulo;
        if (typeof crudo.cuerpo === 'string' && crudo.cuerpo) datos.cuerpo = crudo.cuerpo;
        if (typeof crudo.url === 'string' && crudo.url) datos.url = crudo.url;
    } catch (e) { }
    return datos;
}


// LA URL DEL PAYLOAD ES RELATIVA (`/lactancia`) Y SE RESUELVE ACÁ, contra el
// origen del propio service worker. No es un detalle de estilo:
//
//   a. El servidor no sabe su propia dirección pública. `cfg["ngrok_domain"]`
//      es un hostname pelado (sin esquema) y en DEV está vacío; armar la
//      absoluta allá sería adivinar. El SW, en cambio, SABE de dónde salió.
//   b. El mismo aviso sirve en localhost y en el dominio de ngrok, sin
//      reescribir nada y sin quedar pegado al dominio de ayer.
//
// Y de paso es una guarda: una URL de OTRO origen (un payload armado por
// alguien que consiguió firmar, un copy-paste con dominio adentro) no abre
// nada afuera — cae a la raíz de esta app.
function pushDestino(url) {
    var base = self.location.origin;
    try {
        var u = new URL(url, base);
        return u.origin === base ? u.href : base + '/';
    } catch (e) {
        return base + '/';
    }
}


// Avisarle a las pestañas ABIERTAS que llegó un push, para que la campana se
// actualice sola. Sin esto, alguien que tiene la app abierta ve la
// notificación del sistema y adentro de la app sigue sin haber nada hasta que
// recargue — el aviso y el dato contradiciéndose en la misma pantalla.
//
// ⚠ ESTO NO PUEDE METERSE EN EL CAMINO DE `showNotification()`. Va COLGADO AL
// FINAL de la cadena, después del último `.catch`, y encapsulado en el suyo
// propio: mostrar la notificación es obligatorio (ver el ⚠ de arriba), y un
// `postMessage` que falla —una pestaña que se cerró justo, un cliente que no
// acepta mensajes— no puede ser el motivo por el que Chrome muestre "Este
// sitio se actualizó en segundo plano".
//
// `includeUncontrolled: true` por lo mismo que en `notificationclick`: este SW
// no hace `skipWaiting()`, así que las pestañas abiertas las puede estar
// controlando la versión anterior y sin el flag no aparecerían en la lista.
function pushAvisarVentanas() {
    try {
        if (!self.clients || !self.clients.matchAll) return null;
        return self.clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then(function (lista) {
                var ventanas = lista || [];
                for (var i = 0; i < ventanas.length; i++) {
                    // Uno por uno adentro del try: una pestaña muerta no
                    // puede dejar sin avisar a las demás.
                    try { ventanas[i].postMessage({ tipo: 'push-recibido' }); } catch (e) { }
                }
                return null;
            })['catch'](function () { return null; });
    } catch (e) {
        return null;
    }
}


self.addEventListener('push', function (evento) {
    var datos = pushDatos(evento);
    var destino = pushDestino(datos.url);
    evento.waitUntil(
        self.registration.showNotification(datos.titulo, {
            body: datos.cuerpo,
            icon: '/static/img/icon-192.png',
            badge: '/static/img/icon-192.png',
            // Lo único que viaja al click. Va la URL YA RESUELTA: el que la
            // validó fue este handler, y al `notificationclick` le llega el
            // trabajo hecho.
            data: { url: destino }
        }).catch(function () {
            // Si la versión con íconos falla (un PNG que no está, una opción
            // que ese navegador no banca), se muestra la pelada. Mostrar algo
            // es obligatorio: ver el ⚠ de arriba.
            return self.registration.showNotification(PUSH_TITULO, { body: PUSH_CUERPO });
        }).catch(function () { }).then(pushAvisarVentanas)
    );
});


// ---------------------------------------------------------------------------
// notificationclick — abrir la app donde corresponde
// ---------------------------------------------------------------------------
//
// SE ENFOCA UNA VENTANA QUE YA ESTÉ ABIERTA antes de abrir otra. Sin esto,
// cada aviso tocado deja una pestaña más de la misma app dando vueltas en el
// teléfono.
//
// `includeUncontrolled: true` NO es decorativo: este SW no hace
// `skipWaiting()`, así que las pestañas abiertas las puede estar controlando
// la versión ANTERIOR. Sin ese flag no aparecerían en la lista y el click
// abriría una ventana nueva al lado de la que ya estaba.

self.addEventListener('notificationclick', function (evento) {
    // Primero cerrar: en Android la notificación queda pegada en la barra si
    // no se la cierra a mano.
    evento.notification.close();

    var datos = evento.notification.data || {};
    var destino = pushDestino(datos.url || '/');

    evento.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then(function (lista) {
                var ventanas = lista || [];
                for (var i = 0; i < ventanas.length; i++) {
                    var cliente = ventanas[i];
                    var propia = false;
                    try {
                        propia = new URL(cliente.url).origin === self.location.origin;
                    } catch (e) { }
                    if (!propia) continue;
                    if (cliente.url === destino) return cliente.focus();
                    // `navigate()` solo anda si esa ventana la controla ESTE
                    // service worker; si no, rechaza. Ahí se la enfoca igual:
                    // mejor la app abierta en otra pantalla que una pestaña
                    // nueva de más.
                    if (!cliente.navigate) return cliente.focus();
                    return cliente.navigate(destino).then(function (c) {
                        return (c || cliente).focus();
                    }).catch(function () { return cliente.focus(); });
                }
                if (self.clients.openWindow) return self.clients.openWindow(destino);
                return null;
            })
            .catch(function () { })
    );
});

// ==== FIN ACTIVO ====
