#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef PackageDir
  #error PackageDir is required
#endif

[Setup]
AppId=BensonMail
AppName={cm:AppName}
AppVersion={#AppVersion}
VersionInfoVersion=1.0.0.0
VersionInfoProductVersion=1.0.0.0
VersionInfoProductTextVersion={#AppVersion}
AppPublisher=Benson
DefaultDirName={localappdata}\Programs\BensonMail
AppendDefaultDirName=yes
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist
OutputBaseFilename=BensonMail-Windows-x64-Setup-{#AppVersion}
SetupIconFile=..\assets\mail.ico
Uninstallable=no
CreateAppDir=yes
CloseApplications=no
RestartApplications=no
AppMutex=Local\BensonMail-{username}
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern dynamic windows11
WizardSizePercent=115,115
ShowLanguageDialog=auto
LanguageDetectionMethod=uilanguage
SetupLogging=yes
DisableWelcomePage=no
DisableReadyPage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[LangOptions]
DialogFontName=Segoe UI
DialogFontSize=10

[CustomMessages]
english.AppName=Mail Secretary
english.UninstallName=Uninstall Mail Secretary
english.ShortcutChoices=Choose shortcuts (each option is independent):
english.DesktopApp=Create a desktop shortcut for Mail Secretary
english.DesktopUninstall=Create a desktop shortcut for the uninstaller
english.StartApp=Create a Start menu entry for Mail Secretary
english.StartUninstall=Create a Start menu entry for the uninstaller
english.RunApp=Open Mail Secretary
english.DedicatedFolder=Please use a dedicated folder named BensonMail. Browse can select its parent folder.
chinesesimp.AppName=邮件小秘书
chinesesimp.UninstallName=卸载邮件小秘书
chinesesimp.ShortcutChoices=选择快捷方式（四项可分别勾选）：
chinesesimp.DesktopApp=创建桌面快捷方式
chinesesimp.DesktopUninstall=创建卸载程序的桌面快捷方式
chinesesimp.StartApp=创建开始菜单项目
chinesesimp.StartUninstall=创建卸载程序的开始菜单项目
chinesesimp.RunApp=打开邮件小秘书
chinesesimp.DedicatedFolder=请使用名为 BensonMail 的专用文件夹。“浏览”可选择它所在的位置。
english.FolderInUse=The selected folder contains other files. Please choose an empty, dedicated BensonMail folder.
chinesesimp.FolderInUse=所选文件夹中已有其他文件，请选择空的 BensonMail 专用文件夹。

[Tasks]
Name: "desktopapp"; Description: "{cm:DesktopApp}"; GroupDescription: "{cm:ShortcutChoices}"
Name: "desktopuninstall"; Description: "{cm:DesktopUninstall}"
Name: "startapp"; Description: "{cm:StartApp}"
Name: "startuninstall"; Description: "{cm:StartUninstall}"

[InstallDelete]
Type: files; Name: "{app}\BensonMail-*.exe"
Type: files; Name: "{app}\Uninstall-BensonMail-*.exe"

[Files]
Source: "{#PackageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "installed.json"; DestDir: "{app}"; DestName: ".benson-installed.json"; Flags: ignoreversion

[Icons]
Name: "{code:ShortcutName|desktopapp}"; Filename: "{app}\BensonMail-{#AppVersion}.exe"; WorkingDir: "{app}"; Tasks: desktopapp
Name: "{code:ShortcutName|desktopuninstall}"; Filename: "{app}\Uninstall-BensonMail-{#AppVersion}.exe"; WorkingDir: "{app}"; Tasks: desktopuninstall
Name: "{code:ShortcutName|startapp}"; Filename: "{app}\BensonMail-{#AppVersion}.exe"; WorkingDir: "{app}"; Tasks: startapp
Name: "{code:ShortcutName|startuninstall}"; Filename: "{app}\Uninstall-BensonMail-{#AppVersion}.exe"; WorkingDir: "{app}"; Tasks: startuninstall

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\BensonMail"; ValueType: string; ValueName: "DisplayName"; ValueData: "{cm:AppName}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\BensonMail"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#AppVersion}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\BensonMail"; ValueType: string; ValueName: "Publisher"; ValueData: "Benson"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\BensonMail"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\BensonMail"; ValueType: string; ValueName: "DisplayIcon"; ValueData: "{app}\BensonMail-{#AppVersion}.exe"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\BensonMail"; ValueType: string; ValueName: "UninstallString"; ValueData: """{app}\Uninstall-BensonMail-{#AppVersion}.exe"""
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\BensonMail"; ValueType: dword; ValueName: "NoModify"; ValueData: "1"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\BensonMail"; ValueType: dword; ValueName: "NoRepair"; ValueData: "1"

[Run]
Filename: "{app}\BensonMail-{#AppVersion}.exe"; Description: "{cm:RunApp}"; Flags: nowait postinstall skipifsilent

[Code]
var
  PreviousInstallDirectory: String;

function InitializeSetup: Boolean;
begin
  RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\BensonMail',
    'InstallLocation', PreviousInstallDirectory);
  Result := True;
end;

function IsOurExecutable(const Name: String): Boolean;
var
  Stem, Version: String;
  I: Integer;
begin
  Stem := Lowercase(Name);
  Result := (Stem = 'bensonmail.exe') or (Stem = 'uninstall.exe');
  if Result then Exit;
  if Copy(Stem, 1, 11) = 'bensonmail-' then
    Version := Copy(Stem, 12, Length(Stem))
  else if Copy(Stem, 1, 21) = 'uninstall-bensonmail-' then
    Version := Copy(Stem, 22, Length(Stem))
  else Exit;
  if (Length(Version) <> 16) or (Copy(Version, 13, 4) <> '.exe') then Exit;
  for I := 1 to 12 do
    if (Version[I] < '0') or (Version[I] > '9') then Exit;
  Result := True;
end;

function IsOurShortcut(const Filename: String): Boolean;
var
  Shell, Link: Variant;
  Target, Directory: String;
begin
  Result := False;
  try
    Shell := CreateOleObject('WScript.Shell');
    Link := Shell.CreateShortcut(Filename);
    Target := Link.TargetPath;
    Directory := RemoveBackslashUnlessRoot(ExtractFileDir(Target));
    Result := IsOurExecutable(ExtractFileName(Target)) and
      ((CompareText(Directory, RemoveBackslashUnlessRoot(ExpandConstant('{app}'))) = 0) or
       ((PreviousInstallDirectory <> '') and
        (CompareText(Directory, RemoveBackslashUnlessRoot(PreviousInstallDirectory)) = 0)));
  except
    Log('Preserving an unreadable shortcut: ' + Filename);
  end;
end;

procedure RemoveOldShortcuts(const Directory: String);
var
  Entry: TFindRec;
  Filename: String;
begin
  if FindFirst(AddBackslash(Directory) + '*.lnk', Entry) then
  begin
    try
      repeat
        Filename := AddBackslash(Directory) + Entry.Name;
        if IsOurShortcut(Filename) then
          if not DeleteFile(Filename) then
            RaiseException('Could not remove the previous Mail Secretary shortcut: ' + Filename);
      until not FindNext(Entry);
    finally
      FindClose(Entry);
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    { Clear this application's old choices, including names in the other UI language. }
    RemoveOldShortcuts(ExpandConstant('{userdesktop}'));
    RemoveOldShortcuts(ExpandConstant('{userprograms}'));
  end;
end;

function ShortcutName(Param: String): String;
var
  Directory, LabelText, Candidate: String;
  Number: Integer;
begin
  if (Param = 'desktopapp') or (Param = 'desktopuninstall') then
    Directory := ExpandConstant('{userdesktop}')
  else
    Directory := ExpandConstant('{userprograms}');
  if (Param = 'desktopuninstall') or (Param = 'startuninstall') then
    LabelText := CustomMessage('UninstallName')
  else
    LabelText := CustomMessage('AppName');
  Number := 1;
  repeat
    Candidate := AddBackslash(Directory) + LabelText;
    if Number > 1 then Candidate := Candidate + ' (' + IntToStr(Number) + ')';
    Result := Candidate;
    { Never overwrite another application's shortcut, even when its name matches. }
    if not FileExists(Candidate + '.lnk') then Exit;
    if IsOurShortcut(Candidate + '.lnk') then Exit;
    Number := Number + 1;
  until Number > 999;
  RaiseException('Unable to choose a free shortcut name.');
end;

function InstallDirectoryError: String;
var
  Directory: String;
  Entry: TFindRec;
begin
  Result := '';
  Directory := RemoveBackslashUnlessRoot(WizardDirValue);
  if CompareText(ExtractFileName(Directory), 'BensonMail') <> 0 then
  begin
    Result := CustomMessage('DedicatedFolder');
    Exit;
  end;
  if FileExists(AddBackslash(Directory) + '.benson-installed.json') then Exit;
  if DirExists(AddBackslash(Directory) + '_internal') then Exit;
  if FindFirst(AddBackslash(Directory) + '*', Entry) then
  begin
    try
      repeat
        if (Entry.Name <> '.') and (Entry.Name <> '..') then
        begin
          Result := CustomMessage('FolderInUse');
          Exit;
        end;
      until not FindNext(Entry);
    finally
      FindClose(Entry);
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := InstallDirectoryError;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ErrorText: String;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    ErrorText := InstallDirectoryError;
    if ErrorText <> '' then
    begin
      MsgBox(ErrorText, mbError, MB_OK);
      Result := False;
    end;
  end;
end;
