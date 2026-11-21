# Majordomo always-on daemon — Windows Task Scheduler installer.
#
# Run in PowerShell (no admin needed; the task runs as your user, at
# logon):
#   powershell -ExecutionPolicy Bypass -File deploy\install-windows-task.ps1
#
# If majordomo.exe is not on your PATH, pass its full path:
#   ... install-windows-task.ps1 -MajordomoExe C:\path\to\majordomo.exe
#
# Remove the task later with:
#   Unregister-ScheduledTask -TaskName "Majordomo Daemon" -Confirm:$false
#
# Configuration: Majordomo reads MAJORDOMO_* environment variables, so
# set them in your user environment (Settings > Environment variables)
# or in a .env file in your home directory.

param(
    [string]$MajordomoExe = ""
)

$ErrorActionPreference = "Stop"

if (-not $MajordomoExe) {
    $found = Get-Command majordomo.exe -ErrorAction SilentlyContinue
    if ($found) { $MajordomoExe = $found.Source }
}
if (-not $MajordomoExe -or -not (Test-Path $MajordomoExe)) {
    throw "Could not find majordomo.exe. Install Majordomo first (pip install -e .) or pass -MajordomoExe <path>."
}

$action = New-ScheduledTaskAction -Execute $MajordomoExe -Argument "daemon --interval 30"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName "Majordomo Daemon" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Majordomo always-on daemon: fires due reminders into the inbox session." `
    -Force | Out-Null

Write-Host "Installed. The Majordomo daemon will start at logon (task: 'Majordomo Daemon')."
Write-Host "Run it once right now with:  majordomo daemon --once"
