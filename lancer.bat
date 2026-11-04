@echo off
REM Démarre Chess Coach sur http://127.0.0.1:8000
cd /d "%~dp0"
python manage.py migrate --noinput >nul
python manage.py runserver 127.0.0.1:8000
