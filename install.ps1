$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $ProjectRoot ".venv"

if (-not (Test-Path $Venv)) {
    py -3 -m venv $Venv
}

& (Join-Path $Venv "Scripts\python.exe") -m pip install --upgrade pip
& (Join-Path $Venv "Scripts\python.exe") -m pip install $ProjectRoot

Write-Host "Installed successfully."
Write-Host "Run: $Venv\Scripts\tacz-update.exe init <path> --minecraft 1.20.1 --loader forge"
