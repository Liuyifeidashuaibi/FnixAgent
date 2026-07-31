"""
部署形态（Profile）— GitHub 克隆者默认 standalone，无需域名/云服务器。

| Profile       | 轨道 | 说明 |
|---------------|------|------|
| standalone    | Community（默认） | 本机 Python + Desktop，BYOK，无强制账号 |
| local-stack   | 开发 | 本机 Docker（PG + Redis），可选 Milvus |
| cloud         | Enterprise | JWT/RBAC + 远程部署；见 docs/layers/COMMERCIAL.md |

默认 `pnpm dev` / Community 安装包必须保持 standalone，勿把企业依赖塞进默认路径。
"""

from __future__ import annotations

import os
from enum import Enum


class DeployProfile(str, Enum):
    STANDALONE = "standalone"
    LOCAL_STACK = "local-stack"
    CLOUD = "cloud"


def get_profile() -> DeployProfile:
    raw = os.getenv("FNIXAGENT_PROFILE", "standalone").lower().strip()
    mapping = {
        "standalone": DeployProfile.STANDALONE,
        "local": DeployProfile.LOCAL_STACK,
        "local-stack": DeployProfile.LOCAL_STACK,
        "docker": DeployProfile.LOCAL_STACK,
        "cloud": DeployProfile.CLOUD,
        "prod": DeployProfile.CLOUD,
        "production": DeployProfile.CLOUD,
    }
    return mapping.get(raw, DeployProfile.STANDALONE)


def is_standalone() -> bool:
    return get_profile() == DeployProfile.STANDALONE


def is_cloud() -> bool:
    return get_profile() == DeployProfile.CLOUD


def apply_profile_defaults() -> DeployProfile:
    """在未显式设置时注入 profile 级默认环境变量（不覆盖已有值）。"""
    profile = get_profile()

    os.environ.setdefault("FNIXAGENT_MODE", "both")

    if profile == DeployProfile.STANDALONE:
        os.environ.setdefault("SERVICE_ENV", "development")
        os.environ.setdefault("SERVICE_DEBUG", "true")
        os.environ.setdefault("PROMETHEUS_ENABLED", "false")
        os.environ.setdefault("JAEGER_ENABLED", "false")
        os.environ.setdefault("MODERATION_ENABLED", "false")
        # 不设置 DATABASE_URL → storage 层走内存 + JSON 文件
        if "DATABASE_URL" in os.environ and not os.environ.get("DATABASE_URL"):
            del os.environ["DATABASE_URL"]

    elif profile == DeployProfile.LOCAL_STACK:
        os.environ.setdefault("SERVICE_ENV", "development")
        os.environ.setdefault("SERVICE_DEBUG", "true")
        os.environ.setdefault(
            "DATABASE_URL",
            "postgresql+psycopg2://fnixagent:fnixagent-dev@localhost:5432/fnixagent",
        )

    elif profile == DeployProfile.CLOUD:
        os.environ.setdefault("SERVICE_ENV", "production")
        os.environ.setdefault("SERVICE_DEBUG", "false")

    return profile


def profile_info() -> dict:
    """供 /health 与日志使用的 profile 摘要。"""
    p = get_profile()
    return {
        "profile": p.value,
        "label": {
            DeployProfile.STANDALONE: "standalone-beta",
            DeployProfile.LOCAL_STACK: "local-stack-beta",
            DeployProfile.CLOUD: "cloud",
        }.get(p, p.value),
        "storage": "postgresql" if os.getenv("DATABASE_URL") else "local-json",
        "cloud_required": p == DeployProfile.CLOUD,
    }
