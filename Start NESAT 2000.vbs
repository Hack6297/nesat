Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
command = "cmd /c cd /d """ & folder & """ && start """" pythonw.exe launch.pyw"
shell.Run command, 0, False
