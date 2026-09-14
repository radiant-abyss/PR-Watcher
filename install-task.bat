@echo off
rem ============================================================
rem  PR Watcher autostart installer (run once as Administrator)
rem  Install  : right-click this file -> Run as administrator
rem  Uninstall: schtasks /delete /tn "PRWatcher" /f
rem  Portable : uses its own folder (%~dp0), so moving the folder is fine.
rem ============================================================
echo Registering logon autostart task...
schtasks /create /tn "PRWatcher" /tr "wscript.exe \"%~dp0start-hidden.vbs\"" /sc onlogon /rl limited /f
if %errorlevel%==0 (
  echo.
  echo [OK] Registered. PR Watcher will start automatically at next logon.
  echo      Test now: run PRWatcher.exe or python pr_watcher.py --once
) else (
  echo [FAIL] Please re-run this file as Administrator.
)
pause
