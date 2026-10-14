---
paths:
  - "static/**/*.{css,js}"
  - "templates/**/*.html"
---

# Paleta de colores (regla 1 de `CLAUDE.md` §4, detalle)

Todo color → `var(--color-...)`. **Cero hardcode** (`#fff`, `rgb(...)`, nombres de color).

- **Valores runtime:** `config.json → paleta_light / paleta_dark` (23 vars c/u). `base.html` los inyecta en `<style>` del `<head>` como `:root { ... }` y `html[data-theme="dark"] { ... }`.
- **Fallbacks:** `static/style.css → :root`, mismos valores, por si `config.json` no carga.
- **Excepciones documentadas** (hardcode intencional, NO "arreglar"):
  - `login.html`: standalone, sin acceso a config.
  - **favicon** de `base.html` y `login.html`: SVG en `data:` URI → no lee `var(--color-...)`. Acento + blanco a mano, `%23` en vez de `#`.
  - **íconos PNG de la PWA** (`static/img/icon-*.png`): binario, mismo motivo. Regenerar con `python TempScripts/generar_iconos_pwa.py` si cambia el acento. `theme_color` del manifest sí sigue la paleta en caliente (es ruta).
  - `.dash-toggle-btn.activo { color: #ffffff }`: contraste en dark 4.47:1 vs 3.27:1 de `var(--color-superficie)`.
  - Tema cálido Lactancia: bloque scoped `body.lac-body`, redefine mismas vars.
  - Tema Rutina: `body.rut-body` redefine `--color-texto-muted` con `color-mix` de otras vars → no es hardcode (contraste sobre tarjetas translúcidas, ver `CONTEXT_FRONTEND.md`).
  - `--color-rut-p4`..`p8` en `.rut-wrap, .home-card--rutina`: identificadores de miembro (familias > 3), no colores de marca. Paleta configurable sigue en 23 vars.
- Definición y leyenda: Settings → Paleta. Variable nueva → `CONTEXT_FRONTEND.md` (tabla paleta) + Settings.
