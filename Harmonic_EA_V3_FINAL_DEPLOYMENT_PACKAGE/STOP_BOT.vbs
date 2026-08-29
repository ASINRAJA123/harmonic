Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "taskkill /F /IM pythonw.exe /T", 0, True
WScript.Quit
