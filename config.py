# =============================================================================
# ARCHIVO: config.py
# =============================================================================
#
# Módulo de configuración centralizado.
# Lee y escribe config.json, que es la única fuente de verdad para
# todas las opciones del entorno (puerto, ngrok, primer inicio, etc.)
#
# =============================================================================

import json
import os

_DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

DEFAULTS = {
    "port": 5000,
    "first_run": True,
    "ngrok_enabled": False,
    "ngrok_authtoken": "",
    "ngrok_domain": "",
    "app_name": "Gastos Casa",
    "factor_sueldo": 0.7,
    "usd_a_ars": 1500,
    "google_client_id": "",
    "google_client_secret": "",
    "secret_key": "",
}


def cargar_config(ruta=None):
    """Lee el archivo de config y retorna un dict. Usa defaults para claves faltantes."""
    if ruta is None:
        ruta = _DEFAULT_CONFIG_PATH
    cfg = dict(DEFAULTS)
    if os.path.exists(ruta):
        try:
            with open(ruta, 'r', encoding='utf-8') as f:
                datos = json.load(f)
            cfg.update(datos)
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def guardar_config(data, ruta=None):
    """Escribe el dict `data` en el archivo de config."""
    cfg = cargar_config(ruta)
    cfg.update(data)
    if ruta is None:
        ruta = _DEFAULT_CONFIG_PATH
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def es_primer_inicio():
    """Retorna True si first_run está en True en config.json."""
    return cargar_config().get('first_run', True)
