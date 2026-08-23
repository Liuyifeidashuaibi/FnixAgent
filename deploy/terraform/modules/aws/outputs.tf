# AWS 模块输出 — Phase 2.8
# 单一 outputs 对象,便于根模块通过 module.aws[0].outputs 引用。

output "vpc_id" {
  value = module.vpc.vpc_id
}

output "vpc_cidr" {
  value = module.vpc.vpc_cidr_block
}

output "kubernetes_cluster_name" {
  value = module.eks.cluster_name
}

output "kubernetes_cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "kubernetes_ca_data" {
  value     = module.eks.cluster_certificate_authority_data
  sensitive = true
}

output "database_endpoint" {
  value     = "${aws_db_instance.main.address}:${aws_db_instance.main.port}"
  sensitive = true
}

output "database_name" {
  value = aws_db_instance.main.db_name
}

output "database_username" {
  value = aws_db_instance.main.username
}

output "redis_endpoint" {
  value     = "${aws_elasticache_replication_group.main.primary_endpoint_address}:6379"
  sensitive = true
}

output "storage_bucket" {
  value = aws_s3_bucket.storage.id
}

output "cdn_domain" {
  value = length(aws_cloudfront_distribution.cdn) > 0 ? aws_cloudfront_distribution.cdn[0].domain_name : ""
}
