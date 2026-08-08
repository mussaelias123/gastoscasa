/*
================================================================================
ARCHIVO: static/rutina-sueno.js
================================================================================
Motor de ventanas de sueño del módulo Rutina. Se carga SOLO en /rutina, ANTES
de static/rutina.js. Vanilla JS ES5, IIFE, sin librerías.

QUÉ RESUELVE
  Antes, la rutina del bebé estaba escrita a mano en static/rutina.js para "2
  meses" y no se actualizaba nunca. Ahora se GENERA a partir de tres datos:
    1. la edad (de rutina_miembros.fecha_nacimiento),
    2. el ancla: la primera toma del día (rutina_miembros.ancla_min),
    3. la hora de inicio de la noche (config rutina_hora_noche).

  Una "ventana de sueño" es cuánto puede estar despierto un bebé entre un sueño
  y el siguiente sin llegar al sobrecansancio. Se alargan conforme crece, y ese
  cambio es lo que hace que la rutina se tenga que rearmar sola.

QUÉ DEVUELVE
  generar() arma la misma forma de datos que antes tenía la constante ETAPAS,
  así el resto de rutina.js (cascada, drag, ocultar, "↺ Plan original") sigue
  funcionando sin cambios:
    dia:       [ { id, dibujo, emoji, t, dur, kind, sub } ]   cadena encadenada
    nocturnas: [ { id, off, dibujo, emoji, t, sub } ]         off = min desde
                                                             el inicio de la noche
  Los ids llevan prefijo 'b<miembroId>-' para que los ajustes guardados en
  rutina_ajustes / rutina_dur sean por miembro y no se pisen entre hermanos.
  Respetan el regex del backend _RUT_ITEM_RE (^[a-z0-9-]{1,40}$).

IMPORTANTE — LOS NÚMEROS SON ORIENTATIVOS
  Las señales del bebé (bostezo, mirada perdida, quejoso) mandan más que el
  reloj, y las tomas van a demanda. La app propone un plan y lo deja editar; no
  da indicación médica. Mismo criterio que config.py con el perfil del bebé.
  Fuentes de la tabla: Cleveland Clinic, Taking Cara Babies, Huckleberry,
  Mustela, Humana Baby (ver el plan del rework).
================================================================================
*/

(function () {
    'use strict';

    // ── Tabla de ventanas de sueño por edad ─────────────────────────────────
    // hasta:      edad máxima EN DÍAS de la fila (la primera que cumple gana).
    // ventana:    [min, max] minutos despierto entre sueño y sueño.
    // siestas:    [min, max] cantidad de siestas por día.
    // siestaDur:  [min, max] duración típica de una siesta, en minutos.
    // suenoDia:   [min, max] horas de sueño total en 24 h (solo informativo).
    // nocturnas:  [min, max] despertares nocturnos con toma que son esperables.
    // tomaCada:   minutos entre tomas durante el día (para intercalarlas).
    // Los valores que USA el generador son los del medio de cada rango; los
    // extremos se muestran en la tarjeta de tips.
    var TABLA = [
        {
            hasta: 30, etiqueta: 'recién nacido',
            // 30-60 min, no 45-60: Cleveland Clinic, Huckleberry y Taking Cara
            // Babies coinciden en que un recién nacido aguanta despierto desde
            // los 30. El generador usa el MEDIO del rango, así que la ventana
            // efectiva baja de 55 a 45 min. Solo afecta a bebés de ≤30 días.
            ventana: [30, 60], siestas: [5, 6], siestaDur: [45, 90],
            suenoDia: [14, 17], nocturnas: [3, 4], tomaCada: 150
        },
        {
            hasta: 91, etiqueta: '1 a 3 meses',
            ventana: [60, 90], siestas: [4, 5], siestaDur: [45, 90],
            suenoDia: [14, 17], nocturnas: [2, 3], tomaCada: 165
        },
        {
            hasta: 121, etiqueta: '3 a 4 meses',
            ventana: [75, 120], siestas: [4, 4], siestaDur: [45, 90],
            suenoDia: [14, 16], nocturnas: [1, 2], tomaCada: 180
        },
        {
            hasta: 152, etiqueta: '4 a 5 meses',
            ventana: [120, 150], siestas: [3, 4], siestaDur: [60, 90],
            suenoDia: [12, 16], nocturnas: [1, 2], tomaCada: 195
        },
        {
            hasta: 213, etiqueta: '5 a 7 meses',
            ventana: [120, 180], siestas: [3, 3], siestaDur: [60, 90],
            suenoDia: [12, 15], nocturnas: [0, 1], tomaCada: 210
        },
        {
            hasta: 304, etiqueta: '7 a 10 meses',
            ventana: [150, 210], siestas: [2, 3], siestaDur: [60, 90],
            suenoDia: [12, 15], nocturnas: [0, 1], tomaCada: 225
        },
        {
            hasta: 425, etiqueta: '10 a 14 meses',
            ventana: [180, 240], siestas: [2, 2], siestaDur: [60, 90],
            suenoDia: [11, 14], nocturnas: [0, 0], tomaCada: 240
        },
        {
            hasta: 547, etiqueta: '14 a 18 meses',
            ventana: [240, 300], siestas: [1, 2], siestaDur: [90, 120],
            suenoDia: [11, 14], nocturnas: [0, 0], tomaCada: 260
        },
        {
            hasta: 730, etiqueta: '18 a 24 meses',
            ventana: [300, 360], siestas: [1, 1], siestaDur: [90, 120],
            suenoDia: [11, 14], nocturnas: [0, 0], tomaCada: 280
        },
        {
            hasta: 1095, etiqueta: '2 a 3 años',
            ventana: [300, 360], siestas: [1, 1], siestaDur: [60, 120],
            suenoDia: [10, 13], nocturnas: [0, 0], tomaCada: 300
        },
        {
            hasta: Infinity, etiqueta: 'más de 3 años',
            ventana: [360, 420], siestas: [0, 1], siestaDur: [60, 90],
            suenoDia: [10, 13], nocturnas: [0, 0], tomaCada: 0
        }
    ];

    // Duraciones fijas del ritual, en minutos.
    var DUR_TOMA = 25;
    var DUR_BANO = 15;
    var DUR_RITUAL = DUR_BANO + DUR_TOMA;   // baño + última toma antes de la noche

    // La primera ventana del día es siempre la más corta: es la regla que
    // repiten todas las fuentes. Se le aplica este factor.
    var FACTOR_PRIMERA = 0.85;

    // ── Utilidades ──────────────────────────────────────────────────────────

    function medio(rango) {
        return Math.round((rango[0] + rango[1]) / 2);
    }

    function aMultiploDe5(min) {
        return Math.round(min / 5) * 5;
    }

    /** Fila de la tabla que corresponde a una edad en días. */
    function filaPorEdad(edadDias) {
        var dias = (typeof edadDias === 'number' && edadDias >= 0) ? edadDias : 0;
        for (var i = 0; i < TABLA.length; i++) {
            if (dias <= TABLA[i].hasta) { return TABLA[i]; }
        }
        return TABLA[TABLA.length - 1];
    }

    /** Edad en días entre una fecha 'YYYY-MM-DD' y hoy (fechas LOCALES). */
    function edadEnDias(fechaNacimiento, hoy) {
        if (!fechaNacimiento) { return null; }
        var p = String(fechaNacimiento).split('-');
        if (p.length !== 3) { return null; }
        var nac = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
        if (isNaN(nac.getTime())) { return null; }
        var ref = hoy ? new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate())
                      : new Date();
        var ref0 = new Date(ref.getFullYear(), ref.getMonth(), ref.getDate());
        var dias = Math.floor((ref0 - nac) / 86400000);
        return dias < 0 ? null : dias;
    }

    // ── Generador ───────────────────────────────────────────────────────────
    //
    // Estructura del día que arma:
    //
    //   ancla ─┬─ [Despertar + primera toma]  25'
    //          ├─ [Juego]                     ventana corta (×0.85) − 25'
    //          ├─ [Siesta 1]                  siestaDur
    //          ├─ [Toma 2]                    25'
    //          ├─ [Juego]                     ventana − 25'
    //          ├─ [Siesta 2]                  siestaDur
    //          │  … repite hasta llegar a la hora de la noche …
    //          ├─ [Baño]                      15'
    //          ├─ [Última toma + arrullo]     25'
    //          └─ [Sueño nocturno]            dur 0 = ítem abierto, cierra el día
    //
    // Las tomas nocturnas NO van en esta cadena: se cuelgan aparte con un
    // offset desde el inicio del sueño nocturno (la franja "🌙 Madrugada").
    //
    function generar(opts) {
        var miembroId = opts.miembroId;
        var pfx = 'b' + miembroId + '-';
        var fila = filaPorEdad(opts.edadDias);

        var anclaMin = (typeof opts.anclaMin === 'number') ? opts.anclaMin : 390;
        var nocheMin = (typeof opts.nocheMin === 'number') ? opts.nocheMin : 1200;

        // Se redondean a múltiplos de 5 para que los horarios queden legibles
        // (si no, una siesta de 68' deja la rutina en horas tipo 08:43).
        var ventana = aMultiploDe5(medio(fila.ventana));
        var siestaDur = aMultiploDe5(medio(fila.siestaDur));
        var maxSiestas = fila.siestas[1];

        var items = [];
        var reloj = anclaMin;
        var nSiesta = 0;
        var nToma = 1;
        var nJuego = 0;

        function push(item) {
            item.id = pfx + item.id;
            items.push(item);
            reloj += item.dur;
        }

        // 1. El ancla: el despertar y la toma que ordena todo el resto del día.
        push({
            id: 'desp', dibujo: 'teta', emoji: '🌅', kind: 'teta', dur: DUR_TOMA,
            t: 'Despertar + toma ancla',
            sub: 'La toma que ancla el día: si se corre, se corre todo lo demás. Pañal y luz natural.'
        });

        // 2. Ciclos [juego → siesta → toma] mientras entren antes de la noche.
        //    Cada vuelta consume una ventana de sueño completa.
        while (nSiesta < maxSiestas) {
            var esPrimera = (nSiesta === 0);
            var vent = esPrimera ? aMultiploDe5(ventana * FACTOR_PRIMERA) : ventana;

            // Lo que queda de esta ventana después de la toma que ya se hizo.
            var juego = aMultiploDe5(vent - DUR_TOMA);
            if (juego < 15) { juego = 15; }

            // ¿Entra otra siesta completa antes del ritual de la noche?
            if (reloj + juego + siestaDur + DUR_RITUAL > nocheMin) { break; }

            nJuego += 1;
            push({
                id: 'juego' + nJuego, dibujo: 'juego', emoji: '🧸', kind: 'juego',
                dur: juego, t: 'Juego ' + nJuego, act: true
            });

            nSiesta += 1;
            push({
                id: 'siesta' + nSiesta, dibujo: 'siesta', emoji: '😴', kind: 'sueno',
                dur: siestaDur, t: 'Siesta ' + nSiesta,
                sub: esPrimera
                    ? 'La primera ventana del día es la más corta: no la estires.'
                    : 'Penumbra suave. Si se despierta a los 30–40 min, probá acompañar el pasaje de ciclo.'
            });

            nToma += 1;
            push({
                id: 'toma' + nToma, dibujo: 'teta', emoji: '🤱🏻', kind: 'teta',
                dur: DUR_TOMA, t: 'Toma ' + nToma,
                sub: 'A demanda: si la pide antes, adelantala y todo se corre.'
            });
        }

        // 3. Tramo final hasta el ritual de la noche. Si quedó un hueco muy
        //    largo (más de una ventana y media), se mete una siesta puente
        //    corta: es el momento de mayor fastidio del día y llegar pasado de
        //    sueño a la noche complica el arranque.
        var finDia = nocheMin - DUR_RITUAL;
        var resto = finDia - reloj;

        if (resto > Math.round(ventana * 1.5) && fila.siestas[1] > 0) {
            var previo = aMultiploDe5(ventana - DUR_TOMA);
            if (previo < 15) { previo = 15; }
            if (previo > resto - 30) { previo = Math.max(15, resto - 30); }

            nJuego += 1;
            push({
                id: 'juego' + nJuego, dibujo: 'juego', emoji: '🫂', kind: 'juego',
                dur: previo, t: 'Upa y movimiento',
                sub: 'Suele ser el rato más fastidioso del día: upa, porteo, paciencia.'
            });

            var puente = aMultiploDe5(Math.min(45, finDia - reloj));
            if (puente >= 20) {
                nSiesta += 1;
                push({
                    id: 'siesta' + nSiesta, dibujo: 'siesta', emoji: '😴', kind: 'sueno',
                    dur: puente, t: 'Siesta puente (opcional)',
                    sub: 'Cortita, solo para llegar bien a la noche.'
                });
            }
            resto = finDia - reloj;
        }

        if (resto > 5) {
            nJuego += 1;
            push({
                id: 'juego' + nJuego, dibujo: 'juego', emoji: '🧸', kind: 'juego',
                dur: aMultiploDe5(resto), t: 'Juego tranquilo', act: true,
                sub: 'Bajando revoluciones: luz cálida, sin pantallas ni juegos muy activos.'
            });
        }

        // 4. Ritual: siempre el mismo orden, es lo que le avisa que viene la noche.
        push({
            id: 'bano', dibujo: 'bano', emoji: '🛁', kind: 'bano', dur: DUR_BANO,
            t: 'Baño', sub: 'Arranca el ritual: siempre igual, mismo orden.'
        });
        nToma += 1;
        push({
            id: 'ultima', dibujo: 'teta', emoji: '🤱🏻', kind: 'teta', dur: DUR_TOMA,
            t: 'Última toma + arrullo',
            sub: 'Luz baja. A la cuna despierto-adormecido si se puede.'
        });
        push({
            id: 'noche', dibujo: 'noche', emoji: '🌙', kind: 'noche', dur: 0,
            t: 'Sueño nocturno',
            sub: 'Boca arriba, cuna despejada (AAP). El chupete puede ofrecerse.'
        });

        return {
            dia: items,
            nocturnas: generarNocturnas(pfx, fila, anclaMin, nocheMin),
            fila: fila,
            resumen: resumen(fila)
        };
    }

    /**
     * Tomas nocturnas repartidas parejo a lo largo de la noche.
     * off = minutos desde el INICIO del sueño nocturno (no hora absoluta), que
     * es como las venía manejando rutina.js: si la noche se corre, se corren.
     */
    function generarNocturnas(pfx, fila, anclaMin, nocheMin) {
        var cuantas = fila.nocturnas[1];
        if (!cuantas) { return []; }

        // Largo de la noche: de nocheMin hasta el ancla del día siguiente.
        var largo = (1440 - nocheMin) + anclaMin;
        var out = [];
        for (var i = 1; i <= cuantas; i++) {
            var off = Math.round((largo * i / (cuantas + 1)) / 15) * 15;
            out.push({
                id: pfx + 'noct' + i,
                off: off,
                dibujo: 'teta',
                emoji: '🤱🏻',
                t: 'Toma nocturna ' + i,
                sub: i === 1
                    ? 'A demanda. Luz mínima, sin jugar y de vuelta a la cuna.'
                    : (fila.nocturnas[0] < i
                        ? 'Si la pide. A esta edad puede aparecer o no.'
                        : 'Esperable a esta edad.')
            });
        }
        return out;
    }

    /** Textos para la tarjeta de tips (rangos, no los valores del medio). */
    function resumen(fila) {
        function h(min) {
            if (min < 60) { return min + ' min'; }
            var horas = Math.floor(min / 60);
            var resto = min % 60;
            return resto ? (horas + ' h ' + resto + ' min') : (horas + ' h');
        }
        var siestas = (fila.siestas[0] === fila.siestas[1])
            ? String(fila.siestas[0])
            : (fila.siestas[0] + '–' + fila.siestas[1]);

        return {
            etiqueta: fila.etiqueta,
            ventana: h(fila.ventana[0]) + ' a ' + h(fila.ventana[1]),
            siestas: siestas,
            siestaDur: h(fila.siestaDur[0]) + ' a ' + h(fila.siestaDur[1]),
            suenoDia: fila.suenoDia[0] + '–' + fila.suenoDia[1] + ' h',
            nocturnas: fila.nocturnas[1] === 0
                ? 'a esta edad puede dormir de un tirón'
                : (fila.nocturnas[0] + '–' + fila.nocturnas[1] + ' despertares con toma son esperables')
        };
    }

    window.RutinaSueno = {
        TABLA: TABLA,
        filaPorEdad: filaPorEdad,
        edadEnDias: edadEnDias,
        generar: generar
    };
})();
