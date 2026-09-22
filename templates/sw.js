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

  * ACTIVO (sw_enabled = True): el service worker de verdad. En esta etapa está
    VACÍO a propósito — sin fetch handler y sin precache — para poder probar el
    registro con cero en juego. El caché llega en la etapa siguiente.

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
// SERVICE WORKER REAL (sw_enabled = True). Etapa 2: VACÍO a propósito.
//
// Prendido y todo, este archivo no cachea nada ni intercepta nada. Sirve para
// probar los puntos de integración riesgosos (la ruta, el MIME, el login, el
// registro) sin poner nada en juego. El precache y la estrategia de red vienen
// en la etapa siguiente, y van ACÁ ABAJO — nunca en la mitad de la lápida.
var VERSION = '__VERSION__';

self.addEventListener('install', function () {
    // Tomar el control en cuanto se pueda, sin esperar a que se cierren las
    // pestañas viejas. Con un SW vacío no hay riesgo: no hay caché que mezclar.
    self.skipWaiting();
});

self.addEventListener('activate', function (evento) {
    evento.waitUntil(self.clients.claim());
});

// SIN fetch handler y SIN precache todavía (ver arriba).
// ==== FIN ACTIVO ====
