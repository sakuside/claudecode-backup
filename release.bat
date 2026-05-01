@echo off
REM 一键打新版本：重新构建 exe + 压 zip + 打 tag + 推送
REM 用法:
REM   release.bat 0.2.0
REM
REM 之后浏览器打开 GitHub Releases 页面把 dist/claudecode-backup-viewer.zip 拖上去就行

setlocal

if "%~1"=="" (
  echo 用法: release.bat ^<版本号^>
  echo 例如: release.bat 0.2.0
  exit /b 1
)

set "VERSION=%~1"
set "TAG=v%VERSION%"

echo.
echo === 1/4 PyInstaller 重新打包 ===
python -m PyInstaller --noconfirm claudecode-backup-viewer.spec
if errorlevel 1 (
  echo PyInstaller 失败，停止
  exit /b 1
)

echo.
echo === 2/4 压缩 dist 目录 ===
if exist "dist\claudecode-backup-viewer.zip" del "dist\claudecode-backup-viewer.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\claudecode-backup-viewer' -DestinationPath 'dist\claudecode-backup-viewer.zip' -CompressionLevel Optimal -Force"
if errorlevel 1 (
  echo 压缩失败，停止
  exit /b 1
)

for %%I in ("dist\claudecode-backup-viewer.zip") do echo zip 已生成: %%~zI bytes

echo.
echo === 3/4 打 tag ===
git tag %TAG%
if errorlevel 1 (
  echo tag %TAG% 已存在或 tag 失败
  exit /b 1
)

echo.
echo === 4/4 推送 tag ===
git push origin %TAG%

echo.
echo ====================================================
echo 全部完成。下一步：手工上传 zip 到 GitHub Releases
echo.
echo 1. 浏览器打开:
echo    https://github.com/sakuside/claudecode-backup/releases/new?tag=%TAG%
echo 2. 把 dist\claudecode-backup-viewer.zip 拖入 "Attach binaries" 区域
echo 3. 点 "Publish release"
echo ====================================================

endlocal
