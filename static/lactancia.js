/*
================================================================================
ARCHIVO: static/lactancia.js
================================================================================
Lógica cliente del módulo Lactancia (banco de leche). Se carga SOLO en
/lactancia (templates/lactancia.html, bloque scripts). Vanilla JS, sin
librerías. Todo vive dentro de una IIFE para no pisar los globales de app.js.

FUENTE DE VERDAD:
  window.LAC_DATOS = { freezer, heladera, historial, tablero, params, badge }

Cada mutación (crear / cerrar / trasladar / reabrir / editar / eliminar) se
envía por fetch con X-Requested-With y el backend responde el payload COMPLETO
fresco: acá se reemplaza DATOS y se re-renderiza todo (aviso + tablero +
listas + historial + badge de la nav).

Vencimiento, estado, dias_restantes y horas_restantes vienen CALCULADOS del
servidor: acá no se recalculan, solo se formatean. Las listas ya llegan en
orden FIFO (vencimiento ascendente) del servidor.

Camino estándar de la leche: el form de alta carga SIEMPRE a heladera; el
botón ⬆ del panel Heladera combina las partidas tildadas (checkbox por fila,
tildado por defecto) en UNA partida de freezer (POST /api/lactancia/freezar).

Cierres one-click: marcan con fecha de hoy y muestran un toast con botón
"Deshacer" (8 s) que llama a /reabrir (en una freezada, deshace la
combinación completa). Para cerrar con otra fecha está la hoja "Más
opciones" (⋯) de cada partida.
================================================================================
*/

(function () {
    'use strict';

    // ── Estado del módulo ────────────────────────────────────────────────────
    var DATOS = window.LAC_DATOS ||
        { freezer: [], heladera: [], historial: [], tablero: {}, params: {}, badge: 0,
          recordatorio: { activo: false, hora: '21:00', pendiente: false },
          bebe: { nombre: 'León', fecha_nacimiento: '', edad_texto: '', mes_de_vida: null } };

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

    // Nombre del bebé (configurable): reemplaza el "León" que antes estaba fijo
    // en el código, para que la app sirva para cualquier bebé.
    function nombreBebe() {
        return (DATOS.bebe && DATOS.bebe.nombre) || 'el bebé';
    }

    function $(id) { return document.getElementById(id); }

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

    function horaAhora() {
        var d = new Date();
        return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
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
        return ((Number(ml) || 0) / 1000).toFixed(2).replace('.', ',') + ' L';
    }

    // Freezer: texto relativo desde dias_restantes (del server)
    function textoVencFreezer(dias) {
        if (dias === null || dias === undefined) return '';
        if (dias === 0) return 'Vence hoy';
        if (dias === 1) return 'Vence mañana';
        if (dias > 1) return 'Vence en ' + dias + ' días';
        if (dias === -1) return 'Venció ayer';
        return 'Venció hace ' + Math.abs(dias) + ' días';
    }

    // Heladera: texto relativo desde horas_restantes (del server). Nunca se
    // muestra una hora absoluta (regla del módulo), solo cuánto falta.
    function textoVencHeladera(horas) {
        if (horas === null || horas === undefined) return '';
        if (horas < 0) {
            var h = Math.abs(horas);
            if (h < 24) return 'Venció hace ' + h + ' h';
            return 'Venció hace ' + Math.floor(h / 24) + (h < 48 ? ' día' : ' días');
        }
        if (horas === 0) return 'Vence dentro de 1 h';
        if (horas === 1) return 'Vence en 1 h';
        return 'Vence en ' + horas + ' h';
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
        var label = ESTADO_LABEL[estado] || estado;
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
    function postAccion(url, params, onOk, onFin) {
        fetch(url, {
            method: 'POST',
            body: params,   // URLSearchParams → content-type urlencoded automático
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
                    { nombre: 'León', fecha_nacimiento: '', edad_texto: '', mes_de_vida: null }
            };
            renderTodo();
            if (onOk) onOk(data);
        })
        .catch(function (err) {
            console.error('Error AJAX lactancia:', err);
            toast('⚠ ' + err.message, 'error');
        })
        .finally(function () {
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
        if (vencidas) partes.push(vencidas === 1 ? '1 partida vencida' : vencidas + ' partidas vencidas');
        if (pronto) partes.push(pronto === 1 ? '1 por vencer' : pronto + ' por vencer');
        el.className = 'lac-aviso ' + (vencidas ? 'is-peligro' : 'is-alerta');
        el.innerHTML = '⚠ ' + partes.join(' y ') + '. Revisá el stock.';
        el.hidden = false;
    }

    // ── Render: tablero ──────────────────────────────────────────────────────
    function stat(num, label, clase) {
        return '<div class="lac-stat' + (clase ? ' ' + clase : '') + '">' +
            '<span class="lac-stat-num">' + num + '</span>' +
            '<span class="lac-stat-label">' + label + '</span>' +
        '</div>';
    }

    // Tarjeta de KPI de ciclo de vida (emoji + número grande + etiqueta, con un
    // sub-texto opcional). `clase` permite resaltar (ej. "litros de amor").
    function kpiCard(emoji, num, label, sub, clase) {
        return '<div class="lac-kpi' + (clase ? ' ' + clase : '') + '">' +
            '<span class="lac-kpi-emoji">' + emoji + '</span>' +
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
                '<span class="lac-vacia-t">Todavía no hay partidas cargadas</span>' +
                '<span>Freezá la primera desde el panel Cargar 💪</span>' +
            '</div>';
            return;
        }

        var html = '<div class="lac-stats">' +
            stat(t.freezer_bolsas || 0, 'Bolsas disponibles') +
            stat(fmtMl(t.freezer_ml), 'Stock freezer (' + fmtLitros(t.freezer_ml) + ')') +
            stat(t.freezer_vence_pronto || 0, 'Vencen pronto', t.freezer_vence_pronto ? 'is-alerta' : '') +
            stat(t.freezer_vencidas || 0, 'Vencidas', t.freezer_vencidas ? 'is-peligro' : '') +
            stat(t.freezer_proximo_venc ? fmtFechaCorta(t.freezer_proximo_venc) : '—', 'Próxima a vencer') +
            stat(t.usadas_total || 0, 'Usadas') +
            stat(t.descartadas_total || 0, 'Descartadas') +
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
            hel = '🥛 En heladera: <strong>' + t.heladera_bolsas +
                (t.heladera_bolsas === 1 ? ' partida' : ' partidas') +
                ' · ' + fmtMl(t.heladera_ml) + '</strong>' +
                (proxima !== null ? ' <span class="lac-sep">·</span> la próxima ' +
                    textoVencHeladera(proxima).toLowerCase() : '');
        } else {
            hel = '🥛 Heladera vacía';
        }
        html += '<div class="lac-stats-heladera">' + hel + '</div>';

        // KPIs de ciclo de vida: producción ("litros de amor", resaltado),
        // consumo de León, leche descongelada, desperdicio, y los dos de
        // promedio móvil (días de stock y bolsita sugerida) que se ajustan solos
        // con el consumo real. Los que aún no tienen datos muestran "—".
        var dias = (t.dias_stock !== null && t.dias_stock !== undefined)
            ? t.dias_stock + (t.dias_stock === 1 ? ' día' : ' días') : '—';
        var bolsa = (t.bolsa_sugerida_ml !== null && t.bolsa_sugerida_ml !== undefined)
            ? fmtMl(t.bolsa_sugerida_ml) : '—';
        html += '<div class="lac-kpis-titulo">Ciclo de la leche</div>' +
            '<div class="lac-kpis">' +
            kpiCard('💧', fmtLitros(t.producido_ml), 'Producción total',
                    'todo lo que produjiste', 'lac-kpi--amor') +
            kpiCard('🍼', fmtMl(t.consumida_ml || 0), 'Consumida por ' + nombreBebe()) +
            kpiCard('🧊→🥛', fmtMl(t.descongelada_ml || 0), 'Descongelada') +
            kpiCard('🚱', fmtMl(t.desperdicio_ml || 0), 'Desperdicio', null,
                    (t.desperdicio_ml ? 'is-alerta' : '')) +
            kpiCard('📅', dias, 'Alcanza para',
                    (t.dias_stock == null ? 'cuando ' + nombreBebe() + ' tome de las bolsitas' : 'al ritmo actual')) +
            kpiCard('📏', bolsa, 'Bolsita sugerida',
                    (t.bolsa_sugerida_ml == null ? 'según el consumo de ' + nombreBebe() : 'promedio real')) +
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
        return 'Extraída ' + fmtFechaCorta(p.fecha_extraccion) +
            (p.hora_extraccion ? ' · ' + p.hora_extraccion + ' h' : '');
    }

    function itemFreezer(p) {
        var venc = '<span class="lac-venc t-' + p.estado + '">' + textoVencFreezer(p.dias_restantes) + '</span>' +
                   ' <span class="lac-venc-fecha">(' + fmtFechaCorta(p.vencimiento) + ')</span>';
        return '<div class="lac-item is-' + p.estado + '">' +
            '<div class="lac-item-body">' +
                '<div class="lac-item-top"><span class="lac-item-vol">' + fmtMl(p.volumen_ml) + '</span>' + pill(p.estado) + '</div>' +
                '<div class="lac-item-meta">' + extraidaTxt(p) +
                    ' <span class="lac-sep">·</span> ' + venc +
                '</div>' + notasHtml(p) +
            '</div>' +
            '<div class="lac-item-actions">' +
                '<button type="button" class="lac-btn-bajar" data-lac-bajar="' + p.id + '" title="Bajar a la heladera para descongelar">⬇ Bajar</button>' +
                '<button type="button" class="lac-btn-usar" data-lac-usar="' + p.id + '" title="Se le dio a ' + nombreBebe() + ' (fecha de hoy)">✓ Usada</button>' +
                '<button type="button" class="lac-btn-icono" data-lac-tirar="' + p.id + '" title="Descartar (fecha de hoy)">🗑</button>' +
                '<button type="button" class="lac-btn-icono" data-lac-mas="' + p.id + '" title="Más opciones">⋯</button>' +
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
                (venc ? 'Vencida: se puede freezar igual, pero vas a tener que confirmar que se pasó al freezer antes de vencerse'
                      : 'Tildala para mandarla al freezer con ⬆') + '">' +
            '<input type="checkbox" class="lac-check-input" value="' + p.id + '"' +
                (venc ? ' data-venc="1"' : '') + '>' +
        '</label>';
    }

    // Etiqueta que diferencia leche recién extraída ("Fresca") de la bajada del
    // freezer para descongelar ("Descongelada"). Pedido de Mari: en la heladera
    // van a convivir los dos tipos (ej. cuando León arranque el jardín).
    function tipoTag(p) {
        if (p.tipo === 'descongelada') {
            return '<span class="lac-tipo lac-tipo--desc" title="Bajada del freezer para descongelar">❄→🥛 Descongelada</span>';
        }
        return '<span class="lac-tipo lac-tipo--fresca" title="Extraída y puesta directo en la heladera">🥛 Fresca</span>';
    }

    function itemHeladera(p) {
        var esDesc = p.tipo === 'descongelada';
        return '<div class="lac-item is-' + p.estado + (esDesc ? ' lac-item--desc' : ' lac-item--fresca') + '">' +
            '<div class="lac-item-body">' +
                '<div class="lac-item-top"><span class="lac-item-vol">' + fmtMl(p.volumen_ml) + '</span>' +
                    tipoTag(p) + pill(p.estado) + '</div>' +
                '<div class="lac-item-meta">' + extraidaTxt(p) +
                    ' <span class="lac-sep">·</span> <span class="lac-venc t-' + p.estado + '">' +
                    textoVencHeladera(p.horas_restantes) + '</span>' +
                '</div>' + notasHtml(p) +
            '</div>' +
            '<div class="lac-item-actions">' +
                '<button type="button" class="lac-btn-usar" data-lac-usar="' + p.id + '" title="Se le dio a ' + nombreBebe() + ' (fecha de hoy)">✓ Usada</button>' +
                '<button type="button" class="lac-btn-icono" data-lac-tirar="' + p.id + '" title="Descartar (fecha de hoy)">🗑</button>' +
                '<button type="button" class="lac-btn-icono" data-lac-mas="' + p.id + '" title="Más opciones">⋯</button>' +
                checkHeladera(p) +
            '</div>' +
        '</div>';
    }

    var CIERRE_VERBO = { usada: 'Usada el', descartada: 'Descartada el', trasladada: 'Freezada el' };

    function itemHistorial(p) {
        var ubi = p.ubicacion === 'freezer' ? '🧊' : '🥛';
        var verbo = CIERRE_VERBO[p.motivo_cierre] || 'Cerrada el';
        return '<div class="lac-item lac-item--hist">' +
            '<div class="lac-item-body">' +
                '<div class="lac-item-top"><span class="lac-item-vol">' + fmtMl(p.volumen_ml) + '</span>' +
                    pill(p.estado) + ' <span class="lac-hist-ubi" title="' + (p.ubicacion === 'freezer' ? 'Freezer' : 'Heladera') + '">' + ubi + '</span></div>' +
                '<div class="lac-item-meta">' + extraidaTxt(p) +
                    ' <span class="lac-sep">·</span> ' + verbo + ' ' + fmtFechaCorta(p.fecha_cierre) +
                '</div>' + notasHtml(p) +
            '</div>' +
            '<div class="lac-item-actions">' +
                '<button type="button" class="lac-btn-icono" data-lac-reabrir="' + p.id + '" title="Reabrir (deshacer el cierre)">↩</button>' +
                '<button type="button" class="lac-btn-icono" data-lac-eliminar="' + p.id + '" title="Eliminar definitivamente">✕</button>' +
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
            'Sin partidas en el freezer.');
        renderLista('lac-lista-heladera', 'lac-heladera-count', DATOS.heladera, itemHeladera,
            'Nada en la heladera. Lo que sobre al final del día, se freeza.');
        renderLista('lac-lista-historial', 'lac-historial-count', DATOS.historial, itemHistorial,
            'Todavía no se cerró ninguna partida.');
    }

    function renderTodo() {
        renderAviso();
        renderBebe();
        renderRecordatorio();
        renderTablero();
        renderListas();
        // Estándar de notificaciones: refrescar la campana del header tras
        // mutar datos (DATOS.badge sigue en el payload por compat, ya no se usa).
        if (window.Notif) window.Notif.refrescar();
        // Hint del form de alta con el parámetro vigente
        var hint = $('lac-ex-hint');
        if (hint && DATOS.params.heladera_horas) {
            hint.textContent = 'Va a la heladera y vence a las ' + DATOS.params.heladera_horas +
                ' h de la extracción. Lo que juntes lo freezás con el botón ⬆️ de Heladera.';
        }
    }

    // ── Overlays ─────────────────────────────────────────────────────────────
    var OVERLAYS = ['lac-modal-cerrar', 'lac-modal-mas',
                    'lac-modal-editor', 'lac-modal-confirm'];

    function cerrarOverlay(ov) { ov.hidden = true; }

    function subPartida(p) {
        return '· ' + fmtMl(p.volumen_ml) + ' · ' +
            (p.ubicacion === 'freezer' ? 'freezer' : 'heladera');
    }

    // ── Cierres one-click (fecha = hoy) con Deshacer ─────────────────────────
    function deshacerCierre(id, textoOk) {
        postAccion('/api/lactancia/' + id + '/reabrir', new URLSearchParams(), function () {
            toast(textoOk || '↩ Deshecho: la partida volvió al stock.', 'info');
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
            var vol = p ? fmtMl(p.volumen_ml) : 'Partida';
            var texto = (motivo === 'usada')
                ? '✓ ' + vol + ' marcada como usada.'
                : '🗑 ' + vol + ' descartada.';
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
            ? '✓ Marcar usada ' : '🗑 Marcar descartada ';
        $('lac-cf-sub').textContent = subPartida(p);
        $('lac-cf-fecha-label').textContent = (motivo === 'usada')
            ? '¿Cuándo se usó?' : '¿Cuándo se descartó?';
        fpCfFecha.setDate(isoDate(hoy()), true);
        $('lac-cf-notas').value = '';
        $('lac-modal-cerrar').hidden = false;
    }

    function guardarCierre() {
        if (cfPartidaId === null) return;
        var fecha = $('lac-cf-fecha').value;
        if (!fecha) {
            toast('⚠ Elegí la fecha de cierre.', 'error');
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
            toast(cfMotivo === 'usada' ? '✓ Partida marcada como usada.' : '🗑 Partida descartada.',
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
            toast('⚠ Tildá al menos una partida de heladera.', 'error');
            return;
        }
        // Si hay vencidas entre las tildadas, hay que declarar que se pasaron
        // al freezer antes de vencerse (checkbox obligatorio del modal).
        var vencidas = [].filter.call(checks, function (c) { return c.dataset.venc === '1'; }).length;
        if (vencidas) {
            abrirConfirm({
                emoji: '❄️', titulo: 'Freezar partidas vencidas', peligro: false, boton: 'Freezar',
                msg: vencidas === 1
                    ? 'Una de las partidas tildadas figura vencida en la app.'
                    : vencidas + ' de las partidas tildadas figuran vencidas en la app.',
                check: 'Confirmo que se pasó al freezer ANTES de vencerse (se cargó tarde en la app).',
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
            emoji: '❄️', titulo: 'Freezar al freezer', peligro: false, boton: 'Sí, freezar',
            msg: 'Se combinan ' + ids.length +
                (ids.length === 1 ? ' partida' : ' partidas') +
                (vol ? ' (' + fmtMl(vol) + ')' : '') +
                ' en UNA sola partida de freezer, con la fecha de extracción más vieja.',
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
            toast('❄️ ' + ids.length + (ids.length === 1 ? ' partida freezada' : ' partidas freezadas') +
                (vol ? ': ' + fmtMl(vol) + ' al freezer.' : '.'),
                'ok', function () { deshacerCierre(primero, '↩ Deshecho: volvieron a la heladera.'); });
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
            emoji: '⬇️', titulo: 'Bajar a descongelar', peligro: false, boton: 'Sí, bajar',
            msg: 'Bajás ' + fmtMl(p.volumen_ml) + ' del freezer a la heladera para ' +
                'descongelar. Va a estar lista por ' + horas + ' h y no se puede volver a congelar.',
            check: 'Confirmo que bajé (o bajo ahora) esta bolsita a la heladera.',
            accion: function () { bajarPost(id); }
        });
    }

    function bajarPost(id) {
        var p = buscarPartida(id);
        var vol = p ? fmtMl(p.volumen_ml) : 'La bolsita';
        postAccion('/api/lactancia/' + id + '/bajar', new URLSearchParams(), function () {
            toast('⬇️ ' + vol + ' a la heladera para descongelar.',
                'ok', function () { deshacerCierre(id, '↩ Deshecho: volvió al freezer.'); });
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
            toast('⚠ La fecha de extracción es obligatoria.', 'error');
            return;
        }
        params.append('fecha_extraccion', $('lac-ed-fecha').value);
        params.append('hora_extraccion', $('lac-ed-hora').value);
        var btn = $('lac-ed-guardar');
        btn.disabled = true;
        postAccion('/api/lactancia/' + edPartidaId + '/editar', params, function () {
            $('lac-modal-editor').hidden = true;
            toast('✎ Partida actualizada.');
        }, function () { btn.disabled = false; });
    }

    // ── Modal: Confirmación genérica ─────────────────────────────────────────
    // Cualquier acción que se concrete al toque (Usada, Tirar, Eliminar) pide
    // confirmación antes — así un toque sin querer no la ejecuta (pedido de
    // Mari 2026-07-13). `confirmAccion` es la función que corre al confirmar.
    var confirmAccion = null;

    // Preferencia por DISPOSITIVO (localStorage, no se sincroniza entre
    // teléfonos): si está en '0', las confirmaciones se saltan. Por defecto
    // activadas. Envuelto en try/catch por si localStorage no está disponible.
    function confirmacionesActivadas() {
        try { return localStorage.getItem('lac-confirmar') !== '0'; }
        catch (e) { return true; }
    }
    function setConfirmaciones(on) {
        try { localStorage.setItem('lac-confirmar', on ? '1' : '0'); } catch (e) {}
    }

    // opts.check (opcional): texto de un checkbox OBLIGATORIO — el botón de
    // confirmar queda deshabilitado hasta tildarlo (ej. freezar una vencida:
    // hay que declarar que se pasó al freezer antes de vencerse).
    function abrirConfirm(opts) {
        // Preferencia "sin confirmación" (por dispositivo): ejecuta la acción
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

        // Input numérico OPCIONAL (ej. ml que tomó León). Dejarlo vacío es
        // válido — no toca el estado del botón. opts.input = {label, max}.
        var inWrap = $('lac-confirm-input-wrap');
        var inEl = $('lac-confirm-input');
        inEl.value = '';
        if (opts.input) {
            $('lac-confirm-input-label').textContent = opts.input.label || '';
            if (opts.input.max != null) inEl.max = opts.input.max; else inEl.removeAttribute('max');
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
        var det = fmtMl(p.volumen_ml) + ' (extraída el ' + fmtFecha(p.fecha_extraccion) + ')';
        if (motivo === 'usada') {
            abrirConfirm({
                emoji: '✓', titulo: 'Marcar como usada', peligro: false, boton: 'Sí, usada',
                msg: 'Se le dio a ' + nombreBebe() + ': ' + det + '. Se cierra con fecha de hoy.',
                input: { label: '¿Cuántos ml tomó ' + nombreBebe() + '? (opcional — ej. dato de la maestra)',
                         max: p.volumen_ml },
                accion: function () {
                    cerrarDirecto(id, 'usada', $('lac-confirm-input').value.trim());
                }
            });
        } else {
            abrirConfirm({
                emoji: '🗑', titulo: 'Descartar partida', peligro: true, boton: 'Sí, descartar',
                msg: 'Se descarta ' + det + '. Se cierra con fecha de hoy.',
                accion: function () { cerrarDirecto(id, 'descartada'); }
            });
        }
    }

    function abrirConfirmEliminar(id) {
        var p = buscarPartida(id);
        if (!p) return;
        abrirConfirm({
            emoji: '⚠️', titulo: 'Eliminar partida', peligro: true, boton: 'Sí, eliminar',
            msg: 'Se elimina definitivamente la partida de ' + fmtMl(p.volumen_ml) +
                ' (extraída el ' + fmtFecha(p.fecha_extraccion) + '). Esta acción no se puede deshacer.',
            accion: function () {
                postAccion('/api/lactancia/' + id + '/eliminar', new URLSearchParams(), function () {
                    toast('✕ Partida eliminada.', 'info');
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
            emoji: '↩', titulo: 'Reabrir partida', peligro: false, boton: 'Sí, reabrir',
            msg: 'Vuelve al stock ' + fmtMl(p.volumen_ml) +
                ' (extraída el ' + fmtFecha(p.fecha_extraccion) + ')' +
                (esFreezada ? '. Al ser una freezada, se deshace la combinación COMPLETA.' : '.'),
            accion: function () { reabrir(id); }
        });
    }

    function reabrir(id) {
        postAccion('/api/lactancia/' + id + '/reabrir', new URLSearchParams(), function () {
            toast('↩ Partida reabierta: volvió al stock.', 'info');
        });
    }

    // ── Form de alta (único: toda extracción entra por heladera) ────────────
    function resetFormAlta() {
        $('lac-form-extraccion').reset();
        fpExFecha.setDate(isoDate(hoy()), true);   // reset no repone el altInput
        fpExHora.setDate(horaAhora(), true);
    }

    function initForms() {
        resetFormAlta();

        $('lac-form-extraccion').addEventListener('submit', function (e) {
            e.preventDefault();
            var vol = $('lac-ex-volumen').value.trim();
            if (!vol) {
                toast('⚠ Cargá el volumen en ml.', 'error');
                $('lac-ex-volumen').focus();
                return;
            }
            var params = new URLSearchParams();
            params.append('ubicacion', 'heladera');
            params.append('volumen_ml', vol);
            params.append('fecha_extraccion', $('lac-ex-fecha').value || '');
            params.append('hora_extraccion', $('lac-ex-hora').value || '');
            params.append('notas', $('lac-ex-notas').value.trim());

            var btn = $('lac-ex-guardar');
            btn.disabled = true;
            postAccion('/api/lactancia/crear', params, function () {
                toast('🥛 ' + fmtMl(vol) + ' a la heladera.');
                resetFormAlta();
                $('lac-ex-volumen').focus();
            }, function () { btn.disabled = false; });
        });
    }

    function initFlatpickrs() {
        fpExFecha = flatpickr($('lac-ex-fecha'), {
            locale: 'es', dateFormat: 'Y-m-d', altInput: true, altFormat: 'd/m/Y',
            allowInput: true, maxDate: 'today'
        });
        fpCfFecha = flatpickr($('lac-cf-fecha'), {
            locale: 'es', dateFormat: 'Y-m-d', altInput: true, altFormat: 'd/m/Y',
            allowInput: true, maxDate: 'today'
        });
        fpEdFecha = flatpickr($('lac-ed-fecha'), {
            locale: 'es', dateFormat: 'Y-m-d', altInput: true, altFormat: 'd/m/Y',
            allowInput: true, maxDate: 'today'
        });
        // Hora en 24h. disableMobile es CLAVE: sin él, flatpickr en celulares
        // se reemplaza solo por el <input type="time"> NATIVO ("modo mobile"),
        // que en iOS es 12h AM/PM y desborda la tarjeta "+Cargar" — justo lo
        // que este picker vino a evitar.
        fpExHora = flatpickr($('lac-ex-hora'), {
            enableTime: true, noCalendar: true, dateFormat: 'H:i',
            time_24hr: true, allowInput: true, disableMobile: true
        });
        fpEdHora = flatpickr($('lac-ed-hora'), {
            enableTime: true, noCalendar: true, dateFormat: 'H:i',
            time_24hr: true, allowInput: true, disableMobile: true
        });
        fpRecHora = flatpickr($('lac-rec-hora'), {
            enableTime: true, noCalendar: true, dateFormat: 'H:i',
            time_24hr: true, allowInput: true, disableMobile: true
        });
        fpBebeNac = flatpickr($('lac-bebe-nac'), {
            locale: 'es', dateFormat: 'Y-m-d', altInput: true, altFormat: 'd/m/Y',
            allowInput: true, maxDate: 'today'
        });
    }

    // ── Recordatorio nocturno de bajar bolsitas ──────────────────────────────
    // Refleja la config guardada (toggle + hora) y muestra el banner cuando el
    // recordatorio está VIGENTE (el server decide `pendiente`: activo + pasó la
    // hora + hay leche en freezer + no se bajó ninguna hoy). Es solo un aviso.
    function renderRecordatorio() {
        var rec = DATOS.recordatorio || { activo: false, hora: '21:00', pendiente: false };
        var chk = $('lac-rec-activo');
        if (chk) chk.checked = !!rec.activo;
        if (fpRecHora) fpRecHora.setDate(rec.hora || '21:00', true);
        else { var h = $('lac-rec-hora'); if (h) h.value = rec.hora || '21:00'; }

        var banner = $('lac-rec-banner');
        if (banner) {
            if (rec.pendiente) {
                banner.innerHTML = '🌙 Acordate de <strong>bajar bolsitas del freezer ' +
                    'a la heladera</strong> para mañana.';
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
        var btn = $('lac-rec-guardar');
        btn.disabled = true;
        postAccion('/api/lactancia/recordatorio', params, function () {
            toast('🌙 Recordatorio guardado.');
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
            toast('👶 Datos del bebé guardados.');
        }, function () { btn.disabled = false; });
    }

    // ── Selector de sección (SOLO mobile) ────────────────────────────────────
    // Cambia data-lac-sec en .lac-wrap (el CSS muestra solo esa sección) y, si
    // la sección elegida es un <details> (bebé/recordatorio/historial), la abre.
    // En escritorio el selector está oculto y no afecta nada.
    function initNavMobile() {
        var sel = $('lac-nav-sel');
        var wrap = document.querySelector('.lac-wrap');
        if (!sel || !wrap) return;
        function activar(sec) {
            wrap.setAttribute('data-lac-sec', sec);
            var el = document.querySelector('.lac-sec--' + sec);
            if (el && el.tagName === 'DETAILS') el.open = true;
            if (sel.value !== sec) sel.value = sec;
        }
        sel.addEventListener('change', function () { activar(sel.value); });
        activar(sel.value || 'cargar');
    }

    // ── Init ─────────────────────────────────────────────────────────────────
    function init() {
        if (!document.querySelector('.lac-page')) return;

        // Activa el layout desktop sin scroll de página (fallback: :has en CSS)
        document.body.classList.add('lac-body');

        initFlatpickrs();
        initForms();
        initNavMobile();

        // Botones fijos
        $('lac-cf-guardar').addEventListener('click', guardarCierre);
        $('lac-ed-guardar').addEventListener('click', guardarEditor);
        $('lac-confirm-si').addEventListener('click', confirmarSi);
        // Checkbox obligatorio del modal: habilita/inhabilita el botón confirmar
        $('lac-confirm-check').addEventListener('change', function () {
            $('lac-confirm-si').disabled = !this.checked;
        });
        $('lac-btn-freezar').addEventListener('click', freezarSeleccionadas);
        $('lac-rec-guardar').addEventListener('click', guardarRecordatorio);
        $('lac-bebe-guardar').addEventListener('click', guardarBebe);

        // Toggle "pedir confirmación" (preferencia por dispositivo)
        var ctog = $('lac-confirmar-toggle');
        if (ctog) {
            ctog.checked = confirmacionesActivadas();
            ctog.addEventListener('change', function () {
                setConfirmaciones(this.checked);
                toast(this.checked
                    ? '🔒 Te voy a pedir confirmación en cada acción.'
                    : '⚡ Acciones sin confirmación (en este dispositivo).', 'info');
            });
        }

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
