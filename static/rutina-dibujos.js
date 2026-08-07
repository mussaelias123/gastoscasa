/*
================================================================================
ARCHIVO: static/rutina-dibujos.js
================================================================================
Librería de dibujos propia del módulo Rutina. Datos puros: se carga ANTES de
rutina.js, en /rutina y en / (la tarjeta del Inicio no los usa hoy, pero el
estado del módulo se evalúa igual).

POR QUÉ SVG INLINE Y NO UN SPRITE CON <use>
  Con <symbol> + <use> el dibujo vive en un shadow tree y las animaciones CSS
  de style.css no llegan a sus partes internas. Como el render de la línea de
  tiempo ya arma HTML con innerHTML, inyectar el SVG entero es más simple y
  garantiza que las animaciones funcionen. Cada dibujo pesa ~400 bytes.

CONVENCIONES (mismas que los íconos de Lactancia, .lac-ico)
  - viewBox 0 0 24 24, sin fill, stroke = currentColor → heredan el color de la
    persona (--rut-color) sin tener que duplicar paletas.
  - Los trazos con class="relleno" son el segundo tono: mismo color, opacidad
    baja. Así el dibujo se adapta solo a modo día y modo noche.
  - Las partes animadas llevan una clase con prefijo `an-`; los @keyframes
    están en style.css, dentro del bloque RUTINA. Todas las animaciones usan
    SOLO transform y opacity (baratas para la GPU), se apagan con
    prefers-reduced-motion y se pausan cuando la pestaña está oculta.

CÓMO SE USA
  window.RutinaDibujos.html(clave)  → markup del SVG, o '' si no existe.
  window.RutinaDibujos.resolver(v)  → clave del dibujo a partir de lo guardado:
    acepta la clave directa ('siesta') o un emoji viejo ('😴'), que es lo que
    quedó en las actividades migradas. Si no reconoce nada, devuelve null y el
    front muestra el emoji tal cual — así nunca se pierde lo que el usuario
    haya cargado a mano.
================================================================================
*/

(function () {
    'use strict';

    function svg(cuerpo) {
        return '<svg class="rut-dib" viewBox="0 0 24 24" aria-hidden="true">' +
               cuerpo + '</svg>';
    }

    var D = {
        // Luna con zetas que suben — la siesta
        siesta: svg(
            '<path class="relleno" d="M15.5 4.5A7.5 7.5 0 1 0 19 15.2 6 6 0 0 1 15.5 4.5Z"/>' +
            '<path d="M15.5 4.5A7.5 7.5 0 1 0 19 15.2 6 6 0 0 1 15.5 4.5Z"/>' +
            '<path class="an-zzz an-zzz-1" d="M4 6h3l-3 3.4h3"/>' +
            '<path class="an-zzz an-zzz-2" d="M6.5 1.6h2.2l-2.2 2.5h2.2"/>'
        ),

        // Luna llena y estrellas que titilan — la noche
        noche: svg(
            '<path class="relleno" d="M16 3.4A8.6 8.6 0 1 0 20.6 16 6.9 6.9 0 0 1 16 3.4Z"/>' +
            '<path d="M16 3.4A8.6 8.6 0 1 0 20.6 16 6.9 6.9 0 0 1 16 3.4Z"/>' +
            '<path class="an-titila an-titila-1" d="M5 4.4v2M4 5.4h2"/>' +
            '<path class="an-titila an-titila-2" d="M8.4 1.8v1.6M7.6 2.6h1.6"/>' +
            '<path class="an-titila an-titila-3" d="M3.4 10.2v1.6M2.6 11h1.6"/>'
        ),

        // Sol saliendo sobre el horizonte — el despertar
        despertar: svg(
            '<circle class="relleno" cx="12" cy="14" r="4.2"/>' +
            '<path d="M12 9.8a4.2 4.2 0 0 1 4.2 4.2H7.8A4.2 4.2 0 0 1 12 9.8Z"/>' +
            '<path d="M3 18h18"/>' +
            '<g class="an-rayos">' +
              '<path d="M12 3.4v2.2M5.6 6.1l1.5 1.5M18.4 6.1l-1.5 1.5M2.6 14h2.1M19.3 14h2.1"/>' +
            '</g>'
        ),

        // Corazón con una gota — la toma al pecho
        teta: svg(
            '<path class="relleno an-late" d="M12 19.4s-6.6-4.2-6.6-8.8a3.5 3.5 0 0 1 6.6-1.7 3.5 3.5 0 0 1 6.6 1.7c0 4.6-6.6 8.8-6.6 8.8Z"/>' +
            '<path class="an-late" d="M12 19.4s-6.6-4.2-6.6-8.8a3.5 3.5 0 0 1 6.6-1.7 3.5 3.5 0 0 1 6.6 1.7c0 4.6-6.6 8.8-6.6 8.8Z"/>' +
            '<path class="an-gota" d="M18.6 3.2c1 1.2 1.7 2.1 1.7 3a1.7 1.7 0 0 1-3.4 0c0-.9.7-1.8 1.7-3Z"/>'
        ),

        // Mamadera con la leche adentro
        mamadera: svg(
            '<path d="M9.2 2.6h5.6M10 5.2h4l.8 2H9.2Z"/>' +
            '<path d="M8.6 7.2h6.8a1.6 1.6 0 0 1 1.6 1.6v10.6a1.6 1.6 0 0 1-1.6 1.6H8.6A1.6 1.6 0 0 1 7 19.4V8.8a1.6 1.6 0 0 1 1.6-1.6Z"/>' +
            '<path class="relleno an-leche" d="M7 12.4h10v7a1.6 1.6 0 0 1-1.6 1.6H8.6A1.6 1.6 0 0 1 7 19.4Z"/>' +
            '<path d="M7 12.4h3M7 15.6h2.2"/>'
        ),

        // Plato con cuchara — las comidas
        comida: svg(
            '<path class="relleno" d="M4.4 12.6h11.2a5.6 5.6 0 0 1-11.2 0Z"/>' +
            '<path d="M3.4 12.6h13.2a6.6 6.6 0 0 1-13.2 0Z"/>' +
            '<path d="M2.6 20.4h15.4"/>' +
            '<path d="M20.4 3.4v8M20.4 11.4v9"/>' +
            '<g class="an-vapor"><path d="M7.6 8.6c0-1 1-1.4 1-2.4M11.6 8.6c0-1 1-1.4 1-2.4"/></g>'
        ),

        // Bañera con burbujas que suben
        bano: svg(
            '<path d="M3 12.4h18v2.2a5 5 0 0 1-5 5H8a5 5 0 0 1-5-5Z"/>' +
            '<path class="relleno" d="M4.4 14.6h15.2a4 4 0 0 1-4 3.6H8.4a4 4 0 0 1-4-3.6Z"/>' +
            '<path d="M6 12.4V5.6a2 2 0 0 1 3.6-1.2"/>' +
            '<path d="M5.6 20.4 5 22M18.4 20.4 19 22"/>' +
            '<g class="an-burbuja an-burbuja-1"><circle cx="9.4" cy="9.6" r="1.1"/></g>' +
            '<g class="an-burbuja an-burbuja-2"><circle cx="13.4" cy="7.6" r="0.8"/></g>' +
            '<g class="an-burbuja an-burbuja-3"><circle cx="16.4" cy="10" r="1"/></g>'
        ),

        // Ducha con gotas cayendo
        ducha: svg(
            '<path d="M12 3.2v4M6.6 12.4a5.4 5.4 0 0 1 10.8 0Z"/>' +
            '<path class="relleno" d="M7.6 11.4a4.4 4.4 0 0 1 8.8 0Z"/>' +
            '<g class="an-lluvia an-lluvia-1"><path d="M9 15.4v2"/></g>' +
            '<g class="an-lluvia an-lluvia-2"><path d="M12 16.4v2.4"/></g>' +
            '<g class="an-lluvia an-lluvia-3"><path d="M15 15.4v2"/></g>'
        ),

        // Trencito: la máquina y un vagón, con humo y las ruedas girando.
        // Pedido de Mari (2026-08-06) en reemplazo de la pelota y el bloque.
        // La clave sigue siendo `juego` A PROPÓSITO: es lo que quedó guardado
        // en las actividades y en POR_EMOJI. Cambia el dibujo, no el dato.
        juego: svg(
            '<path d="M2 20.6h20"/>' +
            '<path class="relleno" d="M2.6 11.8h6v5.6h-6Z"/>' +
            '<path d="M2.6 11.8h6v5.6h-6Z"/>' +
            '<path d="M8.6 15h2"/>' +
            '<path class="relleno" d="M14.4 12.2h6.8v5.2h-6.8Z"/>' +
            '<path d="M10.6 8.6h3.8v8.8h-3.8Z"/>' +
            '<path d="M14.4 12.2h6.8v5.2h-6.8Z"/>' +
            '<path d="M11.6 10h1.8v2h-1.8Z"/>' +
            '<path d="M18 12.2V9.4h2.4v2.8"/>' +
            '<g class="an-burbuja an-burbuja-1"><circle cx="19.2" cy="7" r="1.1"/></g>' +
            '<g class="an-burbuja an-burbuja-3"><circle cx="17.2" cy="4.6" r="0.85"/></g>' +
            '<g class="an-rueda"><circle cx="5.6" cy="18.8" r="1.5"/></g>' +
            '<g class="an-rueda an-rueda-2"><circle cx="12.4" cy="18.8" r="1.5"/></g>' +
            '<g class="an-rueda"><circle cx="18.6" cy="18.8" r="1.5"/></g>'
        ),

        // Auto — "salir al trabajo". Antes salía el 🚗 crudo: era el único
        // emoji de la rutina de la familia que no tenía dibujo propio, y se
        // veía de colores en medio de una hoja donde todo el resto va en el
        // color de la persona.
        auto: svg(
            '<path d="M2.6 20.4h18.8"/>' +
            '<path class="relleno" d="M3.6 12.8h16.8v4.2H3.6Z"/>' +
            '<path d="M3 17v-4l2.4-.8 1.9-3.2a2 2 0 0 1 1.7-1h6a2 2 0 0 1 1.7 1l1.9 3.2 2.4.8v4"/>' +
            '<path d="M7.6 12.2 8.9 9.6h6.2l1.3 2.6Z"/>' +
            '<path d="M12 9.6v2.6"/>' +
            '<g class="an-rueda"><circle cx="7.2" cy="17.4" r="1.9"/></g>' +
            '<g class="an-rueda an-rueda-2"><circle cx="16.8" cy="17.4" r="1.9"/></g>'
        ),

        // Despertador — el ⏰ del título del módulo, en los tres lugares donde
        // aparece "Rutina" (la hoja, el Inicio y el menú).
        reloj: svg(
            '<circle class="relleno" cx="12" cy="13.4" r="7.4"/>' +
            '<circle cx="12" cy="13.4" r="7.4"/>' +
            '<path d="M12 9.2v4.2l2.8 1.8"/>' +
            '<path d="M6.4 4.6 3.8 7.2M17.6 4.6l2.6 2.6"/>' +
            '<path class="relleno" d="M5.4 3.4a2.4 2.4 0 0 1 2.6 1.6M18.6 3.4A2.4 2.4 0 0 0 16 5"/>' +
            '<path d="M8.4 20.6 7 22.4M15.6 20.6l1.4 1.8"/>'
        ),

        // Cochecito con las ruedas girando — el paseo
        paseo: svg(
            '<path d="M4.4 5.4h2.2l2 8.4h10"/>' +
            '<path class="relleno" d="M8.6 6.4h10.8a6 6 0 0 1-6 6H10Z"/>' +
            '<path d="M8.6 6.4h10.8a6 6 0 0 1-6 6H10Z"/>' +
            '<g class="an-rueda"><circle cx="10" cy="18.4" r="2"/></g>' +
            '<g class="an-rueda an-rueda-2"><circle cx="17.4" cy="18.4" r="2"/></g>'
        ),

        // Escuela: el edificio con su banderita
        escuela: svg(
            '<path d="M3.4 20.4h17.2"/>' +
            '<path class="relleno" d="M5.4 20.4v-8L12 8.4l6.6 4v8Z"/>' +
            '<path d="M5.4 20.4v-8L12 8.4l6.6 4v8Z"/>' +
            '<path d="M10.2 20.4v-4.2h3.6v4.2"/>' +
            '<path d="M12 8.4V3.4"/>' +
            '<path class="an-bandera relleno" d="M12 3.6h4.2l-1.2 1.6 1.2 1.6H12Z"/>'
        ),

        // Notebook — el trabajo. Era un maletín; Mari (2026-08-06): "tanto mamá
        // como papá usan una portátil". Clave `trabajo` intacta: cambia el
        // dibujo, no el dato (mismo criterio que el trencito).
        trabajo: svg(
            '<path class="relleno" d="M6.4 4.6h11.2v8.4H6.4Z"/>' +
            '<path d="M6.4 4.6h11.2v8.4H6.4Z"/>' +
            '<path class="relleno" d="M3.2 17.8 5.6 13h12.8l2.4 4.8Z"/>' +
            '<path d="M3.2 17.8 5.6 13h12.8l2.4 4.8Z"/>' +
            '<path d="M2.6 17.8h18.8"/>' +
            '<path class="an-cierre" d="M10.2 15.6h3.6"/>'
        ),

        // Dos grandes y un chiquito — la sección Familia
        familia: svg(
            '<circle class="relleno" cx="6.4" cy="6.2" r="2.5"/>' +
            '<circle cx="6.4" cy="6.2" r="2.5"/>' +
            '<path d="M2.6 20.4v-4a3.8 3.8 0 0 1 7.6 0v4"/>' +
            '<circle class="relleno" cx="17.6" cy="6.2" r="2.5"/>' +
            '<circle cx="17.6" cy="6.2" r="2.5"/>' +
            '<path d="M13.8 20.4v-4a3.8 3.8 0 0 1 7.6 0v4"/>' +
            '<circle class="relleno an-respira" cx="12" cy="13" r="1.9"/>' +
            '<circle class="an-respira" cx="12" cy="13" r="1.9"/>' +
            '<path d="M9.2 20.4v-2.6a2.8 2.8 0 0 1 5.6 0v2.6"/>'
        ),

        // Portapapeles con renglones — la sección Actividades
        lista: svg(
            '<path d="M8.6 4.4H6.4A1.6 1.6 0 0 0 4.8 6v13a1.6 1.6 0 0 0 1.6 1.6h11.2A1.6 1.6 0 0 0 19.2 19V6a1.6 1.6 0 0 0-1.6-1.6h-2.2"/>' +
            '<path class="relleno" d="M9.4 2.6h5.2a1 1 0 0 1 1 1v2.2H8.4V3.6a1 1 0 0 1 1-1Z"/>' +
            '<path d="M9.4 2.6h5.2a1 1 0 0 1 1 1v2.2H8.4V3.6a1 1 0 0 1 1-1Z"/>' +
            '<path d="M8.4 10.6h7.2M8.4 13.8h7.2M8.4 17h4.4"/>'
        ),

        // Reloj de arena — "Tiempo libre" y "Aún en…". Era el ⏳ crudo, el
        // último relojito viejo que quedaba en la hoja (Mari, 2026-08-07).
        libre: svg(
            '<path d="M6.6 2.8h10.8M6.6 21.2h10.8"/>' +
            '<path d="M8.2 2.8v3.6L12 12l-3.8 5.6v3.6M15.8 2.8v3.6L12 12l3.8 5.6v3.6"/>' +
            '<path class="relleno" d="M9.6 5.4h4.8L12 9Z"/>' +
            '<path class="relleno" d="M9.4 19.4h5.2L12 15.8Z"/>' +
            '<path class="an-gota" d="M12 11.2v2.6"/>'
        ),

        // Cadena — la marca de "esto lo hacen dos". Antes era un 🔗 crudo; se
        // veía poco porque no había compartidas, y con las tomas de León
        // ancladas a mamá pasó a aparecer siete veces por día.
        link: svg(
            '<path d="M10.2 7.6H7.8a4.4 4.4 0 0 0 0 8.8h2.4"/>' +
            '<path d="M13.8 7.6h2.4a4.4 4.4 0 0 1 0 8.8h-2.4"/>' +
            '<path d="M8.6 12h6.8"/>'
        ),

        // Engranaje — la sección Ajustes
        ajustes: svg(
            '<circle class="relleno" cx="12" cy="12" r="3.1"/>' +
            '<circle cx="12" cy="12" r="3.1"/>' +
            '<path d="M12 2.8v2.8M12 18.4v2.8M2.8 12h2.8M18.4 12h2.8"/>' +
            '<path d="m5.5 5.5 2 2M16.5 16.5l2 2M18.5 5.5l-2 2M7.5 16.5l-2 2"/>'
        ),

        // Almanaque — el calendario / los cumpleaños del mes
        calendario: svg(
            '<path d="M4.6 5.6h14.8A1.4 1.4 0 0 1 20.8 7v11.8a1.4 1.4 0 0 1-1.4 1.4H4.6a1.4 1.4 0 0 1-1.4-1.4V7a1.4 1.4 0 0 1 1.4-1.4Z"/>' +
            '<path class="relleno" d="M3.2 10.4h17.6v8.4a1.4 1.4 0 0 1-1.4 1.4H4.6a1.4 1.4 0 0 1-1.4-1.4Z"/>' +
            '<path d="M3.2 10.4h17.6"/>' +
            '<path d="M7.6 3.4v4M16.4 3.4v4"/>' +
            '<path d="M7 13.8h2M11 13.8h2M15 13.8h2M7 17h2M11 17h2"/>'
        ),

        // Mancuerna que sube y baja — la gimnasia
        gimnasia: svg(
            '<g class="an-pesa">' +
              '<path d="M7.4 12h9.2"/>' +
              '<path class="relleno" d="M4.4 9.2h2.6v5.6H4.4ZM17 9.2h2.6v5.6H17Z"/>' +
              '<path d="M4.4 9.2h2.6v5.6H4.4ZM17 9.2h2.6v5.6H17Z"/>' +
              '<path d="M2.6 10.6v2.8M21.4 10.6v2.8"/>' +
            '</g>'
        ),

        // Libro abierto con la hoja que pasa — el estudio
        estudio: svg(
            '<path class="relleno" d="M12 6.6C10 5 7.4 4.6 3.4 4.8v12.6c4-.2 6.6.2 8.6 1.8Z"/>' +
            '<path d="M12 6.6C10 5 7.4 4.6 3.4 4.8v12.6c4-.2 6.6.2 8.6 1.8Z"/>' +
            '<path class="an-hoja" d="M12 6.6c2-1.6 4.6-2 8.6-1.8v12.6c-4-.2-6.6.2-8.6 1.8Z"/>' +
            '<path d="M12 6.6v12.6"/>'
        ),

        // Grande que alza a chiquito — el upa
        upa: svg(
            '<g class="an-respira">' +
              '<circle class="relleno" cx="9" cy="6.6" r="3.2"/>' +
              '<circle cx="9" cy="6.6" r="3.2"/>' +
              '<path d="M4.4 20.4v-5a4.6 4.6 0 0 1 4.6-4.6 4.6 4.6 0 0 1 4.6 4.6v5"/>' +
              '<circle class="relleno" cx="17.6" cy="11.6" r="2.2"/>' +
              '<circle cx="17.6" cy="11.6" r="2.2"/>' +
              '<path d="M12.4 13.6c1.6-.8 3.4-1 5.2-1a3 3 0 0 1 3 3v4.8"/>' +
            '</g>'
        ),

        // Canasto de ropa — las tareas de la casa
        tareas: svg(
            '<path d="M3.6 8.4h16.8l-1.4 10.4a1.6 1.6 0 0 1-1.6 1.4H6.6a1.6 1.6 0 0 1-1.6-1.4Z"/>' +
            '<path class="relleno" d="M4.8 12.4h14.4l-.8 6.4a1.6 1.6 0 0 1-1.6 1.4H7.2a1.6 1.6 0 0 1-1.6-1.4Z"/>' +
            '<path d="M8.4 8.4 9.6 3.6M15.6 8.4 14.4 3.6"/>' +
            '<path d="M2.6 8.4h18.8"/>'
        ),

        // Torta con la velita titilando — el cumpleaños
        cumple: svg(
            '<path d="M4 20.4h16"/>' +
            '<path class="relleno" d="M4.6 14.4h14.8v6H4.6Z"/>' +
            '<path d="M4.6 20.4v-4.6a1.6 1.6 0 0 1 1.6-1.6h11.6a1.6 1.6 0 0 1 1.6 1.6v4.6"/>' +
            '<path d="M12 14.4V9.6M8.4 14.4v-3.2M15.6 14.4v-3.2"/>' +
            '<g class="an-llama">' +
              '<path class="relleno" d="M12 5.2c1.2 1.5 1.9 2.4 1.9 3.3a1.9 1.9 0 0 1-3.8 0c0-.9.7-1.8 1.9-3.3Z"/>' +
              '<path d="M12 5.2c1.2 1.5 1.9 2.4 1.9 3.3a1.9 1.9 0 0 1-3.8 0c0-.9.7-1.8 1.9-3.3Z"/>' +
            '</g>'
        )
    };

    // Emojis que quedaron guardados antes de que existieran los dibujos
    // (actividades migradas, tareas cargadas a mano). Se traducen para que la
    // hoja se vea pareja sin obligar a nadie a recargar nada.
    var POR_EMOJI = {
        '😴': 'siesta',   '🌙': 'noche',     '🌅': 'despertar', '🤱🏻': 'teta',
        '🤱': 'teta',     '🍼': 'mamadera',  '🍽️': 'comida',    '🍽': 'comida',
        '🍳': 'comida',   '🛁': 'bano',      '🚿': 'ducha',      '🧸': 'juego',
        '🚶': 'paseo',    '🏫': 'escuela',   '💼': 'trabajo',    '🏋️': 'gimnasia',
        '🏋': 'gimnasia', '📚': 'estudio',   '🫂': 'upa',        '🧺': 'tareas',
        '🎂': 'cumple',   '🎉': 'cumple',    '🚗': 'auto',       '🚙': 'auto',
        '🚕': 'auto',     '⏰': 'reloj',     '⏱️': 'reloj',      '🕐': 'reloj',
        '👪': 'familia',  '👨‍👩‍👦': 'familia',   '👩‍👧': 'familia',    '🧑‍🤝‍🧑': 'familia',
        '📋': 'lista',    '📌': 'lista',     '📝': 'lista',      '🗒️': 'lista',
        '⚙️': 'ajustes',  '⚙': 'ajustes',    '🔧': 'ajustes',    '🛠️': 'ajustes',
        '📅': 'calendario', '📆': 'calendario', '🗓️': 'calendario',
        '📖': 'estudio',  '📕': 'estudio',
        '⏳': 'libre',    '⌛': 'libre',     '⏱': 'reloj',       '🕒': 'reloj',
        '🔗': 'link',     '⛓️': 'link'
    };

    function resolver(valor) {
        var v = String(valor || '').trim();
        if (!v) return null;
        if (D[v]) return v;
        return POR_EMOJI[v] || null;
    }

    window.RutinaDibujos = {
        claves: Object.keys(D),
        html: function (clave) { return D[clave] || ''; },
        resolver: resolver
    };
})();
