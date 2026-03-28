; Inno Setup Script para Gastos Casa
; Requiere Inno Setup 6.x  https://jrsoftware.org/isinfo.php
;
; Genera: Output\GastosCasa_Setup_1.0.0.exe

#define AppName      "Gastos Casa"
#define AppVersion   "1.0.0"
#define AppPublisher "Elias"
#define AppExeName   "GastosCasa.exe"
#define ServiceName  "GastosCasa"
#define AppURL       "http://localhost:5000"
; Path al dist generado por PyInstaller (relativo a este .iss)
#define DistDir      "..\dist\GastosCasa"
; Path a nssm.exe descargado por download_nssm.ps1
#define NssmExe      "nssm\nssm.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
DefaultDirName={autopf}\GastosCasa
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; El instalador requiere privilegios de admin para instalar el servicio
PrivilegesRequired=admin
OutputDir=Output
OutputBaseFilename=GastosCasa_Setup_{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Crear icono en el escritorio
ChangesAssociations=no
; Minimo Windows 10
MinVersion=10.0

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear icono en el escritorio"; GroupDescription: "Iconos adicionales:"; Flags: unchecked

[Dirs]
; Crear carpeta de datos de usuario en AppData (compartida entre usuarios del servicio)
Name: "{commonappdata}\GastosCasa"
Name: "{commonappdata}\GastosCasa\logs"
Name: "{commonappdata}\GastosCasa\data"

[Files]
; Copiar todos los archivos del dist de PyInstaller
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Copiar nssm.exe a la carpeta de instalacion (no visible para el usuario)
Source: "{#NssmExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Acceso directo en el menu inicio que abre el navegador
Name: "{group}\{#AppName}"; Filename: "{app}\open_browser.bat"; WorkingDir: "{app}"; Comment: "Abrir Gastos Casa en el navegador"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"

; Acceso directo en escritorio (solo si se eligio la tarea)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\open_browser.bat"; WorkingDir: "{app}"; Comment: "Abrir Gastos Casa en el navegador"; Tasks: desktopicon

[Run]
; Detener servicio si ya existe (actualizacion)
Filename: "sc.exe"; Parameters: "stop {#ServiceName}"; Flags: runhidden waituntilterminated; StatusMsg: "Deteniendo servicio anterior..."; Check: ServiceExists

; Eliminar servicio anterior si existe
Filename: "{app}\nssm.exe"; Parameters: "remove {#ServiceName} confirm"; Flags: runhidden waituntilterminated; StatusMsg: "Eliminando servicio anterior..."; Check: ServiceExists

; Crear carpetas de logs y datos
Filename: "cmd.exe"; Parameters: "/c mkdir ""{commonappdata}\GastosCasa\logs"" 2>nul & mkdir ""{commonappdata}\GastosCasa\data"" 2>nul"; Flags: runhidden waituntilterminated; StatusMsg: "Creando carpetas de datos..."

; Instalar y configurar el servicio Windows con NSSM
Filename: "{app}\nssm.exe"; Parameters: "install {#ServiceName} ""{app}\{#AppExeName}"""; Flags: runhidden waituntilterminated; StatusMsg: "Instalando servicio Windows..."
Filename: "{app}\nssm.exe"; Parameters: "set {#ServiceName} AppDirectory ""{app}"""; Flags: runhidden waituntilterminated; StatusMsg: "Configurando directorio del servicio..."
Filename: "{app}\nssm.exe"; Parameters: "set {#ServiceName} DisplayName ""{#AppName}"""; Flags: runhidden waituntilterminated; StatusMsg: "Configurando nombre del servicio..."
Filename: "{app}\nssm.exe"; Parameters: "set {#ServiceName} Description ""Aplicacion de control de gastos personales"""; Flags: runhidden waituntilterminated; StatusMsg: "Configurando descripcion del servicio..."
Filename: "{app}\nssm.exe"; Parameters: "set {#ServiceName} Start SERVICE_AUTO_START"; Flags: runhidden waituntilterminated; StatusMsg: "Configurando inicio automatico..."
Filename: "{app}\nssm.exe"; Parameters: "set {#ServiceName} AppStdout ""{commonappdata}\GastosCasa\logs\service.log"""; Flags: runhidden waituntilterminated; StatusMsg: "Configurando log de salida..."
Filename: "{app}\nssm.exe"; Parameters: "set {#ServiceName} AppStderr ""{commonappdata}\GastosCasa\logs\error.log"""; Flags: runhidden waituntilterminated; StatusMsg: "Configurando log de errores..."

; Iniciar el servicio
Filename: "sc.exe"; Parameters: "start {#ServiceName}"; Flags: runhidden waituntilterminated; StatusMsg: "Iniciando servicio..."

; Abrir el navegador al finalizar (opcional, con checkbox)
Filename: "{app}\open_browser.bat"; Description: "Abrir Gastos Casa en el navegador"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; Detener el servicio antes de desinstalar
Filename: "sc.exe"; Parameters: "stop {#ServiceName}"; Flags: runhidden waituntilterminated; RunOnceId: "StopService"
; Eliminar el servicio de Windows
Filename: "{app}\nssm.exe"; Parameters: "remove {#ServiceName} confirm"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveService"

[UninstallDelete]
; Eliminar archivos generados en runtime que Inno Setup no rastrea
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
// Funcion auxiliar: verifica si el servicio de Windows ya existe
function ServiceExists: Boolean;
var
  ResultCode: Integer;
begin
  Exec('sc.exe', 'query {#ServiceName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := (ResultCode = 0);
end;

// Al finalizar la instalacion, crear el archivo open_browser.bat
procedure CurStepChanged(CurStep: TSetupStep);
var
  BatchContent: String;
  BatchFile: String;
begin
  if CurStep = ssPostInstall then
  begin
    BatchFile := ExpandConstant('{app}\open_browser.bat');
    BatchContent := '@echo off' + #13#10 +
                    'start "" "http://localhost:5000"' + #13#10;
    SaveStringToFile(BatchFile, BatchContent, False);
  end;
end;
