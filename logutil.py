# =============================================================================
# ARCHIVO: logutil.py
# =============================================================================
#
# QUÉ ES ESTE ARCHIVO:
#   Helper único de logging de la app. Toda línea de log sale por log(),
#   que antepone fecha y hora para que el archivo sea seguible.
#
# CONVENCIÓN (ver docs/CONTEXT_DEPLOY.md → "Convención de logs"):
#   AA/MM/DD-HH:MM:SS | OK:/AVISO:/ERROR: mensaje
#   Ejemplo: 26/06/11-14:30:55 | OK: Backup de DB (manual): fondo_2026-06-11_14-30.db
#
#   - El timestamp lo agrega log(); el mensaje NO debe traer fecha/hora propia.
#   - NO usar print() directo para logs: siempre log() de este módulo.
#   - flush=True para que NSSM escriba el archivo al instante (sin buffer).
# =============================================================================

from datetime import datetime


def log(mensaje):
    """Imprime una línea de log con timestamp: AA/MM/DD-HH:MM:SS | mensaje."""
    print(f"{datetime.now():%y/%m/%d-%H:%M:%S} | {mensaje}", flush=True)
