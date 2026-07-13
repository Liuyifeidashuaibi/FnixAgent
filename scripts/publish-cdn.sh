#!/usr/bin/env bash
# OfficeAgent 安装包 CDN 分发脚本 — Phase 1.9
#
# 用途:将 electron-builder 产物(.exe / .dmg / latest*.yml)同步到自建 CDN
#
# 用法:
#   bash scripts/publish-cdn.sh <version> <artifacts_dir>
#
# 环境变量:
#   CDN_RSYNC_HOST  CDN 服务器主机
#   CDN_RSYNC_USER  CDN 登录用户
#   CDN_RSYNC_KEY   SSH 私钥(base64 编码,解码后使用)
#   CDN_REMOTE_PATH 远程目标路径(默认:/var/www/cdn/officeagent/releases)
#
# 产物结构(CDN 端):
#   /var/www/cdn/officeagent/releases/
#     ├── latest.yml              # Windows 更新元数据
#     ├── latest-mac.yml          # macOS 更新元数据
#     ├── OfficeAgent-Setup-1.0.0.exe
#     ├── OfficeAgent-1.0.0-x64.dmg
#     └── OfficeAgent-1.0.0-arm64.dmg

set -euo pipefail

VERSION="${1:?用法: publish-cdn.sh <version> <artifacts_dir>}"
ARTIFACTS_DIR="${2:?缺少 artifacts_dir 参数}"
REMOTE_PATH="${CDN_REMOTE_PATH:-/var/www/cdn/officeagent/releases}"

if [ -z "${CDN_RSYNC_HOST:-}" ] || [ -z "${CDN_RSYNC_USER:-}" ]; then
  echo "⚠️  CDN_RSYNC_HOST / CDN_RSYNC_USER 未设置,跳过 CDN 同步"
  exit 0
fi

echo "=== OfficeAgent CDN 分发 ==="
echo "版本: ${VERSION}"
echo "产物目录: ${ARTIFACTS_DIR}"
echo "目标: ${CDN_RSYNC_USER}@${CDN_RSYNC_HOST}:${REMOTE_PATH}/${VERSION}/"

# 解码 SSH 私钥
KEY_FILE="$(mktemp)"
trap 'rm -f "${KEY_FILE}"' EXIT
if [ -n "${CDN_RSYNC_KEY:-}" ]; then
  echo "${CDN_RSYNC_KEY}" | base64 -d > "${KEY_FILE}"
  chmod 600 "${KEY_FILE}"
  RSYNC_SSH="ssh -i ${KEY_FILE} -o StrictHostKeyChecking=no"
else
  RSYNC_SSH="ssh -o StrictHostKeyChecking=no"
fi

# 创建远程目录
${RSYNC_SSH} "${CDN_RSYNC_USER}@${CDN_RSYNC_HOST}" "mkdir -p ${REMOTE_PATH}/${VERSION} ${REMOTE_PATH}/latest"

# 同步安装包到版本目录
rsync -avz --progress -e "${RSYNC_SSH}" \
  "${ARTIFACTS_DIR}/" \
  "${CDN_RSYNC_USER}@${CDN_RSYNC_HOST}:${REMOTE_PATH}/${VERSION}/"

# 同步 latest*.yml 到 latest 目录(electron-updater 检查更新用)
for f in latest.yml latest-mac.yml latest-linux.yml; do
  if find "${ARTIFACTS_DIR}" -name "${f}" -print -quit | grep -q .; then
    rsync -avz -e "${RSYNC_SSH}" \
      "$(find "${ARTIFACTS_DIR}" -name "${f}" -print -quit)" \
      "${CDN_RSYNC_USER}@${CDN_RSYNC_HOST}:${REMOTE_PATH}/latest/${f}"
    echo "✓ 已更新 ${f}"
  fi
done

echo "=== CDN 分发完成 ==="
echo "下载页: https://cdn.officeagent.com/releases/${VERSION}/"
echo "更新检查: https://cdn.officeagent.com/releases/latest/latest.yml"
