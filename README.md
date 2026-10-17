# 搜索增强套件（ZCode + LobeHub 通用）

> **发布版说明**：本仓库是脱敏后的配置模板。`secret_key`、代理地址、局域网 IP 均已替换为占位符，使用前请自行填写；仓库不含 SearXNG 上游源码和 Python 虚拟环境。SearXNG 本身遵循 AGPL-3.0，请从其官方仓库获取。


> 目的：用开源 + 免费 + 无需 API Key 的方式，把 ZCode 和 LobeHub 的网页搜索能力做起来。
> 更新时间：2026-08-11（最终方案：本地 SearXNG + 本地代理，已全链路验证通过 ✅）

---

## ✅ 最终方案（已验证）

```
ZCode（MCP npx mcp-searxng）──┐
                              ├──▶ 本地 SearXNG（http://localhost:8888）──▶ 本地代理（<PROXY_HOST>:<PROXY_PORT>）──▶ DuckDuckGo/Brave/Mojeek/Wikipedia（国际结果）
LobeHub（自定义 MCP）──────────┘
```

**核心思路**：SearXNG 是纯 Python 应用，直接在你 Windows 上原生运行（不需要 Docker）；
它的出站请求走本地代理，从而能访问国际搜索引擎。**不需要 VPS、不需要 Docker。**

已实测通过：`searxng_web_search` MCP 工具调用返回国际搜索结果。

---

## 目录结构

```
search-stack/
├── README.md                   ← 本文件
├── start-searxng.bat           ← ✅ 一键启动 SearXNG（双击即可，自动检测是否已运行）
├── zcode-mcp.json              ← ZCode 配置模板（复制到项目根目录改名 .mcp.json）
├── lobehub-mcp.json            ← LobeHub 桌面端"自定义 MCP"导入配置
├── searxng-local-settings.yml  ← 本地 SearXNG 配置（已开 JSON API + 代理指向 <PROXY_HOST>:<PROXY_PORT>）
├── （不含 SearXNG 上游源码；请使用官方镜像或自行安装）
├── （不含虚拟环境；依赖请自行安装）
├── vps-deploy.sh               ← VPS 部署脚本（备用，若以后想放服务器）
├── VPS-DEPLOY-GUIDE.md         ← VPS 部署手册（备用）
└── test-instances.sh           ← 公共 SearXNG 实例检测（备用）
```

---

## 使用步骤

### 第 1 步：启动 SearXNG

双击 `start-searxng.bat`。它会自动检测并启动，等提示"已启动"。

> ⚠️ 前提：**先打开本地代理并连接**（SearXNG 要经由它的代理访问国际引擎）。

### 第 2 步：验证

浏览器打开 `http://localhost:8888/search?q=test`，或命令行：
```bash
curl "http://localhost:8888/search?q=openai&format=json"
```

### 第 3 步：接入 ZCode

把 `zcode-mcp.json` 复制到你的 ZCode 项目根目录，改名 `.mcp.json`，重启 ZCode。
Agent 就能用 `searxng_web_search` 工具搜索了。

### 第 4 步：接入 LobeHub

桌面端 → 设置 → 插件/MCP → 自定义 MCP → 导入 `lobehub-mcp.json`（stdio 模式）。

---

## 常用操作

| 操作 | 方法 |
|---|---|
| 启动 SearXNG | 双击 `start-searxng.bat` |
| 停止 SearXNG | 任务管理器结束 `python.exe`（或重启后自动消失，非自启） |
| 换代理端口 | 本地代理重装/改端口后，改 `searxng-local-settings.yml` 的 `outgoing.proxies`（2026-08-13 当前为 <PROXY_PORT>） |
| 查看系统代理 | `reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyServer` |
| 手动启动（Git Bash） | 需自行准备 `searxng-src` 与 `.venv`：`cd searxng-src && SEARXNG_SETTINGS_PATH=../searxng-local-settings.yml ../.venv/Scripts/python.exe -m searx.webapp` |

---

## 排错速查

| 现象 | 原因 | 解决 |
|---|---|---|
| 搜索返回 0 结果 | 本地代理没开/没连接 | 打开本地代理并点连接，重启 SearXNG |
| 搜索超时 | 代理慢或断 | 换本地代理节点，或调大 `request_timeout` |
| `ModuleNotFoundError: pwd` | 源码被升级覆盖补丁 | 自行重新打 Windows 兼容补丁 |
| healthz 200 但 MCP 无结果 | 引擎被反爬 | 稍后重试，或在设置里增删引擎 |
| 端口 8888 被占用 | 已有服务 | 改 `searxng-local-settings.yml` 的 `server.port` 并同步改 bat 与 mcp 配置 |

---

## 备用方案（备忘）

- **VPS 部署**：`vps-deploy.sh` + `VPS-DEPLOY-GUIDE.md`（如果你以后想用服务器跑）
- **Docker**：`docker-compose.yml` + `searxng-settings.yml`（需自行准备 Docker 环境）
- **DuckDuckGo MCP**：`uvx duckduckgo-mcp-server`（最简单，无代理也试过可能超时）
- **Wikipedia API**：ZCode WebFetch 直接调，真免费无限流，适合资料收集

---

## 成本与限制

| 项目 | 说明 |
|---|---|
| 费用 | 全免费（本地代理本身有流量额度则除外） |
| API Key | 无 |
| 限流 | 引擎反爬有影响，个人使用基本够 |
| 依赖 | 本地代理开启（国际网络）+ SearXNG 运行 |
| 覆盖引擎 | DuckDuckGo / Brave / Mojeek / Startpage / Qwant / Wikipedia / Wikidata 等 |
