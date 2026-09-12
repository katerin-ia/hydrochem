@echo off
chcp 65001 >nul
title HydroChem
cd /d "%~dp0"
echo.
echo   Arrancando HydroChem...
echo   Se abrira solo en tu navegador. Para cerrar, cierra esta ventana.
echo.
python "app\main.py" 8000
if errorlevel 1 (
  echo.
  echo   No se pudo arrancar. Comprueba que Python este instalado.
  pause
)
