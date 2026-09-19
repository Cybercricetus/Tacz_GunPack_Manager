$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $ProjectRoot ".venv"

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
    throw "Python 3.11 or newer is required, but none was found. Install Python 3.12, then rerun this script. Your Python 3.9 environment is not compatible."
}

if (-not (Test-Path $Venv)) {
    & py $PythonSelector -m venv $Venv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the virtual environment (exit code $LASTEXITCODE)."
    }
}

$Python = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "The existing .venv is incomplete. Delete '$Venv' and rerun this script."
}

& $Python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "The existing .venv uses Python older than 3.11. Run 'deactivate', delete '$Venv', and rerun this script."
}

& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upgrade pip (exit code $LASTEXITCODE)."
}

& $Python -m pip install $ProjectRoot
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install tacz-updater (exit code $LASTEXITCODE)."
}

Write-Host "Installed successfully."
Write-Host "Run: $Venv\Scripts\tacz-update.exe init <path> --minecraft 1.20.1 --loader forge"
