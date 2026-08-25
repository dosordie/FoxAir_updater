#define MyAppName "FoxAir Updater"
#define MyAppExeName "FoxAir_Updater.exe"
#define MyAppVersion "0.2.1"
#define MyAppPublisher "DosOrDie"

[Setup]
AppId={{8E4C04CE-4327-4C54-BB0A-6A0D8D88B1E2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\FoxAir Updater
DefaultGroupName=FoxAir Updater
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=FoxAir_Updater_Setup_v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\app_icon.ico
LicenseFile=..\..\..\LICENSE
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Files]
Source: "..\..\..\dist\FoxAir_Updater\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\FoxAir Updater"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\FoxAir Updater"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknuepfung erstellen"; GroupDescription: "Optionale Verknuepfungen:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "FoxAir Updater starten"; Flags: nowait postinstall skipifsilent
