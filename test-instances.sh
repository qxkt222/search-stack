#!/usr/bin/env bash
# 公共 SearXNG 实例可用性检测
# 用法: bash test-instances.sh   （在 Git Bash 下运行）
# 检测项: /healthz 存活 + format=json 是否可用

instances=(
  "https://searx.be"
  "https://searx.xyz"
  "https://searx.underworld.fr"
  "https://searx.tiekoetter.com"
  "https://search.bus-hit.me"
  "https://searxng.world"
  "https://priv.au"
)

echo "== 检测 $(date +%F\ %T) =="
for u in "${instances[@]}"; do
  h=$(curl -s --max-time 8 -o /dev/null -w "%{http_code}" -H "User-Agent: Mozilla/5.0" "$u/healthz" 2>/dev/null)
  if [ "$h" = "200" ]; then
    j=$(curl -s --max-time 8 -o /dev/null -w "%{http_code}" -H "User-Agent: Mozilla/5.0" "$u/search?q=test&format=json" 2>/dev/null)
    echo "json=$j  $u"
  else
    echo "dead($h)  $u"
  fi
done
echo "== 完成。json=200 的实例可直接填进 SEARXNG_URL =="
