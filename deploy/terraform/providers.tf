# Terraform Provider 配置 — Phase 2.8
#
# 根据 cloud 变量选择 AWS 或阿里云 provider。
# 远程状态后端通过 terraform init -backend-config 注入,详见 environments/*.hcl。

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    alicloud = {
      source  = "aliyun/alicloud"
      version = "~> 1.220"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }

  # 远程状态后端(实际值通过 terraform init -backend-config=environments/<cloud>-backend.hcl 注入)
  # AWS 示例 environments/aws-backend.hcl:
  #   bucket = "fnixagent-tfstate"
  #   key    = "env:/dev/fnixagent.tfstate"
  #   region = "ap-east-1"
  #   dynamodb_table = "fnixagent-tflock"
  backend "s3" {}
}

# AWS Provider
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project = "fnixagent"
      Env     = var.env
      Managed = "terraform"
    }
  }
}

# 阿里云 Provider
provider "alicloud" {
  region = var.alicloud_region

  default_tags {
    tags = {
      Project = "fnixagent"
      Env     = var.env
      Managed = "terraform"
    }
  }
}
