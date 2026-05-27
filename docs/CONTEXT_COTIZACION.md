# Contexto: Cotización USD

> Leer junto con `CLAUDE.md`. Para tareas sobre conversión ARS↔USD.

## Archivos del dominio
- `cotizacion.py` (191 líneas).
- `tests/test_cotizacion.py` (205 líneas).
- Persistencia: `config.json` (claves `cotizacion_*`).

## APIs externas
- **Actual**: `dolarapi.com` → endpoint USD oficial → campo `venta`.
- **Histórica**: `argentinadatos.com` → lista de cotizaciones por fecha.

Constantes en módulo: `URL_COTIZACION_ACTUAL`, `URL_COTIZACIONES_HISTORICAS`, `TIMEOUT_SEGUNDOS`, `USER_AGENT`, `MAX_DIAS_RETROCESO=10`.

## Funciones públicas

| Función                                  | Retorna                              | Notas                                      |
|------------------------------------------|--------------------------------------|--------------------------------------------|
| `obtener_cotizacion_actual()`            | `{'valor': float, 'fecha': 'YMD'}`   | Llama a dolarapi. Lanza excepciones        |
| `obtener_cotizaciones_historicas(forzar_refresh=False)` | `dict {YMD: float}`   | Cachea en módulo                           |
| `cotizacion_para_fecha(fecha, historicas)` | `float` o `None`                   | Retrocede hasta 10 días si no hay exacta   |
| `refrescar_cache(config_path)`           | `(ok: bool, mensaje: str)`           | Persiste en config.json. Fallback intacto  |

## Estado en `config.json`
- `cotizacion_valor` — último valor exitoso (default bootstrap 1500.0).
- `cotizacion_fecha` — `YYYY-MM-DD` del valor.
- `cotizacion_ultimo_intento` — timestamp del último intento (éxito o falla).
- `cotizacion_ok` — `True` si último intento fue exitoso.

## Scheduler (definido en `app.py`)
- `iniciar_scheduler_cotizacion()` corre en hilo. Ver `_proximo_horario_refresh()` para horarios fijos.
- Refresh manual: `POST /api/cotizacion/refresh`.

## Reglas específicas
1. **Si la API falla, NO sobrescribir `cotizacion_valor`**. Solo actualizar `cotizacion_ultimo_intento` y `cotizacion_ok=False`.
2. **Movimientos en USD**: `monto_usd = monto`, `cotizacion_usd_aplicada = NULL`.
3. **Movimientos en ARS**: `monto_usd = monto / cotizacion_valor`, `cotizacion_usd_aplicada = cotizacion_valor`.
4. La función `_calcular_monto_usd` de `app.py` es el wrapper. NO duplicar lógica.
5. Cache histórico vive en `_cache_historicas` (variable de módulo). `forzar_refresh=True` lo invalida.

## Al modificar este dominio, actualizar:
- Tabla de funciones si cambia firma o retorno.
- Sección "Estado en config.json" si se agrega clave.
- Lista de constantes si cambia URL o timeout.
