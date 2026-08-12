Option Explicit

Dim shell
Dim fso
Dim repoRoot
Dim command
Dim exitCode

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

repoRoot = fso.GetParentFolderName(WScript.ScriptFullName)
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & repoRoot & "\run-iprus-sync-scheduled.ps1"""

exitCode = shell.Run(command, 0, True)
WScript.Quit exitCode
