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
    # ── Lactancia (banco de leche) — editables desde Settings ──────────────
    # Vencimiento freezer = extracción + N meses; heladera = carga + N horas.
    # Los avisos definen la ventana "vence pronto" de cada ubicación.
    "lactancia_freezer_meses":        6,
    "lactancia_heladera_horas":       48,
    "lactancia_aviso_freezer_dias":   14,
    "lactancia_aviso_heladera_horas": 12,
    # ── Cotización USD oficial ──────────────────────────────────────────────
    # Se obtiene de dolarapi.com (módulo cotizacion.py) y se refresca 1 vez/día.
    # El 1500.0 es solo un bootstrap inicial; se sobrescribe en la primera
    # actualización exitosa.
    "cotizacion_valor":          1500.0,
    "cotizacion_fecha":          None,
    "cotizacion_ultimo_intento": None,
    "cotizacion_ok":             False,
    "google_client_id": "",
    "google_client_secret": "",
    "secret_key": "",
    # ── Bypass de login SOLO para DEV ───────────────────────────────────────
    # Si True, se saltea el login de Google, pero ÚNICAMENTE bajo triple cerrojo
    # (ver auth.py → require_login): auth_disabled + localhost + ngrok apagado.
    # En PROD: dejar SIEMPRE en False. Default seguro = False.
    "auth_disabled": False,
    # ── Backups de la base de datos ────────────────────────────────────────────
    # Ruta relativa a la carpeta del proyecto, o absoluta. Default: "backups".
    "backup_dir": "backups",
    # ── Paletas de colores — editables desde Settings ──────────────────────────
    # 22 variables base. Los aliases (--color-primario, etc.) siguen en style.css
    # como var() y NO se mueven aquí.
    "paleta_light": {
        "acento":         "#4f46e5",
        "acento-oscuro":  "#4338ca",
        "fondo":          "#f9fafb",
        "superficie":     "#ffffff",
        "texto":          "#111827",
        "texto-muted":    "#6b7280",
        "texto-invertido": "#ffffff",
        "borde":          "#e5e7eb",
        "exito":          "#10b981",
        "alerta":         "#f59e0b",
        "peligro":        "#ef4444",
        "exito-suave":    "#d1fae5",
        "alerta-suave":   "#fef3c7",
        "peligro-suave":  "#fee2e2",
        "persona-elias":  "#0284c7",
        "persona-mari":   "#7c3aed",
        "moneda-ars":     "#74acdf",
        "moneda-usd":     "#3d8b37",
        "deco-1":         "#1f2937",
        "deco-2":         "#374151",
        "deco-3":         "#6b7280",
        "deco-4":         "#d1d5db",
    },
    "paleta_dark": {
        "acento":         "#6366f1",
        "acento-oscuro":  "#4f46e5",
        "fondo":          "#0f172a",
        "superficie":     "#1e293b",
        "texto":          "#e5e7eb",
        "texto-muted":    "#94a3b8",
        "texto-invertido": "#ffffff",
        "borde":          "#334155",
        "exito":          "#34d399",
        "alerta":         "#fbbf24",
        "peligro":        "#f87171",
        "exito-suave":    "#064e3b",
        "alerta-suave":   "#78350f",
        "peligro-suave":  "#7f1d1d",
        "persona-elias":  "#38bdf8",
        "persona-mari":   "#a78bfa",
        "moneda-ars":     "#8cbce6",
        "moneda-usd":     "#5cb85c",
        "deco-1":         "#0b1220",
        "deco-2":         "#1e293b",
        "deco-3":         "#64748b",
        "deco-4":         "#334155",
    },
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
            # Paletas: merge por clave. Si config.json trae una paleta guardada
            # vieja (menos claves que DEFAULTS), las claves nuevas de DEFAULTS
            # sobreviven (ej. texto-invertido agregado en 2026-07).
            for paleta in ('paleta_light', 'paleta_dark'):
                base = dict(DEFAULTS.get(paleta, {}))
                base.update(datos.get(paleta) or {})
                cfg[paleta] = base
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
