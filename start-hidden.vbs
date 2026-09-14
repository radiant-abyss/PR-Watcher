' PR Watcher hidden autostart launcher (no console window).
' Portable: it resolves its own folder, so the whole folder can be moved anywhere.
Set fso = CreateObject("Scripting.FileSystemObject")
Set ws  = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
exePath = folder & "\PRWatcher.exe"
script  = folder & "\pr_watcher.py"
If fso.FileExists(exePath) Then
  ws.Run """" & exePath & """", 0, False
ElseIf fso.FileExists(script) Then
  ws.Run "pythonw.exe """ & script & """", 0, False
Else
  MsgBox "PR Watcher files not found in:" & vbCrLf & folder, 48, "PR Watcher"
End If
