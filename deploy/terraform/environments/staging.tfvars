# 预发布环境配置 — Phase 2.8
# 用途:发布前回归测试 + 性能验证,资源中等规模,启用多 AZ 备份。
#
# 应用方式:
#   terraform apply -var-file=environments/staging.tfvars

cloud                = "aws"
env                  = "staging"
project              = "fnixagent"
aws_region           = "ap-east-1"
alicloud_region      = "cn-hangzhou"
domain               = "staging.fnixagent.com"
kubernetes_version   = "1.30"

database = {
  instance_class    = "db.t4g.small"
  allocated_storage = 50
  multi_az          = true
  backup_retention  = 7
}

redis = {
  node_type          = "cache.t4g.small"
  num_cache_nodes    = 2
  automatic_failover = true
}

kubernetes = {
  node_count    = 3
  instance_type = "t3.large"
  disk_size     = 80
}

storage = {
  bucket_name = "fnixagent-staging"
  size_gb     = 100
}

tags = {
  Owner = "platform-team"
}
