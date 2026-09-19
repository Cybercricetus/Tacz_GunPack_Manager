$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $ProjectRoot ".venv-build"

if (-not (Test-Path $Venv)) {
    py -3 -m venv $Venv
}

$Python = Join-Path $Venv "Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install $ProjectRoot pyinstaller
& (Join-Path $Venv "Scripts\pyinstaller.exe") `
    --noconfirm `
    --clean `
    --onefile `
    --name tacz-update `
    --collect-all keyring `
    (Join-Path $ProjectRoot "tacz_update.py")

Write-Host "EXE created at: $ProjectRoot\dist\tacz-update.exe"
