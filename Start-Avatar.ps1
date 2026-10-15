param([switch]$Restart, [switch]$NoWindow, [switch]$Audio)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$avatarPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$avatarUrl = 'http://127.0.0.1:8765'
$avatarLogs = Join-Path $PSScriptRoot 'webcam_mapper\output'
if (-not (Test-Path -LiteralPath $avatarPython)) {
    throw 'Python-Umgebung fehlt. Bitte zuerst die Einrichtung laut webcam_mapper/README.md ausfuehren.'
}
function Test-AvatarServer {
    try {
        $avatarHealth = Invoke-RestMethod "$avatarUrl/healthz" -TimeoutSec 2
        return ($avatarHealth.ok -eq $true -and $avatarHealth.cpu -eq $true -and $avatarHealth.version -eq '2.3.2')
    } catch { return $false }
}
if ($Restart -or -not (Test-AvatarServer)) {
    # Replace only an older server belonging to this project's Python launcher.
    $avatarListener = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($avatarListener) {
        $avatarOld = Get-CimInstance Win32_Process -Filter "ProcessId = $($avatarListener.OwningProcess)"
        $avatarParent = Get-CimInstance Win32_Process -Filter "ProcessId = $($avatarOld.ParentProcessId)"
        if ($avatarOld.CommandLine -like '*-m webcam_mapper.app*' -and ($avatarOld.ExecutablePath -eq $avatarPython -or $avatarParent.ExecutablePath -eq $avatarPython)) {
            Stop-Process -Id $avatarOld.ProcessId
            Start-Sleep -Milliseconds 500
        } else { throw 'Port 8765 wird von einem anderen Prozess verwendet.' }
    }
    New-Item -ItemType Directory -Force -Path $avatarLogs | Out-Null
    $avatarProcess = Start-Process -FilePath $avatarPython -ArgumentList '-m', 'webcam_mapper.app', '--serve' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $avatarLogs 'server.log') -RedirectStandardError (Join-Path $avatarLogs 'server-error.log')
    $avatarDeadline = (Get-Date).AddSeconds(120)
    while (-not (Test-AvatarServer)) {
        if ($avatarProcess.HasExited -or (Get-Date) -gt $avatarDeadline) {
            Get-Content -LiteralPath (Join-Path $avatarLogs 'server-error.log') -Tail 20
            throw 'Avatar-Server konnte nicht starten. Siehe webcam_mapper/output/server-error.log.'
        }
        Start-Sleep -Milliseconds 250
    }
}
if ($NoWindow) { return }
$avatarLaunchUrl = if ($Audio) { "$avatarUrl/?mode=audio" } else { "$avatarUrl/?autostart=1" }
$avatarEdge = Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'
if (Test-Path -LiteralPath $avatarEdge) {
    Start-Process -FilePath $avatarEdge -ArgumentList "--app=$avatarLaunchUrl", '--window-size=1400,900'
} else { Start-Process $avatarLaunchUrl }
