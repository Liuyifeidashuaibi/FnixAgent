# AWS 模块变量 — Phase 2.8

variable "project" {
  type = string
}

variable "env" {
  type = string
}

variable "region" {
  type = string
}

variable "domain" {
  type = string
}

variable "kubernetes_version" {
  type = string
}

variable "database" {
  type = object({
    instance_class    = string
    allocated_storage = number
    multi_az          = bool
    backup_retention  = number
  })
}

variable "redis" {
  type = object({
    node_type          = string
    num_cache_nodes    = number
    automatic_failover = bool
  })
}

variable "kubernetes" {
  type = object({
    node_count    = number
    instance_type = string
    disk_size     = number
  })
}

variable "storage" {
  type = object({
    bucket_name = string
    size_gb     = number
  })
}

variable "tags" {
  type    = map(string)
  default = {}
}
