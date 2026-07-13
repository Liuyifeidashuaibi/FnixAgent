# OfficeAgent 备份与容灾手册 — Phase 2.9

覆盖 PostgreSQL / Redis / Milvus / MinIO / 应用配置的备份、恢复与容灾演练。

## 文件清单

```
deploy/scripts/
├── backup.sh                # 备份脚本(支持全量 / 增量 / 单组件)
├── restore.sh               # 恢复脚本(支持逻辑恢复 / PITR / dry-run)
├── backup.env.example       # 配置模板(复制为 backup.env 填写真实值)
└── README.md                # 本手册
```

## 备份策略

| 组件        | 全量方式                     | 增量方式              | 频率    | 保留期       |
|-------------|------------------------------|-----------------------|---------|--------------|
| PostgreSQL  | pg_dump (logical) + pg_basebackup (physical) | WAL archive | 每日 03:00 | 本地 7d / 异地 90d |
| Redis       | BGSAVE → RDB                 | AOF(若开启)          | 每日 03:30 | 本地 7d / 异地 90d |
| Milvus      | mc mirror bucket              | 增量 mirror          | 每日 04:00 | 本地 7d / 异地 90d |
| MinIO       | mc mirror bucket              | 增量 mirror          | 每日 04:00 | 本地 7d / 异地 90d |
| 应用配置    | cp config/ + values.yaml      | -                     | 每次发布 | 永久         |

## 快速开始

### 1. 配置环境

```bash
cd deploy/scripts
cp backup.env.example backup.env
vim backup.env  # 填写真实密码 / endpoint
```

### 2. 执行备份

```bash
# 全量备份
./backup.sh

# 仅 PostgreSQL + MinIO(跳过 Redis / 配置)
./backup.sh --component postgres,minio

# 增量备份(仅 WAL + MinIO mirror)
./backup.sh --incremental
```

### 3. 执行恢复

```bash
# 恢复前先 dry-run 确认操作
./restore.sh --backup-dir /data/backups/20260101/20260101_030000 --dry-run

# 全量恢复(交互式确认)
./restore.sh --backup-dir /data/backups/20260101/20260101_030000

# PostgreSQL 时间点恢复(PITR)
./restore.sh --backup-dir <DIR> --component postgres --pitr "2026-01-01 04:30:00+08"
```

## K8s 定时备份

Helm chart 已内置 CronJob(`deploy/helm/officeagent/templates/officeagent-backup-cronjob.yaml`),每日 03:00 自动执行:

```bash
# 安装时启用
helm install officeagent deploy/helm/officeagent \
  -f deploy/helm/officeagent/values.yaml \
  --set backup.enabled=true \
  --set backup.schedule="0 19 * * *" \  # UTC 19:00 = 北京 03:00
  --set backup.storage.size=100Gi
```

CronJob 会:
1. 启动一个携带 backup.sh + mc + postgres-client 的 Pod
2. 通过 PVC 持久化备份文件
3. 同步到异地对象存储(若配置)
4. 失败时通过 Alertmanager 告警

## 恢复演练手册

### 演练目标

- **RTO** (Recovery Time Objective): < 1 小时
- **RPO** (Recovery Point Objective): < 15 分钟

### 演练流程(每月一次,在 staging 环境)

#### Step 1: 准备

```bash
# 在隔离的 staging 环境执行
export KUBECONFIG=/path/to/staging.kubeconfig
kubectl scale deployment officeagent --replicas=0  # 停止写入

# 选择最近一次备份
LATEST_BACKUP=$(ls -1 /data/backups/ | sort | tail -1)
LATEST_DIR=$(ls -1 /data/backups/${LATEST_BACKUP}/ | sort | tail -1)
BACKUP_DIR="/data/backups/${LATEST_BACKUP}/${LATEST_DIR}"
```

#### Step 2: dry-run 验证

```bash
./restore.sh --backup-dir "${BACKUP_DIR}" --dry-run
```

#### Step 3: 实际恢复

```bash
./restore.sh --backup-dir "${BACKUP_DIR}" --force
```

#### Step 4: 验证 RTO

```bash
# 记录开始时间
START=$(date +%s)

# 执行恢复(略)
# ...

# 记录结束时间
END=$(date +%s)
DURATION=$((END - START))
echo "恢复耗时: ${DURATION}s"
# 期望: DURATION < 3600(1 小时)
```

#### Step 5: 业务验证

```bash
# 重启应用
kubectl scale deployment officeagent --replicas=3

# 等待 Pod 就绪
kubectl wait --for=condition=ready pod -l app=officeagent --timeout=300s

# 验证核心功能
curl -f https://staging.officeagent.com/healthz
curl -f -X POST https://staging.officeagent.com/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"test"}'

# 验证数据完整性
kubectl exec -it deploy/officeagent -- \
  python -c "from officeagent.db import get_session; s=get_session(); print(s.execute('SELECT COUNT(*) FROM users').scalar())"
```

#### Step 6: 演练报告

| 项目 | 实际值 | 目标 | 是否达标 |
|---|---|---|---|
| 恢复耗时 (RTO) | ___ | < 1h | ☐ |
| 数据丢失 (RPO) | ___ | < 15min | ☐ |
| 业务功能 | ☐ | 全部通过 | ☐ |
| 数据完整性 | ☐ | 记录数一致 | ☐ |

## 异地容灾

### 跨可用区(ZA)

- **AWS**:RDS Multi-AZ + ElastiCache Multi-AZ(已在 Terraform 配置)
- **阿里云**:RDS 主备高可用 + Redis 主从版(已在 Terraform 配置)
- **K8s**:Pod 反亲和 + 跨 AZ 节点池(已在 Helm values 配置)

### 跨区域(DR)

异地备份同步到对象存储,灾难时通过 restore.sh 拉取并恢复:

```bash
# 配置异地 endpoint(在 backup.env 中)
REMOTE_ENDPOINT=https://s3.ap-east-1.amazonaws.com
REMOTE_BUCKET=officeagent-backup-dr

# 灾难恢复流程:
# 1. 在新区域部署基础设施(terraform apply -var-file=environments/prod.tfvars)
# 2. 从异地对象存储拉取备份
mc mirror --overwrite remote/officeagent-backup-dr/20260101/ /data/backups/20260101/
# 3. 执行恢复
./restore.sh --backup-dir /data/backups/20260101/20260101_030000
# 4. 切换 DNS
```

## 故障排查

### 1. pg_dump 报错 "database is being accessed by other users"

```bash
# 终止所有连接后重试
psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='officeagent' AND pid<>pg_backend_pid();"
./backup.sh --component postgres
```

### 2. Redis BGSAVE 超时

```bash
# 检查 Redis 内存使用
redis-cli -h redis INFO memory | grep used_memory_human

# 若内存 > 50%,触发 fork 可能很慢
# 解决方案:配置 save "" 关闭自动 RDB,改用 AOF + 手动 BGSAVE
```

### 3. MinIO mc mirror 失败

```bash
# 检查 endpoint 连通性
mc admin info local

# 重试(增量同步已实现,断点续传)
./backup.sh --component minio
```

### 4. 异地同步失败

```bash
# 检查异地 endpoint 凭据
mc alias list remote

# 单独执行同步
mc mirror --overwrite /data/backups/<DATE>/ remote/officeagent-backup/<DATE>/
```

## 安全注意事项

1. **backup.env 切勿提交 Git**:已在 .gitignore 中排除
2. **备份文件加密**:对象存储服务端加密已启用(SSE-S3 / OSS-Standard)
3. **异地传输加密**:mc 默认使用 HTTPS
4. **最小权限原则**:备份账户仅授予 PutObject / GetObject,不授予 Delete
5. **审计日志**:备份 / 恢复操作通过 audit.log 记录(action: `data_export` / `data_delete`)
