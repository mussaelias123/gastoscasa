# Gastos Casa — Build Guide

Guía para generar el instalador Windows (`.exe`) desde el código fuente.

---

## Pre-requisitos

| Herramienta | Versión mínima | Instalación |
|-------------|---------------|-------------|
| Python | 3.10+ | https://www.python.org/downloads/ |
| pip | (incluido con Python) | — |
| PyInstaller | 6.x | `pip install pyinstaller` |
| Inno Setup | 6.x | https://jrsoftware.org/isinfo.php |
| NSSM | 2.24 | Auto-descargado por `download_nssm.ps1` |

> **NSSM** (Non-Sucking Service Manager) se descarga automáticamente al correr `build.bat`.
> Si no hay internet, descargar manualmente desde https://nssm.cc/download y colocar
> el ejecutable en `build/nssm/nssm.exe`.

---

## Paso previo: ajustar app.py para el ejecutable

Antes de compilar, `app.py` debe manejar los paths correctamente cuando corre
como `.exe` congelado por PyInstaller. Agregar al inicio del archivo:

```python
import sys
import os

# Detectar si corre como .exe de PyInstaller
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Carpeta de datos del usuario (para la DB y config)
DATA_DIR = os.path.join(os.environ.get('APPDATA', BASE_DIR), 'GastosCasa')
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static'),
)
```

Y cambiar la ruta de la base de datos a:
```python
DB_PATH = os.path.join(DATA_DIR, 'gastos.db')
```

---

## Cómo correr el build completo

```bat
cd gastos-casa\build
build.bat
```

Esto ejecuta los 5 pasos en orden y genera el instalador en:
```
build\Output\GastosCasa_Setup_1.0.0.exe
```

### Opciones del build.bat

```bat
build.bat                    # Build completo (PyInstaller + Inno Setup)
build.bat --only-pyinstaller # Solo genera el .exe sin crear el instalador
build.bat --only-inno        # Solo crea el instalador (asume que ya existe el dist/)
```

---

## Qué hace cada archivo

### `gastos-casa.spec`
Archivo de configuración de **PyInstaller**. Define:
- Entry point: `app.py`
- Archivos a incluir: `templates/`, `static/`, `.env.example`
- Archivos a excluir: `.env`, `gastos.db`
- Nombre del ejecutable: `GastosCasa.exe`
- Modo: `onedir` (carpeta, no un solo .exe) — mejor para Flask con templates
- Sin ventana de consola (`console=False`)

El resultado queda en `dist/GastosCasa/`.

### `setup_installer.iss`
Script de **Inno Setup** que genera el instalador `.exe`. Hace:
1. Copia todos los archivos de `dist/GastosCasa/` a `C:\Program Files\GastosCasa\`
2. Copia `nssm.exe` a la carpeta de instalación
3. Crea carpeta de datos en `C:\ProgramData\GastosCasa\`
4. Registra **GastosCasa como servicio Windows** (inicio automático)
5. Crea acceso directo en escritorio que abre `http://localhost:5000`
6. Incluye desinstalador que detiene y elimina el servicio

### `build.bat`
Orquestador del build. Verifica dependencias, descarga NSSM, ejecuta
PyInstaller e Inno Setup en orden, y reporta el resultado.

### `download_nssm.ps1`
Script PowerShell que descarga NSSM 2.24 desde `https://nssm.cc/release/nssm-2.24.zip`,
detecta si el sistema es 32 o 64-bit, extrae el binario correcto y lo coloca en
`build/nssm/nssm.exe`.

---

## Estructura de archivos generados

```
gastos-casa/
  build/
    nssm/
      nssm.exe              ← descargado automáticamente
    Output/
      GastosCasa_Setup_1.0.0.exe  ← INSTALADOR FINAL
  dist/
    GastosCasa/
      GastosCasa.exe        ← ejecutable Flask
      templates/            ← incluido en el bundle
      static/               ← incluido en el bundle
      *.dll, *.pyd, ...     ← dependencias Python
```

---

## Cómo actualizar la versión

1. Editar `setup_installer.iss`, cambiar la línea:
   ```
   #define AppVersion   "1.0.0"
   ```
2. El instalador se generará como `GastosCasa_Setup_X.Y.Z.exe`.

---

## Dónde quedan los datos en el equipo del usuario

| Elemento | Ubicación |
|----------|-----------|
| Ejecutable | `C:\Program Files\GastosCasa\GastosCasa.exe` |
| Base de datos | `C:\ProgramData\GastosCasa\` (o `%APPDATA%\GastosCasa\`) |
| Logs del servicio | `C:\ProgramData\GastosCasa\logs\service.log` |
| Logs de errores | `C:\ProgramData\GastosCasa\logs\error.log` |

---

## Solución de problemas

**PyInstaller no encuentra los templates en runtime**
→ Verificar que `app.py` usa `BASE_DIR` con `sys._MEIPASS` (ver sección "Paso previo").

**El servicio no inicia**
→ Revisar `C:\ProgramData\GastosCasa\logs\error.log`
→ Verificar que el puerto 5000 no esté ocupado: `netstat -ano | findstr :5000`

**Inno Setup no encuentra `dist\GastosCasa`**
→ Correr `build.bat --only-pyinstaller` primero y verificar que se genere `dist/GastosCasa/GastosCasa.exe`

**NSSM no se descarga**
→ Descargar manualmente: https://nssm.cc/download
→ Colocar en `build\nssm\nssm.exe`

**Error "acceso denegado" al instalar**
→ Ejecutar el instalador como Administrador (clic derecho → Ejecutar como administrador)
