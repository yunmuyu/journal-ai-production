param([int]$TimeoutSeconds = 5)
$ErrorActionPreference = 'Stop'
$task = Get-ScheduledTask -TaskName 'NovemberFigureWorkbench' -ErrorAction SilentlyContinue
$listener = @(Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 18741 -State Listen -ErrorAction SilentlyContinue)
$server = @(Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object { $_.CommandLine -match '(?i)november-workbench[\\/]server\.mjs' })
$result = [ordered]@{
  checkedAt = [DateTimeOffset]::Now.ToString('o')
  taskState = if ($task) { [string]$task.State } else { 'missing' }
  listenerPids = @($listener | ForEach-Object { $_.OwningProcess })
  serverPids = @($server | ForEach-Object { $_.ProcessId })
  state = 'unavailable'
  rows = $null
  message = $null
}
try {
  $data = Invoke-RestMethod -Uri 'http://127.0.0.1:18741/data' -TimeoutSec $TimeoutSeconds
  if ($null -eq $data.rows -or $null -eq $data.articles) { throw 'Data response lacks rows or articles' }
  $result.state = 'ready'; $result.rows = @($data.rows).Count
} catch {
  $result.message = $_.Exception.Message
  if ($listener.Count -gt 0) { $result.state = 'listening_not_ready' }
  elseif ($server.Count -gt 0) { $result.state = 'starting_or_stalled' }
}
$result | ConvertTo-Json -Depth 5
if ($result.state -ne 'ready') { exit 2 }
