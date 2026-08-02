Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

batPath = scriptDir & "\run_playlist_app.bat"
WshShell.Run "cmd /c """ & batPath & """", 0, False
