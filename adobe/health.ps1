param([switch]$RestartEmpty)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$report = [ordered]@{status='com_unavailable'; observedAt=(Get-Date).ToUniversalTime().ToString('o'); documents=@(); restartAllowed=$false}
function DocumentState($application) {
 $items = @()
 for ($i=1; $i -le $application.Documents.Count; $i++) {
  $document = $application.Documents.Item($i)
  $items += [pscustomobject]@{name=$document.Name; saved=[bool]$document.Saved; pageItems=[int]$document.PageItems.Count}
 }
 return $items
}
function EmitReport { $report | ConvertTo-Json -Depth 6 -Compress }
try {
 $apps = @(Get-Process Illustrator -ErrorAction SilentlyContinue)
 if ($apps.Count -eq 0) { $report.status='not_running'; EmitReport; exit }
 if ($apps.Count -ne 1 -or -not $apps[0].Responding) { $report.status='busy'; $report.reason='Multiple or unresponsive Illustrator processes'; EmitReport; exit }
 $report.processId=$apps[0].Id
 . "$PSScriptRoot/window-state.ps1"
 $dialogs=@(Get-IllustratorDialogs $report.processId)
 if($dialogs.Count){$report.status='startup_dialog';$report.dialogs=$dialogs;EmitReport;exit}
 $workers = @(Get-CimInstance Win32_Process -Filter "Name='cscript.exe'" | Where-Object { $_.CommandLine -match '[\/]adobe[\/]invoke\.js' })
 if ($workers.Count) { $report.status='busy'; $report.workerIds=@($workers.ProcessId); EmitReport; exit }
 # ROT attachment never starts an application or touches foreground focus.
 $app = [Runtime.InteropServices.Marshal]::GetActiveObject('Illustrator.Application.CC.2019')
 $report.version=$app.Version
 $report.documents=@(DocumentState $app)
 $report.restartAllowed=@($report.documents | Where-Object { -not $_.saved -or $_.pageItems -ne 0 }).Count -eq 0
 if ($RestartEmpty) {
  if (-not $report.restartAllowed) { $report.status='restart_refused'; $report.reason='Saved content or unsaved documents require user preservation first'; EmitReport; exit }
  $again = @(Get-Process Illustrator -ErrorAction SilentlyContinue)
  $documentsAgain = @(DocumentState $app)
  if ($again.Count -ne 1 -or $again[0].Id -ne $report.processId -or @($documentsAgain | Where-Object { -not $_.saved -or $_.pageItems -ne 0 }).Count) {
   $report.status='restart_refused'; $report.reason='Application or document state changed'; EmitReport; exit
  }
  $executable=$apps[0].Path
  $app.Quit()
  [Runtime.InteropServices.Marshal]::FinalReleaseComObject($app) | Out-Null
  $app=$null
  [GC]::Collect(); [GC]::WaitForPendingFinalizers()
  $deadline=(Get-Date).AddSeconds(10)
  while (Get-Process -Id $report.processId -ErrorAction SilentlyContinue) {
   if ((Get-Date) -gt $deadline) { $report.status='restart_pending'; EmitReport; exit }
   Start-Sleep -Milliseconds 200
  }
  $started=Start-Process -FilePath $executable -WindowStyle Hidden -PassThru
  $report.processId=$started.Id
  $report.restarted=$true
  $deadline=(Get-Date).AddSeconds(25)
  while($null -eq $app){
   $dialogs=@(Get-IllustratorDialogs $report.processId)
   if($dialogs.Count){$report.status='startup_dialog';$report.dialogs=$dialogs;EmitReport;exit}
   if(-not (Get-Process -Id $report.processId -ErrorAction SilentlyContinue)){$report.status='startup_exited';EmitReport;exit}
   try{$app=[Runtime.InteropServices.Marshal]::GetActiveObject('Illustrator.Application.CC.2019')}catch{}
   if($null -eq $app -and (Get-Date) -gt $deadline){$report.status='restart_pending';EmitReport;exit}
   if($null -eq $app){Start-Sleep -Milliseconds 250}
  }
  $report.documents=@(DocumentState $app)
 }
 try {
  $answer=$app.DoJavaScript('"JFW_HEALTH_OK";')
  if ($answer -ne 'JFW_HEALTH_OK') { throw 'Unexpected script sentinel' }
  $report.status='healthy'
 } catch {
  $report.status='script_fault'
  $exception=$_.Exception
  while ($exception.InnerException) { $exception=$exception.InnerException }
  $report.hresult=$exception.HResult
  $report.message=$exception.Message
 }
} catch {
 $report.message=$_.Exception.Message
}
EmitReport
