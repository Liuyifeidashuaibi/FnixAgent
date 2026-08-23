# AWS 模块 — Phase 2.8
#
# 资源清单:
#   - VPC(2 AZ,公/私网子网 + NAT Gateway)
#   - EKS Kubernetes 集群 + 托管节点组
#   - RDS PostgreSQL(多 AZ 可选,自动备份)
#   - ElastiCache Redis(主从可选,自动故障切换)
#   - S3 存储桶(版本化 + 加密 + 生命周期)
#   - CloudFront CDN(可选,基于 domain 触发)
#   - Secrets Manager(数据库密码 / 应用密钥)
#   - Route53 记录(可选,域名托管时)
#
# 注意:本架构只声明资源,不包含真实证书或敏感数据。
#       所有密钥通过 Secrets Manager 或 terraform.tfvars 注入。

# ----------------------------------------------------------------------------
# Locals
# ----------------------------------------------------------------------------
locals {
  name_prefix = "${var.project}-${var.env}"

  # 网段划分(/16 VPC → /18 公网 ×2 + /18 私网 ×2)
  vpc_cidr = "10.${var.env == "prod" ? 0 : var.env == "staging" ? 16 : 32}.0.0/16"
  public_subnets = [
    cidrsubnet(local.vpc_cidr, 2, 0),
    cidrsubnet(local.vpc_cidr, 2, 1),
  ]
  private_subnets = [
    cidrsubnet(local.vpc_cidr, 2, 2),
    cidrsubnet(local.vpc_cidr, 2, 3),
  ]
  azs = ["${var.region}a", "${var.region}b"]
}

# ----------------------------------------------------------------------------
# 随机密码(数据库 + Redis)
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
# VPC
# ----------------------------------------------------------------------------
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name                 = "${local.name_prefix}-vpc"
  cidr                 = local.vpc_cidr
  azs                  = local.azs
  public_subnets       = local.public_subnets
  private_subnets      = local.private_subnets
  enable_nat_gateway   = true
  single_nat_gateway   = var.env != "prod"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = var.tags
}

# ----------------------------------------------------------------------------
# EKS 集群
# ----------------------------------------------------------------------------
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = "${local.name_prefix}-eks"
  cluster_version = var.kubernetes_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_endpoint_public_access = true
  cluster_endpoint_private_access = true

  enable_irsa = true

  eks_managed_node_groups = {
    main = {
      name           = "${local.name_prefix}-ng"
      instance_types = [var.kubernetes.instance_type]
      min_size       = var.kubernetes.node_count
      max_size       = var.kubernetes.node_count * 3
      desired_size   = var.kubernetes.node_count
      disk_size      = var.kubernetes.disk_size
      capacity_type  = var.env == "prod" ? "ON_DEMAND" : "SPOT"
    }
  }

  tags = var.tags
}

# ----------------------------------------------------------------------------
# RDS PostgreSQL(安全组 + 子网组 + 实例)
# ----------------------------------------------------------------------------
resource "aws_security_group" "rds" {
  name        = "${local.name_prefix}-rds-sg"
  description = "Allow PostgreSQL from VPC"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "PostgreSQL from VPC"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [local.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.tags
}

resource "aws_db_subnet_group" "main" {
  name       = "${local.name_prefix}-db-subnet-group"
  subnet_ids = module.vpc.private_subnets

  tags = var.tags
}

resource "aws_db_instance" "main" {
  identifier = "${local.name_prefix}-pg"

  engine         = "postgres"
  engine_version = "16.2"
  instance_class = var.database.instance_class

  allocated_storage     = var.database.allocated_storage
  max_alloc_storage     = var.database.allocated_storage * 4
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "fnixagent"
  username = "fnixagent"
  password = random_password.db_password.result

  multi_az               = var.database.multi_az
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false

  backup_retention_period = var.database.backup_retention
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:30-sun:05:30"

  deletion_protection      = var.env == "prod"
  skip_final_snapshot      = var.env != "prod"
  final_snapshot_identifier = var.env == "prod" ? "${local.name_prefix}-pg-final" : null

  tags = var.tags
}

# ----------------------------------------------------------------------------
# ElastiCache Redis
# ----------------------------------------------------------------------------
resource "aws_security_group" "redis" {
  name        = "${local.name_prefix}-redis-sg"
  description = "Allow Redis from VPC"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "Redis from VPC"
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = [local.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.tags
}

resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.name_prefix}-redis-subnet-group"
  subnet_ids = module.vpc.private_subnets

  tags = var.tags
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "${local.name_prefix}-redis"
  description          = "FnixAgent Redis cache"

  node_type            = var.redis.node_type
  num_cache_clusters   = var.redis.automatic_failover ? max(2, var.redis.num_cache_nodes) : 1
  automatic_failover_enabled = var.redis.automatic_failover
  multi_az_enabled     = var.redis.automatic_failover && var.env == "prod"

  engine               = "redis"
  engine_version       = "7.1"
  parameter_group_name = "default.redis7"
  port                 = 6379

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = false
  auth_token                 = random_password.redis_auth_token.result

  snapshot_retention_limit = var.env == "prod" ? 7 : 1
  snapshot_window          = "04:00-05:00"

  tags = var.tags
}

# ----------------------------------------------------------------------------
# S3 存储桶(对象存储)
# ----------------------------------------------------------------------------
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "storage" {
  bucket = "${var.storage.bucket_name}-${var.env}-${random_id.bucket_suffix.hex}"

  tags = var.tags
}

resource "aws_s3_bucket_versioning" "storage" {
  bucket = aws_s3_bucket.storage.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "storage" {
  bucket = aws_s3_bucket.storage.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "storage" {
  bucket = aws_s3_bucket.storage.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "storage" {
  bucket = aws_s3_bucket.storage.id

  rule {
    id     = "transition-to-ia"
    status = "Enabled"

    filter {}

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

# ----------------------------------------------------------------------------
# CloudFront CDN(可选,当 domain 已配置时启用)
# ----------------------------------------------------------------------------
resource "aws_cloudfront_distribution" "cdn" {
  count = var.env == "prod" ? 1 : 0

  enabled             = true
  is_ipv6_enabled     = true
  comment             = "FnixAgent ${var.env} CDN"
  default_root_object = "index.html"

  origin {
    domain_name = aws_s3_bucket.storage.bucket_regional_domain_name
    origin_id   = "s3-storage"

    s3_origin_config {
      origin_access_identity = aws_cloudfront_origin_access_identity.main[0].cloudfront_access_identity_path
    }
  }

  default_cache_behavior {
    target_origin_id       = "s3-storage"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]
    compress               = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 3600
    max_ttl     = 86400
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # 证书通过 ACM 注入(架构模板,实际值由环境变量填入)
  viewer_certificate {
    cloudfront_default_certificate = true
    # 生产环境替换为:
    # acm_certificate_arn      = aws_acm_certificate.main[0].arn
    # ssl_support_method       = "sni-only"
    # minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = var.tags
}

resource "aws_cloudfront_origin_access_identity" "main" {
  count = var.env == "prod" ? 1 : 0

  comment = "FnixAgent OAI for S3 access"
}

# ----------------------------------------------------------------------------
# Secrets Manager(存储数据库密码 / Redis Token / 应用密钥)
# ----------------------------------------------------------------------------
resource "aws_secretsmanager_secret" "db_credentials" {
  name        = "/${var.project}/${var.env}/db/credentials"
  description = "FnixAgent PostgreSQL credentials"

  recovery_window_in_days = var.env == "prod" ? 30 : 0

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id

  secret_string = jsonencode({
    username = "fnixagent"
    password = random_password.db_password.result
    host     = aws_db_instance.main.address
    port     = 5432
    dbname   = "fnixagent"
  })
}

resource "aws_secretsmanager_secret" "redis_credentials" {
  name        = "/${var.project}/${var.env}/redis/credentials"
  description = "FnixAgent Redis credentials"

  recovery_window_in_days = var.env == "prod" ? 30 : 0

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "redis_credentials" {
  secret_id = aws_secretsmanager_secret.redis_credentials.id

  secret_string = jsonencode({
    host       = aws_elasticache_replication_group.main.primary_endpoint_address
    port       = 6379
    auth_token = random_password.redis_auth_token.result
  })
}

# ----------------------------------------------------------------------------
# 聚合输出(供根模块通过 module.aws[0].outputs 引用)
# ----------------------------------------------------------------------------
output "outputs" {
  value = {
    vpc_id                       = module.vpc.vpc_id
    vpc_cidr                     = module.vpc.vpc_cidr_block
    kubernetes_cluster_name      = module.eks.cluster_name
    kubernetes_cluster_endpoint  = module.eks.cluster_endpoint
    kubernetes_ca_data           = module.eks.cluster_certificate_authority_data
    database_endpoint            = "${aws_db_instance.main.address}:${aws_db_instance.main.port}"
    database_name                = aws_db_instance.main.db_name
    database_username            = aws_db_instance.main.username
    redis_endpoint               = "${aws_elasticache_replication_group.main.primary_endpoint_address}:6379"
    storage_bucket               = aws_s3_bucket.storage.id
    cdn_domain                   = length(aws_cloudfront_distribution.cdn) > 0 ? aws_cloudfront_distribution.cdn[0].domain_name : ""
    db_credentials_secret_arn    = aws_secretsmanager_secret.db_credentials.id
    redis_credentials_secret_arn = aws_secretsmanager_secret.redis_credentials.id
  }
}
