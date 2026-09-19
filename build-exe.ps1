$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $ProjectRoot ".venv-build"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python Launcher (py.exe) was not found. Install Python 3.11 or newer from python.org, then rerun this script."
}

$PythonSelector = $null
foreach ($Candidate in @("-3.13", "-3.12", "-3.11")) {
    $PreviousPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    & py $Candidate -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
    $CandidateExitCode = $LASTEXITCODE
    $ErrorActionPreference = $PreviousPreference
    if ($CandidateExitCode -eq 0) {
        $PythonSelector = $Candidate
        break
    }
}

if (-not $PythonSelector) {
    throw "Python 3.11 or newer is required, but none was found. Install Python 3.12, then rerun this script."
}

if (-not (Test-Path $Venv)) {
    & py $PythonSelector -m venv $Venv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the build environment (exit code $LASTEXITCODE)."
    }
}

$Python = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "The existing .venv-build is incomplete. Delete '$Venv' and rerun this script."
}

& $Python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "The existing .venv-build uses Python older than 3.11. Delete '$Venv' and rerun this script."
}

& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upgrade pip (exit code $LASTEXITCODE)."
}

& $Python -m pip install $ProjectRoot pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install build dependencies (exit code $LASTEXITCODE)."
}

& (Join-Path $Venv "Scripts\pyinstaller.exe") `
    --noconfirm `
    --clean `
    --onefile `
    --name tacz-update `
    --collect-all keyring `
    (Join-Path $ProjectRoot "tacz_update.py")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed (exit code $LASTEXITCODE)."
}

Write-Host "EXE created at: $ProjectRoot\dist\tacz-update.exe"
