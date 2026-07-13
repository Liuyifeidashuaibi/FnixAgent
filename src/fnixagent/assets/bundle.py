"""
资产包 (Assets Bundle) 加载与保存。

将自进化 Agent 的全部可迁移资产打包为统一的 AssetsBundle,支持:
    - 拓扑快照 (topology_snapshot)
    - 技能注册表 (skills_registry)
    - 飞轮历史 (flywheel_history)
    - 轨迹归档 (traces_archive)
    - 提示词 (prompts)
    - 版本元信息 (version / created_at)

资产文件布局:
    <path>/
    ├── topology/
    │   └── snapshot.json          KTG 完整快照
    ├── skills/
    │   └── registry.json          技能注册表
    ├── flywheel/
    │   └── history.jsonl          进化历史(每行一条)
    ├── traces/
    │   └── traces.jsonl           执行轨迹归档(每行一条)
    ├── prompts/                   提示词模板目录(每个文件一项)
    │   ├── system.yaml
    │   └── ...
    └── meta/
        └── version.json           版本与创建时间

设计原则:
    - 所有文件使用 UTF-8 编码
    - JSON 序列化使用 ensure_ascii=False
    - SkillRecord 通过 to_dict/from_dict 处理枚举
    - 缺失文件按空值兜底,不抛异常(便于增量迁移)
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from fnixagent.core.types import SkillLevel, SkillRecord


# 资产版本(随 schema 升级递增)
ASSETS_VERSION: str = "1.0.0"


# ---------------------------------------------------------------------------
# SkillRecord 序列化辅助
# ---------------------------------------------------------------------------

def skill_record_to_dict(record: SkillRecord) -> dict[str, Any]:
    """SkillRecord 序列化为 dict(枚举转字符串)。"""
    return {
        "name": record.name,
        "skill_level": record.skill_level.value,
        "bound_concept_id": record.bound_concept_id,
        "priority": record.priority,
        "success_count": record.success_count,
        "failure_count": record.failure_count,
        "last_invoked_at": record.last_invoked_at,
    }


def skill_record_from_dict(d: dict[str, Any]) -> SkillRecord:
    """dict 反序列化为 SkillRecord。"""
    try:
        level = SkillLevel(d.get("skill_level", SkillLevel.BASIC.value))
    except ValueError:
        level = SkillLevel.BASIC
    return SkillRecord(
        name=d["name"],
        skill_level=level,
        bound_concept_id=d.get("bound_concept_id"),
        priority=d.get("priority", 0.5),
        success_count=d.get("success_count", 0),
        failure_count=d.get("failure_count", 0),
        last_invoked_at=d.get("last_invoked_at", 0.0),
    )


# ---------------------------------------------------------------------------
# AssetsBundle 数据类
# ---------------------------------------------------------------------------

@dataclass
class AssetsBundle:
    """资产包:自进化 Agent 的全部可迁移资产。

    Attributes:
        topology_snapshot: KTG 完整快照(nodes + edges + weights)
        skills_registry:   技能注册表(SkillRecord 列表)
        flywheel_history:  进化历史(EvolutionSnapshot 序列化 dict 列表)
        traces_archive:    执行轨迹归档(TraceRecord 序列化 dict 列表)
        prompts:           提示词模板(filename -> content)
        version:           资产 schema 版本
        created_at:        创建时间(Unix 时间戳)
    """
    topology_snapshot: dict[str, Any] = field(default_factory=dict)
    skills_registry: list[SkillRecord] = field(default_factory=list)
    flywheel_history: list[dict[str, Any]] = field(default_factory=list)
    traces_archive: list[dict[str, Any]] = field(default_factory=list)
    prompts: dict[str, str] = field(default_factory=dict)
    version: str = ASSETS_VERSION
    created_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# JSONL 读写辅助
# ---------------------------------------------------------------------------

def _write_jsonl(path: str, records: list[dict[str, Any]]) -> None:
    """写入 JSONL 文件(覆盖写,每行一条 JSON)。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    """读取 JSONL 文件,返回记录列表。"""
    if not os.path.exists(path):
        return []
    records: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def _write_json(path: str, data: Any) -> None:
    """写入 JSON 文件(UTF-8, ensure_ascii=False, 缩进 2)。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _read_json(path: str) -> Any:
    """读取 JSON 文件,不存在返回 None。"""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 资产包保存
# ---------------------------------------------------------------------------

def save_assets(bundle: AssetsBundle, path: str) -> None:
    """保存全部资产到目录。

    Args:
        bundle: 资产包实例
        path:   目标目录(自动创建)
    """
    os.makedirs(path, exist_ok=True)

    # 1. 拓扑快照
    _write_json(
        os.path.join(path, "topology", "snapshot.json"),
        bundle.topology_snapshot,
    )

    # 2. 技能注册表
    _write_json(
        os.path.join(path, "skills", "registry.json"),
        [skill_record_to_dict(r) for r in bundle.skills_registry],
    )

    # 3. 飞轮历史(JSONL)
    _write_jsonl(
        os.path.join(path, "flywheel", "history.jsonl"),
        bundle.flywheel_history,
    )

    # 4. 轨迹归档(JSONL)
    _write_jsonl(
        os.path.join(path, "traces", "traces.jsonl"),
        bundle.traces_archive,
    )

    # 5. 提示词目录(每个 key 一个文件)
    prompts_dir = os.path.join(path, "prompts")
    # 清空旧 prompts 目录后再写入,保证一致性
    if os.path.isdir(prompts_dir):
        for fname in os.listdir(prompts_dir):
            fpath = os.path.join(prompts_dir, fname)
            if os.path.isfile(fpath):
                os.remove(fpath)
    os.makedirs(prompts_dir, exist_ok=True)
    for fname, content in bundle.prompts.items():
        with open(os.path.join(prompts_dir, fname), "w", encoding="utf-8") as f:
            f.write(content)

    # 6. 版本元信息
    _write_json(
        os.path.join(path, "meta", "version.json"),
        {
            "version": bundle.version,
            "created_at": bundle.created_at,
            "saved_at": time.time(),
        },
    )


# ---------------------------------------------------------------------------
# 资产包加载
# ---------------------------------------------------------------------------

def load_assets(path: str) -> AssetsBundle:
    """从目录加载全部资产。

    缺失文件按空值兜底,不抛异常(便于增量迁移)。

    Args:
        path: 资产目录

    Returns:
        AssetsBundle 实例
    """
    # 1. 拓扑快照(缺失返回空 dict)
    topology_snapshot = _read_json(
        os.path.join(path, "topology", "snapshot.json")
    ) or {}

    # 2. 技能注册表(缺失返回空列表)
    skills_data = _read_json(
        os.path.join(path, "skills", "registry.json")
    ) or []
    skills_registry = [skill_record_from_dict(d) for d in skills_data]

    # 3. 飞轮历史(JSONL)
    flywheel_history = _read_jsonl(
        os.path.join(path, "flywheel", "history.jsonl")
    )

    # 4. 轨迹归档(JSONL)
    traces_archive = _read_jsonl(
        os.path.join(path, "traces", "traces.jsonl")
    )

    # 5. 提示词目录
    prompts: dict[str, str] = {}
    prompts_dir = os.path.join(path, "prompts")
    if os.path.isdir(prompts_dir):
        for fname in os.listdir(prompts_dir):
            fpath = os.path.join(prompts_dir, fname)
            if os.path.isfile(fpath):
                with open(fpath, "r", encoding="utf-8") as f:
                    prompts[fname] = f.read()

    # 6. 版本元信息
    meta = _read_json(os.path.join(path, "meta", "version.json")) or {}
    version = meta.get("version", ASSETS_VERSION)
    created_at = meta.get("created_at", time.time())

    return AssetsBundle(
        topology_snapshot=topology_snapshot,
        skills_registry=skills_registry,
        flywheel_history=flywheel_history,
        traces_archive=traces_archive,
        prompts=prompts,
        version=version,
        created_at=created_at,
    )
