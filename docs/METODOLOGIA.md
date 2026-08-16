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
- Antes de empezar, escanear: `ls docs/CONTEXT_*.md` y leer solo el del dominio.

## §3b Memoria de Claude vs docs del repo (regla 2026-07-19)

El conocimiento del proyecto vive en el **REPO** (`CLAUDE.md` + `docs/CONTEXT_*.md` + este archivo), NUNCA en la memoria local de Claude (`~/.claude/projects/.../memory/`). Razones:
- La memoria local NO viaja con el repo: los agentes de Mari no la ven, y otro entorno/máquina tampoco.
- No tiene backup: se pierde con la instalación de Claude o con la máquina.

Reglas:
1. **Información del proyecto y cómo trabajar en él** → mantener actualizados los `CONTEXT_*.md` (tabla del §1). Si un agente aprende algo útil del proyecto, va al doc del dominio, no a la memoria.
2. **Decisiones históricas** ("qué se hizo y cuándo") NO se guardan en ningún lado nuevo: la bitácora son los PRs y el git log.
3. La memoria local de Claude queda solo para lo estrictamente de esta máquina/instalación (si es que hay algo); ante la duda, va al repo.

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
0. **Permiso del usuario (obligatorio, regla 2026-07-13)**: ningún agente mergea a main por su cuenta. Abrir el PR, avisar al usuario qué hay para verificar en DEV, y esperar su autorización explícita. Lección: en la reestructuración del home se mergearon 7 PRs sin pedir permiso — el usuario quería verificar en DEV primero.
1. `git fetch origin`. Si `origin/main` avanzó: mergear `origin/main` EN LA RAMA, resolver conflictos ahí, re-verificar que la app sigue sana (mínimo `python -c "import app"` + smoke en dev) y recién entonces mergear el PR.
2. Tras el merge: `git checkout main && git pull`, **borrar la rama local Y la
   remota** (ver abajo), y al desplegar sincronizar el clon PROD (`E:\Fondo`).

**Borrar la rama mergeada — local Y remota (regla 2026-07-26):**

No alcanza con borrar la local. Lección: se acumularon 8 ramas mergeadas en
`origin` porque los agentes borraban solo la copia local (o ni eso), y la
redacción vieja de este punto decía "borrar la rama" sin aclarar cuál.

Lo más simple es que lo haga el merge en un paso:

```
gh pr merge <N> --merge --delete-branch
```

`--delete-branch` borra la remota y la local. Si el PR se mergeó por la web o
sin ese flag, limpiar a mano:

```
git push origin --delete <rama>
git branch -d <rama>          # -d, nunca -D: si se niega, la rama NO estaba mergeada
git fetch origin --prune      # barre las referencias locales muertas
```

Auditoría — listar ramas de `origin` ya contenidas en main (candidatas a borrar):

```
git fetch origin --prune
git branch -r --merged origin/main | grep -v 'origin/main$'
```

Nada se pierde: el historial queda en `main` y en el PR. Si `git branch -d` se
niega, la rama tiene commits propios — no forzar con `-D`, avisar al usuario.

**Excepción: no borrar una rama que sea base de un PR abierto (regla 2026-08-16).**

Estar mergeada a main NO alcanza como criterio. Antes de borrar, chequear que
nada cuelgue de ella:

```
gh pr list --state open --json number,baseRefName,headRefName
```

**Qué pasa si se borra igual** (lección de los PRs #66 → #67): GitHub **CIERRA**
el PR hijo en vez de reapuntarlo a main, y después queda trabado — no se puede
reabrir (le falta su rama base) ni cambiarle la base (está cerrado). Destrabarlo
obliga a recrear la rama base en el remoto:

```
git push origin <sha>:refs/heads/<rama-base>   # el sha sigue vivo: es ancestro del hijo
gh pr reopen <N-hijo>
gh pr edit <N-hijo> --base main
gh pr merge <N-hijo> --merge --delete-branch
git push origin --delete <rama-base>
```

**Cómo evitarlo — PRs encadenados.** Cuando un PR sale de la rama de otro (pasa
cuando los dos tocan el mismo archivo), antes de mergear el padre:

1. `gh pr edit <N-hijo> --base main` — reapuntar el hijo PRIMERO.
2. Recién ahí mergear el padre con `--delete-branch`.

Alternativa: mergear el padre **sin** `--delete-branch` y borrar la rama a mano
después de mergear el hijo.
