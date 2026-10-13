---
paths:
  - "docs/**/*.md"
  - "CLAUDE.md"
  - ".claude/agents/**"
  - ".claude/rules/**"
---

# Escribir texto que lee otro agente

- **Telegráfico desde la primera versión** (`docs/METODOLOGIA.md` §2b): sin artículos, intro, cierre ni relleno. Conservar textual: identificadores, rutas, comandos, números CON unidad, negaciones (no / nunca / solo / siempre…), cada ⚠ con su porqué.
- **Cada dato UNA vez.** Si está en otro lado, apuntar (`ver CONTEXT_DB.md`), no copiar.
- Editar el `.md` en la sección que ya existe. Cada `CONTEXT_*.md` < 150 líneas; si crece, partir en sub-secciones.
- Al reescribir texto viejo: `python TempScripts/validar_telegrafico.py validar ORIGINAL NUEVO`.
- Auditoría: `grep -rn "TODO contexto" docs/` vacío.

## Rules (`.claude/rules/*.md`) y `CLAUDE.md` de subcarpeta

- Se cargan SOLOS al Read / Edit / Write / `cat` de un archivo que coincide → **NO** nombrarlos ni apuntarlos desde `CLAUDE.md` raíz ni `docs/` (gasto sin uso).
- Rule = detalle que solo importa al tocar ciertos archivos → frontmatter `paths:`. Regla de toda la sesión → `CLAUDE.md` §4. Rule sin `paths:` = no usar (eso es `CLAUDE.md`).
- Preferir rule con `paths:` a `CLAUDE.md` de subcarpeta: apunta también a archivos de la raíz (`app.py`) y a varias carpetas.
- ⚠ Grep / Glob NO disparan la carga. ⚠ Write de archivo NUEVO → llega DESPUÉS de escribir. Por eso regla crítica deja 1 línea núcleo (sin puntero) en `CLAUDE.md` §4.
- ⚠ `Explore` arranca sin `CLAUDE.md`, pero rules con `paths:` sí le llegan.
