@echo off
chcp 65001 >nul
cd /d "%~dp0"
python wren.py gui
if errorlevel 1 pause
