# Contexto: Notificaciones

> Leer junto con `CLAUDE.md`. Para tareas sobre la campana de notificaciones
> del header, o para sumar notificaciones desde un módulo nuevo.

## 1. Qué es el dominio

Sistema de notificaciones genérico y extensible. Reemplaza los badges de nav
por módulo (ej. el viejo `lac_badge` de Lactancia) por UNA campana en el
header, con un panel/drawer a la derecha que lista los ítems de TODOS los
módulos juntos, ordenados por severidad. Cualquier módulo de negocio puede
sumar sus propias notificaciones sin tocar la campana ni los demás módulos:
solo escribe un "provider" (función que arma sus ítems) y lo registra.

## 2. Contrato JSON del ítem (CERRADO — no agregar ni quitar claves)

| Clave           | Tipo | Notas                                                              |
|------------------|------|---------------------------------------------------------------------|
| `modulo`         | str  | Slug del módulo origen. Ej. `"lactancia"`.                          |
| `modulo_nombre`  | str  | Nombre legible. Ej. `"Lactancia"`.                                   |
| `icono`          | str  | Emoji del módulo. Ej. `"🍼"`.                                        |
| `titulo`         | str  | Título corto del ítem. Ej. `"Partida vencida"`.                     |
| `detalle`        | str  | Línea descriptiva. Ej. `"Freezer · 180 ml · venció hace 2 días"`.   |
| `url`            | str  | A dónde navega el click. Ej. `"/lactancia"`.                         |
| `severidad`      | str  | `"peligro"` \| `"alerta"` \| `"info"`.                               |

`severidad` → variable de paleta (el frontend la mapea; ver `CONTEXT_FRONTEND.md`):

| `severidad` | Variable de paleta |
|--------------|----------------------|
| `peligro`    | `--color-peligro`    |
| `alerta`     | `--color-alerta`     |
| `info`       | `--color-acento`     |

Ejemplo real (provider Lactancia, partida vencida):
```json
{ "modulo": "lactancia", "modulo_nombre": "Lactancia", "icono": "🍼",
  "titulo": "Partida vencida", "detalle": "Freezer · 180 ml · venció hace 2 días",
  "url": "/lactancia", "severidad": "peligro" }
```

## 3. Backend (`app.py`)

- **Registry `NOTIF_PROVIDERS`**: lista de funciones sin argumentos; cada una
  devuelve `list[dict]` con el contrato de la sección 2.
- **`_notificaciones()`**: agrega TODOS los providers de `NOTIF_PROVIDERS`.
  Cada llamada a un provider corre en su propio try/except — si uno falla,
  se loguea `AVISO:` (vía `log()` de `logutil.py`, NUNCA `print()` directo) y
  se sigue con los demás; un módulo roto nunca tumba la campana. Ordena el
  resultado final por severidad: `peligro` → `alerta` → `info` (sort
  estable: respeta el orden interno de cada provider y, dentro de una misma
  severidad, el orden de `NOTIF_PROVIDERS` entre módulos distintos).
- **Ruta `GET /api/notificaciones`**: solo lectura, sin parámetros. Devuelve
  `{'ok': True, 'total': int, 'items': [...]}`. Misma protección de auth que
  el resto de las rutas (middleware `before_request` de `auth.py`; sin
  decorador propio, igual que `/api/lactancia` y `/api/actividades`).
- **Context processor `inject_notif_badge`**: expone `notif_badge`
  (`= len(_notificaciones())`) a TODOS los templates, con try/except → 0 (un
  fallo jamás rompe un render). Reemplaza al viejo
  `inject_lactancia_badge`/`lac_badge` (eliminados junto con
  `_lac_badge_count()`, que quedó huérfana).

## 4. Providers actuales: Lactancia

`_notif_lactancia()` — un ítem por partida ABIERTA (sin `motivo_cierre`) en
estado `vencida` o `vence_pronto`. Reusa `_lac_params()` y `_lac_enriquecer()`
tal cual (NUNCA reimplementa el cálculo de vencimiento, que vive solo en los
helpers `_lac_*` — ver `CONTEXT_BACKEND.md`). Mapeo: `vencida` → severidad
`peligro`, título "Partida vencida"; `vence_pronto` → severidad `alerta`,
título "Partida por vencer". `detalle` combina ubicación + volumen + tiempo
relativo: freezer en días ("vence en 3 días" / "venció hace 2 días" / "vence
hoy" si 0, singular/plural correcto), heladera en horas ("vence en 5 h"); una
heladera vencida muestra solo "venció" (sin cantidad de horas, ya que
`horas_restantes` redondea hacia el pasado y podría subestimar cuánto hace
que venció). Orden interno: vencidas primero, luego por vencer; dentro de
cada grupo, por vencimiento ascendente.

`_notif_recordatorio_bajar()` — recordatorio nocturno de bajar bolsitas del
freezer a la heladera (para el día siguiente de jardín). Devuelve 0 o 1 ítem:
icono `🌙`, severidad `alerta`, título "Bajá bolsitas para mañana". La condición
la decide `_lac_recordatorio_pendiente()` (ver `CONTEXT_BACKEND.md`): activo +
ya pasó la hora configurada + hay leche ABIERTA en el freezer + todavía no se
bajó ninguna hoy. Se **autolimpia** al bajar una bolsa (nace una partida
`descongelada` con `cargada` de hoy). Es un aviso IN-APP (campana + banner en
`/lactancia`): el push al celular con la app cerrada requiere una app
instalable (PWA/nativa), fuera del alcance de esta versión.

`NOTIF_PROVIDERS = [_notif_lactancia, _notif_recordatorio_bajar]`.

## 5. Checklist — cómo sumar notificaciones desde un módulo nuevo

1. Escribir `_notif_<modulo>()` en `app.py`: función sin argumentos que arma
   y devuelve una lista de ítems con el contrato de la sección 2 (mismas 7
   claves, ni una más ni una menos).
2. Agregarla a `NOTIF_PROVIDERS` (una línea). Listo — no hay que tocar la
   ruta, el context processor, ni el frontend: la campana la muestra sola.
3. NO recalcular lógica de estado/vencimiento que ya exista en helpers del
   módulo (mismo espíritu que `_lac_*`): el provider solo LEE y da formato,
   no decide.
4. Si el provider puede fallar (ej. depende de una API externa), dejar que
   la excepción suba: `_notificaciones()` ya la aísla con try/except + log
   `AVISO:`. No hace falta duplicar ese try/except adentro del provider.
5. En el JS del módulo nuevo, llamar `window.Notif.refrescar()` después de
   cualquier mutación (alta/edición/borrado) para que la campana se
   actualice sin esperar el próximo render de página.

## Frontend

Campana `#notif-toggle` en `.header-acciones` (header, ver `CONTEXT_FRONTEND.md`)
con pill `#notif-badge` (server-rendered vía `notif_badge`). Al abrirla se
despliega el drawer derecho `#notif-panel` y su lista `#notif-lista`.

**`window.Notif.refrescar()`** (en `app.js`) — API pública del estándar. Hace
`fetch('/api/notificaciones', {headers:{'X-Requested-With':'XMLHttpRequest'}})`,
lee `{ok, total, items}`, sincroniza el badge (crea/actualiza/borra `#notif-badge`
según `total`) y re-renderiza `#notif-lista`. Los nodos se arman con
`createElement`/`textContent` (NUNCA `innerHTML` con datos del server). Error de
red = silencioso (`console.warn`): la campana nunca rompe la página. **Cuándo
llamarla desde un módulo**: después de cualquier mutación (alta/edición/borrado)
para que el badge se actualice sin recargar — ej. `lactancia.js` la llama en
`renderTodo()` (`if (window.Notif) window.Notif.refrescar();`).

**Flujo de refresco (3 momentos)**: (1) al cargar la página el badge viene
server-rendered (`notif_badge`); (2) al ABRIR el panel, `initDrawers()` llama
`Notif.refrescar()`; (3) tras una mutación, el módulo llama `Notif.refrescar()`.

**Ítem** (`.notif-item`, un `<a href="{url}">`): `.notif-item-icono` (emoji) +
`.notif-item-cuerpo` con `.notif-item-modulo` (pill uppercase muted = `modulo_nombre`),
`.notif-item-titulo` (negrita), `.notif-item-detalle` (muted). Severidad → clase
`is-{severidad}` → borde izquierdo 3px + tinte de fondo `color-mix`:

| `severidad` | clase       | variable de paleta |
|-------------|-------------|--------------------|
| `peligro`   | `.is-peligro` | `--color-peligro` |
| `alerta`    | `.is-alerta`  | `--color-alerta`  |
| `info`      | `.is-info`    | `--color-acento`  |

Lista vacía → `.notif-vacio` ("Sin notificaciones"). CSS: sección
"PANEL NOTIFICACIONES" al final de `style.css`.

## Al modificar este dominio, actualizar:
- Sección 2 (contrato) si cambia una clave o un valor posible de `severidad`.
- Sección 3 si cambia el registry, `_notificaciones()`, la ruta o el context processor.
- Sección 4 si cambia el provider de Lactancia, o sumar una sub-sección si se agrega un provider nuevo.
