@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "APP_VERSION=1.3.5"
set "INSTALL_ROOT=%LOCALAPPDATA%\Programs\PeperTranslator"
set "RUNTIME_ROOT=%INSTALL_ROOT%\runtime"
set "BUILD_ROOT=%TEMP%\PeperTranslatorNativeBuild_%RANDOM%_%RANDOM%"
set "PACK_OUT=%BUILD_ROOT%\packaged"
set "TOOLS=%BUILD_ROOT%\tools"
set "PYSEL="

 echo === PeperTranslator Windows App v%APP_VERSION% ===
 echo Install location: %INSTALL_ROOT%
 echo Library location: %LOCALAPPDATA%\PeperTranslator
 echo.

where node.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: Node.js was not found in PATH.
  goto :fail
)
where npm.cmd >nul 2>&1
if errorlevel 1 (
  echo ERROR: npm was not found in PATH.
  goto :fail
)

py -3.13 -c "import sys" >nul 2>&1 && set "PYSEL=-3.13"
if not defined PYSEL py -3.12 -c "import sys" >nul 2>&1 && set "PYSEL=-3.12"
if not defined PYSEL py -3.11 -c "import sys" >nul 2>&1 && set "PYSEL=-3.11"
if not defined PYSEL py -3.10 -c "import sys" >nul 2>&1 && set "PYSEL=-3.10"
if not defined PYSEL (
  echo ERROR: Python 3.10-3.13 with py.exe is required.
  goto :fail
)

 echo [1/8] Closing an older native PeperTranslator...
taskkill /IM PeperTranslator.exe /T /F >nul 2>&1

 echo [2/8] Preparing application directory...
if exist "%INSTALL_ROOT%" rmdir /s /q "%INSTALL_ROOT%"
mkdir "%RUNTIME_ROOT%" >nul 2>&1
if errorlevel 1 goto :fail
robocopy "%CD%\backend" "%RUNTIME_ROOT%\backend" /E /NFL /NDL /NJH /NJS /NP /XD __pycache__ tests >nul
if errorlevel 8 goto :fail
robocopy "%CD%\frontend" "%RUNTIME_ROOT%\frontend" /E /NFL /NDL /NJH /NJS /NP /XD node_modules .next >nul
if errorlevel 8 goto :fail
copy /y "%CD%\setup_layout_translation.cmd" "%RUNTIME_ROOT%\setup_layout_translation.cmd" >nul
copy /y "%CD%\setup_layout_translation.ps1" "%RUNTIME_ROOT%\setup_layout_translation.ps1" >nul

 echo [3/8] Creating Python backend runtime...
py %PYSEL% -m venv "%RUNTIME_ROOT%\backend_env"
if errorlevel 1 goto :fail
set "BACKENDPY=%RUNTIME_ROOT%\backend_env\Scripts\python.exe"
"%BACKENDPY%" -m pip install --upgrade pip
if errorlevel 1 goto :fail
"%BACKENDPY%" -m pip install -r "%RUNTIME_ROOT%\backend\requirements.txt"
if errorlevel 1 goto :fail

 echo [4/8] Building standalone frontend...
pushd "%RUNTIME_ROOT%\frontend"
call npm ci
if errorlevel 1 goto :frontend_fail
call npm run build
if errorlevel 1 goto :frontend_fail
popd
mkdir "%RUNTIME_ROOT%\frontend_server" >nul 2>&1
robocopy "%RUNTIME_ROOT%\frontend\.next\standalone" "%RUNTIME_ROOT%\frontend_server" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail
mkdir "%RUNTIME_ROOT%\frontend_server\.next\static" >nul 2>&1
robocopy "%RUNTIME_ROOT%\frontend\.next\static" "%RUNTIME_ROOT%\frontend_server\.next\static" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail
if exist "%RUNTIME_ROOT%\frontend\public" (
  robocopy "%RUNTIME_ROOT%\frontend\public" "%RUNTIME_ROOT%\frontend_server\public" /E /NFL /NDL /NJH /NJS /NP >nul
  if errorlevel 8 goto :fail
)
rmdir /s /q "%RUNTIME_ROOT%\frontend"
goto :frontend_done

:frontend_fail
popd
goto :fail

:frontend_done
 echo [5/8] Preparing PDF layout translation runtime...
pushd "%RUNTIME_ROOT%"
call setup_layout_translation.cmd
if errorlevel 1 goto :pdf_fail
popd
goto :pdf_done

:pdf_fail
popd
goto :fail

:pdf_done
 echo [6/8] Downloading native Windows shell build tools...
mkdir "%BUILD_ROOT%" >nul 2>&1
mkdir "%TOOLS%" >nul 2>&1
pushd "%TOOLS%"
call npm init -y >nul 2>&1
call npm install --no-fund --no-audit --save-dev electron@latest @electron/packager@latest
if errorlevel 1 goto :tools_fail

rem Resolve Electron from its package metadata. electron\dist\version is not
rem guaranteed to exist after npm install, which caused v1.3.0 to pass an empty
rem --electron-version to @electron/packager.
node -e "process.stdout.write(require('./node_modules/electron/package.json').version)" > "%TOOLS%\electron-version.txt"
if errorlevel 1 goto :tools_fail
set /p ELECTRON_VERSION=<"%TOOLS%\electron-version.txt"
if not defined ELECTRON_VERSION (
  echo ERROR: Installed Electron version could not be resolved.
  goto :tools_fail
)
echo     Electron version: %ELECTRON_VERSION%
if not exist "%TOOLS%\node_modules\.bin\electron-packager.cmd" (
  echo ERROR: electron-packager.cmd was not installed.
  goto :tools_fail
)
popd
goto :tools_done

:tools_fail
popd
goto :fail

:tools_done
 echo [7/8] Building PeperTranslator.exe...
call "%TOOLS%\node_modules\.bin\electron-packager.cmd" "%CD%\native_shell" PeperTranslator --platform=win32 --arch=x64 --electron-version=%ELECTRON_VERSION% --icon="%CD%\native_shell\assets\PeperTranslator.ico" --out="%PACK_OUT%" --overwrite --prune=true --asar
if errorlevel 1 goto :fail
set "PACKAGED_DIR=%PACK_OUT%\PeperTranslator-win32-x64"
if not exist "%PACKAGED_DIR%\PeperTranslator.exe" (
  echo ERROR: Native executable was not produced.
  goto :fail
)
robocopy "%PACKAGED_DIR%" "%INSTALL_ROOT%" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail
copy /y "%CD%\UNINSTALL_PEPERTRANSLATOR.vbs" "%INSTALL_ROOT%\UNINSTALL_PEPERTRANSLATOR.vbs" >nul

 echo [8/8] Registering Windows app, Start Menu, and uninstaller...
cscript.exe //nologo "%CD%\scripts\create_native_shortcuts.vbs" "%INSTALL_ROOT%"
if errorlevel 1 goto :fail
rmdir /s /q "%BUILD_ROOT%" >nul 2>&1

echo.
echo =====================================================
echo PeperTranslator Windows App installed successfully.
echo =====================================================
echo Start Menu : PeperTranslator
echo Executable : %INSTALL_ROOT%\PeperTranslator.exe
echo Library    : %LOCALAPPDATA%\PeperTranslator
echo Uninstall  : Windows Settings ^> Apps ^> Installed apps
 echo.
start "" "%INSTALL_ROOT%\PeperTranslator.exe"
pause
exit /b 0

:fail
 echo.
echo INSTALL FAILED.
echo The existing Library under %%LOCALAPPDATA%%\PeperTranslator was not deleted.
if exist "%BUILD_ROOT%" rmdir /s /q "%BUILD_ROOT%" >nul 2>&1
pause
exit /b 1
