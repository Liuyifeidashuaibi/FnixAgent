# FnixAgent Kubernetes 部署

> 将 FnixAgent agentd 部署到 Kubernetes 集群的标准 manifest。

---

## ⚠️ 重要前提

**FnixAgent 主要是桌面应用**,K8s 部署只适用于:

- ✅ **服务端模式**:`agentd` 单独运行 + 团队 web UI 共享
- ✅ **CI/CD Agent**:在 build runner 上跑 agentd 做自动化
- ❌ **个人用户**应直接装桌面 App,不要 K8s

详见 [`docs/COMPARISON.md`](../../docs/COMPARISON.md)。

---

## 目录

```
deploy/kubernetes/
├── README.md                             ← 本文件
├── fnixagent-namespace.yaml              ← Namespace + PVC + ConfigMap + Secrets + SA + Quota
├── fnixagent-agentd.yaml                 ← Deployment
├── fnixagent-service.yaml                ← Service + Headless Service
├── fnixagent-pdb-hpa-netpol.yaml         ← PDB + HPA + NetworkPolicy
└── fnixagent-ingress.yaml                ← (可选) Ingress
```

---

## 部署步骤

### 1. 前置

- Kubernetes 1.27+
- 集群已装 metrics-server(HPA 需要)
- 已配置 StorageClass(默认 `standard`)
- Helm 3+ (可选,见 `deploy/helm/fnixagent/`)

### 2. 创建 namespace + 资源

```bash
kubectl apply -f deploy/kubernetes/fnixagent-namespace.yaml

# 检查 namespace 已创建并打了安全标签
kubectl get namespace fnixagent --show-labels
# 应看到 pod-security.kubernetes.io/enforce=restricted
```

### 3. 注入 Secrets

**❌ 不要**直接 commit API Key。推荐方式:

#### 方案 A: External Secrets Operator

```yaml
# external-secrets/fnixagent-openai.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: fnixagent-openai
  namespace: fnixagent
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: fnixagent-secrets
  data:
    - secretKey: OPENAI_API_KEY
      remoteRef:
        key: secret/fnixagent/openai
        property: api_key
```

#### 方案 B: Sealed Secrets

```bash
# 1. 安装 kubeseal
brew install kubeseal

# 2. 加密
echo -n "sk-real-key" | kubectl create secret generic -n fnixagent \
  fnixagent-secrets --dry-run=client \
  --from-file=OPENAI_API_KEY=/dev/stdin -o json | \
  kubeseal --format yaml > sealed-secret.yaml

# 3. 提交 sealed-secret.yaml 到 git
git add sealed-secret.yaml
```

#### 方案 C: Workload Identity (GKE)

```yaml
# service-account.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: fnixagent
  namespace: fnixagent
  annotations:
    iam.gke.io/gcp-service-account: fnixagent@PROJECT.iam.gserviceaccount.com
```

### 4. 部署 agentd

```bash
kubectl apply -f deploy/kubernetes/fnixagent-agentd.yaml
kubectl apply -f deploy/kubernetes/fnixagent-service.yaml
kubectl apply -f deploy/kubernetes/fnixagent-pdb-hpa-netpol.yaml
```

### 5. 验证

```bash
# 检查 pod 起来
kubectl -n fnixagent get pods -l app.kubernetes.io/component=agentd

# 等 30s 让 startup probe 通过
sleep 30

# 健康检查
kubectl -n fnixagent port-forward svc/fnixagent-agentd 7891:7891
curl http://localhost:7891/v1/health
# {"status":"ok","version":"0.5.0","uptime_seconds":42}

# 测一个真实请求
curl -X POST http://localhost:7891/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt":"hello","provider":"openai","model":"gpt-4o-mini"}'
```

---

## 安全加固

### Pod Security Standards

`fnixagent-namespace.yaml` 已配置 `restricted` 模式:

- 必须 `runAsNonRoot: true`
- 必须 `seccompProfile: RuntimeDefault`
- 必须 `allowPrivilegeEscalation: false`
- 必须 `capabilities.drop: ALL`
- 必须 `readOnlyRootFilesystem: true`

### NetworkPolicy

`fnixagent-pdb-hpa-netpol.yaml` 默认拒绝所有流量:

- Ingress:仅允许同 namespace + 同 label 的 pod 访问 7891/9090
- Egress:仅允许 DNS (53) + HTTPS (443) + NTP (123)
- **不允许**任意出站,降低数据外泄风险

### PodDisruptionBudget

`minAvailable: 2` — 即使维护时也保证至少 2 个 pod 在线。

### HPA

- 3-10 副本自动伸缩
- CPU 70% / Memory 80% 触发
- scale-up 30秒激进 / scale-down 5分钟稳定

---

## 监控

### Prometheus

`fnixagent-agentd.yaml` 已带 annotations,前提是你部署了 Prometheus Operator:

```yaml
# ServiceMonitor
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: fnixagent
  namespace: fnixagent
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: fnixagent
      app.kubernetes.io/component: agentd
  endpoints:
    - port: metrics
      path: /metrics
      interval: 30s
```

### Grafana Dashboard

`deploy/grafana/fnixagent-dashboard.json` 包含 16 个面板:
- 请求延迟 P50/P95/P99
- Token 消耗速率
- 记忆增长
- Skill 调用频次
- Memory / CPU

---

## 故障排查

### Pod 起不来

```bash
kubectl -n fnixagent describe pod <pod-name>
kubectl -n fnixagent logs <pod-name>
```

常见原因:
- Image pull 失败 → 检查 imagePullSecrets
- PVC 挂载失败 → 检查 StorageClass
- 端口冲突 → 检查 Service 是否已被占用
- Liveness probe 失败 → 健康检查路径是否正确

### HPA 不工作

```bash
kubectl -n fnixagent describe hpa fnixagent-agentd
# metrics-server 必须装:
kubectl top nodes
```

### NetworkPolicy 拒绝合法流量

```bash
# 临时关闭测试
kubectl -n fnixagent delete networkpolicy fnixagent-agentd

# 然后看哪个 pod 连不上
kubectl -n fnixagent logs <pod-name>
```

---

## 升级

### 滚动升级

```bash
# 更新 image tag
kubectl -n fnixagent set image deployment/fnixagent-agentd \
  agentd=ghcr.io/fnixagent/agentd:0.6.0

# 看进度
kubectl -n fnixagent rollout status deployment/fnixagent-agentd

# 失败回滚
kubectl -n fnixagent rollout undo deployment/fnixagent-agentd
```

### 蓝绿部署

参考 [`docs/operations/INCIDENT-RESPONSE.md`](../../docs/operations/INCIDENT-RESPONSE.md)。

---

## Helm

更高级的部署方式(支持 values 覆盖、CI 集成):

```bash
helm install fnixagent deploy/helm/fnixagent/ \
  --namespace fnixagent \
  --create-namespace \
  --values my-values.yaml
```

详见 [`deploy/helm/fnixagent/README.md`](../helm/fnixagent/README.md)。

---

## Terraform (可选)

基础设施即代码版本见 `deploy/terraform/`。

---

© 2024-2026 FnixAgent. All Rights Reserved.