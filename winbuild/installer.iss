#ifndef Version
  #define Version "1.0.0"
#endif

[Setup]
AppId={{7A4C2E10-9B3D-4F58-A1C6-2E9D5B0F3A71}
AppName=WisprClone
AppVersion={#Version}
AppPublisher=rgonaute
WizardStyle=modern
DefaultDirName={localappdata}\Programs\WisprClone
DefaultGroupName=WisprClone
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=WisprClone-Setup
Compression=lzma2
SolidCompression=yes
AppMutex=Local\WisprClone
UninstallDisplayIcon={app}\WisprClone.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start WisprClone when Windows starts"
Name: "purgedata"; Description: "On uninstall, also delete settings, history, and the downloaded model"; Flags: unchecked

[Files]
Source: "..\dist\WisprClone\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\WisprClone"; Filename: "{app}\WisprClone.exe"
Name: "{group}\Uninstall WisprClone"; Filename: "{uninstallexe}"
Name: "{userdesktop}\WisprClone"; Filename: "{app}\WisprClone.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "WisprClone"; ValueData: """{app}\WisprClone.exe"""; Tasks: startup; Flags: uninsdeletevalue

[InstallDelete]
; Remove the old dev launcher so it doesn't double-launch alongside the installed app.
Type: files; Name: "{userstartup}\WisprClone.vbs"

[Run]
Filename: "{app}\WisprClone.exe"; Description: "Launch WisprClone"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\wisprclone"; Tasks: purgedata
Type: filesandordirs; Name: "{%USERPROFILE}\.cache\huggingface\hub\models--Systran--faster-whisper-*"; Tasks: purgedata
