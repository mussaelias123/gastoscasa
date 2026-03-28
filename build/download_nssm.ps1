# download_nssm.ps1
# Descarga NSSM 2.24 y extrae nssm.exe a build/nssm/nssm.exe
#
# Uso: powershell -ExecutionPolicy Bypass -File download_nssm.ps1

$ErrorActionPreference = "Stop"

$NssmVersion  = "2.24"
$NssmUrl      = "https://nssm.cc/release/nssm-$NssmVersion.zip"
$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$NssmDir      = Join-Path $ScriptDir "nssm"
$ZipPath      = Join-Path $ScriptDir "nssm-$NssmVersion.zip"
$NssmExeDest  = Join-Path $NssmDir "nssm.exe"

# Elegir el binario correcto segun la arquitectura
if ([Environment]::Is64BitOperatingSystem) {
    $NssmBinPath = "nssm-$NssmVersion\win64\nssm.exe"
    $Arch = "64-bit"
} else {
    $NssmBinPath = "nssm-$NssmVersion\win32\nssm.exe"
    $Arch = "32-bit"
}

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Descargando NSSM $NssmVersion ($Arch)" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Crear carpeta de destino
if (-not (Test-Path $NssmDir)) {
    New-Item -ItemType Directory -Path $NssmDir | Out-Null
    Write-Host "  Carpeta creada: $NssmDir" -ForegroundColor Gray
}

# 2. Si ya existe, no descargar de nuevo
if (Test-Path $NssmExeDest) {
    Write-Host "  nssm.exe ya existe en: $NssmExeDest" -ForegroundColor Green
    Write-Host "  Saltando descarga." -ForegroundColor Green
    exit 0
}

# 3. Descargar ZIP
Write-Host "  Descargando desde: $NssmUrl" -ForegroundColor Yellow
Write-Host "  Destino temporal:  $ZipPath" -ForegroundColor Gray
Write-Host ""

try {
    # Usar TLS 1.2 (requerido por nssm.cc)
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    $ProgressPreference = 'SilentlyContinue'  # Ocultar barra de progreso (mas rapido)
    Invoke-WebRequest -Uri $NssmUrl -OutFile $ZipPath -UseBasicParsing
    $ProgressPreference = 'Continue'

    Write-Host "  Descarga completada." -ForegroundColor Green
}
catch {
    Write-Host "  ERROR al descargar: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Descarga manual:" -ForegroundColor Yellow
    Write-Host "    1. Ir a https://nssm.cc/download" -ForegroundColor Yellow
    Write-Host "    2. Descargar nssm-$NssmVersion.zip" -ForegroundColor Yellow
    Write-Host "    3. Extraer win64\nssm.exe a: $NssmExeDest" -ForegroundColor Yellow
    exit 1
}

# 4. Extraer nssm.exe del ZIP
Write-Host ""
Write-Host "  Extrayendo nssm.exe..." -ForegroundColor Yellow

try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem

    $zip    = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    $entry  = $zip.Entries | Where-Object { $_.FullName -eq $NssmBinPath }

    if ($null -eq $entry) {
        $zip.Dispose()
        throw "No se encontro '$NssmBinPath' dentro del ZIP."
    }

    # Extraer a destino
    [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $NssmExeDest, $true)
    $zip.Dispose()

    Write-Host "  Extraido a: $NssmExeDest" -ForegroundColor Green
}
catch {
    if ($zip) { $zip.Dispose() }
    Write-Host "  ERROR al extraer: $_" -ForegroundColor Red
    exit 1
}
finally {
    # 5. Limpiar ZIP temporal
    if (Test-Path $ZipPath) {
        Remove-Item $ZipPath -Force
        Write-Host "  ZIP temporal eliminado." -ForegroundColor Gray
    }
}

# 6. Verificar resultado
if (Test-Path $NssmExeDest) {
    $size = (Get-Item $NssmExeDest).Length / 1KB
    Write-Host ""
    Write-Host "  OK: nssm.exe listo ($([math]::Round($size)) KB)" -ForegroundColor Green
    Write-Host ""
    exit 0
} else {
    Write-Host "  ERROR: nssm.exe no fue creado." -ForegroundColor Red
    exit 1
}
