[CmdletBinding()]
param(
    [ValidateSet("Start", "Status", "Log", "Ack", "Cleanup")]
    [string] $Action = "Start",
    [string] $RunId,
    [string] $AdbPath = (Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"),
    [string] $AdbServerSocket = "tcp:192.168.10.50:5038",
    [switch] $NoMonitor
)

$ErrorActionPreference = "Stop"
$remoteBase = "/data/foxair_ota_runner"
$remoteRuns = "$remoteBase/runs"
$localSupervisor = Join-Path $PSScriptRoot "dtu_ota_supervisor_stage2.sh"
$localHook = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\..\tools\phnix_ota\phnix_ota_runtime_hook"))
$previousAdbServerSocket = $env:ADB_SERVER_SOCKET

function Invoke-Adb {
    param([Parameter(Mandatory)][string[]] $Arguments)

    # adb writes normal progress messages to stderr. Windows PowerShell 5.x can
    # otherwise turn those into NativeCommandError records, so only the native
    # process exit code decides success here.
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & $AdbPath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    $text = (($output | ForEach-Object { $_.ToString() }) | Out-String).Trim()
    if ($exitCode -ne 0) {
        throw "ADB failed with exit code $exitCode`: $text"
    }
    return $text
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
    $last = $last.Trim()
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

    foreach ($field in @(
        "schema", "run_id", "state", "phase", "terminal", "progress", "pid",
        "updated_at", "transfer_started", "original_service_authoritative", "recovery"
    )) {
        if ($field -notin $status.PSObject.Properties.Name) {
            throw "Status for run '$Id' is missing '$field': $raw"
        }
    }
    if ($status.schema -ne "foxair-dtu-ota-run-v1") {
        throw "Unexpected Stage-2 status schema '$($status.schema)'."
    }
    if ($status.run_id -ne $Id) {
        throw "Status run_id '$($status.run_id)' does not match requested run '$Id'."
    }
    return $status
}

function Show-Status {
    param([Parameter(Mandatory)] $Status)
    Write-Host ("run={0} state={1} phase={2} terminal={3} progress={4}% runner_pid={5} ppid={6} hook_pid={7} updated={8}" -f `
        $Status.run_id, $Status.state, $Status.phase, $Status.terminal, $Status.progress,
        $Status.runner_pid, $Status.ppid, $Status.hook_pid, $Status.updated_at)
    Write-Host ("transfer_started={0} original_service_authoritative={1} recovery={2}" -f `
        $Status.transfer_started, $Status.original_service_authoritative, $Status.recovery)
    if ($Status.reason) {
        Write-Host ("reason={0}" -f $Status.reason)
    }
    if ($Status.detail) {
        Write-Host ("detail={0}" -f $Status.detail)
    }
}

function Start-Run {
    foreach ($path in @($localSupervisor, $localHook)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Required Stage-2 file is missing: '$path'."
        }
    }

    $id = if ($RunId) { $RunId } else { "stage2-{0}-{1}" -f (Get-Date -Format "yyyyMMdd-HHmmss"), (Get-Random -Minimum 1000 -Maximum 9999) }
    Assert-RunId -Value $id

    $runDir = "$remoteRuns/$id"
    $payloadDir = "$runDir/payload"
    $remoteSupervisor = "$runDir/dtu_ota_supervisor_stage2.sh"
    $remoteHook = "$payloadDir/phnix_ota_runtime_hook"
    $expectedHashFile = "$runDir/hook.sha256.expected"
    $hookSha256 = (Get-FileHash -LiteralPath $localHook -Algorithm SHA256).Hash.ToLowerInvariant()

    Write-Host "Preparing Stage-2 DTU run $id ..."
    Write-Host "Runtime hook SHA-256: $hookSha256"

    Invoke-Adb -Arguments @("shell", "mkdir -p '$payloadDir'") | Out-Null
    Invoke-Adb -Arguments @("push", $localSupervisor, $remoteSupervisor) | Out-Null
    Invoke-Adb -Arguments @("push", $localHook, $remoteHook) | Out-Null
    Invoke-Adb -Arguments @("shell", "chmod 700 '$remoteSupervisor' '$remoteHook'") | Out-Null
    Invoke-Adb -Arguments @("shell", "printf '%s\n' '$hookSha256' > '$expectedHashFile'") | Out-Null

    Write-Host "Starting detached Stage-2 supervisor (hook action: verify only) ..."
    Invoke-Adb -Arguments @(
        "shell",
        "setsid /system/bin/sh '$remoteSupervisor' '$id' verify </dev/null >'$runDir/launcher.log' 2>&1 & sleep 2"
    ) | Out-Null

    try {
        $status = Read-Status -Id $id
    }
    catch {
        $launcher = Invoke-Adb -Arguments @("shell", "cat '$runDir/launcher.log' 2>/dev/null || true")
        if ($launcher) {
            Write-Host "launcher.log:"
            Write-Host $launcher
        }
        throw
    }

    Show-Status -Status $status

    if ([bool]$status.terminal) {
        Write-Host "Stage-2 verify already reached a terminal state. Diagnostic files remain stored on the modem."
        Write-Host "Run ID: $id"
        return
    }

    if ($NoMonitor) {
        Write-Host "Monitoring detached. The DTU supervisor and its local hook child continue independently of this PowerShell process."
        Write-Host "Run ID: $id"
        return
    }

    while (-not [bool]$status.terminal) {
        Start-Sleep -Seconds 2
        try {
            $status = Read-Status -Id $id
            Show-Status -Status $status
        }
        catch {
            Write-Warning "ADB monitoring was lost. No stop/kill is sent to the DTU supervisor or hook."
            Write-Warning $_.Exception.Message
            Write-Host "Later status query: .\Invoke-DtuOtaSupervisorStage2.ps1 -Action Status -RunId $id -AdbServerSocket '$AdbServerSocket'"
            return
        }
    }

    Write-Host "Terminal Stage-2 result retained on the modem. Use -Action Log for hook details, then Ack/Cleanup deliberately."
}

function Show-Logs {
    param([Parameter(Mandatory)][string] $Id)
    $runDir = "$remoteRuns/$Id"
    foreach ($entry in @(
        @{ Name = "runner.log"; Path = "$runDir/runner.log" },
        @{ Name = "hook-status.json"; Path = "$runDir/hook-status.json" },
        @{ Name = "hook.log"; Path = "$runDir/hook.log" },
        @{ Name = "launcher.log"; Path = "$runDir/launcher.log" }
    )) {
        Write-Host "--- $($entry.Name) ---"
        $text = Invoke-Adb -Arguments @("shell", "cat '$($entry.Path)' 2>/dev/null || true")
        if ($text) { Write-Host $text } else { Write-Host "<empty or missing>" }
    }
}

function Ack-Run {
    param([Parameter(Mandatory)][string] $Id)
    $status = Read-Status -Id $Id
    Show-Status -Status $status
    if (-not [bool]$status.terminal) {
        throw "Run '$Id' is not terminal; refusing acknowledgement."
    }
    Invoke-Adb -Arguments @("shell", "touch '$remoteRuns/$Id/acknowledged'") | Out-Null
    Write-Host "Terminal Stage-2 result acknowledged. Diagnostic files are still retained."
}

function Cleanup-Run {
    param([Parameter(Mandatory)][string] $Id)
    $status = Read-Status -Id $Id
    Show-Status -Status $status
    if (-not [bool]$status.terminal) {
        throw "Run '$Id' is not terminal; refusing cleanup."
    }

    $runDir = "$remoteRuns/$Id"
    $ackState = Invoke-Adb -Arguments @(
        "shell",
        "if [ -f '$runDir/acknowledged' ]; then echo ACK_OK; else echo ACK_MISSING; fi"
    )
    if ($ackState -ne "ACK_OK") {
        throw "Cleanup precondition failed: $ackState"
    }

    $runnerPidText = Invoke-Adb -Arguments @("shell", "cat '$runDir/runner.pid' 2>/dev/null || true")
    $runnerPidText = $runnerPidText.Trim()
    if ($runnerPidText) {
        if ($runnerPidText -notmatch '^[0-9]+$') {
            throw "Cleanup precondition failed: invalid runner.pid '$runnerPidText'."
        }
        $runnerPid = [int64]$runnerPidText
        $cmdline = Invoke-Adb -Arguments @(
            "shell",
            "if [ -r '/proc/$runnerPid/cmdline' ]; then tr '\000' ' ' < '/proc/$runnerPid/cmdline'; fi"
        )
        if ($cmdline -match 'dtu_ota_supervisor_stage2\.sh') {
            throw "Cleanup precondition failed: runner PID $runnerPid is still an active Stage-2 supervisor."
        }
        if ($cmdline) {
            Write-Host "runner.pid $runnerPid currently belongs to another process; it will not be touched."
        }
    }

    Invoke-Adb -Arguments @("shell", "rm -rf '$runDir'") | Out-Null
    Write-Host "Stage-2 run directory removed after terminal status and explicit acknowledgement."
}

if (-not (Test-Path -LiteralPath $AdbPath -PathType Leaf)) {
    throw "ADB was not found at '$AdbPath'. Pass another path with -AdbPath."
}

try {
    $env:ADB_SERVER_SOCKET = $AdbServerSocket

    switch ($Action) {
        "Start"   { Start-Run }
        "Status"  { $id = Resolve-RunId; Show-Status -Status (Read-Status -Id $id) }
        "Log"     { $id = Resolve-RunId; Show-Logs -Id $id }
        "Ack"     { $id = Resolve-RunId; Ack-Run -Id $id }
        "Cleanup" { $id = Resolve-RunId; Cleanup-Run -Id $id }
    }
}
finally {
    $env:ADB_SERVER_SOCKET = $previousAdbServerSocket
}
