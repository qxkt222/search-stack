@echo off
setlocal EnableExtensions
rem ============================================================
rem  start-searxng.bat - native Windows launcher
rem  - all paths are relative to this script (%~dp0)
rem  - syncs the local proxy port, then checks the outbound proxy
rem  - waits up to 30 seconds for /healthz
rem  - prints a hint when the new search-mcp binary is present
rem  Usage: double-click, or: start-searxng.bat /nopause
rem ============================================================

set "ROOT=%~dp0"
set "SETTINGS=%ROOT%searxng-local-settings.yml"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
set "SRC=%ROOT%searxng-src"
rem Use an IPv4 literal: .NET may resolve localhost to ::1 and time out
rem when SearXNG is bound to 127.0.0.1.
set "HEALTHZ=http://127.0.0.1:8888/healthz"
set "TMP_OUT=%TEMP%\searxng-launch-%RANDOM%%RANDOM%.txt"

echo ================================================
echo   SearXNG Launcher - native mode
echo ================================================
echo   Project: %ROOT%
echo.

if not exist "%SETTINGS%" (
  echo   ERROR: settings file not found:
  echo          %SETTINGS%
  echo   This repository is a sanitized template; create or copy the
  echo   settings file first. See docs\DEPLOY.md.
  goto :fatal
)

if not exist "%PYTHON%" (
  echo   ERROR: Python virtualenv not found:
  echo          %PYTHON%
  echo   Native mode needs the SearXNG source tree and its venv.
  echo   See docs\DEPLOY.md, or use Docker: docker compose up -d
  goto :fatal
)

rem ---------- 1/4: sync local proxy port (existing behavior) ----------
echo   [1/4] Syncing local proxy port...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%sync-searxng-proxy.ps1"
set "SYNC_RC=%ERRORLEVEL%"
if "%SYNC_RC%"=="0" (
  echo   Proxy sync: OK
) else (
  echo   Proxy sync: FAILED with exit code %SYNC_RC%
  echo   See searxng-proxy-sync.log for details.
)
echo.

rem ---------- 2/4: check the outbound proxy from the synced settings ----------
echo   [2/4] Checking outbound proxy from settings...
set "SEARX_SETTINGS=%SETTINGS%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$y=Get-Content -Raw -LiteralPath $env:SEARX_SETTINGS; if($y -match '(?m)^[ \t]*-[ \t]*http://([^:/\s<>]+):(\d+)[ \t]*\r?$'){ $h=$matches[1]; $p=[int]$matches[2]; $c=New-Object Net.Sockets.TcpClient; try { $ar=$c.BeginConnect($h,$p,$null,$null); if($ar.AsyncWaitHandle.WaitOne(2000) -and $c.Connected){ 'UP ' + $h + ':' + $p } else { 'DOWN ' + $h + ':' + $p } } catch { 'DOWN ' + $h + ':' + $p } finally { $c.Close() } } else { 'UNSET proxy-placeholder-or-missing-outgoing-proxies' }" > "%TMP_OUT%" 2>&1
set /p PROXY_STATUS=<"%TMP_OUT%"
echo   Proxy: %PROXY_STATUS%
echo %PROXY_STATUS% | findstr /B /C:"UP " >nul
if errorlevel 1 (
  echo   WARN: outbound proxy is not reachable.
  echo         1. Fill ^<PROXY_HOST^>:^<PROXY_PORT^> in searxng-local-settings.yml
  echo         2. Start your local proxy and connect it, then rerun.
  echo   Continuing anyway; searches may return 0 results until the
  echo   proxy is available.
)
echo.

rem ---------- 3/4: start SearXNG if healthz is not already up ----------
echo   [3/4] Checking SearXNG...
rem Use HttpWebRequest with Proxy=$null: Invoke-WebRequest honors the system
rem proxy and can time out on localhost when that proxy is down.
powershell -NoProfile -ExecutionPolicy Bypass -Command "function C($u){ try { $q=[System.Net.HttpWebRequest]::Create($u); $q.Proxy=$null; $q.Timeout=3000; $q.Method='GET'; $s=$q.GetResponse(); $c=[int]$s.StatusCode; $s.Close(); $c } catch { 0 } }; if((C '%HEALTHZ%') -eq 200){'UP'}else{'DOWN'}" > "%TMP_OUT%" 2>&1
set /p SX_STATUS=<"%TMP_OUT%"
if /I "%SX_STATUS%"=="UP" (
  echo   Already running at http://localhost:8888
  goto :after_start
)

if not exist "%SRC%" (
  echo   ERROR: SearXNG source not found:
  echo          %SRC%
  echo   See docs\DEPLOY.md for native setup, or use Docker.
  goto :fatal
)

echo   Starting SearXNG...
set "SEARXNG_SETTINGS_PATH=%SETTINGS%"
pushd "%SRC%"
start "SearXNG" /MIN "%PYTHON%" -m searx.webapp
popd

:after_start
echo.

rem ---------- 4/4: poll healthz for up to 30 seconds ----------
echo   [4/4] Waiting for healthz (max 30s)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "function C($u){ try { $q=[System.Net.HttpWebRequest]::Create($u); $q.Proxy=$null; $q.Timeout=2000; $q.Method='GET'; $s=$q.GetResponse(); $c=[int]$s.StatusCode; $s.Close(); $c } catch { 0 } }; $deadline=(Get-Date).AddSeconds(30); while((Get-Date) -lt $deadline){ if((C '%HEALTHZ%') -eq 200){ Write-Output 'OK'; exit 0 }; Start-Sleep -Milliseconds 1000 }; Write-Output 'TIMEOUT'; exit 1" > "%TMP_OUT%" 2>&1
set "POLL_RC=%ERRORLEVEL%"
if "%POLL_RC%"=="0" (
  echo   OK - SearXNG is UP at %HEALTHZ%
) else (
  echo   ERROR - healthz did not return 200 within 30 seconds.
  echo     1. Is the local proxy running and connected?
  echo     2. Run sync-searxng-proxy.ps1 and check searxng-proxy-sync.log
  echo     3. Check the SearXNG console output for startup errors.
  echo     4. Docker alternative: docker compose up -d
)
echo.

rem ---------- optional search-mcp hint (never auto-started) ----------
if exist "%ROOT%mcp-server\.venv\Scripts\search-mcp.exe" (
  echo   Search MCP detected:
  echo     %ROOT%mcp-server\.venv\Scripts\search-mcp.exe
  echo   It speaks stdio; register it in your MCP client.
  echo   See docs\DEPLOY.md. This launcher does not start it.
  echo.
)

echo   Test in browser:  http://localhost:8888/search?q=test
echo   This window can be closed without stopping SearXNG.
echo ================================================

del "%TMP_OUT%" >nul 2>&1
endlocal & set "SEARXNG_LAUNCH_RC=%POLL_RC%"
if /I not "%~1"=="/nopause" pause
exit /b %SEARXNG_LAUNCH_RC%

:fatal
echo ================================================
del "%TMP_OUT%" >nul 2>&1
endlocal
if /I not "%~1"=="/nopause" pause
exit /b 1
