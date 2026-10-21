#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef PackageDir
  #error PackageDir is required
#endif
#ifndef MinimumDotnet
  #error MinimumDotnet must be read from the published runtimeconfig.json
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
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[LangOptions]
DialogFontName=Segoe UI
DialogFontSize=10

[CustomMessages]
english.AppName=Email Assistant
english.UninstallName=Uninstall Email Assistant
english.ShortcutChoices=Choose shortcuts (each option is independent):
english.DesktopApp=Create a desktop shortcut for Email Assistant
english.DesktopUninstall=Create a desktop shortcut for the uninstaller
english.StartApp=Create a Start menu entry for Email Assistant
english.StartUninstall=Create a Start menu entry for the uninstaller
english.RunApp=Open Email Assistant
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
english.RuntimeConsent=The following required components are missing or too old:%n%1%n%nDownload and install ONLY these components from Microsoft? .NET may request Windows administrator permission. Existing shared runtimes will be kept, including when Email Assistant is uninstalled.%n%nNo application files or settings will be changed if you choose No.
chinesesimp.RuntimeConsent=检测到以下必要组件缺失或版本过旧：%n%1%n%n是否仅从微软官方下载并安装这些组件？安装 .NET 时可能需要 Windows 管理员授权。已安装的共享运行时会保留，卸载邮件小秘书时也不会删除。%n%n选择“否”不会修改软件文件或配置。
english.RuntimeDeclined=Required runtime installation was declined. No application files or settings were changed. Run Setup again to approve the missing components.
chinesesimp.RuntimeDeclined=已取消安装必要运行时，软件文件和配置均未修改。需要时请重新运行安装程序并确认安装缺失组件。
english.RuntimeFailed=Could not prepare the required runtimes. No application files were changed. Check the network and Windows security prompts, then retry.%n%1
chinesesimp.RuntimeFailed=必要运行时准备失败，软件文件未修改。请检查网络和 Windows 安全授权提示后重试。%n%1
english.RuntimeUntrustedMount=Windows blocked the WinUI 3 installer because a path contains an untrusted mount point (0x800701C0). This can involve redirected temporary or application folders. Try restarting Windows and running Setup from a local folder. If it fails again, send the installation log below for diagnosis; do not disable Windows security.
chinesesimp.RuntimeUntrustedMount=Windows 拒绝运行 WinUI 3 安装：路径包含不受信任的挂载点（0x800701C0）。可能涉及被重定向的临时目录或应用目录。请重启电脑，从本机文件夹重新运行安装程序；若仍失败，请提供下方安装日志排查，无需关闭 Windows 安全防护。
spanish.RuntimeUntrustedMount=Windows bloqueó la instalación de WinUI 3 porque una ruta contiene un punto de montaje no confiable (0x800701C0). Puede afectar a carpetas temporales o de aplicaciones redirigidas. Reinicia Windows y ejecuta el instalador desde una carpeta local. Si vuelve a fallar, envía el registro indicado abajo; no desactives la seguridad de Windows.
english.RuntimeLog=Installation log: %1
chinesesimp.RuntimeLog=安装日志：%1
spanish.RuntimeLog=Registro de instalación: %1
english.RuntimeOpenLog=Open the installation log now?
chinesesimp.RuntimeOpenLog=现在打开安装日志吗？
spanish.RuntimeOpenLog=¿Abrir el registro de instalación ahora?
english.RuntimeRestart=Microsoft requires a Windows restart to finish installing the runtime. No application files were changed. Restart Windows, then run this installer again.
chinesesimp.RuntimeRestart=微软运行时需要重启 Windows 才能完成安装。软件文件未修改。请重启电脑后重新运行此安装程序。
english.RuntimeProgressTitle=Preparing required components
chinesesimp.RuntimeProgressTitle=正在准备必要组件
english.RuntimeProgressDescription=Downloading and installing the Microsoft components you approved.
chinesesimp.RuntimeProgressDescription=正在下载并安装你已同意安装的微软组件。
english.RuntimeProgressText=Please wait. This may take several minutes. Approve the Windows administrator prompt if it appears.
chinesesimp.RuntimeProgressText=请稍候，这可能需要几分钟。如果出现 Windows 管理员授权提示，请确认。

spanish.AppName=Asistente de correo electrónico
spanish.UninstallName=Desinstalar Asistente de correo electrónico
spanish.ShortcutChoices=Elige los accesos directos (cada opción es independiente):
spanish.DesktopApp=Crear un acceso directo al Asistente de correo electrónico en el escritorio
spanish.DesktopUninstall=Crear un acceso directo al desinstalador en el escritorio
spanish.StartApp=Crear una entrada del Asistente de correo electrónico en Inicio
spanish.StartUninstall=Crear una entrada del desinstalador en Inicio
spanish.RunApp=Abrir Asistente de correo electrónico
spanish.DeleteInstaller=Eliminar este instalador al cerrar la instalación
spanish.DedicatedFolder=Usa una carpeta exclusiva llamada BensonMail. Examinar permite elegir su ubicación.
spanish.FolderInUse=La carpeta seleccionada contiene otros archivos. Elige una carpeta BensonMail vacía y exclusiva.
spanish.RuntimeConsent=Faltan los siguientes componentes necesarios o son demasiado antiguos:%n%1%n%n¿Descargar e instalar SOLO estos componentes desde Microsoft? .NET puede solicitar permisos de administrador de Windows. Se conservarán los componentes compartidos, incluso al desinstalar la aplicación.%n%nSi eliges No, no se cambiarán archivos ni ajustes.
spanish.RuntimeDeclined=Se canceló la instalación de los componentes necesarios. No se cambiaron archivos ni ajustes. Ejecuta el instalador de nuevo para autorizarla.
spanish.RuntimeFailed=No se pudieron preparar los componentes necesarios. No se cambiaron archivos. Revisa la conexión y los avisos de seguridad de Windows y vuelve a intentarlo.%n%1
spanish.RuntimeRestart=Microsoft requiere reiniciar Windows para terminar de instalar el componente. No se cambiaron archivos de la aplicación. Reinicia Windows y ejecuta este instalador de nuevo.
spanish.RuntimeProgressTitle=Preparando los componentes necesarios
spanish.RuntimeProgressDescription=Descargando e instalando los componentes de Microsoft que autorizaste.
spanish.RuntimeProgressText=Espera. Esto puede tardar varios minutos. Acepta la solicitud de permisos de administrador si aparece.
english.LanguageChoices=Optional interface languages (download required):
chinesesimp.LanguageChoices=选择界面语言（需要下载）：
spanish.LanguageChoices=Idiomas opcionales de la interfaz (requieren descarga):
english.DownloadChinese=Download Simplified Chinese
english.DownloadEnglish=Download English
english.DownloadSpanish=Download Spanish
chinesesimp.DownloadChinese=下载简体中文
chinesesimp.DownloadEnglish=下载英文
chinesesimp.DownloadSpanish=下载西班牙文
spanish.DownloadChinese=Descargar chino simplificado
spanish.DownloadEnglish=Descargar inglés
spanish.DownloadSpanish=Descargar español
english.LanguageDownloadFailed=The %1 language pack could not be downloaded or verified. Retry now? Cancel keeps the application installed; it will ask to download the missing language when you open it.
chinesesimp.LanguageDownloadFailed=%1语言包下载或校验失败。是否重试？取消后软件仍已安装，打开时会提示下载缺失的语言。
spanish.LanguageDownloadFailed=No se pudo descargar o verificar el paquete de idioma %1. ¿Reintentar? Si cancelas, la aplicación seguirá instalada y te pedirá descargar el idioma cuando la abras.

english.UpdateCancelled=Update cancelled before installation.
chinesesimp.UpdateCancelled=已在安装开始前取消更新。
spanish.UpdateCancelled=Actualización cancelada antes de la instalación.
english.NoShortcutName=Unable to choose an available shortcut name.
chinesesimp.NoShortcutName=无法选择可用的快捷方式名称。
spanish.NoShortcutName=No se pudo elegir un nombre disponible para el acceso directo.
english.ShortcutPreserveFailed=The existing shortcut choices could not be preserved.
chinesesimp.ShortcutPreserveFailed=无法保留原有快捷方式选择。
spanish.ShortcutPreserveFailed=No se pudieron conservar las opciones de accesos directos existentes.
english.ShortcutRemoveFailed=Could not remove the previous Email Assistant shortcut:
chinesesimp.ShortcutRemoveFailed=无法移除旧版邮件小秘书快捷方式：
spanish.ShortcutRemoveFailed=No se pudo quitar el acceso directo anterior:
english.MigrationListFailed=Cannot read the legacy payload migration list.
chinesesimp.MigrationListFailed=无法读取旧版文件迁移清单。
spanish.MigrationListFailed=No se pudo leer la lista de migración de archivos anteriores.
english.ObsoleteRuntimeFailed=Cannot remove an obsolete runtime file:
chinesesimp.ObsoleteRuntimeFailed=无法移除旧版运行时文件：
spanish.ObsoleteRuntimeFailed=No se pudo quitar un archivo de componente obsoleto:
english.NewExecutableMissing=The new application executable is missing.
chinesesimp.NewExecutableMissing=新版本应用程序文件缺失。
spanish.NewExecutableMissing=Falta el ejecutable de la nueva versión de la aplicación.

[Tasks]
Name: "desktopapp"; Description: "{cm:DesktopApp}"; GroupDescription: "{cm:ShortcutChoices}"
Name: "desktopuninstall"; Description: "{cm:DesktopUninstall}"
Name: "startapp"; Description: "{cm:StartApp}"
Name: "startuninstall"; Description: "{cm:StartUninstall}"

Name: "downloadzh"; Description: "{cm:DownloadChinese}"; GroupDescription: "{cm:LanguageChoices}"; Flags: unchecked
Name: "downloaden"; Description: "{cm:DownloadEnglish}"; Flags: unchecked
Name: "downloades"; Description: "{cm:DownloadSpanish}"; Flags: unchecked

[InstallDelete]
Type: files; Name: "{app}\BensonMail-*.exe"
Type: files; Name: "{app}\Uninstall-BensonMail-*.exe"

[Files]
Source: "prerequisites.ps1"; Flags: dontcopy
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
Filename: "{app}\BensonMail-{#AppVersion}.exe"; Parameters: "{code:UpdateRelaunchArguments}"; Flags: nowait skipifnotsilent; Check: RelaunchUpdatedApplication
Filename: "{app}\BensonMail-{#AppVersion}.exe"; Description: "{cm:RunApp}"; Flags: nowait postinstall skipifsilent

Filename: "{app}\MailWorker.exe"; Parameters: "--delete-installer ""{srcexe}"" --setup-pid {code:SetupProcessId} --installer-sha256 {code:SetupFingerprint}"; Description: "{cm:DeleteInstaller}"; Flags: postinstall unchecked nowait skipifsilent runhidden

[Code]
var
  PreviousInstallDirectory: String;
  TaskDefaultsApplied: Boolean;
  LanguageDefaultsApplied: Boolean;
  HadLegacyPayload: Boolean;
  DependenciesReady: Boolean;
  DependenciesRestart: Boolean;

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

function InstallDirectoryErrorFor(const Requested: String): String;
var
  Directory: String;
  Entry: TFindRec;
begin
  Result := '';
  Directory := RemoveBackslashUnlessRoot(Requested);
  { Existing owned installations may have a versioned portable or custom folder name. }
  if DirExists(AddBackslash(Directory) + '_internal') and FileExists(AddBackslash(Directory) + 'MailWorker.exe') then
  begin
    if FileExists(AddBackslash(Directory) + '.benson-installed.json') then Exit;
    if FindFirst(AddBackslash(Directory) + 'BensonMail-*.exe', Entry) then
    begin
      try
        repeat
          if IsOurExecutable(Entry.Name) then Exit;
        until not FindNext(Entry);
      finally FindClose(Entry); end;
    end;
  end;
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

function WriteUpdateState(const State, Detail: String): Boolean;
var
  Filename: String;
begin
  Filename := ExpandConstant('{param:UPDATESTATUS|}');
  Result := True;
  if Filename = '' then Exit;
  Result := SaveStringToFile(Filename + '.tmp', UTF8Encode(State + #10 + Detail), False);
  if not Result then Exit;
  DeleteFile(Filename);
  Result := RenameFile(Filename + '.tmp', Filename);
end;

function UpdateCancelled: Boolean;
var
  Filename: String;
begin
  Filename := ExpandConstant('{param:UPDATESTATUS|}');
  Result := (Filename <> '') and FileExists(Filename + '.cancel');
  if Result then WriteUpdateState('cancelled', 'Cancelled before installation / 安装前已取消。');
end;

function UpdateFailure(const Reason: String): Boolean;
begin
  WriteUpdateState('failed', Reason);
  SuppressibleMsgBox('Email Assistant update could not start / 邮件小秘书更新未能启动：' + #13#10 + Reason,
    mbError, MB_OK, IDOK);
  Result := False;
end;

function RunPrerequisiteHelper(const Operation, Components: String; var Detail, Status: String): Boolean;
var
  ResultPath, Parameters, Reason, LogPath: String;
  LogExitCode: Integer;
  ExitCode: Integer;
begin
  ExitCode := -1;
  ResultPath := ExpandConstant('{tmp}\benson-prerequisites.ini');
  DeleteFile(ResultPath);
  if not FileExists(ExpandConstant('{tmp}\prerequisites.ps1')) then ExtractTemporaryFile('prerequisites.ps1');
  Parameters := '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
    ExpandConstant('{tmp}\prerequisites.ps1') + '" -Mode ' + Operation +
    ' -MinimumDotnet "{#MinimumDotnet}" -MinimumWinUI "8000.994.2142.0" -ResultFile "' + ResultPath + '"';
  if Components <> '' then Parameters := Parameters + ' -Components "' + Components + '"';
  Result := Exec(ExpandConstant('{sysnative}\WindowsPowerShell\v1.0\powershell.exe'), Parameters,
    ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, ExitCode);
  Status := GetIniString('Prerequisites', 'Status', '', ResultPath);
  Detail := GetIniString('Prerequisites', 'Error', 'Runtime helper did not return a result. Windows exit code: ' + IntToStr(ExitCode), ResultPath);
  Result := Result and (ExitCode = 0) and (Status <> '');
  if not Result then
  begin
    Reason := GetIniString('Prerequisites', 'Reason', '', ResultPath);
    if Reason = 'untrusted_mount_point' then
      Detail := CustomMessage('RuntimeUntrustedMount') + #13#10 + Detail;
    LogPath := GetIniString('Prerequisites', 'LogPath', '', ResultPath);
    if (LogPath <> '') and FileExists(LogPath) then
    begin
      Detail := Detail + #13#10 + FmtMessage(CustomMessage('RuntimeLog'), [LogPath]);
      if not WizardSilent then
        if SuppressibleMsgBox(Detail + #13#10 + #13#10 + CustomMessage('RuntimeOpenLog'),
          mbError, MB_YESNO, IDNO) = IDYES then
          ShellExec('', ExpandConstant('{sys}\notepad.exe'), '"' + LogPath + '"', '',
            SW_SHOWNORMAL, ewNoWait, LogExitCode);
    end;
  end;
end;

function EnsurePrerequisites: String;
var
  Detail, Status, Missing, Components, ResultPath: String;
  Approved, WasVisible: Boolean;
  ProgressPage: TOutputMarqueeProgressWizardPage;
begin
  Result := '';
  if DependenciesReady then Exit;
  if not RunPrerequisiteHelper('Detect', '', Detail, Status) then
  begin Result := FmtMessage(CustomMessage('RuntimeFailed'), [Detail]); Exit; end;
  ResultPath := ExpandConstant('{tmp}\benson-prerequisites.ini');
  Missing := ''; Components := '';
  if GetIniString('Prerequisites', 'DotNet', '0', ResultPath) <> '1' then
  begin Missing := '  - .NET 8 runtime (x64)'; Components := 'dotnet'; end;
  if GetIniString('Prerequisites', 'WinUI', '0', ResultPath) <> '1' then
  begin
    if Missing <> '' then begin Missing := Missing + #13#10; Components := Components + ','; end;
    Missing := Missing + '  - WinUI 3 / Windows App Runtime 1.8 (x64)';
    Components := Components + 'winui';
  end;
  if Components = '' then begin DependenciesReady := True; Exit; end;
  WriteUpdateState('prerequisites', Missing);
  { Silent/suppressed installs default to No. Only this explicit switch can preapprove runtime downloads. }
  Approved := ExpandConstant('{param:INSTALLDEPENDENCIES|0}') = '1';
  if not Approved then
    Approved := SuppressibleMsgBox(FmtMessage(CustomMessage('RuntimeConsent'), [Missing]),
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES;
  if not Approved or UpdateCancelled then
  begin Result := CustomMessage('RuntimeDeclined'); Exit; end;
  { PrepareToInstall runs after WizardForm exists. Keep the installation visible
    during the potentially long helper call, including a /SILENT update. }
  ProgressPage := CreateOutputMarqueeProgressPage(CustomMessage('RuntimeProgressTitle'),
    CustomMessage('RuntimeProgressDescription'));
  ProgressPage.SetText(CustomMessage('RuntimeProgressText'), Missing);
  WasVisible := WizardForm.Visible;
  WizardForm.Show;
  ProgressPage.Show;
  try
    ProgressPage.Animate;
    WizardForm.Update;
    if not RunPrerequisiteHelper('Install', Components, Detail, Status) then
    begin Result := FmtMessage(CustomMessage('RuntimeFailed'), [Detail]); Exit; end;
  finally
    ProgressPage.Hide;
    if not WasVisible then WizardForm.Hide;
  end;
  if Status = 'reboot' then
  begin DependenciesRestart := True; Result := CustomMessage('RuntimeRestart'); Exit; end;
  if Status <> 'ready' then
  begin Result := FmtMessage(CustomMessage('RuntimeFailed'), [Detail]); Exit; end;
  DependenciesReady := True;
end;

function InitializeSetup: Boolean;
var
  ParentId, WaitResult, Size, Attempt: LongWord;
  Handle: THandle;
  ParentPath, RequestedDirectory, DirectoryError: String;
begin
  RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\BensonMail',
    'InstallLocation', PreviousInstallDirectory);
  Result := True;
  if ExpandConstant('{param:UPDATE|0}') <> '1' then Exit;
  Result := False;
  if UpdateCancelled then Exit;
  ParentId := StrToIntDef(ExpandConstant('{param:UPDATEPID|0}'), 0);
  if (ParentId = 0) or (ParentId = GetCurrentProcessId) then
  begin Result := UpdateFailure('Invalid application PID / 应用进程编号无效。'); Exit; end;
  RequestedDirectory := RemoveBackslashUnlessRoot(ExpandConstant('{param:DIR|}'));
  DirectoryError := InstallDirectoryErrorFor(RequestedDirectory);
  if DirectoryError <> '' then begin Result := UpdateFailure(DirectoryError); Exit; end;
  Handle := OpenProcess($00101000, False, ParentId);
  if Handle = 0 then
  begin
    if DLLGetLastError = 87 then
    begin
      Result := WriteUpdateState('ready', '{#AppVersion}');
      if not Result then Result := UpdateFailure('Cannot write update acknowledgment / 无法写入更新确认文件。');
    end
    else Result := UpdateFailure('Cannot inspect application PID. Windows error / 无法查询应用进程，Windows 错误：' + IntToStr(DLLGetLastError));
    Exit;
  end;
  try
    Size := 32768;
    SetLength(ParentPath, Size);
    if not QueryFullProcessImageName(Handle, 0, ParentPath, Size) then
    begin Result := UpdateFailure('Cannot verify application executable / 无法验证应用程序路径。'); Exit; end;
    SetLength(ParentPath, Size);
    if not IsOurExecutable(ExtractFileName(ParentPath)) then
    begin Result := UpdateFailure('Application executable name does not match / 应用程序名称不匹配。'); Exit; end;
    if CompareText(RemoveBackslashUnlessRoot(ExtractFileDir(ParentPath)), RequestedDirectory) <> 0 then
    begin Result := UpdateFailure('Application directory does not match update target / 正在运行的应用与更新目标目录不匹配。'); Exit; end;
    if (ExpandConstant('{param:UPDATEFIXTUREACKDELAY|0}') = '1000') and
      FileExists(AddBackslash(ExtractFileDir(RequestedDirectory)) + '.benson-uninstall-fixture') then Sleep(1000);
    if UpdateCancelled then Exit;
    if not WriteUpdateState('ready', '{#AppVersion}') then
    begin Result := UpdateFailure('Cannot write update acknowledgment / 无法写入更新确认文件。'); Exit; end;
    Log('Update handoff acknowledged; waiting for matching application PID ' + IntToStr(ParentId));
    WaitResult := 258;
    for Attempt := 1 to 450 do
    begin
      if UpdateCancelled then Exit;
      WaitResult := WaitForSingleObject(Handle, 100);
      if WaitResult <> 258 then Break;
    end;
    if UpdateCancelled then Exit;
    if WaitResult = 0 then Log('Update parent exited; installation can continue');
    Result := WaitResult = 0;
    if not Result then Result := UpdateFailure('Application did not finish closing within 45 seconds / 应用在45秒内未退出，请关闭后重试。');
  finally CloseHandle(Handle); end;
end;

function InstalledVersionMatches: Boolean;
var
  Lines: TArrayOfString;
begin
  Result := LoadStringsFromFile(ExpandConstant('{app}\build-version.txt'), Lines);
  if Result then Result := GetArrayLength(Lines) > 0;
  if Result then Result := Trim(Lines[0]) = '{#AppVersion}';
end;

function UpdateRelaunchArguments(Param: String): String;
var
  Filename, Parent: String;
begin
  Result := '';
  Filename := ExpandConstant('{param:UPDATEFIXTURERESULT|}');
  Parent := ExtractFileDir(RemoveBackslashUnlessRoot(ExpandConstant('{app}')));
  if (Filename <> '') and FileExists(AddBackslash(Parent) + '.benson-uninstall-fixture') and
      (CompareText(Filename, AddBackslash(Parent) + 'relaunch-result.json') = 0) then
    Result := '--update-relaunch-fixture "' + Filename + '"';
end;

function RelaunchUpdatedApplication: Boolean;
begin
  Result := (ExpandConstant('{param:UPDATE|0}') = '1') and
    (ExpandConstant('{param:UPDATENORELAUNCH|0}') <> '1') and InstalledVersionMatches;
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
  if not DesktopApp then Tasks := Tasks + '!';
  Tasks := Tasks + 'desktopapp,';
  if not DesktopUninstall then Tasks := Tasks + '!';
  Tasks := Tasks + 'desktopuninstall,';
  if not StartApp then Tasks := Tasks + '!';
  Tasks := Tasks + 'startapp,';
  if not StartUninstall then Tasks := Tasks + '!';
  Tasks := Tasks + 'startuninstall';
  { Apply after Inno has populated defaults, explicitly deselecting absent shortcuts. }
  WizardSelectTasks(Tasks);
  if (WizardIsTaskSelected('desktopapp') <> DesktopApp) or
    (WizardIsTaskSelected('desktopuninstall') <> DesktopUninstall) or
    (WizardIsTaskSelected('startapp') <> StartApp) or
    (WizardIsTaskSelected('startuninstall') <> StartUninstall) then
      RaiseException(CustomMessage('ShortcutPreserveFailed'));
  Log('Restored shortcut choices: ' + Tasks);
end;

procedure ApplyLanguageDefaults;
var
  Code, Existing: String;
begin
  if LanguageDefaultsApplied then Exit;
  LanguageDefaultsApplied := True;
  if ExpandConstant('{param:UPDATE|0}') = '1' then Exit;
  if ExpandConstant('{param:TASKS|__unspecified__}') <> '__unspecified__' then Exit;
  Code := 'en';
  if ActiveLanguage = 'chinesesimp' then Code := 'zh';
  if ActiveLanguage = 'spanish' then Code := 'es';
  Existing := WizardSelectedTasks(False);
  if Existing <> '' then Existing := Existing + ',';
  WizardSelectTasks(Existing + 'download' + Code);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectTasks then
  begin
    ApplyPreviousTaskDefaults;
    ApplyLanguageDefaults;
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
            RaiseException(CustomMessage('ShortcutRemoveFailed') + ' ' + Filename);
      until not FindNext(Entry);
    finally
      FindClose(Entry);
    end;
  end;
end;

function FileAttributes(const Filename: String): LongWord;
  external 'GetFileAttributesW@kernel32.dll stdcall';

function SafeMigrationPath(const Relative: String): Boolean;
var
  Candidate, Root: String;
  Attributes: LongWord;
begin
  Result := False;
  if (Relative = '') or (Pos('..', Relative) <> 0) or (Pos(':', Relative) <> 0) or
    (Relative[1] = '\') or (Pos('{', Relative) <> 0) then Exit;
  Root := RemoveBackslashUnlessRoot(ExpandConstant('{app}'));
  Candidate := Root + '\' + Relative;
  { Never follow junctions or symlinks in a legacy dependency path. }
  while Length(Candidate) >= Length(Root) do
  begin
    Attributes := FileAttributes(Candidate);
    if (Attributes <> $FFFFFFFF) and ((Attributes and $400) <> 0) then Exit;
    if CompareText(Candidate, Root) = 0 then Break;
    Candidate := ExtractFileDir(Candidate);
  end;
  Result := True;
end;

procedure RemoveObsoletePayload;
var
  Lines: TArrayOfString;
  I: Integer;
  Digest, Relative, Filename, Parent, Root: String;
begin
  if not HadLegacyPayload then Exit;
  if not LoadStringsFromFile(ExpandConstant('{app}\.benson-obsolete-files.tsv'), Lines) then
    RaiseException(CustomMessage('MigrationListFailed'));
  Root := RemoveBackslashUnlessRoot(ExpandConstant('{app}'));
  for I := 0 to GetArrayLength(Lines) - 1 do
  begin
    if Length(Lines[I]) > 65 then
    begin
      Digest := Copy(Lines[I], 1, 64);
      Relative := Copy(Lines[I], 66, MaxInt);
      StringChangeEx(Relative, '/', '\', True);
      if (Lines[I][65] = #9) and SafeMigrationPath(Relative) then
      begin
        Filename := Root + '\' + Relative;
        if FileExists(Filename) then
        begin
          if CompareText(GetSHA256OfFile(Filename), Digest) = 0 then
          begin
            if not DeleteFile(Filename) then
            begin
              WriteUpdateState('failed', CustomMessage('ObsoleteRuntimeFailed') + ' ' + Relative);
              RaiseException(CustomMessage('ObsoleteRuntimeFailed') + ' ' + Relative);
            end;
            Log('Removed obsolete owned payload: ' + Relative);
            Parent := ExtractFileDir(Filename);
            { Remove only empty directories; unrelated files are always retained. }
            while (Length(Parent) > Length(Root)) and RemoveDir(Parent) do
              Parent := ExtractFileDir(Parent);
          end
          else Log('Preserved modified legacy file: ' + Relative);
        end;
      end;
    end;
  end;
end;

procedure DownloadLanguagePack(const Code: String);
var
  ExitCode, Response: Integer;
  Success: Boolean;
begin
  if not WizardIsTaskSelected('download' + Code) then Exit;
  repeat
    Log('Downloading selected language pack: ' + Code);
    Success := Exec(ExpandConstant('{app}\MailWorker.exe'),
      '--home "' + ExpandConstant('{app}') + '" --download-language ' + Code,
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ExitCode);
    Success := Success and (ExitCode = 0) and FileExists(ExpandConstant('{app}\languages\') + Code + '.json');
    if Success then Exit;
    Log('Language pack download failed: ' + Code + ', exit code ' + IntToStr(ExitCode));
    if WizardSilent then Exit;
    Response := MsgBox(FmtMessage(CustomMessage('LanguageDownloadFailed'), [Code]), mbError, MB_RETRYCANCEL);
  until Response <> IDRETRY;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    ApplyLanguageDefaults;
    HadLegacyPayload := FileExists(ExpandConstant('{app}\MailWorker.exe')) and
      DirExists(ExpandConstant('{app}\_internal'));
    if ExpandConstant('{param:UPDATE|0}') = '1' then
      WriteUpdateState('installing', '{#AppVersion}');
    { Clear this application's old choices, including names in the other UI language. }
    RemoveOldShortcuts(ExpandConstant('{userdesktop}'));
    RemoveOldShortcuts(ExpandConstant('{userprograms}'));
  end;
  if CurStep = ssPostInstall then
  begin
    RemoveObsoletePayload;
    if ActiveLanguage = 'chinesesimp' then
      SaveStringToFile(ExpandConstant('{app}\installed-language.txt'), 'zh', False)
    else if ActiveLanguage = 'spanish' then
      SaveStringToFile(ExpandConstant('{app}\installed-language.txt'), 'es', False)
    else
      SaveStringToFile(ExpandConstant('{app}\installed-language.txt'), 'en', False);
    DownloadLanguagePack('zh');
    DownloadLanguagePack('en');
    DownloadLanguagePack('es');
  end;
  if (CurStep = ssPostInstall) and (ExpandConstant('{param:UPDATE|0}') = '1') then
  begin
    if not FileExists(ExpandConstant('{app}\BensonMail-{#AppVersion}.exe')) or not InstalledVersionMatches then
    begin
      WriteUpdateState('failed', CustomMessage('NewExecutableMissing'));
      RaiseException(CustomMessage('NewExecutableMissing'));
    end;
    WriteUpdateState('installed', '{#AppVersion}');
    Log('Update installation completed: {#AppVersion}');
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
  RaiseException(CustomMessage('NoShortcutName'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  ApplyPreviousTaskDefaults;
  if UpdateCancelled then Result := CustomMessage('UpdateCancelled')
  else Result := InstallDirectoryErrorFor(WizardDirValue);
  if Result = '' then Result := EnsurePrerequisites;
  if Result <> '' then WriteUpdateState('failed', Result);
  NeedsRestart := DependenciesRestart;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ErrorText: String;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    ErrorText := InstallDirectoryErrorFor(WizardDirValue);
    if ErrorText <> '' then
    begin
      MsgBox(ErrorText, mbError, MB_OK);
      Result := False;
    end;
  end;
end;
