@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "DEFAULT_MODEL_PATH=H:/WorkSpace/GMPmaster/ctl/suite/mcs_pmsm_nt/project/simulate/MCS_STD_PMSM_MODEL_2022b.slx"
set "MODEL_PATH=%DEFAULT_MODEL_PATH%"

if not "%~1"=="" (
    set "MODEL_PATH=%~1"
    shift
) else (
    if not "%GMP_LOCAL_MODEL_PATH%"=="" (
        set "MODEL_PATH=%GMP_LOCAL_MODEL_PATH%"
    )
)

if "%MODEL_PATH%"=="" set "MODEL_PATH=%DEFAULT_MODEL_PATH%"

python "%SCRIPT_DIR%run_local_job.py" --model-path "%MODEL_PATH%" --scope-map "%SCRIPT_DIR%scope_channel_map.example.json" --raw-output "%SCRIPT_DIR%raw.json" --processed-output "%SCRIPT_DIR%processed.json"

endlocal
