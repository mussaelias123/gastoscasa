# Contexto: Frontend (HTML / CSS / JS)

> Leer junto con `CLAUDE.md`. Para cambios visuales y de interactividad.

## Archivos del dominio
- `static/style.css` (~4650 líneas): estilos globales + variables.
- `static/app.js` (1164 líneas): interactividad cliente, AJAX, edición inline.
- `static/calendario.js` (826 líneas): módulo Calendario. Solo se carga en `/calendario` (vía `{% block scripts %}` de `base.html`, con el mismo `?v={{ static_version }}`).
- `templates/`:
  - `base.html` — layout. Header + nav van en `.site-topbar` (sticky, siempre visible al scrollear; `top:24px` si hay dev-banner). Todas extienden esto.
  - `index.html` — pantalla principal (saldos + form rápido + tabla).
  - `nuevo.html` — formulario completo de alta.
  - `editar.html` — edición completa de movimiento.
  - `resumen.html` — dashboard mensual (Chart.js), 5 secciones: saldos, sueldos (Elías vs Mari, evolución 6 meses), análisis de gastos, envíos, fijos.
  - `gastos_fijos.html` — gestión de fijos recurrentes y cuotas.
  - `settings.html` — ajustes. Layout 2 columnas (`.settings-layout`): izquierda scrollea (General, Paleta, Backups, Gastos fijos); derecha `.settings-aside` sticky con el Monitor de recursos (relojitos). Responsive: apila en 1 columna < 900px. **No incluye** ngrok/OAuth/estado-entorno (se manejan en `config.json`, fuera de la UI).
  - `calendario.html` — módulo Calendario (tareas del hogar): agenda Pendientes + calendario mensual + alta rápida + modales Completar / Editor / Todas / Confirmar. Inyecta `window.CAL_DATOS/CAL_AREAS/CAL_RESPONSABLES` (tojson) y carga `calendario.js`. El form de alta rápida es un `<form>` real (POST `/api/actividades/crear`, funciona sin JS, pero pierde el date picker: el input queda de texto libre validado ISO por el backend). Desktop ≥900px: `body.cal-body` (la agrega el JS) fija alto = viewport, sin scroll de página. Fechas: los 3 date inputs (`cal-qa-ultima`, `cal-comp-fecha`, `cal-ed-ultima`/`cal-ed-limite`) son `type="text"` + flatpickr (mismo patrón que `inicializarFechaHoy()` de `app.js`), no `<input type="date">` nativo: valor real ISO `Y-m-d` vía `altInput`, display `d/m/Y`. `cal-comp-fecha` tiene `maxDate: 'today'`.
  - `login.html` — pantalla pre-OAuth.
  - `404.html`, `405.html` — errores.

## Paleta de colores (regla NO negociable)

**Config-driven desde Fase 1 de dark mode.** Los 22 colores base se guardan en `config.json` como `paleta_light` y `paleta_dark`. `base.html` los inyecta en un `<style>` en el `<head>` antes del stylesheet, así:

```css
:root { --color-acento: #4f46e5; ... }          /* desde cfg.paleta_light */
html[data-theme="dark"] { --color-acento: #6366f1; ... }  /* desde cfg.paleta_dark */
```

`static/style.css → :root` sigue definiendo los mismos colores como **fallback** (por si config.py no carga). Regla intacta: **NUNCA usar colores literales**. Siempre `var(--color-...)`.

**Filosofía de grises (regla de diseño):** Chrome estructural/decorativo (botones, nav, headers, bordes, fondos) usa solo `--color-deco-1..4`. Los colores llamativos (`acento`, `exito`, `peligro`, `persona-*`, `moneda-*`) se reservan **exclusivamente** para elementos que transmiten información (badges de tipo, persona, moneda, estados de saldo). No hay aliases: cada regla CSS referencia directamente la variable que necesita.

> **Excepción — botones de acción semánticos:** los botones que disparan una acción importante pueden usar color: `.btn-peligro` (rojo) para destructivas (ej. Restaurar backup) y `.btn-acento` (indigo) para la acción primaria de una sección (ej. Crear backup). Motivo práctico además del semántico: `.btn-primario` usa `--color-deco-2`, que en dark (`#1e293b`) coincide con `--color-superficie` y queda **invisible** sobre una tarjeta. NO revertir `.btn-acento` a `.btn-primario` "para cumplir la filosofía": reintroduce el bug.

**Dark mode:** `document.documentElement.dataset.theme = 'dark'` activa la paleta oscura. Un script inline en `base.html` (antes del stylesheet) lee `localStorage.getItem('tema')` y setea `data-theme` antes del primer paint, evitando parpadeo. Default: `'light'`.

**Toggle Light/Dark:** botón `#theme-toggle` en `.site-header` (absoluto a la izquierda), visible en todas las páginas. Icono `#theme-icon` = `🌙` en light, `☀` en dark. JS: `inicializarToggleTema()` (en `app.js`) lee `dataset.theme`, pinta el icono inicial, y al click alterna `dataset.theme`, guarda `localStorage.setItem('tema', ...)`, repinta el icono, y llama `window._refrescarColoresSelects()` para actualizar los fondos/textos de los selects de persona y moneda con los colores del nuevo tema. El modo activo es por dispositivo (localStorage); los valores de color son compartidos (config.json).

**UI de edición:** en `settings.html → sección "Paleta de colores"` hay **una sola** `<table>` con columnas Nombre · Uso · Light · Dark. Jinja itera `paleta_meta` (de `app.py`) y agrupa las filas con encabezados por categoría (Marca, Superficies, Estados, Personas, Monedas, Decorativos) vía un dict `grupos` + `namespace` en la plantilla. Cada fila tiene dos `<input type="color">` (`data-tema="light"` y `data-tema="dark"`, `data-key`), tomando valor de `cfg.paleta_light[key]` / `cfg.paleta_dark[key]`. El hex **no** se muestra como texto: se ve solo en el picker. Botón "Guardar paleta" → `POST /api/paleta` (JSON con ambas paletas, valida hex, escribe `config.json`). Al recargar, `base.html` re-inyecta los valores. Cero hex hardcodeado en el HTML.

**Monitor de recursos (relojitos):** panel sticky en `.settings-aside`. 4 gauges SVG (CPU app, RAM app, CPU sistema, RAM sistema) dibujados con dos `<circle>` (`.gauge-bg` + `.gauge-arc` con `stroke-dasharray`/`stroke-dashoffset`). JS `fetchMetrics()` (en `settings.html`) hace `GET /api/metrics` cada 3s y `setGauge()` ajusta arco + valor + color por umbral (verde/amarillo/rojo). Sin historización: solo el valor actual. Pie con PID, estado "En ejecución" y cotización OK/Falló.

Variables actuales (al modificar, actualizar también `config.py DEFAULTS`, `app.py PALETA_META` y la página Settings → Paleta):

| Variable                  | Uso semántico                                  |
|---------------------------|------------------------------------------------|
| `--color-acento`          | Botones primarios, links, focus ring           |
| `--color-acento-oscuro`   | Hover de botones, fondo nav                    |
| `--color-fondo`           | Fondo general                                  |
| `--color-superficie`      | Tarjetas, inputs, modales                      |
| `--color-texto`           | Texto principal                                |
| `--color-texto-muted`     | Texto secundario                               |
| `--color-texto-invertido` | Texto sobre botones/badges de color (acento, éxito, peligro, badges responsable) |
| `--color-borde`           | Bordes, separadores                            |
| `--color-exito`           | Ingresos, OK, semáforo verde                   |
| `--color-alerta`          | Pendiente, advertencia                         |
| `--color-peligro`         | Eliminar, error, saldo negativo                |
| `--color-exito-suave`     | Fondo badge OK                                 |
| `--color-alerta-suave`    | Fondo badge alerta                             |
| `--color-peligro-suave`   | Fondo badge error                              |
| `--color-persona-elias`   | Identificador visual Elías                     |
| `--color-persona-mari`    | Identificador visual Mari                      |
| `--color-moneda-ars`      | Badge AR$, gauge total ARS                     |
| `--color-moneda-usd`      | Badge USD, gauge total USD                     |
| `--color-deco-1..4`       | Grises decorativos: nav, botones, bordes estructurales |

No-color (también en `:root`, NO editables desde Settings): `--fuente-principal`, `--radio-borde`, `--espaciado-base`, `--sombra-card`, `--sombra-focus`, `--sombra-modal`, `--overlay-modal` (fondo de overlays de modal).

## Mapa de secciones de `style.css` (línea inicial)

57 banner DEV · 79 variables · 147 reset · 193 layout · 211 header · 283 nav · 326 footer · 347 page-header · 364 botones · 442 tabla gastos · 529 badges categoría · 557 sin-datos · 575 forms · 630 resumen · 735 tarjeta saldo · 761 carga rápida · 852 grilla saldos · 907 filtros · 986 badges tipo · 1010 badges persona · 1026 badges moneda · 1055 dashboard · 1528 edición inline · 1619 envío · 1690 badge envío · 1736 toasts · 1802 banner primer inicio · 1822 banner éxito · 1836 settings · 1969 monitor recursos · 2091 paginación · 2147 form rápido · 2163 responsive mobile · 2299 tabla saldos · 2364 nav mes · 2417 checklist fijos · 2531 gastos_fijos · 2606 git backup · 2691 fijos en settings · 2758 layout desktop · 2796 tarjeta saldos · 2860 movimientos card · 2968 select filtro · 2992 gauges · 3096 paleta settings · 3162 cotización settings · 3372 **settings v2** (layout 2 col sticky · cot-box · paleta tabla única agrupada · backups · fijos chips con switch · relojitos/gauges monitor) · 3796 **calendario** (prefijo `cal-`: paneles, agenda, grilla mensual, alta rápida, switch, modales, tabla Todas, toasts `cal-toast-*` · desktop ≥900px: 2 col `minmax(0,1fr) 416px`, `body.cal-body` alto 100dvh sin scroll de página, scroll interno en agenda/detalle).

## Funciones JS principales (`static/app.js`)

| Función                         | Propósito                                            |
|---------------------------------|------------------------------------------------------|
| `llenarSelectCategorias()`      | Pobla `<select>` según tipo                          |
| `inicializarCategorias()`       | Bind cambio de tipo                                  |
| `actualizarDescripcionSegunCategoria()` | Auto-llena descripción                       |
| `inicializarFechaHoy()`         | flatpickr + default hoy                              |
| `inicializarFormatoMonto()`     | Separadores miles en input                           |
| `inicializarPersona()`          | Selector visual persona                              |
| `inicializarColoresDinamicos()` | Lee `--color-*` del tema activo; calcula texto claro/oscuro con `textForBg()` (WCAG L>0.35 → oscuro); expone `window._refrescarColoresSelects` |
| `inicializarToggleTema()`       | Botón header Light/Dark; persiste en localStorage; llama `_refrescarColoresSelects()` al cambiar tema |
| `resaltarNavActual()`           | Marca link nav activo                                |
| `initSelectVista()`             | Cambio de vista de tabla                             |
| `initFiltros()` / `initOrden()` | Filtros y ordenamiento de tabla                      |
| `initEdicionInline()`           | Doble click → editar fila in-place                   |
| `activarEdicion()` / `guardarEdicion()` / `cancelarEdicion()` | Ciclo edición |
| `actualizarSaldos()`            | Refresca las 6 celdas de saldos en DOM               |
| `actualizarGauges()`            | Refresca los 3 gauges (arcos/textos/leyendas) sin recargar |
| `inicializarSaldosFecha()`      | Date picker en tarjeta saldos; `fetch /api/saldos` → saldos+gauges a una fecha |
| `crearFilaMovimiento()`         | Renderea fila tras AJAX                              |
| `mostrarToast()`                | Toast confirmación                                   |
| `initFormAjax()`                | Submit sin recarga                                   |

`var ordenarTablaFn` expuesta para que `initFormAjax` reordene tras insertar.

## Funciones JS del módulo Calendario (`static/calendario.js`)

Todo en una IIFE: no expone globales ni pisa `fmtFecha`/`mostrarToast` de app.js. Estado local = `window.CAL_DATOS`; cada mutación AJAX devuelve el payload completo fresco y se re-renderiza todo. El estado/próxima fecha NO se recalcula acá (viene del server).

| Función                          | Propósito                                              |
|----------------------------------|--------------------------------------------------------|
| `sumarIntervalo()`               | Espejo de `_act_sumar_intervalo` (clamp fin de mes) — solo para el preview del modal Completar |
| `fmtFecha/fmtMesAnio/fmtIntervalo/textoRelativo` | Formatos es-AR; clave ASCII `anios` → "años" |
| `renderAgenda/renderCalendario/renderDetalle/renderTodas` | Re-render de cada bloque desde `DATOS` |
| `mapaPorDia()`                   | iso → puntos: vencida/proxima/aldia (próxima fecha) + `hecha` (historial) |
| `abrirCompletar/abrirEditor/abrirTodas` + `guardar*` | Modales y mutaciones (`postAccion()` = fetch + `X-Requested-With`) |
| `toast()`                        | Toast propio: `.toast` base + `.cal-toast-ok/info/error` en `#cal-toast-container` |

## Reglas específicas frontend
1. **Cero hardcode de color**. Solo `var(--color-...)`. Cero aliases: cada regla CSS nombra la variable real que necesita. Excepciones: (a) valores en `style.css :root` son fallbacks legítimos; (b) `login.html` usa hardcode (standalone pre-auth, sin config); (c) `.dash-toggle-btn.activo { color: #ffffff }` intencional (4.47:1 en dark). **Filosofía**: solo deco-1..4 para chrome estructural; colores llamativos únicamente para información.
2. Templates extienden `base.html` con bloques `{% block titulo %}` y `{% block contenido %}`.
3. AJAX usa header `X-Requested-With: XMLHttpRequest`. Si está, backend responde JSON.
4. Cache busting: `?v={{ static_version }}` en `<link>` y `<script>` (versión = mtime del archivo).
5. flatpickr y CDN externos: solo lo ya importado en `base.html`. No agregar libs sin acordar.
6. Mobile breakpoint: `< 768px` (sección 2163 de `style.css`). Desktop dos columnas: `>= 900px` (2758).

## Al modificar este dominio, actualizar:
- Tabla de paleta si se agrega/renombra variable.
- Mapa de secciones si se agrega un bloque nuevo grande en CSS.
- Tabla de funciones JS si se agrega función pública.
- Lista de templates si se agrega/elimina archivo.
