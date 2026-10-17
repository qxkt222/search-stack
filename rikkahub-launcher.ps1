# ============================================================
# rikkahub-launcher.ps1
# One-click launcher for the RikkaHub search stack on this PC.
#   1. Sync local proxy port into SearXNG outbound config
#      (reuses sync-searxng-proxy.ps1; no-op when port unchanged)
#   2. Ensure local SearXNG is listening on :8888
#      (RikkaHub built-in search connects to http://<LAN_IP>:8888)
#   3. Ensure mcp-searxng HTTP server is listening on :3000
#      (RikkaHub MCP endpoint: http://<LAN_IP>:3000/mcp)
# Idempotent: services already listening are left untouched.
# Requires: globally installed mcp-searxng (npm install -g mcp-searxng)
#
# Note: the new stdio server (mcp-server/, entry point search-mcp) is a
# separate stdio MCP and is not part of this HTTP launcher.
# ============================================================

$ErrorActionPreference = 'Continue'

# Ensure core system dirs are on PATH regardless of the launching
# environment (some terminals/launchers strip PATH entries).
$sysRoot = $env:SystemRoot
if (-not $sysRoot) { $sysRoot = 'C:\WINDOWS' }
$env:PATH = "$sysRoot\system32;$sysRoot;$sysRoot\System32\WindowsPowerShell\v1.0;" + $env:PATH

# Use IPv4 literals: .NET may resolve localhost to ::1 and time out when
# the service is bound to 127.0.0.1 only.
$searxngHealth = 'http://127.0.0.1:8888/healthz'
$mcpHealth     = 'http://127.0.0.1:3000/health'

function Get-HttpStatus {
    param(
        [string]$Url,
        [int]$TimeoutSec = 3
    )
    # Disable the system proxy explicitly: when the local proxy is down,
    # Invoke-WebRequest would time out even for localhost.
    try {
        $req = [System.Net.HttpWebRequest]::Create($Url)
        $req.Proxy = $null
        $req.Method = 'GET'
        $req.Timeout = $TimeoutSec * 1000
        $resp = $req.GetResponse()
        $code = [int]$resp.StatusCode
        $resp.Close()
        return $code
    } catch {
        return 0
    }
}

function Test-Healthz {
    param(
        [string]$Url,
        [int]$TimeoutSec = 30
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        if ((Get-HttpStatus -Url $Url -TimeoutSec 3) -eq 200) { return $true }
        Start-Sleep -Milliseconds 800
    } while ((Get-Date) -lt $deadline)
    return $false
}

Write-Host '=== RikkaHub Search Stack Launcher ==='

# --- 1/3 proxy sync (original behavior preserved) ---
Write-Host '[1/3] Sync local proxy port...'
$syncScript = Join-Path $PSScriptRoot 'sync-searxng-proxy.ps1'
if (Test-Path -LiteralPath $syncScript) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $syncScript
    Write-Host "      proxy sync exit code: $LASTEXITCODE"
} else {
    Write-Host "      WARN: sync-searxng-proxy.ps1 not found next to this script"
}

# --- 2/3 SearXNG on :8888 ---
if (Get-NetTCPConnection -State Listen -LocalPort 8888 -ErrorAction SilentlyContinue) {
    Write-Host '[2/3] SearXNG already running on :8888'
} else {
    Write-Host '[2/3] Starting SearXNG on :8888...'
    $searxngSrc = Join-Path $PSScriptRoot 'searxng-src'
    $settings   = Join-Path $PSScriptRoot 'searxng-local-settings.yml'
    $python     = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

    if ((Test-Path -LiteralPath $searxngSrc) -and (Test-Path -LiteralPath $python)) {
        $env:SEARXNG_SETTINGS_PATH = $settings
        Start-Process $env:ComSpec -ArgumentList '/c', "cd /d `"$searxngSrc`" && `"$python`" -m searx.webapp" -WindowStyle Minimized
    } else {
        Write-Host '      ERROR: SearXNG source/venv not found.'
        Write-Host "             expected: $searxngSrc"
        Write-Host "             expected: $python"
        Write-Host '             See docs/DEPLOY.md, or use Docker: docker compose up -d'
    }
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
    if (Test-Path -LiteralPath $mcpCmd) {
        Start-Process -FilePath $mcpCmd -WorkingDirectory $PSScriptRoot -WindowStyle Minimized
    } else {
        Write-Host '      WARN: global mcp-searxng not found (run: npm install -g mcp-searxng)'
    }
}

# --- wait & verify ---
Write-Host 'Waiting for SearXNG (max 30s)...'
if (Test-Healthz -Url $searxngHealth -TimeoutSec 30) {
    Write-Host 'SearXNG  :8888 -> HTTP 200'
} else {
    Write-Host ''
    Write-Host 'WARN: SearXNG healthz did not return 200 within 30 seconds.'
    Write-Host '  1. Is the local proxy running and connected?'
    Write-Host '     Check outgoing.proxies in searxng-local-settings.yml.'
    Write-Host '  2. Run sync-searxng-proxy.ps1 to re-sync the proxy port'
    Write-Host '     and check searxng-proxy-sync.log.'
    Write-Host '  3. Check the SearXNG window/log for startup errors.'
    Write-Host '  4. Docker alternative: docker compose up -d'
    Write-Host ''
}

Write-Host 'Waiting for MCP (max 15s)...'
if (Test-Healthz -Url $mcpHealth -TimeoutSec 15) {
    Write-Host 'MCP      :3000 -> HTTP 200'
} else {
    Write-Host 'MCP      :3000 -> not ready yet (check the npm mcp-searxng window)'
}

Write-Host ''
$lanIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.PrefixOrigin -eq 'Dhcp' -and
        $_.InterfaceAlias -notmatch 'vEthernet' -and
        $_.IPAddress -notmatch '^169\.254'
    } |
    Select-Object -First 1).IPAddress
if (-not $lanIp) { $lanIp = '<LAN_IP>' }
Write-Host "Done. RikkaHub built-in search: http://${lanIp}:8888"
Write-Host "      RikkaHub MCP endpoint  : http://${lanIp}:3000/mcp"
Write-Host ''
Write-Host 'Tip: the new stdio server (mcp-server\...\search-mcp.exe) is'
Write-Host '     registered directly in an MCP client, not through this launcher.'
