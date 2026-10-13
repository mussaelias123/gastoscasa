---
paths:
  - "templates/**/*.html"
  - "static/**/*.js"
---

# Seguridad en front (regla 9 de `CLAUDE.md` §4, parte HTML/JS)

- **Salida escapada:** datos → `<script>` con `| tojson` (NUNCA `json.dumps(...)` + `| safe`). JS: todo dato → `innerHTML` pasa por `escHtml()` (app.js) / `esc()` del módulo, o `createElement` + `textContent`.
- **CSP:** todo `<script>` inline lleva `nonce="{{ csp_nonce }}"`. Prohibidos `onclick=` y todo `on*=` inline (también en HTML armado en JS), `javascript:`, `eval`, `new Function`. Eventos → `addEventListener` / `data-accion`. ⚠ Romperlo = navegador bloquea EN SILENCIO (solo error en consola). Test: `tests/test_csp_templates.py`.
- **Librerías de terceros solo en `static/vendor/`**, nunca `<script src>` a un CDN.
- Detalle: `docs/CONTEXT_SEGURIDAD.md` §Reglas 4-6.
