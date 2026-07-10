/*
================================================================================
ARCHIVO: static/rutina.js
================================================================================
Lógica cliente del módulo Rutina. Se carga SOLO en /rutina
(templates/rutina.html, bloque scripts). Vanilla JS, sin librerías. Todo vive
dentro de una IIFE para no pisar los globales de app.js.

FUENTE DE VERDAD:
  - ETAPAS (constante acá): definición de la rutina por etapa — cadenas de
    ítems de León, tomas nocturnas, agendas de mamá/papá, variantes de finde
    y tips. Port literal del design handoff "Rutina" (Word "Rutina de León").
  - window.RUTINA_ACTIVIDADES (static/rutina-actividades.js): 82 actividades
    de estimulación de la guía "Estimulación Temprana" (Karina Rivera).
  - window.RUT_DATOS = { ajustes, hoy, desde, hasta }: ajustes de horario
    persistidos en SQLite (tabla rutina_ajustes), sincronizados entre ambos
    teléfonos. Shape: ajustes[fecha][etapa][item_id] = inicioEnMinutos.
  - localStorage 'rutina-ui-v1' = { sel, dia, etapa }: selección de UI por
    dispositivo (NO se sincroniza; decisión de diseño).

REGLA DE CASCADA: ajustar un ítem NO mueve los anteriores; los siguientes sin
ajuste propio se re-encadenan (inicio = fin del anterior). Un ítem con ajuste
propio queda clavado hasta que se resetee ("↺ Plan original" borra todos los
ajustes de la fecha+etapa visibles).

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

    // ── Definición de rutina por etapa (port literal del handoff) ───────────
    // ItemLeon  = { id, emoji, t, dur (min; 0 = fin del día), kind, sub?, act? }
    //             act: true → el sub se reemplaza por la actividad del día.
    // Nocturna  = { id, off (min desde inicio del sueño nocturno), emoji, t, sub? }
    // ItemAdulto= { id, clock (min absolutos), emoji, t, dur, sub? }  → editable
    //           | { link: <idItemLeon>, emoji, t, sub? } → hereda horario, NO editable
    var ETAPAS = {
        actual: {
            nombre: '2 meses', sup: 'Hoy · licencia', anchor: 390,
            leon: [
                { id: 'desp', emoji: '🌅', t: 'Despertar + teta ancla', dur: 30, kind: 'teta', sub: 'La toma clave: en septiembre será la de antes de salir a trabajar. Pañal y luz natural.' },
                { id: 'juego1', emoji: '🧸', t: 'Vigilia 1 — juego', dur: 75, kind: 'juego', act: true },
                { id: 'siesta1', emoji: '😴', t: 'Siesta 1', dur: 75, kind: 'sueno', sub: 'A upa, cochecito o cuna. Penumbra suave' },
                { id: 'teta2', emoji: '🤱', t: 'Teta 2', dur: 25, kind: 'teta', sub: 'A demanda: si pide antes, adelantá y todo se corre' },
                { id: 'juego2', emoji: '🚶', t: 'Vigilia 2 — paseo', dur: 50, kind: 'juego', act: true },
                { id: 'siesta2', emoji: '😴', t: 'Siesta 2', dur: 75, kind: 'sueno', sub: 'Suele ser una de las más largas' },
                { id: 'teta3', emoji: '🤱', t: 'Teta 3', dur: 25, kind: 'teta' },
                { id: 'juego3', emoji: '🧸', t: 'Vigilia 3 — juego', dur: 50, kind: 'juego', act: true },
                { id: 'siesta3', emoji: '😴', t: 'Siesta 3', dur: 90, kind: 'sueno' },
                { id: 'teta4', emoji: '🤱', t: 'Teta 4', dur: 25, kind: 'teta' },
                { id: 'juego4', emoji: '🧸', t: 'Vigilia 4 — juego', dur: 50, kind: 'juego', act: true },
                { id: 'siesta4', emoji: '😴', t: 'Siesta 4 (puente)', dur: 60, kind: 'sueno', sub: 'Corta, para llegar bien a la noche' },
                { id: 'teta5', emoji: '🤱', t: 'Teta 5', dur: 25, kind: 'teta' },
                { id: 'brazos', emoji: '🫂', t: 'Upa y movimiento', dur: 50, kind: 'juego', sub: 'Momento de mayor fastidio del día: paciencia, upa, porteo' },
                { id: 'siesta5', emoji: '😴', t: 'Micro-siesta (opcional)', dur: 45, kind: 'sueno', sub: 'Si la necesita para no llegar pasado de sueño' },
                { id: 'bano', emoji: '🛁', t: 'Baño', dur: 15, kind: 'bano', sub: 'Inicio del ritual: siempre igual, mismo orden' },
                { id: 'ultimateta', emoji: '🤱', t: 'Teta 6 + arrullo', dur: 25, kind: 'teta', sub: 'Luz baja. A la cuna despierto-adormecido si se puede' },
                { id: 'noche', emoji: '🌙', t: 'Sueño nocturno', dur: 0, kind: 'noche', sub: 'Boca arriba, cuna despejada (AAP). Chupete puede ofrecerse' },
            ],
            nocturnas: [
                { id: 'noct1', off: 210, emoji: '🤱', t: 'Toma nocturna 1', sub: 'A demanda. Luz mínima, sin jugar' },
                { id: 'noct2', off: 420, emoji: '🤱', t: 'Toma nocturna 2', sub: '2–3 despertares son normales a esta edad' },
                { id: 'noct3', off: 570, emoji: '🤱', t: 'Toma nocturna 3', sub: 'Si la pide' },
            ],
            mama: [
                { link: 'siesta1', emoji: '🚿', t: 'Ducha, desayuno y tareas', sub: 'mientras León duerme 😴' },
                { link: 'siesta2', emoji: '🏋️', t: 'Gimnasia', sub: 'mientras León duerme 😴' },
                { link: 'siesta3', emoji: '🍽️', t: 'Almuerzo + descanso', sub: 'mientras León duerme 😴' },
                { link: 'siesta4', emoji: '📚', t: 'Estudio / proyecto', sub: 'mientras León duerme 😴' },
                { link: 'siesta5', emoji: '🍼', t: 'Extracción (banco de leche)', sub: 'mientras León duerme 😴' },
                { id: 'm-cena', clock: 1230, emoji: '🍽️', t: 'Cena con Elías', dur: 45 },
                { id: 'm-dormir', clock: 1350, emoji: '😴', t: 'A dormir', dur: 0 },
            ],
            papa: [
                { id: 'p-desp', clock: 405, emoji: '🌅', t: 'Despertar', dur: 45 },
                { id: 'p-salir', clock: 450, emoji: '🚗', t: 'Salir al trabajo', dur: 30 },
                { id: 'p-am', clock: 480, emoji: '💼', t: 'Trabajo (Villa María)', dur: 300 },
                { id: 'p-alm', clock: 780, emoji: '🍽️', t: 'Almuerzo', dur: 60 },
                { id: 'p-pm', clock: 840, emoji: '💼', t: 'Trabajo', dur: 180 },
                { id: 'p-leon', clock: 1040, emoji: '🫂', t: 'Upa con León', dur: 100, sub: 'Refuerzo en la hora sensible' },
                { id: 'p-cena', clock: 1230, emoji: '🍽️', t: 'Cena con Mari', dur: 45 },
                { id: 'p-dormir', clock: 1380, emoji: '😴', t: 'A dormir', dur: 0 },
            ],
            papaFinde: [
                { link: 'juego2', emoji: '🚶', t: 'Paseo familiar', sub: 'con León y Mari' },
                { link: 'siesta3', emoji: '🧺', t: 'Tareas de la casa' },
                { link: 'brazos', emoji: '🫂', t: 'Upa con León' },
                { id: 'pf-cena', clock: 1230, emoji: '🍳', t: 'Cocinar y cenar', dur: 60 },
            ],
            tips: [
                { texto: 'Ventanas de 60–90 min (la primera del día es la más corta). Señales de sueño — bostezo, mirada perdida, quejoso — mandan más que el reloj.' },
                { texto: '14–17 h de sueño en 24 h: ninguna siesta de más de 2 h, noche de hasta 12–12,5 h.' },
                { texto: 'Teta a demanda cada 2–4 h: la tabla se adapta a León, no al revés. Manos a la boca y buscar el pecho = ofrecer antes (el llanto es señal tardía).' },
                { texto: 'De tu guía: practicá mínimo 2 actividades por día (o las 4 si hay tiempo). Anticipale siempre a León lo que van a hacer.' },
            ],
        },
        tres: {
            nombre: '3 meses', sup: 'Agosto · transición', anchor: 390,
            leon: [
                { id: 't-desp', emoji: '🌅', t: 'Despertar + teta ancla', dur: 30, kind: 'teta', sub: 'Ir corriéndola 10–15 min/semana hacia las 6:15–6:30 fijas' },
                { id: 't-juego1', emoji: '🧸', t: 'Vigilia 1 — juego', dur: 65, kind: 'juego', act: true },
                { id: 't-siesta1', emoji: '😴', t: 'Siesta 1 (corta)', dur: 70, kind: 'sueno', sub: 'La de la mañana se va acortando' },
                { id: 't-teta2', emoji: '🤱', t: 'Teta 2', dur: 25, kind: 'teta' },
                { id: 't-juego2', emoji: '🚶', t: 'Vigilia 2 — paseo', dur: 70, kind: 'juego', act: true },
                { id: 't-siesta2', emoji: '😴', t: 'Siesta 2 (la larga)', dur: 100, kind: 'sueno', sub: 'La larga del mediodía se instala' },
                { id: 't-teta3', emoji: '🤱', t: 'Teta 3', dur: 25, kind: 'teta' },
                { id: 't-juego3', emoji: '🧸', t: 'Vigilia 3 — juego', dur: 75, kind: 'juego', act: true },
                { id: 't-siesta3', emoji: '😴', t: 'Siesta 3', dur: 75, kind: 'sueno' },
                { id: 't-teta4', emoji: '🤱', t: 'Teta 4', dur: 25, kind: 'teta' },
                { id: 't-juego4', emoji: '🫂', t: 'Vigilia 4 — upa y calma', dur: 80, kind: 'juego', act: true },
                { id: 't-siesta4', emoji: '😴', t: 'Siesta 4 (puente)', dur: 40, kind: 'sueno' },
                { id: 't-teta5', emoji: '🤱', t: 'Teta 5', dur: 25, kind: 'teta' },
                { id: 't-calma', emoji: '🧸', t: 'Juego calmo', dur: 45, kind: 'juego', sub: 'Luces bajas, bajar revoluciones' },
                { id: 't-bano', emoji: '🛁', t: 'Baño', dur: 15, kind: 'bano', sub: 'Mismo ritual, mismo orden' },
                { id: 't-teta6', emoji: '🤱', t: 'Teta 6 + arrullo', dur: 25, kind: 'teta' },
                { id: 't-noche', emoji: '🌙', t: 'Sueño nocturno', dur: 0, kind: 'noche', sub: 'Boca arriba, cuna despejada (AAP)' },
            ],
            nocturnas: [
                { id: 't-noct1', off: 240, emoji: '🤱', t: 'Toma nocturna 1', sub: 'Luz mínima, sin jugar' },
                { id: 't-noct2', off: 480, emoji: '🤱', t: 'Toma nocturna 2', sub: 'Puede empezar a espaciarse' },
            ],
            mama: [
                { link: 't-siesta1', emoji: '🚿', t: 'Ducha, desayuno y tareas', sub: 'mientras León duerme 😴' },
                { link: 't-siesta2', emoji: '🏋️', t: 'Gimnasia', sub: 'mientras León duerme 😴' },
                { link: 't-siesta3', emoji: '🍽️', t: 'Almuerzo + estudio', sub: 'mientras León duerme 😴' },
                { link: 't-siesta4', emoji: '🍼', t: 'Extracción (banco de leche)', sub: 'stock para la guardería' },
                { id: 'tm-cena', clock: 1230, emoji: '🍽️', t: 'Cena con Elías', dur: 45 },
                { id: 'tm-dormir', clock: 1350, emoji: '😴', t: 'A dormir', dur: 0 },
            ],
            papa: [
                { id: 'tp-desp', clock: 405, emoji: '🌅', t: 'Despertar', dur: 45 },
                { id: 'tp-salir', clock: 450, emoji: '🚗', t: 'Salir al trabajo', dur: 30 },
                { id: 'tp-am', clock: 480, emoji: '💼', t: 'Trabajo (Villa María)', dur: 300 },
                { id: 'tp-alm', clock: 780, emoji: '🍽️', t: 'Almuerzo', dur: 60 },
                { id: 'tp-pm', clock: 840, emoji: '💼', t: 'Trabajo', dur: 180 },
                { id: 'tp-leon', clock: 1040, emoji: '🫂', t: 'Upa con León', dur: 100 },
                { id: 'tp-cena', clock: 1230, emoji: '🍽️', t: 'Cena con Mari', dur: 45 },
                { id: 'tp-dormir', clock: 1380, emoji: '😴', t: 'A dormir', dur: 0 },
            ],
            papaFinde: [
                { link: 't-juego2', emoji: '🚶', t: 'Paseo familiar' },
                { link: 't-siesta3', emoji: '🧺', t: 'Tareas de la casa' },
                { link: 't-juego4', emoji: '🫂', t: 'Upa con León' },
                { id: 'tpf-cena', clock: 1230, emoji: '🍳', t: 'Cocinar y cenar', dur: 60 },
            ],
            tips: [
                { texto: 'Ventanas de 60 min hacia 2 h. Si pelea las siestas o despierta temprano, alargá la ventana 10–15 min.' },
                { texto: 'Las siestas se ordenan: corta a la mañana, la larga al mediodía. Cuando una desaparece sola, juntó dos en una (de 5 a 4).' },
                { texto: 'Mantené fijas las dos anclas: teta al despertar y ritual de noche. Todo lo demás puede moverse.' },
            ],
        },
        guarderia: {
            nombre: '4 meses · guardería', sup: 'Sep — quizás antes (adaptación)', anchor: 375,
            leon: [
                { id: 'g-desp', emoji: '🌅', t: 'Despertar + teta ancla con mamá', dur: 30, kind: 'teta', sub: 'Recién despierto, para salir sin hambre. Si duerme profundo, despertarlo suave' },
                { id: 'g-prep', emoji: '🧦', t: 'Listo con papá', dur: 20, kind: 'juego', sub: 'Mamá sale 6:40. Bolso: leche del banco, pañales, mudas, chupete' },
                { id: 'g-viaje', emoji: '🚗', t: 'Papá lo lleva a la guardería', dur: 15, kind: 'juego' },
                { id: 'g-guar', emoji: '🏫', t: 'Guardería', dur: 580, kind: 'guarderia', sub: 'Leche del banco a demanda. Pedir el parte diario de siestas y tomas' },
                { id: 'g-retiro', emoji: '🚗', t: 'Papá lo retira, vuelven a casa', dur: 40, kind: 'juego' },
                { id: 'g-teta1', emoji: '🤱', t: 'Teta del reencuentro', dur: 40, kind: 'teta', sub: 'Mamá ya volvió de Tío Pujio' },
                { id: 'g-juego', emoji: '🧸', t: 'Juego calmo en casa', dur: 30, kind: 'juego', act: true },
                { id: 'g-bano', emoji: '🛁', t: 'Baño', dur: 15, kind: 'bano', sub: 'Mismo ritual de siempre: viaja con él aunque el día cambie' },
                { id: 'g-teta2', emoji: '🤱', t: 'Teta + arrullo', dur: 25, kind: 'teta' },
                { id: 'g-noche', emoji: '🌙', t: 'Sueño nocturno (temprano)', dur: 0, kind: 'noche', sub: 'Noche 18:30–19:30 compensa si durmió poco en la guardería' },
            ],
            nocturnas: [{ id: 'g-noct1', off: 480, emoji: '🤱', t: 'Toma nocturna', sub: 'Regresión de los 4 meses: más despertares es normal y pasajero' }],
            mama: [
                { id: 'gm-desp', clock: 360, emoji: '🌅', t: 'Se levanta y se prepara', dur: 15 },
                { link: 'g-desp', emoji: '🤱', t: 'Teta ancla a León', sub: 'antes de salir' },
                { id: 'gm-viaje', clock: 400, emoji: '🚗', t: 'Sale hacia Tío Pujio', dur: 45 },
                { id: 'gm-am', clock: 480, emoji: '💼', t: 'Trabajo', dur: 270 },
                { id: 'gm-ext', clock: 750, emoji: '🍼', t: 'Almuerzo + extracción', dur: 45, sub: 'Mantiene producción y banco de leche' },
                { id: 'gm-pm', clock: 795, emoji: '💼', t: 'Trabajo', dur: 195 },
                { id: 'gm-vuelta', clock: 990, emoji: '🚗', t: 'Vuelta a Villa María', dur: 50 },
                { link: 'g-teta1', emoji: '🤱', t: 'Teta del reencuentro' },
                { id: 'gm-cena', clock: 1230, emoji: '🍽️', t: 'Cena con Elías', dur: 45 },
                { id: 'gm-dormir', clock: 1330, emoji: '😴', t: 'A dormir', dur: 0 },
            ],
            mamaFinde: [
                { link: 'f-siesta1', emoji: '🚿', t: 'Ducha y desayuno', sub: 'mientras León duerme 😴' },
                { link: 'f-paseo', emoji: '🚶', t: 'Paseo familiar' },
                { link: 'f-siesta2', emoji: '🏋️', t: 'Gimnasia / descanso', sub: 'mientras León duerme 😴' },
                { link: 'f-siesta3', emoji: '🍼', t: 'Extracción (banco de leche)' },
                { id: 'gmf-cena', clock: 1230, emoji: '🍽️', t: 'Cena con Elías', dur: 45 },
            ],
            papa: [
                { id: 'gp-desp', clock: 390, emoji: '🌅', t: 'Despertar', dur: 15 },
                { link: 'g-prep', emoji: '🧦', t: 'Prepara a León' },
                { link: 'g-viaje', emoji: '🚗', t: 'Lo lleva a la guardería' },
                { id: 'gp-am', clock: 480, emoji: '💼', t: 'Trabajo (Villa María)', dur: 300 },
                { id: 'gp-alm', clock: 780, emoji: '🍽️', t: 'Almuerzo', dur: 60 },
                { id: 'gp-pm', clock: 840, emoji: '💼', t: 'Trabajo', dur: 180 },
                { link: 'g-retiro', emoji: '🚗', t: 'Retira a León' },
                { link: 'g-juego', emoji: '🧸', t: 'Juego con León' },
                { id: 'gp-cena', clock: 1200, emoji: '🍳', t: 'Cocina y cenan', dur: 75 },
                { id: 'gp-dormir', clock: 1380, emoji: '😴', t: 'A dormir', dur: 0 },
            ],
            papaFinde: [
                { link: 'f-paseo', emoji: '🚶', t: 'Paseo familiar' },
                { link: 'f-juego2', emoji: '🧸', t: 'Juego con León' },
                { id: 'gpf-cena', clock: 1200, emoji: '🍳', t: 'Cocina y cenan', dur: 75 },
            ],
            finde: [
                { id: 'f-desp', emoji: '🌅', t: 'Despertar + teta', dur: 30, kind: 'teta', sub: 'Finde: sin madrugón, pero misma ancla' },
                { id: 'f-juego1', emoji: '🧸', t: 'Vigilia 1 — juego', dur: 80, kind: 'juego', act: true },
                { id: 'f-siesta1', emoji: '😴', t: 'Siesta 1', dur: 90, kind: 'sueno' },
                { id: 'f-teta2', emoji: '🤱', t: 'Teta', dur: 30, kind: 'teta' },
                { id: 'f-paseo', emoji: '🚶', t: 'Paseo familiar', dur: 105, kind: 'juego', act: true },
                { id: 'f-siesta2', emoji: '😴', t: 'Siesta 2 (la larga)', dur: 95, kind: 'sueno' },
                { id: 'f-teta3', emoji: '🤱', t: 'Teta', dur: 30, kind: 'teta' },
                { id: 'f-juego2', emoji: '🧸', t: 'Vigilia 3 — juego', dur: 105, kind: 'juego', act: true },
                { id: 'f-siesta3', emoji: '😴', t: 'Siesta 3 (puente)', dur: 45, kind: 'sueno' },
                { id: 'f-calma', emoji: '🫂', t: 'Juego calmo', dur: 60, kind: 'juego' },
                { id: 'f-bano', emoji: '🛁', t: 'Baño', dur: 15, kind: 'bano' },
                { id: 'f-teta4', emoji: '🤱', t: 'Teta + arrullo', dur: 25, kind: 'teta' },
                { id: 'f-noche', emoji: '🌙', t: 'Sueño nocturno', dur: 0, kind: 'noche' },
            ],
            tips: [
                { texto: 'A los 4 meses: ventanas de 90–120 min, 3–4 siestas, noche de 11–12 h. La "regresión de los 4 meses" es normal y pasajera.' },
                { texto: 'Semanas previas: corré despertar y teta ancla 10–15 min/semana hacia las 6:15–6:30, y adelantá la noche (18:30–19:30).' },
                { texto: 'La licencia de mamá va del 23/04 al 23/09. Si la adaptación de guardería arranca antes, usá esta etapa esos días y ajustá las horas.' },
            ],
        },
    };

    var NACIMIENTO = new Date(2026, 4, 14);   // León, 14/05/2026
    var NOMBRES = { leon: 'León', mama: 'Mamá', papa: 'Papá' };
    var EMOJIS = { leon: '🦁', mama: '💜', papa: '💙' };
    var ORDEN_ETAPAS = ['actual', 'tres', 'guarderia'];
    var LS_KEY = 'rutina-ui-v1';

    // ── Estado del módulo ────────────────────────────────────────────────────
    var RUT = window.RUT_DATOS || { ajustes: {}, hoy: '', desde: '', hasta: '' };
    var AJUSTES = RUT.ajustes || {};       // fecha → etapa → item_id → min (server)
    var DESDE = RUT.desde || '';
    var HASTA = RUT.hasta || '';
    var UI = cargarUI();                   // { sel, dia, etapa } — por dispositivo
    var editando = null;                   // item_id con editor inline abierto
    var timers = {};                       // item_id → timeout del POST debounced
    var enVuelo = 0;                       // POSTs en curso
    var sinSync = false;                   // último POST/GET falló (offline)

    function $(id) { return document.getElementById(id); }

    function cargarUI() {
        var g = {};
        try { g = JSON.parse(localStorage.getItem(LS_KEY) || '{}'); } catch (e) {}
        return {
            sel: g.sel || { leon: true, mama: true, papa: false },
            dia: (g.dia !== undefined ? g.dia : new Date().getDay()),
            etapa: ORDEN_ETAPAS.indexOf(g.etapa) >= 0 ? g.etapa : 'actual'
        };
    }

    function persistirUI() {
        try { localStorage.setItem(LS_KEY, JSON.stringify(UI)); } catch (e) {}
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
        return (AJUSTES[fecha] || {})[UI.etapa] || {};
    }

    function hayPendientes() {
        return enVuelo > 0 || Object.keys(timers).length > 0;
    }

    // ── Cálculo del día (port literal del prototipo) ─────────────────────────
    // Cascada: run = anchor; start = ajuste ?? run; end = start + dur; run = end.
    // Nocturnas: start = inicio del sueño nocturno + off (dur fija 25).
    // Adultos link: hereda horario del ítem de León (end mín. 30 min), NO editable.
    // Adultos clock: minutos absolutos, editable.
    function calcular() {
        var R = ETAPAS[UI.etapa];
        var aj = ajustesDia();
        var usaFinde = esFinde() && R.finde;
        var chain = usaFinde ? R.finde : R.leon;

        // Actividad de estimulación del día (rota con la fecha, estable durante el día)
        var A = window.RUTINA_ACTIVIDADES || { m2: [], m3: [], m46: [] };
        var pool = UI.etapa === 'actual' ? A.m2 : UI.etapa === 'tres' ? A.m3 : A.m46;
        var seed = Math.floor(fechaVista().getTime() / 86400000);
        var slot = 0;

        var run = R.anchor;
        var leon = [];
        var porId = {};
        chain.forEach(function (it) {
            var start = (aj[it.id] !== undefined) ? aj[it.id] : run;
            var sub = it.sub;
            if (it.act && pool.length) {
                var a = pool[(seed * 3 + slot * 7) % pool.length];
                sub = '✨ ' + a.n + ' (' + a.d + ', ' + a.min + '): ' + a.p;
                slot++;
            }
            var item = Object.assign({}, it, { sub: sub, start: start, end: start + it.dur, user: 'leon', editable: true });
            leon.push(item);
            porId[it.id] = item;
            run = start + it.dur;
        });
        var noche = leon[leon.length - 1];
        (R.nocturnas || []).forEach(function (n) {
            var start = (aj[n.id] !== undefined) ? aj[n.id] : noche.start + n.off;
            var item = Object.assign({}, n, { dur: 25, start: start, end: start + 25, user: 'leon', kind: 'noct', editable: true });
            leon.push(item);
            porId[n.id] = item;
        });
        function expandir(defs, user) {
            return defs.map(function (d) {
                if (d.link) {
                    var L = porId[d.link];
                    if (!L) return null;
                    return Object.assign({}, d, {
                        id: user + '-' + d.link, start: L.start,
                        end: Math.max(L.end, L.start + 30), dur: L.dur || 30,
                        user: user, editable: false, kind: d.kind || 'adulto'
                    });
                }
                if (d.clock === undefined) return null;
                var start = (aj[d.id] !== undefined) ? aj[d.id] : d.clock;
                return Object.assign({}, d, {
                    start: start, end: start + (d.dur || 0),
                    user: user, editable: true, kind: d.kind || 'adulto'
                });
            }).filter(Boolean);
        }
        var mamaDefs = (esFinde() && R.mamaFinde) ? R.mamaFinde : (R.mama || []);
        var papaDefs = esFinde() ? (R.papaFinde || []) : (R.papa || []);
        return { leon: leon, mama: expandir(mamaDefs, 'mama'), papa: expandir(papaDefs, 'papa'), R: R };
    }

    // ── Mutaciones (optimistic + debounce; el server guarda por fecha) ──────
    function ajustar(itemId, min) {
        min = Math.max(0, min);
        var fecha = isoLocal(fechaVista());
        if (!AJUSTES[fecha]) AJUSTES[fecha] = {};
        if (!AJUSTES[fecha][UI.etapa]) AJUSTES[fecha][UI.etapa] = {};
        AJUSTES[fecha][UI.etapa][itemId] = min;
        renderTodo();

        if (timers[itemId]) clearTimeout(timers[itemId]);
        timers[itemId] = setTimeout(function () {
            delete timers[itemId];
            var valor = ((AJUSTES[fecha] || {})[UI.etapa] || {})[itemId];
            if (valor === undefined) return;   // el día se reseteó mientras tanto
            postAccion('/api/rutina/ajustar', {
                fecha: fecha, etapa: UI.etapa, item_id: itemId, inicio_min: valor
            });
        }, 400);
    }

    function resetDia() {
        var fecha = isoLocal(fechaVista());
        if (AJUSTES[fecha]) delete AJUSTES[fecha][UI.etapa];
        editando = null;
        renderTodo();
        postAccion('/api/rutina/reset', { fecha: fecha, etapa: UI.etapa });
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
                DESDE = data.desde;
                HASTA = data.hasta;
            }
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
                DESDE = data.desde;
                HASTA = data.hasta;
            }
        })
        .catch(function () { /* offline: el reloj sigue con estado local */ })
        .finally(function () { renderTodo(); });
    }

    // ── Render ───────────────────────────────────────────────────────────────
    function renderHeader() {
        $('rut-fecha').textContent = new Date().toLocaleDateString('es-AR',
            { weekday: 'long', day: 'numeric', month: 'long' });
        var edad;
        if (UI.etapa === 'guarderia') edad = '4 meses (proyección)';
        else if (UI.etapa === 'tres') edad = '3 meses (proyección)';
        else {
            var diasEdad = Math.floor((Date.now() - NACIMIENTO.getTime()) / 86400000);
            edad = Math.floor(diasEdad / 7) + ' semanas';
        }
        $('rut-edad').textContent = edad;
    }

    function renderChips() {
        $('rut-chips').innerHTML = ['leon', 'mama', 'papa'].map(function (u) {
            return '<button type="button" class="rut-chip rut--' + u +
                (UI.sel[u] ? ' activo' : '') + '" data-user="' + u + '">' +
                EMOJIS[u] + ' ' + NOMBRES[u] + '</button>';
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

    function renderEtapas() {
        $('rut-etapas').innerHTML = ORDEN_ETAPAS.map(function (e) {
            var d = ETAPAS[e];
            return '<button type="button" class="rut-etapa-btn' +
                (UI.etapa === e ? ' activo' : '') + '" data-etapa="' + e + '">' +
                '<span class="rut-etapa-sup">' + escapeHtml(d.sup) + '</span>' +
                '<span class="rut-etapa-nombre">' + escapeHtml(d.nombre) + '</span>' +
                '</button>';
        }).join('');
    }

    function renderAviso(esHoy) {
        var el = $('rut-aviso');
        var partes = [];
        if (!esHoy) {
            var nombreDia = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'][UI.dia];
            partes.push(UI.etapa === 'guarderia'
                ? '👀 Proyección: día tipo con guardería (mamá vuelve al trabajo el 23/09; si la adaptación arranca antes, usá esta etapa).'
                : UI.etapa === 'tres'
                    ? '👀 Proyección: así se ajusta la rutina en agosto, a los 3 meses.'
                    : '👀 Estás viendo el plan tipo del ' + nombreDia + '. Volvé al día de hoy para seguir la rutina en vivo.');
        }
        if (sinSync) {
            partes.push('⚠ Sin conexión: el último ajuste quedó en este teléfono y no se sincronizó.');
        }
        el.hidden = partes.length === 0;
        el.innerHTML = partes.map(escapeHtml).join('<br>');
    }

    function renderAhora(items, leon, esHoy, now, nocheItem, nocheActiva, enCurso) {
        var cont = $('rut-ahora');
        if (!esHoy) { cont.innerHTML = ''; return; }
        var html = '';
        ['leon', 'mama', 'papa'].forEach(function (u) {
            if (!UI.sel[u]) return;
            var propios = items.filter(function (i) { return i.user === u; });
            var cur = null;
            propios.forEach(function (i) { if (!cur && enCurso(i)) cur = i; });
            if (!cur && u === 'leon' && nocheActiva) cur = nocheItem;
            var sig = null;
            propios.forEach(function (i) { if (!sig && i.start > now) sig = i; });
            if (!cur && !sig) return;
            var el = cur || { emoji: '⏳', t: 'Tiempo libre', start: now, end: sig ? sig.start : now + 30, sub: '', dur: 1, editable: false };
            var pct = Math.round(Math.min(100, Math.max(3, ((now - el.start) / Math.max(1, (el.end - el.start))) * 100)));
            var rango = fmt(el.start) + ' – ' + (el.dur === 0 ? '…' : fmt(el.end));
            var editable = !!(cur && cur.editable && u === 'leon');
            html += '<div class="rut-card-ahora rut--' + u + '">' +
                '<div class="rut-ahora-head">' +
                    '<span class="rut-ahora-quien">' + EMOJIS[u] + ' ' + NOMBRES[u] + ' · ahora</span>' +
                    '<span class="rut-ahora-rango">' + rango + '</span>' +
                '</div>' +
                '<div class="rut-ahora-cuerpo">' +
                    '<span class="rut-ahora-emoji">' + el.emoji + '</span>' +
                    '<div class="rut-ahora-texto">' +
                        '<div class="rut-ahora-titulo">' + escapeHtml(el.t) + '</div>' +
                        (el.sub ? '<div class="rut-ahora-sub">' + escapeHtml(el.sub) + '</div>' : '') +
                    '</div>' +
                '</div>' +
                '<div class="rut-barra"><div class="rut-barra-fill" style="width:' + pct + '%"></div></div>' +
                '<div class="rut-ahora-pie">' +
                    '<span class="rut-ahora-luego">luego: ' + (sig ? sig.emoji : '🌙') + ' ' +
                        escapeHtml(sig ? sig.t : 'fin del día') +
                        ' · <span class="rut-mono">' + (sig ? fmt(sig.start) : '—') + '</span></span>' +
                    (editable ? '<button type="button" class="rut-btn-empezo" data-empezo="' + cur.id + '">⏱ Empezó ahora</button>' : '') +
                '</div>' +
            '</div>';
        });
        cont.innerHTML = html;
    }

    function renderTimeline(items, esHoy, now, nocheActiva, enCurso) {
        var html = items.map(function (it) {
            var activa = enCurso(it) || (it.kind === 'noche' && nocheActiva);
            var clases = 'rut-fila rut--' + it.user;
            if (it.kind && it.kind !== 'adulto' && it.kind !== 'juego') clases += ' rut-fila--' + it.kind;
            if (activa) clases += ' is-ahora';
            var tapAttr = it.editable ? ' data-tap="' + it.id + '"' : '';
            var fila = '<div class="' + clases + '">' +
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
                    '<span class="rut-fila-dur">' + fmtDur(it.dur) + '</span>' +
                '</div>';
            if (editando === it.id && it.editable) {
                fila += '<div class="rut-editor">' +
                    '<button type="button" class="rut-editor-btn" data-menos="' + it.id + '">−15</button>' +
                    '<span class="rut-editor-hora">' + fmt(it.start) + '</span>' +
                    '<button type="button" class="rut-editor-btn" data-mas="' + it.id + '">+15</button>' +
                    '<button type="button" class="rut-editor-ahora" data-poner-ahora="' + it.id + '">Ahora</button>' +
                    '<button type="button" class="rut-editor-ok" data-cerrar="1">OK</button>' +
                '</div>';
            }
            return fila + '</div>';
        }).join('');
        $('rut-filas').innerHTML = html;
    }

    function renderTips(R) {
        var titulo = UI.etapa === 'guarderia' ? 'Qué cambia a los 4 meses'
            : UI.etapa === 'tres' ? 'Qué cambia a los 3 meses'
            : 'Lo que dicen los expertos (2 meses)';
        $('rut-tips').innerHTML = '<div class="rut-tips-card">' +
            '<div class="rut-tips-titulo">📖 ' + escapeHtml(titulo) + '</div>' +
            R.tips.map(function (t) {
                return '<div class="rut-tip">• ' + escapeHtml(t.texto) + '</div>';
            }).join('') +
            '<div class="rut-tips-nota">Basada en tu Word "Rutina de León" (AAP, Sleep Foundation, ' +
            'Taking Cara Babies, Huckleberry, Cleveland Clinic) y las actividades de tu guía ' +
            '"Estimulación Temprana" (Karina Rivera) — validá siempre con su pediatra. ' +
            'Ritmo flexible, no horario rígido.</div>' +
        '</div>';
    }

    function renderTodo() {
        ajustarSticky();   // remedir siempre: el alto del topbar global puede variar
        var calc = calcular();
        var hoyIdx = new Date().getDay();
        var esHoy = UI.dia === hoyIdx && UI.etapa === 'actual';
        var now = ahoraMin();

        var items = [];
        if (UI.sel.leon) items = items.concat(calc.leon);
        if (UI.sel.mama) items = items.concat(calc.mama);
        if (UI.sel.papa) items = items.concat(calc.papa);
        items.sort(function (a, b) {
            return a.start - b.start || (a.user === 'leon' ? -1 : 1);
        });

        var nocheItem = null;
        calc.leon.forEach(function (i) { if (!nocheItem && i.kind === 'noche') nocheItem = i; });
        function enCurso(it) {
            return esHoy && it.kind !== 'noche' && now >= it.start && now < Math.max(it.end, it.start + 1);
        }
        // La noche queda activa desde su inicio hasta las 05:00 (cruza medianoche)
        var nocheActiva = esHoy && nocheItem && (now >= nocheItem.start || now < 300);

        renderHeader();
        renderChips();
        renderDias();
        renderEtapas();
        renderAviso(esHoy);
        renderAhora(items, calc.leon, esHoy, now, nocheItem, nocheActiva, enCurso);
        renderTimeline(items, esHoy, now, nocheActiva, enCurso);
        renderTips(calc.R);
    }

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
            persistirUI();
            renderTodo();
        });

        $('rut-etapas').addEventListener('click', function (ev) {
            var btn = ev.target.closest('[data-etapa]');
            if (!btn) return;
            UI.etapa = btn.dataset.etapa;
            editando = null;
            persistirUI();
            renderTodo();
        });

        $('rut-filas').addEventListener('click', function (ev) {
            var t = ev.target;
            var el;
            if ((el = t.closest('[data-menos]'))) return ajustarDesdeFila(el.dataset.menos, -15);
            if ((el = t.closest('[data-mas]'))) return ajustarDesdeFila(el.dataset.mas, +15);
            if ((el = t.closest('[data-poner-ahora]'))) return ajustar(el.dataset.ponerAhora, ahoraMin());
            if (t.closest('[data-cerrar]')) { editando = null; return renderTodo(); }
            if ((el = t.closest('[data-tap]'))) {
                editando = (editando === el.dataset.tap) ? null : el.dataset.tap;
                renderTodo();
            }
        });

        $('rut-ahora').addEventListener('click', function (ev) {
            var btn = ev.target.closest('[data-empezo]');
            if (btn) ajustar(btn.dataset.empezo, ahoraMin());
        });

        $('rut-reset').addEventListener('click', resetDia);

        // −15/+15 parten del inicio VIGENTE del ítem (con cascada aplicada)
        function ajustarDesdeFila(itemId, delta) {
            var calc = calcular();
            var todos = calc.leon.concat(calc.mama, calc.papa);
            var it = null;
            todos.forEach(function (i) { if (!it && i.id === itemId) it = i; });
            if (it) ajustar(itemId, it.start + delta);
        }

        window.addEventListener('resize', ajustarSticky);
        renderTodo();
        // Remedir cuando terminan de cargar fuentes/estáticos (el alto del
        // topbar global puede cambiar entre DOMContentLoaded y load).
        window.addEventListener('load', ajustarSticky);

        // Reloj vivo + sync entre teléfonos (30 s); sync extra al volver a la app
        setInterval(syncAjustes, 30000);
        document.addEventListener('visibilitychange', function () {
            if (!document.hidden) syncAjustes();
        });
    }

    document.addEventListener('DOMContentLoaded', init);
})();
