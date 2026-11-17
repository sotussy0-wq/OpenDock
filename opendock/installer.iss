[Setup]
AppName=OpenDock
AppVersion=1.0.0
AppPublisher=OpenDock
AppMutex=OpenDockSingleInstance
DefaultDirName={autopf}\OpenDock
DefaultGroupName=OpenDock
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer_out
OutputBaseFilename=OpenDock-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\OpenDock.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start OpenDock when Windows starts"

[Files]
Source: "dist\OpenDock.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\OpenDock"; Filename: "{app}\OpenDock.exe"
Name: "{group}\Uninstall OpenDock"; Filename: "{uninstallexe}"
Name: "{autodesktop}\OpenDock"; Filename: "{app}\OpenDock.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "OpenDock"; ValueData: """{app}\OpenDock.exe"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\OpenDock.exe"; Description: "Launch OpenDock"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/f /im OpenDock.exe"; Flags: runhidden; RunOnceId: "KillOpenDock"
