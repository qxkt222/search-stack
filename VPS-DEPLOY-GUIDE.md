# VPS 部署 SearXNG —— 通用操作手册

> 全程大约 10 分钟。所有操作都在**服务器终端**里完成，不需要任何面板或特殊权限。
> 文中 `<SERVER_IP>` 请替换为你的服务器公网 IP。

---

## 第 1 步：连上服务器

用你平时的 SSH 方式连上任意一台服务器，看到类似 `root@xxx:~#` 的提示符即可。

> 查看公网 IP：在服务器里执行 `curl -s ifconfig.me`。

## 第 2 步：把部署脚本传到服务器（二选一）

**方式 A（推荐）：粘贴法**

在服务器终端执行：

```bash
cat > /root/vps-deploy.sh
```

然后把本地 `search-stack/vps-deploy.sh` 的内容全部粘贴进去，按 `Ctrl+D` 结束。

**方式 B：scp 上传**

在本地 `search-stack` 目录执行（替换 `<SERVER_IP>`）：

```bash
scp ./vps-deploy.sh root@<SERVER_IP>:/root/
```

## 第 3 步：执行部署脚本

```bash
bash /root/vps-deploy.sh
```

脚本会：检测/安装 Docker → 写入 `/opt/searxng/settings.yml` 与 `docker-compose.yml`
→ 启动 SearXNG → 尝试放行系统防火墙 → 输出验证结果。

默认端口为 `8888`，可在执行前覆盖：

```bash
export PORT=8899
bash /root/vps-deploy.sh
```

> 脚本会自动探测公网 IP。若探测不对，可先 `export VPS_IP=<SERVER_IP>` 再运行。

## 第 4 步：云厂商控制台放行端口

这是**最容易漏**的一步。进入云厂商控制台：

安全组 / 防火墙 → 入方向规则 → 新增规则 → **TCP 8888** → 来源 `0.0.0.0/0` → 保存。

（若第 3 步改了 `PORT`，这里放行对应端口。）

## 第 5 步：设置随机 secret

部署脚本写入的是公开占位符 `change-me-to-a-random-secret`，必须替换：

```bash
SECRET=$(openssl rand -hex 32)
sed -i "s|secret_key: .*|secret_key: \"$SECRET\"|" /opt/searxng/settings.yml
cd /opt/searxng && docker compose up -d --force-recreate
```

> 也可以把 secret 放进 compose 的 `SEARXNG_SECRET` 环境变量；两种方式选一种即可，
> 不要把真实 secret 提交到代码仓库。

## 第 6 步：本地验证

在本地终端执行（替换 `<SERVER_IP>`）：

```bash
curl -s http://<SERVER_IP>:8888/healthz
curl -s "http://<SERVER_IP>:8888/search?q=openai&format=json" | head -c 300
```

看到 HTTP 200 且 JSON 中有 `"results":[...]` 即成功。

Docker 状态检查（在服务器上）：

```bash
cd /opt/searxng
docker compose ps
docker logs --tail 100 searxng
```

## 第 7 步：接入 MCP 客户端

### 新版 search-mcp（stdio）

在客户端注册（JSON 中把 `<SERVER_IP>` 换成服务器 IP）：

```json
{
  "mcpServers": {
    "search": {
      "command": "<SEARCH_STACK_DIR>\\mcp-server\\.venv\\Scripts\\search-mcp.exe",
      "args": [],
      "env": {
        "SEARXNG_URL": "http://<SERVER_IP>:8888",
        "SEARCH_MCP_TIMEOUT": "20",
        "SEARCH_MCP_CACHE_TTL": "300"
      }
    }
  }
}
```

或使用 uv：

```json
{
  "mcpServers": {
    "search": {
      "command": "uv",
      "args": ["--directory", "<SEARCH_STACK_DIR>/mcp-server", "run", "search-mcp"],
      "env": { "SEARXNG_URL": "http://<SERVER_IP>:8888" }
    }
  }
}
```

### 旧版 mcp-searxng

把 `zcode-mcp.json` 或 `lobehub-mcp.json` 中的 `SEARXNG_URL` 改成
`http://<SERVER_IP>:8888`，再按对应客户端的方式导入。

### RikkaHub（局域网 HTTP MCP）

RikkaHub 的连接目标是 `http://<LAN_IP>:3000/mcp`，需要在本机运行
`rikkahub-launcher.ps1` 启动的 HTTP MCP；它再连接本机或 VPS 上的 SearXNG。

## 第 8 步（可选）：出站代理

VPS 通常可直连国际站点。如果目标引擎被反爬或网络受限，可在
`/opt/searxng/settings.yml` 中配置出站代理，然后重启：

```yaml
outgoing:
  proxies:
    all://:
      - http://<PROXY_HOST>:<PROXY_PORT>
```

```bash
cd /opt/searxng && docker compose restart
```

---

## 排错速查

| 现象 | 原因 | 解决 |
|---|---|---|
| `docker: command not found` 且安装卡住 | get.docker.com 被墙/超时 | 换源安装：`curl -fsSL https://get.docker.com \| sed 's\|download.docker.com\|mirrors.aliyun.com/docker-ce\|g' \| sh` |
| `docker compose: command not found` | 没装 compose 插件 | `apt install -y docker-compose-plugin`（Debian/Ubuntu）或 `yum install -y docker-compose-plugin`（CentOS） |
| `curl localhost:8888` 通，外部不通 | 云厂商安全组没放行 | 回第 4 步 |
| healthz 不通 | 容器未启动或配置语法错误 | `docker compose ps`；`docker logs searxng`；`docker compose config` |
| 搜索返回 0 结果 | 引擎被反爬或网络不通国际站 | 稍后重试；`curl -s -o /dev/null -w "%{http_code}" https://duckduckgo.com` 检查网络；必要时配置出站代理 |
| 端口 8888 被占用 | 服务器已有服务占用 | `lsof -i:8888` 查看；改 `PORT` 后重新部署，并同步安全组 |
| 浏览器/客户端提示 403 | 可能触发了 limiter 或安全组来源限制 | 检查 `server.limiter`、实例访问控制与来源 IP |
| secret 相关报错 | 仍在使用占位符或 secret 为空 | 按第 5 步重新生成并重启容器 |

---

## 安全提示

- 公网实例请至少：设置随机 `secret_key`、启用 HTTPS、按需开启 limiter。
- 不要将真实 secret、代理地址、内网 IP 写入公开仓库。
- 定期更新镜像并备份 `/opt/searxng/settings.yml`。
