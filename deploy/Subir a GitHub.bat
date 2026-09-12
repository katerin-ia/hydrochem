@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Subir HydroChem a GitHub
cd /d "%~dp0.."

echo.
echo   ============================================================
echo    SUBIR HYDROCHEM A GITHUB
echo   ============================================================
echo.
echo   El proyecto ya esta preparado: tiene su repositorio local y
echo   su primer commit hecho. Solo falta enviarlo a GitHub.
echo.
echo   ANTES de seguir, crea el repositorio vacio:
echo.
echo     1. Entra en  https://github.com/new
echo     2. Repository name:  hydrochem
echo     3. Marca Private si no quieres que se vea
echo     4. NO marques "Add a README file" ^(debe quedar vacio^)
echo     5. Create repository
echo     6. Copia la direccion que te muestra, del tipo:
echo        https://github.com/TU-USUARIO/hydrochem.git
echo.
echo   ------------------------------------------------------------
echo.

set /p REPO="  Pega aqui esa direccion y pulsa Enter: "

if "%REPO%"=="" (
  echo.
  echo   No has escrito nada. Vuelve a ejecutar el archivo cuando
  echo   tengas la direccion.
  echo.
  pause
  exit /b 1
)

echo.
set /p NOMBRE="  Tu nombre (para firmar los commits): "
set /p CORREO="  Tu correo de GitHub: "

if not "%NOMBRE%"=="" git config user.name "%NOMBRE%"
if not "%CORREO%"=="" git config user.email "%CORREO%"

echo.
echo   Conectando con GitHub...
echo.

git remote remove origin >nul 2>&1
git remote add origin "%REPO%"
if errorlevel 1 (
  echo   No se pudo usar esa direccion. Comprueba que la copiaste entera.
  echo.
  pause
  exit /b 1
)

echo   Enviando el proyecto. Se abrira una ventana para que inicies
echo   sesion en GitHub: esa contrasena la escribes tu, no queda
echo   guardada en ningun archivo del proyecto.
echo.

git push -u origin main
if errorlevel 1 (
  echo.
  echo   ------------------------------------------------------------
  echo    Algo fallo al enviar. Lo mas habitual:
  echo.
  echo    - El repositorio de GitHub no esta vacio ^(tiene README^).
  echo      Borralo y crealo de nuevo sin marcar ninguna casilla.
  echo    - La direccion esta incompleta o mal copiada.
  echo    - Cancelaste el inicio de sesion.
  echo   ------------------------------------------------------------
  echo.
  pause
  exit /b 1
)

echo.
echo   ============================================================
echo    LISTO. El proyecto ya esta en GitHub.
echo   ============================================================
echo.
echo   Ahora, para ponerlo en internet:
echo.
echo     1. Entra en  https://render.com
echo     2. Get Started  ^-^>  Sign in with GitHub
echo     3. New  ^-^>  Blueprint
echo     4. Elige el repositorio  hydrochem
echo     5. Apply
echo.
echo   Render lee el archivo render.yaml y lo configura solo.
echo   La primera construccion tarda entre 4 y 8 minutos.
echo.
echo   Los detalles estan en  deploy\Render.md
echo.
pause
