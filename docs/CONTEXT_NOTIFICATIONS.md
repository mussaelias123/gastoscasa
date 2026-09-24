# Contexto: Notificaciones — el estándar de Núcleo

> Leer junto con `CLAUDE.md`. Este doc define **CÓMO avisa Núcleo**, para
> cualquier módulo. El push al teléfono es un canal de este mismo estándar y
> tiene su propio doc (`CONTEXT_PUSH.md` / `CONTEXT_PUSH_MOTOR.md`).
>
> ⚠ Excepción aceptada al tope de 150 líneas de `CLAUDE.md` §5: esto es un
> estándar transversal y partirlo en dos archivos rompe justo lo que tiene que
> lograr — que haya UN lugar donde está escrito cómo se avisa. Ya se movieron
> afuera el push (2 docs) y el DOM/CSS de la campana (`CONTEXT_FRONTEND.md`).
> Antes de recortar más, leer §3 y §4: son el estándar, y no se tocan.

## 1. De quién es este dominio

**Las notificaciones son de NÚCLEO, no de un módulo.** Que hoy solo las use
Lactancia es un dato de hoy, no la arquitectura: mañana avisa Gastos, Rutina, o
un módulo que todavía no existe. **Todos avisan por acá, con el mismo contrato,
el mismo canal y el mismo código.**

Un módulo NO escribe su propia campana, su propio badge ni su propio aviso:
escribe un **provider** y lo registra. Eso es todo.

⚠ Antes cada módulo tenía su badge propio (`lac_badge`) y había que tocar el
header cada vez que uno quería avisar algo. Se eliminó por eso. Si un agente
vuelve a proponer un contador propio en el nav de un módulo, la respuesta es
este archivo.

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

Listo: ya aparece en la campana y en el badge. **No se toca** la ruta, ni el
context processor, ni el frontend, ni `base.html`, ni el CSS.

**3. ¿También tiene que despertar un teléfono?** Es una decisión aparte y
explícita — no todo lo que merece un puntito merece hacer sonar un celular a
las 11 de la noche. Si la respuesta es sí, una línea más:

```python
PUSH_AVISOS = [..., ('<modulo>', _notif_<modulo>)]
```

Antes de agregarla, leer `CONTEXT_PUSH_MOTOR.md`: ahí está el flanco, las
horas de silencio y los topes. **Si no se agrega, el módulo avisa igual — solo
que in-app.**

**4. En el JS del módulo**, después de cualquier alta/edición/borrado:

```js
if (window.Notif) window.Notif.refrescar();
```

Sin esto el badge queda viejo hasta el próximo render de página.

**5. Actualizar el apéndice §8 de este archivo** con el provider nuevo.

## 4. Las reglas que hacen que esto funcione

- **Un provider devuelve un NIVEL, no un evento.** Contesta "¿qué hay AHORA?"
  cada vez que se lo llama, sin memoria y sin saber qué contestó antes.
  Detectar que algo *apareció* es trabajo del motor de push, no del provider.
- ⚠ **El `titulo` es la identidad del aviso, y tiene que ser ESTABLE.** El push
  deduplica por `(provider, severidad, titulo)`. Un título con un número
  adentro —`"3 tareas pendientes"`, `"Vence el 12/05"`— genera una clave nueva
  cada vez que ese número cambia, y eso es **un teléfono sonando de nuevo por
  lo mismo**. El número va en `detalle`, que no entra en ninguna clave.
- ⚠ **El `titulo` no lleva plata, ni saldos, ni nombres de banco.** Vía push se
  lee en la **pantalla bloqueada**, sin desbloquear el teléfono. El monto se
  mira adentro de la app; el aviso dice que hay algo para mirar.
- **El provider tiene que ser BARATO.** Corre en CADA render de CADA página
  (el context processor del badge) y además cada 10 minutos en el hilo de push.
  Una query pesada o una llamada a una API externa sin caché se paga en todas
  las pantallas de la app. Si hace falta algo caro, cachearlo antes.
- **El provider solo LEE y da formato.** No recalcula estados ni vencimientos
  que ya vivan en los helpers del módulo, y no escribe nada en la base.
- **Que falle está contemplado**: dejar que la excepción suba.
  `_notificaciones()` la aísla con try/except + `AVISO:`, y un módulo roto
  nunca tumba la campana. No hace falta un try/except propio adentro.
- **La `url` va relativa** (`/lactancia`). El servidor no conoce su dirección
  pública, y por push la resuelve el service worker.

## 5. Los dos canales

- **Campana** (`NOTIF_PROVIDERS`, este doc): *pull* — se evalúa cuando alguien
  mira, y muestra el NIVEL completo. Se ve con la app abierta.
- **Push** (`PUSH_AVISOS`, `CONTEXT_PUSH_MOTOR.md`): *report by exception* — el
  servidor empuja, y solo el **flanco** (lo que antes no estaba). Se ve con la
  app cerrada, en la pantalla bloqueada.

Son **el mismo provider** leído por dos registries distintos. Estar en la
campana no pone nada en el push: eso se decide con una línea explícita.

## 6. Backend (`app.py`)

- **`_notificaciones()`**: agrega todos los providers de `NOTIF_PROVIDERS`,
  cada uno en su propio try/except con `log()` (NUNCA `print()`). Ordena por
  severidad `peligro` → `alerta` → `info`, con sort **estable**: respeta el
  orden interno de cada provider y el del registry entre módulos.
- **`GET /api/notificaciones`** → `{'ok', 'total', 'items'}`. Solo lectura,
  auth por el `before_request` de `auth.py`.
- **`inject_notif_badge`**: expone `notif_badge` (`= len(_notificaciones())`) a
  TODOS los templates, con try/except → 0. Acá nace la regla "el provider
  tiene que ser barato" de §4.

## 7. Frontend

**`window.Notif.refrescar()`** (`app.js`) — la API pública del estándar, y lo
único que un módulo necesita saber del frontend. Hace
`fetch('/api/notificaciones')`, sincroniza el badge y re-renderiza la lista con
`createElement`/`textContent` (**nunca** `innerHTML` con datos del server). Un
error de red es silencioso: la campana no rompe la página.

**Se refresca en 4 momentos**: al cargar (server-rendered vía `notif_badge`), al
abrir el panel, tras una mutación si el módulo la llama, y cuando llega un push
(vía el `postMessage` del service worker).

El DOM, las clases y el CSS están en `CONTEXT_FRONTEND.md`: un módulo no los toca.

## 8. Apéndice — los providers que existen HOY

> Esto es **el ejemplo, no la definición**. La lista cambia; §1-§7 no.

**`_notif_lactancia()`** — un ítem por partida ABIERTA `vencida` o
`vence_pronto`. Reusa `_lac_params()` / `_lac_enriquecer()` tal cual (el cálculo
vive solo en los helpers `_lac_*`). `vencida` → `peligro` + "Partida vencida";
`vence_pronto` → `alerta` + "Partida por vencer". ⚠ Los dos títulos son FIJOS —
ubicación, volumen y tiempo relativo van en `detalle`. Es §4 aplicado.

**`_notif_recordatorio_bajar()`** — 0 o 1 ítem: `🌙`, `alerta`, "Bajá bolsitas
para mañana"; la condición la decide `_lac_recordatorio_pendiente()`.

Los dos están también en `PUSH_AVISOS`.

## Al modificar este dominio, actualizar:
- §2 si cambia una clave del contrato o un valor de `severidad`.
- §3 o §4 si cambia el procedimiento o una regla — **son el estándar**.
- §6 / §7 si cambia el registry, la ruta, el context processor o la campana.
- §8 al sumar o sacar un provider (y `PUSH_AVISOS` si además va al teléfono).
