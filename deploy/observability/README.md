# fnixagent 全链路监控运维 — Phase 2.10

Prometheus + Grafana + Alertmanager 监控栈,覆盖业务/系统/应用/安全 4 大维度。

## 文件结构

```
deploy/observability/
├── prometheus.yml                          # Prometheus 抓取配置
├── alertmanager.yml                        # Alertmanager 告警路由
├── docker-compose.monitoring.yml           # 监控栈编排
├── alerts/
│   └── fnixagent-alerts.yml              # 告警规则(15+ 条)
├── dashboards/
│   └── fnixagent-overview.json           # Grafana 大盘(17 个面板)
├── grafana/
│   └── provisioning/
│       ├── datasources/
│       │   └── prometheus.yml              # 数据源自动注入
│       └── dashboards/
│           └── dashboards.yml              # 大盘自动加载
└── README.md                               # 本文档
```

## 快速开始

### 1. Docker Compose 启动(开发/测试)

```bash
# 先启动主应用
docker compose up -d

# 再启动监控栈
docker compose -f deploy/observability/docker-compose.monitoring.yml up -d
```

访问:
- Prometheus: http://localhost:9090
- Alertmanager: http://localhost:9093
- Grafana: http://localhost:3000 (admin/admin)

### 2. Kubernetes 部署(生产)

推荐使用 kube-prometheus-stack Helm chart:

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  --set grafana.adminPassword=CHANGE_ME \
  --set prometheus.prometheusSpec.retention=30d \
  --set prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.storageClassName=gp3 \
  --set prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage=100Gi

# 加载自定义告警规则
kubectl create configmap fnixagent-alerts \
  --from-file=deploy/observability/alerts/fnixagent-alerts.yml \
  -n monitoring
kubectl apply -f - <<EOF
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: fnixagent-alerts
  namespace: monitoring
spec:
  groups:
    $(cat deploy/observability/alerts/fnixagent-alerts.yml | yq -r '.groups')
EOF

# 加载自定义大盘
kubectl create configmap fnixagent-dashboards \
  --from-file=deploy/observability/dashboards/ \
  -n monitoring
```

## 监控维度

### 1. 业务监控
- HTTP QPS / 延迟 / 状态码分布
- 聊天消息 QPS(按 legacy / evolve 模式)
- 用户注册 / 活跃度
- 文档操作 / 任务创建

### 2. 系统监控
- CPU / 内存 / 磁盘 / 网络(Node Exporter)
- HTTP P50/P90/P99 延迟
- 在途请求数
- 5xx 错误率

### 3. 应用监控
- LangGraph 节点耗时 + 执行次数
- 飞轮触发(4 阶段)
- 拓扑图增长(节点 + 边)
- 工具执行(成功率 + 延迟 + 错误)
- LLM 调用(QPS + Token + 延迟 + 错误)

### 4. 安全监控
- 登录尝试(成功 vs 失败,按方法)
- 权限拒绝
- 限流触发
- 注入拦截
- 敏感词命中
- MFA 验证(成功 vs 失败)
- 审计日志写入

## 告警规则

共 15+ 条告警规则,分为 3 级:

| 级别 | 触发条件 | 通知方式 | 响应时间 |
|---|---|---|---|
| critical | 服务宕机 / LLM 错误率 >20% / 注入攻击激增 / 备份失败 | 邮件 + 钉钉 + 电话 | 立即 |
| warning | 5xx >5% / P99 >2s / 登录失败率 >30% / 工具错误率 >10% | 邮件 + 钉钉 | 5min 聚合 |
| info | 注册激增 / 部署完成 | 邮件 | 每日汇总 |

## Prometheus 抓取目标

| Job | 目标 | 指标 |
|---|---|---|
| fnixagent | fnixagent:8000/metrics | 应用全量指标 |
| postgres | postgres-exporter:9187 | 数据库指标 |
| redis | redis-exporter:9121 | 缓存指标 |
| milvus | milvus:9091/metrics | 向量数据库指标 |
| node | node-exporter:9100 | 主机指标 |
| kubernetes-pods | K8s 自动发现 | 带 scrape 注解的 Pod |
| kube-state-metrics | kube-state-metrics:8080 | K8s 集群状态 |

## 验收标准

- [x] Grafana 大盘可查看全链路指标(17 个面板覆盖 4 大维度)
- [x] 告警 5min 内触达 oncall(critical 立即发送,warning 5min 聚合)
- [x] HPA 生效(已在 Helm chart 中配置,基于 CPU/内存利用率)
