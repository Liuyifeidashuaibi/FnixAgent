# 根输出 — Phase 2.8
# 统一字段命名,屏蔽 AWS 与 Aliyun 差异,方便后续 CI/CD 或 Helm values 注入。

output "cloud" {
  description = "当前使用的云厂商"
  value       = var.cloud
}

output "env" {
  description = "环境名"
  value       = var.env
}

output "region" {
  description = "当前区域"
  value       = var.cloud == "aws" ? var.aws_region : var.alicloud_region
}

output "vpc_id" {
  description = "VPC ID"
  value       = local.cloud_outputs.vpc_id
}

output "vpc_cidr" {
  description = "VPC CIDR 网段"
  value       = local.cloud_outputs.vpc_cidr
}

output "kubernetes_cluster_name" {
  description = "Kubernetes 集群名称"
  value       = local.cloud_outputs.kubernetes_cluster_name
}

output "kubernetes_cluster_endpoint" {
  description = "Kubernetes API Server endpoint"
  value       = local.cloud_outputs.kubernetes_cluster_endpoint
}

output "kubernetes_ca_data" {
  description = "Kubernetes 集群 CA 证书(base64,用于 kubeconfig 生成)"
  value       = local.cloud_outputs.kubernetes_ca_data
  sensitive   = true
}

output "database_endpoint" {
  description = "RDS 主节点 endpoint(host:port)"
  value       = local.cloud_outputs.database_endpoint
  sensitive   = true
}

output "database_name" {
  description = "数据库名"
  value       = local.cloud_outputs.database_name
}

output "database_username" {
  description = "数据库用户名"
  value       = local.cloud_outputs.database_username
}

output "redis_endpoint" {
  description = "Redis endpoint(host:port)"
  value       = local.cloud_outputs.redis_endpoint
  sensitive   = true
}

output "storage_bucket" {
  description = "对象存储 bucket 名称"
  value       = local.cloud_outputs.storage_bucket
}

output "cdn_domain" {
  description = "CDN 加速域名(若启用)"
  value       = local.cloud_outputs.cdn_domain
}

output "helm_values_file" {
  description = "建议传给 Helm 的 values 文件路径(运行时由脚本渲染,这里仅占位)"
  value       = "deploy/helm/fnixagent/values.${var.env}.yaml"
}
