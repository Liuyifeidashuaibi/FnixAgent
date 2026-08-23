# 根模块 — Phase 2.8
#
# 根据 var.cloud 条件实例化 AWS 或 Aliyun 子模块。
# 子模块输出统一通过 local.cloud_outputs 暴露,便于 outputs.tf 聚合。
#
# 用法:
#   terraform init -backend-config=environments/aws-backend.hcl
#   terraform apply -var-file=environments/dev.tfvars

locals {
  common_tags = merge(var.tags, {
    Project = var.project
    Env     = var.env
  })
}

# ----------------------------------------------------------------------------
# AWS 模块
# ----------------------------------------------------------------------------
module "aws" {
  source = "./modules/aws"
  count  = var.cloud == "aws" ? 1 : 0

  project            = var.project
  env                = var.env
  region             = var.aws_region
  domain             = var.domain
  kubernetes_version = var.kubernetes_version
  database           = var.database
  redis              = var.redis
  kubernetes         = var.kubernetes
  storage            = var.storage
  tags               = local.common_tags
}

# ----------------------------------------------------------------------------
# 阿里云模块
# ----------------------------------------------------------------------------
module "aliyun" {
  source = "./modules/aliyun"
  count  = var.cloud == "aliyun" ? 1 : 0

  project            = var.project
  env                = var.env
  region             = var.alicloud_region
  domain             = var.domain
  kubernetes_version = var.kubernetes_version
  database           = var.database
  redis              = var.redis
  kubernetes         = var.kubernetes
  storage            = var.storage
  tags               = local.common_tags
}

# ----------------------------------------------------------------------------
# 聚合输出(根据 cloud 选择活跃模块的输出)
# ----------------------------------------------------------------------------
locals {
  cloud_outputs = var.cloud == "aws" ? module.aws[0].outputs : module.aliyun[0].outputs
}
