/* ============================================================================
 * static/lactancia.js — módulo Lactancia (banco de leche)
 * ============================================================================
 * Se trajo entero de la app suelta de banco de leche (C:\Proyectos\lactancia,
 * publicada en paralasmamas.pythonanywhere.com), que es donde se venía
 * trabajando el rediseño. Lo que NO se trajo: el cambio español/inglés (acá
 * T() solo rellena huecos), las sugerencias por correo y el borrado de cuenta.
 *
 * Estado: DATOS = window.LAC_DATOS, que inyecta lactancia.html. Después de
 * cada mutación el backend devuelve el payload completo y acá se re-renderiza
 * todo — nunca se parchea el DOM a mano ni se recalculan vencimientos en el
 * cliente (esos viven en los helpers _lac_* de app.py).
 * ========================================================================== */
(function () {
    'use strict';

    // ── Estado del módulo ────────────────────────────────────────────────────
    var DATOS = window.LAC_DATOS ||
        { freezer: [], heladera: [], historial: [], tablero: {}, params: {}, badge: 0,
          recordatorio: { activo: false, hora: '21:00', pendiente: false },
          bebe: { nombre: '', fecha_nacimiento: '', edad_texto: '', mes_de_vida: null } };

    var cfPartidaId = null;      // id en el modal Cerrar con fecha
    var cfMotivo = 'usada';      // 'usada' | 'descartada' en ese modal
    var masPartidaId = null;     // id en la hoja Más opciones
    var edPartidaId = null;      // id en el Editor

    // Instancias flatpickr (mismo patrón que calendario.js: valor real ISO
    // Y-m-d, altInput muestra d/m/Y). Se llenan en initFlatpickrs().
    var fpExFecha = null;
    var fpCfFecha = null;
    var fpEdFecha = null;
    var fpExHora = null;   // hora extracción alta (24h)
    var fpEdHora = null;   // hora extracción editor (24h)
    var fpRecHora = null;  // hora del recordatorio nocturno (24h)
    var fpBebeNac = null;  // fecha de nacimiento del bebé

    // Nombre del bebé: lo carga cada mamá en Ajustes. Si todavía no lo puso,
    // la app dice "el bebé" — nunca un nombre de ejemplo.
    function nombreBebe() {
        return (DATOS.bebe && DATOS.bebe.nombre) || 'el bebé';
    }

    function $(id) { return document.getElementById(id); }

    // ── Textos con huecos ────────────────────────────────────────────────────
    // Rellena los huecos entre llaves de los textos que arma el JavaScript:
    //   T('Vence en {n} días', {n: 3})  →  'Vence en 3 días'
    // En la app suelta esta función además traducía al inglés con un
    // diccionario que mandaba el servidor; Gastos Casa es solo en español, así
    // que quedó únicamente el relleno.
    function T(texto, valores) {
        if (valores) {
            Object.keys(valores).forEach(function (k) {
                texto = texto.split('{' + k + '}').join(valores[k]);
            });
        }
        return texto;
    }

    // ── Fechas y formato es-AR ───────────────────────────────────────────────
    function hoy() {
        var d = new Date();
        d.setHours(0, 0, 0, 0);
        return d;
    }

    function isoDate(d) {
        var m = String(d.getMonth() + 1).padStart(2, '0');
        var dia = String(d.getDate()).padStart(2, '0');
        return d.getFullYear() + '-' + m + '-' + dia;
    }

    // 'HH:MM' de un Date
    function fmtHoraDe(d) {
        return String(d.getHours()).padStart(2, '0') + ':' +
               String(d.getMinutes()).padStart(2, '0');
    }

    // Acepta 'YYYY-MM-DD' o ISO con hora ('YYYY-MM-DDTHH:MM:SS')
    function parseISO(s) {
        if (!s) return null;
        var p = String(s).split('T')[0].split('-');
        if (p.length !== 3) return null;
        var d = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
        d.setHours(0, 0, 0, 0);
        return d;
    }

    var MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
                 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

    // '12 mar 2026' | '—'
    function fmtFecha(f) {
        var d = (f instanceof Date) ? f : parseISO(f);
        if (!d) return '—';
        return d.getDate() + ' ' + MESES[d.getMonth()] + ' ' + d.getFullYear();
    }

    // '12 mar' | '—'
    function fmtFechaCorta(f) {
        var d = (f instanceof Date) ? f : parseISO(f);
        if (!d) return '—';
        return d.getDate() + ' ' + MESES[d.getMonth()];
    }

    function fmtMl(n) { return (Number(n) || 0) + ' ml'; }

    function fmtLitros(ml) {
        var n = ((Number(ml) || 0) / 1000).toFixed(2);
        // En español la coma es el separador decimal.
        return n.replace('.', ',') + ' L';
    }

    // Freezer: texto relativo desde dias_restantes (del server)
    function textoVencFreezer(dias) {
        if (dias === null || dias === undefined) return '';
        if (dias === 0) return T('Vence hoy');
        if (dias === 1) return T('Vence mañana');
        if (dias > 1) return T('Vence en {n} días', { n: dias });
        if (dias === -1) return T('Venció ayer');
        return T('Venció hace {n} días', { n: Math.abs(dias) });
    }

    // Heladera: texto relativo desde horas_restantes (del server). Nunca se
    // muestra una hora absoluta (regla del módulo), solo cuánto falta.
    function textoVencHeladera(horas) {
        if (horas === null || horas === undefined) return '';
        if (horas < 0) {
            var h = Math.abs(horas);
            if (h < 24) return T('Venció hace {n} h', { n: h });
            var d = Math.floor(h / 24);
            return d === 1 ? T('Venció hace 1 día') : T('Venció hace {n} días', { n: d });
        }
        if (horas === 0) return T('Vence dentro de 1 h');
        if (horas === 1) return T('Vence en 1 h');
        return T('Vence en {n} h', { n: horas });
    }

    // ── Estados ──────────────────────────────────────────────────────────────
    // Etiquetas en el vocabulario de Mari ("Freezada" para el cierre por
    // traslado heladera → freezer). Las claves son las del backend.
    var ESTADO_LABEL = {
        disponible:   'Disponible',
        vence_pronto: 'Vence pronto',
        vencida:      'Vencida',
        en_heladera:  'En heladera',
        usada:        'Usada',
        descartada:   'Descartada',
        trasladada:   'Freezada'
    };

    function pill(estado) {
        var label = T(ESTADO_LABEL[estado] || estado);
        return '<span class="lac-pill lac-pill-' + estado + '">' + label + '</span>';
    }

    function buscarPartida(id) {
        var listas = [DATOS.freezer, DATOS.heladera, DATOS.historial];
        for (var l = 0; l < listas.length; l++) {
            for (var i = 0; i < listas[l].length; i++) {
                if (listas[l][i].id === id) return listas[l][i];
            }
        }
        return null;
    }

    // Escape para armar HTML con datos del usuario (notas)
    function esc(s) {
        return String(s === null || s === undefined ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // ── AJAX ─────────────────────────────────────────────────────────────────
    // Toda mutación responde {ok:true, ...payload} (fresco) o {ok:false, error}.
    // onOk corre DESPUÉS de reemplazar DATOS y re-renderizar.
    // Tres cosas pueden salir mal y cada una necesita su mensaje (antes todas
    // terminaban en un "HTTP 200" incomprensible y la acción no se hacía):
    //   1. No se llega al servidor (sin internet, o la app no está corriendo).
    //   2. La sesión se cerró: el servidor contesta la pantalla de entrada o un
    //      aviso `sesion_cerrada` → hay que recargar para volver a entrar.
    //   3. El servidor rechazó la acción con un motivo (ej. partida vencida).
    function errorRed() {
        var e = new Error(T('No pudimos conectarnos con la app. Fijate que tengas internet y volvé a probar.'));
        e.recargar = false;
        return e;
    }

    function errorSesion() {
        var e = new Error(T('Se cerró tu sesión. Actualizá la página para volver a entrar.'));
        e.recargar = true;
        return e;
    }

    // Un pedido que nunca contesta (pasa en el celular cuando se corta el wifi
    // en medio) dejaría el botón como si no hubiera pasado nada: se corta solo
    // a los 15 segundos y ahí sí avisa.
    var ESPERA_MAX_MS = 15000;

    function postAccion(url, params, onOk, onFin) {
        var corte = ('AbortController' in window) ? new AbortController() : null;
        var reloj = corte && setTimeout(function () { corte.abort(); }, ESPERA_MAX_MS);

        fetch(url, {
            method: 'POST',
            body: params,   // URLSearchParams → content-type urlencoded automático
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            signal: corte ? corte.signal : undefined
        })
        .catch(function () { throw errorRed(); })
        .then(function (res) {
            return res.text().then(function (texto) {
                var data;
                try {
                    data = JSON.parse(texto);
                } catch (e) {
                    // Llegó una página HTML donde esperábamos datos.
                    throw errorSesion();
                }
                return data;
            });
        })
        .then(function (data) {
            if (!data.ok) {
                if (data.sesion_cerrada) throw errorSesion();
                if (data.offline) throw errorRed();
                throw new Error(data.error || T('No pudimos guardar el cambio. Probá de nuevo.'));
            }
            DATOS = {
                freezer: data.freezer || [],
                heladera: data.heladera || [],
                historial: data.historial || [],
                tablero: data.tablero || {},
                params: data.params || {},
                badge: data.badge || 0,
                recordatorio: data.recordatorio || DATOS.recordatorio ||
                    { activo: false, hora: '21:00', pendiente: false },
                bebe: data.bebe || DATOS.bebe ||
                    { nombre: '', fecha_nacimiento: '', edad_texto: '', mes_de_vida: null },
                // Las extracciones que alimentan el gráfico del Resumen. Va en
                // esta lista como todo lo demás: lo que no se nombre acá, el
                // servidor lo manda igual pero la pantalla lo tira.
                muestras: data.muestras || []
            };
            // El cambio YA quedó guardado. Si fallara el repintado de la
            // pantalla no hay que decirle que falló la acción (sería mentira):
            // se avisa y se recarga, que muestra el estado real.
            try {
                renderTodo();
            } catch (e) {
                console.error('Error al repintar lactancia:', e);
                toast('✓ ' + T('Se guardó. Refrescando la pantalla…'), 'info');
                setTimeout(function () { location.reload(); }, 1500);
                return;
            }
            if (onOk) onOk(data);
        })
        .catch(function (err) {
            console.error('Error AJAX lactancia:', err);
            toast('⚠ ' + err.message, 'error');
            if (err && err.recargar) {
                setTimeout(function () { location.reload(); }, 3000);
            }
        })
        .finally(function () {
            if (reloj) clearTimeout(reloj);
            if (onFin) onFin();
        });
    }

    // ── Toasts (reusan .toast base; con botón "Deshacer" opcional) ──────────
    function toast(texto, tipo, undoCb) {
        var cont = $('lac-toast-container');
        if (!cont) return;
        var clase = 'lac-toast-ok';
        if (tipo === 'error') clase = 'lac-toast-error';
        else if (tipo === 'info') clase = 'lac-toast-info';

        var el = document.createElement('div');
        el.className = 'toast ' + clase;
        el.textContent = texto;

        var duracion = 3000;
        if (undoCb) {
            duracion = 8000;   // con Deshacer se le da más tiempo
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'lac-toast-accion';
            btn.textContent = 'Deshacer';
            btn.addEventListener('click', function () {
                if (el.parentNode) el.parentNode.removeChild(el);
                undoCb();
            });
            el.appendChild(btn);
        }

        cont.appendChild(el);
        setTimeout(function () { el.classList.add('toast-visible'); }, 10);
        setTimeout(function () {
            el.classList.remove('toast-visible');
            el.classList.add('toast-saliendo');
            setTimeout(function () {
                if (el.parentNode) el.parentNode.removeChild(el);
            }, 300);
        }, duracion);
    }

    // ── Render: aviso al entrar ──────────────────────────────────────────────
    function renderAviso() {
        var el = $('lac-aviso');
        var t = DATOS.tablero || {};
        var vencidas = Number(t.freezer_vencidas) || 0;
        // Las de heladera vencidas también cuentan para el aviso
        DATOS.heladera.forEach(function (p) { if (p.estado === 'vencida') vencidas++; });
        var pronto = (Number(DATOS.badge) || 0) - vencidas;
        if (pronto < 0) pronto = 0;

        if (!vencidas && !pronto) {
            el.hidden = true;
            el.innerHTML = '';
            return;
        }
        var partes = [];
        if (vencidas) partes.push(vencidas === 1 ? T('1 bolsita vencida')
                                                 : T('{n} bolsitas vencidas', { n: vencidas }));
        if (pronto) partes.push(pronto === 1 ? T('1 por vencer')
                                             : T('{n} por vencer', { n: pronto }));
        el.className = 'lac-aviso ' + (vencidas ? 'is-peligro' : 'is-alerta');
        el.innerHTML = '⚠ ' + partes.join(T(' y ')) + T('. Revisá el stock.');
        el.hidden = false;
    }

    // ── Render: tablero ──────────────────────────────────────────────────────
    function stat(num, label, clase) {
        return '<div class="lac-stat' + (clase ? ' ' + clase : '') + '">' +
            '<span class="lac-stat-num">' + num + '</span>' +
            '<span class="lac-stat-label">' + label + '</span>' +
        '</div>';
    }

    // ── Íconos propios de los KPI ────────────────────────────────────────────
    // Antes acá había emojis (💧🍼📅…). El problema del emoji es que no es
    // nuestro: cada teléfono lo dibuja distinto —en Android la mamadera es
    // celeste, en iPhone es blanca— y ninguno acompaña la paleta cálida del
    // módulo. Estos son dibujos propios, con el mismo lenguaje que el resto de
    // los íconos: caja de 24×24, trazo en currentColor (así heredan el color de
    // la tarjeta) y un `.relleno` translúcido para el segundo tono.
    var ICO_KPI = {
        // Gota de leche con un corazón adentro: la producción, los "litros de amor"
        gota_corazon:
            '<path class="relleno" d="M12 3.4c3.1 3.7 5.4 6.7 5.4 9.6a5.4 5.4 0 1 1-10.8 0C6.6 10.1 8.9 7.1 12 3.4Z"/>' +
            '<path d="M12 3.4c3.1 3.7 5.4 6.7 5.4 9.6a5.4 5.4 0 1 1-10.8 0C6.6 10.1 8.9 7.1 12 3.4Z"/>' +
            '<path d="M12 17.2s-2.8-1.8-2.8-3.8a1.5 1.5 0 0 1 2.8-.9 1.5 1.5 0 0 1 2.8.9c0 2-2.8 3.8-2.8 3.8Z"/>',
        // Mamadera con leche hasta la mitad: lo que tomó el bebé
        mamadera:
            '<path class="relleno" d="M7.3 12.4h9.4v6.9a1.6 1.6 0 0 1-1.6 1.6H8.9a1.6 1.6 0 0 1-1.6-1.6Z"/>' +
            '<path d="M10.7 5.1c-.4-1.6.2-2.9 1.3-2.9s1.7 1.3 1.3 2.9Z"/>' +
            '<path d="M8.7 5.1h6.6a.6.6 0 0 1 .6.6v1.4H8.1V5.7a.6.6 0 0 1 .6-.6Z"/>' +
            '<path d="M8.9 7.1h6.2a1.6 1.6 0 0 1 1.6 1.6v10.6a1.6 1.6 0 0 1-1.6 1.6H8.9a1.6 1.6 0 0 1-1.6-1.6V8.7a1.6 1.6 0 0 1 1.6-1.6Z"/>' +
            '<path d="M7.3 12.4h9.4"/>',
        // Copo derritiéndose en una gota: la leche que se bajó a descongelar
        copo_gota:
            '<path class="relleno" d="M12 13.2c1.7 2 2.9 3.6 2.9 4.9a2.9 2.9 0 0 1-5.8 0c0-1.3 1.2-2.9 2.9-4.9Z"/>' +
            '<path d="M12 3.4v6.8M9 5.2l6 3.2M15 5.2l-6 3.2"/>' +
            '<path d="M12 13.2c1.7 2 2.9 3.6 2.9 4.9a2.9 2.9 0 0 1-5.8 0c0-1.3 1.2-2.9 2.9-4.9Z"/>',
        // Gota tachada: la leche que no llegó a tomarse. El `corte` es un trazo
        // grueso del color del fondo que va DEBAJO de la barra: abre un hueco a
        // los costados para que la barra se lea por encima de la gota y no se
        // empasten las dos. Es el mismo truco de los carteles de "prohibido".
        gota_tachada:
            '<path class="relleno" d="M12 4.6c2.7 3.2 4.6 5.8 4.6 8.3a4.6 4.6 0 1 1-9.2 0c0-2.5 1.9-5.1 4.6-8.3Z"/>' +
            '<path d="M12 4.6c2.7 3.2 4.6 5.8 4.6 8.3a4.6 4.6 0 1 1-9.2 0c0-2.5 1.9-5.1 4.6-8.3Z"/>' +
            '<path class="corte" d="M6.2 18.4 17.8 5.6"/>' +
            '<path d="M6.2 18.4 17.8 5.6"/>',
        // Almanaque: para cuántos días alcanza el stock
        almanaque:
            '<path class="relleno" d="M5.4 6.2h13.2a1.4 1.4 0 0 1 1.4 1.4v2.8H4V7.6a1.4 1.4 0 0 1 1.4-1.4Z"/>' +
            '<path d="M5.4 6.2h13.2a1.4 1.4 0 0 1 1.4 1.4v11.2a1.4 1.4 0 0 1-1.4 1.4H5.4A1.4 1.4 0 0 1 4 18.8V7.6a1.4 1.4 0 0 1 1.4-1.4Z"/>' +
            '<path d="M4 10.4h16M8.4 4v3.4M15.6 4v3.4"/>' +
            '<path d="M8.2 14h.01M12 14h.01M15.8 14h.01M8.2 17.1h.01M12 17.1h.01"/>',
        // Bolsita con la marca de hasta dónde llenarla: el tamaño sugerido
        bolsita:
            '<path class="relleno" d="M6.9 11.6h10.2v5.6a3.2 3.2 0 0 1-3.2 3.2h-3.8a3.2 3.2 0 0 1-3.2-3.2Z"/>' +
            '<path d="M6.9 3.6h10.2v13.6a3.2 3.2 0 0 1-3.2 3.2h-3.8a3.2 3.2 0 0 1-3.2-3.2Z"/>' +
            '<path d="M6.9 6.4h10.2"/>' +
            '<path d="M6.9 11.6h10.2"/>'
    };

    function icoKpi(nombre) {
        return '<svg class="lac-ico lac-kpi-ico" viewBox="0 0 24 24" aria-hidden="true">' +
            ICO_KPI[nombre] + '</svg>';
    }

    // Tarjeta de KPI de ciclo de vida (ícono + número grande + etiqueta, con un
    // sub-texto opcional). `clase` permite resaltar (ej. "litros de amor").
    function kpiCard(ico, num, label, sub, clase) {
        return '<div class="lac-kpi' + (clase ? ' ' + clase : '') + '">' +
            icoKpi(ico) +
            '<span class="lac-kpi-num">' + num + '</span>' +
            '<span class="lac-kpi-label">' + label +
                (sub ? ' <small>' + sub + '</small>' : '') + '</span>' +
        '</div>';
    }

    function renderTablero() {
        var cont = $('lac-tablero');
        var t = DATOS.tablero || {};
        var vacio = !DATOS.freezer.length && !DATOS.heladera.length && !DATOS.historial.length;

        if (vacio) {
            cont.innerHTML = '<div class="lac-vacia">' +
                '<span class="lac-vacia-em">🍼</span>' +
                '<span class="lac-vacia-t">' + T('Todavía no hay bolsitas cargadas') + '</span>' +
                '<span>' + T('Cargá la primera desde el panel Cargar') + ' 💪</span>' +
            '</div>';
            return;
        }

        var html = '<div class="lac-stats">' +
            stat(t.freezer_bolsas || 0, T('Bolsitas disponibles')) +
            stat(fmtMl(t.freezer_ml), T('Stock freezer') + ' (' + fmtLitros(t.freezer_ml) + ')') +
            stat(t.freezer_vence_pronto || 0, T('Vencen pronto'), t.freezer_vence_pronto ? 'is-alerta' : '') +
            stat(t.freezer_vencidas || 0, T('Vencidas'), t.freezer_vencidas ? 'is-peligro' : '') +
            stat(t.freezer_proximo_venc ? fmtFechaCorta(t.freezer_proximo_venc) : '—', T('Próxima a vencer')) +
            stat(t.usadas_total || 0, T('Usadas')) +
            stat(t.descartadas_total || 0, T('Descartadas')) +
        '</div>';

        // Heladera aparte: stock de otra naturaleza, no se suma al freezer
        var hel;
        if (t.heladera_bolsas) {
            var proxima = null;
            DATOS.heladera.forEach(function (p) {
                if (p.estado !== 'vencida' && (proxima === null || p.horas_restantes < proxima)) {
                    proxima = p.horas_restantes;
                }
            });
            hel = '🥛 ' + T('En heladera:') + ' <strong>' + t.heladera_bolsas + ' ' +
                (t.heladera_bolsas === 1 ? T('bolsita') : T('bolsitas')) +
                ' · ' + fmtMl(t.heladera_ml) + '</strong>' +
                (proxima !== null ? ' <span class="lac-sep">·</span> ' + T('la próxima') + ' ' +
                    textoVencHeladera(proxima).toLowerCase() : '');
        } else {
            hel = '🥛 ' + T('Heladera vacía');
        }
        html += '<div class="lac-stats-heladera">' + hel + '</div>';

        // KPIs de ciclo de vida: producción ("litros de amor", resaltado),
        // consumo de León, leche descongelada, desperdicio, y los dos de
        // promedio móvil (días de stock y bolsita sugerida) que se ajustan solos
        // con el consumo real. Los que aún no tienen datos muestran "—".
        var dias = (t.dias_stock !== null && t.dias_stock !== undefined)
            ? t.dias_stock + ' ' + (t.dias_stock === 1 ? T('día') : T('días')) : '—';
        var bolsa = (t.bolsa_sugerida_ml !== null && t.bolsa_sugerida_ml !== undefined)
            ? fmtMl(t.bolsa_sugerida_ml) : '—';
        html += '<div class="lac-kpis-titulo">' + T('Ciclo de la leche') + '</div>' +
            '<div class="lac-kpis">' +
            kpiCard('gota_corazon', fmtLitros(t.producido_ml), T('Producción total'),
                    T('todo lo que produjiste'), 'lac-kpi--amor') +
            kpiCard('mamadera', fmtMl(t.consumida_ml || 0), T('Consumida por {bebe}', { bebe: nombreBebe() })) +
            kpiCard('copo_gota', fmtMl(t.descongelada_ml || 0), T('Descongelada')) +
            kpiCard('gota_tachada', fmtMl(t.desperdicio_ml || 0), T('Desperdicio'), null,
                    (t.desperdicio_ml ? 'is-alerta' : '')) +
            kpiCard('almanaque', dias, T('Alcanza para'),
                    (t.dias_stock == null ? T('cuando {bebe} tome de las bolsitas', { bebe: nombreBebe() })
                                          : T('al ritmo actual'))) +
            kpiCard('bolsita', bolsa, T('Bolsita sugerida'),
                    (t.bolsa_sugerida_ml == null ? T('según el consumo de {bebe}', { bebe: nombreBebe() })
                                                 : T('promedio real'))) +
        '</div>';

        cont.innerHTML = html;
    }

    // ── Render: listas ───────────────────────────────────────────────────────
    function notasHtml(p) {
        return p.notas ? '<div class="lac-item-notas">📝 ' + esc(p.notas) + '</div>' : '';
    }

    // "Extraída 10 jul · 14:30 h" — FECHA primero, hora después (pedido de
    // Mari 2026-07-14; sin hora cargada queda solo la fecha)
    function extraidaTxt(p) {
        return T('Extraída') + ' ' + fmtFechaCorta(p.fecha_extraccion) +
            (p.hora_extraccion ? ' · ' + p.hora_extraccion + ' h' : '');
    }

    // Momento real de extracción (fecha + hora si la hay). Espeja
    // _lac_extraccion_dt del backend: sin hora cargada vale 00:00.
    function extraccionDt(p) {
        var d = parseISO(p.fecha_extraccion);
        if (!d) return null;
        var hm = String(p.hora_extraccion || '').split(':');
        if (hm.length >= 2) d.setHours(Number(hm[0]), Number(hm[1]), 0, 0);
        return d;
    }

    // EDAD de la muestra: cuánto pasó desde que se extrajo (pedido de Mari
    // 2026-07-30). Es distinto del vencimiento: una bolsita del freezer puede
    // tener 5 meses de vida y todavía faltarle un mes para vencerse.
    function edadTxt(p) {
        var d = extraccionDt(p);
        if (!d) return '';
        var ms = Date.now() - d.getTime();
        if (ms < 0) return '';
        var horas = Math.floor(ms / 3600000);
        if (horas < 1) return T('hace menos de 1 h');
        if (horas < 24) return T('hace {n} h', { n: horas });
        var dias = Math.floor(horas / 24);
        if (dias < 60) return dias === 1 ? T('hace 1 día') : T('hace {n} días', { n: dias });
        var meses = Math.floor(dias / 30);
        return meses === 1 ? T('hace 1 mes') : T('hace {n} meses', { n: meses });
    }

    function edadHtml(p) {
        var txt = edadTxt(p);
        if (!txt) return '';
        return ' <span class="lac-sep">·</span> <span class="lac-edad" title="' +
            T('Tiempo que pasó desde que te la extrajiste') + '">' + txt + '</span>';
    }

    function itemFreezer(p) {
        var venc = '<span class="lac-venc t-' + p.estado + '">' + textoVencFreezer(p.dias_restantes) + '</span>' +
                   ' <span class="lac-venc-fecha">(' + fmtFechaCorta(p.vencimiento) + ')</span>';
        return '<div class="lac-item is-' + p.estado + '">' +
            '<div class="lac-item-body">' +
                '<div class="lac-item-top"><span class="lac-item-vol">' + fmtMl(p.volumen_ml) + '</span>' + pill(p.estado) + '</div>' +
                '<div class="lac-item-meta">' + extraidaTxt(p) + edadHtml(p) +
                    ' <span class="lac-sep">·</span> ' + venc +
                '</div>' + notasHtml(p) +
            '</div>' +
            '<div class="lac-item-actions">' +
                '<button type="button" class="lac-btn-bajar" data-lac-bajar="' + p.id + '" title="' + T('Bajar a la heladera para descongelar') + '">⬇ ' + T('Bajar') + '</button>' +
                '<button type="button" class="lac-btn-usar" data-lac-usar="' + p.id + '" title="' + T('Se le dio a {bebe} (fecha de hoy)', { bebe: nombreBebe() }) + '">✓ ' + T('Usada') + '</button>' +
                '<button type="button" class="lac-btn-icono" data-lac-tirar="' + p.id + '" title="' + T('Descartar (fecha de hoy)') + '">🗑</button>' +
                '<button type="button" class="lac-btn-icono" data-lac-mas="' + p.id + '" title="' + T('Más opciones') + '">⋯</button>' +
            '</div>' +
        '</div>';
    }

    // El checkbox marca qué partidas entran en la próxima freezada (botón ⬆).
    // SIEMPRE arranca destildado (pedido de Mari 2026-07-13): la usuaria tilda
    // a mano las que quiere mandar al freezer. Una partida VENCIDA también se
    // puede tildar (pedido de Mari 2026-07-14: se freezó a término pero se
    // cargó tarde en la app) — se marca en ámbar y al freezar pide confirmar
    // que se pasó al freezer antes de vencerse.
    function checkHeladera(p) {
        var venc = !p.freezable;
        return '<label class="lac-check' + (venc ? ' lac-check--venc' : '') + '" title="' +
                (venc ? T('Vencida: se puede freezar igual, pero vas a tener que confirmar que se pasó al freezer antes de vencerse')
                      : T('Tildala para mandarla al freezer con ⬆')) + '">' +
            '<input type="checkbox" class="lac-check-input" value="' + p.id + '"' +
                (venc ? ' data-venc="1"' : '') + '>' +
        '</label>';
    }

    // Etiqueta que diferencia leche recién extraída ("Fresca") de la bajada del
    // freezer para descongelar ("Descongelada"). Pedido de Mari: en la heladera
    // van a convivir los dos tipos (ej. cuando León arranque el jardín).
    function tipoTag(p) {
        if (p.tipo === 'descongelada') {
            return '<span class="lac-tipo lac-tipo--desc" title="' + T('Bajada del freezer para descongelar') + '">❄→🥛 ' + T('Descongelada') + '</span>';
        }
        return '<span class="lac-tipo lac-tipo--fresca" title="' + T('Extraída y puesta directo en la heladera') + '">🥛 ' + T('Fresca') + '</span>';
    }

    function itemHeladera(p) {
        var esDesc = p.tipo === 'descongelada';
        return '<div class="lac-item is-' + p.estado + (esDesc ? ' lac-item--desc' : ' lac-item--fresca') + '">' +
            '<div class="lac-item-body">' +
                '<div class="lac-item-top"><span class="lac-item-vol">' + fmtMl(p.volumen_ml) + '</span>' +
                    tipoTag(p) + pill(p.estado) + '</div>' +
                '<div class="lac-item-meta">' + extraidaTxt(p) + edadHtml(p) +
                    ' <span class="lac-sep">·</span> <span class="lac-venc t-' + p.estado + '">' +
                    textoVencHeladera(p.horas_restantes) + '</span>' +
                '</div>' + notasHtml(p) +
            '</div>' +
            '<div class="lac-item-actions">' +
                '<button type="button" class="lac-btn-usar" data-lac-usar="' + p.id + '" title="' + T('Se le dio a {bebe} (fecha de hoy)', { bebe: nombreBebe() }) + '">✓ ' + T('Usada') + '</button>' +
                '<button type="button" class="lac-btn-icono" data-lac-tirar="' + p.id + '" title="' + T('Descartar (fecha de hoy)') + '">🗑</button>' +
                '<button type="button" class="lac-btn-icono" data-lac-mas="' + p.id + '" title="' + T('Más opciones') + '">⋯</button>' +
                checkHeladera(p) +
            '</div>' +
        '</div>';
    }

    var CIERRE_VERBO = { usada: 'Usada el', descartada: 'Descartada el', trasladada: 'Freezada el' };

    function itemHistorial(p) {
        var ubi = p.ubicacion === 'freezer' ? '🧊' : '🥛';
        var verbo = T(CIERRE_VERBO[p.motivo_cierre] || 'Cerrada el');
        return '<div class="lac-item lac-item--hist">' +
            '<div class="lac-item-body">' +
                '<div class="lac-item-top"><span class="lac-item-vol">' + fmtMl(p.volumen_ml) + '</span>' +
                    pill(p.estado) + ' <span class="lac-hist-ubi" title="' + (p.ubicacion === 'freezer' ? T('Freezer') : T('Heladera')) + '">' + ubi + '</span></div>' +
                '<div class="lac-item-meta">' + extraidaTxt(p) +
                    ' <span class="lac-sep">·</span> ' + verbo + ' ' + fmtFechaCorta(p.fecha_cierre) +
                '</div>' + notasHtml(p) +
            '</div>' +
            '<div class="lac-item-actions">' +
                '<button type="button" class="lac-btn-icono" data-lac-reabrir="' + p.id + '" title="' + T('Reabrir (deshacer el cierre)') + '">↩</button>' +
                '<button type="button" class="lac-btn-icono" data-lac-eliminar="' + p.id + '" title="' + T('Eliminar definitivamente') + '">✕</button>' +
            '</div>' +
        '</div>';
    }

    function renderLista(contId, countId, items, itemFn, vacioHtml) {
        var cont = $(contId);
        $(countId).textContent = items.length ? items.length : '';
        if (!items.length) {
            cont.innerHTML = '<div class="lac-lista-vacia">' + vacioHtml + '</div>';
            return;
        }
        cont.innerHTML = items.map(itemFn).join('');
    }

    function renderListas() {
        renderLista('lac-lista-freezer', 'lac-freezer-count', DATOS.freezer, itemFreezer,
            T('Sin bolsitas en el freezer.'));
        renderLista('lac-lista-heladera', 'lac-heladera-count', DATOS.heladera, itemHeladera,
            T('Nada en la heladera. Lo que sobre al final del día, se freeza.'));
        renderLista('lac-lista-historial', 'lac-historial-count', DATOS.historial, itemHistorial,
            T('Todavía no se cerró ninguna bolsita.'));
    }

    // El botón ⬆ está apagado mientras no haya ninguna bolsita tildada en la
    // heladera, y se enciende apenas hay una. El estado se mira siempre del DOM
    // (los checkbox son la fuente de verdad de lo que se tildó) y se repinta al
    // dibujar las listas y con cada tilde.
    function pintarBotonFreezar() {
        var btn = $('lac-btn-freezar');
        if (!btn) return;
        var hay = !!document.querySelector('#lac-lista-heladera .lac-check-input:checked');
        btn.classList.toggle('is-lista', hay);
    }

    function renderTodo() {
        renderAviso();
        renderBebe();
        renderRecordatorio();
        renderConfig();
        renderTablero();
        renderListas();
        // Va DESPUÉS de renderListas: los checkbox se dibujan ahí, y al
        // redibujarse arrancan todos destildados.
        pintarBotonFreezar();
        // El gráfico se repinta con cada payload fresco: si se acaba de cargar
        // una bolsita, ya se ve reflejada sin recargar la página.
        if (window.LAC_GRAFICO) window.LAC_GRAFICO.render(DATOS);
        // Tarjeta de vencimiento del form de alta: se repinta con los
        // parámetros vigentes (si la mamá los cambió en Ajustes, se ve acá).
        if ($('lac-ex-hint')) pintarVencimiento();
    }

    // ── Overlays ─────────────────────────────────────────────────────────────
    var OVERLAYS = ['lac-modal-cerrar', 'lac-modal-mas',
                    'lac-modal-editor', 'lac-modal-confirm'];

    function cerrarOverlay(ov) { ov.hidden = true; }

    function subPartida(p) {
        return '· ' + fmtMl(p.volumen_ml) + ' · ' +
            (p.ubicacion === 'freezer' ? T('freezer') : T('heladera'));
    }

    // ── Cierres one-click (fecha = hoy) con Deshacer ─────────────────────────
    function deshacerCierre(id, textoOk) {
        postAccion('/api/lactancia/' + id + '/reabrir', new URLSearchParams(), function () {
            toast(textoOk || ('↩ ' + T('Deshecho: la bolsita volvió al stock.')), 'info');
        });
    }

    function cerrarDirecto(id, motivo, consumido) {
        var p = buscarPartida(id);
        var params = new URLSearchParams();
        params.append('motivo', motivo);   // fecha_cierre vacía → hoy en el server
        // Consumo real de León (opcional, solo 'usada'): cuántos ml tomó.
        if (motivo === 'usada' && consumido !== undefined && consumido !== null && consumido !== '') {
            params.append('consumido_ml', consumido);
        }
        postAccion('/api/lactancia/' + id + '/cerrar', params, function () {
            var vol = p ? fmtMl(p.volumen_ml) : T('Bolsita');
            var texto = (motivo === 'usada')
                ? '✓ ' + T('{vol} marcada como usada.', { vol: vol })
                : '🗑 ' + T('{vol} descartada.', { vol: vol });
            toast(texto, 'ok', function () { deshacerCierre(id); });
        });
    }

    // ── Modal: Cerrar con otra fecha ─────────────────────────────────────────
    function abrirCerrarFecha(id, motivo) {
        var p = buscarPartida(id);
        if (!p) return;
        cfPartidaId = id;
        cfMotivo = motivo;
        $('lac-cf-titulo').childNodes[0].textContent = (motivo === 'usada')
            ? '✓ ' + T('Marcar usada') + ' ' : '🗑 ' + T('Marcar descartada') + ' ';
        $('lac-cf-sub').textContent = subPartida(p);
        $('lac-cf-fecha-label').textContent = (motivo === 'usada')
            ? T('¿Cuándo se usó?') : T('¿Cuándo se descartó?');
        fpCfFecha.setDate(isoDate(hoy()), true);
        $('lac-cf-notas').value = '';
        $('lac-modal-cerrar').hidden = false;
    }

    function guardarCierre() {
        if (cfPartidaId === null) return;
        var fecha = $('lac-cf-fecha').value;
        if (!fecha) {
            toast('⚠ ' + T('Elegí la fecha de cierre.'), 'error');
            return;
        }
        var params = new URLSearchParams();
        params.append('motivo', cfMotivo);
        params.append('fecha_cierre', fecha);
        params.append('notas', $('lac-cf-notas').value.trim());
        var id = cfPartidaId;
        var btn = $('lac-cf-guardar');
        btn.disabled = true;
        postAccion('/api/lactancia/' + id + '/cerrar', params, function () {
            $('lac-modal-cerrar').hidden = true;
            toast(cfMotivo === 'usada' ? '✓ ' + T('Bolsita marcada como usada.')
                                       : '🗑 ' + T('Bolsita descartada.'),
                'ok', function () { deshacerCierre(id); });
        }, function () { btn.disabled = false; });
    }

    // ── Freezar la combinación de las tildadas (botón ⬆ del panel Heladera) ──
    // Combina las partidas de heladera con checkbox tildado en UNA partida de
    // freezer (el server suma volúmenes y usa la extracción más vieja).
    // Deshacer llama a /reabrir de un origen y revierte la combinación entera.
    function freezarSeleccionadas() {
        var checks = document.querySelectorAll('#lac-lista-heladera .lac-check-input:checked');
        var ids = [].map.call(checks, function (c) { return c.value; });
        if (!ids.length) {
            toast('⚠ ' + T('Tildá al menos una bolsita de heladera.'), 'error');
            return;
        }
        // Si hay vencidas entre las tildadas, hay que declarar que se pasaron
        // al freezer antes de vencerse (checkbox obligatorio del modal).
        var vencidas = [].filter.call(checks, function (c) { return c.dataset.venc === '1'; }).length;
        if (vencidas) {
            abrirConfirm({
                emoji: '❄️', titulo: T('Freezar bolsitas vencidas'), peligro: false, boton: T('Freezar'),
                msg: vencidas === 1
                    ? T('Una de las bolsitas tildadas figura vencida.')
                    : T('{n} de las bolsitas tildadas figuran vencidas.', { n: vencidas }),
                check: T('Confirmo que se pasó al freezer antes de vencerse (se cargó tarde en la app).'),
                accion: function () { freezarPost(ids, true); }
            });
            return;
        }
        // Caso normal (ninguna vencida): igual confirma, como el resto de las
        // acciones que se concretan al toque (pedido de Mari 2026-07-19).
        var vol = 0;
        ids.forEach(function (id) {
            var p = buscarPartida(parseInt(id, 10));
            if (p) vol += p.volumen_ml;
        });
        abrirConfirm({
            emoji: '❄️', titulo: T('Mandar al freezer'), peligro: false, boton: T('Sí, freezar'),
            msg: T('Se combinan {n} {cuales}{vol} en una sola bolsita de freezer, con la fecha de extracción más vieja.', {
                n: ids.length,
                cuales: ids.length === 1 ? T('bolsita') : T('bolsitas'),
                vol: vol ? ' (' + fmtMl(vol) + ')' : ''
            }),
            accion: function () { freezarPost(ids, false); }
        });
    }

    function freezarPost(ids, confirmarVencidas) {
        var params = new URLSearchParams();
        params.append('ids', ids.join(','));
        if (confirmarVencidas) params.append('confirmar_vencidas', '1');
        var primero = parseInt(ids[0], 10);
        var btn = $('lac-btn-freezar');
        btn.disabled = true;
        postAccion('/api/lactancia/freezar', params, function (data) {
            var vol = null;
            (data.historial || []).forEach(function (p) {
                if (ids.indexOf(String(p.id)) !== -1) vol = (vol || 0) + p.volumen_ml;
            });
            toast('❄️ ' + T('{n} {cuales}{detalle}', {
                    n: ids.length,
                    cuales: ids.length === 1 ? T('bolsita freezada') : T('bolsitas freezadas'),
                    detalle: vol ? T(': {vol} al freezer.', { vol: fmtMl(vol) }) : '.'
                }),
                'ok', function () { deshacerCierre(primero, '↩ ' + T('Deshecho: volvieron a la heladera.')); });
        }, function () { btn.disabled = false; });
    }

    // ── Bajar del freezer a la heladera para descongelar ─────────────────────
    // Acción nueva: doble confirmación (modal + checkbox obligatorio). Crea una
    // partida de heladera 'descongelada' (vence a las N h de bajarla, no se
    // vuelve a congelar). Deshacer llama a /reabrir del id de freezer (borra la
    // descongelada y repone la bolsa al freezer).
    function pedirBajar(id) {
        var p = buscarPartida(id);
        if (!p) return;
        var horas = DATOS.params.descongelada_horas || 24;
        abrirConfirm({
            emoji: '⬇️', titulo: T('Bajar a descongelar'), peligro: false, boton: T('Sí, bajar'),
            msg: T('Bajás {vol} del freezer a la heladera para descongelar. Va a estar lista por {h} h y no se puede volver a congelar.',
                   { vol: fmtMl(p.volumen_ml), h: horas }),
            check: T('Confirmo que bajé (o bajo ahora) esta bolsita a la heladera.'),
            accion: function () { bajarPost(id); }
        });
    }

    function bajarPost(id) {
        var p = buscarPartida(id);
        var vol = p ? fmtMl(p.volumen_ml) : T('La bolsita');
        postAccion('/api/lactancia/' + id + '/bajar', new URLSearchParams(), function () {
            toast('⬇️ ' + T('{vol} a la heladera para descongelar.', { vol: vol }),
                'ok', function () { deshacerCierre(id, '↩ ' + T('Deshecho: volvió al freezer.')); });
        });
    }

    // ── Hoja "Más opciones" ──────────────────────────────────────────────────
    function abrirMas(id) {
        var p = buscarPartida(id);
        if (!p) return;
        masPartidaId = id;
        $('lac-mas-sub').textContent = subPartida(p);
        $('lac-modal-mas').hidden = false;
    }

    // ── Modal: Editor (fecha/hora de extracción editables en ambas
    //    ubicaciones; `cargada` — base del vencimiento de heladera — no) ──────
    function abrirEditor(id) {
        var p = buscarPartida(id);
        if (!p) return;
        edPartidaId = id;
        $('lac-ed-sub').textContent = subPartida(p);
        $('lac-ed-volumen').value = p.volumen_ml;
        $('lac-ed-notas').value = p.notas || '';
        fpEdFecha.setDate(p.fecha_extraccion, true);
        fpEdHora.setDate(p.hora_extraccion || '', true);
        $('lac-modal-editor').hidden = false;
    }

    function guardarEditor() {
        if (edPartidaId === null) return;
        var params = new URLSearchParams();
        params.append('volumen_ml', $('lac-ed-volumen').value);
        params.append('notas', $('lac-ed-notas').value.trim());
        if (!$('lac-ed-fecha').value) {
            toast('⚠ ' + T('La fecha de extracción es obligatoria.'), 'error');
            return;
        }
        params.append('fecha_extraccion', $('lac-ed-fecha').value);
        params.append('hora_extraccion', $('lac-ed-hora').value);
        var btn = $('lac-ed-guardar');
        btn.disabled = true;
        postAccion('/api/lactancia/' + edPartidaId + '/editar', params, function () {
            $('lac-modal-editor').hidden = true;
            toast('✎ ' + T('Bolsita actualizada.'));
        }, function () { btn.disabled = false; });
    }

    // ── Modal: Confirmación genérica ─────────────────────────────────────────
    // Cualquier acción que se concrete al toque (Usada, Tirar, Eliminar) pide
    // confirmación antes — así un toque sin querer no la ejecuta (pedido de
    // Mari 2026-07-13). `confirmAccion` es la función que corre al confirmar.
    var confirmAccion = null;

    // Preferencia guardada en el PERFIL de la mamá (no en el teléfono): se
    // cambia desde Configuraciones y la acompaña a cualquier dispositivo donde
    // entre con su cuenta. Si el dato todavía no llegó, se asume que sí.
    function confirmacionesActivadas() {
        var p = DATOS.params || {};
        return p.pedir_confirmacion !== false;
    }

    // opts.check (opcional): texto de un checkbox OBLIGATORIO — el botón de
    // confirmar queda deshabilitado hasta tildarlo (ej. freezar una vencida:
    // hay que declarar que se pasó al freezer antes de vencerse).
    function abrirConfirm(opts) {
        // Preferencia "sin confirmación" (de Configuraciones): ejecuta la acción
        // directo, sin modal ni checkbox ni input opcional. Aplica a TODAS.
        if (!confirmacionesActivadas()) {
            var inSalto = $('lac-confirm-input');
            if (inSalto) inSalto.value = '';
            if (opts.accion) opts.accion();
            return;
        }
        $('lac-confirm-emoji').textContent = opts.emoji || '⚠️';
        $('lac-confirm-titulo').textContent = opts.titulo;
        $('lac-confirm-msg').textContent = opts.msg;
        var btn = $('lac-confirm-si');
        btn.textContent = opts.boton;
        btn.className = opts.peligro ? 'btn-peligro' : 'btn-acento';

        var wrap = $('lac-confirm-check-wrap');
        var chk = $('lac-confirm-check');
        chk.checked = false;
        if (opts.check) {
            $('lac-confirm-check-txt').textContent = opts.check;
            wrap.hidden = false;
            btn.disabled = true;
        } else {
            wrap.hidden = true;
            btn.disabled = false;
        }

        // Input numérico OPCIONAL (ej. ml que tomó el bebé). Dejarlo vacío es
        // válido — no toca el estado del botón.
        // opts.input = {label, hint, max}: con `max` aparece además el botón
        // "Tomó todo (N ml)", que es el caso más común de un toque.
        var inWrap = $('lac-confirm-input-wrap');
        var inEl = $('lac-confirm-input');
        var btnTodo = $('lac-confirm-input-todo');
        inEl.value = '';
        if (opts.input) {
            $('lac-confirm-input-label').textContent = opts.input.label || '';
            $('lac-confirm-input-hint').textContent = opts.input.hint || '';
            if (opts.input.max != null) {
                inEl.max = opts.input.max;
                btnTodo.textContent = '✓ ' + T('Tomó todo ({vol})',
                                               { vol: fmtMl(opts.input.max) });
                btnTodo.hidden = false;
            } else {
                inEl.removeAttribute('max');
                btnTodo.hidden = true;
            }
            inWrap.hidden = false;
        } else {
            inWrap.hidden = true;
        }

        confirmAccion = opts.accion;
        $('lac-modal-confirm').hidden = false;
    }

    function confirmarSi() {
        var accion = confirmAccion;
        confirmAccion = null;
        $('lac-modal-confirm').hidden = true;
        if (accion) accion();
    }

    // "✓ Usada" y "🗑 Tirar" de cada partida: piden confirmación antes de cerrar
    function pedirCierre(id, motivo) {
        var p = buscarPartida(id);
        if (!p) return;
        var det = T('{vol} (extraída el {fecha})',
                    { vol: fmtMl(p.volumen_ml), fecha: fmtFecha(p.fecha_extraccion) });
        if (motivo === 'usada') {
            abrirConfirm({
                emoji: '✓', titulo: T('Marcar como usada'), peligro: false, boton: T('Sí, usada'),
                msg: T('Se le dio a {bebe}: {det}. Se cierra con fecha de hoy.',
                       { bebe: nombreBebe(), det: det }),
                input: { label: T('¿Cuántos ml tomó {bebe}?', { bebe: nombreBebe() }),
                         hint: T('Es opcional, pero con este dato calculo la bolsita que te conviene y para cuántos días te alcanza.'),
                         max: p.volumen_ml },
                accion: function () {
                    cerrarDirecto(id, 'usada', $('lac-confirm-input').value.trim());
                }
            });
        } else {
            abrirConfirm({
                emoji: '🗑', titulo: T('Descartar bolsita'), peligro: true, boton: T('Sí, descartar'),
                msg: T('Se descarta {det}. Se cierra con fecha de hoy.', { det: det }),
                accion: function () { cerrarDirecto(id, 'descartada'); }
            });
        }
    }

    function abrirConfirmEliminar(id) {
        var p = buscarPartida(id);
        if (!p) return;
        abrirConfirm({
            emoji: '⚠️', titulo: T('Eliminar bolsita'), peligro: true, boton: T('Sí, eliminar'),
            msg: T('Se elimina definitivamente la bolsita de {vol} (extraída el {fecha}). Esta acción no se puede deshacer.',
                   { vol: fmtMl(p.volumen_ml), fecha: fmtFecha(p.fecha_extraccion) }),
            accion: function () {
                postAccion('/api/lactancia/' + id + '/eliminar', new URLSearchParams(), function () {
                    toast('✕ ' + T('Bolsita eliminada.'), 'info');
                });
            }
        });
    }

    // ── Reabrir desde el historial ───────────────────────────────────────────
    // ↩ del historial: pide confirmación como el resto de las acciones que se
    // concretan al toque (pedido de Mari 2026-07-19). En una freezada revierte
    // la combinación COMPLETA, así que se avisa explícitamente.
    function pedirReabrir(id) {
        var p = buscarPartida(id);
        if (!p) return;
        var esFreezada = p.motivo_cierre === 'trasladada';
        abrirConfirm({
            emoji: '↩', titulo: T('Reabrir bolsita'), peligro: false, boton: T('Sí, reabrir'),
            msg: T('Vuelve al stock {vol} (extraída el {fecha}){extra}', {
                vol: fmtMl(p.volumen_ml),
                fecha: fmtFecha(p.fecha_extraccion),
                extra: esFreezada ? T('. Al ser una freezada, se deshace la combinación completa.') : '.'
            }),
            accion: function () { reabrir(id); }
        });
    }

    function reabrir(id) {
        postAccion('/api/lactancia/' + id + '/reabrir', new URLSearchParams(), function () {
            toast('↩ ' + T('Bolsita reabierta: volvió al stock.'), 'info');
        });
    }

    // ── Form de alta (destino elegible: heladera o freezer) ─────────────────
    // La extracción suele tomar ~30 min, así que se precarga la hora de INICIO
    // estimada (ahora − 30 min). Fecha y hora salen del MISMO Date, así que si
    // cruza medianoche la fecha pasa sola al día anterior. El backend acepta
    // pasado; solo rechaza futuro.
    function resetFormAlta() {
        $('lac-form-extraccion').reset();   // reset devuelve el radio a heladera
        var d = new Date(Date.now() - 30 * 60 * 1000);
        fpExFecha.setDate(isoDate(d), true);   // reset no repone el altInput
        fpExHora.setDate(fmtHoraDe(d), true);
        pintarDestino();
        pintarVencimiento();
    }

    function initForms() {
        resetFormAlta();

        $('lac-form-extraccion').addEventListener('submit', function (e) {
            e.preventDefault();
            var vol = $('lac-ex-volumen').value.trim();
            if (!vol) {
                toast('⚠ ' + T('Cargá el volumen en ml.'), 'error');
                $('lac-ex-volumen').focus();
                return;
            }
            var ubi = ubicacionElegida();
            var params = new URLSearchParams();
            params.append('ubicacion', ubi);
            params.append('volumen_ml', vol);
            params.append('fecha_extraccion', $('lac-ex-fecha').value || '');
            params.append('hora_extraccion', $('lac-ex-hora').value || '');
            params.append('notas', $('lac-ex-notas').value.trim());

            var btn = $('lac-ex-guardar');
            btn.disabled = true;
            postAccion('/api/lactancia/crear', params, function () {
                if (ubi === 'freezer') {
                    toast('🧊 ' + T('{vol} al freezer.', { vol: fmtMl(vol) }));
                } else {
                    toast('🥛 ' + T('{vol} a la heladera.', { vol: fmtMl(vol) }));
                }
                resetFormAlta();
                $('lac-ex-volumen').focus();
            }, function () { btn.disabled = false; });
        });
    }

    // ── Stepper ±10 ml ───────────────────────────────────────────────────────
    // Sin focus() desde los botones: en el celular abriría el teclado en cada
    // tap. El número igual se toca directo y se escribe a mano.
    function initStepper() {
        var inp = $('lac-ex-volumen');
        if (!inp) return;
        function paso(delta) {
            var v = parseInt(inp.value, 10);
            if (isNaN(v)) {
                if (delta < 0) return;   // vacío y "−" → se queda vacío
                v = 0;
            }
            inp.value = Math.min(2000, Math.max(1, v + delta));
        }
        $('lac-ex-menos').addEventListener('click', function () { paso(-10); });
        $('lac-ex-mas').addEventListener('click', function () { paso(10); });
    }

    // ── Destino + vencimiento dinámico ───────────────────────────────────────
    // Espeja _lac_vencimiento del backend (logica.py): heladera = extracción +
    // heladera_horas; freezer = extracción + freezer_meses (al fin del día).
    // Es SOLO informativo — el backend recalcula siempre por su cuenta.
    function ubicacionElegida() {
        var r = document.querySelector('#lac-form-extraccion input[name="ubicacion"]:checked');
        return r ? r.value : 'heladera';
    }

    // Suma meses clampeando al último día del mes, igual que
    // _act_sumar_intervalo en logica.py (31-ene + 1 mes → 28-feb, no 3-mar).
    function sumarMeses(d, n) {
        var total = d.getMonth() + n;
        var anio = d.getFullYear() + Math.floor(total / 12);
        var mes = ((total % 12) + 12) % 12;
        var ultimoDia = new Date(anio, mes + 1, 0).getDate();
        return new Date(anio, mes, Math.min(d.getDate(), ultimoDia));
    }

    function pintarVencimiento() {
        var hint = $('lac-ex-hint');
        if (!hint) return;
        var f = $('lac-ex-fecha').value, h = $('lac-ex-hora').value;
        if (!f || !h) { hint.textContent = ''; return; }
        var p = String(f).split('-'), hm = String(h).split(':');
        if (p.length !== 3 || hm.length < 2) { hint.textContent = ''; return; }
        var base = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]),
                            Number(hm[0]), Number(hm[1]));
        if (isNaN(base.getTime())) { hint.textContent = ''; return; }

        if (ubicacionElegida() === 'freezer') {
            var m = DATOS.params.freezer_meses || 6;
            hint.textContent = T('Vence el {fecha} ({m} meses en freezer).',
                                 { fecha: fmtFechaCorta(sumarMeses(base, m)), m: m });
        } else {
            var hs = DATOS.params.heladera_horas || 48;
            var v = new Date(base.getTime() + hs * 3600 * 1000);
            hint.textContent = T('Vence el {fecha} a las {hora} ({h} h en heladera).',
                                 { fecha: fmtFechaCorta(v), hora: fmtHoraDe(v), h: hs });
        }
    }

    // La tarjeta elegida se pinta por CSS con :has(input:checked), pero algunos
    // navegadores no la repintan al vuelo cuando cambia el radio (recién al
    // recargar). Por eso el JS marca además la clase is-activa: mismo estilo,
    // repintado seguro. Sin JS manda :has y funciona igual.
    function pintarDestino() {
        var cards = document.querySelectorAll('#lac-form-extraccion .lac-destino-card');
        [].slice.call(cards).forEach(function (c) {
            var r = c.querySelector('input[name="ubicacion"]');
            c.classList.toggle('is-activa', !!(r && r.checked));
        });
    }

    function initDestino() {
        var radios = document.querySelectorAll('#lac-form-extraccion input[name="ubicacion"]');
        [].slice.call(radios).forEach(function (r) {
            r.addEventListener('change', function () {
                pintarDestino();
                pintarVencimiento();
            });
        });
        pintarDestino();
    }

    // Calendarios: el formato de fecha es día/mes (decisión de Mari).
    var LOCALE_FP = 'es';

    // El teclado nativo no debe taparle el calendario/reloj en el primer
    // toque: ese toque solo tiene que abrir el picker. Recién si vuelve a
    // tocar el campo (ya enfocado, para escribir la fecha/hora a mano) se
    // habilita el teclado. inputmode="none" es lo que el navegador respeta
    // para no levantar el teclado al enfocar.
    function frenarTecladoHastaSegundoToque(fp) {
        var el = fp.altInput || fp.input;
        el.setAttribute('inputmode', 'none');
        el.addEventListener('pointerdown', function () {
            el.setAttribute('inputmode', document.activeElement === el ? 'text' : 'none');
        });
        el.addEventListener('blur', function () { el.setAttribute('inputmode', 'none'); });
    }

    function initFlatpickrs() {
        // Fecha del alta: en la pastilla se muestra corta ("Hoy" o "28/07").
        // disableMobile es CLAVE acá (mismo motivo que en las horas): sin él,
        // en celulares flatpickr se reemplaza por el <input type="date"> NATIVO
        // y se pierden el altInput y el "Hoy".
        fpExFecha = flatpickr($('lac-ex-fecha'), {
            locale: LOCALE_FP, dateFormat: 'Y-m-d', altInput: true, altFormat: 'd/m',
            allowInput: true, maxDate: 'today', disableMobile: true,
            formatDate: function (date, format, locale) {
                if (format === 'd/m' && isoDate(date) === isoDate(hoy())) return T('Hoy');
                return flatpickr.formatDate(date, format, locale);
            },
            onChange: function () { pintarVencimiento(); }
        });
        frenarTecladoHastaSegundoToque(fpExFecha);
        fpCfFecha = flatpickr($('lac-cf-fecha'), {
            locale: LOCALE_FP, dateFormat: 'Y-m-d', altInput: true, altFormat: 'd/m/Y',
            allowInput: true, maxDate: 'today'
        });
        frenarTecladoHastaSegundoToque(fpCfFecha);
        fpEdFecha = flatpickr($('lac-ed-fecha'), {
            locale: LOCALE_FP, dateFormat: 'Y-m-d', altInput: true, altFormat: 'd/m/Y',
            allowInput: true, maxDate: 'today'
        });
        frenarTecladoHastaSegundoToque(fpEdFecha);
        // Hora en 24h. disableMobile es CLAVE: sin él, flatpickr en celulares
        // se reemplaza solo por el <input type="time"> NATIVO ("modo mobile"),
        // que en iOS es 12h AM/PM y desborda la tarjeta "+Cargar" — justo lo
        // que este picker vino a evitar.
        fpExHora = flatpickr($('lac-ex-hora'), {
            enableTime: true, noCalendar: true, dateFormat: 'H:i',
            time_24hr: true, allowInput: true, disableMobile: true,
            onChange: function () { pintarVencimiento(); },
            onClose: function () { pintarVencimiento(); }
        });
        frenarTecladoHastaSegundoToque(fpExHora);
        fpEdHora = flatpickr($('lac-ed-hora'), {
            enableTime: true, noCalendar: true, dateFormat: 'H:i',
            time_24hr: true, allowInput: true, disableMobile: true
        });
        frenarTecladoHastaSegundoToque(fpEdHora);
        fpRecHora = flatpickr($('lac-rec-hora'), {
            enableTime: true, noCalendar: true, dateFormat: 'H:i',
            time_24hr: true, allowInput: true, disableMobile: true
        });
        frenarTecladoHastaSegundoToque(fpRecHora);
        fpBebeNac = flatpickr($('lac-bebe-nac'), {
            locale: LOCALE_FP, dateFormat: 'Y-m-d', altInput: true, altFormat: 'd/m/Y',
            allowInput: true, maxDate: 'today'
        });
        frenarTecladoHastaSegundoToque(fpBebeNac);
    }

    // ── Recordatorio nocturno de bajar bolsitas ──────────────────────────────
    // Refleja la config guardada (toggle + hora) y muestra el banner cuando el
    // recordatorio está VIGENTE (el server decide `pendiente`: activo + pasó la
    // hora + hay leche en freezer + no se bajó ninguna hoy). Es solo un aviso.
    function renderRecordatorio() {
        var rec = DATOS.recordatorio || { activo: false, hora: '21:00', pendiente: false, dias: [0, 1, 2, 3, 4, 5, 6] };
        var chk = $('lac-rec-activo');
        if (chk) chk.checked = !!rec.activo;
        if (fpRecHora) fpRecHora.setDate(rec.hora || '21:00', true);
        else { var h = $('lac-rec-hora'); if (h) h.value = rec.hora || '21:00'; }

        var dias = rec.dias || [0, 1, 2, 3, 4, 5, 6];
        var cont = $('lac-rec-dias');
        if (cont) {
            var botones = cont.querySelectorAll('.lac-rec-dia');
            for (var i = 0; i < botones.length; i++) {
                var d = parseInt(botones[i].getAttribute('data-dia'), 10);
                botones[i].classList.toggle('is-activo', dias.indexOf(d) !== -1);
            }
        }

        var banner = $('lac-rec-banner');
        if (banner) {
            if (rec.pendiente) {
                banner.innerHTML = '🌙 ' + T('Acordate de') + ' <strong>' +
                    T('bajar bolsitas del freezer a la heladera') + '</strong> ' +
                    T('para mañana.');
                banner.hidden = false;
            } else {
                banner.hidden = true;
                banner.innerHTML = '';
            }
        }
    }

    function guardarRecordatorio() {
        var params = new URLSearchParams();
        params.append('activo', $('lac-rec-activo').checked ? '1' : '0');
        params.append('hora', ($('lac-rec-hora').value || '').trim());
        var cont = $('lac-rec-dias');
        if (cont) {
            var activos = [];
            var botones = cont.querySelectorAll('.lac-rec-dia.is-activo');
            for (var i = 0; i < botones.length; i++) activos.push(botones[i].getAttribute('data-dia'));
            params.append('dias', activos.join(','));
        }
        var btn = $('lac-rec-guardar');
        btn.disabled = true;
        postAccion('/api/lactancia/recordatorio', params, function () {
            toast('🌙 ' + T('Recordatorio guardado.'));
        }, function () { btn.disabled = false; });
    }

    // ── Perfil del bebé (nombre + fecha de nacimiento) ───────────────────────
    function renderBebe() {
        var b = DATOS.bebe || { nombre: '', fecha_nacimiento: '', edad_texto: '' };
        var nom = $('lac-bebe-nombre');
        if (nom && document.activeElement !== nom) nom.value = b.nombre || '';
        if (fpBebeNac) fpBebeNac.setDate(b.fecha_nacimiento || '', false);
        var edad = $('lac-bebe-edad');
        if (edad) edad.textContent = b.edad_texto ? '· ' + b.edad_texto : '';
    }

    function guardarBebe() {
        var params = new URLSearchParams();
        params.append('nombre', ($('lac-bebe-nombre').value || '').trim());
        params.append('fecha_nacimiento', $('lac-bebe-nac').value || '');
        var btn = $('lac-bebe-guardar');
        btn.disabled = true;
        postAccion('/api/lactancia/bebe', params, function () {
            toast('👶 ' + T('Datos del bebé guardados.'));
        }, function () { btn.disabled = false; });
    }

    // ── Configuraciones (tiempos, bolsitas y confirmaciones) ────────────────
    // Los valores viven en el perfil de la mamá y llegan en DATOS.params, ya
    // resueltos por el servidor (lo que ella configuró o, si no tocó nada, el
    // valor por defecto). Acá solo se pintan y se mandan de vuelta.
    var CFG_NUM = ['freezer_meses', 'heladera_horas', 'descongelada_horas',
                   'aviso_freezer_dias', 'aviso_heladera_horas',
                   'aviso_descongelada_horas', 'combinar_min_horas',
                   'freezar_hasta_horas', 'bolsa_capacidad_ml'];
    var CFG_BOOL = ['bolsa_capacidad_activa', 'pedir_confirmacion'];

    // La capacidad solo se edita si la mamá declaró que sus bolsitas tienen tope.
    function pintarCapacidad() {
        var tog = $('cfg-bolsa_capacidad_activa');
        var fila = $('cfg-bolsa-fila');
        if (tog && fila) fila.classList.toggle('is-inactiva', !tog.checked);
    }

    function renderConfig() {
        var p = DATOS.params || {};
        CFG_NUM.forEach(function (k) {
            var el = $('cfg-' + k);
            // No pisar lo que la mamá está tipeando en ese momento.
            if (el && p[k] !== undefined && document.activeElement !== el) el.value = p[k];
        });
        CFG_BOOL.forEach(function (k) {
            var el = $('cfg-' + k);
            if (el && p[k] !== undefined) el.checked = !!p[k];
        });
        pintarCapacidad();
    }

    function guardarConfig() {
        var params = new URLSearchParams();
        CFG_NUM.forEach(function (k) {
            var el = $('cfg-' + k);
            if (el) params.append(k, (el.value || '').trim());
        });
        CFG_BOOL.forEach(function (k) {
            var el = $('cfg-' + k);
            if (el) params.append(k, el.checked ? '1' : '0');
        });
        var btn = $('lac-config-guardar');
        btn.disabled = true;
        postAccion('/api/lactancia/config', params, function () {
            toast('⚙️ ' + T('Ajustes guardadas.'));
        }, function () { btn.disabled = false; });
    }

    // ── Barra de secciones (SOLO mobile) ─────────────────────────────────────
    // Cambia data-lac-sec en .lac-wrap (el CSS muestra solo esa sección) y, si
    // la sección elegida es un <details> (bebé/recordatorio/historial), la abre.
    // En escritorio la barra está oculta y no afecta nada.
    // Es una barra fija abajo (estilo app), no un desplegable: la pestaña
    // activa se marca con .is-activa y el CSS le sube la opacidad.
    function initNavMobile() {
        var barra = document.querySelector('.lac-tabbar');
        var wrap  = document.querySelector('.lac-wrap');
        if (!barra || !wrap) return;
        var tabs = [].slice.call(barra.querySelectorAll('.lac-tab'));

        function activar(sec) {
            wrap.setAttribute('data-lac-sec', sec);
            var el = document.querySelector('.lac-sec--' + sec);
            if (el && el.tagName === 'DETAILS') el.open = true;
            tabs.forEach(function (t) {
                var esta = t.getAttribute('data-sec') === sec;
                t.classList.toggle('is-activa', esta);
                t.setAttribute('aria-current', esta ? 'page' : 'false');
            });
        }

        tabs.forEach(function (t) {
            t.addEventListener('click', function () {
                activar(t.getAttribute('data-sec'));
            });
        });

        activar(wrap.getAttribute('data-lac-sec') || 'cargar');
    }

    // ── Init ─────────────────────────────────────────────────────────────────
    function init() {
        if (!document.querySelector('.lac-page')) return;

        // Activa el layout desktop sin scroll de página (fallback: :has en CSS)
        document.body.classList.add('lac-body');

        initFlatpickrs();
        initStepper();
        initDestino();
        initForms();
        initNavMobile();

        // El gráfico del Resumen vive en static/grafico.js. Le prestamos los
        // ayudantes de acá para que formatee igual que el resto del módulo (y
        // no tenga su propia versión de "120 ml" ni de "12 ago").
        if (window.LAC_GRAFICO) {
            window.LAC_GRAFICO.init({ T: T, fmtMl: fmtMl, esc: esc,
                                      fmtFechaCorta: fmtFechaCorta });
        }

        // Botones fijos
        $('lac-cf-guardar').addEventListener('click', guardarCierre);
        $('lac-ed-guardar').addEventListener('click', guardarEditor);
        $('lac-confirm-si').addEventListener('click', confirmarSi);
        // Checkbox obligatorio del modal: habilita/inhabilita el botón confirmar
        $('lac-confirm-check').addEventListener('change', function () {
            $('lac-confirm-si').disabled = !this.checked;
        });
        // "Tomó todo": completa el consumo con lo que tenía la bolsita
        $('lac-confirm-input-todo').addEventListener('click', function () {
            var inEl = $('lac-confirm-input');
            inEl.value = inEl.max || '';
        });
        $('lac-btn-freezar').addEventListener('click', freezarSeleccionadas);
        // Los checkbox de la heladera nacen y mueren con cada repintado, así que
        // el oyente va en el contenedor, que sí es siempre el mismo.
        $('lac-lista-heladera').addEventListener('change', function (e) {
            if (e.target.classList.contains('lac-check-input')) pintarBotonFreezar();
        });
        $('lac-rec-guardar').addEventListener('click', guardarRecordatorio);
        var recDias = $('lac-rec-dias');
        if (recDias) recDias.addEventListener('click', function (e) {
            var btn = e.target.closest('.lac-rec-dia');
            if (btn) btn.classList.toggle('is-activo');
        });
        $('lac-bebe-guardar').addEventListener('click', guardarBebe);
        $('lac-config-guardar').addEventListener('click', guardarConfig);
        var capTog = $('cfg-bolsa_capacidad_activa');
        if (capTog) capTog.addEventListener('change', pintarCapacidad);

        // Hoja "Más opciones" → acciones sobre masPartidaId
        $('lac-mas-usada').addEventListener('click', function () {
            $('lac-modal-mas').hidden = true;
            abrirCerrarFecha(masPartidaId, 'usada');
        });
        $('lac-mas-descartada').addEventListener('click', function () {
            $('lac-modal-mas').hidden = true;
            abrirCerrarFecha(masPartidaId, 'descartada');
        });
        $('lac-mas-editar').addEventListener('click', function () {
            $('lac-modal-mas').hidden = true;
            abrirEditor(masPartidaId);
        });
        $('lac-mas-eliminar').addEventListener('click', function () {
            $('lac-modal-mas').hidden = true;
            abrirConfirmEliminar(masPartidaId);
        });

        // Delegación global: acciones repetidas en listas e historial
        document.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-lac-usar]');
            if (btn) { pedirCierre(parseInt(btn.getAttribute('data-lac-usar'), 10), 'usada'); return; }
            btn = e.target.closest('[data-lac-tirar]');
            if (btn) { pedirCierre(parseInt(btn.getAttribute('data-lac-tirar'), 10), 'descartada'); return; }
            btn = e.target.closest('[data-lac-bajar]');
            if (btn) { pedirBajar(parseInt(btn.getAttribute('data-lac-bajar'), 10)); return; }
            btn = e.target.closest('[data-lac-mas]');
            if (btn) { abrirMas(parseInt(btn.getAttribute('data-lac-mas'), 10)); return; }
            btn = e.target.closest('[data-lac-reabrir]');
            if (btn) { pedirReabrir(parseInt(btn.getAttribute('data-lac-reabrir'), 10)); return; }
            btn = e.target.closest('[data-lac-eliminar]');
            if (btn) { abrirConfirmEliminar(parseInt(btn.getAttribute('data-lac-eliminar'), 10)); return; }
            btn = e.target.closest('[data-lac-cerrar-modal]');
            if (btn) {
                var ov = btn.closest('.lac-overlay');
                if (ov) cerrarOverlay(ov);
            }
        });

        // Cierre por click en el backdrop
        OVERLAYS.forEach(function (id) {
            var ov = $(id);
            ov.addEventListener('mousedown', function (e) {
                if (e.target === ov) cerrarOverlay(ov);
            });
        });

        // Escape cierra el modal visible (nunca hay más de uno a la vez)
        document.addEventListener('keydown', function (e) {
            if (e.key !== 'Escape') return;
            for (var i = 0; i < OVERLAYS.length; i++) {
                var ov = $(OVERLAYS[i]);
                if (!ov.hidden) { cerrarOverlay(ov); return; }
            }
        });

        renderTodo();

        console.log('✓ lactancia.js cargado —', DATOS.freezer.length, 'en freezer,',
            DATOS.heladera.length, 'en heladera');
    }

    document.addEventListener('DOMContentLoaded', init);
})();
