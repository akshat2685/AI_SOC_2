<#
  EDYSOR sensor auto-start installer (Windows).

  Creates a Windows Scheduled Task that runs the sensor at system startup
  and restarts it if it crashes. No new dependencies — uses the built-in
  Task Scheduler (works on every Windows machine, no admin-only service
  wrapper needed... though creating the task itself needs admin once).

  Usage (run PowerShell AS ADMINISTRATOR, from the folder containing
  edysor_sensor.py and sensor.json):
      .\install_autostart.ps1

  What it does:
  - Creates task "EDYSOR Sensor" that runs at startup + at user logon
  - Runs: pythonw.exe <this folder>\edysor_sensor.py  (pythonw = no console window)
  - Restarts automatically if the sensor exits (every 1 minute, up to 3 days)
  - Logs stay in sensor.log next to the sensor, as before

  To remove later:  Unregister-ScheduledTask -TaskName "EDYSOR Sensor" -Confirm:$false
#>

$ErrorActionPreference = "Stop"
$TaskName = "EDYSOR Sensor"
$SensorDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SensorScript = Join-Path $SensorDir "edysor_sensor.py"
$ConfigFile  = Join-Path $SensorDir "sensor.json"

if (-not (Test-Path $SensorScript)) { throw "edysor_sensor.py not found in $SensorDir" }
if (-not (Test-Path $ConfigFile))  { throw "sensor.json not found in $SensorDir - run setup first" }

# Prefer pythonw (no console window); fall back to python
$PythonW = $null
foreach ($cmd in @("pythonw", "python")) {
    $p = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($p) { $PythonW = $p.Source; break }
}
if (-not $PythonW) { throw "No Python found on PATH. Install Python 3 and re-run." }
if ($PythonW -like "*\python.exe") {
    $w = Join-Path (Split-Path $PythonW) "pythonw.exe"
    if (Test-Path $w) { $PythonW = $w }
}

$Action = New-ScheduledTaskAction -Execute $PythonW `
    -Argument "`"$SensorScript`" --log-file `"$SensorDir\sensor.log`"" -WorkingDirectory $SensorDir

$Triggers = @(
    (New-ScheduledTaskTrigger -AtStartup),
    (New-ScheduledTaskTrigger -AtLogOn)
)

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 3)

$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

try {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "Removing existing '$TaskName' task..."
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Triggers `
        -Settings $Settings -Principal $Principal -Description "EDYSOR AI SOC endpoint sensor" | Out-Null
    Start-ScheduledTask -TaskName $TaskName
    Write-Host ""
    Write-Host "EDYSOR sensor installed as a scheduled task '$TaskName'."
    Write-Host "It starts at boot, at logon, and restarts automatically on crashes."
    Write-Host "Check sensor.log in $SensorDir for its heartbeat."
} catch {
    Write-Host ""
    Write-Host "FAILED: $($_.Exception.Message)"
    Write-Host "Tip: right-click PowerShell -> 'Run as administrator', then re-run this script."
    exit 1
}
