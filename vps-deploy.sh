#!/usr/bin/env bash
# SearXNG 一键部署脚本 —— 在 VPS 上运行（Linux，root 或 sudo 均可）
# 用法：把本文件传到 VPS（scp 或粘贴），然后执行  bash vps-deploy.sh
set -euo pipefail

# ============ 可配置项 ============
# 留空则自动探测公网 IP（也可以在服务器上先 export VPS_IP=你的IP 再运行）
VPS_IP="${VPS_IP:-}"
PORT=8888
if [ -z "$VPS_IP" ]; then
  VPS_IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || echo 127.0.0.1)
fi
# ==================================

echo "== SearXNG VPS 一键部署 =="

# 1) 检测/安装 Docker
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "[1/5] Docker 已就绪"
else
  echo "[1/5] 安装 Docker ..."
  if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh || { echo "Docker 安装失败，请手动安装后再运行"; exit 1; }
  fi
  (systemctl enable --now docker 2>/dev/null || service docker start)
fi

# 2) 创建目录
APP_DIR=/opt/searxng
mkdir -p "$APP_DIR"
echo "[2/5] 配置目录: $APP_DIR"

# 3) 写入 settings.yml（已开启 JSON API + 国际引擎，Google 反爬强默认禁用）
cat > "$APP_DIR/settings.yml" <<'YAML'
use_default_settings: true

general:
  instance_name: "My SearXNG"
  debug: false

search:
  # 必须包含 json，MCP 才能拿结构化结果
  formats:
    - html
    - json
  safe_search: 0
  autocomplete: ""

server:
  secret_key: "change-me-to-a-random-secret"
  limiter: false
  public_instance: false
  image_proxy: false
  method: "POST"

outgoing:
  request_timeout: 8.0
  max_request_timeout: 15.0

engines:
  - name: google
    disabled: true
  - name: bing
    disabled: false
  - name: duckduckgo
    disabled: false
  - name: brave
    disabled: false
  - name: mojeek
    disabled: false
  - name: startpage
    disabled: false
  - name: qwant
    disabled: false
  - name: wikipedia
    disabled: false
  - name: wikidata
    disabled: false
YAML
echo "[3/5] settings.yml 已写入"

# 4) 写入 docker-compose.yml
cat > "$APP_DIR/docker-compose.yml" <<YAML
services:
  searxng:
    image: searxng/searxng:latest
    container_name: searxng
    restart: unless-stopped
    ports:
      - "${PORT}:8080"
    environment:
      - SEARXNG_BASE_URL=http://${VPS_IP}:${PORT}/
    volumes:
      - ./settings.yml:/etc/searxng/settings.yml:ro
YAML
echo "[4/5] docker-compose.yml 已写入"

# 5) 启动
cd "$APP_DIR"
docker compose up -d
echo "[5/5] 启动完成"

# 系统防火墙放行（注意：云厂商控制台的安全组/防火墙也需单独放行 ${PORT}）
if command -v ufw >/dev/null 2>&1; then
  ufw allow ${PORT}/tcp >/dev/null 2>&1 && echo "ufw 已放行 ${PORT}"
elif command -v firewall-cmd >/dev/null 2>&1; then
  firewall-cmd --permanent --add-port=${PORT}/tcp >/dev/null 2>&1 && firewall-cmd --reload >/dev/null 2>&1 && echo "firewalld 已放行 ${PORT}"
fi

sleep 4
echo
echo "== 验证 =="
curl -s -o /dev/null -w "healthz: %{http_code}\n" http://localhost:${PORT}/healthz
curl -s "http://localhost:${PORT}/search?q=test&format=json" | head -c 300
echo
echo
echo "== 完成！下一步 =="
echo "1) 去云厂商控制台（安全组/防火墙）放行 TCP ${PORT}"
echo "2) 本地电脑验证：curl http://${VPS_IP}:${PORT}/search?q=test&format=json"
echo "3) 把本地 .mcp.json 里 SEARXNG_URL 改成 http://${VPS_IP}:${PORT}"
