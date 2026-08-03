Option Explicit

Dim fso, WshShell, projectRoot, pythonExe, scriptPath
Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

' Resolve the project from this launcher so the repository can live anywhere.
projectRoot = fso.GetParentFolderName( _
    fso.GetParentFolderName( _
        fso.GetParentFolderName(WScript.ScriptFullName)))
scriptPath = fso.BuildPath(projectRoot, "scripts\ops\obsidian_sync.py")

' Set CORNELL_KB_PYTHON to a virtual-environment interpreter when needed.
pythonExe = WshShell.ExpandEnvironmentStrings("%CORNELL_KB_PYTHON%")
If pythonExe = "%CORNELL_KB_PYTHON%" Then pythonExe = "python"

WshShell.CurrentDirectory = projectRoot
WshShell.Run """" & pythonExe & """ """ & scriptPath & """ --watch --interval 3", 0, False
Set WshShell = Nothing
