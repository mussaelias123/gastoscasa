# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec para Gastos Casa
#
# IMPORTANTE: Antes de compilar, asegurarse de que app.py maneje
# correctamente los paths cuando corre como .exe congelado.
# Agregar al inicio de app.py:
#
#   import sys, os
#   if getattr(sys, 'frozen', False):
#       BASE_DIR = sys._MEIPASS
#   else:
#       BASE_DIR = os.path.dirname(os.path.abspath(__file__))
#
#   app = Flask(__name__,
#               template_folder=os.path.join(BASE_DIR, 'templates'),
#               static_folder=os.path.join(BASE_DIR, 'static'))
#
# La base de datos (gastos.db) debe guardarse fuera del _MEIPASS, por ejemplo:
#   DATA_DIR = os.path.join(os.environ.get('APPDATA', BASE_DIR), 'GastosCasa')
#   os.makedirs(DATA_DIR, exist_ok=True)
#   DB_PATH = os.path.join(DATA_DIR, 'gastos.db')

import os

block_cipher = None

# Paths relativos al directorio raiz del proyecto (un nivel arriba de build/)
PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'app.py')],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        # Incluir carpetas de templates y static
        (os.path.join(PROJECT_ROOT, 'templates'), 'templates'),
        (os.path.join(PROJECT_ROOT, 'static'),    'static'),
        # Incluir .env.example como referencia (NO el .env con secretos)
        (os.path.join(PROJECT_ROOT, '.env.example'), '.'),
    ],
    hiddenimports=[
        'flask',
        'flask.templating',
        'jinja2',
        'jinja2.ext',
        'werkzeug',
        'werkzeug.serving',
        'werkzeug.routing',
        'sqlite3',
        'json',
        'os',
        'sys',
        'win32service',
        'win32serviceutil',
        'win32event',
        'servicemanager',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # No incluir la DB, se crea en runtime
        'gastos.db',
        # No incluir archivos de desarrollo
        'pytest',
        'pytest_mock',
        'setuptools',
        'pip',
        'black',
        'flake8',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GastosCasa',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # console=False oculta la ventana de consola (modo produccion)
    # Cambiar a console=True para depuracion
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Descomentar si existe el icono:
    # icon=os.path.join(PROJECT_ROOT, 'static', 'favicon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GastosCasa',
)
