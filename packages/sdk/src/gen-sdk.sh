#!/bin/bash
# ===========================================================================
# FnixAgent SDK — 从 FastAPI OpenAPI spec 生成 TypeScript 类型
# Phase P2-01
#
# 用法:
#   bash gen-sdk.sh [base_url]
#
# 参数:
#   base_url  后端服务地址(默认 http://localhost:8000)
#             脚本会从 {base_url}/openapi.json 拉取 schema
#
# 若后端未启动,会自动回退到本地 ../../openapi.json 文件(仓库根目录)
#
# 依赖:
#   npx openapi-typescript(首次运行会自动安装)
#
# 生成产物:
#   src/generated/schema.ts(自动覆盖,勿手动编辑)
# ===========================================================================

set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_FILE="${SCRIPT_DIR}/generated/schema.ts"
LOCAL_SPEC="${SCRIPT_DIR}/../../openapi.json"

echo "▶ FnixAgent SDK 类型生成"
echo "  目标输出: ${OUTPUT_FILE}"

# 确保输出目录存在
mkdir -p "$(dirname "${OUTPUT_FILE}")"

# 优先从远端拉取;失败则回退到本地 openapi.json
if curl -sf "${BASE_URL}/openapi.json" -o /tmp/oa-openapi.json; then
  echo "  数据来源: ${BASE_URL}/openapi.json (远端)"
  npx openapi-typescript /tmp/oa-openapi.json -o "${OUTPUT_FILE}"
else
  if [ -f "${LOCAL_SPEC}" ]; then
    echo "  ⚠ 远端不可达,回退到本地: ${LOCAL_SPEC}"
    npx openapi-typescript "${LOCAL_SPEC}" -o "${OUTPUT_FILE}"
  else
    echo "  ✗ 无法获取 OpenAPI spec:远端 ${BASE_URL}/openapi.json 不可达,且本地 ${LOCAL_SPEC} 不存在"
    exit 1
  fi
fi

echo "✔ 类型生成完成 → ${OUTPUT_FILE}"
