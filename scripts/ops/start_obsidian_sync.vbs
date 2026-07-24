Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\TobyC\hermes_related\Cornell_KB"
WshShell.Run """C:\Users\TobyC\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"" """C:\Users\TobyC\hermes_related\Cornell_KB\scripts\ops\obsidian_sync.py"" --watch --interval 3", 0, False
Set WshShell = Nothing
