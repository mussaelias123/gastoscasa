# Contexto: Cotización USD

> Leer con `CLAUDE.md`. Tareas ARS↔USD.

## Archivos del dominio
- `cotizacion.py` (485 líneas).
- `tests/test_cotizacion.py` (897 líneas; 66 tests, sin internet: `urlopen` mockeado, bloqueado por defecto en clases nuevas).
- Persistencia: `config.json` (claves `cotizacion_*`).

## APIs externas
- **Actual**: `dolarapi.com` → endpoint USD oficial → campo `venta`.
- **Histórica**: `argentinadatos.com` → lista cotizaciones por fecha.

Constantes en módulo: `URL_COTIZACION_ACTUAL`, `URL_COTIZACIONES_HISTORICAS`, `TIMEOUT_SEGUNDOS`, `USER_AGENT`, `MAX_DIAS_RETROCESO=10`, y blindaje: `MAX_RESPUESTA_BYTES` (5 MB), `COTIZACION_MAXIMA` (10.000.000, exclusivo), `SALTO_MAXIMO` (0.5 = ±50%).

Excepciones: `CotizacionRechazada(ValueError)` (API contestó, no se acepta; `str(e)` = mensaje para mostrar) y `RespuestaDemasiadoGrande(ValueError)`.

## Funciones públicas

| Función | Retorna | Notas |
|---|---|---|
| `obtener_cotizacion_actual()` | `{'valor': float, 'fecha': 'YMD'}` | Llama dolarapi, **valida** valor y fecha. Lanza `CotizacionRechazada` si valor no sirve; red/HTTP/JSON/tamaño se propagan tal cual |
| `obtener_cotizaciones_historicas(forzar_refresh=False)` | `dict {YMD: float}` | Cachea en módulo. **Ignora** filas basura (valor o fecha inválidos, no-objetos). NO aplica ±50% (hubo saltos reales, ej. dic 2023) |
| `cotizacion_para_fecha(fecha, historicas)` | `float` o `None` | Retrocede hasta 10 días si no hay exacta |
| `refrescar_cache(config_path)` | `(ok: bool, mensaje: str)` | Persiste en config.json. Controla ±50%. **Nunca levanta**. Fallback intacto |

Helpers internos: `_valor_valido`, `_exigir_valor`, `_fecha_valida`, `_salto_excesivo`, `_porcentaje`, `_controlar_salto` (validan y deciden, no escriben) y `_explicar`, `_registrar_fallo` (arman mensaje y anotan intento fallido).

## Estado en `config.json`
- `cotizacion_valor` — último valor **ACEPTADO** (default bootstrap 1500.0). Base del control ±50%.
- `cotizacion_fecha` — `YYYY-MM-DD` del valor. `None`/vacía = nunca hubo actualización exitosa (ver excepción de arranque).
- `cotizacion_ultimo_intento` — timestamp último intento (éxito, rechazo o falla).
- `cotizacion_ok` — `True` si último intento exitoso.

No hay claves nuevas: blindaje usa solo estas cuatro.

## Blindaje del dato: una cotización mala nunca entra
**Por qué**: `monto_usd` de cada movimiento en pesos se congela al insertar. Cotización falsa → USD falso **para siempre**, no se distingue de uno bueno. `_calcular_monto_usd` (app.py) = último resguardo; **el origen se blinda acá**.

`refrescar_cache` devuelve `(False, mensaje)` y NO toca el valor cuando (punto 1 se valida DOS veces: en `obtener_cotizacion_actual` y en `refrescar_cache`, en la puerta de `config.json`):
1. **Valor inválido**: no número finito, > 0 y < `COTIZACION_MAXIMA`. Cubre 0, negativos, NaN, infinito, booleanos, texto no numérico, ausente, `null`, absurdos. Texto que SÍ es número (`"1450.5"`) se acepta, como siempre.
2. **Salto > ±50%** contra `cotizacion_valor`: `abs(nuevo - anterior) / anterior > 0.5`. **Exactamente ±50% se acepta.** Cuenta en `Decimal` (con floats, +50% exacto de 1619.84 → 2429.76 se rechazaría por error).
3. **Respuesta > 5 MB**: `_http_get_json` lee `MAX_RESPUESTA_BYTES + 1` y corta.
4. **Falla de conexión** (timeout, error HTTP, JSON roto): igual que siempre, ahora con mensaje en español.

**Excepción de arranque** (única que saltea ±50%): `cotizacion_fecha` vacía (1500.0 de DEFAULTS = bootstrap, no valor a defender) o valor anterior no sirve (0, basura, ≥ tope). Entra el primer valor **válido**. Validación punto 1 rige siempre.

**Qué se escribe en CUALQUIER rechazo o falla**: solo `cotizacion_ultimo_intento` y `cotizacion_ok=False`. Nunca `cotizacion_valor` ni `cotizacion_fecha`.

**Fecha de la API**: se usa solo si empieza con fecha real `YYYY-MM-DD` (calendario, ASCII); si no, la de hoy. Texto de API nunca llega a config.json.

**`config.json` ilegible** (`config.ConfigIlegible`): `(False, mensaje)` sin escribir nada, ni el intento. Otros errores al escribir (`PermissionError`, disco) también salen como `(False, mensaje)`.

### Mensajes (los loguea el scheduler y los muestra el botón de Settings)
- `Cotización rechazada: ...` → API contestó pero no se acepta (valor inválido, formato, salto).
- `No se pudo actualizar la cotización: ...` → no hubo respuesta usable (red, HTTP, JSON, 5 MB) o no se pudo guardar.
- Lo que dice la API se acota y se muestra con `repr`: no mete saltos de línea, no falsifica línea del log.

### Cómo destrabar a mano (devaluación real de más del 50%)
Control rechaza valor real; app sigue con último aceptado (movimientos en pesos nuevos se convierten con ese) y Settings muestra "Desactualizada" (por `cotizacion_ok=False`). Destrabar:
1. Editar `config.json`, poner `cotizacion_valor` en valor **cercano al real** (dentro ±50% del de la API). Se lee en caliente: no hace falta reiniciar.
2. Apretar "↻ Actualizar" en Settings (o esperar scheduler). Compara contra valor nuevo y entra.
- Alternativa: `cotizacion_fecha` en `null` → próximo refresh lo trata como arranque y acepta primer válido sin comparar. Usar solo si no se sabe valor cercano.
- Mismo caso: app parada mucho tiempo y dólar se movió > 50% desde último valor. Control no mira antigüedad del valor.

## Scheduler (definido en `app.py`)
- `iniciar_scheduler_cotizacion()` corre en hilo: refresh al arrancar, luego 8 y 17 h (`HORAS_REFRESH_COTIZACION`). Ver `_proximo_horario_refresh()`.
- Si refresh sale `ok=False` (falla o rechazo), reintenta UNA vez a los 15 min (`REINTENTO_FALLO_SEGUNDOS`). Rechazo se repite igual: dos líneas `AVISO:` en log; normal.
- Refresh manual: `POST /api/cotizacion/refresh` (devuelve `ok`, `mensaje`, valor vigente de config).

## Reglas específicas
1. **Si API falla o rechaza valor, NO sobrescribir `cotizacion_valor` ni `cotizacion_fecha`**. Solo `cotizacion_ultimo_intento` y `cotizacion_ok=False`.
2. **Movimientos en USD**: `monto_usd = monto`, `cotizacion_usd_aplicada = NULL`.
3. **Movimientos en ARS**: `monto_usd = monto / cotizacion_valor`, `cotizacion_usd_aplicada = cotizacion_valor`.
4. `_calcular_monto_usd` de `app.py` = wrapper (rechaza cotización 0/no finita). NO duplicar lógica.
5. Cache histórico en `_cache_historicas` (var módulo). `forzar_refresh=True` lo invalida. Resultado vacío también se cachea.
6. **No aflojar blindaje** (más tope, quitar ±50%) sin pedido del usuario: decisión suya. Si hay que cambiar: tocar constantes y tests.
7. `refrescar_cache` no levanta nunca; todo error vuelve como `(False, mensaje)`.

## Al modificar este dominio, actualizar:
- Tabla de funciones si cambia firma o retorno.
- Sección "Estado en config.json" si se agrega clave.
- Lista de constantes si cambia URL, timeout o tope.
- Reglas de rechazo de arriba y `docs/CONTEXT_CONFIG.md` (filas `cotizacion_*`) si cambia qué se rechaza.
