# Contexto: Notificaciones — el estándar de Núcleo

> Leer con `CLAUDE.md`. Define **CÓMO avisa Núcleo**, cualquier módulo. Push = canal de este estándar, doc propio (`CONTEXT_PUSH.md` / `CONTEXT_PUSH_MOTOR.md`).
>
> ⚠ Excepción al tope de 150 líneas de `CLAUDE.md` §5: estándar transversal; partirlo rompe lo que tiene que lograr — UN lugar donde está escrito cómo se avisa. Ya afuera: push (2 docs) y DOM/CSS de la campana (`CONTEXT_FRONTEND.md`). Antes de recortar más, leer §3 y §4: son el estándar, y no se tocan.

## 1. De quién es este dominio

**Notificaciones = NÚCLEO, no un módulo.** Hoy solo las usa Lactancia: dato de hoy, no arquitectura. Mañana Gastos, Rutina o módulo que todavía no existe. **Todos avisan acá: mismo contrato, mismo canal, mismo código.**

Módulo NO escribe campana, badge ni aviso propio: escribe un **provider** y lo registra.

⚠ Antes cada módulo tenía badge propio (`lac_badge`) → había que tocar el header por cada aviso. Eliminado por eso. Agente que propone contador propio en nav → respuesta = este archivo.

## 2. El contrato del ítem — CERRADO, 7 claves

| Clave           | Tipo | Notas                                                          |
|-----------------|------|----------------------------------------------------------------|
| `modulo` / `modulo_nombre` | str | Slug y nombre legible. Ej. `"lactancia"` / `"Lactancia"`. |
| `icono`     | str | Emoji del módulo. Ej. `"🍼"`.                              |
| `titulo`    | str | Título corto. ⚠ **Es la IDENTIDAD del aviso** — ver §4.     |
| `detalle`   | str | Línea descriptiva. Puede cambiar todo lo que quiera.       |
| `url`       | str | A dónde navega el click. **Relativa**, empieza con `/`.    |
| `severidad` | str | `"peligro"` \| `"alerta"` \| `"info"` → color de la paleta. |

Ni una clave más, ni una menos.

## 3. CÓMO SE AGREGA UNA NOTIFICACIÓN (el procedimiento, completo)

**1. Escribir el provider en `app.py`**, al lado de los otros `_notif_*`:

```python
def _notif_<modulo>():
    """Provider de <Módulo>: un ítem por <cosa que hay que mirar>."""
    items = []
    for x in <lo que ya calculan los helpers del módulo>:
        items.append({
            'modulo': '<modulo>', 'modulo_nombre': '<Módulo>', 'icono': '<emoji>',
            'titulo': '<título ESTABLE>',        # ver §4
            'detalle': f'<lo que cambia>',
            'url': '/<modulo>', 'severidad': 'alerta',
        })
    return items
```

**2. Registrarlo en la campana** — una línea:

```python
NOTIF_PROVIDERS = [_notif_lactancia, _notif_recordatorio_bajar, _notif_<modulo>]
```

Listo: aparece en campana y badge. **No se toca**: ruta, ni context processor, ni frontend, ni `base.html`, ni CSS.

**3. ¿También despierta un teléfono?** Decisión aparte y explícita — no todo lo que merece puntito merece sonar celular a las 11 de la noche. Si sí, una línea más:

```python
PUSH_AVISOS = [..., ('<modulo>', _notif_<modulo>)]
```

Antes: leer `CONTEXT_PUSH_MOTOR.md` (flanco, horas de silencio, topes). **Si no se agrega, el módulo avisa igual — solo que in-app.**

**4. JS del módulo**, tras cualquier alta/edición/borrado:

```js
if (window.Notif) window.Notif.refrescar();
```

Sin esto: badge viejo hasta próximo render.

**5. Actualizar apéndice §8** con el provider nuevo.

## 4. Las reglas que hacen que esto funcione

- **Provider devuelve un NIVEL, no un evento.** Contesta "¿qué hay AHORA?" cada llamada, sin memoria y sin saber qué contestó antes. Detectar que algo *apareció* = motor de push, no provider.
- ⚠ **`titulo` = identidad del aviso, tiene que ser ESTABLE.** Push deduplica por `(provider, severidad, titulo)`. Título con número adentro —`"3 tareas pendientes"`, `"Vence el 12/05"`— = clave nueva cada vez que cambia el número → **teléfono sonando de nuevo por lo mismo**. Número va en `detalle`, que no entra en ninguna clave.
- ⚠ **`titulo` no lleva plata, ni saldos, ni nombres de banco.** Push se lee en **pantalla bloqueada**, sin desbloquear. Monto se mira adentro de la app; aviso dice que hay algo para mirar.
- **Provider BARATO.** Corre en CADA render de CADA página (context processor del badge) y cada 10 minutos en hilo de push. Query pesada o API externa sin caché → se paga en todas las pantallas. Si hace falta algo caro, cachearlo antes.
- **Provider solo LEE y da formato.** No recalcula estados ni vencimientos que ya vivan en helpers del módulo, y no escribe nada en la base.
- **Fallar = contemplado**: dejar subir la excepción. `_notificaciones()` la aísla con try/except + `AVISO:`; módulo roto nunca tumba la campana. No hace falta try/except propio adentro.
- **`url` relativa** (`/lactancia`). Servidor no conoce su dirección pública; por push la resuelve el service worker.

## 5. Los dos canales

- **Campana** (`NOTIF_PROVIDERS`, este doc): *pull* — se evalúa al mirar, muestra NIVEL completo. Con app abierta.
- **Push** (`PUSH_AVISOS`, `CONTEXT_PUSH_MOTOR.md`): *report by exception* — servidor empuja, y solo el **flanco** (lo que antes no estaba). App cerrada, pantalla bloqueada.

**Mismo provider**, dos registries. Estar en la campana no pone nada en el push: eso se decide con una línea explícita.

## 6. Backend (`app.py`)

- **`_notificaciones()`**: agrega todos los providers de `NOTIF_PROVIDERS`, cada uno en su try/except con `log()` (NUNCA `print()`). Orden severidad `peligro` → `alerta` → `info`, sort **estable**: respeta orden interno de cada provider y del registry entre módulos.
- **`GET /api/notificaciones`** → `{'ok', 'total', 'items'}`. Solo lectura, auth por `before_request` de `auth.py`.
- **`inject_notif_badge`**: expone `notif_badge` (`= len(_notificaciones())`) a TODOS los templates, try/except → 0. Acá nace la regla "el provider tiene que ser barato" de §4.

## 7. Frontend

**`window.Notif.refrescar()`** (`app.js`) — API pública del estándar; lo único que un módulo necesita del frontend. Hace `fetch('/api/notificaciones')`, sincroniza badge, re-renderiza lista con `createElement`/`textContent` (**nunca** `innerHTML` con datos del server). Error de red = silencioso: campana no rompe la página.

**4 momentos de refresco**: al cargar (server-rendered vía `notif_badge`), al abrir panel, tras mutación si el módulo la llama, y al llegar push (vía `postMessage` del service worker).

DOM, clases y CSS → `CONTEXT_FRONTEND.md`: módulo no los toca.

## 8. Apéndice — los providers que existen HOY

> Esto es **el ejemplo, no la definición**. La lista cambia; §1-§7 no.

**`_notif_lactancia()`** — 1 ítem por partida ABIERTA `vencida` o `vence_pronto`. Reusa `_lac_params()` / `_lac_enriquecer()` tal cual (cálculo solo en helpers `_lac_*`). `vencida` → `peligro` + "Partida vencida"; `vence_pronto` → `alerta` + "Partida por vencer". ⚠ Los 2 títulos FIJOS — ubicación, volumen y tiempo relativo van en `detalle`. Es §4 aplicado.

**`_notif_recordatorio_bajar()`** — 0 o 1 ítem: `🌙`, `alerta`, "Bajá bolsitas para mañana"; condición = `_lac_recordatorio_pendiente()`.

Los 2 también en `PUSH_AVISOS`.

## Al modificar este dominio, actualizar:
- §2 si cambia una clave del contrato o un valor de `severidad`.
- §3 o §4 si cambia el procedimiento o una regla — **son el estándar**.
- §6 / §7 si cambia el registry, la ruta, el context processor o la campana.
- §8 al sumar o sacar un provider (y `PUSH_AVISOS` si además va al teléfono).
