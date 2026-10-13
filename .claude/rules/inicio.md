---
paths:
  - "templates/index.html"
  - "static/home.js"
---

# Inicio (`/`) no se toca sin pedido explícito (regla 7 de `CLAUDE.md` §4, detalle)

- `/` = vitrina de módulos, **no scrollea** (calibrada para iPhone SE).
- Ningún agente agrega, mueve ni amplía tarjeta, barra o sección (`templates/index.html`, `static/home.js`, bloque `.home-*` de `style.css`) por iniciativa propia. Hace falta pedido o confirmación del usuario.
- Lo nuevo va **en su módulo**: lista de tareas → Rutina; saldo → Gastos.
- Origen (2026-09-21): barra "✓ Tareas de hoy" metida de prestado en el Inicio, se quitó. Tareas viven solo en `/rutina`.
