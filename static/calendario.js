/*
================================================================================
ARCHIVO: static/calendario.js
================================================================================
Lógica cliente del módulo Calendario (tareas del hogar). Se carga SOLO en
/calendario (templates/calendario.html, bloque scripts). Vanilla JS, sin
librerías. Todo vive dentro de una IIFE para no pisar los globales de app.js
(app.js ya define fmtFecha/mostrarToast con otras firmas).

FUENTE DE VERDAD:
  window.CAL_DATOS  = { actividades: [...], historial: [...] }  (del template)
  window.CAL_AREAS  = { clave: [Nombre, emoji] }
  window.CAL_RESPONSABLES = { clave: Nombre }

Cada mutación (crear / editar / completar / reactivar / eliminar) se envía por
fetch con X-Requested-With y el backend responde el payload COMPLETO fresco:
acá se reemplaza DATOS y se re-renderiza todo (agenda + calendario + detalle
+ modal Todas si está abierto).

El estado (`vencida|proxima|aldia|terminada`), `proxima_fecha` y
`dias_restantes` vienen CALCULADOS del servidor: acá no se recalculan. La única
lógica espejada es sumarIntervalo() —con clamp de fin de mes, igual que
_act_sumar_intervalo() de app.py— para el preview en vivo del modal Completar.
================================================================================
*/

(function () {
    'use strict';

    // ── Estado del módulo ────────────────────────────────────────────────────
    var DATOS = window.CAL_DATOS || { actividades: [], historial: [] };
    var AREAS = window.CAL_AREAS || {};
    var RESPONSABLES = window.CAL_RESPONSABLES || {};
    var UNIDADES = ['dias', 'semanas', 'meses', 'anios'];

    var mesCursor = null;       // Date, día 1 del mes visible
    var diaSel = null;          // 'YYYY-MM-DD' seleccionado en la grilla
    var compActId = null;       // id en el modal Completar
    var compModo = 'repetir';   // 'repetir' | 'terminar'
    var edActId = null;         // id en el Editor (null = alta nueva)
    var edRecurrente = true;    // tipo elegido en el Editor
    var actEliminarId = null;   // id pendiente de confirmación de borrado
    var volverATodas = false;   // al cerrar Completar/Editor, reabrir "Todas"

    // Instancias flatpickr de los 3 date inputs del módulo (mismo patrón que
    // inicializarFechaHoy() en app.js: valor real ISO Y-m-d, altInput muestra
    // d/m/Y). Se llenan en initFlatpickrs().
    var fpQaUltima = null;
    var fpCompFecha = null;
    var fpEdUltima = null;
    var fpEdLimite = null;

    function $(id) { return document.getElementById(id); }

    // ── Fechas ───────────────────────────────────────────────────────────────
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

    function parseISO(s) {
        if (!s) return null;
        var p = String(s).split('-');
        if (p.length !== 3) return null;
        var d = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
        d.setHours(0, 0, 0, 0);
        return d;
    }

    function diasEnMes(anio, mes0) {
        return new Date(anio, mes0 + 1, 0).getDate();
    }

    // flatpickr de los 3 date inputs del módulo. Mismo patrón que
    // inicializarFechaHoy() (app.js): locale es, dateFormat Y-m-d (valor real
    // que viaja al backend/POST), altInput con altFormat d/m/Y (lo que ve el
    // usuario). El input original queda oculto pero mantiene el name/id y su
    // .value en ISO, así que el resto del código (lectura de .value, POST del
    // form de alta rápida) no cambia.
    function initFlatpickrs() {
        fpQaUltima = flatpickr($('cal-qa-ultima'), {
            locale: 'es',
            dateFormat: 'Y-m-d',
            altInput: true,
            altFormat: 'd/m/Y',
            allowInput: true
        });
        fpCompFecha = flatpickr($('cal-comp-fecha'), {
            locale: 'es',
            dateFormat: 'Y-m-d',
            altInput: true,
            altFormat: 'd/m/Y',
            allowInput: true,
            maxDate: 'today',
            onChange: actualizarPreviewCompletar
        });
        fpEdUltima = flatpickr($('cal-ed-ultima'), {
            locale: 'es',
            dateFormat: 'Y-m-d',
            altInput: true,
            altFormat: 'd/m/Y',
            allowInput: true
        });
        fpEdLimite = flatpickr($('cal-ed-limite'), {
            locale: 'es',
            dateFormat: 'Y-m-d',
            altInput: true,
            altFormat: 'd/m/Y',
            allowInput: true
        });
    }

    // Espejo de _act_sumar_intervalo (app.py): suma n unidades con clamp al
    // último día del mes destino (31-ene + 1 mes → 28/29-feb). unidad en ASCII:
    // dias | semanas | meses | anios.
    function sumarIntervalo(fecha, n, unidad) {
        n = parseInt(n, 10) || 0;
        var d = new Date(fecha.getTime());
        if (unidad === 'dias') { d.setDate(d.getDate() + n); return d; }
        if (unidad === 'semanas') { d.setDate(d.getDate() + n * 7); return d; }
        var meses = (unidad === 'anios') ? n * 12 : n;   // meses | anios
        var total = d.getMonth() + meses;
        var anio = d.getFullYear() + Math.floor(total / 12);
        var mes = ((total % 12) + 12) % 12;
        var dia = Math.min(d.getDate(), diasEnMes(anio, mes));
        return new Date(anio, mes, dia);
    }

    // ── Formato es-AR ────────────────────────────────────────────────────────
    var MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
                 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
    var MESES_LARGO = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                       'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
    var DOW = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'];

    // Acepta ISO string o Date. '12 mar 2026' | '—'
    function fmtFecha(f) {
        var d = (f instanceof Date) ? f : parseISO(f);
        if (!d) return '—';
        return d.getDate() + ' ' + MESES[d.getMonth()] + ' ' + d.getFullYear();
    }

    function fmtFechaCorta(f) {
        var d = (f instanceof Date) ? f : parseISO(f);
        if (!d) return '—';
        return d.getDate() + ' ' + MESES[d.getMonth()];
    }

    function fmtMesAnio(d) {
        var m = MESES_LARGO[d.getMonth()];
        return m.charAt(0).toUpperCase() + m.slice(1) + ' ' + d.getFullYear();
    }

    // Etiquetas de unidad (clave ASCII del backend → texto con tilde)
    var UNIDAD_LABEL = {
        dias:    ['día', 'días'],
        semanas: ['semana', 'semanas'],
        meses:   ['mes', 'meses'],
        anios:   ['año', 'años']
    };

    function fmtIntervalo(n, u) {
        n = Number(n) || 0;
        var par = UNIDAD_LABEL[u];
        var label = par ? (n === 1 ? par[0] : par[1]) : (u || '');
        return 'cada ' + n + ' ' + label;
    }

    // 'Vence hoy' / 'Vence mañana' / 'Vence en N días' / 'Atrasada N días'
    function textoRelativo(dias) {
        if (dias === null || dias === undefined) return 'Sin fecha';
        if (dias === 0) return 'Vence hoy';
        if (dias === 1) return 'Vence mañana';
        if (dias > 1) return 'Vence en ' + dias + ' días';
        if (dias === -1) return 'Atrasada 1 día';
        return 'Atrasada ' + Math.abs(dias) + ' días';
    }

    // ── Datos ────────────────────────────────────────────────────────────────
    function areaInfo(clave) {
        var par = AREAS[clave];
        if (par) return { label: par[0], icon: par[1] };
        return { label: clave, icon: '•' };
    }

    function respLabel(clave) { return RESPONSABLES[clave] || clave; }

    function buscarAct(id) {
        for (var i = 0; i < DATOS.actividades.length; i++) {
            if (DATOS.actividades[i].id === id) return DATOS.actividades[i];
        }
        return null;
    }

    // Escape para armar HTML con datos del usuario
    function esc(s) {
        return String(s === null || s === undefined ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    // ── AJAX ─────────────────────────────────────────────────────────────────
    // Toda mutación responde {ok:true, actividades, historial} (payload fresco)
    // o {ok:false, error}. onOk corre DESPUÉS de reemplazar DATOS y re-renderizar.
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
                actividades: data.actividades || [],
                historial: data.historial || []
            };
            renderTodo();
            if (onOk) onOk(data);
        })
        .catch(function (err) {
            console.error('Error AJAX calendario:', err);
            toast('⚠ ' + err.message, 'error');
        })
        .finally(function () {
            if (onFin) onFin();
        });
    }

    // ── Toasts (reusa la infra .toast de style.css con fondos cal-toast-*) ───
    function toast(texto, tipo) {
        var cont = $('cal-toast-container');
        if (!cont) return;
        var clase = 'cal-toast-ok';
        if (tipo === 'error') clase = 'cal-toast-error';
        else if (tipo === 'info') clase = 'cal-toast-info';
        var el = document.createElement('div');
        el.className = 'toast ' + clase;
        el.textContent = texto;
        cont.appendChild(el);
        setTimeout(function () { el.classList.add('toast-visible'); }, 10);
        setTimeout(function () {
            el.classList.remove('toast-visible');
            el.classList.add('toast-saliendo');
            setTimeout(function () {
                if (el.parentNode) el.parentNode.removeChild(el);
            }, 300);
        }, 3000);
    }

    // ── Render: agenda de pendientes ─────────────────────────────────────────
    function badgeResp(r) {
        if (!r) return '';
        return '<span class="cal-badge-resp cal-resp-' + esc(r) + '">' + esc(respLabel(r)) + '</span>';
    }

    function itemAgenda(a) {
        var ar = areaInfo(a.area);
        var campana = a.avisar
            ? ' <span class="cal-campana" title="Aviso ' + (Number(a.lead_dias) || 0) + ' días antes">🔔</span>'
            : '';
        var uso = a.uso_nota ? '<span class="cal-uso">' + esc(a.uso_nota) + '</span>' : '';
        return '<div class="cal-agenda-item is-' + a.estado + '">' +
            '<div class="cal-agenda-ico" title="' + esc(ar.label) + '">' + ar.icon + '</div>' +
            '<div class="cal-agenda-body">' +
                '<div class="cal-agenda-name">' + esc(a.nombre) + campana + '</div>' +
                '<div class="cal-agenda-meta">' +
                    '<span class="cal-estado-txt t-' + a.estado + '">' + textoRelativo(a.dias_restantes) + '</span>' +
                    '<span class="cal-sep">·</span>' +
                    '<span>' + fmtFecha(a.proxima_fecha) + '</span>' +
                    badgeResp(a.responsable) + uso +
                '</div>' +
            '</div>' +
            '<div class="cal-agenda-actions">' +
                '<button type="button" class="cal-btn-completar" data-cal-completar="' + a.id + '">✓ Completar</button>' +
                '<button type="button" class="cal-btn-icono" title="Editar" data-cal-editar="' + a.id + '">✎</button>' +
            '</div>' +
        '</div>';
    }

    function grupoAgenda(titulo, clase, items) {
        if (!items.length) return '';
        var html = '<div class="cal-agenda-group">' +
            '<div class="cal-agenda-group-title ' + clase + '">' +
                '<span class="cal-grp-dot"></span> ' + titulo +
                ' <span class="cal-grp-n">' + items.length + '</span>' +
            '</div>';
        for (var i = 0; i < items.length; i++) html += itemAgenda(items[i]);
        return html + '</div>';
    }

    function renderAgenda() {
        var vencidas = [], proximas = [];
        DATOS.actividades.forEach(function (a) {
            if (a.estado === 'vencida') vencidas.push(a);
            else if (a.estado === 'proxima') proximas.push(a);
        });
        function ord(a, b) {
            return String(a.proxima_fecha || '').localeCompare(String(b.proxima_fecha || ''));
        }
        vencidas.sort(ord);
        proximas.sort(ord);

        var total = vencidas.length + proximas.length;
        $('cal-pend-count').textContent = (total === 0)
            ? 'todo al día'
            : total + (total === 1 ? ' actividad' : ' actividades');

        var html;
        if (total === 0) {
            html = '<div class="cal-agenda-vacia">' +
                '<div class="cal-vacia-em">🌿</div>' +
                '<div class="cal-vacia-t">No hay nada pendiente</div>' +
                '<div>Cuando algo se acerque a su fecha, va a aparecer acá.</div>' +
            '</div>';
        } else {
            html = grupoAgenda('Vencidas', 'cal-grp-vencida', vencidas) +
                   grupoAgenda('Por vencer', 'cal-grp-proxima', proximas);
        }
        $('cal-agenda').innerHTML = html;
    }

    // ── Render: calendario mensual ───────────────────────────────────────────
    // Mapa 'YYYY-MM-DD' → [{id, est}]. est: vencida|proxima|aldia (próxima
    // fecha de actividad activa) o 'hecha' (fecha_hecha del historial).
    function mapaPorDia() {
        var m = {};
        function push(iso, id, est) {
            (m[iso] = m[iso] || []).push({ id: id, est: est });
        }
        DATOS.actividades.forEach(function (a) {
            if (a.terminada || !a.proxima_fecha) return;
            push(a.proxima_fecha, a.id, a.estado);
        });
        DATOS.historial.forEach(function (h) {
            if (h.fecha_hecha) push(h.fecha_hecha, h.actividad_id, 'hecha');
        });
        return m;
    }

    // Hasta 3 puntitos, prioridad vencida → proxima → hecha → programada
    function dotsDelDia(lista) {
        function tiene(e) {
            return lista.some(function (x) { return x.est === e; });
        }
        var dots = [];
        if (tiene('vencida')) dots.push('cal-d-vencida');
        if (tiene('proxima')) dots.push('cal-d-proxima');
        if (tiene('hecha')) dots.push('cal-d-hecha');
        if (tiene('aldia')) dots.push('cal-d-aldia');
        return dots.slice(0, 3);
    }

    function renderCalendario() {
        $('cal-mes-label').textContent = fmtMesAnio(mesCursor);

        var porDia = mapaPorDia();
        var hoyIso = isoDate(hoy());
        var anio = mesCursor.getFullYear();
        var mes = mesCursor.getMonth();

        var startDow = new Date(anio, mes, 1).getDay();     // 0 = domingo
        startDow = (startDow === 0) ? 6 : startDow - 1;     // lunes = 0
        // Solo las semanas que el mes necesita (5 o 6), sin fila gris de más
        var semanas = Math.ceil((startDow + diasEnMes(anio, mes)) / 7);

        var html = '';
        for (var i = 0; i < DOW.length; i++) {
            html += '<div class="cal-dow">' + DOW[i] + '</div>';
        }

        var d = new Date(anio, mes, 1 - startDow);
        for (var c = 0; c < semanas * 7; c++) {
            var iso = isoDate(d);
            var cls = 'cal-day';
            if (d.getMonth() !== mes) cls += ' is-otro-mes';
            if (iso === hoyIso) cls += ' is-hoy';
            if (iso === diaSel) cls += ' is-sel';
            html += '<div class="' + cls + '" data-fecha="' + iso + '">' + d.getDate();
            var dots = dotsDelDia(porDia[iso] || []);
            if (dots.length) {
                html += '<div class="cal-dots">';
                for (var j = 0; j < dots.length; j++) {
                    html += '<span class="cal-dot ' + dots[j] + '"></span>';
                }
                html += '</div>';
            }
            html += '</div>';
            d.setDate(d.getDate() + 1);
        }
        $('cal-grid').innerHTML = html;
    }

    // ── Render: detalle del día seleccionado ─────────────────────────────────
    function renderDetalle() {
        var hoyIso = isoDate(hoy());
        $('cal-dd-title').innerHTML = esc(fmtFecha(diaSel)) +
            (diaSel === hoyIso ? ' <span class="cal-dd-hoy">hoy</span>' : '');

        var lista = mapaPorDia()[diaSel] || [];
        var vencen = [], hechas = [];
        lista.forEach(function (x) {
            (x.est === 'hecha' ? hechas : vencen).push(x);
        });

        var html = '';
        vencen.concat(hechas).forEach(function (x) {
            var act = buscarAct(x.id);
            if (!act) return;
            var ar = areaInfo(act.area);
            var tag = (x.est === 'hecha')
                ? '<span class="cal-dd-tag cal-dd-tag-hecha">✓ hecha</span>'
                : '<span class="cal-dd-tag cal-dd-tag-' + x.est + '">vence</span>';
            html += '<div class="cal-dd-item" data-cal-editar="' + act.id + '">' +
                '<span class="cal-dd-ico">' + ar.icon + '</span>' +
                '<span class="cal-dd-nombre">' + esc(act.nombre) + '</span>' +
                tag +
            '</div>';
        });
        if (!html) html = '<div class="cal-dd-empty">Sin actividades este día.</div>';
        $('cal-dd-lista').innerHTML = html;
    }

    // ── Render: modal "Todas las actividades" ────────────────────────────────
    var PILL = {
        vencida:   ['cal-pill-vencida', 'Vencida'],
        proxima:   ['cal-pill-proxima', 'Por vencer'],
        aldia:     ['cal-pill-aldia', 'Programada'],
        terminada: ['cal-pill-terminada', 'Terminada']
    };

    function renderTodas() {
        var orden = DATOS.actividades.slice().sort(function (a, b) {
            if (!!a.terminada !== !!b.terminada) return a.terminada ? 1 : -1;
            var pa = a.proxima_fecha || '9999-12-31';
            var pb = b.proxima_fecha || '9999-12-31';
            return pa.localeCompare(pb);
        });

        var activas = DATOS.actividades.filter(function (a) { return !a.terminada; }).length;
        $('cal-todas-sub').textContent = '· ' + activas + (activas === 1 ? ' activa' : ' activas');

        var html = '';
        orden.forEach(function (a) {
            var ar = areaInfo(a.area);
            var p = PILL[a.estado] || PILL.aldia;
            var frec = a.recurrente ? fmtIntervalo(a.intervalo_n, a.intervalo_u) : 'Una vez';
            var acciones = a.terminada
                ? '<button type="button" class="cal-btn-icono" title="Reactivar" data-cal-reactivar="' + a.id + '">↺</button>'
                : '<button type="button" class="cal-btn-icono" title="Completar" data-cal-completar="' + a.id + '">✓</button>' +
                  '<button type="button" class="cal-btn-icono" title="Editar" data-cal-editar="' + a.id + '">✎</button>';
            html += '<tr' + (a.terminada ? ' class="cal-fila-terminada"' : '') + '>' +
                '<td class="cal-td-nombre"><span class="cal-td-ico">' + ar.icon + '</span>' +
                    esc(a.nombre) + (a.avisar ? ' <span title="Con aviso">🔔</span>' : '') + '</td>' +
                '<td>' + esc(frec) + '</td>' +
                '<td>' + fmtFecha(a.proxima_fecha) + '</td>' +
                '<td><span class="cal-pill ' + p[0] + '">' + p[1] + '</span></td>' +
                '<td>' + badgeResp(a.responsable) + '</td>' +
                '<td class="cal-td-acciones">' + acciones + '</td>' +
            '</tr>';
        });
        $('cal-todas-tbody').innerHTML = html;
    }

    function renderTodo() {
        renderAgenda();
        renderCalendario();
        renderDetalle();
        if (!$('cal-modal-todas').hidden) renderTodas();
    }

    // ── Modales: apertura / cierre ───────────────────────────────────────────
    function reabrirTodasSiCorresponde() {
        if (volverATodas) {
            volverATodas = false;
            renderTodas();
            $('cal-modal-todas').hidden = false;
        }
    }

    // Cierra un overlay respetando el flujo "volver a Todas" del prototipo.
    function cerrarOverlay(overlay) {
        overlay.hidden = true;
        if (overlay.id === 'cal-modal-completar' || overlay.id === 'cal-modal-editor') {
            reabrirTodasSiCorresponde();
        } else {
            volverATodas = false;
        }
    }

    // Si la acción nace dentro del modal Todas, lo cerramos y marcamos volver.
    function prepararDesdeTodas(el) {
        if (el.closest('#cal-modal-todas')) {
            volverATodas = true;
            $('cal-modal-todas').hidden = true;
        } else {
            volverATodas = false;
        }
    }

    // ── Modal Completar ──────────────────────────────────────────────────────
    function setModoCompletar(m) {
        compModo = m;
        $('cal-comp-seg-repetir').classList.toggle('is-on', m === 'repetir');
        $('cal-comp-seg-terminar').classList.toggle('is-on', m === 'terminar');
        $('cal-comp-bloque-repetir').hidden = (m !== 'repetir');
        $('cal-comp-bloque-terminar').hidden = (m === 'repetir');
        $('cal-comp-guardar').textContent =
            (m === 'repetir') ? 'Guardar y reprogramar' : 'Marcar como terminada';
    }

    function actualizarPreviewCompletar() {
        var f = parseISO($('cal-comp-fecha').value);
        var n = parseInt($('cal-comp-int-n').value, 10) || 1;
        var u = $('cal-comp-int-u').value;
        $('cal-comp-preview').textContent = f ? fmtFecha(sumarIntervalo(f, n, u)) : '—';
    }

    function abrirCompletar(id) {
        var act = buscarAct(id);
        if (!act) return;
        compActId = id;
        $('cal-comp-sub').textContent = '· ' + act.nombre;
        fpCompFecha.setDate(isoDate(hoy()), true);   // true = dispara onChange (preview)
        $('cal-comp-int-n').value = act.intervalo_n || 6;
        $('cal-comp-int-u').value =
            (act.intervalo_u && UNIDADES.indexOf(act.intervalo_u) !== -1) ? act.intervalo_u : 'meses';
        setModoCompletar('repetir');
        actualizarPreviewCompletar();
        $('cal-modal-completar').hidden = false;
    }

    function guardarCompletar() {
        var act = buscarAct(compActId);
        if (!act) return;
        var fecha = $('cal-comp-fecha').value;
        if (!fecha) { toast('⚠ Elegí la fecha en que la hiciste.', 'error'); return; }

        var params = new URLSearchParams();
        params.append('fecha_hecha', fecha);
        params.append('repetir', compModo === 'repetir' ? '1' : '0');
        if (compModo === 'repetir') {
            params.append('intervalo_n', $('cal-comp-int-n').value);
            params.append('intervalo_u', $('cal-comp-int-u').value);
        }

        var nombre = act.nombre;
        var modo = compModo;
        var btn = $('cal-comp-guardar');
        btn.disabled = true;
        postAccion('/api/actividades/' + compActId + '/completar', params, function () {
            $('cal-modal-completar').hidden = true;
            if (modo === 'repetir') {
                var fresco = buscarAct(compActId);
                toast('✅ Listo. Próxima: ' +
                    (fresco && fresco.proxima_fecha ? fmtFecha(fresco.proxima_fecha) : '—'));
            } else {
                toast('✔ “' + nombre + '” marcada como terminada');
            }
            reabrirTodasSiCorresponde();
        }, function () { btn.disabled = false; });
    }

    // ── Modal Editor (alta completa / edición) ───────────────────────────────
    function setTipoEditor(rec) {
        edRecurrente = !!rec;
        $('cal-ed-seg-rec').classList.toggle('is-on', edRecurrente);
        $('cal-ed-seg-unica').classList.toggle('is-on', !edRecurrente);
        $('cal-ed-bloque-rec').hidden = !edRecurrente;
        $('cal-ed-bloque-unica').hidden = edRecurrente;
    }

    function abrirEditor(id) {
        edActId = (id === undefined || id === null) ? null : id;
        var act = edActId !== null ? buscarAct(edActId) : null;

        $('cal-ed-titulo').textContent = act ? '✎ Editar actividad' : '➕ Nueva actividad';
        $('cal-ed-guardar').textContent = act ? 'Guardar cambios' : 'Crear';
        $('cal-ed-eliminar').hidden = !act;

        $('cal-ed-nombre').value = act ? act.nombre : '';
        $('cal-ed-area').value = act ? act.area : 'casa';
        $('cal-ed-resp').value = act ? act.responsable : 'familia';
        setTipoEditor(act ? !!act.recurrente : true);
        $('cal-ed-int-n').value = (act && act.intervalo_n) ? act.intervalo_n : 6;
        $('cal-ed-int-u').value =
            (act && act.intervalo_u && UNIDADES.indexOf(act.intervalo_u) !== -1) ? act.intervalo_u : 'meses';
        fpEdUltima.setDate(act ? (act.ultima || '') : isoDate(hoy()), true);
        fpEdLimite.setDate(act
            ? (act.proxima_manual || '')
            : isoDate(sumarIntervalo(hoy(), 30, 'dias')), true);
        $('cal-ed-uso').value = (act && act.uso_nota) ? act.uso_nota : '';
        $('cal-ed-avisar').checked = act ? !!act.avisar : true;
        $('cal-ed-lead').value = act ? (Number(act.lead_dias) || 0) : 30;
        sincronizarAvisar('ed');

        $('cal-modal-editor').hidden = false;
        $('cal-ed-nombre').focus();
    }

    function guardarEditor() {
        var nombre = $('cal-ed-nombre').value.trim();
        if (!nombre) {
            toast('⚠ El nombre es obligatorio.', 'error');
            $('cal-ed-nombre').focus();
            return;
        }

        var params = new URLSearchParams();
        params.append('nombre', nombre);
        params.append('area', $('cal-ed-area').value);
        params.append('responsable', $('cal-ed-resp').value);
        params.append('recurrente', edRecurrente ? '1' : '0');
        if (edRecurrente) {
            params.append('intervalo_n', $('cal-ed-int-n').value);
            params.append('intervalo_u', $('cal-ed-int-u').value);
            params.append('ultima', $('cal-ed-ultima').value || '');
            params.append('proxima_manual', '');
        } else {
            params.append('ultima', '');
            params.append('proxima_manual', $('cal-ed-limite').value || '');
        }
        params.append('avisar', $('cal-ed-avisar').checked ? '1' : '0');
        params.append('lead_dias', $('cal-ed-lead').value || '0');
        params.append('uso_nota', $('cal-ed-uso').value.trim());

        var esNuevo = (edActId === null);
        var url = esNuevo ? '/api/actividades/crear' : '/api/actividades/' + edActId + '/editar';
        var btn = $('cal-ed-guardar');
        btn.disabled = true;
        postAccion(url, params, function () {
            $('cal-modal-editor').hidden = true;
            toast(esNuevo ? '➕ Actividad creada' : '✎ Cambios guardados');
            reabrirTodasSiCorresponde();
        }, function () { btn.disabled = false; });
    }

    // ── Modal Confirmar (eliminar) ───────────────────────────────────────────
    function abrirConfirmEliminar() {
        var act = buscarAct(edActId);
        if (!act) return;
        actEliminarId = edActId;
        $('cal-confirm-msg').textContent =
            '¿Seguro que querés eliminar “' + act.nombre + '”? Se borra de forma permanente. ' +
            'Si solo querés dejar de hacerla, usá “Completar → No, terminada”.';
        $('cal-modal-editor').hidden = true;
        $('cal-modal-confirm').hidden = false;
    }

    function confirmarEliminar() {
        var act = buscarAct(actEliminarId);
        var nombre = act ? act.nombre : '';
        var btn = $('cal-confirm-si');
        btn.disabled = true;
        postAccion('/api/actividades/' + actEliminarId + '/eliminar', new URLSearchParams(), function () {
            $('cal-modal-confirm').hidden = true;
            volverATodas = false;   // como el prototipo: eliminar cierra todo
            toast('🗑️ “' + nombre + '” eliminada', 'info');
        }, function () { btn.disabled = false; });
    }

    // ── Reactivar (desde "Todas", sin confirmación) ──────────────────────────
    function reactivar(id) {
        var act = buscarAct(id);
        var nombre = act ? act.nombre : '';
        postAccion('/api/actividades/' + id + '/reactivar', new URLSearchParams(), function () {
            toast('↺ “' + nombre + '” reactivada');
        });
    }

    // ── Modal Todas ──────────────────────────────────────────────────────────
    function abrirTodas() {
        renderTodas();
        $('cal-modal-todas').hidden = false;
    }

    // ── Switch "Avisar antes" (alta rápida 'qa' y editor 'ed') ───────────────
    function sincronizarAvisar(pre) {
        var chk = $('cal-' + pre + '-avisar');
        var lead = $('cal-' + pre + '-lead');
        var hint = $('cal-' + pre + '-avisar-hint');
        lead.hidden = !chk.checked;
        var n = parseInt(lead.value, 10) || 0;
        if (pre === 'qa') {
            hint.textContent = chk.checked
                ? (n + ' días antes de vencer')
                : 'Solo aparece cuando vence';
        } else {
            hint.textContent = chk.checked
                ? ('Aparece en pendientes ' + n + ' días antes')
                : 'Solo aparece cuando ya venció';
        }
    }

    // ── Alta rápida ──────────────────────────────────────────────────────────
    function initQuickAdd() {
        var form = $('cal-form-rapido');
        fpQaUltima.setDate(isoDate(hoy()), true);
        sincronizarAvisar('qa');

        $('cal-qa-avisar').addEventListener('change', function () { sincronizarAvisar('qa'); });
        $('cal-qa-lead').addEventListener('input', function () { sincronizarAvisar('qa'); });

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            var nombre = $('cal-qa-nombre').value.trim();
            if (!nombre) {
                toast('⚠ Escribí qué no hay que olvidarse.', 'error');
                $('cal-qa-nombre').focus();
                return;
            }
            var params = new URLSearchParams();
            params.append('nombre', nombre);
            params.append('area', $('cal-qa-area').value);
            params.append('responsable', $('cal-qa-resp').value);
            params.append('recurrente', '1');
            params.append('intervalo_n', $('cal-qa-int-n').value);
            params.append('intervalo_u', $('cal-qa-int-u').value);
            params.append('ultima', $('cal-qa-ultima').value || '');
            params.append('proxima_manual', '');
            params.append('avisar', $('cal-qa-avisar').checked ? '1' : '0');
            params.append('lead_dias', $('cal-qa-lead').value || '0');
            params.append('uso_nota', '');

            var btn = $('cal-qa-guardar');
            btn.disabled = true;
            postAccion('/api/actividades/crear', params, function () {
                toast('➕ “' + nombre + '” agregada');
                form.reset();   // vuelve a los defaults del markup
                fpQaUltima.setDate(isoDate(hoy()), true);   // reset no toca el altInput
                sincronizarAvisar('qa');
            }, function () { btn.disabled = false; });
        });
    }

    // ── Init ─────────────────────────────────────────────────────────────────
    function init() {
        if (!document.querySelector('.cal-page')) return;

        // Activa el layout desktop sin scroll de página (fallback: :has en CSS)
        document.body.classList.add('cal-body');

        var h = hoy();
        mesCursor = new Date(h.getFullYear(), h.getMonth(), 1);
        diaSel = isoDate(h);

        initFlatpickrs();

        // Navegación del mes
        $('cal-mes-prev').addEventListener('click', function () {
            mesCursor = new Date(mesCursor.getFullYear(), mesCursor.getMonth() - 1, 1);
            renderCalendario();
        });
        $('cal-mes-next').addEventListener('click', function () {
            mesCursor = new Date(mesCursor.getFullYear(), mesCursor.getMonth() + 1, 1);
            renderCalendario();
        });
        $('cal-mes-hoy').addEventListener('click', function () {
            var hd = hoy();
            mesCursor = new Date(hd.getFullYear(), hd.getMonth(), 1);
            diaSel = isoDate(hd);
            renderCalendario();
            renderDetalle();
        });

        // Selección de día en la grilla
        $('cal-grid').addEventListener('click', function (e) {
            var celda = e.target.closest('.cal-day');
            if (!celda) return;
            diaSel = celda.getAttribute('data-fecha');
            renderCalendario();
            renderDetalle();
        });

        // Botones fijos
        $('cal-btn-ver-todas').addEventListener('click', abrirTodas);
        $('cal-btn-mas-opciones').addEventListener('click', function () {
            volverATodas = false;
            abrirEditor(null);
        });
        $('cal-todas-nueva').addEventListener('click', function () {
            volverATodas = true;
            $('cal-modal-todas').hidden = true;
            abrirEditor(null);
        });

        // Modal Completar (el cambio de fecha dispara el preview vía
        // onChange de flatpickr, configurado en initFlatpickrs())
        $('cal-comp-seg-repetir').addEventListener('click', function () { setModoCompletar('repetir'); });
        $('cal-comp-seg-terminar').addEventListener('click', function () { setModoCompletar('terminar'); });
        $('cal-comp-int-n').addEventListener('input', actualizarPreviewCompletar);
        $('cal-comp-int-u').addEventListener('change', actualizarPreviewCompletar);
        $('cal-comp-guardar').addEventListener('click', guardarCompletar);

        // Modal Editor
        $('cal-ed-seg-rec').addEventListener('click', function () { setTipoEditor(true); });
        $('cal-ed-seg-unica').addEventListener('click', function () { setTipoEditor(false); });
        $('cal-ed-avisar').addEventListener('change', function () { sincronizarAvisar('ed'); });
        $('cal-ed-lead').addEventListener('input', function () { sincronizarAvisar('ed'); });
        $('cal-ed-guardar').addEventListener('click', guardarEditor);
        $('cal-ed-eliminar').addEventListener('click', abrirConfirmEliminar);

        // Modal Confirmar
        $('cal-confirm-si').addEventListener('click', confirmarEliminar);

        // Delegación global: acciones repetidas en agenda / detalle / tabla
        document.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-cal-completar]');
            if (btn) {
                prepararDesdeTodas(btn);
                abrirCompletar(parseInt(btn.getAttribute('data-cal-completar'), 10));
                return;
            }
            btn = e.target.closest('[data-cal-editar]');
            if (btn) {
                prepararDesdeTodas(btn);
                abrirEditor(parseInt(btn.getAttribute('data-cal-editar'), 10));
                return;
            }
            btn = e.target.closest('[data-cal-reactivar]');
            if (btn) {
                reactivar(parseInt(btn.getAttribute('data-cal-reactivar'), 10));
                return;
            }
            btn = e.target.closest('[data-cal-cerrar]');
            if (btn) {
                var ov = btn.closest('.cal-overlay');
                if (ov) cerrarOverlay(ov);
            }
        });

        // Cierre por click en el backdrop
        ['cal-modal-completar', 'cal-modal-editor', 'cal-modal-todas', 'cal-modal-confirm']
            .forEach(function (id) {
                var ov = $(id);
                ov.addEventListener('mousedown', function (e) {
                    if (e.target === ov) cerrarOverlay(ov);
                });
            });

        // Escape cierra el modal visible (nunca hay más de uno a la vez)
        document.addEventListener('keydown', function (e) {
            if (e.key !== 'Escape') return;
            var ids = ['cal-modal-confirm', 'cal-modal-completar', 'cal-modal-editor', 'cal-modal-todas'];
            for (var i = 0; i < ids.length; i++) {
                var ov = $(ids[i]);
                if (!ov.hidden) { cerrarOverlay(ov); return; }
            }
        });

        initQuickAdd();

        renderAgenda();
        renderCalendario();
        renderDetalle();

        console.log('✓ calendario.js cargado —', DATOS.actividades.length, 'actividades');
    }

    document.addEventListener('DOMContentLoaded', init);
})();
