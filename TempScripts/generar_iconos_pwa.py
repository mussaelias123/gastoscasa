# =============================================================================
# ARCHIVO: TempScripts/generar_iconos_pwa.py
# =============================================================================
#
# QUÉ HACE:
#   Genera los tres PNG que consume el manifest de la PWA, a partir del MISMO
#   logo que ya usa la app: el favicon "N" de `templates/base.html` (cuadrado
#   redondeado con el violeta del acento + la letra en blanco).
#
#       static/img/icon-192.png            192x192  purpose "any"
#       static/img/icon-512.png            512x512  purpose "any"
#       static/img/icon-512-maskable.png   512x512  purpose "maskable"
#
# POR QUÉ ES UN SCRIPT ONE-SHOT (TempScripts/, regla 3 de CLAUDE.md):
#   Los íconos son archivos binarios versionados en el repo. La app NO los
#   genera en runtime y NO importa Pillow: por eso Pillow no va a
#   `requirements.txt`. Este script se corre a mano solo si cambia el logo o
#   el color de acento:
#
#       pip install pillow
#       python TempScripts/generar_iconos_pwa.py
#
# COLORES:
#   Se leen de `config.json → paleta_light` (`acento` y `texto-invertido`), no
#   se escriben a mano acá. Un PNG igual NO puede leer `var(--color-...)`: una
#   vez generado, el color queda horneado en el binario. Es la misma excepción
#   documentada del favicon (CLAUDE.md punto 4, regla 1) — si se cambia el
#   acento en Settings, hay que volver a correr este script.
#
# GEOMETRÍA (calcada del favicon SVG, viewBox 0 0 100 100):
#   - rect redondeado rx=22       → radio = 22% del lado
#   - text font-size=70 y=72 x=50 → tipografía = 70% del lado,
#                                    línea de base a 72%, centrada
#   Se dibuja a 4x y se reduce con LANCZOS: bordes y curva de la letra suaves.
#
# MASKABLE:
#   Android/Chrome recortan el ícono con la forma que quiera el launcher
#   (círculo, gota, rombo). Solo el 80% central está garantizado. Por eso la
#   versión maskable va a sangre (cuadrado lleno, sin esquinas redondeadas ni
#   transparencia) y la "N" se dibuja al 80% → ~10% de aire por lado.
# =============================================================================

import json
import os

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
DEST_DIR = os.path.join(BASE_DIR, 'static', 'img')

SS = 4  # supersampling: se dibuja a 4x y se baja con LANCZOS

# Segoe UI Bold es la primera de la pila del favicon ("Segoe UI,Arial,...").
FUENTES = [
    r'C:\Windows\Fonts\segoeuib.ttf',   # Segoe UI Bold
    r'C:\Windows\Fonts\arialbd.ttf',    # Arial Bold (fallback de la pila)
]

LETRA = 'N'


def _hex_a_rgb(valor, defecto):
    """'#4f46e5' → (79, 70, 229). Si el hex no sirve, cae al defecto."""
    txt = (valor or '').strip().lstrip('#')
    if len(txt) != 6:
        return defecto
    try:
        return tuple(int(txt[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return defecto


def _cargar_colores():
    """Lee acento y texto-invertido de config.json → paleta_light."""
    try:
        with open(CONFIG_FILE, encoding='utf-8') as f:
            paleta = json.load(f).get('paleta_light', {})
    except (OSError, ValueError):
        paleta = {}
    fondo = _hex_a_rgb(paleta.get('acento'), (79, 70, 229))
    letra = _hex_a_rgb(paleta.get('texto-invertido'), (255, 255, 255))
    return fondo, letra


def _cargar_fuente(tam):
    for ruta in FUENTES:
        if os.path.exists(ruta):
            return ImageFont.truetype(ruta, tam)
    raise SystemExit('ERROR: no se encontró ninguna fuente de la lista FUENTES.')


def generar(lado, destino, maskable=False):
    """Dibuja un ícono de `lado`x`lado` px y lo guarda en `destino`.

    maskable=False → tile redondeado sobre fondo transparente (purpose "any").
    maskable=True  → cuadrado lleno a sangre y letra al 80% (purpose "maskable").
    """
    fondo, color_letra = _cargar_colores()
    px = lado * SS

    lienzo = Image.new('RGBA', (px, px), (0, 0, 0, 0))
    dibujo = ImageDraw.Draw(lienzo)

    if maskable:
        # A sangre: sin esquinas redondeadas ni transparencia. El launcher
        # recorta la forma que quiera y siempre encuentra color debajo.
        dibujo.rectangle([0, 0, px, px], fill=fondo + (255,))
        escala = 0.80  # zona segura: ~10% de aire por lado
    else:
        dibujo.rounded_rectangle([0, 0, px - 1, px - 1],
                                 radius=int(px * 0.22),
                                 fill=fondo + (255,))
        escala = 1.0

    # Proporciones del favicon SVG, escaladas por `escala` respecto del centro.
    fuente = _cargar_fuente(int(px * 0.70 * escala))
    base_y = px / 2 + (0.72 - 0.5) * px * escala   # línea de base
    dibujo.text((px / 2, base_y), LETRA, font=fuente,
                fill=color_letra + (255,), anchor='ms')

    icono = lienzo.resize((lado, lado), Image.LANCZOS)
    if maskable:
        # Sin canal alfa: deja explícito que va a sangre y pesa menos.
        icono = icono.convert('RGB')
    icono.save(destino, 'PNG', optimize=True)
    print(f'OK: {destino}  ({lado}x{lado}{", maskable" if maskable else ""})')


if __name__ == '__main__':
    os.makedirs(DEST_DIR, exist_ok=True)
    generar(192, os.path.join(DEST_DIR, 'icon-192.png'))
    generar(512, os.path.join(DEST_DIR, 'icon-512.png'))
    generar(512, os.path.join(DEST_DIR, 'icon-512-maskable.png'), maskable=True)
