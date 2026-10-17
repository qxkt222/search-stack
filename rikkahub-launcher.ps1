# ============================================================
# rikkahub-launcher.ps1
# One-click launcher for the RikkaHub search stack on this PC.
#   1. Sync local proxy port into SearXNG outbound config
#      (reuses sync-searxng-proxy.ps1; no-op when port unchanged)
#   2. Ensure local SearXNG is listening on :8888
#      (RikkaHub built-in search connects to http://<LAN-IP>:8888)
#   3. Ensure mcp-searxng HTTP server is listening on :3000
#      (RikkaHub MCP endpoint: http://<LAN-IP>:3000/mcp)
# Idempotent: services already listening are left untouched.
# Requires: globally installed mcp-searxng (npm install -g mcp-searxng)
# ============================================================

$ErrorActionPreference = 'Continue'

# Ensure core system dirs are on PATH regardless of the launching
# environment (some terminals/launchers strip PATH entries).
$env:PATH = 'C:\WINDOWS\system32;C:\WINDOWS;C:\WINDOWS\System32\WindowsPowerShell\v1.0;' + $env:PATH

Write-Host '=== RikkaHub Search Stack Launcher ==='

# --- 1/3 proxy sync (original behavior preserved) ---
Write-Host '[1/3] Sync local proxy port...'
try {
    & '$PSScriptRoot\sync-searxng-proxy.ps1'
} catch {
    Write-Host "      proxy sync skipped: $($_.Exception.Message)"
}

# --- 2/3 SearXNG on :8888 ---
if (Get-NetTCPConnection -State Listen -LocalPort 8888 -ErrorAction SilentlyContinue) {
    Write-Host '[2/3] SearXNG already running on :8888'
} else {
    Write-Host '[2/3] Starting SearXNG on :8888...'
    Start-Process $env:ComSpec -ArgumentList '/c','cd /d $PSScriptRoot\searxng-src && set SEARXNG_SETTINGS_PATH=$PSScriptRoot\searxng-local-settings.yml && $PSScriptRoot\.venv\Scripts\python.exe -m searx.webapp' -WindowStyle Minimized
}

# --- 3/3 mcp-searxng HTTP on :3000 ---
if (Get-NetTCPConnection -State Listen -LocalPort 3000 -ErrorAction SilentlyContinue) {
    Write-Host '[3/3] MCP already running on :3000'
} else {
    Write-Host '[3/3] Starting MCP on :3000...'
    $env:MCP_HTTP_PORT = '3000'
    $env:MCP_HTTP_HOST = '0.0.0.0'
    $env:SEARXNG_URL = 'http://localhost:8888'
    $mcpCmd = Join-Path $env:APPDATA 'npm\mcp-searxng.cmd'
    if (Test-Path $mcpCmd) {
        Start-Process -FilePath $mcpCmd -WorkingDirectory '$PSScriptRoot' -WindowStyle Minimized
    } else {
        Write-Host '      WARN: global mcp-searxng not found (run: npm install -g mcp-searxng)'
    }
}

# --- wait & verify ---
Write-Host 'Waiting for services...'
Start-Sleep -Seconds 5
try {
    $s = (Invoke-WebRequest -Uri 'http://localhost:8888/healthz' -UseBasicParsing -TimeoutSec 4).StatusCode
    Write-Host "SearXNG  :8888 -> HTTP $s"
} catch { Write-Host 'SearXNG  :8888 -> not ready yet (still starting?)' }
try {
    $m = (Invoke-WebRequest -Uri 'http://localhost:3000/health' -UseBasicParsing -TimeoutSec 4).Content
    Write-Host "MCP      :3000 -> $m"
} catch { Write-Host 'MCP      :3000 -> not ready yet (still starting?)' }
Write-Host ''
$lanIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.PrefixOrigin -eq 'Dhcp' -and $_.InterfaceAlias -notmatch 'vEthernet' -and $_.IPAddress -notmatch '^169\.254' } | Select-Object -First 1).IPAddress
if (-not $lanIp) { $lanIp = '<LAN_IP>' }
Write-Host "Done. RikkaHub built-in search: http://${lanIp}:8888"
Write-Host "      RikkaHub MCP endpoint  : http://${lanIp}:3000/mcp"
