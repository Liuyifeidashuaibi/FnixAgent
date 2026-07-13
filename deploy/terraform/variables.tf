# 输入变量 — Phase 2.8

variable "cloud" {
  description = "云厂商:aws 或 aliyun"
  type        = string
  default     = "aws"

  validation {
    condition     = contains(["aws", "aliyun"], var.cloud)
    error_message = "cloud 只支持 aws 或 aliyun。"
  }
}

variable "env" {
  description = "环境名:dev / staging / prod"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.env)
    error_message = "env 只支持 dev / staging / prod。"
  }
}

variable "project" {
  description = "项目名(资源前缀)"
  type        = string
  default     = "fnixagent"
}

variable "aws_region" {
  description = "AWS 区域"
  type        = string
  default     = "ap-east-1"
}

variable "alicloud_region" {
  description = "阿里云区域"
  type        = string
  default     = "cn-hangzhou"
}

variable "domain" {
  description = "主域名(已在该云厂商的 DNS 服务托管)"
  type        = string
  default     = "fnixagent.com"
}

variable "kubernetes_version" {
  description = "Kubernetes 版本"
  type        = string
  default     = "1.30"
}

variable "database" {
  description = "数据库配置"
  type = object({
    instance_class    = string
    allocated_storage = number
    multi_az          = bool
    backup_retention  = number
  })
  default = {
    instance_class    = "db.t4g.micro"
    allocated_storage = 20
    multi_az          = false
    backup_retention  = 7
  }
}

variable "redis" {
  description = "Redis 配置"
  type = object({
    node_type          = string
    num_cache_nodes    = number
    automatic_failover = bool
  })
  default = {
    node_type          = "cache.t4g.micro"
    num_cache_nodes    = 1
    automatic_failover = false
  }
}

variable "kubernetes" {
  description = "Kubernetes 集群配置"
  type = object({
    node_count    = number
    instance_type = string
    disk_size     = number
  })
  default = {
    node_count    = 2
    instance_type = "t3.medium"
    disk_size     = 50
  }
}

variable "storage" {
  description = "对象存储配置"
  type = object({
    bucket_name = string
    size_gb     = number
  })
  default = {
    bucket_name = "fnixagent-storage"
    size_gb     = 50
  }
}

variable "tags" {
  description = "附加标签"
  type        = map(string)
  default     = {}
}
