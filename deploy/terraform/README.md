# fnixagent Terraform 基础设施 — Phase 2.8

多云支持:AWS + 阿里云,多环境:dev / staging / prod。

## 结构

```
deploy/terraform/
├── main.tf                       # 根模块(根据 cloud 变量实例化 aws 或 aliyun 子模块)
├── variables.tf                  # 输入变量
├── outputs.tf                    # 输出(聚合屏蔽云厂商差异)
├── providers.tf                  # AWS + Aliyun Provider 配置 + 远程状态后端占位
├── modules/
│   ├── aws/                      # AWS 模块
│   │   ├── main.tf               # VPC + EKS + RDS + ElastiCache + S3 + CloudFront + Secrets
│   │   ├── variables.tf
│   │   └── outputs.tf
│   └── aliyun/                   # 阿里云模块
│       ├── main.tf               # VPC + ACK + RDS + Redis + OSS + CDN + KMS
│       ├── variables.tf
│       └── outputs.tf
└── environments/
    ├── dev.tfvars                # 开发环境(最小规格)
    ├── staging.tfvars            # 预发布(中等规模,多 AZ)
    ├── prod.tfvars               # 生产(高可用 + CDN + 长期备份)
    ├── aws-backend.hcl           # AWS S3 + DynamoDB 状态后端
    └── aliyun-backend.hcl        # 阿里云 OSS + TableStore 状态后端
```

## 快速开始

### 1. 选择云厂商

```bash
cd deploy/terraform

# AWS
terraform init -backend-config=environments/aws-backend.hcl

# 阿里云
terraform init -backend-config=environments/aliyun-backend.hcl
```

### 2. 配置凭据

**AWS**:
```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_DEFAULT_REGION="ap-east-1"
```

**阿里云**:
```bash
export ALICLOUD_ACCESS_KEY="..."
export ALICLOUD_SECRET_KEY="..."
export ALICLOUD_REGION="cn-hangzhou"
```

### 3. 规划并应用

```bash
# 预览变更
terraform plan -var-file=environments/dev.tfvars

# 应用
terraform apply -var-file=environments/dev.tfvars

# 销毁(谨慎!)
terraform destroy -var-file=environments/dev.tfvars
```

## 资源清单

### AWS 模块

| 资源 | 类型 | 说明 |
|---|---|---|
| VPC | `aws_vpc` | 3 AZ 高可用 |
| 子网 | `aws_subnet` | public + private 各 3 |
| EKS 集群 | `aws_eks_cluster` | Kubernetes 控制平面 |
| EKS 节点组 | `aws_eks_node_group` | 按需 + Spot 混合 |
| RDS PostgreSQL | `aws_db_instance` | Multi-AZ 高可用 |
| ElastiCache Redis | `aws_elasticache_replication_group` | 主从 + 自动故障转移 |
| S3 存储桶 | `aws_s3_bucket` | 文档/快照存储 |
| CloudFront | `aws_cloudfront_distribution` | CDN 加速 |
| Route53 | `aws_route53_record` | DNS 解析 |
| ACM | `aws_acm_certificate` | TLS 证书 |
| Secrets Manager | `aws_secretsmanager_secret` | 密钥管理 |

### 阿里云模块

| 资源 | 类型 | 说明 |
|---|---|---|
| VPC | `alicloud_vpc` | 多可用区 |
| 交换机 | `alicloud_vswitch` | public + private |
| ACK 集群 | `alicloud_cs_managed_kubernetes` | 托管版 K8s |
| 节点池 | `alicloud_cs_kubernetes_node_pool` | 按量 + 竞价 |
| RDS PostgreSQL | `alicloud_db_instance` | 主备高可用 |
| Redis | `alicloud_kvstore_instance` | 主从 + 哨兵 |
| OSS Bucket | `alicloud_oss_bucket` | 对象存储 |
| CDN | `alicloud_cdn_domain` | CDN 加速 |
| DNS | `alicloud_dns_record` | DNS 解析 |
| SSL 证书 | `alicloud_ssl_certificate` | TLS 证书 |
| KMS | `alicloud_kms_key` | 密钥管理 |

## 多环境隔离

| 环境 | 集群规模 | 数据库 | Redis | S3/OSS | 用途 |
|---|---|---|---|---|---|
| dev | 2 节点 / t3.medium | db.t4g.micro | cache.t4g.micro | 5 GiB | 开发联调 |
| staging | 3 节点 / t3.large | db.t4g.small | cache.t4g.small | 50 GiB | 预发布验证 |
| prod | 5+ 节点 / t3.xlarge | db.r6g.xlarge(Multi-AZ) | cache.r6g.large | 500 GiB | 生产环境 |

## 状态管理

Terraform 状态存储在远程后端,支持状态锁定防止并发写入:

- **AWS**:S3 + DynamoDB(状态文件 + 锁表)
- **阿里云**:OSS + TableStore(状态文件 + 锁表)

首次部署前需手动创建状态后端:

```bash
# AWS(执行一次)
aws s3api create-bucket --bucket fnixagent-tfstate --region ap-east-1
aws dynamodb create-table \
  --table-name fnixagent-tflock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

## 注意事项

1. **凭据安全**:切勿将 `*.tfvars` 中包含真实密钥的文件提交到 Git(已在 .gitignore 中排除 `*secret*.tfvars`)
2. **状态隔离**:每个环境使用独立的 state key(`env:/${env}/fnixagent.tfstate`)
3. **资源命名**:所有资源以 `${project}-${env}-` 前缀命名,避免冲突
4. **标签**:所有资源打上 `Project=fnixagent` `Env=${env}` 标签,便于成本分析
5. **销毁顺序**:`terraform destroy` 时 RDS 会保留快照,需手动清理
