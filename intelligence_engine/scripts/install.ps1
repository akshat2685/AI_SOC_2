# install.ps1
$ErrorActionPreference = 'Stop'

Write-Host "Starting AI SOC Intelligence Engine setup..."

# Check Administrator privileges
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Please run PowerShell as Administrator"
    exit 1
}

Write-Host "Checking for Python..."
if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
    Write-Error "Python is not installed or not in PATH."
    exit 1
}

Write-Host "Setting up Python virtual environment..."
python -m venv venv
.\venv\Scripts\Activate.ps1

if (Test-Path "requirements.txt") {
    pip install -r requirements.txt
} else {
    Write-Warning "requirements.txt not found."
}

Write-Host "Creating Windows Service (Requires NSSM - Non-Sucking Service Manager)..."
if (-not (Get-Command "nssm" -ErrorAction SilentlyContinue)) {
    Write-Warning "NSSM is not installed. Cannot create Windows Service automatically."
    Write-Host "To install as a service, please install NSSM and run:"
    Write-Host "nssm install IntelligenceEngine `"$PWD\venv\Scripts\python.exe`" `"$PWD\main.py`""
} else {
    nssm install IntelligenceEngine "$PWD\venv\Scripts\python.exe" "$PWD\main.py"
    nssm set IntelligenceEngine AppDirectory "$PWD"
    nssm set IntelligenceEngine AppStdout "$PWD\logs\service.log"
    nssm set IntelligenceEngine AppStderr "$PWD\logs\service_error.log"
    Start-Service IntelligenceEngine
    Write-Host "Windows Service created and started."
}

Write-Host "Setup complete."
