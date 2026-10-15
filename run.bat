@echo off
cd /d "%~dp0"
REM Keep this batch file ASCII-only for cmd.exe legacy code pages.
REM PowerShell stays in this console and owns both child servers.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-web.ps1" %*

