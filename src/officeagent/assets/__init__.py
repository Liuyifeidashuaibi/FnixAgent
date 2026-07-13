"""
跨平台资产 (Cross-Platform Assets) 模块。

存放自进化 Agent 的可迁移资产,支持在不同环境(本地/云/边缘)间导入导出,
以及加密保护与版本快照管理。

资产类型:
    - topology_snapshot.json:  KTG 完整快照(节点 + 边 + 权重)
    - skills_registry.json:    技能注册表(名称 + 权限 + 绑定 + 优先级)
    - flywheel_history.json:   进化历史(EvolutionSnapshot 序列)
    - trace_archive.jsonl:     执行轨迹归档(TraceRecord 流式日志)
    - prompts/:                提示词模板目录(飞轮 ②③④ 的 LLM 提示)

子模块(按 Day6 计划):
    - serializer:   资产序列化/反序列化(JSON / MessagePack 双格式)
    - encryptor:    资产加密(AES-256-GCM,密钥从环境变量读取)
    - snapshot:     快照管理(创建/恢复/对比差异)
    - migrator:     跨版本迁移(资产 schema 版本升级)

设计原则:
    - 所有资产均可序列化为 JSON,确保跨平台可迁移
    - 敏感资产(含用户数据)必须加密后落盘
    - 快照不可变(immutable),恢复时创建新分支而非覆盖
    - 迁移脚本单向不可逆,每次升级前自动备份
"""
from officeagent.assets.bundle import (
    ASSETS_VERSION,
    AssetsBundle,
    load_assets,
    save_assets,
    skill_record_from_dict,
    skill_record_to_dict,
)
from officeagent.assets.crypto import AssetEncryptor, is_encryption_available
from officeagent.assets.snapshot import SnapshotManager

__all__ = [
    "ASSETS_VERSION",
    "AssetsBundle",
    "AssetEncryptor",
    "SnapshotManager",
    "is_encryption_available",
    "load_assets",
    "save_assets",
    "skill_record_from_dict",
    "skill_record_to_dict",
]
