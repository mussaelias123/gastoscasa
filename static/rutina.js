/*
================================================================================
ARCHIVO: static/rutina.js
================================================================================
Lógica cliente del módulo Rutina. Se carga SOLO en /rutina
(templates/rutina.html, bloque scripts). Vanilla JS, sin librerías. Todo vive
dentro de una IIFE para no pisar los globales de app.js.

FUENTE DE VERDAD (todo del servidor; acá NO hay rutinas hardcodeadas):
  - window.RUT_DATOS = { miembros, actividades, config, ajustes, duraciones,
    tareas, ocultos, calendario, hoy, desde, hasta }, persistido en SQLite +
    config.json y sincronizado entre ambos teléfonos.
      miembros    = la familia (tabla rutina_miembros), con edad y cumpleaños
                    ya derivados por el backend. El id manda: un "usuario" de
                    la UI es String(miembro.id).
      actividades = actividades con su frecuencia (tabla rutina_actividades).
                    Ítems de horario fijo, id 'a<id>', editables, NO entran en
                    la cascada. Una compartida es UN ítem que aparece en la
                    línea de todos sus participantes.
      config      = hora de inicio de noche/amanecer y el interruptor de la
                    tarjeta de cumpleaños (config.json).
      ajustes[fecha][etapa][item_id] = inicioEnMinutos (tabla rutina_ajustes)
      tareas      = tareas añadidas (tabla rutina_tareas; fecha '' =
                    permanente), id 'c-<rowid>'.
      ocultos     = ítems quitados (tabla rutina_ocultos; fecha '' =
                    permanente). Un ítem del bebé quitado sale de la cadena
                    ANTES de la cascada.
  - window.RutinaSueno (static/rutina-sueno.js): la tabla de ventanas de sueño
    por edad y el motor que GENERA la rutina de un bebé — siestas, tomas y
    despertares nocturnos — anclada en su primera toma del día. Es lo que
    reemplazó a la vieja constante ETAPAS (las tres etapas fijas escritas a
    mano para León, que caducaban solas).
  - window.RUTINA_ACTIVIDADES (static/rutina-actividades.js): 82 actividades
    de estimulación de la guía "Estimulación Temprana" (Karina Rivera).
  - localStorage 'rutina-ui-v1' = { sel, dia, sec }: selección de UI por
    dispositivo (NO se sincroniza; decisión de diseño). `sel` está tecleado
    por id de miembro.

MENÚ (mismo patrón que Lactancia): secciones Hoy / Familia / Actividades /
Ajustes. El wrapper lleva data-rut-sec y en mobile el CSS muestra solo la
sección activa. Desde Familia se cargan los miembros (con su fecha de
nacimiento y, si es bebé, la hora de su primera toma).

MODO EDICIÓN ("✎ Editar" en el header del timeline): cada fila muestra ✕
(quitar, preguntando "¿solo hoy o siempre?"), aparece "＋ Añadir tarea" (form
inline: persona, emoji, título, hora, duración, alcance) y al pie la lista de
tareas quitadas con ↩ Restaurar. Mutaciones no-optimistas (payload fresco).

REGLA DE CASCADA (solo la cadena generada del bebé): ajustar un ítem NO mueve
los anteriores; los siguientes sin ajuste propio se re-encadenan (inicio = fin
del anterior). Un ítem con ajuste propio queda clavado hasta que se resetee
("↺ Plan original" borra todos los ajustes del día y devuelve lo generado).

MUTACIONES — optimistic con debounce: cada tap de −15/+15 escribe local y
re-renderiza al instante; el POST /api/rutina/ajustar sale debounced (400 ms
por ítem: una ráfaga de taps = un solo POST, último valor gana). La respuesta
trae el payload completo del rango visible y reemplaza AJUSTES (solo si no
quedan cambios locales en vuelo). Si el POST falla (offline), el valor local
queda y se avisa discreto en #rut-aviso — sin toasts (los ajustes son
inmediatos y reversibles).

RELOJ VIVO: re-render cada 30 s (mueve el resaltado "ahora" y las barras de
progreso) + GET del rango para traer ajustes hechos desde el otro teléfono.
La fila "Sueño nocturno" queda activa desde su inicio hasta las 05:00 (cruza
la medianoche). FECHAS: siempre locales armadas a mano (isoLocal) — nunca
toISOString(), que corre a UTC y cambia de día después de las 21:00 ART.
================================================================================
*/

(function () {
    'use strict';

    // ── Identidad: la familia sale de la base, no de constantes ─────────────
    // Acá vivía la constante ETAPAS: la rutina de León escrita a mano para "2
    // meses" más las agendas completas de mamá y papá, y las tres etapas fijas
    // ('actual' / 'tres' / 'guarderia'). Todo eso caducaba solo y no se podía
    // editar sin tocar código. Ahora:
    //   · los miembros salen de rutina_miembros  → RUT_DATOS.miembros
    //   · la rutina de un bebé la GENERA window.RutinaSueno según su edad
    //   · las actividades salen de rutina_actividades → RUT_DATOS.actividades
    //
    // Un "usuario" de la UI (UI.sel, item.user, data-user) es el id del miembro
    // pasado a string: '3'. Los ids de ítem derivan de ahí: 'b3-siesta1'
    // (generado del bebé) y 'a17' (actividad cargada).

    // La columna `etapa` de las tablas de ajustes sobrevive por compatibilidad
    // con las filas viejas; todo lo que escribe este front usa 'plan'.
    var ETAPA = 'plan';
    var LS_KEY = 'rutina-ui-v1';

    // ── Estado del módulo ────────────────────────────────────────────────────
    var RUT = window.RUT_DATOS || { ajustes: {}, hoy: '', desde: '', hasta: '' };
    var AJUSTES = RUT.ajustes || {};       // fecha → etapa → item_id → min (server)
    var DURACIONES = RUT.duraciones || {}; // fecha → etapa → item_id → dur (drag Teams)
    var TAREAS = RUT.tareas || [];         // tareas añadidas (rutina_tareas, server)
    var OCULTOS = RUT.ocultos || [];       // ítems quitados (rutina_ocultos, server)
    var CALHOY = RUT.calendario || [];     // actividades del Calendario que vencen HOY
    var MIEMBROS = RUT.miembros || [];     // la familia (rutina_miembros, con edad)
    var ACTIVIDADES = RUT.actividades || [];  // actividades con frecuencia (rutina_actividades)
    var CFG = RUT.config || {};            // hora de noche/amanecer, cumples (config.json)
    var DESDE = RUT.desde || '';
    var HASTA = RUT.hasta || '';
    var UI = cargarUI();                   // { sel, dia, sec } — por dispositivo
    var editando = null;                   // item_id con editor inline abierto
    var timers = {};                       // item_id → timeout del POST debounced
    var enVuelo = 0;                       // POSTs en curso
    var sinSync = false;                   // último POST/GET falló (offline)
    var modoEdicion = false;               // "✎ Editar": muestra ✕ / añadir / restaurar
    var quitando = null;                   // item_id con el "¿solo hoy o siempre?" abierto
    var formAdd = null;                    // estado del form "＋ Añadir tarea" (null = cerrado)
    var formMiembro = null;                // estado del form de familia (null = cerrado)
    var drag = null;                       // drag en curso (mover/estirar, estilo Teams)
    var seArrastro = false;                // suprime el click fantasma tras un drag
    var ahoraHora = null;                  // item_id con el editor "empezó a las…" abierto

    function $(id) { return document.getElementById(id); }

    function cargarUI() {
        var g = {};
        try { g = JSON.parse(localStorage.getItem(LS_KEY) || '{}'); } catch (e) {}
        // Solo la selección de personas es preferencia persistida. El día
        // arranca SIEMPRE en hoy: al entrar se ve la rutina del día corriente
        // en vivo, no el último que se haya mirado.
        // La selección guardada por la versión vieja estaba tecleada por
        // 'leon'/'mama'/'papa'; ahora la clave es el id del miembro, así que
        // esos valores se descartan y se arranca con todos visibles.
        var sel = g.sel && typeof g.sel === 'object' ? g.sel : null;
        if (sel && (sel.leon !== undefined || sel.mama !== undefined || sel.papa !== undefined)) {
            sel = null;
        }
        return {
            sel: sel || {},
            dia: new Date().getDay(),
            sec: 'hoy'          // sección visible del menú (mobile)
        };
    }

    function persistirUI() {
        try { localStorage.setItem(LS_KEY, JSON.stringify(UI)); } catch (e) {}
    }

    // ── La familia ───────────────────────────────────────────────────────────
    // Un "usuario" es siempre el id del miembro como string.

    function usuarios() {
        return MIEMBROS.map(function (m) { return String(m.id); });
    }

    function miembroDe(u) {
        var clave = String(u);
        for (var i = 0; i < MIEMBROS.length; i++) {
            if (String(MIEMBROS[i].id) === clave) return MIEMBROS[i];
        }
        return null;
    }

    function nombreDe(u) {
        var m = miembroDe(u);
        return m ? m.nombre : '';
    }

    // Hasta que existan los dibujos propios (PR de visuales), cada miembro se
    // identifica con un emoji según su rol; si el usuario cargó uno, gana el suyo.
    var EMOJI_ROL = { mama: '💜', papa: '💙', hijo: '🧒', otro: '🙂' };

    function emojiDe(u) {
        var m = miembroDe(u);
        if (!m) return '🙂';
        if (m.dibujo) return m.dibujo;
        if (m.es_bebe) return '🍼';
        return EMOJI_ROL[m.rol] || '🙂';
    }

    // Color identificador. El token lo valida el backend contra _RUT_COLORES,
    // así que se puede inyectar como valor de custom property sin riesgo. Si el
    // miembro no tiene color propio, se reparte uno de la paleta por posición.
    var COLOR_CICLO = ['persona-leon', 'persona-mari', 'persona-elias',
                       'rut-p4', 'rut-p5', 'rut-p6', 'rut-p7', 'rut-p8'];

    function colorTokenDe(u) {
        var m = miembroDe(u);
        if (!m) return 'persona-leon';
        if (m.color_token) return m.color_token;
        var idx = MIEMBROS.indexOf(m);
        return COLOR_CICLO[(idx < 0 ? 0 : idx) % COLOR_CICLO.length];
    }

    // Atributo style listo para pegar en el HTML: fija --rut-color, que es la
    // variable que consumen todos los estilos del módulo (dot, borde, barra,
    // tinte). Antes lo fijaban las clases .rut--leon / .rut--mama / .rut--papa,
    // que no servían con una familia de tamaño variable.
    function styleColor(u) {
        return ' style="--rut-color: var(--color-' + colorTokenDe(u) + ')"';
    }

    function usuariosSel() {
        return usuarios().filter(function (u) { return UI.sel[u]; });
    }

    // Un miembro recién cargado arranca visible. Lo que el usuario apagó a mano
    // queda apagado (UI.sel se persiste por dispositivo).
    function normalizarSeleccion() {
        usuarios().forEach(function (u) {
            if (UI.sel[u] === undefined) UI.sel[u] = true;
        });
    }

    function bebes() {
        return MIEMBROS.filter(function (m) { return m.es_bebe; });
    }

    // Hora de inicio de la noche (config): tope del día para el motor de sueño.
    function nocheMin() {
        return typeof CFG.noche_min === 'number' ? CFG.noche_min : 1200;
    }

    // ── Fechas y formato ─────────────────────────────────────────────────────
    // SIEMPRE fecha local armada a mano (nunca toISOString → corre a UTC).
    function isoLocal(d) {
        var m = String(d.getMonth() + 1).padStart(2, '0');
        var dia = String(d.getDate()).padStart(2, '0');
        return d.getFullYear() + '-' + m + '-' + dia;
    }

    // Fecha concreta del día visible: hoy + (día seleccionado − día de hoy),
    // siempre dentro de la semana calendario actual (domingo..sábado).
    function fechaVista() {
        var hoy = new Date();
        var f = new Date(hoy);
        f.setDate(hoy.getDate() + (UI.dia - hoy.getDay()));
        return f;
    }

    function esFinde() { return UI.dia === 0 || UI.dia === 6; }

    function ahoraMin() {
        var d = new Date();
        return d.getHours() * 60 + d.getMinutes();
    }

    // minutos → 'HH:MM' con módulo 1440 (las nocturnas cruzan la medianoche)
    function fmt(min) {
        var m = ((min % 1440) + 1440) % 1440;
        return String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0');
    }

    // "45′" | "1 h 30′" | "9 h 40′" | "" si dur = 0
    function fmtDur(dur) {
        if (!dur) return '';
        if (dur >= 60) return Math.floor(dur / 60) + ' h' + (dur % 60 ? ' ' + (dur % 60) + '′' : '');
        return dur + '′';
    }

    // Semana calendario del cliente (domingo..sábado), para el rango del server
    function semanaCliente() {
        var hoy = new Date();
        var d0 = new Date(hoy);
        d0.setDate(hoy.getDate() - hoy.getDay());
        var d6 = new Date(d0);
        d6.setDate(d0.getDate() + 6);
        return { desde: isoLocal(d0), hasta: isoLocal(d6) };
    }

    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // ── Ajustes (capa de acceso al dict anidado del server) ──────────────────
    function ajustesDia() {
        var fecha = isoLocal(fechaVista());
        return (AJUSTES[fecha] || {})[ETAPA] || {};
    }

    function duracionesDia() {
        var fecha = isoLocal(fechaVista());
        return (DURACIONES[fecha] || {})[ETAPA] || {};
    }

    function hayPendientes() {
        return enVuelo > 0 || Object.keys(timers).length > 0;
    }

    // Ítems quitados que aplican al día visible: los permanentes (fecha '')
    // y los de la fecha exacta. Devuelve un set { item_id: true }.
    function ocultosVista() {
        var fecha = isoLocal(fechaVista());
        var set = {};
        OCULTOS.forEach(function (o) {
            if (o.etapa === ETAPA && (o.fecha === '' || o.fecha === fecha)) set[o.item_id] = true;
        });
        return set;
    }

    // Resuelve solapes en una línea de tiempo: dos actividades de la MISMA
    // persona nunca ocurren a la vez. Recorre en orden de inicio; los links
    // PUROS (atados a León: tetas/upa/paseo, no editables) son barreras
    // inamovibles — son la misma actividad que la de León y no pueden correrse;
    // el resto (cadena de León, clocks, customs) se empuja hacia adelante lo
    // justo para no pisar ni al anterior ni a un link fijo. Los ítems de dur 0
    // ("A dormir"/"Sueño nocturno") no ocupan lugar y se dejan como están.
    // Muta start/end en el lugar. Pedido de Mari 2026-07-13.
    function sinSolapes(items) {
        var arr = items.filter(function (i) { return i.dur > 0; })
                       .sort(function (a, b) { return a.start - b.start; });
        var fijos = arr.filter(function (i) { return !i.editable; })
                       .map(function (i) { return { s: i.start, e: i.end }; });
        var cursor = -Infinity;
        arr.forEach(function (it) {
            if (!it.editable) { cursor = Math.max(cursor, it.end); return; }
            var s = Math.max(it.start, cursor);
            var choco = true, vueltas = 0;
            while (choco && vueltas++ < 50) {
                choco = false;
                fijos.forEach(function (f) {
                    if (s < f.e && s + it.dur > f.s) { s = f.e; choco = true; }
                });
            }
            it.start = s;
            it.end = s + it.dur;
            cursor = it.end;
        });
        return items;
    }

    // ── Frecuencia de una actividad ─────────────────────────────────────────
    // Tres capas que se combinan, más los recesos:
    //   1. días de la semana  (dias:  '1111100' = L a V, lunes primero)
    //   2. meses del año      (meses: '111111111111', enero primero)
    //   3. rango de fechas    (desde/hasta; anual = compara solo día y mes)
    //   − recesos             (pausas: sub-rangos donde NO va, también anuales)
    // Para faltar un día suelto (un feriado) está rutina_ocultos con fecha, que
    // se resuelve aparte en ocultosVista().
    function actividadAplica(act, f) {
        if (!act.activo) return false;

        // getDay(): domingo = 0. La grilla de la UI arranca en lunes.
        var idxDia = (f.getDay() + 6) % 7;
        if ((act.dias || '1111111').charAt(idxDia) !== '1') return false;
        if ((act.meses || '111111111111').charAt(f.getMonth()) !== '1') return false;

        var iso = isoLocal(f);
        if (act.anual) {
            if (!dentroAnual(iso, act.desde, act.hasta)) return false;
        } else {
            if (act.desde && iso < act.desde) return false;
            if (act.hasta && iso > act.hasta) return false;
        }

        var pausas = act.pausas || [];
        for (var i = 0; i < pausas.length; i++) {
            var p = pausas[i];
            if (p.anual ? dentroAnual(iso, p.desde, p.hasta)
                        : (iso >= p.desde && iso <= p.hasta)) return false;
        }
        return true;
    }

    // Comparación por día y mes, ignorando el año: así "escuela del 1/3 al
    // 15/12" revive sola cada año. Si el rango cruza el año nuevo (ej. 1/12 a
    // 28/2, una temporada de verano), vale estar en cualquiera de las dos puntas.
    function dentroAnual(iso, desde, hasta) {
        if (!desde && !hasta) return true;
        var dm = iso.slice(5);
        var d = (desde || '01-01').slice(5);
        var h = (hasta || '12-31').slice(5);
        return (d <= h) ? (dm >= d && dm <= h) : (dm >= d || dm <= h);
    }

    // ── Cálculo del día ──────────────────────────────────────────────────────
    // Para cada miembro se arma su línea de tiempo:
    //   · BEBÉ  → la genera window.RutinaSueno con su edad, su ancla (primera
    //     toma del día) y la hora de inicio de la noche. Es una CADENA: cascada
    //     run = ancla; start = ajuste ?? run; end = start + dur; run = end. Un
    //     ítem quitado sale ANTES de la cascada y los siguientes se re-encadenan.
    //     Las tomas nocturnas van aparte: start = inicio de la noche + off.
    //   · RESTO → sus actividades (horario fijo, editable) + las tareas añadidas.
    // Una actividad compartida aparece en la línea de TODOS sus participantes,
    // pero es UN solo ítem ('a<id>'): moverla desde cualquiera la mueve en todas.
    // Devuelve { porUser, quitados, bebe } — `bebe` es el primer bebé visible,
    // el que manda en la tarjeta de tips y en la franja de madrugada.
    function calcular() {
        var aj = ajustesDia();
        var dd = duracionesDia();   // duraciones estiradas (drag estilo Teams)
        var ocultos = ocultosVista();
        var quitados = [];
        var fecha = isoLocal(fechaVista());
        var fv = fechaVista();

        // Actividad de estimulación del día (rota con la fecha, estable en el día)
        var A = window.RUTINA_ACTIVIDADES || { m2: [], m3: [], m46: [] };
        var seed = Math.floor(fv.getTime() / 86400000);

        function poolDe(m) {
            var meses = m.mes_de_vida || 1;
            if (meses <= 2) return A.m2 || [];
            if (meses === 3) return A.m3 || [];
            return A.m46 || [];
        }

        // — Rutina generada de un bebé —
        function rutinaBebe(m) {
            var u = String(m.id);
            if (!window.RutinaSueno || typeof m.dias !== 'number') {
                return { items: [], noct: [] };
            }
            var plan = window.RutinaSueno.generar({
                miembroId: m.id,
                edadDias: m.dias,
                anclaMin: m.ancla_min,
                nocheMin: nocheMin()
            });

            var pool = poolDe(m);
            var slot = 0;
            var cadena = plan.dia.filter(function (it) {
                if (!ocultos[it.id]) return true;
                quitados.push({ id: it.id, emoji: it.emoji, t: it.t, user: u });
                return false;
            });

            var run = m.ancla_min;
            var items = [];
            cadena.forEach(function (it) {
                // Clamp: un ajuste nunca arranca antes de que termine el anterior
                // (la cadena del bebé no se solapa consigo misma).
                var start = (aj[it.id] !== undefined) ? Math.max(aj[it.id], run) : run;
                var dur = (it.dur && dd[it.id] !== undefined) ? dd[it.id] : it.dur;
                var sub = it.sub;
                if (it.act && pool.length) {
                    var a = pool[(seed * 3 + slot * 7) % pool.length];
                    sub = '✨ ' + a.n + ' (' + a.d + ', ' + a.min + '): ' + a.p;
                    slot++;
                }
                items.push(Object.assign({}, it, {
                    sub: sub, dur: dur, start: start, end: start + dur,
                    user: u, editable: true
                }));
                run = start + dur;
            });

            var noche = items[items.length - 1];
            var noct = [];
            (plan.nocturnas || []).forEach(function (n) {
                if (ocultos[n.id]) {
                    quitados.push({ id: n.id, emoji: n.emoji, t: n.t, user: u });
                    return;
                }
                var start = (aj[n.id] !== undefined) ? aj[n.id] : (noche ? noche.start : 0) + n.off;
                noct.push(Object.assign({}, n, {
                    dur: 25, start: start, end: start + 25,
                    user: u, kind: 'noct', editable: true
                }));
            });
            return { items: items, noct: noct, resumen: plan.resumen };
        }

        // — Actividades cargadas (rutina_actividades) —
        // Se listan para el dueño y para cada participante extra. El emoji/dibujo
        // es input del usuario: se escapa acá, UNA vez (el render lo inserta crudo).
        function actividadesDe(u) {
            var out = [];
            ACTIVIDADES.forEach(function (act) {
                var suyo = String(act.miembro_id) === u ||
                    (act.participantes || []).some(function (p) { return String(p) === u; });
                if (!suyo || !actividadAplica(act, fv)) return;
                var aid = 'a' + act.id;
                var emoji = escapeHtml(act.dibujo) || '📌';
                if (ocultos[aid]) {
                    quitados.push({ id: aid, emoji: emoji, t: act.titulo, user: u });
                    return;
                }
                var start = (aj[aid] !== undefined) ? aj[aid] : act.inicio_min;
                var dur = (dd[aid] !== undefined) ? dd[aid] : act.dur_min;
                var compartida = (act.participantes || []).length > 0;
                out.push({
                    id: aid, actividadId: act.id, emoji: emoji, t: act.titulo,
                    sub: act.nota || (compartida ? 'compartida' : ''),
                    start: start, end: start + dur, dur: dur,
                    user: u, kind: 'act', compartida: compartida, editable: true
                });
            });
            return out;
        }

        // — Tareas añadidas por el usuario (rutina_tareas, id 'c-<rowid>') —
        function tareasDe(u) {
            var out = [];
            TAREAS.forEach(function (t) {
                if (String(t.usuario) !== u) return;
                if (t.fecha !== '' && t.fecha !== fecha) return;
                var cid = 'c-' + t.id;
                var emoji = escapeHtml(t.emoji) || '📌';
                if (ocultos[cid]) {
                    quitados.push({ id: cid, emoji: emoji, t: t.titulo, user: u });
                    return;
                }
                var start = (aj[cid] !== undefined) ? aj[cid] : t.inicio_min;
                var durT = (dd[cid] !== undefined) ? dd[cid] : t.dur;
                out.push({
                    id: cid, tareaId: t.id, permanente: t.fecha === '', custom: true,
                    emoji: emoji, t: t.titulo, sub: t.fecha === '' ? '' : 'solo hoy',
                    start: start, end: start + durT, dur: durT,
                    user: u, kind: 'custom', editable: true
                });
            });
            return out;
        }

        function porInicio(a, b) { return a.start - b.start; }

        var porUser = {};
        var bebe = null;
        MIEMBROS.forEach(function (m) {
            var u = String(m.id);
            var propios = [];
            if (m.es_bebe) {
                var r = rutinaBebe(m);
                propios = r.items.concat(r.noct);
                if (!bebe) bebe = { miembro: m, resumen: r.resumen };
            }
            propios = propios.concat(actividadesDe(u)).concat(tareasDe(u));
            porUser[u] = sinSolapes(propios).sort(porInicio);
        });

        return { porUser: porUser, quitados: quitados, bebe: bebe };
    }

    // Todos los ítems del día, de toda la familia (para buscar uno por id).
    function todosLosItems(calc) {
        var out = [];
        usuarios().forEach(function (u) {
            out = out.concat(calc.porUser[u] || []);
        });
        return out;
    }

    // ── Mutaciones (optimistic + debounce; el server guarda por fecha) ──────
    function ajustar(itemId, min) {
        min = Math.max(0, min);
        var fecha = isoLocal(fechaVista());
        if (!AJUSTES[fecha]) AJUSTES[fecha] = {};
        if (!AJUSTES[fecha][ETAPA]) AJUSTES[fecha][ETAPA] = {};
        AJUSTES[fecha][ETAPA][itemId] = min;
        renderTodo();

        if (timers[itemId]) clearTimeout(timers[itemId]);
        timers[itemId] = setTimeout(function () {
            delete timers[itemId];
            var valor = ((AJUSTES[fecha] || {})[ETAPA] || {})[itemId];
            if (valor === undefined) return;   // el día se reseteó mientras tanto
            postAccion('/api/rutina/ajustar', {
                fecha: fecha, etapa: ETAPA, item_id: itemId, inicio_min: valor
            });
        }, 400);
    }

    // Estirar/encoger (drag estilo Teams): mismo esquema optimista+debounce
    // que ajustar(), con clave de timer propia ('d:' + id).
    function ajustarDur(itemId, durMin) {
        durMin = Math.max(5, Math.min(720, durMin));
        var fecha = isoLocal(fechaVista());
        if (!DURACIONES[fecha]) DURACIONES[fecha] = {};
        if (!DURACIONES[fecha][ETAPA]) DURACIONES[fecha][ETAPA] = {};
        DURACIONES[fecha][ETAPA][itemId] = durMin;
        renderTodo();

        var clave = 'd:' + itemId;
        if (timers[clave]) clearTimeout(timers[clave]);
        timers[clave] = setTimeout(function () {
            delete timers[clave];
            var valor = ((DURACIONES[fecha] || {})[ETAPA] || {})[itemId];
            if (valor === undefined) return;   // el día se reseteó mientras tanto
            postAccion('/api/rutina/duracion', {
                fecha: fecha, etapa: ETAPA, item_id: itemId, dur_min: valor
            });
        }, 400);
    }

    // "Empezó a tal hora": la actividad actual arrancó a la hora T (ahora, o
    // una que Mari elija). Pone su inicio en T y hace que la ANTERIOR termine
    // ahí (se acorta/estira hasta T) — así reflejan la realidad sin pisarse.
    // Los siguientes se re-encadenan solos. Pedido de Mari 2026-07-13.
    function empezoALas(curId, T) {
        T = Math.max(0, T);
        // La "anterior" es la anterior DE ESA MISMA PERSONA: estirar la de otro
        // miembro no tendría sentido.
        var calc = calcular();
        var duenio = null;
        todosLosItems(calc).forEach(function (i) {
            if (!duenio && i.id === curId) duenio = String(i.user);
        });
        if (!duenio) return;
        var lista = calc.porUser[duenio] || [];
        var idx = -1;
        lista.forEach(function (i, k) { if (i.id === curId) idx = k; });
        if (idx < 0) return;
        var prev = null;
        for (var j = idx - 1; j >= 0; j--) {
            if (lista[j].dur > 0) { prev = lista[j]; break; }
        }
        if (prev) T = Math.max(T, prev.start + 5);   // dejarle algo al anterior
        ajustar(curId, T);
        if (prev && prev.editable && prev.start < T) {
            ajustarDur(prev.id, T - prev.start);
        }
    }

    // "Termina a tal hora": ajusta la duración para que el fin caiga en T
    // (el inicio no se mueve). Los siguientes se re-encadenan.
    function terminaALas(curId, T) {
        var it = null;
        todosLosItems(calcular()).forEach(function (i) { if (i.id === curId) it = i; });
        if (!it) return;
        ajustarDur(curId, Math.max(5, T - it.start));
    }

    function resetDia() {
        var fecha = isoLocal(fechaVista());
        if (AJUSTES[fecha]) delete AJUSTES[fecha][ETAPA];
        if (DURACIONES[fecha]) delete DURACIONES[fecha][ETAPA];
        editando = null;
        ahoraHora = null;
        renderTodo();
        postAccion('/api/rutina/reset', { fecha: fecha, etapa: ETAPA });
    }

    // ── Mutaciones del modo edición (no-optimistas: mandan y esperan el
    //    payload fresco; son acciones poco frecuentes) ─────────────────────────
    function ocultarItem(itemId, fecha) {
        quitando = null;
        postAccion('/api/rutina/ocultar', { etapa: ETAPA, item_id: itemId, fecha: fecha });
    }

    function borrarTarea(tareaId) {
        quitando = null;
        postAccion('/api/rutina/tarea/borrar', { id: tareaId });
    }

    function restaurarItem(itemId) {
        postAccion('/api/rutina/restaurar', { etapa: ETAPA, item_id: itemId });
    }

    function crearTarea(datos) {
        formAdd = null;
        postAccion('/api/rutina/tarea/crear', datos);
    }

    // POST con el contrato del backend: responde el payload completo del rango.
    // Si falla (offline), el valor local queda y se avisa discreto (sin toasts).
    function postAccion(url, campos) {
        var rango = semanaCliente();
        var params = new URLSearchParams(campos);
        params.set('desde', rango.desde);
        params.set('hasta', rango.hasta);
        enVuelo++;
        fetch(url, {
            method: 'POST',
            body: params,
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(function (res) {
            return res.json().then(
                function (data) { return data; },
                function () { throw new Error('HTTP ' + res.status); }
            );
        })
        .then(function (data) {
            if (!data.ok) throw new Error(data.error || 'Error del servidor');
            sinSync = false;
            enVuelo--;
            // No pisar cambios locales que todavía no salieron
            if (!hayPendientes()) {
                AJUSTES = data.ajustes || {};
                DURACIONES = data.duraciones || {};
                DESDE = data.desde;
                HASTA = data.hasta;
            }
            // Tareas/ocultos/calendario no tienen edición local: siempre frescos
            if (data.tareas) TAREAS = data.tareas;
            if (data.ocultos) OCULTOS = data.ocultos;
            if (data.calendario) CALHOY = data.calendario;
            // La familia, sus actividades y las preferencias no tienen edición
            // local optimista: siempre se toma lo del servidor.
            if (data.miembros) MIEMBROS = data.miembros;
            if (data.actividades) ACTIVIDADES = data.actividades;
            if (data.config) CFG = data.config;
            renderTodo();
        })
        .catch(function (err) {
            enVuelo--;
            sinSync = true;
            console.error('Error AJAX rutina:', err);
            renderTodo();
        });
    }

    // GET del rango (tick de 30 s): trae ajustes hechos desde el otro teléfono.
    function syncAjustes() {
        if (document.hidden || hayPendientes()) return;
        var rango = semanaCliente();
        fetch('/api/rutina?desde=' + rango.desde + '&hasta=' + rango.hasta, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (!data.ok) return;
            sinSync = false;
            if (!hayPendientes()) {
                AJUSTES = data.ajustes || {};
                DURACIONES = data.duraciones || {};
                DESDE = data.desde;
                HASTA = data.hasta;
            }
            if (data.tareas) TAREAS = data.tareas;
            if (data.ocultos) OCULTOS = data.ocultos;
            if (data.calendario) CALHOY = data.calendario;
            // La familia, sus actividades y las preferencias no tienen edición
            // local optimista: siempre se toma lo del servidor.
            if (data.miembros) MIEMBROS = data.miembros;
            if (data.actividades) ACTIVIDADES = data.actividades;
            if (data.config) CFG = data.config;
        })
        .catch(function () { /* offline: el reloj sigue con estado local */ })
        .finally(function () { renderTodo(); });
    }

    // ── Render ───────────────────────────────────────────────────────────────
    // El encabezado muestra la fecha y, si hay un bebé cargado, su nombre y su
    // edad (que es lo que manda en toda su rutina). Sin bebé, muestra cuántos
    // son en la familia.
    function renderHeader() {
        $('rut-fecha').textContent = new Date().toLocaleDateString('es-AR',
            { weekday: 'long', day: 'numeric', month: 'long' });
        var nombre = $('rut-header-nombre');
        var edad = $('rut-edad');
        if (!nombre || !edad) return;

        var b = bebes()[0];
        if (b) {
            nombre.textContent = emojiDe(b.id) + ' ' + b.nombre;
            edad.textContent = b.edad_texto || '';
        } else if (MIEMBROS.length) {
            nombre.textContent = '👪 Familia';
            edad.textContent = MIEMBROS.length +
                (MIEMBROS.length === 1 ? ' integrante' : ' integrantes');
        } else {
            nombre.textContent = '👪 Familia';
            edad.textContent = 'sin cargar';
        }
    }

    function renderChips() {
        var us = usuarios();
        if (!us.length) {
            $('rut-chips').innerHTML =
                '<span class="rut-chips-vacio">Cargá tu familia en el menú 👆</span>';
            return;
        }
        $('rut-chips').innerHTML = us.map(function (u) {
            return '<button type="button" class="rut-chip rut--persona' +
                (UI.sel[u] ? ' activo' : '') + '" data-user="' + u + '"' +
                styleColor(u) + '>' +
                emojiDe(u) + ' ' + escapeHtml(nombreDe(u)) + '</button>';
        }).join('');
    }

    function renderDias() {
        var hoyIdx = new Date().getDay();
        var orden = [1, 2, 3, 4, 5, 6, 0];   // lunes primero
        var labels = { 1: 'L', 2: 'M', 3: 'X', 4: 'J', 5: 'V', 6: 'S', 0: 'D' };
        $('rut-dias').innerHTML = orden.map(function (d) {
            var cls = 'rut-dia-btn' + (UI.dia === d ? ' activo' : '') +
                (d === hoyIdx ? ' es-hoy' : '');
            return '<button type="button" class="' + cls + '" data-dia="' + d + '">' +
                labels[d] + '</button>';
        }).join('');
    }

    // Tarjeta de cumpleaños: aparece el día que alguno de la familia cumple.
    // Se apaga desde el panel de ajustes (rutina_cumple_activo).
    function renderCumple() {
        var el = $('rut-cumple');
        if (!el) return;
        var hoyIdx = new Date().getDay();
        var festejan = (UI.dia === hoyIdx && CFG.cumple_activo)
            ? MIEMBROS.filter(function (m) { return m.cumple_hoy; })
            : [];
        el.hidden = !festejan.length;
        el.innerHTML = festejan.map(function (m) {
            var anios = m.cumple_anios;
            var cuantos = anios === 0
                ? '¡su primer día!'
                : (anios === 1 ? '¡1 añito!' : '¡' + anios + ' años!');
            return '<div class="rut-cumple-card rut--persona"' + styleColor(m.id) + '>' +
                '<span class="rut-cumple-emoji">🎂</span>' +
                '<div class="rut-cumple-texto">' +
                    '<div class="rut-cumple-titulo">¡Feliz cumple, ' +
                        escapeHtml(m.nombre) + '! ' + cuantos + '</div>' +
                    '<div class="rut-cumple-sub">Que sea un día hermoso 💛</div>' +
                '</div>' +
            '</div>';
        }).join('');
    }

    function renderAviso(esHoy) {
        var el = $('rut-aviso');
        var partes = [];
        if (!esHoy) {
            var nombreDia = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'][UI.dia];
            partes.push('👀 Estás viendo el plan del ' + nombreDia +
                '. Volvé al día de hoy para seguir la rutina en vivo.');
        }
        if (sinSync) {
            partes.push('⚠ Sin conexión: el último ajuste quedó en este teléfono y no se sincronizó.');
        }
        el.hidden = partes.length === 0;
        el.innerHTML = partes.map(escapeHtml).join('<br>');
    }

    // Selección "actual / siguiente" de un usuario. Extraída de renderAhora()
    // tal cual (cut-paste, con las variables de closure como parámetros) para
    // reusarla desde hoyAhora() — la lógica NO cambió.
    function _seleccionAhora(propios, now, esHoy, nocheActiva, nocheItem, u, enCurso) {
        var cur = null;
        propios.forEach(function (i) { if (!cur && enCurso(i)) cur = i; });
        // El sueño nocturno es de un bebé concreto: solo aplica a su tarjeta.
        if (!cur && nocheActiva && nocheItem && String(nocheItem.user) === String(u)) {
            cur = nocheItem;
        }
        // Durmiendo: el último ítem "abierto" (dur 0: A dormir / Sueño
        // nocturno) ya empezó → la tarjeta se mantiene toda la noche
        // (hasta las 05:00 si cruza la medianoche), para los 3 usuarios.
        if (!cur && esHoy) {
            var abierto = null;
            propios.forEach(function (i) { if (!i.dur) abierto = i; });
            if (abierto && (now >= abierto.start || now < 300)) cur = abierto;
        }
        var sig = null;
        propios.forEach(function (i) { if (!sig && i.start > now) sig = i; });
        return { cur: cur, sig: sig };
    }

    function renderAhora(items, esHoy, now, nocheItem, nocheActiva, enCurso) {
        var cont = $('rut-ahora');
        if (!esHoy) { cont.innerHTML = ''; return; }
        var html = '';
        usuariosSel().forEach(function (u) {
            var propios = items.filter(function (i) { return String(i.user) === u; });
            var sel = _seleccionAhora(propios, now, esHoy, nocheActiva, nocheItem, u, enCurso);
            var cur = sel.cur, sig = sel.sig;
            if (!cur && !sig) return;
            var el = cur || { emoji: '⏳', t: 'Tiempo libre', start: now, end: sig ? sig.start : now + 30, sub: '', dur: 1, editable: false };
            var pct = Math.round(Math.min(100, Math.max(3, ((now - el.start) / Math.max(1, (el.end - el.start))) * 100)));
            var rango = fmt(el.start) + ' – ' + (el.dur === 0 ? '…' : fmt(el.end));
            var editable = !!(cur && cur.editable);
            // La actividad está EN CURSO y es ajustable → knob arrastrable en la
            // barra (mover = corregir cuánto avanzó) + editor de inicio/fin.
            var enVentana = editable && cur.dur && now >= cur.start && now < cur.end;
            // "⏳ Aún en {anterior}": lo real va atrasado — la actividad en
            // curso todavía no arrancó. Estira la ANTERIOR hasta ahora (+10'
            // de changüí) y corre la actual. Solo si la actual está de verdad
            // en ventana (dur > 0, no un fallback nocturno) y la anterior es
            // ajustable (ni atada 🔗 ni abierta).
            var btnAun = '';
            if (cur && cur.dur && cur.editable && now >= cur.start && now < cur.end) {
                var prev = null;
                propios.forEach(function (i) {
                    if (i.id !== cur.id && i.dur && i.start < cur.start &&
                        (!prev || i.start > prev.start)) prev = i;
                });
                if (prev && prev.editable) {
                    btnAun = '<button type="button" class="rut-btn-aun" data-aun="' + prev.id + '" ' +
                        'data-aun-cur="' + cur.id + '">⏳ Aún en ' + escapeHtml(prev.t) + '</button>';
                }
            }
            // Emoji clickeable: salta al ítem en la línea de tiempo (si es
            // "Tiempo libre", salta a lo que viene)
            var irId = cur ? cur.id : (sig ? sig.id : null);
            var emojiHtml = irId
                ? '<button type="button" class="rut-ahora-emoji" data-ir="' + irId + '" ' +
                      'title="Ver en la línea de tiempo">' + el.emoji + '</button>'
                : '<span class="rut-ahora-emoji">' + el.emoji + '</span>';
            html += '<div class="rut-card-ahora rut--persona"' + styleColor(u) + '>' +
                '<div class="rut-ahora-head">' +
                    '<span class="rut-ahora-quien">' + emojiDe(u) + ' ' +
                        escapeHtml(nombreDe(u)) + ' · ahora</span>' +
                    '<span class="rut-ahora-rango">' + rango + '</span>' +
                '</div>' +
                '<div class="rut-ahora-cuerpo">' +
                    emojiHtml +
                    '<div class="rut-ahora-texto">' +
                        '<div class="rut-ahora-titulo">' + escapeHtml(el.t) + '</div>' +
                        (el.sub ? '<div class="rut-ahora-sub">' + escapeHtml(el.sub) + '</div>' : '') +
                    '</div>' +
                '</div>' +
                '<div class="rut-barra' + (enVentana ? ' rut-barra-mueve' : '') + '"' +
                    (enVentana ? ' data-barra="' + cur.id + '" data-bstart="' + cur.start + '" data-bnow="' + now + '"' : '') + '>' +
                    '<div class="rut-barra-fill" style="width:' + pct + '%"></div>' +
                    (enVentana ? '<span class="rut-barra-knob" style="left:' + pct + '%"></span>' : '') +
                '</div>' +
                '<div class="rut-ahora-pie">' +
                    '<span class="rut-ahora-luego">luego: ' + (sig ? sig.emoji : '🌙') + ' ' +
                        escapeHtml(sig ? sig.t : 'fin del día') +
                        ' · <span class="rut-mono">' + (sig ? fmt(sig.start) : '—') + '</span></span>' +
                    accionesAhora(cur, btnAun, editable) +
                '</div>' +
            '</div>';
        });
        cont.innerHTML = html;
    }

    // Botonera de la tarjeta "Ahora". Con el editor "empezó a las…" abierto
    // (ahoraHora === cur.id) muestra los dos inputs de hora + OK; si no, los
    // botones: "⏳ Aún en…" (si aplica), "🕐" (empezó a otra hora) y
    // "⏱ Empezó ahora". El 🕐 y "Empezó ahora" solo si es editable (León).
    function accionesAhora(cur, btnAun, editable) {
        if (editable && ahoraHora === cur.id) {
            var s = ((cur.start % 1440) + 1440) % 1440;
            var e = (((cur.start + cur.dur) % 1440) + 1440) % 1440;
            function campo(etiq, aH, aM, val) {
                var m = ((val % 1440) + 1440) % 1440;
                return '<span class="rut-ah-campo"><span class="rut-ah-label">' + etiq + '</span>' +
                    '<input class="rut-hora-in" type="number" min="0" max="23" inputmode="numeric" ' +
                        aH + ' value="' + Math.floor(m / 60) + '" aria-label="Hora ' + etiq + '">' +
                    '<span class="rut-hora-sep">:</span>' +
                    '<input class="rut-hora-in" type="number" min="0" max="59" inputmode="numeric" ' +
                        aM + ' value="' + (m % 60) + '" aria-label="Minutos ' + etiq + '"></span>';
            }
            return '<span class="rut-ahora-acciones rut-ah-edit">' +
                campo('empezó', 'data-ah-h', 'data-ah-m', cur.start) +
                campo('termina', 'data-ah-eh', 'data-ah-em', cur.start + cur.dur) +
                '<button type="button" class="rut-editor-ahora" data-ah-ok="' + cur.id + '">OK</button>' +
                '<button type="button" class="rut-editor-ok" data-ah-x="1">✕</button>' +
            '</span>';
        }
        if (!btnAun && !editable) return '';
        return '<span class="rut-ahora-acciones">' + btnAun +
            (editable
                ? '<button type="button" class="rut-btn-hora" data-ahora-hora="' + cur.id + '" ' +
                      'title="Empezó / termina a otra hora">🕐</button>' +
                  '<button type="button" class="rut-btn-empezo" data-empezo="' + cur.id + '">⏱ Empezó ahora</button>'
                : '') +
        '</span>';
    }

    // ── Lienzo de columnas: una línea de tiempo por persona ─────────────────
    // Eje de tiempo REAL: top = (start − ejeInicio) × ESCALA, height = dur ×
    // ESCALA. Columnas = personas activas en los chips. Las nocturnas van
    // aparte en la franja "🌙 Madrugada", ARRIBA del lienzo (el día arranca
    // después de las 00:00 con esas tomas; a escala sumarían ~10 h de scroll
    // vacío). El texto `sub` no se muestra en el lienzo: vive en el popover
    // de tap (junto al editor −15/+15/Ahora si es editable).
    var ESCALA = 1.6;        // px por minuto (da aire para tipografía estándar)
    var COL_MAX = 380;       // ancho máximo de cada columna: el lienzo se ciñe
                             // a la información en pantallas anchas (el ancho
                             // sobrante queda como margen, no como ítems XXL)

    function renderTimeline(calc, esHoy, now, nocheActiva, enCurso) {
        var usuarios = usuariosSel();
        // Las tomas nocturnas de TODOS los bebés visibles se sacan de las
        // columnas y van juntas a la franja "🌙 Madrugada".
        var porUser = {};
        var nocturnas = [];
        usuarios.forEach(function (u) {
            porUser[u] = (calc.porUser[u] || []).filter(function (i) {
                if (i.kind === 'noct') { nocturnas.push(i); return false; }
                return true;
            });
        });
        nocturnas.sort(function (a, b) { return a.start - b.start; });

        // Los ítems "abiertos" (dur 0: Sueño nocturno) se extienden hasta las
        // 00:00 — o hasta la primera toma nocturna si cayera antes de
        // medianoche (arrancó a dormir muy temprano).
        var primeraNocturna = Infinity;
        nocturnas.forEach(function (n) { if (n.start < primeraNocturna) primeraNocturna = n.start; });
        function finAbierto(i) {
            if (i.kind === 'noche' && primeraNocturna < 1440) return primeraNocturna;
            return 1440;
        }

        var html = modoEdicion ? renderZonaAdd() : '';

        if (!usuarios.length) {
            $('rut-filas').innerHTML = html +
                '<div class="rut-canvas-vacio">' + (MIEMBROS.length
                    ? 'Elegí arriba de quién querés ver la rutina 👆'
                    : 'Todavía no cargaste a nadie. Entrá a <strong>Familia</strong> en el menú de arriba y sumá a mamá, papá o un hijo.') +
                '</div>' +
                (modoEdicion ? renderZonaQuitados(calc.quitados) : '');
            return;
        }

        // Eje temporal: hora en punto ≤ primer inicio .. ≥ último fin visible
        var min = Infinity, max = -Infinity;
        usuarios.forEach(function (u) {
            porUser[u].forEach(function (i) {
                var fin = i.dur ? i.end : finAbierto(i);
                if (i.start < min) min = i.start;
                if (fin > max) max = fin;
            });
        });
        // Nadie visible tiene todavía nada cargado: sin esto el eje quedaría en
        // Infinity y el lienzo saldría en NaN.
        if (min === Infinity) {
            $('rut-filas').innerHTML = html + renderNoche(nocturnas, enCurso) +
                '<div class="rut-canvas-vacio">Sin actividades para este día. ' +
                'Cargalas desde <strong>Actividades</strong> en el menú de arriba.</div>' +
                (modoEdicion ? renderZonaQuitados(calc.quitados) : '');
            return;
        }
        var ejeIni = Math.floor(min / 60) * 60;
        var ejeFin = Math.ceil(max / 60) * 60;
        var altoCanvas = Math.round((ejeFin - ejeIni) * ESCALA);
        function y(m) { return Math.round((m - ejeIni) * ESCALA); }

        // Ancho del lienzo ceñido a la información: gutter + N columnas con tope
        var anchoMax = 40 + usuarios.length * COL_MAX + (usuarios.length - 1) * 4 + 4;

        // El día nuevo arranca después de las 00:00 → las tomas de la
        // madrugada abren la línea de tiempo, ANTES de las columnas.
        html += renderNoche(nocturnas, enCurso);

        // Cabecera de columnas
        html += '<div class="rut-canvas-head" style="max-width:' + anchoMax + 'px">' +
            usuarios.map(function (u) {
                return '<span class="rut-col-head rut--persona"' + styleColor(u) + '>' +
                    emojiDe(u) + ' ' + escapeHtml(nombreDe(u)) + '</span>';
            }).join('') +
        '</div>';

        // Reglas de hora (líneas tenues + etiquetas en el gutter)
        var grid = '', horas = '';
        for (var hm = ejeIni; hm <= ejeFin; hm += 60) {
            grid += '<div class="rut-gridline" style="top:' + y(hm) + 'px"></div>';
            horas += '<span class="rut-hora-label" style="top:' + y(hm) + 'px">' +
                String(Math.floor((((hm % 1440) + 1440) % 1440) / 60)).padStart(2, '0') +
                '</span>';
        }

        // Columnas con ítems posicionados a escala. Solapes dentro de una
        // columna (el día real se corrió y una teta pisa la cena): CARRILES
        // estilo agenda — los ítems del mismo cluster se reparten el ancho,
        // lado a lado y legibles. Los dur 0 ("A dormir") no compiten: son
        // marcadores de final abierto y quedan siempre a ancho completo.
        var cols = usuarios.map(function (u) {
            var its = porUser[u].slice().sort(function (a, b) { return a.start - b.start; });
            var cluster = [], lanesEnd = [], finCluster = -Infinity;
            function cerrarCluster() {
                var n = lanesEnd.length || 1;
                cluster.forEach(function (i) { i._lanes = n; });
                cluster = []; lanesEnd = [];
            }
            its.forEach(function (i) {
                if (!i.dur) { i._lane = 0; i._lanes = 1; return; }
                if (cluster.length && i.start >= finCluster - 0.5) cerrarCluster();
                var lane = -1;
                for (var li = 0; li < lanesEnd.length; li++) {
                    if (lanesEnd[li] <= i.start + 0.5) { lane = li; break; }
                }
                if (lane === -1) { lane = lanesEnd.length; lanesEnd.push(i.end); }
                else lanesEnd[lane] = i.end;
                i._lane = lane;
                cluster.push(i);
                if (i.end > finCluster) finCluster = i.end;
            });
            cerrarCluster();
            return '<div class="rut-col">' + its.map(function (it) {
                var h = it.dur
                    ? Math.max(20, Math.round(it.dur * ESCALA))
                    : Math.max(24, Math.round((Math.min(finAbierto(it), ejeFin) - it.start) * ESCALA));
                var n = it._lanes || 1;
                var izq = 'calc(' + ((it._lane || 0) / n * 100) + '% + 2px)';
                var ancho = 'calc(' + (100 / n) + '% - 4px)';
                var clases = 'rut-item rut--persona';
                if (it.kind && it.kind !== 'adulto' && it.kind !== 'juego') clases += ' rut-item--' + it.kind;
                if (!it.dur) clases += ' rut-item--abierto';
                if (h < 38) clases += ' rut-item--mini';
                if (enCurso(it) || (it.kind === 'noche' && nocheActiva)) clases += ' is-ahora';
                if (!it.editable) clases += ' rut-item--fijado';
                var tapAttr = modoEdicion ? '' : ' data-tap="' + it.id + '"';
                // Drag estilo Teams: mover (cuerpo) y estirar (manija inferior),
                // solo ítems editables fuera del modo edición
                var dragAttr = (it.editable && !modoEdicion) ? ' data-drag="' + it.id + '"' : '';
                var grip = (it.editable && it.dur && !modoEdicion)
                    ? '<span class="rut-item-grip" data-grip="' + it.id + '"></span>' : '';
                // Bloques altos: vuelve el texto descriptivo, recortado a las
                // líneas que realmente entran (el completo vive en el popover)
                var subHtml = '';
                if (it.sub && h >= 68) {
                    var lineas = Math.max(1, Math.min(4, Math.floor((h - 42) / 18)));
                    subHtml = '<span class="rut-item-sub" style="-webkit-line-clamp:' + lineas + '">' +
                        escapeHtml(it.sub) + '</span>';
                }
                return '<div class="' + clases + '"' + tapAttr + dragAttr + ' data-item="' + it.id + '"' +
                    ' style="--rut-color: var(--color-' + colorTokenDe(it.user) + ');top:' +
                    y(it.start) + 'px;height:' + h + 'px;left:' + izq + ';width:' + ancho + '">' +
                    '<span class="rut-item-linea">' +
                        '<span class="rut-item-hora">' + fmt(it.start) + '</span>' +
                        '<span class="rut-item-emoji">' + it.emoji + '</span>' +
                        '<span class="rut-item-titulo">' + escapeHtml(it.t) + '</span>' +
                        (it.compartida && h >= 24 ? '<span class="rut-item-candado" title="Compartida con otro miembro">🔗</span>' : '') +
                        (it.dur && h >= 38 ? '<span class="rut-item-dur">' + fmtDur(it.dur) + '</span>' : '') +
                    '</span>' +
                    subHtml +
                    grip +
                    (modoEdicion
                        ? '<button type="button" class="rut-item-quitar" data-quitar="' + it.id + '" ' +
                              'aria-label="Quitar ' + escapeHtml(it.t) + '">✕</button>'
                        : '') +
                '</div>';
            }).join('') + '</div>';
        }).join('');

        // Línea "ahora" cruzando todas las columnas (solo hoy real)
        var lineaAhora = '';
        if (esHoy && now >= ejeIni && now <= ejeFin) {
            lineaAhora = '<div class="rut-linea-ahora" style="top:' + y(now) + 'px">' +
                '<span>' + fmt(now) + '</span></div>';
        }

        html += '<div class="rut-canvas" style="height:' + altoCanvas + 'px;max-width:' + anchoMax + 'px">' +
            grid +
            '<div class="rut-gutter">' + horas + '</div>' +
            '<div class="rut-cols">' + cols + '</div>' +
            lineaAhora +
            renderPopover(porUser, usuarios, y, altoCanvas) +
        '</div>';

        if (modoEdicion) html += renderZonaQuitados(calc.quitados);
        $('rut-filas').innerHTML = html;
    }

    // Popover superpuesto del lienzo: detalle + editor de hora (tap normal)
    // o "¿Quitar solo hoy o siempre?" (✕ del modo edición). Anclado a la
    // altura del ítem, ancho completo menos gutter, clampeado al lienzo.
    function renderPopover(porUser, usuarios, y, altoCanvas) {
        var id = modoEdicion ? quitando : editando;
        if (!id) return '';
        var it = null;
        usuarios.forEach(function (u) {
            porUser[u].forEach(function (i) { if (!it && i.id === id) it = i; });
        });
        if (!it) return '';
        var top = Math.max(4, Math.min(y(it.start) + 6, altoCanvas - 150));

        if (modoEdicion) {
            // Tarea añadida permanente: "Siempre" la borra de raíz. Tocar el
            // popover fuera de los botones también cancela (data-q-cancelar
            // en el contenedor; Solo hoy/Siempre se chequean antes).
            var borrarAttr = (it.custom && it.permanente) ? ' data-tarea="' + it.tareaId + '"' : '';
            return '<div class="rut-popover rut--persona" data-q-cancelar="1" style="--rut-color: var(--color-' +
                colorTokenDe(it.user) + ');top:' + top + 'px">' +
                '<div class="rut-popover-head">' +
                    '<span class="rut-popover-titulo">' + it.emoji + ' ' + escapeHtml(it.t) + '</span>' +
                '</div>' +
                '<div class="rut-popover-botones">' +
                    '<span class="rut-quitar-txt">Quitar:</span>' +
                    '<button type="button" class="rut-editor-btn rut-q-btn" data-q-hoy="' + it.id + '">Solo hoy</button>' +
                    '<button type="button" class="rut-editor-btn rut-q-btn rut-q-siempre" data-q-siempre="' + it.id + '"' + borrarAttr + '>Siempre</button>' +
                    '<button type="button" class="rut-editor-ok" data-q-cancelar="1">Cancelar</button>' +
                '</div>' +
            '</div>';
        }

        // Sin botón OK: tocar CUALQUIER parte del detalle lo cierra (data-cerrar
        // en el contenedor; los botones −15/+15/Ahora se chequean ANTES en el
        // handler, así que ajustan sin cerrar).
        var rango = fmt(it.start) + ' – ' + (it.dur ? fmt(it.end) + ' · ' + fmtDur(it.dur) : '…');
        return '<div class="rut-popover rut--persona" data-cerrar="1" style="--rut-color: var(--color-' +
            colorTokenDe(it.user) + ');top:' + top + 'px">' +
            '<div class="rut-popover-head">' +
                '<span class="rut-popover-titulo">' + it.emoji + ' ' + escapeHtml(it.t) + '</span>' +
                '<span class="rut-popover-rango">' + rango + '</span>' +
            '</div>' +
            (it.sub ? '<div class="rut-popover-sub">' + escapeHtml(it.sub) + '</div>' : '') +
            '<div class="rut-popover-botones">' +
                (it.editable
                    ? '<button type="button" class="rut-editor-btn" data-menos="' + it.id + '">−15</button>' +
                      inputsHora(it) +
                      '<button type="button" class="rut-editor-btn" data-mas="' + it.id + '">+15</button>' +
                      '<button type="button" class="rut-editor-ahora" data-poner-ahora="' + it.id + '">Ahora</button>'
                    : '<span class="rut-popover-nota">' +
                        (it.link ? 'Sigue el horario de León' : 'Horario fijo') + '</span>') +
                '<span class="rut-popover-cerrar">tocá para cerrar</span>' +
            '</div>' +
        '</div>';
    }

    // Hora editable del editor: dos inputs numéricos (ruedita del mouse
    // ±1 h / ±5 min; en el teléfono abre el teclado numérico). El cambio se
    // aplica al salir del input o con la ruedita (delegado en #rut-filas).
    function inputsHora(it) {
        var m = ((it.start % 1440) + 1440) % 1440;
        return '<span class="rut-editor-hora">' +
            '<input class="rut-hora-in" type="number" min="0" max="23" inputmode="numeric" ' +
                'data-hora-h="' + it.id + '" value="' + Math.floor(m / 60) + '" aria-label="Hora">' +
            '<span class="rut-hora-sep">:</span>' +
            '<input class="rut-hora-in" type="number" min="0" max="59" inputmode="numeric" ' +
                'data-hora-m="' + it.id + '" value="' + (m % 60) + '" aria-label="Minutos">' +
        '</span>';
    }

    // Franja "🌙 Madrugada": las tomas nocturnas como filas apiladas, ARRIBA
    // del lienzo (el día nuevo arranca después de las 00:00, así que las
    // tomas de madrugada lo abren). Reusan .rut-fila con su editor inline y
    // ✕ de siempre — son a demanda, el eje a escala no aporta ahí.
    function renderNoche(nocturnas, enCurso) {
        if (!nocturnas.length) return '';
        return '<div class="rut-noche">' +
            '<div class="rut-noche-titulo">🌙 Madrugada — así arranca el día ' +
                '<span>a demanda, horarios orientativos</span></div>' +
            nocturnas.map(function (it) {
                var activa = enCurso(it);
                var clases = 'rut-fila rut--persona rut-fila--noct' + (activa ? ' is-ahora' : '');
                var tapAttr = modoEdicion ? '' : ' data-tap="' + it.id + '"';
                var fila = '<div class="' + clases + '"' + styleColor(it.user) +
                    ' data-item="' + it.id + '">' +
                    '<div class="rut-fila-tap"' + tapAttr + '>' +
                        '<span class="rut-fila-hora">' + fmt(it.start) + '</span>' +
                        '<span class="rut-fila-dot"></span>' +
                        '<span class="rut-fila-emoji">' + it.emoji + '</span>' +
                        '<div class="rut-fila-cuerpo">' +
                            '<div class="rut-fila-titulo">' + escapeHtml(it.t) +
                                (activa ? '<span class="rut-badge-ahora">ahora</span>' : '') +
                            '</div>' +
                            (it.sub ? '<div class="rut-fila-sub">' + escapeHtml(it.sub) + '</div>' : '') +
                        '</div>' +
                        (modoEdicion
                            ? '<button type="button" class="rut-btn-quitar" data-quitar="' + it.id + '" ' +
                                  'aria-label="Quitar ' + escapeHtml(it.t) + '">✕</button>'
                            : '<span class="rut-fila-dur">' + fmtDur(it.dur) + '</span>') +
                    '</div>';
                if (editando === it.id && !modoEdicion) {
                    fila += '<div class="rut-editor">' +
                        '<button type="button" class="rut-editor-btn" data-menos="' + it.id + '">−15</button>' +
                        inputsHora(it) +
                        '<button type="button" class="rut-editor-btn" data-mas="' + it.id + '">+15</button>' +
                        '<button type="button" class="rut-editor-ahora" data-poner-ahora="' + it.id + '">Ahora</button>' +
                        '<button type="button" class="rut-editor-ok" data-cerrar="1">OK</button>' +
                    '</div>';
                }
                if (modoEdicion && quitando === it.id) {
                    fila += '<div class="rut-editor rut-quitar-bar">' +
                        '<span class="rut-quitar-txt">Quitar:</span>' +
                        '<button type="button" class="rut-editor-btn rut-q-btn" data-q-hoy="' + it.id + '">Solo hoy</button>' +
                        '<button type="button" class="rut-editor-btn rut-q-btn rut-q-siempre" data-q-siempre="' + it.id + '">Siempre</button>' +
                        '<button type="button" class="rut-editor-ok" data-q-cancelar="1">Cancelar</button>' +
                    '</div>';
                }
                return fila + '</div>';
            }).join('') +
        '</div>';
    }

    // Botón/form "＋ Añadir tarea" (solo en modo edición, arriba del timeline)
    function renderZonaAdd() {
        // El form puede estar abierto acá ('filas') o en la tarjeta de
        // calendario ('cal'): si no es de acá, mostrar el botón.
        if (!formAdd || formAdd.en !== 'filas') {
            return '<div class="rut-add-row">' +
                '<button type="button" class="rut-add-btn" data-add="1">＋ Añadir tarea</button>' +
            '</div>';
        }
        return formAddHtml();
    }

    function formAddHtml() {
        var horas = '', minutos = '', durs = '';
        for (var h = 0; h < 24; h++) {
            var hh = String(h).padStart(2, '0');
            horas += '<option value="' + h + '"' + (formAdd.hora === h ? ' selected' : '') + '>' + hh + '</option>';
        }
        [0, 15, 30, 45].forEach(function (m) {
            var mm = String(m).padStart(2, '0');
            minutos += '<option value="' + m + '"' + (formAdd.min === m ? ' selected' : '') + '>' + mm + '</option>';
        });
        [15, 30, 45, 60, 90, 120].forEach(function (d) {
            durs += '<option value="' + d + '"' + (formAdd.dur === d ? ' selected' : '') + '>' + fmtDur(d) + '</option>';
        });
        return '<div class="rut-add-form">' +
            '<div class="rut-add-linea">' +
                usuarios().map(function (u) {
                    return '<button type="button" class="rut-add-pill rut--persona' +
                        (String(formAdd.user) === u ? ' activo' : '') +
                        '" data-add-user="' + u + '"' + styleColor(u) + '>' +
                        emojiDe(u) + ' ' + escapeHtml(nombreDe(u)) + '</button>';
                }).join('') +
            '</div>' +
            '<div class="rut-add-linea">' +
                '<input type="text" class="rut-add-input rut-add-emoji" id="rut-add-emoji" maxlength="4" ' +
                    'placeholder="📌" value="' + escapeHtml(formAdd.emoji) + '" aria-label="Emoji (opcional)">' +
                '<input type="text" class="rut-add-input" id="rut-add-titulo" maxlength="60" ' +
                    'placeholder="Nombre de la tarea" value="' + escapeHtml(formAdd.titulo) + '">' +
            '</div>' +
            '<div class="rut-add-linea">' +
                '<span class="rut-add-label">Empieza</span>' +
                '<select class="rut-add-select" id="rut-add-hora">' + horas + '</select>' +
                '<span class="rut-add-label">:</span>' +
                '<select class="rut-add-select" id="rut-add-min">' + minutos + '</select>' +
                '<span class="rut-add-label">· dura</span>' +
                '<select class="rut-add-select" id="rut-add-dur">' + durs + '</select>' +
            '</div>' +
            '<div class="rut-add-linea">' +
                '<button type="button" class="rut-add-pill' + (formAdd.alcance === 'hoy' ? ' activo' : '') + '" data-add-alcance="hoy">Solo hoy</button>' +
                '<button type="button" class="rut-add-pill' + (formAdd.alcance === 'siempre' ? ' activo' : '') + '" data-add-alcance="siempre">Todos los días</button>' +
                '<span class="rut-add-espacio"></span>' +
                '<button type="button" class="rut-editor-ahora" data-add-guardar="1">Guardar</button>' +
                '<button type="button" class="rut-editor-ok" data-add-cancelar="1">Cancelar</button>' +
            '</div>' +
        '</div>';
    }

    // Tarjeta "Hoy por calendario": si una actividad del módulo Calendario
    // vence HOY, se ofrece añadirla a la rutina. Discreta y monocromática
    // (todo en tono muted/deco); solo aparece mirando el día de hoy real.
    // Click → abre el form de añadir prefijado acá mismo; ✕ la descarta por
    // hoy (localStorage 'rutina-cal-v1'). No toca el estado del Calendario.
    var LS_CAL = 'rutina-cal-v1';

    function calDescartadas(fecha) {
        var g = {};
        try { g = JSON.parse(localStorage.getItem(LS_CAL) || '{}'); } catch (e) {}
        return g[fecha] || [];
    }

    function descartarCal(id) {
        var fecha = isoLocal(new Date());
        var lista = calDescartadas(fecha);
        if (lista.indexOf(id) < 0) lista.push(id);
        var g = {};
        g[fecha] = lista;   // se guarda SOLO la fecha de hoy: lo viejo se descarta solo
        try { localStorage.setItem(LS_CAL, JSON.stringify(g)); } catch (e) {}
        if (formAdd && formAdd.en === 'cal') formAdd = null;
        renderTodo();
    }

    function renderCal() {
        var el = $('rut-cal');
        if (!el) return;
        var hoyIdx = new Date().getDay();
        var fecha = isoLocal(new Date());
        if (UI.dia !== hoyIdx || !CALHOY.length) {
            el.hidden = true; el.innerHTML = ''; return;
        }
        var ocultas = calDescartadas(fecha);
        var pendientes = CALHOY.filter(function (c) {
            if (ocultas.indexOf(c.id) >= 0) return false;
            // ya añadida a la rutina (misma fecha u hoy permanente, mismo título)
            return !TAREAS.some(function (t) {
                return t.titulo === c.nombre && (t.fecha === fecha || t.fecha === '');
            });
        });
        var html = pendientes.map(function (c) {
            return '<div class="rut-cal-card" data-cal-add="' + c.id + '">' +
                '<span class="rut-cal-txt">📅 Hoy por calendario: <b>' + escapeHtml(c.nombre) + '</b>' +
                    ' · proponemos 10:00 – 11:00 — tocá para añadir</span>' +
                '<button type="button" class="rut-cal-x" data-cal-x="' + c.id + '" ' +
                    'aria-label="Descartar por hoy">✕</button>' +
            '</div>';
        }).join('');
        if (formAdd && formAdd.en === 'cal') html += formAddHtml();
        el.hidden = html === '';
        el.innerHTML = html;
    }

    // Tareas quitadas del día visible (grisadas, con ↩ para restaurarlas)
    function renderZonaQuitados(quitados) {
        var visibles = (quitados || []).filter(function (q) { return UI.sel[q.user]; });
        if (!visibles.length) return '';
        return '<div class="rut-quitados">' +
            '<div class="rut-quitados-titulo">Tareas quitadas</div>' +
            visibles.map(function (q) {
                return '<div class="rut-quitado-fila rut--persona"' + styleColor(q.user) + '>' +
                    '<span class="rut-fila-dot"></span>' +
                    '<span class="rut-fila-emoji">' + q.emoji + '</span>' +
                    '<span class="rut-quitado-titulo">' + escapeHtml(q.t) + '</span>' +
                    '<button type="button" class="rut-btn-restaurar" data-restaurar="' + q.id + '">↩ Restaurar</button>' +
                '</div>';
            }).join('') +
        '</div>';
    }

    // Lee lo tipeado en el form de añadir antes de un re-render (los inputs
    // de texto se reconstruyen; sin esto se perdería lo escrito).
    function capturarFormAdd() {
        if (!formAdd) return;
        var titulo = $('rut-add-titulo'), emoji = $('rut-add-emoji');
        var hora = $('rut-add-hora'), min = $('rut-add-min'), dur = $('rut-add-dur');
        if (titulo) formAdd.titulo = titulo.value;
        if (emoji) formAdd.emoji = emoji.value;
        if (hora) formAdd.hora = Number(hora.value);
        if (min) formAdd.min = Number(min.value);
        if (dur) formAdd.dur = Number(dur.value);
    }

    // Tarjeta de tips: sale de la ventana de sueño que corresponde a la edad
    // del bebé visible. Sin bebé cargado, no hay tarjeta.
    function renderTips(bebe) {
        var cont = $('rut-tips');
        if (!bebe || !bebe.resumen) { cont.innerHTML = ''; return; }
        var r = bebe.resumen;
        var nombre = bebe.miembro.nombre;

        var tips = [
            'Ventana de sueño a esta edad (' + r.etiqueta + '): ' + r.ventana +
                ' despierto entre sueño y sueño. La primera del día es la más corta.',
            'Suelen ser ' + r.siestas + ' siestas de ' + r.siestaDur +
                ', y ' + r.suenoDia + ' de sueño en total en 24 h.',
            'De noche: ' + r.nocturnas + '.',
            'Las señales de ' + nombre + ' —bostezo, mirada perdida, quejoso— mandan ' +
                'más que el reloj. Las tomas van a demanda: la tabla se adapta a él, no al revés.'
        ];

        cont.innerHTML = '<div class="rut-tips-card">' +
            '<div class="rut-tips-titulo">📖 Ventanas de sueño — ' +
                escapeHtml(nombre) + ', ' + escapeHtml(bebe.miembro.edad_texto || r.etiqueta) +
            '</div>' +
            tips.map(function (t) {
                return '<div class="rut-tip">• ' + escapeHtml(t) + '</div>';
            }).join('') +
            '<div class="rut-tips-nota">Valores orientativos, consolidados de guías públicas de ' +
            'sueño infantil (Cleveland Clinic, Taking Cara Babies, Huckleberry, Mustela). ' +
            'La app propone un plan y te deja corregirlo: no reemplaza a su pediatra. ' +
            'Ritmo flexible, no horario rígido.</div>' +
        '</div>';
    }

    // ── Panel Familia ────────────────────────────────────────────────────────
    // Alta, edición y baja de miembros. Es la pantalla que reemplaza a las tres
    // etapas hardcodeadas: lo que antes había que tocar en el código, ahora se
    // carga acá y la rutina se rearma sola.

    var ROLES = [
        { v: 'mama', t: 'Mamá' },
        { v: 'papa', t: 'Papá' },
        { v: 'hijo', t: 'Hijo/a' },
        { v: 'otro', t: 'Otro' }
    ];

    function formMiembroNuevo() {
        return {
            id: null, nombre: '', rol: 'hijo', es_bebe: false,
            fecha_nacimiento: '', color_token: '', ancla_min: 390, error: ''
        };
    }

    function formMiembroDe(m) {
        return {
            id: m.id, nombre: m.nombre, rol: m.rol, es_bebe: !!m.es_bebe,
            fecha_nacimiento: m.fecha_nacimiento || '',
            color_token: m.color_token || colorTokenDe(m.id),
            ancla_min: m.ancla_min, error: ''
        };
    }

    // Lee lo tipeado antes de un re-render (los inputs se reconstruyen).
    function capturarFormMiembro() {
        if (!formMiembro) return;
        var n = $('rut-fm-nombre'), f = $('rut-fm-fnac'), a = $('rut-fm-ancla');
        if (n) formMiembro.nombre = n.value;
        if (f) formMiembro.fecha_nacimiento = f.value;
        if (a) formMiembro.ancla_min = horaAMin(a.value, formMiembro.ancla_min);
    }

    function horaAMin(valor, porDefecto) {
        var p = String(valor || '').split(':');
        if (p.length !== 2) return porDefecto;
        var h = Number(p[0]), m = Number(p[1]);
        if (isNaN(h) || isNaN(m)) return porDefecto;
        return Math.max(0, Math.min(1439, h * 60 + m));
    }

    function minAHora(min) {
        var m = ((min % 1440) + 1440) % 1440;
        return String(Math.floor(m / 60)).padStart(2, '0') + ':' +
               String(m % 60).padStart(2, '0');
    }

    function renderFamilia() {
        var cont = $('rut-familia');
        if (!cont) return;

        var lista = MIEMBROS.map(function (m) {
            var detalle = [];
            ROLES.forEach(function (r) { if (r.v === m.rol) detalle.push(r.t); });
            if (m.es_bebe) detalle.push('bebé');
            if (m.edad_texto) detalle.push(m.edad_texto);
            else if (!m.fecha_nacimiento) detalle.push('sin fecha de nacimiento');

            return '<div class="rut-miembro rut--persona"' + styleColor(m.id) + '>' +
                '<span class="rut-miembro-emoji">' + emojiDe(m.id) + '</span>' +
                '<div class="rut-miembro-texto">' +
                    '<div class="rut-miembro-nombre">' + escapeHtml(m.nombre) +
                        (m.cumple_hoy ? ' <span class="rut-miembro-cumple">🎂 hoy</span>' : '') +
                    '</div>' +
                    '<div class="rut-miembro-sub">' + escapeHtml(detalle.join(' · ')) +
                        (m.es_bebe ? ' · primera toma ' + minAHora(m.ancla_min) : '') +
                    '</div>' +
                '</div>' +
                '<button type="button" class="rut-btn-icono" data-fm-editar="' + m.id + '" ' +
                    'aria-label="Editar ' + escapeHtml(m.nombre) + '">✎</button>' +
                '<button type="button" class="rut-btn-icono" data-fm-borrar="' + m.id + '" ' +
                    'aria-label="Borrar ' + escapeHtml(m.nombre) + '">🗑</button>' +
            '</div>';
        }).join('');

        var vacio = MIEMBROS.length ? '' :
            '<p class="rut-panel-vacio">Todavía no hay nadie cargado. Empezá sumando ' +
            'a mamá, a papá o a un hijo — si es bebé, marcá la casilla y su rutina ' +
            'se arma sola con las ventanas de sueño de su edad.</p>';

        var boton = formMiembro ? '' :
            '<button type="button" class="rut-add-btn" data-fm-nuevo="1">＋ Agregar miembro</button>';

        cont.innerHTML = vacio + lista + (formMiembro ? formMiembroHtml() : boton);
    }

    function formMiembroHtml() {
        var f = formMiembro;
        var esHijo = f.rol === 'hijo';

        var pillsRol = ROLES.map(function (r) {
            return '<button type="button" class="rut-add-pill' +
                (f.rol === r.v ? ' activo' : '') + '" data-fm-rol="' + r.v + '">' +
                r.t + '</button>';
        }).join('');

        var swatches = COLOR_CICLO.map(function (tok) {
            return '<button type="button" class="rut-swatch' +
                (f.color_token === tok ? ' activo' : '') + '" data-fm-color="' + tok + '" ' +
                'style="background: var(--color-' + tok + ')" ' +
                'aria-label="Color ' + tok + '"></button>';
        }).join('');

        return '<div class="rut-fm">' +
            (f.error ? '<div class="rut-fm-error">⚠ ' + escapeHtml(f.error) + '</div>' : '') +
            '<div class="rut-fm-linea">' +
                '<input type="text" class="rut-add-input" id="rut-fm-nombre" maxlength="40" ' +
                    'placeholder="Nombre" value="' + escapeHtml(f.nombre) + '">' +
            '</div>' +
            '<div class="rut-fm-linea rut-fm-pills">' + pillsRol + '</div>' +
            (esHijo
                ? '<label class="rut-fm-check">' +
                      '<input type="checkbox" data-fm-bebe="1"' + (f.es_bebe ? ' checked' : '') + '>' +
                      '<span>Es bebé — armale la rutina con las ventanas de sueño</span>' +
                  '</label>'
                : '') +
            '<div class="rut-fm-linea">' +
                '<span class="rut-add-label">Nacimiento</span>' +
                '<input type="date" class="rut-add-input rut-fm-fecha" id="rut-fm-fnac" ' +
                    'value="' + escapeHtml(f.fecha_nacimiento) + '">' +
            '</div>' +
            (f.es_bebe
                ? '<div class="rut-fm-linea">' +
                      '<span class="rut-add-label">Primera toma del día</span>' +
                      '<input type="time" class="rut-add-input rut-fm-hora" id="rut-fm-ancla" ' +
                          'value="' + minAHora(f.ancla_min) + '">' +
                  '</div>' +
                  '<p class="rut-fm-nota">Esta hora es el ancla: todas las siestas y ' +
                  'tomas del día se calculan a partir de ella.</p>'
                : '') +
            '<div class="rut-fm-linea rut-fm-colores">' + swatches + '</div>' +
            '<div class="rut-fm-linea">' +
                '<span class="rut-add-espacio"></span>' +
                '<button type="button" class="rut-editor-ahora" data-fm-guardar="1">Guardar</button>' +
                '<button type="button" class="rut-editor-ok" data-fm-cancelar="1">Cancelar</button>' +
            '</div>' +
        '</div>';
    }

    function guardarMiembro() {
        capturarFormMiembro();
        var f = formMiembro;
        if (!f) return;
        if (!f.nombre.trim()) {
            f.error = 'Poné un nombre.';
            return renderTodo();
        }
        if (f.es_bebe && !f.fecha_nacimiento) {
            f.error = 'Para un bebé hace falta la fecha de nacimiento: sin edad no hay ventana de sueño.';
            return renderTodo();
        }
        var campos = {
            nombre: f.nombre.trim(),
            rol: f.rol,
            es_bebe: f.es_bebe ? '1' : '0',
            fecha_nacimiento: f.fecha_nacimiento || '',
            color_token: f.color_token || '',
            ancla_min: f.ancla_min
        };
        if (f.id) {
            campos.id = f.id;
            campos.activo = '1';
        }
        formMiembro = null;
        postAccion(f.id ? '/api/rutina/miembro/editar' : '/api/rutina/miembro/crear', campos);
    }

    // ── Panel Ajustes ────────────────────────────────────────────────────────
    function renderAjustes() {
        var noche = $('rut-cfg-noche');
        var amanecer = $('rut-cfg-amanecer');
        var cumple = $('rut-cfg-cumple');
        // No pisar lo que el usuario está tipeando: solo sincronizar cuando el
        // campo no tiene el foco.
        if (noche && document.activeElement !== noche) {
            noche.value = CFG.hora_noche || '20:00';
        }
        if (amanecer && document.activeElement !== amanecer) {
            amanecer.value = CFG.hora_amanecer || '06:30';
        }
        if (cumple) cumple.checked = !!CFG.cumple_activo;
    }

    function guardarAjustes() {
        var noche = $('rut-cfg-noche'), amanecer = $('rut-cfg-amanecer');
        var cumple = $('rut-cfg-cumple');
        postAccion('/api/rutina/ajustes', {
            hora_noche: noche ? noche.value : '20:00',
            hora_amanecer: amanecer ? amanecer.value : '06:30',
            cumple_activo: (cumple && cumple.checked) ? '1' : '0'
        });
    }

    // ── Menú de secciones (mismo patrón que Lactancia) ───────────────────────
    // No es un <select> nativo porque las opciones llevan ícono. El wrapper
    // recibe data-rut-sec y el CSS muestra solo la sección activa en mobile.
    function initNavMenu() {
        var wrap = document.querySelector('.rut-wrap');
        var trigger = $('rut-nav-trigger');
        var lista = $('rut-nav-lista');
        if (!wrap || !trigger || !lista) return;

        function aplicar(sec) {
            UI.sec = sec;
            wrap.setAttribute('data-rut-sec', sec);
            var activa = null;
            lista.querySelectorAll('[data-sec]').forEach(function (btn) {
                var on = btn.dataset.sec === sec;
                btn.classList.toggle('is-activa', on);
                if (on) activa = btn;
            });
            if (activa) trigger.innerHTML = activa.innerHTML;
            lista.hidden = true;
            trigger.setAttribute('aria-expanded', 'false');
            persistirUI();
        }

        trigger.addEventListener('click', function () {
            var abierto = !lista.hidden;
            lista.hidden = abierto;
            trigger.setAttribute('aria-expanded', abierto ? 'false' : 'true');
        });

        lista.addEventListener('click', function (ev) {
            var btn = ev.target.closest('[data-sec]');
            if (btn) aplicar(btn.dataset.sec);
        });

        document.addEventListener('click', function (ev) {
            if (!lista.hidden && !ev.target.closest('.rut-nav-menu')) {
                lista.hidden = true;
                trigger.setAttribute('aria-expanded', 'false');
            }
        });

        document.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape' && !lista.hidden) {
                lista.hidden = true;
                trigger.setAttribute('aria-expanded', 'false');
            }
        });

        aplicar(UI.sec || 'hoy');
    }

    // Cálculo de noche + predicado "en curso". El ítem de noche es el del
    // primer bebé visible (el mismo que manda en la tarjeta de tips).
    function _nocheInfo(calc, esHoy, now) {
        var nocheItem = null;
        usuarios().forEach(function (u) {
            (calc.porUser[u] || []).forEach(function (i) {
                if (!nocheItem && i.kind === 'noche') nocheItem = i;
            });
        });
        function enCurso(it) {
            return esHoy && it.kind !== 'noche' && now >= it.start && now < Math.max(it.end, it.start + 1);
        }
        // La noche queda activa desde su inicio hasta las 05:00 (cruza medianoche)
        var nocheActiva = esHoy && nocheItem && (now >= nocheItem.start || now < 300);
        return { nocheItem: nocheItem, nocheActiva: nocheActiva, enCurso: enCurso };
    }

    function renderTodo() {
        ajustarSticky();   // remedir siempre: el alto del topbar global puede variar
        capturarFormAdd();     // preservar lo tipeado en el form de añadir
        capturarFormMiembro(); // ídem en el form de familia
        normalizarSeleccion();
        var calc = calcular();
        var hoyIdx = new Date().getDay();
        var esHoy = UI.dia === hoyIdx;
        var now = ahoraMin();

        // Orden estable entre personas: a igual hora manda el orden de la
        // familia (el `orden` de rutina_miembros).
        var orden = usuarios();
        var items = [];
        usuariosSel().forEach(function (u) {
            items = items.concat(calc.porUser[u] || []);
        });
        items.sort(function (a, b) {
            return a.start - b.start ||
                (orden.indexOf(String(a.user)) - orden.indexOf(String(b.user)));
        });

        var ni = _nocheInfo(calc, esHoy, now);
        var nocheItem = ni.nocheItem, nocheActiva = ni.nocheActiva, enCurso = ni.enCurso;

        renderHeader();
        renderChips();
        renderDias();
        renderCumple();
        renderCal();
        renderAviso(esHoy);
        renderAhora(items, esHoy, now, nocheItem, nocheActiva, enCurso);
        renderTimeline(calc, esHoy, now, nocheActiva, enCurso);
        renderTips(calc.bebe);
        renderFamilia();
        renderAjustes();

        var btnEditar = $('rut-editar');
        if (btnEditar) {
            btnEditar.textContent = modoEdicion ? '✓ Listo' : '✎ Editar';
            btnEditar.classList.toggle('activo', modoEdicion);
        }
    }

    // ── API pública para la tarjeta Rutina del Inicio (window.Rutina) ───────
    // Fuerza "hoy real" con save/restore síncrono de UI.dia (try/finally, SIN
    // persistir: jamás toca localStorage — UI.sel no afecta a calcular() ni a
    // la selección, no hace falta tocarlo) y devuelve, por miembro, qué está
    // haciendo AHORA y qué viene después:
    //   [{ user, nombre, emoji, color,
    //      actual:    { titulo, emoji, desde, hasta|null },   // null = abierto (dur 0)
    //      siguiente: { titulo, emoji, hora } | null }]
    // `color` es el token de la variable CSS (--color-<token>): antes el color
    // lo fijaba una clase por persona en home.js, que ya no sirve con una
    // familia de tamaño variable.
    // Sin actividad en curso pero con siguiente → mismo "Tiempo libre" (⏳)
    // sintético que usan las tarjetas "Ahora". Miembro sin actual ni
    // siguiente → se omite. Requiere window.RUT_DATOS inyectado ANTES de
    // cargar este script (igual que en /rutina): el estado del módulo se
    // popula al evaluar la IIFE, no en init().
    function hoyAhora() {
        var diaOrig = UI.dia;
        try {
            UI.dia = new Date().getDay();   // fechaVista() pasa a ser HOY real
            var calc = calcular();
            var now = ahoraMin();
            var ni = _nocheInfo(calc, true, now);
            var out = [];
            usuarios().forEach(function (u) {
                // calc.porUser[u] ya viene ordenado por inicio (mismo orden que
                // los `propios` que renderAhora filtra de la lista combinada)
                var sel = _seleccionAhora(calc.porUser[u] || [], now, true,
                                          ni.nocheActiva, ni.nocheItem, u, ni.enCurso);
                if (!sel.cur && !sel.sig) return;
                var el = sel.cur || { emoji: '⏳', t: 'Tiempo libre', start: now, end: sel.sig ? sel.sig.start : now + 30, dur: 1 };
                out.push({
                    user: u, nombre: nombreDe(u), emoji: emojiDe(u),
                    color: colorTokenDe(u),
                    actual: {
                        titulo: el.t, emoji: el.emoji,
                        desde: fmt(el.start),
                        hasta: el.dur === 0 ? null : fmt(el.end)
                    },
                    siguiente: sel.sig
                        ? { titulo: sel.sig.t, emoji: sel.sig.emoji, hora: fmt(sel.sig.start) }
                        : null
                });
            });
            return out;
        } finally {
            UI.dia = diaOrig;
        }
    }

    window.Rutina = { hoyAhora: hoyAhora };

    // ── Topbar sticky: se pega justo debajo del topbar global de la app.
    //    El .site-topbar puede estar corrido (banner DEV: top 24px), así que
    //    el top propio = top del site-topbar + su alto. ────────────────────
    function ajustarSticky() {
        var site = document.querySelector('.site-topbar');
        var propio = $('rut-topbar');
        if (!site || !propio) return;
        var topSite = parseFloat(getComputedStyle(site).top) || 0;
        propio.style.top = (topSite + site.offsetHeight) + 'px';
    }

    // ── Eventos (delegación: los contenedores no se reemplazan nunca) ───────
    function init() {
        if (!$('rut-filas')) return;   // no estamos en /rutina
        // Desktop ≥900px: mismo patrón que cal-body/lac-body (alto = viewport,
        // scroll interno en el timeline). En mobile la clase no tiene efecto.
        document.body.classList.add('rut-body');

        initNavMenu();

        // Panel Familia: alta / edición / baja de miembros.
        var panelFam = $('rut-familia');
        if (panelFam) {
            panelFam.addEventListener('click', function (ev) {
                var el;
                if (ev.target.closest('[data-fm-nuevo]')) {
                    formMiembro = formMiembroNuevo();
                    renderTodo();
                    var inp = $('rut-fm-nombre');
                    if (inp) inp.focus();
                    return;
                }
                if ((el = ev.target.closest('[data-fm-editar]'))) {
                    var m = miembroDe(el.dataset.fmEditar);
                    if (m) { formMiembro = formMiembroDe(m); renderTodo(); }
                    return;
                }
                if ((el = ev.target.closest('[data-fm-borrar]'))) {
                    var q = miembroDe(el.dataset.fmBorrar);
                    if (!q) return;
                    // Se lleva sus actividades y sus ajustes de horario: conviene
                    // preguntar aunque el resto del módulo no use confirmaciones.
                    if (!window.confirm('¿Borrar a ' + q.nombre + '? Se van también ' +
                        'sus actividades y los horarios que hayas ajustado.')) return;
                    formMiembro = null;
                    return postAccion('/api/rutina/miembro/borrar', { id: q.id });
                }
                if ((el = ev.target.closest('[data-fm-rol]'))) {
                    capturarFormMiembro();
                    formMiembro.rol = el.dataset.fmRol;
                    if (formMiembro.rol !== 'hijo') formMiembro.es_bebe = false;
                    return renderTodo();
                }
                if ((el = ev.target.closest('[data-fm-color]'))) {
                    capturarFormMiembro();
                    formMiembro.color_token = el.dataset.fmColor;
                    return renderTodo();
                }
                if (ev.target.closest('[data-fm-guardar]')) return guardarMiembro();
                if (ev.target.closest('[data-fm-cancelar]')) {
                    formMiembro = null;
                    return renderTodo();
                }
            });

            panelFam.addEventListener('change', function (ev) {
                if (ev.target.closest('[data-fm-bebe]')) {
                    capturarFormMiembro();
                    formMiembro.es_bebe = ev.target.checked;
                    renderTodo();
                }
            });
        }

        // Panel Ajustes: se guarda al tocar el botón (las horas se tipean).
        var panelCfg = $('rut-ajustes');
        if (panelCfg) {
            panelCfg.addEventListener('click', function (ev) {
                if (ev.target.closest('[data-cfg-guardar]')) guardarAjustes();
            });
        }

        $('rut-chips').addEventListener('click', function (ev) {
            var btn = ev.target.closest('[data-user]');
            if (!btn) return;
            var u = btn.dataset.user;
            UI.sel[u] = !UI.sel[u];
            persistirUI();
            renderTodo();
        });

        $('rut-dias').addEventListener('click', function (ev) {
            var btn = ev.target.closest('[data-dia]');
            if (!btn) return;
            UI.dia = Number(btn.dataset.dia);
            editando = null;
            quitando = null;
            persistirUI();
            renderTodo();
        });

        // Handler compartido: la línea de tiempo (#rut-filas) y la tarjeta de
        // calendario (#rut-cal) usan los mismos data-* (el form de añadir
        // puede vivir en cualquiera de los dos).
        function clickTimeline(ev) {
            if (seArrastro) return;   // click fantasma tras mover/estirar
            var t = ev.target;
            var el;
            if ((el = t.closest('[data-menos]'))) return ajustarDesdeFila(el.dataset.menos, -15);
            if ((el = t.closest('[data-mas]'))) return ajustarDesdeFila(el.dataset.mas, +15);
            if ((el = t.closest('[data-poner-ahora]'))) return ajustar(el.dataset.ponerAhora, ahoraMin());
            if (t.closest('.rut-hora-in')) return;   // tipeando la hora: no cerrar
            if (t.closest('[data-cerrar]')) { editando = null; return renderTodo(); }

            // ── Tarjeta "Hoy por calendario" ──
            if ((el = t.closest('[data-cal-x]'))) return descartarCal(Number(el.dataset.calX));
            if ((el = t.closest('[data-cal-add]'))) return abrirFormCal(Number(el.dataset.calAdd));

            // ── Modo edición ──
            if ((el = t.closest('[data-quitar]'))) return abrirQuitar(el.dataset.quitar);
            if ((el = t.closest('[data-q-hoy]'))) return ocultarItem(el.dataset.qHoy, isoLocal(fechaVista()));
            if ((el = t.closest('[data-q-siempre]'))) {
                // Tarea añadida permanente → borrarla de raíz; el resto → oculto permanente
                if (el.dataset.tarea) return borrarTarea(el.dataset.tarea);
                return ocultarItem(el.dataset.qSiempre, '');
            }
            if (t.closest('[data-q-cancelar]')) { quitando = null; return renderTodo(); }
            if ((el = t.closest('[data-restaurar]'))) return restaurarItem(el.dataset.restaurar);
            if (t.closest('[data-add]')) {
                var pri = usuariosSel()[0] || usuarios()[0];
                if (!pri) return;   // familia vacía: nada a lo que añadirle
                formAdd = { en: 'filas', user: pri, emoji: '', titulo: '', hora: 9, min: 0, dur: 30, alcance: 'siempre' };
                renderTodo();
                var inp = $('rut-add-titulo');
                if (inp) inp.focus();
                return;
            }
            if ((el = t.closest('[data-add-user]'))) {
                capturarFormAdd(); formAdd.user = el.dataset.addUser; return renderTodo();
            }
            if ((el = t.closest('[data-add-alcance]'))) {
                capturarFormAdd(); formAdd.alcance = el.dataset.addAlcance; return renderTodo();
            }
            if (t.closest('[data-add-cancelar]')) { formAdd = null; return renderTodo(); }
            if (t.closest('[data-add-guardar]')) return guardarTareaNueva();

            if ((el = t.closest('[data-tap]'))) {
                editando = (editando === el.dataset.tap) ? null : el.dataset.tap;
                renderTodo();
            }
        }
        $('rut-filas').addEventListener('click', clickTimeline);
        $('rut-cal').addEventListener('click', clickTimeline);

        // Click en la tarjeta de calendario: form de añadir prefijado con la
        // tarea (título, persona según responsable, 10:00, 1 h, solo hoy)
        function abrirFormCal(id) {
            var c = null;
            CALHOY.forEach(function (x) { if (!c && x.id === id) c = x; });
            if (!c) return;
            // El Calendario habla de 'elias' | 'mari' | 'familia'; acá la
            // persona es un miembro. Se busca por rol (papá/mamá) y, si no
            // hay, cae en el primero seleccionado.
            var rolBuscado = c.responsable === 'elias' ? 'papa'
                           : c.responsable === 'mari' ? 'mama' : null;
            var persona = null;
            if (rolBuscado) {
                MIEMBROS.forEach(function (m) {
                    if (!persona && m.rol === rolBuscado) persona = String(m.id);
                });
            }
            persona = persona || usuariosSel()[0] || usuarios()[0];
            if (!persona) return;
            formAdd = { en: 'cal', user: persona, emoji: '📅', titulo: c.nombre,
                        hora: 10, min: 0, dur: 60, alcance: 'hoy' };
            renderTodo();
        }

        $('rut-ahora').addEventListener('click', function (ev) {
            var el;
            // "⏱ Empezó ahora" → empezó a esta hora (el anterior termina ahora)
            if ((el = ev.target.closest('[data-empezo]'))) return empezoALas(el.dataset.empezo, ahoraMin());
            // "🕐" → abrir el editor "empezó a las…"
            if ((el = ev.target.closest('[data-ahora-hora]'))) { ahoraHora = el.dataset.ahoraHora; return renderTodo(); }
            if (ev.target.closest('.rut-hora-in')) return;   // tipeando: no cerrar
            if ((el = ev.target.closest('[data-ah-ok]'))) {
                var id = el.dataset.ahOk;
                var cur = buscarItem(id);
                if (cur) {
                    var gv = function (attr, max) {
                        var i = document.querySelector('[' + attr + ']');
                        return Math.min(max, Math.max(0, parseInt(i && i.value, 10) || 0));
                    };
                    var S = gv('data-ah-h', 23) * 60 + gv('data-ah-m', 59);
                    var E = gv('data-ah-eh', 23) * 60 + gv('data-ah-em', 59);
                    var start0 = cur.start, end0 = cur.start + cur.dur;
                    ahoraHora = null;
                    if (S !== start0) empezoALas(id, S);          // mueve el inicio (y el anterior)
                    if (E !== end0) terminaALas(id, E);           // ajusta el fin
                    if (S === start0 && E === end0) renderTodo();
                }
                return;
            }
            if (ev.target.closest('[data-ah-x]')) { ahoraHora = null; return renderTodo(); }
            // "⏳ Aún en {anterior}": estira la anterior hasta ahora +10' y
            // corre la actual a continuación (queda clavada ahí)
            var aun = ev.target.closest('[data-aun]');
            if (aun) {
                var prev = buscarItem(aun.dataset.aun);
                if (!prev) return;
                var nuevoDur = Math.max(5, Math.round((ahoraMin() - prev.start + 10) / 5) * 5);
                ajustarDur(prev.id, nuevoDur);
                if (aun.dataset.aunCur) ajustar(aun.dataset.aunCur, prev.start + nuevoDur);
                return;
            }
            var ir = ev.target.closest('[data-ir]');
            if (ir) irAItem(ir.dataset.ir);
        });

        // Ruedita del mouse sobre los inputs del editor (inicio y fin)
        $('rut-ahora').addEventListener('wheel', function (ev) {
            var inp = ev.target.closest('.rut-hora-in');
            if (!inp) return;
            ev.preventDefault();
            var esH = inp.hasAttribute('data-ah-h') || inp.hasAttribute('data-ah-eh');
            var paso = esH ? 1 : 5, max = esH ? 23 : 59;
            var v = (parseInt(inp.value, 10) || 0) + (ev.deltaY < 0 ? paso : -paso);
            inp.value = Math.max(0, Math.min(max, v));
        }, { passive: false });

        // ── Knob arrastrable en la barra de progreso de la tarjeta "Ahora" ──
        // Arrastrarlo = corregir cuánto avanzó la actividad: la fracción bajo
        // el knob es dónde estamos AHORA dentro de la actividad, así que la
        // duración se recalcula = transcurrido / fracción (el inicio no se
        // mueve; el fin se adelanta o atrasa). Pedido de Mari 2026-07-13.
        var barDrag = null;

        function barPreview(f) {
            var fill = barDrag.bar.querySelector('.rut-barra-fill');
            var knob = barDrag.bar.querySelector('.rut-barra-knob');
            if (fill) fill.style.width = (f * 100) + '%';
            if (knob) knob.style.left = (f * 100) + '%';
        }

        function barMover(clientX) {
            var trans = Math.max(1, barDrag.now - barDrag.start);   // min transcurridos
            var fMin = trans / 720;                                  // dur máx 720
            var f = (clientX - barDrag.left) / Math.max(1, barDrag.w);
            barDrag.f = Math.max(fMin, Math.min(1, f));
            barPreview(barDrag.f);
        }

        function barSoltar() {
            var d = barDrag; barDrag = null;
            if (!d || d.f === null) return;
            var trans = Math.max(1, d.now - d.start);
            var dur = Math.max(5, Math.min(720, Math.round((trans / d.f) / 5) * 5));
            ajustarDur(d.id, dur);
        }

        function barIniciar(bar, clientX) {
            var r = bar.getBoundingClientRect();
            barDrag = { bar: bar, id: bar.dataset.barra, start: +bar.dataset.bstart,
                        now: +bar.dataset.bnow, left: r.left, w: r.width, f: null };
            barMover(clientX);
        }

        $('rut-ahora').addEventListener('mousedown', function (ev) {
            if (ev.button !== 0) return;
            var bar = ev.target.closest('[data-barra]');
            if (!bar) return;
            barIniciar(bar, ev.clientX);
            ev.preventDefault();
        });
        document.addEventListener('mousemove', function (ev) { if (barDrag) barMover(ev.clientX); });
        document.addEventListener('mouseup', function () { if (barDrag) barSoltar(); });

        $('rut-ahora').addEventListener('touchstart', function (ev) {
            if (ev.touches.length !== 1) return;
            var bar = ev.target.closest('[data-barra]');
            if (!bar) return;
            barIniciar(bar, ev.touches[0].clientX);
        }, { passive: true });
        $('rut-ahora').addEventListener('touchmove', function (ev) {
            if (!barDrag) return;
            ev.preventDefault();
            barMover(ev.touches[0].clientX);
        }, { passive: false });
        $('rut-ahora').addEventListener('touchend', function () { if (barDrag) barSoltar(); });

        // Busca el ítem vigente por id en el cálculo actual
        function buscarItem(itemId) {
            var todos = todosLosItems(calcular());
            var it = null;
            todos.forEach(function (i) { if (!it && i.id === itemId) it = i; });
            return it;
        }

        // Hora editable: tipear y salir del input (o Enter) aplica el cambio.
        // Las nocturnas conservan su cruce de medianoche (start >= 1440).
        $('rut-filas').addEventListener('change', function (ev) {
            var t = ev.target;
            var id = t.dataset.horaH || t.dataset.horaM;
            if (!id) return;
            var hEl = document.querySelector('[data-hora-h="' + id + '"]');
            var mEl = document.querySelector('[data-hora-m="' + id + '"]');
            if (!hEl || !mEl) return;
            var h = Math.min(23, Math.max(0, parseInt(hEl.value, 10) || 0));
            var m = Math.min(59, Math.max(0, parseInt(mEl.value, 10) || 0));
            var it = buscarItem(id);
            var base = (it && it.start >= 1440) ? 1440 : 0;
            ajustar(id, base + h * 60 + m);
        });

        // Ruedita del mouse sobre los inputs de hora: ±1 h / ±5 min
        $('rut-filas').addEventListener('wheel', function (ev) {
            var t = ev.target;
            var id = t.dataset.horaH || t.dataset.horaM;
            if (!id) return;
            ev.preventDefault();
            var paso = t.dataset.horaH ? 60 : 5;
            var delta = ev.deltaY < 0 ? paso : -paso;
            var it = buscarItem(id);
            if (it) ajustar(id, Math.max(0, it.start + delta));
        }, { passive: false });

        // ── Drag estilo Teams: mover un ítem (cambia su inicio) o estirarlo
        //    desde la manija inferior (cambia su duración). Mouse: directo,
        //    con umbral de 4 px para no comerse el tap del popover. Táctil:
        //    mover requiere TOQUE SOSTENIDO (350 ms quieto — si el dedo se
        //    desplaza antes, gana el scroll); estirar es directo (la manija
        //    tiene touch-action: none). Durante el drag solo se mueve el
        //    bloque agarrado; la cascada se reacomoda al soltar. ────────────
        var PASO_DRAG = 5;   // snap en minutos

        function dragComenzar(modo, id, el, clientY) {
            var it = buscarItem(id);
            if (!it || !it.editable) return null;
            return {
                modo: modo, id: id, el: el, y0: clientY, activo: false,
                startOrig: it.start, durOrig: it.dur || 30,
                topOrig: parseFloat(el.style.top) || 0,
                hOrig: parseFloat(el.style.height) || 0
            };
        }

        function dragMover(clientY) {
            var dy = clientY - drag.y0;
            if (!drag.activo) {
                if (Math.abs(dy) < 4) return;
                drag.activo = true;
                drag.el.classList.add('is-arrastrando');
                seArrastro = true;
            }
            var minutos = Math.round(dy / ESCALA / PASO_DRAG) * PASO_DRAG;
            if (drag.modo === 'mover') {
                drag.nuevoStart = Math.max(0, drag.startOrig + minutos);
                drag.el.style.top = (drag.topOrig + (drag.nuevoStart - drag.startOrig) * ESCALA) + 'px';
                var hEl = drag.el.querySelector('.rut-item-hora');
                if (hEl) hEl.textContent = fmt(drag.nuevoStart);
            } else {
                drag.nuevaDur = Math.max(5, Math.min(720, drag.durOrig + minutos));
                drag.el.style.height = Math.max(20, Math.round(drag.nuevaDur * ESCALA)) + 'px';
                var dEl = drag.el.querySelector('.rut-item-dur');
                if (dEl) dEl.textContent = fmtDur(drag.nuevaDur);
            }
        }

        function dragSoltar() {
            var d = drag;
            drag = null;
            if (!d) return;
            if (d.timer) clearTimeout(d.timer);
            d.el.classList.remove('is-arrastrando');
            if (!d.activo) return;
            if (d.modo === 'mover' && d.nuevoStart !== undefined && d.nuevoStart !== d.startOrig) {
                ajustar(d.id, d.nuevoStart);
            } else if (d.modo === 'estirar' && d.nuevaDur !== undefined && d.nuevaDur !== d.durOrig) {
                ajustarDur(d.id, d.nuevaDur);
            } else {
                renderTodo();   // volvió al lugar original: restaurar el DOM
            }
            // el click fantasma llega justo después del mouseup/touchend
            setTimeout(function () { seArrastro = false; }, 0);
        }

        $('rut-filas').addEventListener('mousedown', function (ev) {
            if (ev.button !== 0 || modoEdicion || drag) return;
            var g = ev.target.closest('[data-grip]');
            var m = !g && ev.target.closest('[data-drag]');
            if (!g && !m) return;
            var el = ev.target.closest('.rut-item');
            if (!el) return;
            drag = dragComenzar(g ? 'estirar' : 'mover', g ? g.dataset.grip : m.dataset.drag, el, ev.clientY);
            if (drag) ev.preventDefault();   // sin selección de texto
        });
        document.addEventListener('mousemove', function (ev) {
            if (drag && !drag.esTouch) dragMover(ev.clientY);
        });
        document.addEventListener('mouseup', function () {
            if (drag && !drag.esTouch) dragSoltar();
        });

        $('rut-filas').addEventListener('touchstart', function (ev) {
            if (modoEdicion || drag || ev.touches.length !== 1) return;
            var t0 = ev.touches[0];
            var g = ev.target.closest('[data-grip]');
            var m = !g && ev.target.closest('[data-drag]');
            if (!g && !m) return;
            var el = ev.target.closest('.rut-item');
            if (!el) return;
            if (g) {
                drag = dragComenzar('estirar', g.dataset.grip, el, t0.clientY);
                if (drag) drag.esTouch = true;
                return;
            }
            var pend = dragComenzar('mover', m.dataset.drag, el, t0.clientY);
            if (!pend) return;
            pend.esTouch = true;
            pend.pendiente = true;
            pend.timer = setTimeout(function () {
                pend.pendiente = false;
                pend.activo = true;
                pend.el.classList.add('is-arrastrando');
                seArrastro = true;
            }, 350);
            drag = pend;
        }, { passive: true });
        $('rut-filas').addEventListener('touchmove', function (ev) {
            if (!drag || !drag.esTouch) return;
            var ty = ev.touches[0].clientY;
            if (drag.pendiente) {
                // el dedo se movió antes del toque sostenido: es un scroll
                if (Math.abs(ty - drag.y0) > 10) { clearTimeout(drag.timer); drag = null; }
                return;
            }
            ev.preventDefault();
            dragMover(ty);
        }, { passive: false });
        $('rut-filas').addEventListener('touchend', function () {
            if (drag && drag.esTouch) dragSoltar();
        });
        $('rut-filas').addEventListener('touchcancel', function () {
            if (drag && drag.esTouch) {
                if (drag.timer) clearTimeout(drag.timer);
                drag.el.classList.remove('is-arrastrando');
                drag = null;
            }
        });

        // Click en el emoji de una tarjeta "Ahora": scrollea la línea de
        // tiempo hasta ese ítem (lienzo o franja nocturna) y lo destella —
        // para corregir la hora sin buscarla a mano. Salto INSTANTÁNEO:
        // behavior:'smooth' se cancela solo en el contenedor con scroll
        // interno del desktop (Chromium) y el destello ya orienta la vista.
        function irAItem(itemId) {
            var el = document.querySelector('[data-item="' + itemId + '"]');
            if (!el) return;
            el.scrollIntoView({ block: 'center' });
            el.classList.add('is-foco');
            setTimeout(function () {
                var e2 = document.querySelector('[data-item="' + itemId + '"]');
                if (e2) e2.classList.remove('is-foco');
            }, 1800);
        }

        $('rut-reset').addEventListener('click', resetDia);

        $('rut-editar').addEventListener('click', function () {
            modoEdicion = !modoEdicion;
            editando = null;
            quitando = null;
            formAdd = null;
            renderTodo();
        });

        // ✕ en una fila: tarea añadida "solo hoy" se borra directo (solo existe
        // hoy); el resto abre el "¿Solo hoy o siempre?"
        function abrirQuitar(itemId) {
            var calc = calcular();
            var todos = todosLosItems(calc);
            var it = null;
            todos.forEach(function (i) { if (!it && i.id === itemId) it = i; });
            if (it && it.custom && !it.permanente) return borrarTarea(it.tareaId);
            quitando = (quitando === itemId) ? null : itemId;
            renderTodo();
        }

        function guardarTareaNueva() {
            capturarFormAdd();
            var titulo = (formAdd.titulo || '').trim();
            if (!titulo) {
                var inp = $('rut-add-titulo');
                if (inp) { inp.classList.add('rut-add-error'); inp.focus(); }
                return;
            }
            crearTarea({
                etapa: ETAPA,
                usuario: formAdd.user,
                titulo: titulo,
                emoji: (formAdd.emoji || '').trim(),
                inicio_min: formAdd.hora * 60 + formAdd.min,
                dur: formAdd.dur,
                fecha: formAdd.alcance === 'hoy' ? isoLocal(fechaVista()) : ''
            });
            renderTodo();
        }

        // −15/+15 parten del inicio VIGENTE del ítem (con cascada aplicada)
        function ajustarDesdeFila(itemId, delta) {
            var calc = calcular();
            var todos = todosLosItems(calc);
            var it = null;
            todos.forEach(function (i) { if (!it && i.id === itemId) it = i; });
            if (it) ajustar(itemId, it.start + delta);
        }

        window.addEventListener('resize', ajustarSticky);
        renderTodo();
        // Remedir cuando terminan de cargar fuentes/estáticos (el alto del
        // topbar global puede cambiar entre DOMContentLoaded y load).
        window.addEventListener('load', ajustarSticky);

        // Reloj vivo + sync entre teléfonos (30 s); sync extra al volver a la app.
        // El tick se saltea en modo edición, con un popover abierto (editando)
        // o durante un drag: el re-render pisaría lo que se está haciendo.
        setInterval(function () { if (!modoEdicion && !editando && !drag && !ahoraHora) syncAjustes(); }, 30000);
        document.addEventListener('visibilitychange', function () {
            if (!document.hidden && !modoEdicion && !editando && !drag && !ahoraHora) syncAjustes();
        });
    }

    document.addEventListener('DOMContentLoaded', init);
})();
