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
- Rule nueva en `.claude/rules/` → solo si aplica a archivos puntuales (`paths:`); regla de toda la sesión → `CLAUDE.md` §4. Ver `docs/METODOLOGIA.md` §2c.
