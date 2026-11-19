; Inno Setup script for RevelateTW Lite.
; The desktop and Start menu shortcuts point at RevelateTWLite.exe, so they
; inherit the exe icon (set by PyInstaller --icon in build_lite.bat) for free.
; SetupIconFile below gives the installer itself the same icon.

#define MyAppName "RevelateTW Lite"
#define MyAppExeName "RevelateTWLite.exe"

[Setup]
AppId={{3B9A6F4E-7D5B-4C2A-9F1E-8C4D5E6F7A8B}
AppName={#MyAppName}
AppVersion=1.0
DefaultDirName={autopf}\RevelateTW Lite
DefaultGroupName=RevelateTW Lite
DisableProgramGroupPage=yes
OutputBaseFilename=RevelateTWLitesetup
SetupIconFile=..\lite\revelatelite\resources\logo_icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "..\dist\RevelateTWLite\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\RevelateTW Lite"; Filename: "{app}\{#MyAppExeName}"
Name: "{autoprograms}\RevelateTW Lite"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch RevelateTW Lite"; Flags: nowait postinstall skipifsilent
