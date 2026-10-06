# Builds HonestHands for Windows.  Run in PowerShell from the project folder:   .\build_win.ps1
#   dist\HonestHands\HonestHands.exe        the program
#   dist\HonestHands-Setup.exe              the installer (needs Inno Setup: winget install JRSoftware.InnoSetup)
# Optional signing: set CERT_PFX (path) and CERT_PASSWORD, and the program and installer get an Authenticode signature.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$py = if (Test-Path .\.venv\Scripts\python.exe) { '.\.venv\Scripts\python.exe' } else { 'python' }
if (-not (Test-Path .\.buildenv)) { & $py -m venv .buildenv }
$bp = '.\.buildenv\Scripts\python.exe'
& $bp -m pip install --quiet --upgrade pip
& $bp -m pip install --quiet --prefer-binary -r requirements.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

# the build number is the same counter the Mac build uses (version.py)
$ver = (Select-String -Path version.py -Pattern "VERSION = '([^']*)'").Matches[0].Groups[1].Value
$build = (Select-String -Path version.py -Pattern 'BUILD = (\d+)').Matches[0].Groups[1].Value
Write-Host "Building HonestHands $ver (build $build)"

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
& $bp -m PyInstaller --noconfirm --windowed --name HonestHands --icon icon.ico `
    --add-data "ui;ui" --add-data "extension;extension" `
    --collect-all llama_cpp --hidden-import net --hidden-import updates --hidden-import version --hidden-import rules `
    --hidden-import store --hidden-import engine --hidden-import ai_guard --hidden-import distill --hidden-import docs `
    --hidden-import watcher_win --hidden-import winlock --hidden-import winlockrules --hidden-import winoverlay `
    --hidden-import winkeepalive --hidden-import extension_host --hidden-import bridge --hidden-import bridge_server `
    winmain.py

function Sign($file) {
    if ($env:CERT_PFX -and (Test-Path $env:CERT_PFX)) {
        $st = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue | Select-Object -Last 1
        if ($st) { & $st.FullName sign /f $env:CERT_PFX /p $env:CERT_PASSWORD /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $file }
        else { Write-Host "  (signtool not found: $file left unsigned)" }
    }
}
Sign .\dist\HonestHands\HonestHands.exe

$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "${env:ProgramFiles}\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc "/DAppVersion=$ver" "/DAppBuild=$build" installer.iss
    Sign .\dist\HonestHands-Setup.exe
    Write-Host "Done: dist\HonestHands-Setup.exe"
} else {
    Write-Host "Done: dist\HonestHands\HonestHands.exe  (install Inno Setup to also make the installer)"
}
