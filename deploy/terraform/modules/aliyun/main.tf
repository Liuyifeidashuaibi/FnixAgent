# 阿里云模块 — Phase 2.8
#
# 资源清单:
#   - VPC + vSwitch(2 AZ,公/私网交换机 + NAT 网关)
#   - ACK Kubernetes 集群(托管版) + 节点池
#   - RDS PostgreSQL(高可用版可选,自动备份)
#   - Redis 实例(主从版可选,自动故障切换)
#   - OSS Bucket(版本化 + 加密 + 生命周期)
#   - CDN 加速(可选,prod 启用)
#   - KMS Secrets Manager(数据库密码 / 应用密钥)

# ----------------------------------------------------------------------------
# Locals
# ----------------------------------------------------------------------------
locals {
  name_prefix = "${var.project}-${var.env}"

  vpc_cidr = "10.${var.env == "prod" ? 0 : var.env == "staging" ? 16 : 32}.0.0/16"
  vswitch_cidrs = [
    cidrsubnet(local.vpc_cidr, 2, 0),
    cidrsubnet(local.vpc_cidr, 2, 1),
  ]

  # 阿里云可用区(根据 region 选择,这里取 region 默认的前两个 AZ)
  zone_ids = data.alicloud_zones.default.zones[*].id
}

data "alicloud_zones" "default" {
  available_resource_creation = "VSwitch"
}

# ----------------------------------------------------------------------------
# 随机密码
# ----------------------------------------------------------------------------
resource "random_password" "db_password" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "random_password" "redis_auth_token" {
  length  = 64
  special = false
}

# ----------------------------------------------------------------------------
# VPC + vSwitch + NAT
# ----------------------------------------------------------------------------
resource "alicloud_vpc" "main" {
  vpc_name   = "${local.name_prefix}-vpc"
  cidr_block = local.vpc_cidr

  tags = var.tags
}

resource "alicloud_vswitch" "public" {
  count      = length(local.vswitch_cidrs)
  vpc_id     = alicloud_vpc.main.id
  cidr_block = local.vswitch_cidrs[count.index]
  zone_id    = local.zone_ids[count.index]

  vswitch_name = "${local.name_prefix}-public-${count.index}"

  tags = var.tags
}

resource "alicloud_vswitch" "private" {
  count      = length(local.vswitch_cidrs)
  vpc_id     = alicloud_vpc.main.id
  cidr_block = cidrsubnet(local.vpc_cidr, 2, count.index + 2)
  zone_id    = local.zone_ids[count.index]

  vswitch_name = "${local.name_prefix}-private-${count.index}"

  tags = var.tags
}

resource "alicloud_nat_gateway" "main" {
  vpc_id        = alicloud_vpc.main.id
  nat_gateway_name = "${local.name_prefix}-nat"
  payment_type  = "PayAsYouGo"
  vswitch_id    = alicloud_vswitch.public[0].id

  tags = var.tags
}

resource "alicloud_eip" "nat" {
  bandwidth            = 100
  internet_charge_type = "PayByTraffic"
}

resource "alicloud_nat_gateway" "association" {
  count       = 0 # 占位,NAT 关联通过 resource "alicloud_eip_association" 完成
  vpc_id      = alicloud_vpc.main.id
  vswitch_id  = alicloud_vswitch.public[0].id
}

resource "alicloud_eip_association" "nat" {
  allocation_id = alicloud_eip.nat.id
  instance_id   = alicloud_nat_gateway.main.id
}

resource "alicloud_snat_entry" "main" {
  count            = length(alicloud_vswitch.private)
  snat_table_id    = alicloud_nat_gateway.main.snat_table_ids[0]
  source_vswitch_id = alicloud_vswitch.private[count.index].id
  snat_ip          = alicloud_eip.nat.ip_address
}

# ----------------------------------------------------------------------------
# 安全组(数据库 + Redis 共用)
# ----------------------------------------------------------------------------
resource "alicloud_security_group" "main" {
  name        = "${local.name_prefix}-sg"
  description = "FnixAgent security group"
  vpc_id      = alicloud_vpc.main.id

  tags = var.tags
}

resource "alicloud_security_group_rule" "allow_pg" {
  type              = "ingress"
  ip_protocol       = "tcp"
  port_range        = "5432/5432"
  source_cidr_ip    = local.vpc_cidr
  security_group_id = alicloud_security_group.main.id
}

resource "alicloud_security_group_rule" "allow_redis" {
  type              = "ingress"
  ip_protocol       = "tcp"
  port_range        = "6379/6379"
  source_cidr_ip    = local.vpc_cidr
  security_group_id = alicloud_security_group.main.id
}

# ----------------------------------------------------------------------------
# ACK Kubernetes 集群(托管版)
# ----------------------------------------------------------------------------
resource "alicloud_cs_managed_kubernetes" "main" {
  name                         = "${local.name_prefix}-ack"
  cluster_spec                 = var.env == "prod" ? "ack.pro" : "ack.standard"
  version                      = var.kubernetes_version
  worker_vswitch_ids           = alicloud_vswitch.private[*].id
  new_nat_gateway              = false # 已自建 NAT
  pod_cidr                     = "172.20.0.0/16"
  service_cidr                 = "172.21.0.0/20"
  install_cloud_monitor        = true
  is_enterprise_security_group = true

  deletion_protection = var.env == "prod"

  tags = var.tags
}

resource "alicloud_cs_kubernetes_node_pool" "main" {
  cluster_id         = alicloud_cs_managed_kubernetes.main.id
  name               = "${local.name_prefix}-pool"
  vswitch_ids        = alicloud_vswitch.private[*].id
  instance_types     = [var.kubernetes.instance_type]
  desired_size       = var.kubernetes.node_count
  min_size           = var.kubernetes.node_count
  max_size           = var.kubernetes.node_count * 3
  system_disk_size   = var.kubernetes.disk_size
  system_disk_category = "cloud_essd"
  instance_charge_type = var.env == "prod" ? "PostPaid" : "PostPaid"
  spot_strategy      = var.env == "prod" ? "NoSpot" : "SpotAsPriceGo"

  tags = var.tags
}

# ----------------------------------------------------------------------------
# RDS PostgreSQL
# ----------------------------------------------------------------------------
resource "alicloud_db_instance" "main" {
  engine               = "PostgreSQL"
  engine_version       = "16.0"
  instance_type        = var.database.instance_class
  instance_storage     = var.database.allocated_storage
  instance_storage_type = "cloud_essd"

  vswitch_id           = alicloud_vswitch.private[0].id
  security_ips         = [local.vpc_cidr]
  security_group_ids   = [alicloud_security_group.main.id]

  instance_name        = "${local.name_prefix}-pg"
  zone_id_slave_a      = var.database.multi_az ? local.zone_ids[1] : ""
  zone_id              = local.zone_ids[0]
  instance_charge_type = var.env == "prod" ? "PrePaid" : "PostPaid"
  period               = var.env == "prod" ? 12 : 1

  backup_period        = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
  backup_retention_period = var.database.backup_retention
  backup_time          = "03:00Z-04:00Z"
  log_backup           = true
  log_backup_retention_period = var.database.backup_retention * 2

  deletion_protection = var.env == "prod"

  tags = var.tags
}

resource "alicloud_rds_account" "main" {
  db_instance_id   = alicloud_db_instance.main.id
  account_name     = "fnixagent"
  account_password = random_password.db_password.result
  account_type     = "Super"
}

resource "alicloud_rds_database" "main" {
  db_instance_id = alicloud_db_instance.main.id
  db_name        = "fnixagent"
  character_set  = "UTF8"
}

# ----------------------------------------------------------------------------
# Redis 实例
# ----------------------------------------------------------------------------
resource "alicloud_kvstore_instance" "main" {
  instance_class       = var.redis.node_type
  instance_name        = "${local.name_prefix}-redis"
  vswitch_id           = alicloud_vswitch.private[0].id
  security_group_id    = alicloud_security_group.main.id
  zone_id              = local.zone_ids[0]
  instance_type        = var.redis.automatic_failover ? "MasterSlave" : "Standard"
  engine_version       = "7.0"
  instance_charge_type = var.env == "prod" ? "PrePaid" : "PostPaid"
  period               = var.env == "prod" ? 12 : 1

  backup_period  = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
  backup_time    = "04:00Z-05:00Z"
  backup_retention_period = var.env == "prod" ? 7 : 1

  password = random_password.redis_auth_token.result
  config   = "maxmemory-policy allkeys-lru"

  tags = var.tags
}

# ----------------------------------------------------------------------------
# OSS Bucket
# ----------------------------------------------------------------------------
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "alicloud_oss_bucket" "storage" {
  bucket = "${var.storage.bucket_name}-${var.env}-${random_id.bucket_suffix.hex}"
  acl    = "private"

  tags = var.tags
}

resource "alicloud_oss_bucket_versioning" "storage" {
  bucket = alicloud_oss_bucket.storage.bucket
  status = "Enabled"
}

resource "alicloud_oss_bucket_server_side_encryption" "storage" {
  bucket = alicloud_oss_bucket.storage.bucket
  sse_algorithm = "AES256"
}

resource "alicloud_oss_bucket_lifecycle" "storage" {
  bucket = alicloud_oss_bucket.storage.bucket

  rule {
    id      = "transition-to-ia"
    enabled = true

    filter {
      prefix = ""
    }

    transition {
      days          = 30
      storage_class = "IA"
    }

    transition {
      days          = 90
      storage_class = "Archive"
    }

    expiration {
      days = 365
    }

    noncurrent_version_expiration {
      days = 30
    }
  }
}

# ----------------------------------------------------------------------------
# CDN 加速(prod 环境启用)
# ----------------------------------------------------------------------------
resource "alicloud_cdn_domain_new" "main" {
  count         = var.env == "prod" ? 1 : 0
  domain_name   = "cdn.${var.domain}"
  cdn_type      = "web"
  scope         = "overseas"
  sources {
    content  = alicloud_oss_bucket.storage.bucket
    type     = "oss"
    priority = "20"
  }

  tags = var.tags
}

resource "alicloud_cdn_domain_config" "https" {
  count       = var.env == "prod" ? 1 : 0
  domain_name = alicloud_cdn_domain_new.main[0].domain_name
  function_name = "https_option"

  function_args {
    arg_name  = "http2"
    arg_value = "on"
  }
  # 证书通过 aliyun_cas_certificate 关联,实际值由环境变量填入
}

# ----------------------------------------------------------------------------
# KMS Secrets Manager
# ----------------------------------------------------------------------------
resource "alicloud_kms_secret" "db_credentials" {
  secret_name   = "${var.project}/${var.env}/db/credentials"
  description   = "FnixAgent PostgreSQL credentials"
  secret_data   = jsonencode({
    username = "fnixagent"
    password = random_password.db_password.result
    host     = alicloud_db_instance.main.connection_string
    port     = 5432
    dbname   = "fnixagent"
  })
  version_id    = "v1"
  force_delete_without_recovery = var.env != "prod"

  tags = var.tags
}

resource "alicloud_kms_secret" "redis_credentials" {
  secret_name   = "${var.project}/${var.env}/redis/credentials"
  description   = "FnixAgent Redis credentials"
  secret_data   = jsonencode({
    host       = alicloud_kvstore_instance.main.connection_string
    port       = 6379
    auth_token = random_password.redis_auth_token.result
  })
  version_id    = "v1"
  force_delete_without_recovery = var.env != "prod"

  tags = var.tags
}

# ----------------------------------------------------------------------------
# 聚合输出(统一字段命名,屏蔽云厂商差异)
# ----------------------------------------------------------------------------
output "outputs" {
  value = {
    vpc_id                       = alicloud_vpc.main.id
    vpc_cidr                     = alicloud_vpc.main.cidr_block
    kubernetes_cluster_name      = alicloud_cs_managed_kubernetes.main.name
    kubernetes_cluster_endpoint  = alicloud_cs_managed_kubernetes.main.apiserver_internet
    kubernetes_ca_data           = alicloud_cs_managed_kubernetes.main.certificate_authority.0.certificate
    database_endpoint            = "${alicloud_db_instance.main.connection_string}:5432"
    database_name                = "fnixagent"
    database_username            = "fnixagent"
    redis_endpoint               = "${alicloud_kvstore_instance.main.connection_string}:6379"
    storage_bucket               = alicloud_oss_bucket.storage.bucket
    cdn_domain                   = length(alicloud_cdn_domain_new.main) > 0 ? alicloud_cdn_domain_new.main[0].domain_name : ""
    db_credentials_secret_arn    = alicloud_kms_secret.db_credentials.id
    redis_credentials_secret_arn = alicloud_kms_secret.redis_credentials.id
  }
}
