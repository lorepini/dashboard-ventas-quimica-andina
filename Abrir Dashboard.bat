@echo off
REM ===========================================================
REM  Dashboard de Ventas - AAA Quimica
REM  Doble clic en este archivo para abrir el dashboard.
REM  No hace falta saber nada de programacion.
REM ===========================================================

title Dashboard de Ventas
cd /d "%~dp0"

echo.
echo  ============================================
echo    DASHBOARD DE VENTAS - AAA QUIMICA
echo  ============================================
echo.

if not exist "app.py" (
    echo  [!] Falta el archivo app.py en esta carpeta:
    echo      %cd%
    echo.
    echo  El .bat tiene que quedar dentro de la carpeta "dashboard",
    echo  junto con app.py y las carpetas core y ui.
    echo.
    pause
    exit /b 1
)

REM --- 1) Buscar Python instalado en Windows ------------------
REM Ojo: Windows trae un "python.exe" falso que solo abre la
REM tienda de Microsoft. Por eso no basta con que exista: se
REM comprueba que de verdad responda la version.
set "PYTHON="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PYTHON=py -3"

if not defined PYTHON (
    python --version >nul 2>&1
    if not errorlevel 1 set "PYTHON=python"
)

if defined PYTHON goto :usar_windows

REM --- 2) Si no hay Python en Windows, usar el de WSL ---------
REM Esta computadora tiene WSL (Linux dentro de Windows) con todo
REM ya instalado, asi que no hay que instalar nada.
wsl.exe -e true >nul 2>&1
if not errorlevel 1 goto :usar_wsl

echo  [!] No se encontro Python ni WSL en esta computadora.
echo.
echo  Para poder usar el dashboard hay que instalar Python
echo  una sola vez:
echo.
echo    1. Entrar a  https://www.python.org/downloads/
echo    2. Descargar el boton grande amarillo "Download Python".
echo    3. Al instalarlo, MARCAR la casilla
echo       "Add python.exe to PATH" antes de dar Install.
echo    4. Terminada la instalacion, volver a dar doble clic aqui.
echo.
pause
exit /b 1


:usar_windows
echo  Usando el Python instalado en Windows.
echo.
%PYTHON% -c "import streamlit, pandas, plotly, xlrd, openpyxl" >nul 2>&1
if errorlevel 1 (
    echo  Primera vez: instalando lo necesario.
    echo  Esto puede tardar unos minutos. No cierres esta ventana.
    echo.
    %PYTHON% -m pip install --upgrade pip >nul 2>&1
    %PYTHON% -m pip install -r requirements.txt
    if errorlevel 1 goto :error_instalacion
    echo.
    echo  Listo, ya quedo instalado. Las proximas veces abre directo.
    echo.
)
call :aviso_ventana
%PYTHON% -m streamlit run app.py --server.headless false --server.port 8501
goto :fin


:usar_wsl
echo  Usando el Python de WSL (Linux dentro de Windows).
echo.
wsl.exe --cd "%~dp0" -e bash -lc "python3 -c 'import streamlit, pandas, plotly, xlrd, openpyxl' >/dev/null 2>&1" >nul 2>&1
if errorlevel 1 (
    echo  Primera vez: instalando lo necesario.
    echo  Esto puede tardar unos minutos. No cierres esta ventana.
    echo.
    wsl.exe --cd "%~dp0" -e bash -lc "python3 -m pip install --user -r requirements.txt"
    if errorlevel 1 goto :error_instalacion
    echo.
    echo  Listo, ya quedo instalado. Las proximas veces abre directo.
    echo.
)
call :aviso_ventana
REM WSL no puede abrir el navegador de Windows, asi que lo abrimos
REM aparte unos segundos despues, cuando el servidor ya responde.
start "" /b cmd /c "timeout /t 8 /nobreak >nul & start "" http://localhost:8501"
wsl.exe --cd "%~dp0" -e bash -lc "python3 -m streamlit run app.py --server.headless true --server.port 8501"
goto :fin


:aviso_ventana
echo  Abriendo el dashboard en el navegador...
echo.
echo  Si no se abre solo, entra a esta direccion:
echo.
echo        http://localhost:8501
echo.
echo  IMPORTANTE: no cierres esta ventana negra mientras
echo  uses el dashboard. Para terminar, cierrala.
echo.
exit /b 0


:error_instalacion
echo.
echo  [!] No se pudieron instalar las librerias.
echo.
echo  Suele ser por falta de internet o porque la red de la
echo  oficina bloquea la descarga. Revisa la conexion y
echo  vuelve a intentar. Si sigue igual, avisa a sistemas.
echo.
pause
exit /b 1


:fin
if errorlevel 1 (
    echo.
    echo  [!] El dashboard se cerro con un error.
    echo  Toma una foto de esta ventana y enviala a sistemas.
    echo.
    pause
    exit /b 1
)
echo.
echo  Dashboard cerrado. Ya puedes cerrar esta ventana.
echo.
pause
