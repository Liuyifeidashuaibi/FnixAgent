# 阿里云远程状态后端配置 — Phase 2.8
#
# 用法:
#   terraform init -backend-config=environments/aliyun-backend.hcl
#
# 前置条件:
#   1. 已创建 OSS 桶 officeagent-tfstate
#   2. 已开通 TableStore 实例 officeagent-tflock + 表 tfstate(主键 LockID)
#   3. RAM 权限:oss:PutObject / oss:GetObject / ots:* 等
#
# 多环境隔离:不同 env 使用不同 key,状态完全隔离。
#   dev     → env:/dev/officeagent.tfstate
#   staging → env:/staging/officeagent.tfstate
#   prod    → env:/prod/officeagent.tfstate

# 注意:阿里云 OSS backend 复用 S3 协议(terraform 也支持 oss backend,这里用 s3 兼容方式)
bucket         = "officeagent-tfstate"
key            = "env:/dev/officeagent.tfstate"
region         = "cn-hangzhou"
endpoint       = "oss-cn-hangzhou.aliyuncs.com"
encrypt        = true

# TableStore 锁(需通过单独的 backend "oss" + lock_table 配置,详见 README)
# 若使用 alicloud 自带的 oss backend,锁逻辑通过 tablestore 实现
