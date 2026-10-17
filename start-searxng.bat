@echo off
echo ================================================
echo   SearXNG Launcher (local + proxy)
echo  ==============================================
echo   Step 1: 同步本地代理端口...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0sync-searxng-proxy.ps1"
echo.
echo   Step 2: 检查 SearXNG 状态...
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://localhost:8888/healthz' -UseBasicParsing -TimeoutSec 3).StatusCode } catch { 'DOWN' }" > %TEMP%\searx_check.txt 2>&1
set /p CHECK=<%TEMP%\searx_check.txt
if "%CHECK%"=="200" (
  echo   Already running. Just use it.
) else (
  echo   Starting... please wait.
  start /B cmd /c "cd /d %~dp0searxng-src && set SEARXNG_SETTINGS_PATH=%~dp0searxng-local-settings.yml && %~dp0.venv\Scripts\python.exe -m searx.webapp"
  echo   Waiting for service...
  powershell -NoProfile -Command "$i=0; while($i -lt 20){ try { $r=Invoke-WebRequest -Uri 'http://localhost:8888/healthz' -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -eq 200){ Write-Host '   OK - SearXNG is UP!'; exit 0 } } catch {}; Start-Sleep 1; $i++ }; Write-Host '   WARN - timeout. Open local proxy first, then rerun.'"
)
echo.
echo   Test in browser:  http://localhost:8888/search?q=test
echo   Closing this window does NOT stop SearXNG
echo ================================================
pause
