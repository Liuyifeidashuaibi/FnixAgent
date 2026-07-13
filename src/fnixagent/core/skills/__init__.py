"""
技能-拓扑突触协议 (Skill-Topology Synapse Protocol, STP) 模块。

STP 是 KTG 与工具执行平台之间的桥梁,核心思想:
    L2 概念节点  ←binds→  技能(工具)

突触式连接的含义:
    - 拓扑权重高 = 该概念频繁被命中 = 绑定的技能优先级高
    - 技能调用结果反馈权重(成功强化/失败惩罚),形成双向闭环
    - 类似生物突触:用进废退,长期不用则权重衰减

三级权限(对应 ToolMetadata.skill_level):
    - basic:     纯计算/检索,无副作用 → 自动调用
    - reasoning: 调用外部 API/读写文件 → 需用户确认
    - meta:      修改自身(技能/拓扑)  → 默认禁用,需显式授权

子模块(按 Day3 计划):
    - protocol:  突触协议定义(绑定/解绑/权重换算规则)
    - levels:    三级权限策略(自动/确认/禁用判定)
    - scheduler: 技能调度器(基于优先级 + 权限的策略调度)
    - feedback:  反馈处理器(成功/失败 → 权重双向更新)

与 core/tools 的关系:
    STP 不重新实现工具执行,而是基于 ToolExecutor 之上增加调度策略层。
    ToolMetadata 中的 skill_level/topology_binding/priority 字段由 STP 动态维护。

P2-2 新增子模块:
    - market:    组织内技能市场(草稿 → 审核 → 发布 → 弃用 生命周期)
    - install:   技能安装器(把市场技能注册到本地 ToolRegistry)
"""

# P2-2: 技能市场 + 安装器
from fnixagent.core.skills.market import (
    SkillAlreadyExistsError,
    SkillMarket,
    SkillMarketEntry,
    SkillMarketError,
    SkillNotFoundError,
    SkillReviewError,
    SkillStatus,
    SkillStatusError,
    SkillVersion,
    SkillVersionNotFoundError,
)
from fnixagent.core.skills.installer import (
    InstallScope,
    InstallStatus,
    SkillAlreadyInstalledError,
    SkillInstallation,
    SkillInstaller,
    SkillInstallerError,
    SkillNotInstalledError,
    SkillNotPublishedError,
    ToolLoader,
    ToolLoaderError,
)

__all__ = [
    # P2-2: 技能市场
    "SkillMarket",
    "SkillMarketEntry",
    "SkillVersion",
    "SkillStatus",
    "SkillMarketError",
    "SkillNotFoundError",
    "SkillVersionNotFoundError",
    "SkillStatusError",
    "SkillAlreadyExistsError",
    "SkillReviewError",
    # P2-2: 技能安装器
    "SkillInstaller",
    "SkillInstallation",
    "InstallScope",
    "InstallStatus",
    "SkillInstallerError",
    "SkillNotInstalledError",
    "SkillNotPublishedError",
    "SkillAlreadyInstalledError",
    "ToolLoader",
    "ToolLoaderError",
]
