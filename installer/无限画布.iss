; 无限画布 · Inno Setup 安装包脚本
;
; 前置：先在 proto\ 下跑 PyInstaller 生成 onedir 产物 proto\dist\无限画布\
;       （spec 是 proto\无限画布.spec，产物含 无限画布.exe + _internal\）
;
; 编译：installer\build-installer.ps1   （会从 server.py 读 APP_VERSION 传进来）
; 手动：ISCC.exe /DAppVersion=3.8.1 "installer\无限画布.iss"
;
; 注意：安装包**不包含 .env**。那份文件里有用户加密后的 API Key，
;       打进安装包等于随安装包外发。首次运行由用户在设置里自己填。

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "无限画布"
#define AppExe  "无限画布.exe"
#define AppPub  "无限画布"
#define SrcDir  "..\proto\dist\无限画布"

[Setup]
; AppId 一旦发出去就不能改，否则新版本会被当成另一个软件（覆盖安装失效）
AppId={{8F3C1A62-5B4D-4E7A-9C21-7D6E5A4B3C10}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPub}
VersionInfoVersion={#AppVersion}

; {autopf} 在普通权限下解析成 %LOCALAPPDATA%\Programs（免 UAC），
; 用户主动以管理员运行则落到 Program Files。两种都支持。
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes

UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName} {#AppVersion}

OutputDir=..\proto\dist\installer
OutputBaseFilename=无限画布-Setup-{#AppVersion}
SetupIconFile=..\proto\app.ico

Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; PyInstaller 产物是 x64；WebView2 也只在 64 位上有意义
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "chs"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
; Excludes 里的 .env 是关键：不能把用户的 API Key 打进安装包
Source: "{#SrcDir}\*"; DestDir: "{app}"; \
  Excludes: ".env,.env.*,*.log,dist-onefile-prev\*"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "立即启动 {#AppName}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 卸载只清安装目录里的缓存，不碰用户数据。
; 画布数据在 WebView2 的 IndexedDB 里（%LOCALAPPDATA%\...\EBWebView），
; 和安装目录无关，卸载后仍然保留 —— 重装能看到原来的画布。
Type: filesandordirs; Name: "{app}\_internal\__pycache__"
