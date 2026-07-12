# Metodología de trabajo con IA

> Documento corto. Todo el equipo de IAs (padre + sub-agentes) lo respeta.

## Ciclo de cualquier cambio

```
0. PREPARAR     → Worktree limpio + main fresco antes de abrir rama (ver §5).
1. CLARIFICAR  → AskUserQuestion si la tarea no es trivial.
2. LEER         → Solo el contexto necesario (ver tabla en CLAUDE.md §3).
3. EJECUTAR     → Cambio mínimo y reversible.
4. ACTUALIZAR   → CONTEXT_*.md del dominio tocado (ver §1 abajo).
5. VERIFICAR    → Sub-agente verifier en ngrok.
6. REPORTAR     → Resumen corto al usuario.
7. ORDENAR      → Dejar el worktree en buen estado (ver §5).
```

## §1 Qué actualizar después de cambiar el programa (CRÍTICO)

| Si cambiaste...                              | Actualizar                                              |
|----------------------------------------------|---------------------------------------------------------|
| Una ruta de `app.py`                         | `docs/CONTEXT_BACKEND.md` → tabla de rutas              |
| Un helper de `app.py` (`_calcular_monto_usd` etc.) | `docs/CONTEXT_BACKEND.md` → "Helpers internos clave" |
| Esquema de tabla en `database.py`            | `docs/CONTEXT_DB.md` → "Esquema"                        |
| Firma de función en `database.py`            | `docs/CONTEXT_DB.md` → "Funciones públicas"             |
| Variable de color en `:root` de CSS          | `docs/CONTEXT_FRONTEND.md` → tabla paleta + Settings UI |
| Sección grande nueva en `style.css`          | `docs/CONTEXT_FRONTEND.md` → "Mapa de secciones"        |
| Función JS pública en `static/app.js`        | `docs/CONTEXT_FRONTEND.md` → tabla funciones JS         |
| Plantilla nueva en `templates/`              | `docs/CONTEXT_FRONTEND.md` → lista de templates         |
| URL pública (ngrok) o servicio Windows       | `docs/CONTEXT_DEPLOY.md` → URL / comandos               |
| Whitelist de emails OAuth                    | `docs/CONTEXT_AUTH.md` → "Whitelist de emails"          |
| Clave nueva en `config.json`                 | `docs/CONTEXT_CONFIG.md` → tabla de claves              |
| Lógica de cotización                         | `docs/CONTEXT_COTIZACION.md` → reglas o estado          |
| Archivo nuevo en raíz / carpeta nueva        | `CLAUDE.md` → tabla §2 "Mapa de archivos por dominio"   |
| Nueva regla de proyecto acordada             | `CLAUDE.md` → §4 "Reglas globales"                      |

**Si no aplica nada de la tabla, no se necesita actualizar contexto.**

## §2 Qué NO documentar
- Nombres de variables internas pequeñas.
- Lógica que se lee en 30 segundos del código.
- Detalles de implementación que cambian seguido.

El contexto debe ser **un mapa**, no una copia del código.

## §3 Auditoría rápida
- Cada `CONTEXT_*.md` debe seguir bajo 150 líneas. Si crece, partir.
- `MEMORY.md` (memoria de Claude) NO reemplaza a estos docs. Son sistemas distintos.
- Antes de empezar, escanear: `ls docs/CONTEXT_*.md` y leer solo el del dominio.

## §4 Cuando un sub-agente cierra una tarea
Reportar siempre:
1. Archivos tocados.
2. `CONTEXT_*.md` actualizado (sí/no, y cuál).
3. Resultado de verificación en ngrok.

## §5 Higiene de git y worktree (reduce conflictos)

**Antes de empezar (quien orquesta la sesión):**
1. `git status` limpio. Restos de otra sesión → resolverlos ANTES (commitear, descartar o preguntar al usuario). Nunca arrancar una tarea encima de cambios ajenos sin entender qué son.
2. `git fetch` + main actualizado (`git checkout main && git pull`) **SIEMPRE antes de abrir una rama**. Lección 2026-07-12: una rama cortada de un main local viejo terminó en conflicto al mergear su PR (#33 chocó con los PRs #30-32 que ya estaban en `origin/main`).
3. Rama nueva desde ese main fresco (`feat/...`, `fix/...`, `docs/...`).

**Al terminar (todos los agentes):**
1. `git status` sin sorpresas: solo los archivos de la tarea. Nada suelto sin explicar en el reporte.
2. Temporales al scratchpad (fuera del repo); scripts one-shot a `TempScripts/`; nada nuevo en raíz.
3. Los sub-agentes NO commitean: editan, reportan, y el orquestador commitea.

**Antes de mergear un PR:**
1. `git fetch origin`. Si `origin/main` avanzó: mergear `origin/main` EN LA RAMA, resolver conflictos ahí, re-verificar que la app sigue sana (mínimo `python -c "import app"` + smoke en dev) y recién entonces mergear el PR.
2. Tras el merge: `git checkout main && git pull`, borrar la rama, y al desplegar sincronizar el clon PROD (`E:\Fondo`).
