# fnixagent Helm Chart

> Phase 2.7 — Kubernetes Helm Charts

部署 fnixagent 到 Kubernetes 集群。

## 快速开始

### 1. 添加 Bitnami 仓库(子 Chart 依赖)

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm dependency update deploy/helm/fnixagent
```

### 2. 创建 secrets.yaml(生产环境必需)

```yaml
# secrets.yaml(不要提交到 Git!)
secret:
  create: true
  values:
    POSTGRES_PASSWORD: "<strong-password>"
    REDIS_PASSWORD: "<strong-password>"
    MINIO_ACCESS_KEY: "<access-key>"
    MINIO_SECRET_KEY: "<secret-key>"
    ES_PASSWORD: "<es-password>"
    JWT_SECRET_KEY: "<strong-random-key>"
    GLM_API_KEY: "<your-api-key>"
    OPENAI_API_KEY: ""
    DEEPSEEK_API_KEY: ""
    QWEN_API_KEY: ""
```

**生产环境推荐使用 Sealed Secrets**:

```bash
# 安装 Sealed Secrets Controller
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.27.3/controller.yaml

# 加密 Secret
echo -n '<strong-password>' | kubectl create secret generic fnixagent-secrets \
  --dry-run=client --from-file=POSTGRES_PASSWORD=/dev/stdin -o yaml | \
  kubeseal --format yaml > fnixagent-sealed.yaml

kubectl apply -f fnixagent-sealed.yaml
```

### 3. 安装 Chart

**开发环境(使用子 Chart 部署 PG/Redis)**:

```bash
helm install fnixagent deploy/helm/fnixagent \
  --set postgres.enabled=true \
  --set redis.enabled=true \
  --set secret.create=false \
  -n fnixagent --create-namespace
```

**生产环境(使用云托管数据库)**:

```bash
helm install fnixagent deploy/helm/fnixagent \
  -f deploy/helm/fnixagent/values.prod.yaml \
  -f secrets.yaml \
  -n fnixagent --create-namespace
```

### 4. 配置说明

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `fnixagent.replicaCount` | 2 | API 副本数 |
| `fnixagent.image.repository` | `ghcr.io/fnixagent/fnixagent` | 镜像仓库 |
| `fnixagent.hpa.enabled` | true | 启用 HPA 自动扩缩容 |
| `fnixagent.hpa.maxReplicas` | 10 | HPA 最大副本数 |
| `fnixagent.persistence.size` | 50Gi | 持久化存储大小 |
| `postgres.enabled` | false | 启用 Bitnami PostgreSQL 子 Chart |
| `redis.enabled` | false | 启用 Bitnami Redis 子 Chart |
| `externalDatabase.enabled` | true | 使用外部数据库 |
| `ingress.enabled` | true | 启用 Ingress |
| `secret.create` | true | 创建 Secret(开发)或使用外部(生产) |

### 5. 升级

```bash
helm upgrade fnixagent deploy/helm/fnixagent \
  -f deploy/helm/fnixagent/values.prod.yaml \
  -f secrets.yaml -n fnixagent
```

### 6. 卸载

```bash
helm uninstall fnixagent -n fnixagent

# 清理 PVC(谨慎操作,会删除数据!)
kubectl -n fnixagent delete pvc -l app.kubernetes.io/instance=fnixagent
```

## 架构

```
                    ┌─────────────┐
                    │   Ingress   │  (nginx + cert-manager + Let's Encrypt)
                    │  443/HTTPS  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Service   │  (ClusterIP)
                    │   :8000     │
                    └──────┬──────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
     ┌──────▼──────┐ ┌────▼────┐ ┌──────▼──────┐
     │  Pod 1      │ │ Pod 2   │ │  Pod N      │  (HPA: 2-20)
     │ fnixagent │ │  ...    │ │  ...        │
     └──────┬──────┘ └────┬────┘ └──────┬──────┘
            │              │              │
            └──────────────┼──────────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌───▼────┐ ┌────▼─────┐
        │ PostgreSQL│ │ Redis  │ │ Milvus   │  (外部托管或子 Chart)
        │  (RDS)    │ │(Elasti)│ │ (独立)    │
        └───────────┘ └────────┘ └──────────┘
```

## 生产环境检查清单

- [ ] `secret.create=false`(使用 Sealed Secrets 或 External Secrets)
- [ ] `externalDatabase.host` 配置为云托管数据库地址
- [ ] `ingress.hosts[0].host` 配置为真实域名
- [ ] DNS 已解析到 Ingress Controller
- [ ] cert-manager 已安装并配置 ClusterIssuer
- [ ] `fnixagent.persistence.storageClass` 设置为高性能存储(gp3/ESSD)
- [ ] 配置 Pod 反亲和(分散到不同节点,见 values.prod.yaml)
- [ ] 配置节点容忍 + nodeSelector(部署到专用节点池)
- [ ] 配置 PodDisruptionBudget(保证最少可用副本)
- [ ] 配置 NetworkPolicy(限制 Pod 间通信)
- [ ] 配置监控告警(Prometheus + Grafana)

## 故障排查

### Pod 启动失败

```bash
kubectl -n fnixagent describe pod -l app.kubernetes.io/instance=fnixagent
kubectl -n fnixagent logs -l app.kubernetes.io/instance=fnixagent --tail=100
```

### 数据库连接失败

检查 Secret 是否正确注入:

```bash
kubectl -n fnixagent exec deploy/fnixagent -- env | grep -E "DATABASE|REDIS|POSTGRES"
```

### Ingress 无法访问

```bash
kubectl -n fnixagent get ingress
kubectl -n ingress-nginx get svc
# 确认 DNS 解析到 LoadBalancer External IP
nslookup api.fnixagent.com
```

## 与 docker-compose 的差异

| 维度 | docker-compose | Helm Chart |
|---|---|---|
| 部署目标 | 单机 | Kubernetes 集群 |
| 副本数 | 1 | 2-20(HPA) |
| 数据库 | 容器内置 | 云托管或子 Chart |
| 反向代理 | nginx 容器 | Ingress Controller |
| TLS | 手动证书 | cert-manager 自动 |
| 持久化 | docker volume | PVC + StorageClass |
| 配置 | .env 文件 | ConfigMap + Secret |
| 升级 | `docker compose pull` | `helm upgrade` |
| 回滚 | 手动 | `helm rollback` |
