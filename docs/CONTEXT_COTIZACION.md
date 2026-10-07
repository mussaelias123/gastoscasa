# Contexto: Cotización USD

> Leer junto con `CLAUDE.md`. Para tareas sobre conversión ARS↔USD.

## Archivos del dominio
- `cotizacion.py` (485 líneas).
- `tests/test_cotizacion.py` (897 líneas; 66 tests, sin internet: `urlopen` mockeado, y bloqueado por defecto en las clases nuevas).
- Persistencia: `config.json` (claves `cotizacion_*`).

## APIs externas
- **Actual**: `dolarapi.com` → endpoint USD oficial → campo `venta`.
- **Histórica**: `argentinadatos.com` → lista de cotizaciones por fecha.

Constantes en módulo: `URL_COTIZACION_ACTUAL`, `URL_COTIZACIONES_HISTORICAS`, `TIMEOUT_SEGUNDOS`, `USER_AGENT`, `MAX_DIAS_RETROCESO=10`, y las del blindaje: `MAX_RESPUESTA_BYTES` (5 MB), `COTIZACION_MAXIMA` (10.000.000, exclusivo), `SALTO_MAXIMO` (0.5 = ±50%).

Excepciones: `CotizacionRechazada(ValueError)` (la API contestó pero no se acepta; `str(e)` ya es el mensaje para mostrar) y `RespuestaDemasiadoGrande(ValueError)`.

## Funciones públicas

| Función                                  | Retorna                              | Notas                                      |
|------------------------------------------|--------------------------------------|--------------------------------------------|
| `obtener_cotizacion_actual()`            | `{'valor': float, 'fecha': 'YMD'}`   | Llama a dolarapi y **valida** valor y fecha. Lanza `CotizacionRechazada` si el valor no sirve; red/HTTP/JSON/tamaño se propagan tal cual |
| `obtener_cotizaciones_historicas(forzar_refresh=False)` | `dict {YMD: float}`   | Cachea en módulo. **Ignora** filas basura (valor o fecha inválidos, no-objetos). NO aplica el ±50% (hubo saltos reales, ej. dic 2023) |
| `cotizacion_para_fecha(fecha, historicas)` | `float` o `None`                   | Retrocede hasta 10 días si no hay exacta   |
| `refrescar_cache(config_path)`           | `(ok: bool, mensaje: str)`           | Persiste en config.json. Controla el ±50%. **Nunca levanta**. Fallback intacto |

Helpers internos: `_valor_valido`, `_exigir_valor`, `_fecha_valida`, `_salto_excesivo`, `_porcentaje`, `_controlar_salto` (validan y deciden, no escriben nada) y `_explicar`, `_registrar_fallo` (arman el mensaje y anotan el intento fallido).

## Estado en `config.json`
- `cotizacion_valor` — último valor **ACEPTADO** (default bootstrap 1500.0). Es la base del control ±50%.
- `cotizacion_fecha` — `YYYY-MM-DD` del valor. `None`/vacía = nunca hubo una actualización exitosa (ver excepción de arranque).
- `cotizacion_ultimo_intento` — timestamp del último intento (éxito, rechazo o falla).
- `cotizacion_ok` — `True` si el último intento fue exitoso.

No hay claves nuevas: el blindaje usa solo estas cuatro.

## Blindaje del dato: una cotización mala nunca entra
**Por qué**: el `monto_usd` de cada movimiento en pesos se congela al insertarlo. Una cotización falsa guarda un USD falso **para siempre**, y después no se distingue de uno bueno. `_calcular_monto_usd` (app.py) es el último resguardo; **el origen se blinda acá**.

`refrescar_cache` devuelve `(False, mensaje)` y NO toca el valor cuando (el punto 1 se valida DOS veces: en `obtener_cotizacion_actual` y de nuevo en `refrescar_cache`, ya en la puerta de `config.json`):
1. **Valor inválido**: no es un número finito, > 0 y < `COTIZACION_MAXIMA`. Cubre 0, negativos, NaN, infinito, booleanos, texto no numérico, ausente, `null` y absurdos. El texto que SÍ es un número (`"1450.5"`) se acepta, como siempre.
2. **Salto de más de ±50%** contra `cotizacion_valor`: `abs(nuevo - anterior) / anterior > 0.5`. **Exactamente ±50% se acepta.** La cuenta va en `Decimal` (con floats, un +50% exacto de 1619.84 → 2429.76 se rechazaría por error).
3. **Respuesta de más de 5 MB**: `_http_get_json` lee `MAX_RESPUESTA_BYTES + 1` y corta.
4. **Falla de conexión** (timeout, error HTTP, JSON roto): igual que siempre, ahora con mensaje en español.

**Excepción de arranque** (lo único que saltea el ±50%): `cotizacion_fecha` vacía (el 1500.0 de DEFAULTS es un bootstrap, no un valor a defender) o el valor anterior no sirve (0, basura, ≥ tope). Entonces entra el primer valor **válido**. La validación del punto 1 rige siempre.

**Qué se escribe en CUALQUIER rechazo o falla**: solo `cotizacion_ultimo_intento` y `cotizacion_ok=False`. Nunca `cotizacion_valor` ni `cotizacion_fecha`.

**Fecha de la API**: se usa solo si empieza con una fecha real `YYYY-MM-DD` (calendario, ASCII); si no, la de hoy. Texto de la API nunca llega a config.json.

**`config.json` ilegible** (`config.ConfigIlegible`): `(False, mensaje)` sin escribir nada, ni el intento. Otros errores al escribir (`PermissionError`, disco) también salen como `(False, mensaje)`.

### Mensajes (los loguea el scheduler y los muestra el botón de Settings)
- `Cotización rechazada: ...` → la API contestó pero no se acepta (valor inválido, formato, salto).
- `No se pudo actualizar la cotización: ...` → no hubo respuesta usable (red, HTTP, JSON, 5 MB) o no se pudo guardar.
- Lo que dice la API se acota y se muestra con `repr`: no mete saltos de línea, no falsifica una línea del log.

### Cómo destrabar a mano (devaluación real de más del 50%)
El control va a rechazar el valor real; la app sigue con el último aceptado (los movimientos en pesos nuevos se convierten con ese) y Settings muestra "Desactualizada" (por `cotizacion_ok=False`). Para destrabar:
1. Editar `config.json` y poner `cotizacion_valor` en un valor **cercano al real** (dentro del ±50% del que da la API). Se lee en caliente: no hace falta reiniciar.
2. Apretar "↻ Actualizar" en Settings (o esperar al scheduler). Ahora compara contra el valor nuevo y entra.
- Alternativa: poner `cotizacion_fecha` en `null` → el próximo refresh lo trata como arranque y acepta el primer valor válido sin comparar. Usarlo solo si no se sabe un valor cercano.
- Mismo caso: app parada mucho tiempo y el dólar se movió > 50% desde el último valor. El control no mira la antigüedad del valor.

## Scheduler (definido en `app.py`)
- `iniciar_scheduler_cotizacion()` corre en hilo: un refresh al arrancar y luego a las 8 y 17 h (`HORAS_REFRESH_COTIZACION`). Ver `_proximo_horario_refresh()`.
- Si un refresh sale `ok=False` (falla o rechazo), reintenta UNA vez a los 15 min (`REINTENTO_FALLO_SEGUNDOS`). Un rechazo se repite igual: dos líneas `AVISO:` en el log; es normal.
- Refresh manual: `POST /api/cotizacion/refresh` (devuelve `ok`, `mensaje`, y el valor vigente de la config).

## Reglas específicas
1. **Si la API falla o se rechaza el valor, NO sobrescribir `cotizacion_valor` ni `cotizacion_fecha`**. Solo `cotizacion_ultimo_intento` y `cotizacion_ok=False`.
2. **Movimientos en USD**: `monto_usd = monto`, `cotizacion_usd_aplicada = NULL`.
3. **Movimientos en ARS**: `monto_usd = monto / cotizacion_valor`, `cotizacion_usd_aplicada = cotizacion_valor`.
4. La función `_calcular_monto_usd` de `app.py` es el wrapper (y rechaza una cotización 0/no finita). NO duplicar lógica.
5. Cache histórico vive en `_cache_historicas` (variable de módulo). `forzar_refresh=True` lo invalida. Un resultado vacío también se cachea.
6. **No aflojar el blindaje** (más tope, quitar el ±50%) sin que lo pida el usuario: la decisión es suya. Si hay que cambiarlo, tocar las constantes y los tests.
7. `refrescar_cache` no levanta nunca; todo error vuelve como `(False, mensaje)`.

## Al modificar este dominio, actualizar:
- Tabla de funciones si cambia firma o retorno.
- Sección "Estado en config.json" si se agrega clave.
- Lista de constantes si cambia URL, timeout o un tope.
- Las reglas de rechazo de arriba y `docs/CONTEXT_CONFIG.md` (filas `cotizacion_*`) si cambia qué se rechaza.
