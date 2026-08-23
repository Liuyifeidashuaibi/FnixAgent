# 生产环境配置 — Phase 2.8
# 用途:对外服务,资源规格按高峰预估,多 AZ + 高可用 + 长期备份 + CDN。
#
# 应用方式:
#   terraform apply -var-file=environments/prod.tfvars
#
# 重要:
#   1. 应用前必须先用 environments/aws-backend.hcl 配置远程状态后端
#   2. 数据库密码 / Redis Token 通过 Secrets Manager 注入,不在此处硬编码
#   3. 域名证书通过 ACM / CAS 上传(架构模板,实际值由运维填入)
#   4. deletion_protection 已开启,删除需手动释放

cloud                = "aws"
env                  = "prod"
project              = "fnixagent"
aws_region           = "ap-east-1"
alicloud_region      = "cn-hangzhou"
domain               = "fnixagent.com"
kubernetes_version   = "1.30"

database = {
  instance_class    = "db.r6g.large"
  allocated_storage = 200
  multi_az          = true
  backup_retention  = 30
}

redis = {
  node_type          = "cache.r6g.large"
  num_cache_nodes    = 3
  automatic_failover = true
}

kubernetes = {
  node_count    = 5
  instance_type = "m5.large"
  disk_size     = 120
}

storage = {
  bucket_name = "fnixagent-prod"
  size_gb     = 500
}

tags = {
  Owner       = "platform-team"
  CostCenter  = "fnixagent-prod"
  Compliance  = "strict"
}
