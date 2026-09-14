@echo off
rem Graceful stop: drop the stop marker; the watcher exits within 60 seconds.
echo stop > "%~dp0watcher.stop"
echo Requested stop. The watcher exits within a minute (see watcher.log).
pause
