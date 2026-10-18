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
DefaultDirName={code:DefaultInstallDirectory}
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
english.DeleteInstaller=Delete this installer after closing Setup
english.DedicatedFolder=Please use a dedicated folder named BensonMail. Browse can select its parent folder.
chinesesimp.AppName=邮件小秘书
chinesesimp.UninstallName=卸载邮件小秘书
chinesesimp.ShortcutChoices=选择快捷方式（四项可分别勾选）：
chinesesimp.DesktopApp=创建桌面快捷方式
chinesesimp.DesktopUninstall=创建卸载程序的桌面快捷方式
chinesesimp.StartApp=创建开始菜单项目
chinesesimp.StartUninstall=创建卸载程序的开始菜单项目
chinesesimp.RunApp=打开邮件小秘书
chinesesimp.DeleteInstaller=关闭安装程序后删除此安装程序
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
Name: "{userdesktop}\{code:ShortcutName|desktopapp}"; Filename: "{app}\BensonMail-{#AppVersion}.exe"; WorkingDir: "{app}"; Tasks: desktopapp
Name: "{userdesktop}\{code:ShortcutName|desktopuninstall}"; Filename: "{app}\Uninstall-BensonMail-{#AppVersion}.exe"; WorkingDir: "{app}"; Tasks: desktopuninstall
Name: "{userprograms}\{code:ShortcutName|startapp}"; Filename: "{app}\BensonMail-{#AppVersion}.exe"; WorkingDir: "{app}"; Tasks: startapp
Name: "{userprograms}\{code:ShortcutName|startuninstall}"; Filename: "{app}\Uninstall-BensonMail-{#AppVersion}.exe"; WorkingDir: "{app}"; Tasks: startuninstall

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

Filename: "{app}\MailWorker.exe"; Parameters: "--delete-installer ""{srcexe}"" --setup-pid {code:SetupProcessId} --installer-sha256 {code:SetupFingerprint}"; Description: "{cm:DeleteInstaller}"; Flags: postinstall unchecked nowait skipifsilent runhidden

[Code]
var
  PreviousInstallDirectory: String;
  TaskDefaultsApplied: Boolean;

function GetCurrentProcessId: LongWord;
  external 'GetCurrentProcessId@kernel32.dll stdcall';

function SetupProcessId(Param: String): String;
begin
  Result := IntToStr(GetCurrentProcessId);
end;

function SetupFingerprint(Param: String): String;
begin
  Result := GetSHA256OfFile(ExpandConstant('{srcexe}'));
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

function DefaultInstallDirectory(Param: String): String;
begin
  if (PreviousInstallDirectory <> '') and FileExists(AddBackslash(PreviousInstallDirectory) + '.benson-installed.json') then
    Result := PreviousInstallDirectory
  else Result := ExpandConstant('{localappdata}\Programs\BensonMail');
end;

function OpenProcess(Access: LongWord; InheritHandle: Boolean; ProcessId: LongWord): THandle;
  external 'OpenProcess@kernel32.dll stdcall';
function QueryFullProcessImageName(ProcessHandle: THandle; Flags: LongWord; ExeName: String; var Size: LongWord): Boolean;
  external 'QueryFullProcessImageNameW@kernel32.dll stdcall';
function WaitForSingleObject(Handle: THandle; Milliseconds: LongWord): LongWord;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function InitializeSetup: Boolean;
var
  ParentId, WaitResult, Size: LongWord;
  Handle: THandle;
  ParentPath, RequestedDirectory: String;
begin
  RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\BensonMail',
    'InstallLocation', PreviousInstallDirectory);
  Result := True;
  if ExpandConstant('{param:UPDATE|0}') <> '1' then Exit;
  Result := False;
  ParentId := StrToIntDef(ExpandConstant('{param:UPDATEPID|0}'), 0);
  if (ParentId = 0) or (ParentId = GetCurrentProcessId) then Exit;
  RequestedDirectory := RemoveBackslashUnlessRoot(ExpandConstant('{param:DIR|}'));
  Handle := OpenProcess($00101000, False, ParentId); { SYNCHRONIZE and QUERY_LIMITED_INFORMATION }
  if Handle = 0 then
  begin
    { The parent can exit before Setup starts. Invalid PID means it has already exited. }
    Result := DLLGetLastError = 87;
    Exit;
  end;
  try
    Size := 32768;
    SetLength(ParentPath, Size);
    if not QueryFullProcessImageName(Handle, 0, ParentPath, Size) then Exit;
    SetLength(ParentPath, Size);
    if not IsOurExecutable(ExtractFileName(ParentPath)) then Exit;
    if CompareText(RemoveBackslashUnlessRoot(ExtractFileDir(ParentPath)), RequestedDirectory) <> 0 then Exit;
    Log('Update waiting for matching application PID ' + IntToStr(ParentId));
    WaitResult := WaitForSingleObject(Handle, 45000);
    if WaitResult = 0 then Log('Update parent exited; installation can continue');
    Result := WaitResult = 0;
    if not Result then
      MsgBox('Mail Secretary is still closing. Please close it and start the update again.' + #13#10 +
        '邮件小秘书仍在退出，请关闭后重新安装更新。', mbError, MB_OK);
  finally
    CloseHandle(Handle);
  end;
end;

function IsOurShortcut(const Filename: String): Boolean;
var
  Shell, Link, Folder, Item: Variant;
  Target, Directory: String;
begin
  Result := False;
  try
    Shell := CreateOleObject('WScript.Shell');
    Link := Shell.CreateShortcut(Filename);
    Target := Link.TargetPath;
    if Target = '' then
    begin
      { WScript can return an empty target for newer Shell link formats. }
      Shell := CreateOleObject('Shell.Application');
      Folder := Shell.NameSpace(ExtractFileDir(Filename));
      Item := Folder.ParseName(ExtractFileName(Filename));
      Link := Item.GetLink;
      Target := Link.Path;
    end;
    Directory := RemoveBackslashUnlessRoot(ExtractFileDir(Target));
    Log('Shortcut ownership: ' + Filename + ' -> ' + Target + '; app=' + ExpandConstant('{app}') + '; previous=' + PreviousInstallDirectory);
    Result := IsOurExecutable(ExtractFileName(Target)) and
      ((CompareText(Directory, RemoveBackslashUnlessRoot(ExpandConstant('{app}'))) = 0) or
       ((PreviousInstallDirectory <> '') and
        (CompareText(Directory, RemoveBackslashUnlessRoot(PreviousInstallDirectory)) = 0)));
    Log('Shortcut owned=' + IntToStr(Ord(Result)));
  except
    Log('Preserving an unreadable shortcut: ' + Filename + '; ' + GetExceptionMessage);
  end;
end;

procedure FindPreviousTasks(const Directory: String; IsDesktop: Boolean; var AppTask, UninstallTask: Boolean);
var
  Entry: TFindRec;
  Filename, Target: String;
  Shell, Link, Folder, Item: Variant;
begin
  if FindFirst(AddBackslash(Directory) + '*.lnk', Entry) then
  begin
    try
      repeat
        Filename := AddBackslash(Directory) + Entry.Name;
        if IsOurShortcut(Filename) then
        begin
          Shell := CreateOleObject('WScript.Shell');
          Link := Shell.CreateShortcut(Filename);
          Target := Link.TargetPath;
          if Target = '' then
          begin
            Shell := CreateOleObject('Shell.Application');
            Folder := Shell.NameSpace(Directory);
            Item := Folder.ParseName(Entry.Name);
            Link := Item.GetLink;
            Target := Link.Path;
          end;
          if Pos('uninstall', Lowercase(ExtractFileName(Target))) = 1 then UninstallTask := True
          else AppTask := True;
        end;
      until not FindNext(Entry);
    finally
      FindClose(Entry);
    end;
  end;
end;

procedure ApplyPreviousTaskDefaults;
var
  DesktopApp, DesktopUninstall, StartApp, StartUninstall: Boolean;
  Tasks: String;
begin
  if TaskDefaultsApplied then Exit;
  TaskDefaultsApplied := True;
  if (ExpandConstant('{param:UPDATE|0}') <> '1') and
    not FileExists(AddBackslash(WizardDirValue) + '.benson-installed.json') then Exit;
  if ExpandConstant('{param:TASKS|__unspecified__}') <> '__unspecified__' then Exit;
  DesktopApp := False; DesktopUninstall := False; StartApp := False; StartUninstall := False;
  FindPreviousTasks(ExpandConstant('{userdesktop}'), True, DesktopApp, DesktopUninstall);
  FindPreviousTasks(ExpandConstant('{userprograms}'), False, StartApp, StartUninstall);
  Tasks := '';
  if DesktopApp then Tasks := Tasks + 'desktopapp,';
  if DesktopUninstall then Tasks := Tasks + 'desktopuninstall,';
  if StartApp then Tasks := Tasks + 'startapp,';
  if StartUninstall then Tasks := Tasks + 'startuninstall,';
  if Length(Tasks) > 0 then SetLength(Tasks, Length(Tasks) - 1);
  { Apply after Inno has populated defaults. WizardSelectTasks expects selected names, not command-line ! exclusions. }
  if not WizardSelectTasks(Tasks) then RaiseException('Unable to restore existing shortcut choices.');
  if (WizardIsTaskSelected('desktopapp') <> DesktopApp) or
    (WizardIsTaskSelected('desktopuninstall') <> DesktopUninstall) or
    (WizardIsTaskSelected('startapp') <> StartApp) or
    (WizardIsTaskSelected('startuninstall') <> StartUninstall) then
      RaiseException('The existing shortcut choices could not be preserved.');
  Log('Restored shortcut choices: ' + Tasks);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectTasks then ApplyPreviousTaskDefaults;
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
    Result := ExtractFileName(Candidate);
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
  ApplyPreviousTaskDefaults;
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
