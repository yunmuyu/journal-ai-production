Add-Type @'
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public class JFWNativeWindow {
 public long handle; public string type; public string text;
 public JFWNativeWindow(IntPtr h) { handle=h.ToInt64(); var s=new StringBuilder(2048); GetWindowText(h,s,s.Capacity); text=s.ToString(); s.Clear(); GetClassName(h,s,128); type=s.ToString(); }
 public delegate bool Callback(IntPtr h,IntPtr p);
 [DllImport("user32.dll")] public static extern bool EnumWindows(Callback c,IntPtr p);
 [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h,Callback c,IntPtr p);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint p);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h,StringBuilder s,int n);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h,StringBuilder s,int n);
 public static JFWNativeWindow[] Dialogs(uint processId) {
  var list=new List<JFWNativeWindow>();
  EnumWindows(delegate(IntPtr h,IntPtr p){uint owner;GetWindowThreadProcessId(h,out owner);if(owner==processId&&IsWindowVisible(h)){var w=new JFWNativeWindow(h);if(w.type=="#32770")list.Add(w);}return true;},IntPtr.Zero);
  return list.ToArray();
 }
 public static JFWNativeWindow[] Children(long handle) {
  var list=new List<JFWNativeWindow>();EnumChildWindows(new IntPtr(handle),delegate(IntPtr h,IntPtr p){list.Add(new JFWNativeWindow(h));return true;},IntPtr.Zero);return list.ToArray();
 }
}
'@
function Get-IllustratorDialogs([int]$ProcessId) {
 foreach($dialog in [JFWNativeWindow]::Dialogs($ProcessId)) {
  [pscustomobject]@{handle=$dialog.handle;title=$dialog.text;controls=@([JFWNativeWindow]::Children($dialog.handle))}
 }
}
