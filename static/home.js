/* =============================================================================
   ARCHIVO: static/home.js
   =============================================================================
   Interactividad de la página Inicio (/). Solo se carga en esa página (vía
   {% block scripts %} de index.html, con ?v={{ static_version }}).

   Alcance de esta etapa: manejo genérico de "sheets" (el form de movimiento
   vive en .home-sheet: bloque normal en desktop ≥900px, bottom-sheet fijo en
   mobile). Botones [data-sheet="nombre"] abren #home-sheet-<nombre> + el
   overlay #home-overlay (clase .is-abierta). Cierre por [data-sheet-cerrar],
   click en el overlay y tecla ESC. La lógica AJAX del form es de app.js
   (initFormAjax, rama data-modo="inline"), que al guardar llama a
   window.cerrarHomeSheet('gastos').
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
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
