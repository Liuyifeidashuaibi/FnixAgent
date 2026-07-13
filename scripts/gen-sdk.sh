#!/usr/bin/env bash
# OfficeAgent OpenAPI SDK 自动生成脚本
# 用法: pnpm gen:api
# 依赖: 后端在 localhost:8000 运行

set -euo pipefail

API_URL="${API_URL:-http://localhost:8000/openapi.json}"
OUTPUT="packages/sdk/src/generated/schema.ts"

echo "🔄 从 $API_URL 生成 TypeScript 类型..."
mkdir -p "$(dirname "$OUTPUT")"
npx openapi-typescript "$API_URL" -o "$OUTPUT"
echo "✅ 已生成 $OUTPUT"
echo "💡 前端调用任意端点现在都有类型提示"
