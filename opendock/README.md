# OpenDock
Free widget dock for Windows 10/11 (MIT). Original project, not affiliated with any commercial product.

## Build the installer
**Option A – on your Windows PC:** install Python 3.9+ and Inno Setup 6, then double-click `build.bat`.
Result: `installer_out\OpenDock-Setup.exe`.

**Option B – no tools needed:** push this folder to a GitHub repo, open Actions -> "Build installer" -> Run workflow,
then download the `OpenDock-Setup` artifact.

## Run without installing
`pip install -r requirements.txt` then `python opendock.py`
