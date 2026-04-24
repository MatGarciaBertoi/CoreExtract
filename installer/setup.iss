; ============================================================
;  CoreExtract — Script de Instalação (Inno Setup 6)
;  Gera: CoreExtract_Setup_v2.0.exe
;  Para compilar: iscc installer\setup.iss
; ============================================================

#define AppName        "CoreExtract"
#define AppVersion     "2.0"
#define AppPublisher   "Bertoi Informática"
#define AppURL         "https://github.com/MatGarciaBertoi/CoreExtract"
#define AppExeName     "CoreExtract.exe"
#define AppDescription "CoreExtract · Motor Inteligente de RH"

[Setup]
AppId={{B4F2A1C0-3D8E-4F5A-9B2C-1E7D6A8F0C3D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}

; Instala em AppData\Local do usuário — não precisa de admin
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; Sem necessidade de privilégio de admin
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline

; Saída
OutputDir=..\dist\installer
OutputBaseFilename=CoreExtract_Setup_v{#AppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}

; Compressão
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; Aparência
WizardStyle=modern
WizardSizePercent=120
DisableWelcomePage=no
DisableReadyPage=no

; Não cria registro (instalação limpa)
ChangesAssociations=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon";  Description: "Criar atalho na Área de Trabalho";  GroupDescription: "Atalhos:"; Flags: checked
Name: "startmenu";    Description: "Criar atalho no Menu Iniciar";       GroupDescription: "Atalhos:"; Flags: checked
Name: "autostart";    Description: "Iniciar CoreExtract com o Windows";  GroupDescription: "Inicialização:"; Flags: unchecked

[Files]
; Copia toda a pasta dist\CoreExtract\ (gerada pelo PyInstaller)
Source: "..\dist\CoreExtract\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Atalho na Área de Trabalho
Name: "{autodesktop}\{#AppName}";    Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"; Comment: "{#AppDescription}"; Tasks: desktopicon

; Atalho no Menu Iniciar
Name: "{group}\{#AppName}";          Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"; Comment: "{#AppDescription}"; Tasks: startmenu
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"; Tasks: startmenu

[Registry]
; Inicialização automática com o Windows (opcional)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; Abre o CoreExtract ao fim da instalação
Filename: "{app}\{#AppExeName}"; Description: "Abrir CoreExtract agora"; Flags: nowait postinstall skipifsilent shellexec

[UninstallDelete]
; Remove dados do usuário apenas se explicitamente confirmado
; (não apaga %APPDATA%\CoreExtract\ automaticamente — preserva configurações)
Type: filesandordirs; Name: "{app}"

[Code]
// Verifica se existe instalação anterior e propõe atualização
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

// Mensagem de boas-vindas personalizada
procedure InitializeWizard();
begin
  WizardForm.WelcomeLabel2.Caption :=
    'Bem-vindo ao instalador do CoreExtract v{#AppVersion}.' + #13#10 + #13#10 +
    'O CoreExtract é uma ferramenta de triagem inteligente de currículos ' +
    'que usa Inteligência Artificial (Google Gemini) para extrair, ' +
    'analisar e pontuar candidatos automaticamente.' + #13#10 + #13#10 +
    'Clique em Próximo para continuar.';
end;
