#ifndef AppVersion
#define AppVersion "0.0.0"
#endif

#ifndef SourceRoot
#define SourceRoot "..\..\"
#endif

#ifndef OutputDir
#define OutputDir "..\..\artifacts\installer"
#endif

#ifndef SetupMode
#define SetupMode "both"
#endif

#ifndef SetupAuthToken
#define SetupAuthToken "change-me-token"
#endif

#ifndef SetupServerHost
#define SetupServerHost "0.0.0.0"
#endif

#ifndef SetupServerPort
#define SetupServerPort "8089"
#endif

#ifndef SetupRoutingMode
#define SetupRoutingMode "server_managed"
#endif

#ifndef SetupServerUrl
#define SetupServerUrl ""
#endif

[Setup]
AppId={{B61EB78D-9120-4FD1-8FF6-573009A13268}
AppName=PDF2TSPL Print Automation
AppVersion={#AppVersion}
AppPublisher=PDF2TSPL Team
DefaultDirName={autopf64}\Pdf2Tspl
DefaultGroupName=PDF2TSPL
OutputDir={#OutputDir}
OutputBaseFilename=Pdf2TsplSetup_v{#AppVersion}
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
WizardStyle=modern
DisableDirPage=no
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\setup_windows.bat

[Files]
Source: "{#SourceRoot}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: ".git\*,.venv\*,__pycache__\*,logs\*,agent_work\*,print_automation.db*,*.pyc,build\*,artifacts\*"

[Icons]
Name: "{group}\PDF2TSPL Setup (Admin)"; Filename: "{app}\setup_windows.bat"
Name: "{group}\README"; Filename: "{app}\README.md"

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\setup_windows.ps1"" -Mode {#SetupMode} -InstallDir ""{app}"" -AuthToken ""{#SetupAuthToken}"" -ServerHost ""{#SetupServerHost}"" -ServerPort {#SetupServerPort} -RoutingMode {#SetupRoutingMode} -ServerUrl ""{#SetupServerUrl}"""; Description: "Run initial setup now (recommended)"; Flags: postinstall waituntilterminated skipifsilent
