$ErrorActionPreference = 'Stop'
$taskName = 'JournalFigureWorkbench'
$taskRoot = "C:/Users/xdxxk/Documents/Codex/2026-09-20/i"
$nodePath = "C:/Program Files/nodejs/node.exe"
$actionArguments = "work/october-review/run-service.mjs"
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    if ($existingTask.Actions.Arguments -notcontains $actionArguments -and $existingTask.Actions.Arguments -notcontains 'work/october-review/server.mjs') { throw 'Existing task has a different action; preserving it.' }
    if ($existingTask.Actions.Count -ne 1 -or [IO.Path]::GetFullPath($existingTask.Actions[0].Execute) -ne [IO.Path]::GetFullPath($nodePath)) { throw 'Existing task uses a different executable; preserving it.' }
    $action = New-ScheduledTaskAction -Execute $nodePath -Argument $actionArguments -WorkingDirectory $taskRoot
    $existingTask.Settings.RestartCount = 3
    $existingTask.Settings.RestartInterval = 'PT1M'
    $existingTask.Settings.StartWhenAvailable = $true
    $triggers = @($existingTask.Triggers | Where-Object { $null -ne $_ })
    if (-not ($triggers | Where-Object { $_.CimClass.CimClassName -eq 'MSFT_TaskLogonTrigger' })) { $triggers += $logonTrigger }
    Set-ScheduledTask -TaskName $taskName -Action $action -Settings $existingTask.Settings -Trigger $triggers | Out-Null
} else {
    $action = New-ScheduledTaskAction -Execute $nodePath -Argument $actionArguments -WorkingDirectory $taskRoot
    $principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
    Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Trigger $logonTrigger -Description 'Local journal workbench server; starts when the user logs on.' | Out-Null
}
Start-ScheduledTask -TaskName $taskName
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State
