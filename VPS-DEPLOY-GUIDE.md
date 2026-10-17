# VPS 部署 SearXNG —— 傻瓜操作手册

> 全程大约 10 分钟。所有操作都在**服务器终端**里完成，不需要任何 ID / 面板 / 特殊权限。

---

## 第 1 步：连上服务器

用你平时的一键连接方式，连上**任意一台**服务器（推荐连外网最稳的那台）。
连上后你会看到类似 `root@xxx:~#` 的提示符。

> 记下这台的公网 IP：在服务器里执行 `curl -s ifconfig.me` 就能看到。

## 第 2 步：把部署脚本弄到服务器上（二选一）

**方式 A（推荐，最稳）：粘贴法**
在服务器终端执行下面这条命令，然后**把本地文件 `vps-deploy.sh` 的内容全部复制粘贴进去**，最后按 `Ctrl+D` 结束：

```bash
cat > /root/vps-deploy.sh
```

（本地文件位置：`search-stack\vps-deploy.sh`。用记事本打开全选复制即可。）

**方式 B：scp 上传**（如果你电脑的 Git Bash 能直接连服务器）
```bash
scp /d/1233344/search-stack/vps-deploy.sh root@服务器IP:/root/
```

## 第 3 步：执行部署脚本

```bash
bash /root/vps-deploy.sh
```

脚本会自动：检测/安装 Docker → 写配置（已开 JSON API + 国际引擎）→ 启动 SearXNG → 放行防火墙 → 验证。
**最后会输出公网 IP 和验证结果**，照抄即可。

> 脚本里的 `VPS_IP` 会自动探测，一般无需手动设。若探测不对，可先 `export VPS_IP=服务器IP` 再跑。

## 第 4 步：云厂商控制台放行端口

这是**最容易漏**的一步。去你服务器的云厂商控制台：
安全组 / 防火墙 → 入方向规则 → 新增规则 → **TCP 端口 8888** → 来源 `0.0.0.0/0` → 保存。

## 第 5 步：本地验证

在你电脑的 Git Bash 执行（IP 换成你的服务器 IP）：

```bash
curl "http://你的服务器IP:8888/search?q=openai&format=json"
```

看到 JSON 里有 `"results":[...]` 就成功 ✅

## 第 6 步：接入 ZCode + LobeHub

把服务器 IP 告诉 ZCode（我），我帮你改好两份配置文件；或自己改：

- `zcode-mcp.json` 里 `SEARXNG_URL` → `http://你的服务器IP:8888`，复制到 ZCode 项目根目录改名 `.mcp.json`，重启 ZCode
- `lobehub-mcp.json` 同理，LobeHub 桌面端"自定义 MCP"导入

---

## 排错速查

| 现象 | 原因 | 解决 |
|---|---|---|
| `docker: command not found` 且安装卡住 | get.docker.com 被墙/超时 | 换源安装：`curl -fsSL https://get.docker.com | sed 's|download.docker.com|mirrors.aliyun.com/docker-ce|g' \| sh` |
| `docker compose: command not found` | 没装 compose 插件 | `apt install -y docker-compose-plugin`（Debian/Ubuntu）或 `yum install -y docker-compose-plugin`（CentOS） |
| `curl localhost:8888` 通，但外部访问不通 | 云厂商安全组没放行 | 回第 4 步 |
| 搜索返回 0 结果 | 引擎被反爬或网络不通国际站 | 稍后重试；在 VPS 上 `curl -s -o /dev/null -w "%{http_code}" https://duckduckgo.com` 检查网络 |
| 端口 8888 被占用 | 服务器已有服务占用 | 改 `vps-deploy.sh` 里的 `PORT`（如 8899），或用 `docker compose -f /opt/searxng/docker-compose.yml up -d` 前先 `lsof -i:8888` 查看 |
