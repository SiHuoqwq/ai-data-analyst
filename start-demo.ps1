[CmdletBinding()]
param(
    [ValidateSet("Fake", "DeepSeek")]
    [string]$Provider = "Fake",
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$frontendRoot = Join-Path $projectRoot "frontend-v2"
$runtimeRoot = Join-Path $env:TEMP "xishu-demo-runtime"
$statePath = Join-Path $runtimeRoot "processes.json"
$frontendUrl = "http://localhost:5174"
$healthUrl = "http://127.0.0.1:8000/health"

function Stop-WithError([string]$Message) {
    Write-Error $Message
    exit 1
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    Stop-WithError "Python was not found. Install Python 3.10+ and add it to PATH."
}
if (-not $npmCommand) {
    Stop-WithError "npm was not found. Install Node.js 20+ and add it to PATH."
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot "package.json"))) {
    Stop-WithError "frontend-v2/package.json was not found."
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot "node_modules"))) {
    Stop-WithError "Frontend dependencies are missing. Run npm ci in frontend-v2 first."
}

if ($Provider -eq "DeepSeek") {
    $configuredKey = [string]$env:DEEPSEEK_API_KEY
    if ([string]::IsNullOrWhiteSpace($configuredKey) -or $configuredKey -eq "sk-your-key-here") {
        Stop-WithError "DeepSeek mode requires a valid DEEPSEEK_API_KEY environment variable."
    }
}

Write-Output "Provider: $Provider"
Write-Output "Frontend: $frontendUrl"
Write-Output "Backend health: $healthUrl"

if ($CheckOnly) {
    Write-Output "Environment check completed. No service was started."
    exit 0
}

$occupiedPorts = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 8000, 5174 }
if ($occupiedPorts) {
    $ports = ($occupiedPorts.LocalPort | Sort-Object -Unique) -join ", "
    Stop-WithError "Port $ports is already in use. Run .\stop-demo.ps1 or inspect the existing service."
}

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
$uploadRoot = Join-Path $runtimeRoot "uploads"
$chartRoot = Join-Path $runtimeRoot "charts"
New-Item -ItemType Directory -Force -Path $uploadRoot | Out-Null
New-Item -ItemType Directory -Force -Path $chartRoot | Out-Null

$databasePath = (Join-Path $runtimeRoot "demo.db").Replace("\", "/")
$env:V2_PROVIDER = $Provider.ToLowerInvariant()
$env:DATABASE_URL = "sqlite:///$databasePath"
$env:UPLOAD_DIR = $uploadRoot
$env:CHART_DIR = $chartRoot
$env:BACKEND_HOST = "127.0.0.1"
$env:BACKEND_PORT = "8000"
$env:FRONTEND_ORIGIN = $frontendUrl

Push-Location $projectRoot
try {
    & $pythonCommand.Source -m app.migrate
    if ($LASTEXITCODE -ne 0) {
        Stop-WithError "Database migration failed. Demo services were not started."
    }

    $backend = Start-Process `
        -FilePath $pythonCommand.Source `
        -ArgumentList @("-m", "app.run") `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $runtimeRoot "backend.out.log") `
        -RedirectStandardError (Join-Path $runtimeRoot "backend.err.log") `
        -PassThru

    $frontend = Start-Process `
        -FilePath $npmCommand.Source `
        -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1") `
        -WorkingDirectory $frontendRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $runtimeRoot "frontend.out.log") `
        -RedirectStandardError (Join-Path $runtimeRoot "frontend.err.log") `
        -PassThru

    @{
        project_root = $projectRoot
        runtime_root = $runtimeRoot
        provider = $Provider
        backend_pid = $backend.Id
        frontend_pid = $frontend.Id
        started_at = (Get-Date).ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8

    $deadline = (Get-Date).AddSeconds(30)
    $backendReady = $false
    $frontendReady = $false
    do {
        Start-Sleep -Milliseconds 500
        try {
            $health = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
            $backendReady = $health.StatusCode -eq 200
        } catch {
            $backendReady = $false
        }
        try {
            $page = Invoke-WebRequest -Uri $frontendUrl -UseBasicParsing -TimeoutSec 2
            $frontendReady = $page.StatusCode -eq 200
        } catch {
            $frontendReady = $false
        }
    } until (($backendReady -and $frontendReady) -or (Get-Date) -ge $deadline)

    if (-not ($backendReady -and $frontendReady)) {
        & (Join-Path $projectRoot "stop-demo.ps1")
        Stop-WithError "Services did not become ready within 30 seconds. Logs are in $runtimeRoot."
    }

    Write-Output "Demo services are ready."
    Write-Output "Stop command: .\stop-demo.ps1"
} finally {
    Pop-Location
}
