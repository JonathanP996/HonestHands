; The HonestHands installer for Windows (Inno Setup). Per-user: no administrator prompt, installs to the user's own programs folder.
#ifndef AppVersion
  #define AppVersion "1.0"
#endif
#ifndef AppBuild
  #define AppBuild "0"
#endif

[Setup]
AppId={{8E7C1F42-4F0B-4D43-9F3E-7A5B1C2D9E10}
AppName=HonestHands
AppVersion={#AppVersion}.{#AppBuild}
AppPublisher=HonestHands
DefaultDirName={localappdata}\Programs\HonestHands
DefaultGroupName=HonestHands
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=HonestHands-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\HonestHands.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Files]
Source: "dist\HonestHands\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\HonestHands"; Filename: "{app}\HonestHands.exe"
Name: "{autodesktop}\HonestHands"; Filename: "{app}\HonestHands.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Add a shortcut to the desktop"; Flags: unchecked

[Run]
Filename: "{app}\HonestHands.exe"; Description: "Open HonestHands"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "schtasks"; Parameters: "/Delete /TN HonestHandsKeepAlive /F"; Flags: runhidden; RunOnceId: "RemoveKeepAlive"
