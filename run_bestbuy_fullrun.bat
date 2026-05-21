@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "CATEGORY=%~1"
if "%CATEGORY%"=="" set "CATEGORY=TV"
set "CATEGORY=%CATEGORY:"=%"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "RUN_DATE=%%i"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "RUN_TS=%%i"

set "BESTBUY_CATEGORY=%CATEGORY%"
set "BESTBUY_RUN_DATE=%RUN_DATE%"
set "BESTBUY_BATCH_ID=b_%RUN_TS%"
set "BESTBUY_FETCH_MODE=zenrows"
set "BESTBUY_GRAPHQL_FETCH_MODE=zenrows"
set "BESTBUY_DETAIL_FETCH_MODE=zenrows"
set "BESTBUY_DETAIL_FETCH_COMPARE=0"
if /I "%CATEGORY%"=="TV" set "BESTBUY_OUTPUT_TABLE_TV=tv_retail_com"
set "PYTHONUNBUFFERED=1"

set "LOG_DIR=%~dp0bestbuy\data\%CATEGORY%\%RUN_DATE%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "LOG_FILE=%LOG_DIR%\fullrun_%RUN_TS%.log"

echo ==================================================
echo BestBuy %CATEGORY% full run started
echo batch_id=%BESTBUY_BATCH_ID%
echo output_table=%BESTBUY_OUTPUT_TABLE_TV%
echo log=%LOG_FILE%
echo ==================================================
echo BestBuy %CATEGORY% full run started > "%LOG_FILE%"
echo batch_id=%BESTBUY_BATCH_ID% >> "%LOG_FILE%"
echo output_table=%BESTBUY_OUTPUT_TABLE_TV% >> "%LOG_FILE%"

call :run_step 01 12 "main_list" 01
if errorlevel 1 goto :fail
call :run_step 02 12 "main_targets" 02
if errorlevel 1 goto :fail
call :run_step 03 12 "bsr_list" 03
if errorlevel 1 goto :fail
call :run_step 04 12 "bsr_rank" 04
if errorlevel 1 goto :fail
call :run_step 05 12 "promotion_deals" 05
if errorlevel 1 goto :fail
call :run_step 06 12 "trending_deals" 06
if errorlevel 1 goto :fail
call :run_step 07 12 "final_targets" 07
if errorlevel 1 goto :fail
call :run_step 08 12 "detail_html" 08
if errorlevel 1 goto :fail
call :run_step 09 12 "review20" 09
if errorlevel 1 goto :fail
call :run_step 10 12 "status_check" 10
if errorlevel 1 goto :fail

call :run_step 11 12 "db_prepare" 13
if errorlevel 1 goto :fail
call :run_step 12 12 "db_load" 14
if errorlevel 1 goto :fail

echo ==================================================
echo BestBuy %CATEGORY% full run completed
echo log=%LOG_FILE%
echo ==================================================
echo BestBuy %CATEGORY% full run completed >> "%LOG_FILE%"
exit /b 0

:run_step
set "CUR=%~1"
set "TOTAL=%~2"
set "NAME=%~3"
set "STEP=%~4"
echo.
echo [%CUR%/%TOTAL%] %NAME% started
echo [%CUR%/%TOTAL%] %NAME% started >> "%LOG_FILE%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "& python -m bestbuy.bestbuy_orchestrator --category '%CATEGORY%' '%STEP%' 2>&1 | Tee-Object -FilePath '%LOG_FILE%' -Append"
if errorlevel 1 (
  echo [%CUR%/%TOTAL%] %NAME% failed
  echo [%CUR%/%TOTAL%] %NAME% failed >> "%LOG_FILE%"
  exit /b 1
)
echo [%CUR%/%TOTAL%] %NAME% completed
echo [%CUR%/%TOTAL%] %NAME% completed >> "%LOG_FILE%"
exit /b 0

:fail
echo.
echo BestBuy %CATEGORY% full run failed. See log: %LOG_FILE%
echo BestBuy %CATEGORY% full run failed >> "%LOG_FILE%"
exit /b 1
