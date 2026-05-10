@echo off
setlocal EnableExtensions

rem ============================================================
rem Portable Simulink local run script.
rem Expected location:
rem   <repo_root>\tools\agent\agent_silhelper\run_local_quick.bat
rem ============================================================

set "SCRIPT_DIR=%~dp0"

for %%D in ("%SCRIPT_DIR%..\..\..") do set "REPO_ROOT=%%~fD"

set "DEFAULT_MODEL_PATH=%REPO_ROOT%\ctl\suite\mcs_pmsm_nt\project\simulate\MCS_STD_PMSM_MODEL_2022b.slx"
set "MODEL_PATH=%DEFAULT_MODEL_PATH%"

if not "%~1"=="" (
    set "MODEL_PATH=%~1"
    shift
) else (
    if not "%GMP_LOCAL_MODEL_PATH%"=="" (
        set "MODEL_PATH=%GMP_LOCAL_MODEL_PATH%"
    )
)

if not exist "%MODEL_PATH%" (
    echo [ERROR] Simulink model not found:
    echo "%MODEL_PATH%"
    exit /b 20
)

python "%SCRIPT_DIR%run_local_job.py" --model-path "%MODEL_PATH%" --scope-map "%SCRIPT_DIR%scope_channel_map.example.json"
exit /b %ERRORLEVEL%
