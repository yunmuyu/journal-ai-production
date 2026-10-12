$ErrorActionPreference = 'Stop'
$TargetPath = $env:JFW_OPEN_FILE
$Mode = if ($env:JFW_OPEN_MODE -eq 'locate') { 'locate' } else { 'open' }

if ([string]::IsNullOrWhiteSpace($TargetPath) -or -not (Test-Path -LiteralPath $TargetPath)) {
    throw 'Registered file is unavailable'
}

$TargetPath = (Resolve-Path -LiteralPath $TargetPath).Path
$TargetIsDirectory = Test-Path -LiteralPath $TargetPath -PathType Container
if ($Mode -eq 'open' -and $TargetIsDirectory) { throw 'Registered application file is unavailable' }
$TargetName = [System.IO.Path]::GetFileName($TargetPath)
$TargetStem = [System.IO.Path]::GetFileNameWithoutExtension($TargetPath)
$OpenedProcessName = $null
$KnownApplicationFamilies = @{
    '.doc' = @('WINWORD')
    '.docx' = @('WINWORD')
    '.ai' = @('Illustrator')
    '.pdf' = @('Acrobat', 'AcroRd32', 'msedge', 'chrome', 'firefox', 'FoxitPDFReader', 'SumatraPDF', 'PDFXEdit')
}
$AllowedProcessNames = @()
if ($Mode -eq 'open') {
    $OpenedProcess = Start-Process -FilePath $TargetPath -PassThru -ErrorAction Stop
    try { $OpenedProcessName = (Get-Process -Id $OpenedProcess.Id -ErrorAction Stop).ProcessName } catch { }
    $AllowedProcessNames = @($KnownApplicationFamilies[[System.IO.Path]::GetExtension($TargetPath).ToLowerInvariant()])
    if ($OpenedProcessName) { $AllowedProcessNames += $OpenedProcessName }
} else {
    if ($TargetIsDirectory) {
        Start-Process -FilePath 'explorer.exe' -ArgumentList @('"' + $TargetPath + '"') -ErrorAction Stop | Out-Null
        $TargetDirectory = $TargetPath
    } else {
        Start-Process -FilePath 'explorer.exe' -ArgumentList @('/select,"' + $TargetPath + '"') -ErrorAction Stop | Out-Null
        $TargetDirectory = Split-Path -LiteralPath $TargetPath -Parent
    }
    $TargetDirectory = [System.IO.Path]::GetFullPath($TargetDirectory).TrimEnd('\')
}

if (-not ('JfwWindowActivation' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Text;
using System.Runtime.InteropServices;
public sealed class JfwWindowInfo {
    public IntPtr Handle { get; set; }
    public uint ProcessId { get; set; }
    public string Title { get; set; }
}
public static class JfwWindowActivation {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    public static uint GetProcessIdForWindow(IntPtr hWnd) {
        uint processId;
        GetWindowThreadProcessId(hWnd, out processId);
        return processId;
    }
    public static JfwWindowInfo[] GetVisibleWindows() {
        var windows = new List<JfwWindowInfo>();
        EnumWindows((hWnd, lParam) => {
            if (IsWindowVisible(hWnd)) {
                var title = new StringBuilder(1024);
                GetWindowText(hWnd, title, title.Capacity);
                uint processId;
                GetWindowThreadProcessId(hWnd, out processId);
                if (title.Length > 0) windows.Add(new JfwWindowInfo { Handle = hWnd, ProcessId = processId, Title = title.ToString() });
            }
            return true;
        }, IntPtr.Zero);
        return windows.ToArray();
    }
    [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
'@
}
$Shell = New-Object -ComObject WScript.Shell
$Explorer = if ($Mode -eq 'locate') { New-Object -ComObject Shell.Application }

$Deadline = [DateTime]::UtcNow.AddSeconds(10)
$Activated = $false
do {
    if ($Mode -eq 'open') {
        $Windows = @([JfwWindowActivation]::GetVisibleWindows() | ForEach-Object {
            $windowInfo = $_
            $process = Get-Process -Id $windowInfo.ProcessId -ErrorAction SilentlyContinue
            if ($process -and $AllowedProcessNames -contains $process.ProcessName) {
                $hasDocumentName = [System.Text.RegularExpressions.Regex]::IsMatch(
                    $windowInfo.Title,
                    '(?<![\p{L}\p{N}_])' + [System.Text.RegularExpressions.Regex]::Escape($TargetStem) + '(?![\p{L}\p{N}_])',
                    [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
                )
                if ($hasDocumentName) {
                    [pscustomobject]@{ Id = $process.Id; Handle = $windowInfo.Handle; Title = $windowInfo.Title }
                }
            }
        })
    } else {
        $Windows = @($Explorer.Windows() | ForEach-Object {
            try {
                $path = $_.Document.Folder.Self.Path
                if (-not $path -and $_.LocationURL -match '^file:') { $path = ([Uri]$_.LocationURL).LocalPath }
                if ($path -and [System.IO.Path]::GetFullPath($path).TrimEnd('\').Equals($TargetDirectory, [StringComparison]::OrdinalIgnoreCase)) {
                    [pscustomobject]@{ Id = 0; Handle = [IntPtr]$_.HWND; Title = $_.LocationName }
                }
            } catch { }
        })
    }

    if (($Mode -eq 'open' -and $Windows.Count -eq 1) -or ($Mode -eq 'locate' -and $Windows.Count -gt 0)) {
        $Window = $Windows[0]
        $WindowProcessId = if ($Mode -eq 'locate') { [JfwWindowActivation]::GetProcessIdForWindow($Window.Handle) } else { $Window.Id }
        [void]$Shell.AppActivate([int]$WindowProcessId)
        [void][JfwWindowActivation]::ShowWindowAsync($Window.Handle, 9)
        [void][JfwWindowActivation]::SetForegroundWindow($Window.Handle)
        Start-Sleep -Milliseconds 250
        if ([JfwWindowActivation]::GetForegroundWindow() -eq $Window.Handle) {
            $Activated = $true
            [pscustomobject]@{ foreground = $true; windowTitle = $Window.Title; mode = $Mode } | ConvertTo-Json -Compress | Write-Output
            break
        }
    }
    Start-Sleep -Milliseconds 250
} while ([DateTime]::UtcNow -lt $Deadline)

if (-not $Activated) {
    if ($Mode -eq 'open') { throw "Windows打开请求已发送，但无法确认目标文档窗口已在前台显示：$TargetName" }
    throw "Explorer已收到定位请求，但无法确认目标目录窗口已在前台显示：$TargetDirectory"
}
