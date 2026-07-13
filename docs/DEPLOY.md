# fnixagent 部署手册

> **目标**:新人在 30 分钟内于干净的 Linux 主机上一键部署 fnixagent,并通过桌面客户端完成登录 / 对话 / 文件上传全流程。

本手册覆盖三种部署形态:

| 形态 | 编排文件 | 端口暴露 | 适用场景 |
|---|---|---|---|
| 开发环境 | `docker-compose.yml` | 全部端口暴露 | 本地开发 / 联调 |
| 生产环境(单机) | `deploy/docker/docker-compose.prod.yml` | 仅 80 / 443 | 单机生产部署 |
| 桌面客户端 | 连接远程后端 | — | 终端用户使用 |

---

## 目录

- [1. 环境前提](#1-环境前提)
- [2. 快速开始(30 分钟一键部署)](#2-快速开始30-分钟一键部署)
- [3. 配置详解](#3-配置详解)
- [4. Nginx 反向代理 + HTTPS](#4-nginx-反向代理--https)
- [5. 桌面客户端连接远程后端](#5-桌面客户端连接远程后端)
- [6. 部署验证清单](#6-部署验证清单)
- [7. 运维操作](#7-运维操作)
- [8. 故障排查](#8-故障排查)
- [9. 升级与回滚](#9-升级与回滚)

---

## 1. 环境前提

### 1.1 硬件要求

| 资源 | 最低 | 推荐 |
|---|---|---|
| CPU | 4 核 | 8 核 |
| 内存 | 8 GB | 16 GB |
| 磁盘 | 50 GB SSD | 100 GB SSD |
| 网络 | 10 Mbps | 100 Mbps |

> 内存主要被 Elasticsearch(2G)+ Milvus(4G)+ PostgreSQL(2G)占用,8G 是底线。

### 1.2 软件要求

| 软件 | 版本 | 安装命令(Ubuntu 22.04) |
|---|---|---|
| Docker Engine | ≥ 24.0 | `curl -fsSL https://get.docker.com \| sh` |
| Docker Compose | ≥ 2.20(已内置于 docker) | 随 docker 一同安装 |
| OpenSSL | ≥ 1.1.1 | `apt-get install -y openssl` |
| rsync(可选,CDN 同步用) | 任意 | `apt-get install -y rsync` |

验证安装:

```bash
docker --version          # Docker version 24.x
docker compose version    # Docker Compose version v2.20+
openssl version           # OpenSSL 1.1.1+
```

### 1.3 端口规划

| 端口 | 服务 | 是否对外 |
|---|---|---|
| 80 | nginx HTTP(重定向到 443) | 是 |
| 443 | nginx HTTPS | 是 |
| 8000 | fnixagent 后端 | 生产环境仅容器内可达 |
| 5432 | PostgreSQL | 生产环境仅容器内可达 |
| 6379 | Redis | 生产环境仅容器内可达 |
| 19530 | Milvus | 生产环境仅容器内可达 |
| 9000/9001 | MinIO API / Console | 生产环境仅容器内可达 |
| 9200 | Elasticsearch | 生产环境仅容器内可达 |

> 开发环境(`docker-compose.yml`)会把所有端口暴露到宿主机,方便调试;生产环境(`docker-compose.prod.yml`)仅暴露 80/443。

---

## 2. 快速开始(30 分钟一键部署)

### 2.1 克隆代码(2 分钟)

```bash
git clone <your-repo-url> fnixagent
cd fnixagent
```

### 2.2 准备环境变量(3 分钟)

复制生产环境变量模板并填写:

```bash
cp .env.prod.example .env.prod
vi .env.prod
```

**必须修改的项**:

```bash
# 数据库密码(强随机串)
POSTGRES_PASSWORD=$(openssl rand -hex 24)

# Redis 密码
REDIS_PASSWORD=$(openssl rand -hex 24)

# MinIO 访问密钥(8-20 字符)
MINIO_ACCESS_KEY=fnixagent
MINIO_SECRET_KEY=$(openssl rand -hex 16)

# Elasticsearch 密码
ES_PASSWORD=$(openssl rand -hex 16)

# JWT 密钥(至少 32 字节)
JWT_SECRET_KEY=$(openssl rand -hex 32)

# LLM API 密钥(至少配置一个)
GLM_API_KEY=your_glm_api_key_here
# OPENAI_API_KEY=...
# DEEPSEEK_API_KEY=...
# QWEN_API_KEY=...
```

> 提示:可直接执行 `make gen-secrets` 自动生成随机密码并写入 `.env.prod`。

### 2.3 准备 SSL 证书(5 分钟)

**方案 A:自签证书(开发/内网)**

```bash
mkdir -p deploy/nginx/certs
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout deploy/nginx/certs/privkey.pem \
  -out deploy/nginx/certs/fullchain.pem \
  -days 365 -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

**方案 B:Let's Encrypt(生产/公网域名)**

参见 [§4.2 Let's Encrypt 证书](#42-lets-encrypt-证书生产公网)。

### 2.4 一键启动(10 分钟)

```bash
# 拉取镜像 + 构建应用镜像 + 启动所有服务
docker compose -f deploy/docker/docker-compose.prod.yml --env-file .env.prod up -d --build
```

等待所有健康检查通过:

```bash
# 查看启动状态
docker compose -f deploy/docker/docker-compose.prod.yml ps

# 期望所有服务 STATUS 为 healthy
# NAME                          STATUS                   PORTS
# fnixagent-app-prod          Up (healthy)             8000/tcp
# fnixagent-nginx-prod        Up                       0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
# fnixagent-postgres-prod     Up (healthy)             5432/tcp
# fnixagent-redis-prod        Up (healthy)             6379/tcp
# fnixagent-milvus-prod       Up (healthy)             19530/tcp
# fnixagent-minio-prod        Up (healthy)             9000/tcp
# fnixagent-etcd-prod         Up (healthy)             2379/tcp
# fnixagent-es-prod           Up (healthy)             9200/tcp
```

> Milvus 首次启动需要约 60-90 秒做初始化,请耐心等待。

### 2.5 初始化数据库(3 分钟)

```bash
# 进入应用容器执行数据库迁移
docker compose -f deploy/docker/docker-compose.prod.yml exec fnixagent \
  alembic upgrade head

# 可选:注入内置工具集(文档转换 / 搜索 等)
docker compose -f deploy/docker/docker-compose.prod.yml exec fnixagent \
  python scripts/seed_tools.py
```

### 2.6 验证服务(2 分钟)

```bash
# 1. 健康检查
curl -k https://localhost/health
# 期望: {"status":"ok","service":"fnixagent",...}

# 2. 获取 OpenAPI 文档(浏览器访问)
# https://localhost/docs

# 3. 注册首个管理员账户(register 接口 role 字段默认 user,可显式传 admin 引导首个管理员)
curl -k -X POST https://localhost/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","email":"admin@example.com","password":"Admin@123456","role":"admin"}'

# 若安全策略要求 register 不可直接指定 admin,则:
#   1) 先以 user 注册
#   2) 在数据库中提权:
#      docker compose -f deploy/docker/docker-compose.prod.yml exec postgres \
#        psql -U fnixagent -d fnixagent \
#        -c "UPDATE users SET role='admin' WHERE username='admin';"
```

至此,后端服务部署完成。接下来配置桌面客户端。

---

## 3. 配置详解

### 3.1 环境变量(.env.prod)

完整变量清单见 [.env.prod.example](../.env.prod.example)。关键变量分组:

#### 数据库与缓存

| 变量 | 说明 | 默认 |
|---|---|---|
| `POSTGRES_PASSWORD` | PostgreSQL 密码 | **必填** |
| `REDIS_PASSWORD` | Redis 密码 | **必填** |
| `MINIO_ACCESS_KEY` | MinIO 访问键 | fnixagent |
| `MINIO_SECRET_KEY` | MinIO 秘密键 | **必填** |
| `ES_PASSWORD` | Elasticsearch elastic 用户密码 | **必填** |

#### 应用

| 变量 | 说明 | 默认 |
|---|---|---|
| `JWT_SECRET_KEY` | JWT 签名密钥(≥32 字节) | **必填** |
| `fnixagent_MODE` | 运行模式:`legacy` / `evolve` | evolve |
| `SERVICE_ENV` | 环境标识 | production |

#### LLM 密钥

至少配置一个,否则 AI 对话功能不可用:

| 变量 | Provider |
|---|---|
| `GLM_API_KEY` | 智谱 GLM |
| `OPENAI_API_KEY` | OpenAI |
| `DEEPSEEK_API_KEY` | DeepSeek |
| `QWEN_API_KEY` | 阿里通义千问 |

### 3.2 settings.yaml(运行时配置)

位置:`config/settings.yaml`,通过只读挂载进入容器。**支持热更新**的配置项可通过管理后台 `/api/v1/admin/config` PATCH 修改,无需重启。

热更新白名单(共 10 项):

```yaml
memory.short_term.max_messages       # 短期记忆消息上限
memory.short_term.token_threshold    # 短期记忆 token 阈值
memory.long_term.enabled             # 是否启用长期记忆
llm.router.default_provider          # 默认 LLM Provider
llm.router.fallback_providers        # 备选 Provider 列表
llm.cache.ttl_seconds                # LLM 响应缓存 TTL
retrieval.top_k                      # 向量检索 top_k
retrieval.score_threshold            # 检索分数阈值
security.password.min_length         # 密码最小长度
security.password.require_special    # 密码是否要求特殊字符
```

修改示例:

```bash
curl -k -X PATCH https://localhost/api/v1/admin/config \
  -H "Authorization: Bearer <admin_access_token>" \
  -H "Content-Type: application/json" \
  -d '{"memory.short_term.max_messages": 30}'
```

### 3.3 自进化资产目录

`assets/` 目录通过 volume 挂载,保存 Agent 自进化过程中产生的拓扑、痕迹、快照:

```
assets/
├── topology/    # 技能拓扑图(JSON)
├── traces/      # 执行轨迹(NDJSON)
├── snapshots/   # 能力快照
├── skills/      # 自学习到的技能
├── prompts/     # 动态注入的 prompt 片段
├── flywheel/    # 飞轮规则
└── meta/        # 版本元信息
```

> 首次部署为空目录(含 `.gitkeep`),随使用过程自动填充。

---

## 4. Nginx 反向代理 + HTTPS

### 4.1 配置文件总览

| 文件 | 作用 |
|---|---|
| [deploy/nginx/nginx.conf](../deploy/nginx/nginx.conf) | nginx 主配置:worker、日志、gzip、SSL、限流区、上游 |
| [deploy/nginx/fnixagent.conf](../deploy/nginx/fnixagent.conf) | 站点配置:HTTP→HTTPS 重定向、反向代理、SSE 流式、安全头 |
| `deploy/nginx/certs/fullchain.pem` | SSL 证书链 |
| `deploy/nginx/certs/privkey.pem` | SSL 私钥 |

### 4.2 Let's Encrypt 证书(生产公网)

若已部署 nginx 容器,使用 webroot 方式签发证书:

```bash
# 1. 准备 certbot 验证目录(已由 nginx 配置映射到 /var/www/certbot)
mkdir -p /var/www/certbot

# 2. 临时启动 nginx(或使用已运行实例)
docker compose -f deploy/docker/docker-compose.prod.yml up -d nginx

# 3. 申请证书(替换 your-domain.com 为实际域名)
docker run --rm \
  -v /var/www/certbot:/var/www/certbot \
  -v /etc/letsencrypt:/etc/letsencrypt \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d your-domain.com --email admin@your-domain.com --agree-tos --no-eff-email

# 4. 软链到 nginx 证书目录
ln -sf /etc/letsencrypt/live/your-domain.com/fullchain.pem deploy/nginx/certs/fullchain.pem
ln -sf /etc/letsencrypt/live/your-domain.com/privkey.pem deploy/nginx/certs/privkey.pem

# 5. 重载 nginx
docker compose -f deploy/docker/docker-compose.prod.yml exec nginx nginx -s reload
```

**自动续签**(加入 crontab):

```bash
# 每月 1 号凌晨 3 点检查续签
0 3 1 * * docker run --rm -v /var/www/certbot:/var/www/certbot -v /etc/letsencrypt:/etc/letsencrypt certbot/certbot renew --quiet && docker exec fnixagent-nginx-prod nginx -s reload
```

### 4.3 关键 nginx 配置说明

#### SSE 流式接口不缓冲

```nginx
location ~ ^/api/v1/(chat/stream|chat/evolve)$ {
    proxy_buffering off;        # 关键:关闭缓冲,实时推送
    proxy_cache off;
    proxy_read_timeout 600s;    # 长连接 10 分钟
    chunked_transfer_encoding on;
}
```

#### 限流策略

```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;    # API 全局 10 r/s
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=1r/s;    # 登录 1 r/s(防爆破)
```

#### 安全响应头

```nginx
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Content-Security-Policy "default-src 'self'; ..." always;
```

### 4.4 修改 nginx 配置后重载

```bash
# 测试配置语法
docker compose -f deploy/docker/docker-compose.prod.yml exec nginx nginx -t

# 平滑重载(不断连接)
docker compose -f deploy/docker/docker-compose.prod.yml exec nginx nginx -s reload
```

---

## 5. 桌面客户端连接远程后端

### 5.1 构建桌面客户端

参见 [Phase 1.9 客户端打包](../apps/desktop/electron-builder.yml)。在本机构建:

```bash
cd apps/desktop
pnpm install
pnpm build:win    # 或 build:mac / build:all
```

产物位于 `apps/desktop/dist/`:

- Windows: `fnixagent-Setup-1.0.0.exe`(NSIS 安装包)
- macOS: `fnixagent-1.0.0.dmg`(DMG 镜像)

### 5.2 配置后端地址

桌面客户端通过环境变量 `fnixagent_BACKEND_URL` 指定后端地址,默认 `http://localhost:8000`。

#### 方式 1:安装时指定(推荐)

```bash
# Windows (PowerShell)
$env:fnixagent_BACKEND_URL = "https://your-domain.com"
fnixagent-Setup-1.0.0.exe

# macOS
fnixagent_BACKEND_URL="https://your-domain.com" open fnixagent-1.0.0.dmg
```

#### 方式 2:打包前写入配置

修改 [apps/desktop/src/main/index.ts](../apps/desktop/src/main/index.ts) 第 18 行:

```typescript
const BACKEND_URL = process.env.fnixagent_BACKEND_URL || 'https://your-domain.com';
```

#### 方式 3:用户在登录页手动切换

登录页支持「服务器地址」输入框,允许终端用户填写后端 URL 后再登录(便于多环境切换)。

### 5.3 自动更新

桌面客户端内置 [electron-updater](../apps/desktop/src/main/updater.ts),启动后 10 秒检查 GitHub Releases,每 4 小时复查一次。

**自建更新源**(不走 GitHub):修改 `electron-builder.yml` 的 `publish` 字段:

```yaml
publish:
  - provider: generic
    url: https://your-domain.com/releases/    # 存放 latest.yml + 安装包的目录
```

将 `apps/desktop/dist/` 下的 `latest.yml`、`latest-mac.yml`、`latest-linux.yml` 及安装包上传到该目录即可。

### 5.4 验证客户端全流程

桌面客户端启动后,依次完成:

1. **登录**:输入用户名 / 密码(客户端使用 RSA-OAEP-SHA256 加密传输)
2. **对话**:在 AI 对话面板发送一条消息,验证 SSE 流式回复
3. **文件上传**:在文件树上传一个 .txt / .docx 文件,验证上传成功
4. **自进化**(可选):切换到 Evolve 模式,查看工具调用与概念路径

---

## 6. 部署验证清单

部署完成后,逐项核对:

### 6.1 服务健康

- [ ] `docker compose ps` 所有服务 STATUS 为 `healthy`
- [ ] `curl -k https://localhost/health` 返回 `{"status":"ok"}`
- [ ] `curl -k https://localhost/docs` 能加载 Swagger UI

### 6.2 鉴权流程

- [ ] `POST /api/v1/auth/register` 能注册用户
- [ ] `POST /api/v1/auth/login` 能登录并返回 access_token + refresh_token
- [ ] `GET /api/v1/auth/me` 携带 token 能获取当前用户
- [ ] `POST /api/v1/auth/logout` 后旧 token 失效(401)

### 6.3 业务流程

- [ ] `POST /api/v1/chat/stream` 能收到 NDJSON 流式响应
- [ ] `POST /api/v1/documents/upload` 能上传文件(<50MB)
- [ ] `GET /api/v1/documents/list` 能列出已上传文件
- [ ] `GET /api/v1/chat/topology/stats` 返回拓扑统计

### 6.4 管理后台

> 管理后台前端(`apps/admin`)默认通过 `pnpm dev:admin` 在 5175 端口运行;生产部署时可将其构建产物挂载到 nginx,或单独托管。后端 API 始终可用。

- [ ] `GET /api/v1/admin/users` 能查询用户列表(需 admin 角色 token)
- [ ] 用户管理:能禁用 / 启用 / 重置密码 / 改角色
- [ ] `GET /api/v1/admin/audit-logs` 能按 user_id / action / 时间范围筛选
- [ ] `GET /api/v1/admin/config` 能查看热更新配置;`PATCH` 能修改白名单项

### 6.5 桌面客户端

- [ ] 客户端能连接到远程后端(健康检查通过)
- [ ] 能完成登录 → 对话 → 文件上传全流程
- [ ] 关闭重开客户端,token 仍有效(7 天内)
- [ ] 自动更新检查日志正常(开发模式跳过)

### 6.6 安全性

- [ ] HTTP 自动 301 跳转到 HTTPS
- [ ] 响应头含 HSTS / X-Frame-Options / CSP
- [ ] 登录接口限流生效(连续 5 次失败后锁定 15 分钟)
- [ ] 文件上传超过 50MB 被拒绝
- [ ] 非白名单扩展名上传被拒绝

---

## 7. 运维操作

### 7.1 日常命令

```bash
# 查看实时日志(所有服务)
docker compose -f deploy/docker/docker-compose.prod.yml logs -f

# 查看指定服务日志(最近 200 行)
docker compose -f deploy/docker/docker-compose.prod.yml logs --tail 200 fnixagent

# 重启单个服务
docker compose -f deploy/docker/docker-compose.prod.yml restart fnixagent

# 进入容器
docker compose -f deploy/docker/docker-compose.prod.yml exec fnixagent bash
docker compose -f deploy/docker/docker-compose.prod.yml exec postgres psql -U fnixagent -d fnixagent
```

### 7.2 数据库备份与恢复

```bash
# 备份(每日凌晨 crontab)
docker exec fnixagent-postgres-prod pg_dump -U fnixagent fnixagent | gzip > backup_$(date +%Y%m%d).sql.gz

# 恢复
gunzip -c backup_20260101.sql.gz | docker exec -i fnixagent-postgres-prod psql -U fnixagent -d fnixagent
```

### 7.3 数据卷与升级

```bash
# 查看数据卷
docker volume ls | grep fnixagent

# 升级到新版本
git pull
docker compose -f deploy/docker/docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f deploy/docker/docker-compose.prod.yml exec fnixagent alembic upgrade head
```

### 7.4 Makefile 快捷命令

| 命令 | 作用 |
|---|---|
| `make gen-secrets` | 生成随机密码写入 `.env.prod` |
| `make deploy` | 一键部署(等于 `docker compose up -d --build`) |
| `make deploy-prod` | 生产环境一键部署 |
| `make deploy-ps` | 查看服务状态 |
| `make deploy-logs` | 查看最近日志 |
| `make deploy-down` | 停止并移除容器(保留数据) |
| `make deploy-reset` | 停止并删除所有数据卷(谨慎!) |

---

## 8. 故障排查

### 8.1 服务启动失败

#### 问题:Milvus 一直 unhealthy

**现象**:`docker compose ps` 显示 milvus 为 `unhealthy`,日志含 `connection refused`。

**原因**:Milvus 首次启动需要 60-90 秒做元数据初始化,`start_period: 90s` 内的健康检查失败属正常。

**解决**:

```bash
# 耐心等待 2 分钟后复查
sleep 120 && docker compose -f deploy/docker/docker-compose.prod.yml ps milvus

# 若仍不健康,检查 etcd / minio 是否就绪
docker compose -f deploy/docker/docker-compose.prod.yml logs etcd minio
```

#### 问题:Elasticsearch 启动 OOM

**现象**:ES 日志含 `java.lang.OutOfMemoryError`。

**原因**:`ES_JAVA_OPTS=-Xms2g -Xmx2g` 在 8G 内存机器上过大。

**解决**:编辑 `deploy/docker/docker-compose.prod.yml`,将 ES 内存降到 `1g`:

```yaml
elasticsearch:
  environment:
    - ES_JAVA_OPTS=-Xms1g -Xmx1g
  deploy:
    resources:
      limits:
        memory: 2G
```

#### 问题:fnixagent 容器启动后立即退出

**现象**:`docker compose logs fnixagent` 显示数据库连接失败。

**解决**:确认 PostgreSQL 已 healthy,且 `.env.prod` 中密码与 `DATABASE_URL` 一致:

```bash
# 验证密码
docker exec fnixagent-postgres-prod psql -U fnixagent -d fnixagent -c "SELECT 1;"

# 检查环境变量是否注入
docker compose -f deploy/docker/docker-compose.prod.yml exec fnixagent env | grep DATABASE_URL
```

### 8.2 nginx / HTTPS 问题

#### 问题:浏览器提示证书无效

**原因**:使用了自签证书。

**解决**:

- 开发环境:浏览器手动信任证书,或导入到系统根证书库。
- 生产环境:使用 Let's Encrypt 签发可信证书(见 [§4.2](#42-lets-encrypt-证书生产公网))。

#### 问题:502 Bad Gateway

**原因**:后端 fnixagent 容器未启动或未就绪。

**解决**:

```bash
# 1. 确认后端健康
docker compose -f deploy/docker/docker-compose.prod.yml ps fnixagent

# 2. 直接访问后端验证
docker compose -f deploy/docker/docker-compose.prod.yml exec nginx curl -s http://fnixagent:8000/health

# 3. 若后端正常但仍 502,检查 nginx upstream 配置
docker compose -f deploy/docker/docker-compose.prod.yml exec nginx nginx -t
```

#### 问题:SSE 流式响应被缓冲,客户端看不到实时输出

**原因**:nginx 默认开启 `proxy_buffering`,会缓冲整个响应。

**解决**:确认 `deploy/nginx/fnixagent.conf` 中 `chat/stream` 路径配置了 `proxy_buffering off`(已默认配置)。若修改后仍不生效,重载 nginx:

```bash
docker compose -f deploy/docker/docker-compose.prod.yml exec nginx nginx -s reload
```

### 8.3 鉴权问题

#### 问题:登录返回 401

**排查步骤**:

1. 确认用户名 / 密码正确
2. 确认用户未被禁用(管理后台或 `profile.disabled` 标志)
3. 确认连续失败未触发锁定(5 次失败后锁定 15 分钟)
4. 检查 Redis 是否可用(Token 黑名单依赖 Redis)

```bash
# 检查 Redis
docker exec fnixagent-redis-prod redis-cli -a $REDIS_PASSWORD ping
# 期望: PONG
```

#### 问题:Token 失效后未自动刷新

**原因**:`@fnixagent/sdk` 的 401 拦截器依赖 `refresh_token`,若 refresh_token 也过期(7 天),需重新登录。

**解决**:确认客户端实现了 `installAutoRefreshInterceptor`,且 `refresh_token` 未过期。详见 [packages/sdk/src/auth.ts](../packages/sdk/src/auth.ts)。

### 8.4 文件上传问题

#### 问题:上传返回 413 Request Entity Too Large

**原因**:文件超过 nginx 的 `client_max_body_size 50M` 限制。

**解决**:在 `deploy/nginx/nginx.conf` 调整(注意后端同样有 50MB 限制,需同步修改):

```nginx
client_max_body_size 100M;    # 调整为期望上限
```

#### 问题:上传返回 400 不支持的扩展名

**原因**:文件扩展名不在白名单。

**支持的白名单**:`.txt .md .pdf .docx .doc .xlsx .xls .pptx .ppt .csv .json .yaml .yml .html .png .jpg .jpeg .gif .bmp`。

### 8.5 桌面客户端问题

#### 问题:客户端无法连接后端

**排查**:

1. 在客户端机器上执行 `curl -k https://your-domain.com/health`
2. 确认 `fnixagent_BACKEND_URL` 环境变量正确
3. 确认防火墙允许 443 端口入站
4. 自签证书场景下,客户端机器需信任证书

#### 问题:macOS 客户端提示「无法打开,因为无法验证开发者」

**原因**:未做 Developer ID 签名 + Notarization。

**临时解决**:右键 → 打开(绕过 Gatekeeper)。

**根本解决**:在 CI 中配置 `CSC_NAME` 和 `APPLE_TEAM_ID` 环境变量,详见 [GitHub Actions release.yml](../.github/workflows/release.yml)。

#### 问题:自动更新不工作

**排查**:

1. 确认客户端为打包版本(`app.isPackaged === true`),开发模式跳过更新检查
2. 确认 `electron-builder.yml` 中 `publish.url` 可达
3. 检查 `latest.yml` 中的版本号是否高于当前版本
4. 查看客户端日志:`%APPDATA%/fnixagent/logs/`(Win)或 `~/Library/Logs/fnixagent/`(macOS)

### 8.6 性能问题

#### 问题:对话响应很慢

**排查步骤**:

1. 检查 LLM Provider 响应时间(管理后台审计日志或 `/api/v1/admin/audit-logs`)
2. 确认 LLM 缓存是否生效(`llm.cache.ttl_seconds` > 0)
3. 检查 Milvus 检索延迟(向量化 + 检索)
4. 监控容器资源使用

```bash
docker stats
# 关注 CPU / Memory 是否接近 limit
```

#### 问题:内存占用持续增长

**原因**:短期记忆未及时清理 / LLM 缓存无限增长。

**解决**:

1. 通过管理后台调小 `memory.short_term.max_messages`
2. 设置合理的 `llm.cache.ttl_seconds`(默认 3600 秒)
3. 定期重启 fnixagent 容器(`docker compose restart fnixagent`)

### 8.7 日志位置速查

| 服务 | 日志位置 |
|---|---|
| fnixagent | `docker compose logs fnixagent` 或卷 `app_logs:/app/logs` |
| nginx | `docker compose logs nginx` 或容器内 `/var/log/nginx/` |
| postgres | `docker compose logs postgres` |
| milvus | `docker compose logs milvus` |
| elasticsearch | `docker compose logs elasticsearch` |

---

## 9. 升级与回滚

### 9.1 升级流程

```bash
# 1. 备份数据库
docker exec fnixagent-postgres-prod pg_dump -U fnixagent fnixagent | gzip > backup_pre_upgrade.sql.gz

# 2. 拉取新代码
git pull origin main

# 3. 重新构建并启动
docker compose -f deploy/docker/docker-compose.prod.yml --env-file .env.prod up -d --build

# 4. 执行数据库迁移
docker compose -f deploy/docker/docker-compose.prod.yml exec fnixagent alembic upgrade head

# 5. 验证
curl -k https://localhost/health
```

### 9.2 回滚流程

```bash
# 1. 切回旧版本代码
git checkout <previous-tag>

# 2. 重新构建并启动
docker compose -f deploy/docker/docker-compose.prod.yml --env-file .env.prod up -d --build

# 3. 回滚数据库迁移(谨慎!可能丢数据)
docker compose -f deploy/docker/docker-compose.prod.yml exec fnixagent alembic downgrade -1

# 4. 必要时恢复数据库备份
gunzip -c backup_pre_upgrade.sql.gz | docker exec -i fnixagent-postgres-prod psql -U fnixagent -d fnixagent
```

### 9.3 桌面客户端灰度发布

通过 electron-builder 的 channel 机制实现灰度:

```yaml
# electron-builder.yml
publish:
  - provider: generic
    url: https://your-domain.com/releases/stable/
  - provider: generic
    url: https://your-domain.com/releases/beta/
    channel: beta
```

- 稳定版用户从 `stable/latest.yml` 检查更新
- Beta 用户从 `beta/latest-beta.yml` 检查更新
- 切换 channel:修改客户端 `app-update.yml` 中的 `channel` 字段

---

## 附录:一键部署脚本速查

```bash
# 1. 克隆 + 配置
git clone <repo> fnixagent && cd fnixagent
cp .env.prod.example .env.prod && make gen-secrets

# 2. 生成自签证书(或用 Let's Encrypt)
mkdir -p deploy/nginx/certs
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout deploy/nginx/certs/privkey.pem \
  -out deploy/nginx/certs/fullchain.pem \
  -days 365 -subj "/CN=localhost"

# 3. 一键启动
make deploy-prod

# 4. 初始化数据库
docker compose -f deploy/docker/docker-compose.prod.yml exec fnixagent alembic upgrade head

# 5. 验证
curl -k https://localhost/health
```

完成。整个流程应在 30 分钟内跑通。
