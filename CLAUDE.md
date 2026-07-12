# Gastos Casa — Guía maestra para agentes IA

> **Este archivo es el ÍNDICE.** No contiene detalle de código.
> Para profundizar en un dominio, leer el `docs/CONTEXT_*.md` correspondiente.
> Para tareas especializadas, invocar el sub-agente apropiado en `agents/`.

---

## 1. Modelo de negocio (mínimo indispensable)

- App personal de finanzas para 2 personas: **Elías** y **Mari**.
- 2 monedas: **AR$** (pesos argentinos) y **USD** (dólares).
- 4 saldos primarios: `elias_ars`, `elias_usd`, `mari_ars`, `mari_usd`.
- Saldos **calculados dinámicamente** desde tabla `movimientos` (no almacenados).
- Movimiento = `ingreso | gasto | cambio` (cambio genera 2 filas: salida + entrada).
- Cada movimiento guarda equivalente en USD (`monto_usd`) usando cotización oficial vigente al insertar.

---

## 2. Mapa de archivos por dominio

| Dominio       | Archivos principales                                  | Doc de contexto                  |
|---------------|--------------------------------------------------------|----------------------------------|
| Backend rutas | `app.py`                                               | `docs/CONTEXT_BACKEND.md`        |
| Base de datos | `database.py`, `gastos.db`                             | `docs/CONTEXT_DB.md`             |
| Cotización    | `cotizacion.py`, `tests/test_cotizacion.py`            | `docs/CONTEXT_COTIZACION.md`     |
| Auth Google   | `auth.py`, `templates/login.html`                      | `docs/CONTEXT_AUTH.md`           |
| Config        | `config.py`, `config.json`, `config.example.json`      | `docs/CONTEXT_CONFIG.md`         |
| Frontend      | `static/style.css`, `static/app.js`, `static/calendario.js`, `static/lactancia.js`, `static/rutina.js`, `static/rutina-actividades.js`, `templates/*.html`| `docs/CONTEXT_FRONTEND.md`       |
| Notificaciones| `app.py` (providers + `/api/notificaciones`), `static/app.js` (`window.Notif`), `templates/base.html` (campana/panel) | `docs/CONTEXT_NOTIFICATIONS.md`  |
| Deploy/serv   | NSSM (`E:\Fondo\nssm.exe`, fuera de git), ngrok, `logs/`, `logutil.py` | `docs/CONTEXT_DEPLOY.md` |
| Scripts ad-hoc| `TempScripts/`                                         | (one-shot, no producción)        |

> **Dev / Prod**: `E:\Fondo` = producción (servicio Windows `GastosCasa` vía NSSM,
> arranca solo). `E:\FondoDev` = desarrollo, se corre a mano con `python app.py`.
> El proyecto **no se compila**: NSSM solo envuelve `python app.py`.

---

## 3. Tabla "tarea → contexto a leer"

| Tipo de tarea                          | Leer obligatorio                                              | Sub-agente sugerido     |
|----------------------------------------|---------------------------------------------------------------|-------------------------|
| Cambio visual (color, layout, badge)   | `CLAUDE.md` + `CONTEXT_FRONTEND.md`                           | `frontend-dev`          |
| Nueva ruta o endpoint Flask            | `CLAUDE.md` + `CONTEXT_BACKEND.md` + `CONTEXT_DB.md`          | `backend-dev`           |
| Cambio de esquema, query o saldo       | `CLAUDE.md` + `CONTEXT_DB.md`                                 | `db-engineer`           |
| Bug en cotización USD                  | `CLAUDE.md` + `CONTEXT_COTIZACION.md`                         | `cotizacion-maintainer` |
| Login, OAuth, sesión                   | `CLAUDE.md` + `CONTEXT_AUTH.md`                               | `auth-maintainer`       |
| Build, instalación, servicio Windows   | `CLAUDE.md` + `CONTEXT_DEPLOY.md`                             | (manual)                |
| Verificación final en navegador        | `CLAUDE.md` + `CONTEXT_DEPLOY.md` (sección ngrok)             | `verifier`              |
| Script one-shot (backfill, migración)  | `CLAUDE.md` + `CONTEXT_DB.md`                                 | `db-engineer`           |
| Módulo Lactancia (banco de leche)      | `CLAUDE.md` + `CONTEXT_BACKEND.md` + `CONTEXT_DB.md` + `CONTEXT_FRONTEND.md` (+ `CONTEXT_CONFIG.md` si tocás parámetros) | según capa |
| Módulo Rutina (rutina diaria de León)  | `CLAUDE.md` + `CONTEXT_FRONTEND.md` (la lógica y las definiciones viven en `static/rutina.js`) + `CONTEXT_BACKEND.md`/`CONTEXT_DB.md` si tocás los ajustes persistidos | según capa |
| Notificaciones (sumar provider de un módulo, campana, panel) | `CLAUDE.md` + `CONTEXT_NOTIFICATIONS.md` (+ `CONTEXT_BACKEND.md` o `CONTEXT_FRONTEND.md` según la capa que toques) | según capa |

**Regla**: si la tarea entra en una sola fila, **no leer los demás `CONTEXT_*.md`**. Eso es el ahorro.

---

## 4. Reglas globales (NO negociables)

1. **Paleta de colores**: todos los colores se referencian con `var(--color-...)`. **Cero hardcode** (`#fff`, `rgb(...)`, nombres de color). Arquitectura:
   - **Valores runtime**: `config.json → paleta_light / paleta_dark` (23 vars c/u). `base.html` los inyecta en `<style>` en el `<head>` como `:root { ... }` y `html[data-theme="dark"] { ... }`.
   - **Fallbacks**: `static/style.css → :root` define los mismos valores por si `config.json` no carga.
   - **Excepciones documentadas** (hardcode intencional): `login.html` (página standalone sin acceso a config); `.dash-toggle-btn.activo { color: #ffffff }` (blanco intencional: mejor contraste que `var(--color-superficie)` en dark mode, 4.47:1 vs 3.27:1).
   - Definición y leyenda en página Settings → Paleta.
2. **Verificación**: tras cualquier cambio en dev, ingresar a `http://localhost:5050/` con conector `Claude in Chrome` y confirmar que la app no se rompe. El dominio ngrok (`https://miller-unventured-courtly.ngrok-free.dev/`) es SOLO producción — no probar cambios de dev ahí. Cambios de rutas requieren reiniciar `python app.py`. Detalle en `docs/CONTEXT_DEPLOY.md`.
3. **Scripts one-shot** (backfills, migraciones manuales, utilidades) → carpeta `TempScripts/`, nunca en raíz ni en `scripts/`.
4. **Estilo de respuesta** (preferencia del usuario): frases 3-6 palabras, sin filler, sin artículos, español básico.
5. **Sesión iniciada**: la cuenta del usuario ya está logueada en ngrok. Si la página pide login, **detenerse y avisar**.

---

## 5. Metodología de actualización de contexto (CRÍTICO)

> **Después de modificar el programa, actualizar el contexto correspondiente.**
> Si no se actualiza, los próximos agentes trabajarán con info obsoleta y romperán cosas.
>
> Detalle completo y tabla exhaustiva: `docs/METODOLOGIA.md`.

Checklist obligatorio post-cambio:

- ¿Modifiqué una **ruta o endpoint** en `app.py`? → actualizar `docs/CONTEXT_BACKEND.md` (sección rutas).
- ¿Modifiqué el **esquema** o agregué una columna en `database.py`? → actualizar `docs/CONTEXT_DB.md` (sección esquema).
- ¿Cambié la **paleta** o agregué variable de color? → actualizar `docs/CONTEXT_FRONTEND.md` (sección paleta) y página Settings.
- ¿Agregué un **archivo nuevo** o moví uno? → actualizar tabla del punto 2 de este `CLAUDE.md`.
- ¿Agregué una **regla nueva** acordada con el usuario? → punto 4 de este `CLAUDE.md` o el `CONTEXT_*.md` del dominio.
- ¿Agregué un **flujo o ruta del frontend**? → actualizar `docs/CONTEXT_FRONTEND.md` (sección templates).
- ¿Agregué dependencia? → actualizar `requirements.txt` y `docs/CONTEXT_DEPLOY.md`.

**Cómo actualizar**: editar el `.md` correspondiente en la sección que ya existe. Mantener cada `CONTEXT_*.md` por debajo de 150 líneas. Si crece más, partir en sub-secciones.

**Auditoría rápida**: `grep -rn "TODO contexto" docs/` debe estar vacío.

---

## 6. Sub-agentes disponibles

Ver `agents/`. Cada agente tiene:
- Lista cerrada de archivos/carpetas que puede leer.
- Misión específica.
- Instrucción de actualizar el `CONTEXT_*.md` que le corresponde al terminar.

Lista actual: `frontend-dev`, `backend-dev`, `db-engineer`, `cotizacion-maintainer`, `auth-maintainer`, `verifier`.

---

## 7. Stack técnico (resumen)

Python 3.13 + Flask + SQLite + Authlib (Google OAuth) + pyngrok + flatpickr (front).
Producción: servicio Windows vía NSSM, expuesto por túnel ngrok con dominio fijo.
