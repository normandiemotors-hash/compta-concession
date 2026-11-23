@echo off
cd /d "%~dp0"
echo Lancement de la comptabilite de la concession...
python app.py
if errorlevel 1 py -3 app.py
pause
