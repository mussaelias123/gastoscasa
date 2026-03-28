@echo off
setlocal enabledelayedexpansion

:: ============================================================
:: build.bat - Script de build para Gastos Casa
:: Genera el instalador Windows (.exe) desde el codigo fuente
::
:: Uso: build.bat [opciones]
::   build.bat           - build completo
::   build.bat --only-pyinstaller  - solo PyInstaller
::   build.bat --only-inno         - solo Inno Setup
:: ============================================================

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "BUILD_DIR=%SCRIPT_DIR%"
set "DIST_DIR=%PROJECT_ROOT%\dist"
set "OUTPUT_DIR=%BUILD_DIR%Output"

:: Colores para output (requiere Windows 10+)
set "RED=[91m"
set "GREEN=[92m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "RESET=[0m"

echo.
echo %BLUE%============================================================%RESET%
echo %BLUE%  Gastos Casa - Build Script v1.0%RESET%
echo %BLUE%============================================================%RESET%
echo.

:: ---- Parsear argumentos ----
set ONLY_PYINSTALLER=0
set ONLY_INNO=0

if "%1"=="--only-pyinstaller" set ONLY_PYINSTALLER=1
if "%1"=="--only-inno"        set ONLY_INNO=1

:: ============================================================
:: PASO 1: Verificar Python y PyInstaller
:: ============================================================
if %ONLY_INNO%==0 (
    echo %YELLOW%[1/5] Verificando Python...%RESET%
    python --version >nul 2>&1
    if errorlevel 1 (
        echo %RED%ERROR: Python no encontrado en PATH.%RESET%
        echo        Instalar desde https://www.python.org/downloads/
        exit /b 1
    )
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo       %%i
    echo %GREEN%      OK%RESET%

    echo.
    echo %YELLOW%[2/5] Verificando PyInstaller...%RESET%
    python -m PyInstaller --version >nul 2>&1
    if errorlevel 1 (
        echo %YELLOW%      PyInstaller no encontrado. Instalando...%RESET%
        pip install pyinstaller
        if errorlevel 1 (
            echo %RED%ERROR: No se pudo instalar PyInstaller.%RESET%
            exit /b 1
        )
    )
    for /f "tokens=*" %%i in ('python -m PyInstaller --version 2^>^&1') do echo       PyInstaller %%i
    echo %GREEN%      OK%RESET%
)

:: ============================================================
:: PASO 2: Verificar Inno Setup
:: ============================================================
if %ONLY_PYINSTALLER%==0 (
    echo.
    echo %YELLOW%[3/5] Verificando Inno Setup...%RESET%
    set "ISCC_PATH="

    :: Buscar ISCC.exe en ubicaciones comunes
    if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
        set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    ) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
        set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
    ) else if exist "C:\Program Files (x86)\Inno Setup 5\ISCC.exe" (
        set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
    )

    if not defined ISCC_PATH (
        echo %RED%ERROR: Inno Setup no encontrado.%RESET%
        echo        Instalar desde https://jrsoftware.org/isinfo.php
        echo        Versiones probadas: 6.x
        exit /b 1
    )
    echo       Encontrado en: !ISCC_PATH!
    echo %GREEN%      OK%RESET%
)

:: ============================================================
:: PASO 3: Descargar NSSM si no existe
:: ============================================================
if %ONLY_PYINSTALLER%==0 (
    echo.
    echo %YELLOW%[4/5] Verificando NSSM...%RESET%

    if not exist "%BUILD_DIR%nssm\nssm.exe" (
        echo       NSSM no encontrado. Descargando...
        powershell -ExecutionPolicy Bypass -File "%BUILD_DIR%download_nssm.ps1"
        if errorlevel 1 (
            echo %RED%ERROR: No se pudo descargar NSSM.%RESET%
            echo        Descargar manualmente desde https://nssm.cc/download
            echo        y colocar nssm.exe en: %BUILD_DIR%nssm\nssm.exe
            exit /b 1
        )
    ) else (
        echo       nssm.exe encontrado en build\nssm\
    )
    echo %GREEN%      OK%RESET%
)

:: ============================================================
:: PASO 4: Correr PyInstaller
:: ============================================================
if %ONLY_INNO%==0 (
    echo.
    echo %YELLOW%[5a/5] Ejecutando PyInstaller...%RESET%
    echo       Spec: %BUILD_DIR%gastos-casa.spec
    echo       Output: %DIST_DIR%\GastosCasa\
    echo.

    :: Limpiar build anterior
    if exist "%PROJECT_ROOT%\dist\GastosCasa" (
        echo       Limpiando dist anterior...
        rmdir /s /q "%PROJECT_ROOT%\dist\GastosCasa"
    )
    if exist "%PROJECT_ROOT%\build\GastosCasa" (
        rmdir /s /q "%PROJECT_ROOT%\build\GastosCasa"
    )

    :: Correr PyInstaller desde la raiz del proyecto
    cd /d "%PROJECT_ROOT%"
    python -m PyInstaller "%BUILD_DIR%gastos-casa.spec" --noconfirm --clean

    if errorlevel 1 (
        echo.
        echo %RED%ERROR: PyInstaller fallo. Ver errores arriba.%RESET%
        exit /b 1
    )

    if not exist "%DIST_DIR%\GastosCasa\GastosCasa.exe" (
        echo %RED%ERROR: GastosCasa.exe no fue generado.%RESET%
        exit /b 1
    )

    echo.
    echo %GREEN%      PyInstaller completado.%RESET%
    echo       Ejecutable: %DIST_DIR%\GastosCasa\GastosCasa.exe
)

:: ============================================================
:: PASO 5: Correr Inno Setup
:: ============================================================
if %ONLY_PYINSTALLER%==0 (
    echo.
    echo %YELLOW%[5b/5] Ejecutando Inno Setup...%RESET%
    echo       Script: %BUILD_DIR%setup_installer.iss
    echo.

    :: Crear carpeta Output si no existe
    if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

    cd /d "%BUILD_DIR%"
    "!ISCC_PATH!" setup_installer.iss

    if errorlevel 1 (
        echo.
        echo %RED%ERROR: Inno Setup fallo. Ver errores arriba.%RESET%
        exit /b 1
    )

    echo.
    echo %GREEN%      Inno Setup completado.%RESET%
)

:: ============================================================
:: RESULTADO FINAL
:: ============================================================
echo.
echo %GREEN%============================================================%RESET%
echo %GREEN%  BUILD EXITOSO%RESET%
echo %GREEN%============================================================%RESET%
echo.

if %ONLY_PYINSTALLER%==0 (
    echo  Instalador generado en:
    echo  %OUTPUT_DIR%\GastosCasa_Setup_1.0.0.exe
    echo.
    echo  Para distribuir: copiar ese .exe a cualquier maquina Windows 10+
    echo  y ejecutar como administrador.
) else (
    echo  Ejecutable generado en:
    echo  %DIST_DIR%\GastosCasa\GastosCasa.exe
)

echo.
pause
endlocal
