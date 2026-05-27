# Sub-agentes especializados — Gastos Casa

Cada archivo `.md` en esta carpeta es un perfil de sub-agente. Define misión, contexto a leer, archivos permitidos y reglas.

## Por qué existen
La IA padre (Claude) tiene la visión completa del proyecto.
Los sub-agentes son IAs más pequeñas, con contexto cerrado, que ejecutan tareas específicas gastando menos tokens.

## Lista actual

| Agente                  | Cuándo usarlo                                                |
|-------------------------|--------------------------------------------------------------|
| `frontend-dev`          | Cambios en CSS, JS, HTML.                                    |
| `backend-dev`           | Cambios en rutas Flask (`app.py`).                           |
| `db-engineer`           | Cambios en `database.py`, esquema, queries, backfills.       |
| `cotizacion-maintainer` | Cambios en `cotizacion.py` o scheduler de cotización.        |
| `auth-maintainer`       | Cambios en `auth.py`, login, whitelist, OAuth.               |
| `verifier`              | Verifica en ngrok que la app no se rompió tras un cambio.    |

## Cómo invocarlos

### En Claude Code (CLI)
Copiar este directorio a `.claude/agents/` del proyecto. Claude Code los detecta automáticamente y se pueden invocar con `Task tool` o vía slash command.

### En Cowork / Claude Agent SDK
Usar `Task tool` (Agent) pasando como `prompt` el contenido del archivo del sub-agente como instrucciones de sistema, más la tarea concreta.

### En cualquier IA
Pegar el contenido del archivo del sub-agente como contexto inicial al iniciar una nueva conversación enfocada.

## Regla compartida (importante)
Todos los sub-agentes deben actualizar el `docs/CONTEXT_*.md` que les corresponde al terminar un cambio. Si no lo hacen, el próximo agente trabajará con info obsoleta.

Ver `CLAUDE.md → sección 5` (Metodología de actualización de contexto).
