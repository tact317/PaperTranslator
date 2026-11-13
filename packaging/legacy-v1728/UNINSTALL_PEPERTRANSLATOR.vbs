Option Explicit
Dim shell, fso, root, desktopLink, startLink, cleanup
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)

On Error Resume Next
shell.Run "taskkill.exe /IM PeperTranslator.exe /T /F", 0, True
desktopLink = fso.BuildPath(shell.SpecialFolders("Desktop"), "PeperTranslator.lnk")
startLink = shell.ExpandEnvironmentStrings("%APPDATA%") & "\Microsoft\Windows\Start Menu\Programs\PeperTranslator.lnk"
If fso.FileExists(desktopLink) Then fso.DeleteFile desktopLink, True
If fso.FileExists(startLink) Then fso.DeleteFile startLink, True
shell.RegDelete "HKCU\Software\Microsoft\Windows\CurrentVersion\App Paths\PeperTranslator.exe\"
shell.RegDelete "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\PeperTranslator\"
On Error GoTo 0

cleanup = "cmd.exe /d /c timeout /t 2 /nobreak >nul & rmdir /s /q """ & root & """"
shell.Run cleanup, 0, False
MsgBox "PeperTranslator was uninstalled. Library data in %LOCALAPPDATA%\PeperTranslator was preserved.", 64, "PeperTranslator"
