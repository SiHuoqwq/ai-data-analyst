[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$runtimeRoot = Join-Path $env:TEMP "xishu-demo-runtime"
$statePath = Join-Path $runtimeRoot "processes.json"

function Resolve-ProjectRoot([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    $target = @($item.Target) | Select-Object -First 1
    if ($item.LinkType -and $target) {
        if (-not [System.IO.Path]::IsPathRooted([string]$target)) {
            $target = Join-Path $item.Parent.FullName ([string]$target)
        }
        return [System.IO.Path]::GetFullPath([string]$target).TrimEnd("\")
    }
    return [System.IO.Path]::GetFullPath($item.FullName).TrimEnd("\")
}

if (-not (Test-Path -LiteralPath $statePath)) {
    Write-Output "No recorded demo services are running."
    exit 0
}

$state = Get-Content -LiteralPath $statePath -Raw -Encoding utf8 | ConvertFrom-Json
$recordedProjectRoot = Resolve-ProjectRoot -Path ([string]$state.project_root)
$currentProjectRoot = Resolve-ProjectRoot -Path $projectRoot
if ($recordedProjectRoot -ne $currentProjectRoot) {
    Write-Error "The process state belongs to another project. Refusing to stop it: $statePath"
    exit 1
}

function Get-ChildProcessIds([int]$ParentId) {
    $children = @(
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$ParentId" -ErrorAction SilentlyContinue
    )
    foreach ($child in $children) {
        Get-ChildProcessIds -ParentId ([int]$child.ProcessId)
        [int]$child.ProcessId
    }
}

$rootIds = @([int]$state.backend_pid, [int]$state.frontend_pid)
$allIds = @()
foreach ($rootId in $rootIds) {
    $allIds += @(Get-ChildProcessIds -ParentId $rootId)
    $allIds += $rootId
}

foreach ($processId in ($allIds | Select-Object -Unique)) {
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $processId -Force
    }
}

Remove-Item -LiteralPath $statePath -Force
Write-Output "Demo services stopped. Runtime data remains at $runtimeRoot."
