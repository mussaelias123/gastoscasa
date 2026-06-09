# Contexto: Frontend (HTML / CSS / JS)

> Leer junto con `CLAUDE.md`. Para cambios visuales y de interactividad.

## Archivos del dominio
- `static/style.css` (3227 líneas): estilos globales + variables.
- `static/app.js` (1164 líneas): interactividad cliente, AJAX, edición inline.
- `templates/`:
  - `base.html` — layout. Header + nav van en `.site-topbar` (sticky, siempre visible al scrollear; `top:24px` si hay dev-banner). Todas extienden esto.
  - `index.html` — pantalla principal (saldos + form rápido + tabla).
  - `nuevo.html` — formulario completo de alta.
  - `editar.html` — edición completa de movimiento.
  - `resumen.html` — dashboard mensual (Chart.js), 5 secciones: saldos, sueldos (Elías vs Mari, evolución 6 meses), análisis de gastos, envíos, fijos.
  - `gastos_fijos.html` — gestión de fijos recurrentes y cuotas.
  - `settings.html` — configuración + paleta + backups de la base de datos.
  - `login.html` — pantalla pre-OAuth.
  - `404.html`, `405.html` — errores.

## Paleta de colores (regla NO negociable)

**Config-driven desde Fase 1 de dark mode.** Los 21 colores base se guardan en `config.json` como `paleta_light` y `paleta_dark`. `base.html` los inyecta en un `<style>` en el `<head>` antes del stylesheet, así:

```css
:root { --color-acento: #4f46e5; ... }          /* desde cfg.paleta_light */
html[data-theme="dark"] { --color-acento: #6366f1; ... }  /* desde cfg.paleta_dark */
```

`static/style.css → :root` sigue definiendo los mismos colores como **fallback** (por si config.py no carga). Regla intacta: **NUNCA usar colores literales**. Siempre `var(--color-...)`.

**Filosofía de grises (regla de diseño):** Chrome estructural/decorativo (botones, nav, headers, bordes, fondos) usa solo `--color-deco-1..4`. Los colores llamativos (`acento`, `exito`, `peligro`, `persona-*`, `moneda-*`) se reservan **exclusivamente** para elementos que transmiten información (badges de tipo, persona, moneda, estados de saldo). No hay aliases: cada regla CSS referencia directamente la variable que necesita.

> **Excepción — botones de acción semánticos:** los botones que disparan una acción importante pueden usar color: `.btn-peligro` (rojo) para destructivas (ej. Restaurar backup) y `.btn-acento` (indigo) para la acción primaria de una sección (ej. Crear backup). Motivo práctico además del semántico: `.btn-primario` usa `--color-deco-2`, que en dark (`#1e293b`) coincide con `--color-superficie` y queda **invisible** sobre una tarjeta. NO revertir `.btn-acento` a `.btn-primario` "para cumplir la filosofía": reintroduce el bug.

**Dark mode:** `document.documentElement.dataset.theme = 'dark'` activa la paleta oscura. Un script inline en `base.html` (antes del stylesheet) lee `localStorage.getItem('tema')` y setea `data-theme` antes del primer paint, evitando parpadeo. Default: `'light'`.

**Toggle Light/Dark:** botón `#theme-toggle` en `.site-header` (absoluto a la izquierda), visible en todas las páginas. Icono `#theme-icon` = `🌙` en light, `☀` en dark. JS: `inicializarToggleTema()` (en `app.js`) lee `dataset.theme`, pinta el icono inicial, y al click alterna `dataset.theme`, guarda `localStorage.setItem('tema', ...)`, repinta el icono, y llama `window._refrescarColoresSelects()` para actualizar los fondos/textos de los selects de persona y moneda con los colores del nuevo tema. El modo activo es por dispositivo (localStorage); los valores de color son compartidos (config.json).

**UI de edición:** en `settings.html → sección "Paleta de colores"` hay dos `<table>` (Light Mode y Dark Mode) generadas por Jinja iterando `cfg.paleta_light` / `cfg.paleta_dark` con `paleta_meta` (lista pasada desde `app.py`). Cada fila: muestra | nombre | `--variable` | uso | `<input type="color">`. Botón "Guardar paleta" → `POST /api/paleta` (JSON con ambas paletas, valida hex, escribe `config.json`). Al recargar, `base.html` re-inyecta los valores. Cero hex hardcodeado en el HTML.

Variables actuales (al modificar, actualizar también `config.py DEFAULTS`, `app.py PALETA_META` y la página Settings → Paleta):

| Variable                  | Uso semántico                                  |
|---------------------------|------------------------------------------------|
| `--color-acento`          | Botones primarios, links, focus ring           |
| `--color-acento-oscuro`   | Hover de botones, fondo nav                    |
| `--color-fondo`           | Fondo general                                  |
| `--color-superficie`      | Tarjetas, inputs, modales                      |
| `--color-texto`           | Texto principal                                |
| `--color-texto-muted`     | Texto secundario                               |
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

No-color (también en `:root`): `--fuente-principal`, `--radio-borde`, `--espaciado-base`, `--sombra-card`, `--sombra-focus`.

## Mapa de secciones de `style.css` (línea inicial)

57 banner DEV · 79 variables · 147 reset · 193 layout · 211 header · 283 nav · 326 footer · 347 page-header · 364 botones · 442 tabla gastos · 529 badges categoría · 557 sin-datos · 575 forms · 630 resumen · 735 tarjeta saldo · 761 carga rápida · 852 grilla saldos · 907 filtros · 986 badges tipo · 1010 badges persona · 1026 badges moneda · 1055 dashboard · 1528 edición inline · 1619 envío · 1690 badge envío · 1736 toasts · 1802 banner primer inicio · 1822 banner éxito · 1836 settings · 1969 monitor recursos · 2091 paginación · 2147 form rápido · 2163 responsive mobile · 2299 tabla saldos · 2364 nav mes · 2417 checklist fijos · 2531 gastos_fijos · 2606 git backup · 2691 fijos en settings · 2758 layout desktop · 2796 tarjeta saldos · 2860 movimientos card · 2968 select filtro · 2992 gauges · 3096 paleta settings · 3162 cotización settings.

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
