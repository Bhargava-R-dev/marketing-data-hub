#define AppName "Marketing Data Hub"
#define AppVersion GetEnv("HUB_VERSION")
#if AppVersion == ""
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{7E1C5C1A-2B2E-4B9E-9C2A-4D6F8A1B2C3D}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Growth by Bhargava
AppPublisherURL=https://growthbybhargava.com/tools/marketing-data-hub
AppSupportURL=https://github.com/Bhargava-R-dev/marketing-data-hub/issues
DefaultDirName={localappdata}\Programs\MarketingDataHub
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=MarketingDataHub-Setup
SetupIconFile=..\src\hub\resources\hub.ico
UninstallDisplayIcon={app}\MarketingDataHub.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "dist\MarketingDataHub\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\MarketingDataHub.exe"; IconFilename: "{app}\_internal\hub\resources\hub.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\MarketingDataHub.exe"; IconFilename: "{app}\_internal\hub\resources\hub.ico"

[Run]
Filename: "{app}\MarketingDataHub.exe"; Description: "Open Marketing Data Hub now"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "{app}\hub.exe"; Parameters: "schedule --remove"; Flags: runhidden; RunOnceId: "RemoveTask"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Messages]
FinishedLabel=Installed. Your data and settings live in your user folder under AppData\Local\MarketingDataHub — they are kept if you ever uninstall.
