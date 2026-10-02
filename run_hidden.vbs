Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
' Runs start_server.bat from the same folder as this script (no hard-coded path)
folder = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.Run Chr(34) & folder & "\start_server.bat" & Chr(34), 0
Set WshShell = Nothing
