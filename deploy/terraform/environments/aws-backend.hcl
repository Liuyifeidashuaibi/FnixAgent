# AWS 远程状态后端配置 — Phase 2.8
#
# 用法:
#   terraform init -backend-config=environments/aws-backend.hcl
#
# 前置条件:
#   1. 已创建 S3 桶 fnixagent-tfstate(可启用版本化)
#   2. 已创建 DynamoDB 表 fnixagent-tflock(主键 LockID 字符串)
#   3. IAM 权限:s3:PutObject / s3:GetObject / dynamodb:PutItem / dynamodb:GetItem 等
#
# 多环境隔离:不同 env 使用不同 key,状态完全隔离。
#   dev     → env:/dev/fnixagent.tfstate
#   staging → env:/staging/fnixagent.tfstate
#   prod    → env:/prod/fnixagent.tfstate

bucket         = "fnixagent-tfstate"
key            = "env:/dev/fnixagent.tfstate"
region         = "ap-east-1"
dynamodb_table = "fnixagent-tflock"
encrypt        = true
