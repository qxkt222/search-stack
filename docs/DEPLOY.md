# 部署指南（原生 Windows / Docker / MCP 注册）

本指南覆盖三种部署动作：

1. **原生方式**：在 Windows 上直接运行 SearXNG（源码 + venv）。
2. **Docker 方式**：用 `docker-compose.yml` 运行 SearXNG 容器。
3. **MCP 注册**：把 `search-mcp` 以 stdio 方式接入 Cherry Studio / ZCode / LobeHub。

两种 SearXNG 运行方式二选一即可。`search-mcp` 始终建议运行在宿主机，
通过 HTTP 连接 `http://localhost:8888`。

---

## 0. 前置条件

| 项目 | 原生 | Docker |
|---|---|---|
| 操作系统 | Windows 10/11 | 任意支持 Docker 的系统 |
| Python | 3.11+（含 venv） | 不需要 |
| SearXNG 源码 | 需要 `searxng-src\` | 不需要（镜像内置） |
| Docker | 不需要 | Docker Engine / Docker Desktop |
| 本地代理 | 访问国际引擎时需要 | 同左 |
| 端口 | 8888（可改） | 8888（可改） |

通用检查：

```bash
docker --version          # Docker 方式
docker info               # 守护进程必须可用，否则容器起不来
python --version          # 原生方式
```

> **重要**：本仓库发布时未在 CI 中实测 Docker 容器启动；`docker compose config`
> 仅验证 YAML 结构。请以 `docker compose ps` 与 healthcheck 的实际结果为准。

---

## 1. 方式 A：原生 Windows

### 1.1 准备 SearXNG 源码与虚拟环境

在 `search-stack` 目录下执行（目录名可自定，脚本默认寻找 `searxng-src\` 和 `.venv\`）：

```powershell
git clone https://github.com/searxng/searxng.git searxng-src
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r .\searxng-src\requirements.txt
```

Windows 上若启动时报 `ModuleNotFoundError: pwd` 等错误，说明缺少 Windows 兼容补丁。
可改用 Docker 方式，或自行给源码打补丁。

### 1.2 填写配置

编辑 `searxng-local-settings.yml`：

```yaml
server:
  # 不要使用默认占位符；也可以在启动前设置 SEARXNG_SECRET 环境变量覆盖
  secret_key: "change-me-to-a-random-secret"

outgoing:
  proxies:
    all://:
      - http://<PROXY_HOST>:<PROXY_PORT>
```

- `<PROXY_HOST>` / `<PROXY_PORT>` 换成你的本地代理地址。
- `search.formats` 必须包含 `json`，否则 MCP 无法获得结构化结果。
- 如果代理客户端是 Clash 系，`sync-searxng-proxy.ps1` 会尝试读取其 `mixed-port`
  并改写上面这一行。默认读取路径为
  `%LOCALAPPDATA%\com.example.clash\data\clash\config.yaml`（占位符，需按实际客户端修改）：
  - 设置环境变量 `SEARXNG_PROXY_CONFIG` 指向真实的 `config.yaml`；
  - 或直接手动改 `outgoing.proxies`，不依赖同步脚本。
- 代理主机不是 `127.0.0.1` 时，设置 `SEARXNG_PROXY_HOST`，否则同步脚本不会改写。

### 1.3 启动与验证

```powershell
# 一键：同步代理端口 -> 检查代理 -> 启动 -> 等待 healthz（最多 30 秒）
.\start-searxng.bat

# 自动化场景不暂停
.\start-searxng.bat /nopause
```

手动启动（等价命令）：

```powershell
$env:SEARXNG_SETTINGS_PATH = (Resolve-Path .\searxng-local-settings.yml)
$env:SEARXNG_SECRET = "<random-string>"      # 可选，覆盖 settings.yml
.\searxng-src\..\.venv\Scripts\python.exe -m searx.webapp
```

验证：

```bash
curl -s http://localhost:8888/healthz
curl -s "http://localhost:8888/search?q=openai&format=json" | head -c 300
```

期望：`healthz` 返回 200；JSON 中含 `"results":[...]`。

### 1.4 停止

在任务管理器中结束运行 `searx.webapp` 的 `python.exe`，或：

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'searx\.webapp' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

### 1.5 代理同步脚本行为

`sync-searxng-proxy.ps1`：

- 等待代理配置文件出现（`SEARXNG_PROXY_WAIT_SEC`，默认 30 秒）；
- 读取失败重试 **3 次**，间隔 **2 秒**；
- 端口一致则跳过；不一致则原子改写配置并重启 SearXNG；
- 结果写入 `searxng-proxy-sync.log`；
- 退出码：`0` 成功，`1` 读取代理失败，`2` 配置读写失败，`3` 重启失败。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\sync-searxng-proxy.ps1
echo "exit=$LASTEXITCODE"
```

---

## 2. 方式 B：Docker

### 2.1 设置 secret

`searxng-settings.yml` 里的 `secret_key` 是公开占位符。启动时用环境变量覆盖：

```bash
# bash / Git Bash
export SEARXNG_SECRET="$(openssl rand -hex 32)"
docker compose up -d
```

```powershell
# PowerShell
$env:SEARXNG_SECRET = -join ((1..64) | ForEach-Object { '0123456789abcdef'[(Get-Random -Maximum 16)] })
docker compose up -d
```

也可以创建本地 `.env`（不要提交）：

```dotenv
SEARXNG_SECRET=<random-string>
```

### 2.2 启动、健康检查、日志

```bash
docker compose config          # 只校验 YAML / 变量展开，不启动容器
docker compose up -d
docker compose ps
docker inspect --format "{{.State.Health.Status}}" searxng
docker logs --tail 100 searxng
```

手动检查容器内 healthz：

```bash
docker exec searxng wget -q -O - http://localhost:8080/healthz
```

compose 中的 healthcheck 优先用 `wget`，失败时回退到 Python。若镜像行为与预期不符，
可改为：

```yaml
healthcheck:
  test: ["CMD", "wget", "--spider", "-q", "http://localhost:8080/healthz"]
```

### 2.3 端口与挂载

- 容器内 SearXNG 监听 `8080`，映射到宿主机 `8888`。
- `./searxng-settings.yml` 以只读方式挂载到 `/etc/searxng/settings.yml`。
- 改端口时同时修改 `ports` 映射和 `SEARXNG_BASE_URL`。

### 2.4 可选：MCP 容器（未实测）

推荐做法仍是宿主机运行 `search-mcp`（stdio）。如果确实要容器化：

1. 在 `mcp-server/` 下自行提供 `Dockerfile`；
2. 取消 `docker-compose.yml` 末尾注释块；
3. `SEARXNG_URL` 使用服务名：`http://searxng:8080`；
4. `depends_on` 已按 `service_healthy` 编写。

该路径**未在本仓库实测**，不保证开箱可用。

---

## 3. MCP 注册（stdio）

### 3.1 安装依赖

```bash
cd mcp-server
uv sync
```

安装后入口为 `mcp-server\.venv\Scripts\search-mcp.exe`（Windows）。
也可以不依赖固定路径，使用：

```bash
uv --directory <SEARCH_STACK_DIR>/mcp-server run search-mcp
```

### 3.2 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SEARXNG_URL` | `http://localhost:8888` | SearXNG 地址（Docker 容器内互访时为 `http://searxng:8080`） |
| `SEARCH_MCP_PROXY` | 空 | 可选，正文抓取代理：`http://<PROXY_HOST>:<PROXY_PORT>` |
| `SEARCH_MCP_TIMEOUT` | `20` | 请求超时（秒） |
| `SEARCH_MCP_CACHE_TTL` | `300` | 搜索缓存（秒）；抓取缓存 3600 秒 |

### 3.3 通用 JSON（Cherry Studio / ZCode / LobeHub）

```json
{
  "mcpServers": {
    "search": {
      "command": "<SEARCH_STACK_DIR>\\mcp-server\\.venv\\Scripts\\search-mcp.exe",
      "args": [],
      "env": {
        "SEARXNG_URL": "http://localhost:8888",
        "SEARCH_MCP_PROXY": "http://<PROXY_HOST>:<PROXY_PORT>",
        "SEARCH_MCP_TIMEOUT": "20",
        "SEARCH_MCP_CACHE_TTL": "300"
      }
    }
  }
}
```

或使用 uv（不写死 exe 路径）：

```json
{
  "mcpServers": {
    "search": {
      "command": "uv",
      "args": ["--directory", "<SEARCH_STACK_DIR>/mcp-server", "run", "search-mcp"],
      "env": { "SEARXNG_URL": "http://localhost:8888" }
    }
  }
}
```

> Windows JSON 路径中的反斜杠必须转义为 `\\`，或改用正斜杠。

### 3.4 各客户端

- **Cherry Studio**：设置 → MCP → 添加服务器 → 类型选 `stdio`，填入 command / args / env。
- **ZCode**：把 JSON 保存为项目根目录 `.mcp.json`，重启 ZCode。
  仓库中的 `zcode-mcp.json` 是旧版 `mcp-searxng` 模板，可按上面的新配置替换。
- **LobeHub**：桌面端 → 设置 → 插件 / MCP → 自定义 MCP → 粘贴 JSON。
  仓库中的 `lobehub-mcp.json` 同样是旧版模板。

注册后调用 `health_check` 验证，返回 `{"ok": true, ...}` 即接入成功。

---

## 4. 健康检查清单

```bash
# 1. SearXNG 进程/容器存在
docker compose ps                                  # Docker
Get-Process python                                 # 原生（可选）

# 2. healthz
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8888/healthz

# 3. 搜索 API
curl -s "http://localhost:8888/search?q=test&format=json" | head -c 200

# 4. MCP
#    在客户端调用 health_check()，或直接运行 search-mcp 观察启动日志
```

健康判定：

- `healthz` 返回 `200`；
- `/search?format=json` 返回含 `results` 的 JSON；
- `health_check` 的 `searxng`、`search` 分项为 true。

---

## 5. 常见故障

### 5.1 代理不可用

现象：启动脚本提示 `proxy unreachable`，或搜索返回 0 结果。

处理：

1. 确认本地代理已启动并连接；
2. 检查 `searxng-local-settings.yml` 的 `outgoing.proxies` 是否仍是占位符；
3. 运行同步脚本并查看日志：

   ```powershell
   .\sync-searxng-proxy.ps1
   Get-Content .\searxng-proxy-sync.log -Tail 30
   ```

4. 代理客户端配置路径不同时，设置 `SEARXNG_PROXY_CONFIG`；
5. 代理主机不是 `127.0.0.1` 时，设置 `SEARXNG_PROXY_HOST`。

### 5.2 healthz 超时

现象：`start-searxng.bat` 提示 30 秒内未就绪。

处理：

1. 确认 `.venv\Scripts\python.exe` 与 `searxng-src\` 存在；
2. 手动前台启动，直接观察报错：

   ```powershell
   $env:SEARXNG_SETTINGS_PATH = (Resolve-Path .\searxng-local-settings.yml)
   .\.venv\Scripts\python.exe -m searx.webapp
   ```

3. 检查 8888 是否被占用：

   ```powershell
   Get-NetTCPConnection -State Listen -LocalPort 8888
   ```

4. Docker 方式检查 `docker logs searxng`。

### 5.3 MCP 无法连接

现象：客户端看不到工具，或启动即退出。

处理：

1. 手动运行入口，观察 stderr：

   ```powershell
   .\mcp-server\.venv\Scripts\search-mcp.exe
   ```

2. 确认 `uv sync` 已执行、依赖已安装；
3. 检查 JSON 路径转义与环境变量；
4. 确认 `SEARXNG_URL` 可访问（先 curl healthz）；
5. 若客户端要求 HTTP，不要使用 `search-mcp`（它是 stdio）。

### 5.4 正文抓取失败

现象：`web_fetch` / `search_and_fetch` 返回错误或空正文。

处理：

1. 设置 `SEARCH_MCP_PROXY`，部分站点需要代理；
2. 调大 `SEARCH_MCP_TIMEOUT`；
3. 查看返回的 `status` 与 `final_url`，判断是否被重定向/拦截；
4. JS 渲染页面无法静态抓取，改用 `web_search` 的结果摘要；
5. 站点反爬时可换其他来源或稍后重试。

### 5.5 Docker 相关

| 现象 | 处理 |
|---|---|
| `failed to connect to the docker API` | 启动 Docker Desktop / 守护进程后重试 |
| healthcheck 一直 `starting` | 看 `docker logs searxng`；等待 `start_period` |
| 容器启动即退出 | `docker compose config` 检查配置；确认挂载文件存在 |
| 宿主机访问 8888 失败 | 检查端口映射与防火墙 |

### 5.6 端口占用

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8888
```

修改 `server.port`（原生）或 compose 的 `ports`（Docker），并同步修改脚本与 MCP 的 `SEARXNG_URL`。

---

## 6. 安全与脱敏

- **secret_key**：`searxng-settings.yml` 中仅为占位符。Docker 用 `SEARXNG_SECRET` 覆盖；
  原生可在启动前设置同名环境变量。不要把真实 secret 提交到仓库。
- **代理地址**：使用 `<PROXY_HOST>:<PROXY_PORT>` 占位符，按本机环境填写。
- **局域网 IP**：脚本运行时自动探测，文档与配置中使用 `<LAN_IP>`。
- **路径**：脚本使用 `%~dp0` / `$PSScriptRoot`，不依赖绝对路径。
- 若将 SearXNG 暴露到公网：启用 limiter、配置 HTTPS、限制来源，并定期更新镜像。
