/* =============================================================================
   ARCHIVO: static/home.js
   =============================================================================
   Interactividad de la página Inicio (/). Solo se carga en esa página (vía
   {% block scripts %} de index.html, con ?v={{ static_version }}).

   Alcance: (1) manejo genérico de "sheets" (los forms viven en .home-sheet:
   bloque normal en desktop ≥900px, bottom-sheet fijo en mobile). Botones
   [data-sheet="nombre"] abren #home-sheet-<nombre> + el overlay #home-overlay
   (clase .is-abierta). Cierre por [data-sheet-cerrar], click en el overlay y
   tecla ESC. La lógica AJAX del form de movimiento es de app.js
   (initFormAjax, rama data-modo="inline"), que al guardar llama a
   window.cerrarHomeSheet('gastos').
   (2) Tarjeta Lactancia (initLactancia): form de extracción (partial
   _form_lactancia.html, submit AJAX a /api/lactancia/crear) + botones
   "✓ Usada" (POST /api/lactancia/<id>/cerrar, motivo=usada). Estado local =
   window.LAC_HOME {heladera, freezer_primera}; cada mutación devuelve
   _lac_payload() completo y renderLacHome() re-renderiza #home-lac-listas
   espejando el markup Jinja de index.html (createElement/textContent, nunca
   innerHTML con datos del server). Vencimientos/estados vienen CALCULADOS
   del server (horas_restantes/dias_restantes): acá solo se formatean.
   En el Inicio lactancia.js NO se carga: los helpers de formato y la config
   de flatpickr son copias mínimas de ese archivo.
   (3) Tarjeta Rutina (initRutina): qué está haciendo AHORA cada uno
   (León/Mamá/Papá) y qué viene después. Los datos los da
   window.Rutina.hoyAhora() (rutina.js SÍ se carga en el Inicio, con
   window.RUT_DATOS + rutina-actividades.js antes, mismo orden que /rutina).
   Render con createElement/textContent (títulos = texto libre del usuario);
   tick de 30 s re-llama hoyAhora() (se saltea con la pestaña oculta).
   ============================================================================= */

(function () {
    'use strict';

    function init() {
        // Guard: solo actuar en la página Inicio
        if (!document.querySelector('.home-page')) return;

        // Gancho CSS explícito (backup del selector body:has(.home-page))
        document.body.classList.add('home-body');

        var overlay = document.getElementById('home-overlay');

        function abrirSheet(nombre) {
            var sheet = document.getElementById('home-sheet-' + nombre);
            if (!sheet) return;
            sheet.classList.add('is-abierta');
            if (overlay) overlay.classList.add('is-abierta');
        }

        function cerrarSheets() {
            document.querySelectorAll('.home-sheet.is-abierta').forEach(function (s) {
                s.classList.remove('is-abierta');
            });
            if (overlay) overlay.classList.remove('is-abierta');
        }

        // API pública: la usa initFormAjax (app.js) tras guardar un movimiento.
        // No-op si el sheet no existe.
        window.cerrarHomeSheet = function (nombre) {
            var sheet = document.getElementById('home-sheet-' + nombre);
            if (!sheet) return;
            sheet.classList.remove('is-abierta');
            if (overlay) overlay.classList.remove('is-abierta');
        };

        // Abrir: botones [data-sheet]
        document.querySelectorAll('[data-sheet]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                abrirSheet(btn.dataset.sheet);
            });
        });

        // Cerrar: ✕ ([data-sheet-cerrar]), overlay y ESC
        document.querySelectorAll('[data-sheet-cerrar]').forEach(function (btn) {
            btn.addEventListener('click', cerrarSheets);
        });

        if (overlay) overlay.addEventListener('click', cerrarSheets);

        document.addEventListener('keydown', function (e) {
            if (e.key !== 'Escape') return;
            // Solo actuar si hay un sheet abierto (no pisar el ESC de los drawers)
            if (document.querySelector('.home-sheet.is-abierta')) cerrarSheets();
        });

        initLactancia();
        initRutina();
    }

    /* ════════════════════════════════════════════════════════════════════════
       TARJETA RUTINA — qué hace cada uno AHORA + qué viene después
       Fuente: window.Rutina.hoyAhora() (rutina.js), que fuerza "hoy real +
       etapa actual" y devuelve [{user, nombre, emoji, actual, siguiente}].
       Color por persona: clases home-rut--<user> → var(--color-persona-*)
       con el MISMO mapeo que /rutina (León=leon, mamá=mari, papá=elias).
       Solo createElement/textContent: los títulos pueden ser texto libre
       (tareas añadidas por el usuario).
       ════════════════════════════════════════════════════════════════════════ */

    function initRutina() {
        var cont = document.getElementById('home-rut-lista');
        if (!cont) return;

        // rutina.js no cargó: dejar un texto muted en vez de tarjeta en blanco
        if (!window.Rutina) {
            var sin = document.createElement('p');
            sin.className = 'home-rut-vacio';
            sin.textContent = 'Sin actividades ahora.';
            cont.appendChild(sin);
            return;
        }

        function filaRut(p) {
            var el = document.createElement('div');
            el.className = 'home-rut-item home-rut--' + p.user;

            // "{emoji persona} {nombre}: {emoji act} {titulo} · desde–hasta"
            var linea = document.createElement('div');
            linea.className = 'home-rut-linea';
            var quien = document.createElement('span');
            quien.className = 'home-rut-quien';
            quien.textContent = p.emoji + ' ' + p.nombre + ':';
            var act = document.createElement('span');
            act.className = 'home-rut-act';
            act.textContent = p.actual.emoji + ' ' + p.actual.titulo;
            var horas = document.createElement('span');
            horas.className = 'home-rut-horas';
            // hasta null = actividad abierta (dur 0: sueño nocturno / a dormir)
            horas.textContent = p.actual.desde + '–' + (p.actual.hasta || '…');
            linea.appendChild(quien);
            linea.appendChild(act);
            linea.appendChild(horas);
            el.appendChild(linea);

            if (p.siguiente) {
                var desp = document.createElement('div');
                desp.className = 'home-rut-despues';
                desp.textContent = 'Después: ' + p.siguiente.emoji + ' ' +
                    p.siguiente.titulo + ' · ' + p.siguiente.hora;
                el.appendChild(desp);
            }
            return el;
        }

        function renderRutHome() {
            var lista;
            try { lista = window.Rutina.hoyAhora(); }
            catch (e) {
                console.error('Error rutina (home):', e);
                lista = [];   // render igual: nunca tarjeta en blanco
            }
            cont.textContent = '';   // vaciar
            if (!lista.length) {
                var v = document.createElement('p');
                v.className = 'home-rut-vacio';
                v.textContent = 'Sin actividades ahora.';
                cont.appendChild(v);
                return;
            }
            lista.forEach(function (p) { cont.appendChild(filaRut(p)); });
        }

        renderRutHome();
        // Reloj vivo: mismo ritmo que /rutina (30 s), sin trabajo en background
        setInterval(function () {
            if (!document.hidden) renderRutHome();
        }, 30000);
    }

    /* ════════════════════════════════════════════════════════════════════════
       TARJETA LACTANCIA — cargar extracción + consumir partidas
       Estado local: window.LAC_HOME = { heladera: [...], freezer_primera: {}|null }
       (proyección de _lac_payload() que arma _home_lactancia_payload() en
       app.py). Las mutaciones responden el payload COMPLETO fresco: de ahí se
       toman heladera y freezer[0] para re-renderizar.
       ════════════════════════════════════════════════════════════════════════ */

    // ── Formatos (copias mínimas de lactancia.js, que acá NO se carga) ──────
    var LAC_MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
                     'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

    // '2026-07-12' → '12 jul' (fmtFechaCorta de lactancia.js)
    function lacFechaCorta(f) {
        var p = String(f || '').split('T')[0].split('-');
        if (p.length !== 3) return '—';
        return Number(p[2]) + ' ' + LAC_MESES[Number(p[1]) - 1];
    }

    // Heladera: relativo desde horas_restantes (textoVencHeladera de lactancia.js)
    function lacVencHeladera(horas) {
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

    // Freezer: relativo desde dias_restantes (textoVencFreezer de lactancia.js)
    function lacVencFreezer(dias) {
        if (dias === null || dias === undefined) return '';
        if (dias === 0) return 'Vence hoy';
        if (dias === 1) return 'Vence mañana';
        if (dias > 1) return 'Vence en ' + dias + ' días';
        if (dias === -1) return 'Venció ayer';
        return 'Venció hace ' + Math.abs(dias) + ' días';
    }

    // ── Toast mínimo (reusa .toast base + clases lac-toast-* de style.css) ──
    function lacToast(texto, tipo) {
        var cont = document.getElementById('toast-container');
        if (!cont) return;
        var el = document.createElement('div');
        el.className = 'toast ' + (tipo === 'error' ? 'lac-toast-error' : 'lac-toast-ok');
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

    // ── Re-render client-side de #home-lac-listas ────────────────────────────
    // Espeja el markup Jinja de index.html. Solo createElement/textContent:
    // NUNCA innerHTML con datos del server.
    function lacItem(p, vencTexto) {
        var item = document.createElement('div');
        item.className = 'home-lac-item is-' + p.estado;

        var info = document.createElement('div');
        info.className = 'home-lac-info';

        var top = document.createElement('div');
        top.className = 'home-lac-top';
        var vol = document.createElement('span');
        vol.className = 'home-lac-vol';
        vol.textContent = (Number(p.volumen_ml) || 0) + ' ml';
        var venc = document.createElement('span');
        venc.className = 'home-lac-venc t-' + p.estado;
        venc.textContent = vencTexto;
        top.appendChild(vol);
        top.appendChild(venc);

        var meta = document.createElement('div');
        meta.className = 'home-lac-meta';
        meta.textContent = 'Extraída ' + lacFechaCorta(p.fecha_extraccion) +
            (p.hora_extraccion ? ' · ' + p.hora_extraccion + ' h' : '');

        info.appendChild(top);
        info.appendChild(meta);

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'home-lac-usar';
        btn.setAttribute('data-lac-usar', p.id);
        btn.title = 'Se le dio a León (fecha de hoy)';
        btn.textContent = '✓ Usada';

        item.appendChild(info);
        item.appendChild(btn);
        return item;
    }

    function lacSeccion(titulo) {
        var el = document.createElement('div');
        el.className = 'home-lac-sec';
        el.textContent = titulo;
        return el;
    }

    function lacVacio(texto) {
        var el = document.createElement('p');
        el.className = 'home-lac-vacio';
        el.textContent = texto;
        return el;
    }

    function renderLacHome() {
        var cont = document.getElementById('home-lac-listas');
        var datos = window.LAC_HOME;
        if (!cont || !datos) return;

        cont.textContent = '';   // vaciar
        cont.appendChild(lacSeccion('🥛 Heladera'));
        if (datos.heladera && datos.heladera.length) {
            datos.heladera.forEach(function (p) {
                cont.appendChild(lacItem(p, lacVencHeladera(p.horas_restantes)));
            });
        } else {
            cont.appendChild(lacVacio('Nada en la heladera.'));
        }

        cont.appendChild(lacSeccion('🧊 Freezer · próxima a usar'));
        if (datos.freezer_primera) {
            cont.appendChild(lacItem(datos.freezer_primera,
                lacVencFreezer(datos.freezer_primera.dias_restantes)));
        } else {
            cont.appendChild(lacVacio('Sin partidas en el freezer.'));
        }
    }

    // ── AJAX: toda mutación responde _lac_payload() completo fresco ─────────
    function lacPost(url, params, onOk, onFin) {
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
            // Proyección del payload completo (misma que _home_lactancia_payload)
            window.LAC_HOME = {
                heladera: data.heladera || [],
                freezer_primera: (data.freezer && data.freezer.length) ? data.freezer[0] : null
            };
            renderLacHome();
            if (window.Notif) window.Notif.refrescar();
            if (onOk) onOk(data);
        })
        .catch(function (err) {
            console.error('Error AJAX lactancia (home):', err);
            lacToast('⚠ ' + err.message, 'error');
        })
        .finally(function () {
            if (onFin) onFin();
        });
    }

    function initLactancia() {
        var form = document.getElementById('lac-form-extraccion');
        var listas = document.getElementById('home-lac-listas');
        if (!form || !listas || !window.LAC_HOME) return;

        // Flatpickr de los 2 inputs del form — misma config mínima que usa
        // lactancia.js en su página (acá NO se carga). disableMobile en la
        // hora es CLAVE: sin él, flatpickr en celulares se reemplaza por el
        // <input type="time"> nativo (12h AM/PM en iOS, desborda la tarjeta).
        var fpFecha = flatpickr(document.getElementById('lac-ex-fecha'), {
            locale: 'es', dateFormat: 'Y-m-d', altInput: true, altFormat: 'd/m/Y',
            allowInput: true, maxDate: 'today'
        });
        var fpHora = flatpickr(document.getElementById('lac-ex-hora'), {
            enableTime: true, noCalendar: true, dateFormat: 'H:i',
            time_24hr: true, allowInput: true, disableMobile: true
        });

        // Defaults: hoy + ahora (el backend EXIGE fecha y hora no vacías).
        // form.reset() no repone el altInput de flatpickr: siempre re-fijar.
        function resetFormLac() {
            form.reset();
            var d = new Date();
            var iso = d.getFullYear() + '-' +
                String(d.getMonth() + 1).padStart(2, '0') + '-' +
                String(d.getDate()).padStart(2, '0');
            fpFecha.setDate(iso, true);
            fpHora.setDate(String(d.getHours()).padStart(2, '0') + ':' +
                String(d.getMinutes()).padStart(2, '0'), true);
        }
        resetFormLac();

        // Alta de extracción (submit AJAX; sin JS el form POSTea igual y el
        // backend redirige a /lactancia)
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            var vol = document.getElementById('lac-ex-volumen').value.trim();
            if (!vol) {
                lacToast('⚠ Cargá el volumen en ml.', 'error');
                document.getElementById('lac-ex-volumen').focus();
                return;
            }
            var params = new URLSearchParams();
            params.append('ubicacion', 'heladera');
            params.append('volumen_ml', vol);
            params.append('fecha_extraccion', document.getElementById('lac-ex-fecha').value || '');
            params.append('hora_extraccion', document.getElementById('lac-ex-hora').value || '');
            params.append('notas', document.getElementById('lac-ex-notas').value.trim());

            var btn = document.getElementById('lac-ex-guardar');
            btn.disabled = true;
            lacPost('/api/lactancia/crear', params, function () {
                lacToast('🥛 ' + vol + ' ml a la heladera.');
                resetFormLac();
                window.cerrarHomeSheet('lactancia');
            }, function () { btn.disabled = false; });
        });

        // "✓ Usada" — delegación en el contenedor de listas (sobrevive los
        // re-renders). fecha_cierre vacía → hoy en el server.
        listas.addEventListener('click', function (e) {
            var btn = e.target.closest('[data-lac-usar]');
            if (!btn) return;
            var id = parseInt(btn.getAttribute('data-lac-usar'), 10);
            var params = new URLSearchParams();
            params.append('motivo', 'usada');
            params.append('fecha_cierre', '');
            btn.disabled = true;
            lacPost('/api/lactancia/' + id + '/cerrar', params, function () {
                lacToast('✓ Partida marcada como usada.');
            }, function () { btn.disabled = false; });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
