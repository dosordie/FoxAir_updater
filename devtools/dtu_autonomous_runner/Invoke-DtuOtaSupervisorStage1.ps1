[CmdletBinding()]
param(
    [ValidateSet("Start", "Status", "Abort", "Ack", "Cleanup")]
    [string] $Action = "Start",
    [string] $RunId,
    [string] $AdbPath = (Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"),
    [string] $AdbServerSocket = "tcp:192.168.10.50:5038",
    [switch] $NoMonitor
)

$ErrorActionPreference = "Stop"
$remoteBase = "/data/foxair_ota_runner"
$remoteRuns = "$remoteBase/runs"
$localRunner = Join-Path $PSScriptRoot "dtu_ota_supervisor_stage1.sh"
$previousAdbServerSocket = $env:ADB_SERVER_SOCKET

function Invoke-Adb {
    param([Parameter(Mandatory)][string[]] $Arguments)

    $output = & $AdbPath @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        $detail = ($output | Out-String).Trim()
        throw "ADB failed with exit code $LASTEXITCODE`: $detail"
    }
    return ($output | Out-String).Trim()
}

function Assert-RunId {
    param([Parameter(Mandatory)][string] $Value)
    if ($Value -notmatch '^[A-Za-z0-9._-]+$') {
        throw "Invalid run ID '$Value'."
    }
}

function Resolve-RunId {
    if ($RunId) {
        Assert-RunId -Value $RunId
        return $RunId
    }
    $last = Invoke-Adb -Arguments @("shell", "cat '$remoteBase/last_run_id' 2>/dev/null || true")
    if (-not $last) {
        throw "No run ID was supplied and the modem has no last_run_id."
    }
    Assert-RunId -Value $last
    return $last
}

function Read-Status {
    param([Parameter(Mandatory)][string] $Id)
    $raw = Invoke-Adb -Arguments @("shell", "cat '$remoteRuns/$Id/status.json'")
    try {
        $status = $raw | ConvertFrom-Json
    }
    catch {
        throw "The modem returned invalid status JSON for run '$Id': $raw"
    }
    foreach ($field in @("schema", "run_id", "state", "phase", "terminal", "progress", "pid", "time")) {
        if ($field -notin $status.PSObject.Properties.Name) {
            throw "Status for run '$Id' is missing '$field': $raw"
        }
    }
    if ($status.run_id -ne $Id) {
        throw "Status run_id '$($status.run_id)' does not match requested run '$Id'."
    }
    return $status
}

function Show-Status {
    param([Parameter(Mandatory)] $Status)
    Write-Host ("run={0} state={1} phase={2} terminal={3} progress={4}% pid={5} ppid={6} time={7}" -f `
        $Status.run_id, $Status.state, $Status.phase, $Status.terminal, $Status.progress, $Status.pid, $Status.ppid, $Status.time)
    if ($Status.reason) {
        Write-Host ("reason={0}" -f $Status.reason)
    }
    if ($Status.detail) {
        Write-Host ("detail={0}" -f $Status.detail)
    }
}

function Start-Run {
    if (-not (Test-Path -LiteralPath $localRunner -PathType Leaf)) {
        throw "Stage-1 runner is missing: '$localRunner'."
    }

    $id = if ($RunId) { $RunId } else { "{0}-{1}" -f (Get-Date -Format "yyyyMMdd-HHmmss"), (Get-Random -Minimum 1000 -Maximum 9999) }
    Assert-RunId -Value $id
    $runDir = "$remoteRuns/$id"
    $remoteRunner = "$runDir/dtu_ota_supervisor_stage1.sh"

    Write-Host "Preparing DTU run $id ..."
    Invoke-Adb -Arguments @("shell", "mkdir -p '$runDir'") | Out-Null
    Invoke-Adb -Arguments @("push", $localRunner, $remoteRunner) | Out-Null
    Invoke-Adb -Arguments @("shell", "chmod 700 '$remoteRunner'") | Out-Null

    Write-Host "Starting detached supervisor with setsid ..."
    Invoke-Adb -Arguments @(
        "shell",
        "setsid /system/bin/sh '$remoteRunner' '$id' </dev/null >'$runDir/launcher.log' 2>&1 & sleep 2"
    ) | Out-Null

    $status = Read-Status -Id $id
    Show-Status -Status $status

    if ($NoMonitor) {
        Write-Host "Monitoring detached. The modem runner continues independently."
        Write-Host "Run ID: $id"
        return
    }

    while (-not [bool]$status.terminal) {
        Start-Sleep -Seconds 5
        try {
            $status = Read-Status -Id $id
            Show-Status -Status $status
        }
        catch {
            Write-Warning "ADB monitoring was lost. No stop/kill is sent to the modem runner."
            Write-Warning $_.Exception.Message
            Write-Host "Later status query: .\Invoke-DtuOtaSupervisorStage1.ps1 -Action Status -RunId $id"
            return
        }
    }

    Write-Host "Terminal status retained on the modem. Use -Action Ack and then -Action Cleanup deliberately."
}

function Request-Abort {
    param([Parameter(Mandatory)][string] $Id)
    $status = Read-Status -Id $Id
    Show-Status -Status $status
    if ([bool]$status.terminal) {
        throw "Run '$Id' is already terminal; no abort request was written."
    }
    Invoke-Adb -Arguments @("shell", "touch '$remoteRuns/$Id/abort.request'") | Out-Null
    Write-Host "Controlled abort request written. Stage 1 will notice it without killing the process from ADB."
}

function Ack-Run {
    param([Parameter(Mandatory)][string] $Id)
    $status = Read-Status -Id $Id
    Show-Status -Status $status
    if (-not [bool]$status.terminal) {
        throw "Run '$Id' is not terminal; refusing acknowledgement."
    }
    Invoke-Adb -Arguments @("shell", "touch '$remoteRuns/$Id/acknowledged'") | Out-Null
    Write-Host "Terminal result acknowledged. Diagnostic files are still retained."
}

function Cleanup-Run {
    param([Parameter(Mandatory)][string] $Id)
    $status = Read-Status -Id $Id
    Show-Status -Status $status
    if (-not [bool]$status.terminal) {
        throw "Run '$Id' is not terminal; refusing cleanup."
    }

    $runDir = "$remoteRuns/$Id"
    $check = Invoke-Adb -Arguments @(
        "shell",
        "if [ ! -f '$runDir/acknowledged' ]; then echo ACK_MISSING; exit 41; fi; " +
        "pid=$(cat '$runDir/runner.pid' 2>/dev/null || true); " +
        "if [ -n \"$pid\" ] && [ -r \"/proc/$pid/cmdline\" ] && tr '\0' ' ' <\"/proc/$pid/cmdline\" | grep -q 'dtu_ota_supervisor_stage1.sh'; then echo RUNNER_STILL_ACTIVE; exit 42; fi; " +
        "echo OK"
    )
    if ($check -ne "OK") {
        throw "Cleanup precondition failed: $check"
    }

    Invoke-Adb -Arguments @(
        "shell",
        "TARGET='$runDir'; case \"$TARGET\" in '$remoteRuns/'*) rm -rf \"$TARGET\" ;; *) exit 43 ;; esac"
    ) | Out-Null
    Write-Host "Run directory removed after terminal status and explicit acknowledgement."
}

if (-not (Test-Path -LiteralPath $AdbPath -PathType Leaf)) {
    throw "ADB was not found at '$AdbPath'. Pass another path with -AdbPath."
}

try {
    $env:ADB_SERVER_SOCKET = $AdbServerSocket

    switch ($Action) {
        "Start"   { Start-Run }
        "Status"  { $id = Resolve-RunId; Show-Status -Status (Read-Status -Id $id) }
        "Abort"   { $id = Resolve-RunId; Request-Abort -Id $id }
        "Ack"     { $id = Resolve-RunId; Ack-Run -Id $id }
        "Cleanup" { $id = Resolve-RunId; Cleanup-Run -Id $id }
    }
}
finally {
    $env:ADB_SERVER_SOCKET = $previousAdbServerSocket
}
