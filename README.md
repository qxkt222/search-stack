# 搜索增强套件（SearXNG + search-mcp）

> **发布版说明**：本仓库是脱敏后的配置模板。`secret_key`、代理地址、局域网 IP 均已替换为占位符，使用前请自行填写；仓库不含 SearXNG 上游源码和 Python 虚拟环境。SearXNG 本身遵循 AGPL-3.0，请从其官方仓库获取。
>
> 本仓库提供**两种运行方式**：Windows 原生运行，或 Docker 运行 SearXNG。搜索 MCP 建议在宿主机以 stdio 方式运行。

---

## 架构

```
MCP 客户端（Cherry Studio / ZCode / LobeHub / Claude 等）
        │  stdio
        ▼
search-mcp（mcp-server/，6 个工具）
        │  HTTP JSON（/search?format=json）
        ▼
SearXNG  http://localhost:8888
        │  outgoing.proxies
        ▼
本地代理  http://<PROXY_HOST>:<PROXY_PORT>
        │
        ▼
Bing / DuckDuckGo / Brave / Mojeek / Startpage / Qwant / Wikipedia / Wikidata ...
```

**核心思路**：SearXNG 负责聚合搜索并输出 JSON；`search-mcp` 把它包装成 MCP 工具，
并提供正文抓取、批量搜索、引擎对比等增强能力。SearXNG 的出站请求走本地代理，
从而访问国际搜索引擎。

### search-mcp 工具

| 工具 | 作用 |
|---|---|
| `web_search` | 调用 SearXNG JSON API，返回结构化结果 |
| `web_fetch` | 抓取网页并用 trafilatura 提取正文 |
| `search_and_fetch` | 先搜索，再并发抓取前 N 条正文 |
| `multi_search` | 多查询并发搜索，按 URL 归一化去重 |
| `search_compare` | 同一条查询分别走不同引擎，便于对比 |
| `health_check` | 检查 healthz、搜索接口、代理变量、缓存与版本 |

所有工具统一返回 `{"ok": true, "result": ...}` 或 `{"ok": false, "error": "..."}`，不向 MCP 抛异常。

---

## 目录结构

```
search-stack/
├── README.md
├── docs/
│   ├── DEPLOY.md               ← 原生 / Docker / MCP 注册 / 排错
│   └── engines.md              ← 引擎说明（可选）
├── start-searxng.bat           ← 原生一键启动（同步代理 + 等待 healthz）
├── sync-searxng-proxy.ps1      ← 同步本地代理端口到 SearXNG 配置
├── rikkahub-launcher.ps1       ← RikkaHub 局域网启动器
├── docker-compose.yml          ← Docker 方式（仅 SearXNG）
├── searxng-settings.yml        ← Docker 使用的配置模板
├── searxng-local-settings.yml  ← 原生使用的配置模板（含代理占位符）
├── mcp-server/                 ← 新版 search-mcp（uv + Python 3.12）
├── zcode-mcp.json              ← 旧版 mcp-searxng 模板（可自行替换为 search-mcp）
├── lobehub-mcp.json            ← 旧版 mcp-searxng 模板
├── vps-deploy.sh               ← VPS 部署脚本（备用）
├── VPS-DEPLOY-GUIDE.md         ← VPS 部署手册（备用）
└── test-instances.sh           ← 公共 SearXNG 实例检测（备用）
```

---

## 两种运行方式

### 方式 A：原生（Windows，推荐个人使用）

前提：本机已准备 SearXNG 源码目录 `searxng-src\` 与虚拟环境 `.venv\`（仓库不包含），
并在 `searxng-local-settings.yml` 中填好代理占位符。

1. 打开本地代理并连接。
2. 填写配置：
   - `server.secret_key` 改为随机字符串（或后续用环境变量覆盖）；
   - `outgoing.proxies` 的 `<PROXY_HOST>` / `<PROXY_PORT>` 改为真实代理地址。
3. 双击 `start-searxng.bat`。脚本会：
   - 调用 `sync-searxng-proxy.ps1` 同步代理端口；
   - 从配置中读取代理地址并测试连通性；
   - 启动 SearXNG 后轮询 `/healthz`，最多 30 秒；
   - 如检测到 `mcp-server\.venv\Scripts\search-mcp.exe`，提示注册（不自动启动）。
4. 验证：浏览器打开 `http://localhost:8888/search?q=test`。

> 自动化调用可加 `/nopause`：`start-searxng.bat /nopause`。

### 方式 B：Docker（SearXNG 容器）

```bash
# 1. 设置 secret（不要使用默认占位符）
export SEARXNG_SECRET="$(openssl rand -hex 32)"      # PowerShell: $env:SEARXNG_SECRET = "<random-string>"

# 2. 启动
docker compose up -d

# 3. 查看状态与健康检查
docker compose ps
curl -s http://localhost:8888/healthz
```

说明：

- compose 只启动 SearXNG；`search-mcp` 仍在宿主机以 stdio 运行，连接 `http://localhost:8888`。
- 容器内端口为 8080，映射到宿主机 8888；配置文件挂载为 `./searxng-settings.yml`。
- 使用 Docker 时，原生脚本中的 `searxng-src\` / `.venv\` 不需要存在。
- 可选的 MCP 容器定义以注释形式保留在 compose 文件中，**需要自行提供 Dockerfile，未实测**。

---

## 搜索 MCP 注册（stdio）

环境变量：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SEARXNG_URL` | `http://localhost:8888` | SearXNG 地址 |
| `SEARCH_MCP_PROXY` | 空 | 可选，正文抓取使用的代理，如 `http://<PROXY_HOST>:<PROXY_PORT>` |
| `SEARCH_MCP_TIMEOUT` | `20` | 单次请求超时（秒） |
| `SEARCH_MCP_CACHE_TTL` | `300` | 搜索缓存秒数（抓取缓存固定 3600） |

JSON 配置模板（把 `<SEARCH_STACK_DIR>` 换成仓库所在目录）：

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

如果使用 `uv`，也可以不写死 exe 路径：

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

客户端入口：

- **Cherry Studio**：设置 → MCP → 添加服务器（stdio），填入 command / args / env。
- **ZCode**：把上述 JSON 放进项目根目录的 `.mcp.json`，重启 ZCode。
- **LobeHub**：桌面端 → 设置 → 插件 / MCP → 自定义 MCP → 粘贴上述 JSON。

> `search-mcp` 是 **stdio** 服务，不要把它当成 HTTP 端点。RikkaHub 的内置 MCP 走
> `http://<LAN_IP>:3000/mcp` 时使用 `rikkahub-launcher.ps1` 启动的 `mcp-searxng`（旧方案）。

---

## 健康检查

```bash
# SearXNG 存活
curl -s http://localhost:8888/healthz

# 搜索接口（必须返回 JSON 且有 results）
curl -s "http://localhost:8888/search?q=openai&format=json" | head -c 300

# Docker 健康状态
docker inspect --format "{{.State.Health.Status}}" searxng
```

MCP 侧：在客户端调用 `health_check()`，应返回 `{"ok": true, ...}`，其中包含
`searxng`、`search`、`proxy`、`cache` 各分项。

---

## 常用操作

| 操作 | 方法 |
|---|---|
| 启动 SearXNG（原生） | 双击 `start-searxng.bat` |
| 启动 SearXNG（Docker） | `docker compose up -d` |
| 停止 SearXNG（原生） | 任务管理器结束 `python.exe`（`searx.webapp`） |
| 停止 SearXNG（Docker） | `docker compose down` |
| 同步代理端口 | `powershell -NoProfile -ExecutionPolicy Bypass -File .\sync-searxng-proxy.ps1` |
| 查看同步日志 | 打开 `searxng-proxy-sync.log` |
| 换代理端口 | 改 `searxng-local-settings.yml` 的 `outgoing.proxies`，或让同步脚本自动改写 |
| 查看系统代理 | `reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyServer` |

---

## 排错速查

| 现象 | 原因 | 解决 |
|---|---|---|
| 启动脚本提示 proxy unreachable | 本地代理没开/没连接，或配置仍是 `<PROXY_HOST>` 占位符 | 打开代理并连接；填写 `outgoing.proxies`；重跑 `sync-searxng-proxy.ps1` |
| 搜索返回 0 结果 | 代理不通、引擎被反爬、或引擎被禁用 | 先 `curl healthz` 确认存活；换代理节点；在配置中启用/更换引擎 |
| healthz 30 秒超时 | 源码/虚拟环境路径不对、端口被占用、启动报错 | 看 SearXNG 控制台输出；检查 `.venv\Scripts\python.exe`；确认 8888 未被占用 |
| Docker healthcheck 一直 unhealthy | 镜像内 wget/python 与预期不符，或配置语法错误 | `docker logs searxng`；`docker inspect searxng`；必要时手动 `wget -q -O- http://localhost:8080/healthz` |
| MCP 连不上 / 客户端无工具 | command 路径错、venv 未安装依赖、`SEARXNG_URL` 不对 | 先手动运行 `search-mcp` 看报错；用 `uv sync` 安装依赖；确认 JSON 转义 |
| MCP 搜索成功但 `web_fetch` 失败 | 目标站反爬、超时、需要代理、正文是 JS 渲染 | 设置 `SEARCH_MCP_PROXY`；调大 `SEARCH_MCP_TIMEOUT`；换可静态抓取的来源 |
| 正文抓取为空或过短 | trafilatura 未识别正文 / 页面需登录 | 改用 `include_links` 或直接 `web_search`；`web_fetch` 返回的 `status` / `final_url` 可用于判断跳转 |
| 端口 8888 被占用 | 已有服务 | 改 `searxng-local-settings.yml` 的 `server.port`，并同步改脚本/客户端 URL |
| `ModuleNotFoundError: pwd` | Windows 源码兼容性补丁缺失 | 使用官方 Docker 镜像，或自行打 Windows 兼容补丁 |

---

## 备用方案（备忘）

- **VPS 部署**：`vps-deploy.sh` + `VPS-DEPLOY-GUIDE.md`
- **Docker**：`docker-compose.yml` + `searxng-settings.yml`
- **旧版 MCP**：`npx -y mcp-searxng`（`zcode-mcp.json` / `lobehub-mcp.json` 模板）
- **公共实例**：`test-instances.sh` 可检测一批公开 SearXNG 实例

---

## 成本与限制

| 项目 | 说明 |
|---|---|
| 费用 | 全免费（本地代理本身有流量额度则除外） |
| API Key | 无 |
| 限流 | 引擎反爬有影响，个人使用基本够 |
| 依赖 | 本地代理（国际网络）+ SearXNG 运行 |
| 覆盖引擎 | Bing / DuckDuckGo / Brave / Mojeek / Startpage / Qwant / Wikipedia / Wikidata 等 |

---

## 安全提示

- `searxng-settings.yml` 中的 `secret_key` 是占位符。Docker 方式请通过 `SEARXNG_SECRET`
  环境变量覆盖，或使用本地 `.env` 文件（不要提交）。
- 代理地址、局域网 IP 请按自己的环境填写，不要提交到公开仓库。
- 若把 SearXNG 暴露到公网，请同时配置限流、HTTPS 与访问控制。
