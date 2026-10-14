---
paths:
  - "templates/sw.js"
---

# `templates/sw.js` NO es un template Jinja

- Ruta `/sw.js` de `app.py` lo lee como texto plano (`open().read()`) y reemplaza `__VERSION__` a mano. **NUNCA** `render_template()`: dispara context processors en cada navegación y Jinja rompería cualquier `{{ }}` / `{# #}` del JS.
- Dos mitades (LÁPIDA / ACTIVO), la ruta sirve UNA según `sw_enabled`. ⚠ Un SW instalado no se apaga borrando la ruta → por eso existe la lápida.
- **Leer el encabezado del archivo ANTES de cambiar nada.** Más: `CONTEXT_BACKEND.md` (ruta) + `CONTEXT_PUSH.md` (listeners push).
