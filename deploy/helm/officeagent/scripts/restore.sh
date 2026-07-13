#!/usr/bin/env bash
# OfficeAgent 恢复脚本 — Phase 2.9
#
# 覆盖组件:
#   1. PostgreSQL  — 从 pg_dump 逻辑恢复 / 从 pg_basebackup + WAL 做 PITR
#   2. Redis       — 从 RDB 文件恢复(停止 Redis → 替换 dump.rdb → 启动)
#   3. Milvus     — 从 MinIO 备份恢复(还原 bucket)
#   4. MinIO       — mc mirror 反向同步
#   5. 应用配置    — 还原 config/ + .env.prod
#
# 用法:
#   ./restore.sh --backup-dir /data/backups/20260101/20260101_030000
#   ./restore.sh --backup-dir <DIR> --component postgres
#   ./restore.sh --backup-dir <DIR> --pitr "2026-01-01 04:30:00+08"
#
# 退出码:
#   0  成功
#   1  参数错误
#   2  依赖缺失
#   3  恢复失败
#
# 重要:
#   - 恢复操作具有破坏性,执行前请确认目标环境数据已隔离或废弃
#   - PostgreSQL PITR 恢复需先停库,再加 recovery 配置启动
#   - 恢复演练务必在隔离环境(dev/staging)进行,严禁直接在生产试错

set -Eeuo pipefail

# ============================================================================
# 全局变量
# ============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKUP_ENV_FILE="${BACKUP_ENV_FILE:-${SCRIPT_DIR}/backup.env}"

BACKUP_DIR=""
COMPONENTS=("postgres" "redis" "minio" "config")
PITR_TARGET=""
FORCE=false
DRY_RUN=false

# 加载默认值
if [[ -f "${BACKUP_ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "${BACKUP_ENV_FILE}"
  set +a
fi

# 数据库
PG_HOST="${PG_HOST:-postgres}"
PG_PORT="${PG_PORT:-5432}"
PG_USER="${PG_USER:-officeagent}"
PG_DB="${PG_DB:-officeagent}"
PG_PASSWORD="${PG_PASSWORD:-}"
PG_DATA_DIR="${PG_DATA_DIR:-/var/lib/postgresql/data}"

# Redis
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
REDIS_DATA_DIR="${REDIS_DATA_DIR:-/data}"

# MinIO
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://minio:9000}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-}"
MILVUS_BUCKET="${MILVUS_BUCKET:-milvus}"
APP_BUCKET="${APP_BUCKET:-officeagent}"

# ============================================================================
# 工具函数
# ============================================================================
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE:-/dev/stderr}"
}

err() {
  echo "[ERROR][$(date '+%Y-%m-%d %H:%M:%S')] $*" >&2
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { err "缺少依赖命令: $1"; exit 2; }
}

# ============================================================================
# 参数解析
# ============================================================================
parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --backup-dir)
        BACKUP_DIR="$2"
        shift 2
        ;;
      --component)
        IFS=',' read -ra COMPONENTS <<< "$2"
        shift 2
        ;;
      --pitr)
        PITR_TARGET="$2"
        shift 2
        ;;
      --force)
        FORCE=true
        shift
        ;;
      --dry-run)
        DRY_RUN=true
        shift
        ;;
      --help|-h)
        cat <<EOF
Usage: restore.sh --backup-dir <DIR> [OPTIONS]

Options:
  --backup-dir DIR     备份目录(必填,如 /data/backups/20260101/20260101_030000)
  --component LIST     仅恢复指定组件(逗号分隔:postgres,redis,minio,config)
  --pitr "TIMESTAMP"   PostgreSQL 时间点恢复(如 "2026-01-01 04:30:00+08")
  --force              跳过二次确认(危险!仅恢复演练时使用)
  --dry-run            只打印将执行的操作,不实际执行

Examples:
  # 全量恢复
  ./restore.sh --backup-dir /data/backups/20260101/20260101_030000

  # 仅恢复 PostgreSQL 到指定时间点
  ./restore.sh --backup-dir <DIR> --component postgres --pitr "2026-01-01 04:30:00+08"

  # 恢复演练(dry-run)
  ./restore.sh --backup-dir <DIR> --dry-run
EOF
        exit 0
        ;;
      *)
        err "未知参数: $1"
        exit 1
        ;;
    esac
  done

  if [[ -z "${BACKUP_DIR}" ]]; then
    err "缺少必填参数 --backup-dir"
    exit 1
  fi

  if [[ ! -d "${BACKUP_DIR}" ]]; then
    err "备份目录不存在: ${BACKUP_DIR}"
    exit 1
  fi
}

# ============================================================================
# 二次确认
# ============================================================================
confirm() {
  if [[ "${FORCE}" == "true" ]]; then
    return 0
  fi

  echo "============================================================"
  echo "警告! 恢复操作将覆盖目标环境的以下数据:"
  echo "  备份目录: ${BACKUP_DIR}"
  echo "  恢复组件: ${COMPONENTS[*]}"
  [[ -n "${PITR_TARGET}" ]] && echo "  PITR 目标: ${PITR_TARGET}"
  echo "  目标:"
  echo "    PostgreSQL: ${PG_HOST}:${PG_PORT}/${PG_DB}"
  echo "    Redis:      ${REDIS_HOST}:${REDIS_PORT}"
  echo "    MinIO:      ${MINIO_ENDPOINT}"
  echo "============================================================"
  read -p "确认执行恢复?(yes/no): " reply
  [[ "${reply}" == "yes" ]] || { log "用户取消"; exit 0; }
}

# ============================================================================
# PostgreSQL 恢复
# ============================================================================
restore_postgres() {
  log "[1/$((${#COMPONENTS[@]}))] PostgreSQL 恢复开始"

  require_cmd psql
  require_cmd pg_restore

  local pg_dir="${BACKUP_DIR}/postgres"
  if [[ ! -d "${pg_dir}" ]]; then
    err "备份目录缺少 postgres 子目录: ${pg_dir}"
    return 1
  fi

  export PGPASSWORD="${PG_PASSWORD}"

  # 模式 A:时间点恢复(PITR) — 需 basebackup + WAL
  if [[ -n "${PITR_TARGET}" ]]; then
    log "  - PITR 模式,目标时间: ${PITR_TARGET}"

    if [[ ! -d "${pg_dir}/basebackup" ]]; then
      err "PITR 需要 basebackup 目录,但未找到: ${pg_dir}/basebackup"
      return 1
    fi

    if [[ "${DRY_RUN}" == "true" ]]; then
      log "  [DRY-RUN] 将停止 PostgreSQL,替换 ${PG_DATA_DIR},添加 recovery 配置,启动并恢复到 ${PITR_TARGET}"
      return 0
    fi

    # 实际 PITR 流程(需要在 PostgreSQL 主机上以 postgres 用户执行)
    log "  - 停止 PostgreSQL..."
    pg_ctlcluster stop main 2>/dev/null || systemctl stop postgresql 2>/dev/null || true

    log "  - 清理现有 PG_DATA_DIR: ${PG_DATA_DIR}"
    rm -rf "${PG_DATA_DIR:?}"/*
    mkdir -p "${PG_DATA_DIR}"

    log "  - 解压 basebackup..."
    tar -xzf "${pg_dir}/basebackup/base.tar.gz" -C "${PG_DATA_DIR}"
    [[ -f "${pg_dir}/basebackup/pg_wal.tar.gz" ]] && \
      tar -xzf "${pg_dir}/basebackup/pg_wal.tar.gz" -C "${PG_DATA_DIR}/pg_wal"

    # 配置 recovery
    cat > "${PG_DATA_DIR}/recovery.signal" <<EOF
EOF

    cat > "${PG_DATA_DIR}/postgresql.auto.conf" <<EOF
restore_command = 'cp ${pg_dir}/wal/%f %p'
recovery_target_time = '${PITR_TARGET}'
recovery_target_action = 'promote'
EOF

    log "  - 启动 PostgreSQL(进入恢复模式)..."
    pg_ctlcluster start main 2>/dev/null || systemctl start postgresql 2>/dev/null || true

    log "  - 等待恢复完成..."
    for i in $(seq 1 60); do
      if psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d postgres -tAc \
        "SELECT pg_is_in_recovery()" 2>/dev/null | grep -q "^f$"; then
        log "  - 恢复完成,Promote 成功"
        break
      fi
      sleep 5
    done

    return 0
  fi

  # 模式 B:逻辑恢复(pg_restore)— 适合跨版本 / 跨架构恢复
  local dump_file="${pg_dir}/${PG_DB}_full.dump"
  if [[ ! -f "${dump_file}" ]]; then
    err "未找到 pg_dump 文件: ${dump_file}"
    return 1
  fi

  if [[ "${DRY_RUN}" == "true" ]]; then
    log "  [DRY-RUN] 将执行 pg_restore --dbname=${PG_DB} --clean --if-exists ${dump_file}"
    return 0
  fi

  log "  - 重建数据库(干净恢复)..."
  psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d postgres <<EOF
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${PG_DB}' AND pid<>pg_backend_pid();
DROP DATABASE IF EXISTS ${PG_DB};
CREATE DATABASE ${PG_DB} OWNER ${PG_USER};
EOF

  log "  - pg_restore 逻辑恢复..."
  if ! pg_restore \
      --host="${PG_HOST}" \
      --port="${PG_PORT}" \
      --username="${PG_USER}" \
      --dbname="${PG_DB}" \
      --clean \
      --if-exists \
      --no-owner \
      --no-privileges \
      --jobs="${PARALLEL_JOBS:-4}" \
      "${dump_file}"; then
    err "pg_restore 失败(部分对象可能已恢复,请检查日志)"
    return 1
  fi

  # 验证记录数
  local record_count
  record_count=$(psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${PG_DB}" -tAc \
    "SELECT COUNT(*) FROM users" 2>/dev/null || echo 0)
  log "  - users 表记录数: ${record_count}"

  log "  - PostgreSQL 恢复完成"
}

# ============================================================================
# Redis 恢复
# ============================================================================
restore_redis() {
  log "[2/$((${#COMPONENTS[@]}))] Redis 恢复开始"

  require_cmd redis-cli

  local redis_dir="${BACKUP_DIR}/redis"
  if [[ ! -d "${redis_dir}" ]]; then
    err "备份目录缺少 redis 子目录: ${redis_dir}"
    return 1
  fi

  if [[ "${DRY_RUN}" == "true" ]]; then
    log "  [DRY-RUN] 将停止 Redis,替换 dump.rdb,启动 Redis"
    return 0
  fi

  # Redis 恢复流程:
  # 1. SHUTDOWN NOSAVE 停止 Redis
  # 2. 替换 REDIS_DATA_DIR/dump.rdb
  # 3. 启动 Redis(自动加载 dump.rdb)
  # 注意:此操作需要在 Redis 主机上执行,本脚本通过 kubectl/docker exec 间接操作
  log "  - 停止 Redis(SHUTDOWN NOSAVE)..."
  redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" SHUTDOWN NOSAVE 2>/dev/null || true

  # 假设备份 RDB 文件已通过共享卷或 mc cp 拷贝到 REDIS_DATA_DIR/restore.rdb
  if [[ -f "${redis_dir}/dump.rdb" ]]; then
    log "  - 替换 dump.rdb..."
    cp "${redis_dir}/dump.rdb" "${REDIS_DATA_DIR}/dump.rdb"
    chmod 644 "${REDIS_DATA_DIR}/dump.rdb"
  else
    log "  - 未找到 dump.rdb 文件,可能需要从 MinIO 备份中拉取"
    # 在 K8s 环境下:
    # kubectl cp <pod>:/data/dump.rdb ${redis_dir}/dump.rdb
  fi

  log "  - 启动 Redis..."
  # 在 K8s 环境下,Pod 会自动重启;在裸机环境下需手动启动
  # systemctl start redis 2>/dev/null || docker start officeagent-redis 2>/dev/null || true

  sleep 3

  # 验证连接
  if redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" PING | grep -q PONG; then
    log "  - Redis 已恢复并响应"
  else
    err "Redis 启动后无响应"
    return 1
  fi

  log "  - Redis 恢复完成"
}

# ============================================================================
# MinIO / Milvus 恢复
# ============================================================================
restore_minio() {
  log "[3/$((${#COMPONENTS[@]}))] MinIO + Milvus 恢复开始"

  require_cmd mc

  local minio_dir="${BACKUP_DIR}/minio"
  if [[ ! -d "${minio_dir}" ]]; then
    err "备份目录缺少 minio 子目录: ${minio_dir}"
    return 1
  fi

  if [[ "${DRY_RUN}" == "true" ]]; then
    log "  [DRY-RUN] 将反向 mirror ${minio_dir} → ${MINIO_ENDPOINT}"
    return 0
  fi

  mc alias set local "${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" --api S3v4 >/dev/null

  # 恢复 Milvus bucket
  if [[ -d "${minio_dir}/${MILVUS_BUCKET}" ]]; then
    log "  - 恢复 Milvus bucket: ${MILVUS_BUCKET}"
    mc mirror --overwrite --quiet "${minio_dir}/${MILVUS_BUCKET}/" "local/${MILVUS_BUCKET}"
  fi

  # 恢复应用 bucket
  if [[ -d "${minio_dir}/${APP_BUCKET}" ]]; then
    log "  - 恢复应用 bucket: ${APP_BUCKET}"
    mc mirror --overwrite --quiet "${minio_dir}/${APP_BUCKET}/" "local/${APP_BUCKET}"
  fi

  log "  - MinIO + Milvus 恢复完成"
}

# ============================================================================
# 应用配置恢复
# ============================================================================
restore_config() {
  log "[4/$((${#COMPONENTS[@]}))] 应用配置恢复开始"

  local cfg_dir="${BACKUP_DIR}/config"
  if [[ ! -d "${cfg_dir}" ]]; then
    err "备份目录缺少 config 子目录: ${cfg_dir}"
    return 1
  fi

  if [[ "${DRY_RUN}" == "true" ]]; then
    log "  [DRY-RUN] 将还原 config/ 目录到 ${PROJECT_ROOT}"
    return 0
  fi

  if [[ -d "${cfg_dir}/config" ]]; then
    log "  - 还原 config/ 目录"
    rm -rf "${PROJECT_ROOT}/config.bak"
    [[ -d "${PROJECT_ROOT}/config" ]] && mv "${PROJECT_ROOT}/config" "${PROJECT_ROOT}/config.bak"
    cp -r "${cfg_dir}/config" "${PROJECT_ROOT}/config"
  fi

  if [[ -f "${cfg_dir}/values.yaml" ]]; then
    log "  - 还原 Helm values.yaml"
    cp "${cfg_dir}/values.yaml" "${PROJECT_ROOT}/deploy/helm/officeagent/values.yaml"
  fi
  [[ -f "${cfg_dir}/values.prod.yaml" ]] && \
    cp "${cfg_dir}/values.prod.yaml" "${PROJECT_ROOT}/deploy/helm/officeagent/values.prod.yaml"

  log "  - 应用配置恢复完成(注意: .env.prod 需要手动从密码管理器恢复真实值)"
}

# ============================================================================
# 主流程
# ============================================================================
main() {
  parse_args "$@"

  LOG_FILE="${BACKUP_DIR}/restore_$(date +%Y%m%d_%H%M%S).log"

  log "============================================================"
  log "OfficeAgent 恢复开始"
  log "  备份目录: ${BACKUP_DIR}"
  log "  恢复组件: ${COMPONENTS[*]}"
  [[ -n "${PITR_TARGET}" ]] && log "  PITR 目标: ${PITR_TARGET}"
  log "  DRY_RUN:  ${DRY_RUN}"
  log "============================================================"

  if [[ "${DRY_RUN}" != "true" ]]; then
    confirm
  fi

  local overall_status=0

  for comp in "${COMPONENTS[@]}"; do
    case "$comp" in
      postgres) restore_postgres || overall_status=3 ;;
      redis)    restore_redis    || overall_status=3 ;;
      minio)    restore_minio    || overall_status=3 ;;
      config)   restore_config   || overall_status=3 ;;
      *) err "未知组件: ${comp}"; exit 1 ;;
    esac
  done

  log "============================================================"
  log "OfficeAgent 恢复结束"
  log "  状态: $([[ ${overall_status} -eq 0 ]] && echo 成功 || echo 部分失败)"
  log "  日志: ${LOG_FILE}"
  log "============================================================"

  if [[ ${overall_status} -eq 0 ]]; then
    log "后续步骤:"
    log "  1. 重启应用服务(让应用重新加载配置 / 连接数据库)"
    log "  2. 验证业务功能(用户登录 / 文件上传 / Agent 调用)"
    log "  3. 通知运维团队确认恢复完成"
  fi

  exit ${overall_status}
}

main "$@"
