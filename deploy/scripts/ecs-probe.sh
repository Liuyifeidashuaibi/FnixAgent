#!/usr/bin/env bash
# FnixAgent ECS 只读探查 (read-only probe) — 由云助手 RunCommand 执行
# 目标: 确认 仓库路径 / Docker 容器 / 端口 / 资源。本脚本只读, 不改动任何状态。
set -u
hr() { printf '===== %s =====\n' "$1"; }

hr "1. 主机与资源"
hostname; uname -a
uptime
free -h 2>/dev/null || head -3 /proc/meminfo
df -h / 2>/dev/null
echo -n "docker server: "; docker version -f '{{.Server.Version}}' 2>/dev/null || echo "N/A"

hr "2. Docker 容器与编排"
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}' 2>/dev/null || echo "docker ps 失败(权限/未运行)"
docker compose ls 2>/dev/null || true
docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}' 2>/dev/null | head -20

hr "3. 查找 fnixagent 仓库"
for d in /opt /data /srv /root /home /var/www "$PWD"; do
  [ -d "$d" ] || continue
  find "$d" -maxdepth 4 \( -name 'docker-compose.prod.yml' -o -name 'docker-compose.yml' -o -name 'pyproject.toml' \) 2>/dev/null
done | head -30

hr "4. 监听端口"
( command -v ss >/dev/null && ss -ltnp 2>/dev/null ) || ( command -v netstat >/dev/null && netstat -ltnp 2>/dev/null ) || echo "无 ss/netstat"

hr "5. 后端相关进程"
ps -eo pid,comm,args 2>/dev/null | grep -iE 'fnix|uvicorn|gunicorn|serve' | grep -v grep | head

hr "DONE (read-only probe)"
