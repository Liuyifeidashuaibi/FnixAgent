# 开发环境配置 — Phase 2.8
# 用途:本地联调 / 体验 / Demo,资源规格最小化,无多 AZ,无备份保留。
#
# 应用方式:
#   terraform apply -var-file=environments/dev.tfvars

cloud                = "aws"
env                  = "dev"
project              = "fnixagent"
aws_region           = "ap-east-1"
alicloud_region      = "cn-hangzhou"
domain               = "dev.fnixagent.com"
kubernetes_version   = "1.30"

database = {
  instance_class    = "db.t4g.micro"
  allocated_storage = 20
  multi_az          = false
  backup_retention  = 1
}

redis = {
  node_type          = "cache.t4g.micro"
  num_cache_nodes    = 1
  automatic_failover = false
}

kubernetes = {
  node_count    = 1
  instance_type = "t3.medium"
  disk_size     = 30
}

storage = {
  bucket_name = "fnixagent-dev"
  size_gb     = 20
}

tags = {
  Owner = "platform-team"
}
