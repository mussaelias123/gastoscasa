# Contexto: Frontend (HTML / CSS / JS)

> Leer junto con `CLAUDE.md`. Para cambios visuales y de interactividad.

## Archivos del dominio
- `static/style.css` (3227 líneas): estilos globales + variables.
- `static/app.js` (1164 líneas): interactividad cliente, AJAX, edición inline.
- `templates/`:
  - `base.html` — layout (header, nav, footer). Todas extienden esto.
  - `index.html` — pantalla principal (saldos + form rápido + tabla).
  - `nuevo.html` — formulario completo de alta.
  - `editar.html` — edición completa de movimiento.
  - `resumen.html` — dashboard mensual con gauges y métricas.
  - `gastos_fijos.html` — gestión de fijos recurrentes y cuotas.
  - `settings.html` — configuración + paleta + git backup.
  - `login.html` — pantalla pre-OAuth.
  - `404.html`, `405.html` — errores.

## Paleta de colores (regla NO negociable)

**Config-driven desde Fase 1 de dark mode.** Los 21 colores base se guardan en `config.json` como `paleta_light` y `paleta_dark`. `base.html` los inyecta en un `<style>` en el `<head>` antes del stylesheet, así:

```css
:root { --color-acento: #4f46e5; ... }          /* desde cfg.paleta_light */
html[data-theme="dark"] { --color-acento: #6366f1; ... }  /* desde cfg.paleta_dark */
```

`static/style.css → :root` sigue definiendo los mismos colores como **fallback** (por si config.py no carga). Regla intacta: **NUNCA usar colores literales**. Siempre `var(--color-...)`.

**Dark mode:** `document.documentElement.dataset.theme = 'dark'` activa la paleta oscura. Un script inline en `base.html` (antes del stylesheet) lee `localStorage.getItem('tema')` y setea `data-theme` antes del primer paint, evitando parpadeo. Default: `'light'`.

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
| `--color-deco-1..4`       | Grises decorativos (estructural)               |
| `--color-primario(-hover)`| Alias → deco-2 / deco-1                        |
| `--color-secundario`      | Alias → deco-3                                 |
| `--color-fondo-card`      | Alias → superficie                             |
| `--color-texto-suave`     | Alias → texto-muted                            |

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
| `inicializarColoresDinamicos()` | Lee `--color-*` y los aplica via JS                  |
| `resaltarNavActual()`           | Marca link nav activo                                |
| `initSelectVista()`             | Cambio de vista de tabla                             |
| `initFiltros()` / `initOrden()` | Filtros y ordenamiento de tabla                      |
| `initEdicionInline()`           | Doble click → editar fila in-place                   |
| `activarEdicion()` / `guardarEdicion()` / `cancelarEdicion()` | Ciclo edición |
| `actualizarSaldos()`            | Refresca saldos en DOM                               |
| `crearFilaMovimiento()`         | Renderea fila tras AJAX                              |
| `mostrarToast()`                | Toast confirmación                                   |
| `initFormAjax()`                | Submit sin recarga                                   |

`var ordenarTablaFn` expuesta para que `initFormAjax` reordene tras insertar.

## Reglas específicas frontend
1. **Cero hardcode de color**. Solo `var(--color-...)`. Auditable con `grep -nE "#[0-9a-fA-F]{3,6}\b|rgb\(" static/style.css | grep -v "^[^:]*:.*var(--"`.
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
