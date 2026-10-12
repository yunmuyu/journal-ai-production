param([Parameter(Mandatory=$true)][string]$StatePath)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class JournalNoticeWindow {
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr handle, int command);
 [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr handle, IntPtr after, int x, int y, int cx, int cy, uint flags);
}
'@
$form = New-Object System.Windows.Forms.Form
$form.Text = '期刊图件 · Adobe 自动处理'
$form.Size = New-Object System.Drawing.Size(520,185)
$form.StartPosition = 'CenterScreen'
$form.TopMost = $true
$form.BackColor = [System.Drawing.Color]::FromArgb(255,205,70)
$form.FormBorderStyle = 'FixedToolWindow'
$form.ControlBox = $false
$label = New-Object System.Windows.Forms.Label
$label.Dock = 'Fill'
$label.Padding = New-Object System.Windows.Forms.Padding(14)
$label.Font = New-Object System.Drawing.Font('Microsoft YaHei',12)
$form.Controls.Add($label)
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 500
$timer.Add_Tick({
 if (!(Test-Path -LiteralPath $StatePath)) { $form.Close(); return }
 try {
  $state = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($state.status -eq 'uncertain') {
   $message = "自动处理超时，软件状态尚未确认。`r`n请暂勿操作或强制关闭，等待检查。"
   $form.ControlBox = $true
  } else { $message = "正在自动处理 $($state.application)`r`n请暂勿操作以上软件，完成后提示自动关闭。`r`n可继续使用 InDesign 等其他软件。" }
  if ($label.Text -ne $message) { $label.Text = $message }
 } catch {}
})

$form.Add_Shown({
 [JournalNoticeWindow]::ShowWindow($form.Handle, 4) | Out-Null
 [JournalNoticeWindow]::SetWindowPos($form.Handle, [IntPtr](-1), 0, 0, 0, 0, 0x0013) | Out-Null
 [System.IO.File]::WriteAllText($StatePath + '.shown', 'visible')
})
$timer.Start()
[System.Windows.Forms.Application]::Run($form)
$timer.Dispose()
$form.Dispose()
