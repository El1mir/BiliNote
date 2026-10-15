[CmdletBinding()]
param(
    [switch]$SmokeTest
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendPort = 8483
$FrontendPort = 3015
$BackendUrl = "http://127.0.0.1:$BackendPort/api/sys_check"
$FrontendUrl = "http://127.0.0.1:$FrontendPort/"
$BackendProcess = $null
$FrontendProcess = $null
$StartupClock = [System.Diagnostics.Stopwatch]::StartNew()

function Stop-ChildTree($Process) {
    if ($null -ne $Process -and -not $Process.HasExited) {
        & taskkill.exe /PID $Process.Id /T /F 2>$null | Out-Null
        $Process.WaitForExit(5000) | Out-Null
    }
}

function Test-Ready([string]$Url) {
    try {
        $Response = Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing
        return $Response.StatusCode -ge 200 -and $Response.StatusCode -lt 400
    }
    catch {
        return $false
    }
}

function Wait-Ready([string]$Name, [string]$Url, $Process, [int]$TimeoutSeconds = 180) {
    $Clock = [System.Diagnostics.Stopwatch]::StartNew()
    while ($Clock.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        if ($Process.HasExited) {
            throw "$Name exited before becoming ready (exit code $($Process.ExitCode))."
        }
        if (Test-Ready $Url) {
            $Elapsed = [math]::Round($Clock.Elapsed.TotalSeconds, 2)
            Write-Host "[$Name] ready in [32m$($Elapsed)s[0m"
            return $Elapsed
        }
        Start-Sleep -Milliseconds 150
    }
    throw "$Name did not become ready within $TimeoutSeconds seconds: $Url"
}

try {
    Write-Host "BiliNote web launcher | one console | Ctrl+C stops both servers"
    $Python = Join-Path $Root 'backend/.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw "Backend venv is missing: $Python"
    }
    $NodeCommand = Get-Command node.exe -ErrorAction Stop
    $Node = $NodeCommand.Source
    $Vite = Join-Path $Root 'BillNote_frontend/node_modules/vite/bin/vite.js'
    if (-not (Test-Path -LiteralPath $Vite -PathType Leaf)) {
        throw "Vite is missing. Install frontend dependencies first: $Vite"
    }

    $Occupied = @(Get-NetTCPConnection -LocalPort $BackendPort,$FrontendPort -State Listen -ErrorAction SilentlyContinue)
    if ($Occupied.Count -gt 0) {
        $Owners = $Occupied | Select-Object LocalPort, OwningProcess -Unique | ForEach-Object { "$($_.LocalPort) (PID $($_.OwningProcess))" }
        throw "Required port(s) already in use: $($Owners -join ', '). Stop the listed process yourself and retry; this launcher will not kill unrelated processes."
    }

    Write-Host '[1/2] Starting backend and Vite in parallel...'
    $BackendClock = [System.Diagnostics.Stopwatch]::StartNew()
    $BackendProcess = Start-Process -FilePath $Python -ArgumentList 'main.py' -WorkingDirectory (Join-Path $Root 'backend') -PassThru -NoNewWindow
    $FrontendClock = [System.Diagnostics.Stopwatch]::StartNew()
    $ViteArgument = '"' + $Vite + '"'
    $FrontendProcess = Start-Process -FilePath $Node -ArgumentList $ViteArgument -WorkingDirectory (Join-Path $Root 'BillNote_frontend') -PassThru -NoNewWindow

    $BackendReady = $false
    $FrontendReady = $false
    $BackendSeconds = $null
    $FrontendSeconds = $null
    while (-not ($BackendReady -and $FrontendReady)) {
        if ($StartupClock.Elapsed.TotalSeconds -ge 180) { throw 'Services did not both become ready within 180 seconds.' }
        if (-not $BackendReady) {
            if ($BackendProcess.HasExited) { throw "Backend exited before becoming ready (exit code $($BackendProcess.ExitCode))." }
            if (Test-Ready $BackendUrl) {
                $BackendReady = $true
                $BackendSeconds = [math]::Round($BackendClock.Elapsed.TotalSeconds, 2)
                Write-Host "[Backend] ready in $($BackendSeconds)s"
            }
        }
        if (-not $FrontendReady) {
            if ($FrontendProcess.HasExited) { throw "Frontend exited before becoming ready (exit code $($FrontendProcess.ExitCode))." }
            if (Test-Ready $FrontendUrl) {
                $FrontendReady = $true
                $FrontendSeconds = [math]::Round($FrontendClock.Elapsed.TotalSeconds, 2)
                Write-Host "[Frontend] ready in $($FrontendSeconds)s"
            }
        }
        if (-not ($BackendReady -and $FrontendReady)) { Start-Sleep -Milliseconds 150 }
    }
    $StartupClock.Stop()
    Write-Host ("Both services ready in {0:N2}s (backend {1:N2}s; frontend {2:N2}s)." -f $StartupClock.Elapsed.TotalSeconds, $BackendSeconds, $FrontendSeconds)

    if (-not $SmokeTest) {
        Start-Process $FrontendUrl | Out-Null
        Write-Host 'Browser opened. Press Ctrl+C here to stop both services.'
        while (-not $BackendProcess.HasExited -and -not $FrontendProcess.HasExited) {
            Start-Sleep -Milliseconds 500
        }
        if ($BackendProcess.HasExited) { Write-Host "Backend exited (code $($BackendProcess.ExitCode))." }
        if ($FrontendProcess.HasExited) { Write-Host "Frontend exited (code $($FrontendProcess.ExitCode))." }
    }
}
catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    if (-not $SmokeTest) { Read-Host 'Press Enter to close' | Out-Null }
    exit 1
}
finally {
    Stop-ChildTree $FrontendProcess
    Stop-ChildTree $BackendProcess
}
