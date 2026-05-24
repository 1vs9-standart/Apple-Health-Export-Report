@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo === Отчёт Apple Health ===
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo Python не найден. Установите с python.org и отметьте «Add Python to PATH».
    pause
    exit /b 1
)

echo Установка библиотек...
python -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo Ошибка установки. Попробуйте: python -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo.
echo Сборка отчёта...
python health_insights.py
if errorlevel 1 (
    echo.
    echo Проверьте, что export.xml лежит в папке data\
    pause
    exit /b 1
)

echo.
echo Готово! Открываю output\health_report.html ...
start "" "output\health_report.html"
pause
