# 阿里云模块输出 — Phase 2.8

output "vpc_id" {
  value = alicloud_vpc.main.id
}

output "vpc_cidr" {
  value = alicloud_vpc.main.cidr_block
}

output "kubernetes_cluster_name" {
  value = alicloud_cs_managed_kubernetes.main.name
}

output "kubernetes_cluster_endpoint" {
  value = alicloud_cs_managed_kubernetes.main.apiserver_internet
}

output "kubernetes_ca_data" {
  value     = alicloud_cs_managed_kubernetes.main.certificate_authority.0.certificate
  sensitive = true
}

output "database_endpoint" {
  value     = "${alicloud_db_instance.main.connection_string}:5432"
  sensitive = true
}

output "database_name" {
  value = "fnixagent"
}

output "database_username" {
  value = "fnixagent"
}

output "redis_endpoint" {
  value     = "${alicloud_kvstore_instance.main.connection_string}:6379"
  sensitive = true
}

output "storage_bucket" {
  value = alicloud_oss_bucket.storage.bucket
}

output "cdn_domain" {
  value = length(alicloud_cdn_domain_new.main) > 0 ? alicloud_cdn_domain_new.main[0].domain_name : ""
}
