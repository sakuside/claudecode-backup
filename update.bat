@echo off
REM 一键提交所有改动到 GitHub
REM 用法:
REM   update.bat                       使用默认提交信息（带时间戳）
REM   update.bat "Fix dropdown bug"    使用自定义提交信息
REM
REM 注意: build/ 和 dist/ 已经在 .gitignore 排除，不会被误提交

setlocal

if "%~1"=="" (
  for /f "tokens=2 delims==" %%a in ('wmic os get localdatetime /value ^| find "="') do set DT=%%a
  set "MSG=Update %DT:~0,4%-%DT:~4,2%-%DT:~6,2% %DT:~8,2%:%DT:~10,2%"
) else (
  set "MSG=%~1"
)

echo.
echo === git status ===
git status --short
echo.

set /p CONFIRM="确认推送以上改动？(Y/n) "
if /i "%CONFIRM%"=="n" (
  echo 已取消
  exit /b 0
)

echo.
echo === git add ===
git add -A

echo.
echo === git commit ===
git commit -m "%MSG%"
if errorlevel 1 (
  echo 没有可提交的改动，跳过 push
  exit /b 0
)

echo.
echo === git push ===
git push

echo.
echo 完成。
endlocal
