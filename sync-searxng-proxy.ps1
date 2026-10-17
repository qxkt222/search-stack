# ============================================================
# sync-searxng-proxy.ps1
# 作用：同步「本地代理」端口 -> SearXNG 出站代理配置
#   1. 读取本地代理 config.yaml 里的 mixed-port（失败重试 3 次，间隔 2 秒）
#   2. 与 searxng-local-settings.yml 的代理端口比对
#   3. 不一致则改写配置并重启 SearXNG；一致则跳过
#
# 可配置环境变量（都有安全默认值）：
#   SEARXNG_PROXY_CONFIG  本地代理 config.yaml 路径
#                         （默认 %LOCALAPPDATA%\com.example.clash\data\clash\config.yaml）
#   SEARXNG_PROXY_HOST    出站代理主机（默认 127.0.0.1）
#   SEARXNG_PROXY_WAIT_SEC 等待代理配置出现的最长秒数（默认 30）
#   SEARXNG_URL           SearXNG 本地地址（默认 http://127.0.0.1:8888）
#
# 退出码：
#   0  成功（已同步或无需修改）
#   1  读取本地代理配置失败
#   2  SearXNG 配置文件读取/解析/写入失败
#   3  SearXNG 重启启动失败
# ============================================================

$ErrorActionPreference = 'Stop'

# ---------- 路径与参数（全部基于脚本目录，不写死本机路径） ----------
$scriptRoot      = $PSScriptRoot
$localProxyConfig = if ($env:SEARXNG_PROXY_CONFIG) {
    $env:SEARXNG_PROXY_CONFIG
} else {
    Join-Path $env:LOCALAPPDATA 'com.example.clash\data\clash\config.yaml'
}
$searxngSettings = Join-Path $scriptRoot 'searxng-local-settings.yml'
$searxngSrc      = Join-Path $scriptRoot 'searxng-src'
$searxngPython   = Join-Path $scriptRoot '.venv\Scripts\python.exe'
$logFile         = Join-Path $scriptRoot 'searxng-proxy-sync.log'
$proxyHost       = if ($env:SEARXNG_PROXY_HOST) { $env:SEARXNG_PROXY_HOST } else { '127.0.0.1' }
$searxngUrl      = if ($env:SEARXNG_URL) { $env:SEARXNG_URL.TrimEnd('/') } else { 'http://127.0.0.1:8888' }
$proxyWaitSec    = 30
if ($env:SEARXNG_PROXY_WAIT_SEC -match '^\d+$') { $proxyWaitSec = [int]$env:SEARXNG_PROXY_WAIT_SEC }
$readAttempts    = 3
$retryDelaySec   = 2

function Log([string]$msg, [string]$level = 'INFO') {
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $level, $msg
    Write-Host $line
    try {
        [System.IO.File]::AppendAllText($logFile, $line + "`n", (New-Object System.Text.UTF8Encoding $false))
    } catch {
        # 日志写不进去不影响主流程
    }
}

function Exit-With([int]$code, [string]$message, [string]$level = 'ERROR') {
    if ($message) { Log $message $level }
    Log ("exit code = {0}" -f $code)
    exit $code
}

# ---------- 1. 读取本地代理当前端口（等待就绪 + 3 次重试） ----------
function Get-ProxyPort {
    # 代理客户端可能比本脚本更晚启动：先等配置文件出现（默认最多 30 秒）
    $deadline = (Get-Date).AddSeconds($proxyWaitSec)
    while (-not (Test-Path -LiteralPath $localProxyConfig) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 1
    }

    for ($attempt = 1; $attempt -le $readAttempts; $attempt++) {
        if (Test-Path -LiteralPath $localProxyConfig) {
            try {
                $content = [System.IO.File]::ReadAllText($localProxyConfig, [System.Text.Encoding]::UTF8)
                if ($content -match '(?m)^\s*mixed-port:\s*(\d+)') {
                    $found = $matches[1]
                    Log ("读取本地代理配置成功（第 {0}/{1} 次）：mixed-port={2}" -f $attempt, $readAttempts, $found)
                    return $found
                }
                Log ("本地代理配置存在，但未找到 mixed-port（第 {0}/{1} 次）" -f $attempt, $readAttempts) 'WARN'
            } catch {
                Log ("读取本地代理配置失败（第 {0}/{1} 次）：{2}" -f $attempt, $readAttempts, $_.Exception.Message) 'WARN'
            }
        } else {
            Log ("本地代理配置不存在（第 {0}/{1} 次）：{2}" -f $attempt, $readAttempts, $localProxyConfig) 'WARN'
        }

        if ($attempt -lt $readAttempts) {
            Start-Sleep -Seconds $retryDelaySec
        }
    }
    return $null
}

# ---------- 2. 读取 SearXNG 配置（失败重试 3 次） ----------
function Read-SettingsFile([string]$path) {
    for ($attempt = 1; $attempt -le $readAttempts; $attempt++) {
        try {
            $text = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
            Log ("读取 SearXNG 配置成功（第 {0}/{1} 次）：{2}" -f $attempt, $readAttempts, $path)
            return $text
        } catch {
            Log ("读取 SearXNG 配置失败（第 {0}/{1} 次）：{2}" -f $attempt, $readAttempts, $_.Exception.Message) 'WARN'
            if ($attempt -lt $readAttempts) { Start-Sleep -Seconds $retryDelaySec }
        }
    }
    return $null
}

function Get-HttpStatus([string]$url, [int]$timeoutSec = 3) {
    # 显式禁用系统代理：代理未启动时 Invoke-WebRequest 访问 localhost 会误超时
    try {
        $req = [System.Net.HttpWebRequest]::Create($url)
        $req.Proxy = $null
        $req.Method = 'GET'
        $req.Timeout = $timeoutSec * 1000
        $resp = $req.GetResponse()
        $code = [int]$resp.StatusCode
        $resp.Close()
        return $code
    } catch {
        return 0
    }
}

function Wait-Healthz([int]$timeoutSec) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        if ((Get-HttpStatus "$searxngUrl/healthz" 2) -eq 200) { return $true }
        Start-Sleep -Milliseconds 800
    }
    return $false
}

# ---------- 主流程 ----------
Log "===== 开始同步代理端口 ====="
Log ("脚本目录: {0}" -f $scriptRoot)

if (-not (Test-Path -LiteralPath $searxngSettings)) {
    Exit-With 2 "SearXNG 配置文件不存在：$searxngSettings"
}

$port = Get-ProxyPort
if (-not $port) {
    Exit-With 1 "无法读取本地代理配置/端口（$localProxyConfig），同步失败。请确认代理已启动，或设置 SEARXNG_PROXY_CONFIG。"
}
Log "本地代理当前端口: $port"

$searxContent = Read-SettingsFile $searxngSettings
if ($null -eq $searxContent) {
    Exit-With 2 "无法读取 SearXNG 配置文件：$searxngSettings"
}

# 只匹配代理行，不吞掉行尾的 CR/LF（lookahead 不消费字符）
$portPattern = '(?m)^([ \t]*-[ \t]*http://' + [regex]::Escape($proxyHost) + ':)(\d+)(?=[ \t]*\r?$)'
$currentPort = $null
if ($searxContent -match $portPattern) {
    $currentPort = $matches[2]
}
$currentPortText = if ($null -eq $currentPort) { '无' } else { $currentPort }
Log ("SearXNG 当前配置代理端口: {0}（匹配主机 {1}）" -f $currentPortText, $proxyHost)

# ---------- 3. 比对，不一致则改写 + 重启 SearXNG ----------
if ($currentPort -eq $port) {
    Log "SUCCESS: 端口一致，无需修改。"
    Exit-With 0 ""
}

$newContent = $searxContent -replace $portPattern, ("`${1}" + $port)
if ($newContent -eq $searxContent) {
    Exit-With 2 ("配置中未找到代理行（- http://{0}:端口）。请先在 searxng-local-settings.yml 的 outgoing.proxies 中填写主机；若代理主机不是 {0}，请设置 SEARXNG_PROXY_HOST。" -f $proxyHost)
}

# 原子写入：先写临时文件，再替换，避免中途失败留下半个文件
$tempFile = "$searxngSettings.tmp"
try {
    [System.IO.File]::WriteAllText($tempFile, $newContent, (New-Object System.Text.UTF8Encoding $false))
    Move-Item -LiteralPath $tempFile -Destination $searxngSettings -Force
} catch {
    if (Test-Path -LiteralPath $tempFile) { Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue }
    Exit-With 2 ("写入 SearXNG 配置失败：{0}" -f $_.Exception.Message)
}
Log ("SUCCESS: 已更新 SearXNG 代理端口: {0} -> {1}" -f $currentPortText, $port)

# 重启 SearXNG（若在运行；源码/虚拟环境缺失时跳过，不视为失败）
$running = @()
try {
    $running = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'searx\.webapp' })
} catch {
    Log ("查询 SearXNG 进程失败：{0}" -f $_.Exception.Message) 'WARN'
}

$canRestart = (Test-Path -LiteralPath $searxngSrc) -and (Test-Path -LiteralPath $searxngPython)
if (-not $canRestart) {
    Log ("未找到 SearXNG 源码或虚拟环境，跳过自动重启。配置已更新，请手动重启（或使用 Docker）。") 'WARN'
    if ($running.Count -gt 0) {
        Log ("检测到 {0} 个旧 searx.webapp 进程仍在运行，它们不会自动加载新端口。" -f $running.Count) 'WARN'
    }
    Log "SUCCESS: 配置同步完成（未重启）。"
    Exit-With 0 ""
}

foreach ($p in $running) {
    try {
        Log "停止旧 SearXNG 进程 PID=$($p.ProcessId)"
        Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
    } catch {
        Log ("停止进程 PID={0} 失败：{1}" -f $p.ProcessId, $_.Exception.Message) 'WARN'
    }
}
if ($running.Count -gt 0) { Start-Sleep -Seconds 2 }

try {
    Log "启动 SearXNG..."
    $arg = 'cd /d "{0}" && set "SEARXNG_SETTINGS_PATH={1}" && "{2}" -m searx.webapp' -f $searxngSrc, $searxngSettings, $searxngPython
    Start-Process cmd.exe -ArgumentList '/c', $arg -WindowStyle Hidden -ErrorAction Stop
} catch {
    Exit-With 3 ("启动 SearXNG 失败：{0}" -f $_.Exception.Message)
}

if (Wait-Healthz 20) {
    Log ("SUCCESS: SearXNG 已重启并通过 healthz（{0}/healthz）。" -f $searxngUrl)
    Exit-With 0 ""
}

Log ("WARN: SearXNG 已启动，但 20 秒内 healthz 未就绪（{0}/healthz）。请检查代理与日志。" -f $searxngUrl) 'WARN'
Exit-With 0 ""
