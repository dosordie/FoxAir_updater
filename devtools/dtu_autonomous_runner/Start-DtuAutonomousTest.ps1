[CmdletBinding()]
param(
    [string] $AdbPath = (Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"),
    [string] $AdbServerSocket = "tcp:192.168.10.50:5038"
)

$ErrorActionPreference = "Stop"
$remoteDirectory = "/data/foxair_autonomous_test"
$remoteRunner = "$remoteDirectory/dtu_autonomous_test_runner.sh"
$remoteStatus = "$remoteDirectory/status.json"
$localRunner = Join-Path $PSScriptRoot "dtu_autonomous_test_runner.sh"
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

function Read-RunnerStatus {
    $rawStatus = Invoke-Adb -Arguments @("shell", "cat '$remoteStatus'")
    try {
        $status = $rawStatus | ConvertFrom-Json
    }
    catch {
        throw "The modem returned invalid status JSON: $rawStatus"
    }

    foreach ($field in @("state", "step", "pid", "time")) {
        if ($field -notin $status.PSObject.Properties.Name) {
            throw "The modem status is missing '$field': $rawStatus"
        }
    }

    return $status
}

if (-not (Test-Path -LiteralPath $AdbPath -PathType Leaf)) {
    throw "ADB was not found at '$AdbPath'. Pass another path with -AdbPath."
}
if (-not (Test-Path -LiteralPath $localRunner -PathType Leaf)) {
    throw "The modem runner is missing: '$localRunner'."
}

try {
    $env:ADB_SERVER_SOCKET = $AdbServerSocket

    $existingPid = Invoke-Adb -Arguments @(
        "shell",
        "if [ -f '$remoteDirectory/runner.pid' ]; then cat '$remoteDirectory/runner.pid'; fi"
    )
    if ($existingPid -match "^[0-9]+$") {
        $existingCommand = Invoke-Adb -Arguments @(
            "shell",
            "if [ -r '/proc/$existingPid/cmdline' ]; then tr '\0' ' ' <'/proc/$existingPid/cmdline'; fi"
        )
        if ($existingCommand -like "*$remoteRunner*") {
            throw "Runner PID $existingPid is still active on the modem. Monitor its status or stop it deliberately before starting another test."
        }
    }

    Write-Host "Preparing isolated modem test directory..."
    Invoke-Adb -Arguments @(
        "shell",
        "mkdir -p '$remoteDirectory' && rm -f '$remoteStatus' '$remoteDirectory'/status.json.tmp.* '$remoteDirectory/runner.pid' '$remoteDirectory/runner.log' '$remoteDirectory/launcher.log'"
    ) | Out-Null
    Invoke-Adb -Arguments @("push", $localRunner, $remoteRunner) | Out-Null
    Invoke-Adb -Arguments @("shell", "chmod 700 '$remoteRunner'") | Out-Null

    Write-Host "Starting detached modem runner..."
    Invoke-Adb -Arguments @(
        "shell",
        "setsid /system/bin/sh '$remoteRunner' </dev/null >'$remoteDirectory/launcher.log' 2>&1 & sleep 2"
    ) | Out-Null

    $initialCheck = Invoke-Adb -Arguments @(
        "shell",
        "if [ -f '$remoteStatus' ]; then cat '$remoteStatus'; else echo STATUS_MISSING; exit 44; fi"
    )
    try {
        $status = $initialCheck | ConvertFrom-Json
    }
    catch {
        throw "No valid initial status was available after the two-second startup check: $initialCheck"
    }

    foreach ($field in @("state", "step", "pid", "time")) {
        if ($field -notin $status.PSObject.Properties.Name) {
            throw "The initial modem status is missing '$field': $initialCheck"
        }
    }

    while ($true) {
        Write-Host ("state={0} step={1} pid={2} time={3}" -f $status.state, $status.step, $status.pid, $status.time)

        if ($status.state -eq "completed") {
            Write-Host "The autonomous modem test completed."
            break
        }
        if ($status.state -eq "interrupted") {
            throw "The modem runner reported an interruption."
        }
        if ($status.state -ne "running") {
            throw "The modem runner reported an unknown state: '$($status.state)'."
        }

        Start-Sleep -Seconds 5
        $status = Read-RunnerStatus
    }
}
finally {
    $env:ADB_SERVER_SOCKET = $previousAdbServerSocket
}
