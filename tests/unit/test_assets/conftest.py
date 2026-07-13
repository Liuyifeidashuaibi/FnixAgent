"""
资产模块单元测试公共夹具。

提供以下 fixtures:
    - tmp_bundle_dir: 临时资产目录(基于 tmp_path,不污染工作目录)
    - sample_bundle:  含示例数据的 AssetsBundle
    - encryptor:      AssetEncryptor 实例(测试密码)
"""
import os
import sys

# 确保 src 在路径中(与 tests/unit/test_topology/conftest.py 一致)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import pytest

from officeagent.assets.bundle import AssetsBundle
from officeagent.assets.crypto import AssetEncryptor
from officeagent.core.types import SkillLevel, SkillRecord


# ---------------------------------------------------------------------------
# 临时资产目录
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_bundle_dir(tmp_path) -> str:
    """返回一个临时资产目录路径(基于 pytest tmp_path)。"""
    bundle_dir = tmp_path / "assets_bundle"
    bundle_dir.mkdir()
    return str(bundle_dir)


# ---------------------------------------------------------------------------
# 示例资产包
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_bundle() -> AssetsBundle:
    """返回包含示例数据的 AssetsBundle。

    包含:
        - topology_snapshot: 2 节点 + 1 边
        - skills_registry:   2 个技能记录
        - flywheel_history:  2 条进化历史
        - traces_archive:    2 条执行轨迹
        - prompts:           2 个提示词文件
    """
    return AssetsBundle(
        topology_snapshot={
            "nodes": [
                {
                    "node_id": "L1:goal1",
                    "layer": "L1",
                    "node_type": "goal",
                    "name": "撰写论文综述",
                    "weight": 0.5,
                },
                {
                    "node_id": "L2:concept1",
                    "layer": "L2",
                    "node_type": "concept",
                    "name": "文献检索",
                    "weight": 0.6,
                    "skill_binding": "search_skill",
                },
            ],
            "edges": [
                {
                    "edge_id": "e1",
                    "source_id": "L1:goal1",
                    "target_id": "L2:concept1",
                    "edge_type": "contains",
                    "weight": 1.0,
                }
            ],
        },
        skills_registry=[
            SkillRecord(
                name="search_skill",
                skill_level=SkillLevel.BASIC,
                bound_concept_id="L2:concept1",
                priority=0.8,
                success_count=10,
                failure_count=2,
                last_invoked_at=1700000000.0,
            ),
            SkillRecord(
                name="write_skill",
                skill_level=SkillLevel.REASONING,
                bound_concept_id="L2:concept2",
                priority=0.5,
                success_count=5,
                failure_count=1,
                last_invoked_at=1700000100.0,
            ),
        ],
        flywheel_history=[
            {
                "snapshot_id": "snap_001",
                "stage": "hill_climbing",
                "avg_success_rate": 0.85,
                "created_at": 1700000000.0,
            },
            {
                "snapshot_id": "snap_002",
                "stage": "meta_reflection",
                "avg_success_rate": 0.78,
                "created_at": 1700000200.0,
            },
        ],
        traces_archive=[
            {
                "trace_id": "trace_001",
                "task_id": "task_001",
                "goal": "撰写论文综述",
                "mode": "react",
                "success": True,
                "duration_ms": 1500.0,
                "usage_tokens": 1024,
                "created_at": 1700000000.0,
            },
            {
                "trace_id": "trace_002",
                "task_id": "task_002",
                "goal": "翻译文档",
                "mode": "plan_execute",
                "success": False,
                "duration_ms": 3000.0,
                "usage_tokens": 2048,
                "created_at": 1700000300.0,
            },
        ],
        prompts={
            "system.yaml": "You are a helpful assistant.\n",
            "reflection.yaml": "Reflect on the result.\n",
        },
        version="1.0.0",
        created_at=1700000000.0,
    )


# ---------------------------------------------------------------------------
# 加密器
# ---------------------------------------------------------------------------

@pytest.fixture
def encryptor() -> AssetEncryptor:
    """返回使用测试密码的 AssetEncryptor 实例。"""
    return AssetEncryptor("test_password_123")
