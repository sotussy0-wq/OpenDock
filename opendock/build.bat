@echo off
REM Builds OpenDock.exe and the installer. Needs Python 3.9+ and Inno Setup 6 (https://jrsoftware.org/isdl.php)
python -m pip install -r requirements.txt pyinstaller || exit /b 1
python -m PyInstaller --noconsole --onefile --name OpenDock --icon icon.ico --collect-data tzdata opendock.py || exit /b 1
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
%ISCC% installer.iss || exit /b 1
echo.
echo Done: installer_out\OpenDock-Setup.exe
