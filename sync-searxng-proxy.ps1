# ============================================================
# sync-searxng-proxy.ps1
# 作用：开机同步「本地代理」端口 -> SearXNG 出站代理配置
#   1. 读取本地代理 config.yaml 里的 mixed-port
#   2. 与 searxng-local-settings.yml 的代理端口比对
#   3. 不一致则改写配置并重启 SearXNG；一致则跳过
# 说明：本地代理每次启动会随机分配代理端口，SearXNG 出站
#       依赖该端口，必须同步。本脚本由开机启动自动触发。
# ============================================================

$ErrorActionPreference = 'Stop'

# ---------- 配置（路径固定，勿乱动） ----------
$localProxyConfig  = "$env:LOCALAPPDATA\com.example.clash\data\clash\config.yaml"
$searxngSettings = "$PSScriptRoot\searxng-local-settings.yml"
$searxngSrc     = "$PSScriptRoot\searxng-src"
$searxngPython  = "$PSScriptRoot\.venv\Scripts\python.exe"
$logFile        = "$PSScriptRoot\searxng-proxy-sync.log"

function Log($msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Write-Host $line
    [System.IO.File]::AppendAllText($logFile, $line + "`n", (New-Object System.Text.UTF8Encoding $false))
}

# ---------- 1. 读取本地代理当前端口（等待就绪，最多 30 秒） ----------
$port = $null
for ($i = 0; $i -lt 30; $i++) {
    if (Test-Path $localProxyConfig) {
        $content = Get-Content $localProxyConfig -Raw -ErrorAction SilentlyContinue
        if ($content -match '(?m)^\s*mixed-port:\s*(\d+)') {
            $port = $matches[1]
            break
        }
    }
    Start-Sleep -Seconds 1
}

if (-not $port) {
    Log "ERROR: 无法读取本地代理配置/端口（$localProxyConfig），跳过本次同步。"
    exit 1
}
Log "本地代理当前端口: $port"

# ---------- 2. 读取 SearXNG 配置里当前的代理端口 ----------
$searxContent = [System.IO.File]::ReadAllText($searxngSettings, [System.Text.Encoding]::UTF8)
$currentPort = $null
if ($searxContent -match '(?m)^(\s*-\s*http://127\.0\.0\.1:)(\d+)\s*$') {
    $currentPort = $matches[2]
}
$currentPortText = if ($null -eq $currentPort) { '无' } else { $currentPort }
Log "SearXNG 当前配置代理端口: $currentPortText"

# ---------- 3. 比对，不一致则改写 + 重启 SearXNG ----------
if ($currentPort -eq $port) {
    Log "端口一致，无需修改。"
} else {
    # 只改「- http://127.0.0.1:端口」这一行代理配置，不影响注释
    $newContent = $searxContent -replace '(?m)^(\s*-\s*http://127\.0\.0\.1:)\d+\s*$', ("`${1}" + $port)
    if ($newContent -eq $searxContent) {
        Log "ERROR: 配置中未找到代理行（- http://127.0.0.1:端口），无法修改。"
        exit 1
    }
    # 无 BOM 写入，避免 YAML 解析问题
    [System.IO.File]::WriteAllText($searxngSettings, $newContent, (New-Object System.Text.UTF8Encoding $false))
    Log "已更新 SearXNG 代理端口: $currentPortText -> $port"

    # 重启 SearXNG（若在运行）
    $running = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'searx\.webapp' }
    if ($running) {
        foreach ($p in $running) {
            Log "停止旧 SearXNG 进程 PID=$($p.ProcessId)"
            Stop-Process -Id $p.ProcessId -Force
        }
        Start-Sleep -Seconds 2
    }
    Log "启动 SearXNG..."
    $arg = 'cd /d "{0}" && set SEARXNG_SETTINGS_PATH={1} && "{2}" -m searx.webapp' -f $searxngSrc, $searxngSettings, $searxngPython
    Start-Process cmd.exe -ArgumentList '/c', $arg -WindowStyle Hidden
    Start-Sleep -Seconds 3
}

Log "完成。"
