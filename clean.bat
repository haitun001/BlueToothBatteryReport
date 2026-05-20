@echo off
setlocal

if exist ".sconsign.dblite" del /f /q ".sconsign.dblite"
if exist ".venv" rmdir /s /q ".venv"
if exist ".ruff_cache" rmdir /s /q ".ruff_cache"

if exist "addon\manifest.ini" del /f /q "addon\manifest.ini"
if exist "addon\locale\zh_CN\manifest.ini" del /f /q "addon\locale\zh_CN\manifest.ini"
if exist "addon\locale\zh_CN\LC_MESSAGES\nvda.mo" del /f /q "addon\locale\zh_CN\LC_MESSAGES\nvda.mo"
if exist "BlueToothBatteryReport.pot" del /f /q "BlueToothBatteryReport.pot"

if exist "addon\doc\en" rmdir /s /q "addon\doc\en"
if exist "addon\doc\style.css" del /f /q "addon\doc\style.css"
if exist "addon\doc\zh_CN\readme.html" del /f /q "addon\doc\zh_CN\readme.html"

for /d %%D in (*.egg-info) do (
	if exist "%%D" rmdir /s /q "%%D"
)

for /d /r %%D in (__pycache__) do (
	if exist "%%D" rmdir /s /q "%%D"
)

echo Clean complete.
exit /b 0
