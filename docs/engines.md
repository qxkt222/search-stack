# 引擎配置与实测结果

本文记录 `searxng-local-settings.yml` 的引擎开关、权重，以及在本机环境中的实测可用性。
配置只做文本级修改，保留原有注释和格式；SearXNG 版本不升级。

- 配置日期：2026-10-17
- SearXNG 源码目录：`searxng-src`（`searx/version.py` 标记 1.0.0；`searx/version_frozen.py` 手写为 `2026.8.12`，运行日志显示的版本号以后者为准）
- 出站代理：本地 HTTP 代理（`outgoing.proxies`，真实端口仅在运行目录配置中）
- 测试查询：默认 `q=openai`；`mdn` 另测 `q=javascript`，`pubmed` 另测 `q=cancer`
- 接口：`/search?q=<query>&format=json&engines=<engine>`

## 1. 本次配置改动

### 1.1 新启用（`disabled: true` → 移除）

| 引擎 | 说明 |
|---|---|
| `bing` | 同时把 `base_url` 设为 `https://cn.bing.com`，原因见 3.2 |
| `qwant` | |
| `mojeek` | |
| `crossref` | 保留原有 `timeout: 30` |

### 1.2 权重

SearXNG 引擎条目支持 `weight`（默认 1.0）。本次只改已存在于 `engines:` 列表中的条目：

| 引擎 | weight | 依据 |
|---|---:|---|
| google | 1.5 | 高质量主搜索 |
| bing | 1.4 | 高质量主搜索 |
| brave | 1.4 | 高质量主搜索 |
| startpage | 1.3 | 高质量主搜索 |
| duckduckgo | 1.2 | 次一级 |
| wikipedia | 1.2 | 次一级（infobox） |
| qwant | 1.1 | 次一级 |
| mojeek | 1.0 | 次一级 |
| arxiv | 1.0 | 专业源 |
| crossref | 1.0 | 专业源 |
| semantic scholar | 1.0 | 专业源 |
| pubmed | 1.0 | 专业源 |
| google scholar | 1.0 | 专业源 |
| github | 1.0 | 专业源 |
| stackoverflow | 1.0 | 专业源 |
| mdn | 1.0 | 专业源 |

低质量聚合站（dogpile、fireball、crowdview、encyclosearch、fynd）当前均为 `disabled: true`，
不在默认轮询中，因此没有为它们设置 0.5~0.8 的权重；若以后启用，建议按 0.5~0.8 降权。

### 1.3 Google 的 `inactive`

原配置沿用上游默认值 `inactive: true`。该标记会让 SearXNG **完全不加载**该引擎
（`searx/engines/__init__.py: load_engines()` 直接跳过），此时 `weight` 也不会生效。
本次改为 `inactive: false`，使 Google 真正进入引擎列表。若不需要 Google，可改回 `true`。

### 1.4 Docker 覆盖配置

`searxng-settings.yml`（Docker 挂载的覆盖配置）同步了同样的开关和权重：

- `google`：`disabled: false` + `weight: 1.5`
- `bing/duckduckgo/brave/mojeek/startpage/qwant/wikipedia`：保持启用并写入对应权重
- 新增 `crossref`：`disabled: false` + `weight: 1.0`
- 保留 `secret_key: "change-me-to-a-random-secret"`
- 未写入真实代理地址、端口或内网 IP

> Docker 路径本身**未实测**（本次只验证了原生 `.venv` 启动）。该文件是
> `use_default_settings: true` 的覆盖式配置，引擎条目按名称与上游默认值合并；
> 上述开关/权重字段仍以原生配置的实测结果为准。

## 2. 实测可用性

> 以下“实测”均指 2026-10-17 在本机用 `searxng-src` + `.venv` 启动真实实例后，
> 通过 JSON API 得到的返回；“推断”为未直接测试、根据配置或上游行为判断。

| 引擎 | 返回结果数 | 状态 | 证据 |
|---|---:|---|---|
| google | 0 | 实测：反爬 | HTTP 200，响应为 JS/反爬页，无结果节点；日志无报错 |
| bing | 9 | 实测：可用 | `engines=['bing']`，修复 `base_url` 后 |
| brave | 0 | 实测：限流 | `unresponsive_engines: [["brave","Suspended: too many requests"]]` |
| startpage | 0 | 实测：CAPTCHA | `get_sc_code: got redirected to https://www.startpage.com/sp/captcha` |
| qwant | 0 | 实测：拒绝访问 | `Access denied (suspended_time=180)` |
| mojeek | 0 | 实测：拒绝访问 | `HTTP error 403 (suspended_time=180)` |
| duckduckgo | 0 | 实测：CAPTCHA | `CAPTCHA (wt-wt)` |
| wikipedia | 0 条 + 1 infobox | 实测：可用（infobox 模式） | `infobox: OpenAI`；`display_type: ["infobox"]` 不产生列表结果 |
| arxiv | 10 | 实测：可用 | `engines=['arxiv']` |
| crossref | 20 | 实测：可用 | `engines=['crossref']` |
| semantic scholar | 10 | 实测：可用 | `engines=['semantic scholar']` |
| pubmed | 0 | 实测：连接失败 | `httpx.ConnectError: eutils.ncbi.nlm.nih.gov`；直连/代理 curl 均为 SSL connect error |
| google scholar | 10 | 实测：可用 | `engines=['google scholar']` |
| github | 30 | 实测：可用 | `engines=['github']` |
| stackoverflow | 10 | 实测：可用 | `engines=['stackoverflow']` 返回 10 条 |
| mdn | 0（`openai`）/ 10（`javascript`） | 实测：可用 | 查询词与文档库相关时有结果 |
| bing news | 未测 | 推断：可用 | 复用 Bing 通道；本次未单独请求 |
| google cse | 20 | 实测：可用（旁证） | 未指定引擎的联合搜索中出现 `google cse` 20 条 |

联合搜索（`q=openai`，不指定引擎）实测：**29 条结果 / 0.50 秒**，
其中 `bing` 9 条、`google cse` 20 条，另有 Wikipedia `OpenAI` infobox；
brave、duckduckgo、mojeek、qwant、startpage 被上游拒绝（见上表）。

### 2.1 失败原因归类

- **上游反爬 / 限流**：google、brave、startpage、qwant、mojeek、duckduckgo。
  这类失败取决于出口 IP 与代理共享情况，换代理节点或降低请求频率可能改善，**不是配置错误**。
- **网络不可达**：pubmed 的 `eutils.ncbi.nlm.nih.gov` 在当前网络下 TLS 连接失败。
- **查询相关性**：mdn 对 `openai` 无结果，对 `javascript` 有 10 条，属于正常现象。

## 3. 关键修复说明

### 3.1 Google 不加载

`inactive: true` 会让 `load_engines()` 跳过该引擎。表现为：
`engines=google` 不再报“引擎不存在”，但实际由兜底/其它引擎返回结果，
`/config` 的引擎列表中也没有 `google`。改为 `inactive: false` 后 `/config` 可见且 `enabled=True`。

### 3.2 Bing 302 重定向

`https://www.bing.com/search?...` 在本机（含经代理）返回 **302 → `https://cn.bing.com/search?...`**。
SearXNG 的在线引擎默认 `allow_redirects: false`（`searx/search/processors/online.py`），
因此拿到的是 302 空壳页，解析结果为 0。将条目改为：

```yaml
base_url: https://cn.bing.com
```

后直接返回 200，解析到 9 条结果。若部署在境外且 `cn.bing.com` 反而发生重定向，
可移除该 `base_url` 使用默认值。

## 4. 验证结果

```text
YAML OK  searxng-local-settings.yml (engines=344)
YAML OK  searxng-settings.yml      (engines=10)
YAML OK  publish/searxng-local-settings.yml (engines=344)
YAML OK  publish/searxng-settings.yml      (engines=10)

本地配置文件：
  lines=3482  comments=116  disabled:true=245  inactive:true=67  weight=23
  （改动前：lines=3470  comments=116  disabled:true=249  inactive:true=68  weight=7）
  注释数量未减少；删除了 4 个 disabled、1 个 inactive，新增 16 个 weight。

发布副本与运行配置的差异仅剩脱敏项（secret_key / 代理占位符 / 内网地址注释）。
发布副本中检索不到真实端口 <PROXY_PORT>、真实 secret_key 或 127.0.0.1:<PROXY_PORT>。
```

权重由 SearXNG 实际加载确认（`load_engines()` 后读取 `engine.weight`）：

```text
google 1.5 / bing 1.4 / brave 1.4 / startpage 1.3 / duckduckgo 1.2 / wikipedia 1.2 /
qwant 1.1 / mojeek 1.0 / arxiv 1.0 / crossref 1.0 / semantic scholar 1.0 /
pubmed 1.0 / google scholar 1.0 / github 1.0 / stackoverflow 1.0 / mdn 1.0
```

## 5. 测试环境备注

- 测试时 `localhost:8888` 已被另一个 SearXNG 进程（外部 uv 安装，非本项目启动）占用，
  为避免干扰，本次实例使用 `SEARXNG_PORT=8889`、`SEARXNG_BIND_ADDRESS=127.0.0.1` 启动。
- 测试完成后已按 PID 终止本次启动的进程树，8889 已无监听；8888 上的外部进程保持运行。
- 复现命令：

```bash
cd searxng-src
SEARXNG_SETTINGS_PATH=/path/to/searxng-local-settings.yml \
SEARXNG_PORT=8889 SEARXNG_BIND_ADDRESS=127.0.0.1 \
../.venv/Scripts/python.exe -m searx.webapp

curl "http://127.0.0.1:8889/search?q=openai&format=json&engines=bing"
```
