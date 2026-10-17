# search-mcp

本地 SearXNG 的增强搜索 MCP 服务器（stdio）。在 SearXNG 原生搜索之上提供正文抓取、
搜索后自动抓正文、批量搜索、多引擎对比、缓存与健康检查。

## 工具（9 个）

| 工具 | 作用 |
|---|---|
| `web_search` | 调 SearXNG JSON API，返回标题/URL/摘要/引擎/分数 |
| `web_fetch` | 抓取网页并用 trafilatura 提取正文 |
| `search_and_fetch` | 搜索后并发抓取前 N 条正文 |
| `multi_search` | 多个 query 并发搜索，按 URL 归一化去重合并 |
| `search_compare` | 同一个 query 按引擎分别搜索，便于对比 |
| `health_check` | 检查 SearXNG、搜索接口、代理与缓存 |
| `cache_stats` / `cache_clear` | 查看/清空进程内 TTL 缓存 |
| `config_info` | 当前 URL、超时、缓存 TTL、代理（打码） |

所有工具返回统一信封：成功 `{"ok": true, "result": ...}`，失败 `{"ok": false, "error": "..."}`。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `SEARXNG_URL` | `http://localhost:8888` | SearXNG 地址 |
| `SEARCH_MCP_PROXY` | 空 | 外部抓取使用的代理，如 `http://<PROXY_HOST>:<PROXY_PORT>`；访问本机 SearXNG 自动直连 |
| `SEARCH_MCP_TIMEOUT` | `20` | HTTP 超时（秒） |
| `SEARCH_MCP_CACHE_TTL` | `300` | 搜索缓存 TTL（秒） |
| `SEARCH_MCP_FETCH_CACHE_TTL` | `3600` | 抓取缓存 TTL（秒） |

## 启动

```powershell
cd mcp-server
uv sync
uv run search-mcp
```

或使用虚拟环境入口：

```text
mcp-server\.venv\Scripts\search-mcp.exe
```

## Cherry / ZCode / LobeHub 注册

stdio 模式，命令指向上面的 exe（或 `uv run --directory <mcp-server> search-mcp`），
参数为空。环境变量按上表配置；需要抓取国际网页时设置 `SEARCH_MCP_PROXY`。

## 测试

```powershell
cd mcp-server
uv run pytest -q
```

测试全部离线（`httpx.MockTransport`），不依赖真实 SearXNG 或网络。
