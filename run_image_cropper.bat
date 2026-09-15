@echo off
cd /d "%~dp0"
if exist ".venv-build\Scripts\python.exe" (
  ".venv-build\Scripts\python.exe" image_cropper.py
) else (
  python image_cropper.py
)
pause
