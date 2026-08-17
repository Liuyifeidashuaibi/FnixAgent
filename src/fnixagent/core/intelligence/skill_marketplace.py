"""
FnixAgent ∞ 技能市场 (Skill Marketplace) — Layer 6

设计思路:
  - 自动技能创建: 对话中自动创建技能, 46% token减少
  - Evolver/EvoMap GEP: Genome Evolution Protocol, 标准基因胶囊, 审计轨迹
  - GenericAgent (Fudan): 技能树结晶, 6x token减少
  - 主动知识持久化 → 技能创建, 通才技能包
  - DeerFlow 2.0: 技能市场插件生态
  - 技能市场: 技能发现与分发

核心思想:
  ┌─────────────────────────────────────────────────────────────────┐
  │                      Skill Lifecycle                            │
  ├─────────────────────────────────────────────────────────────────┤
  │  DETECT → CREATE → VALIDATE → VERSION → PUBLISH → EVOLVE        │
  │  │         │         │          │         │          │           │
  │  │  检测到   │  从经验   │  沙箱    │  基因    │  技能    │  遗传优化   │
  │  │  可复用   │  中提取   │  验证    │  版本    │  市场    │  进化   │
  │  │  模式    │  技能    │  安全    │  控制    │  分发    │  优化   │
  │  └─────────┴─────────┴─────────┴─────────┴─────────┴─────────┘  │
  └─────────────────────────────────────────────────────────────────┘

  Skill DNA (Evolver GEP风格):
    每个技能包含完整的基因序列:
    - skill_gene: 技能核心逻辑
    - prompt_gene: 关联的系统提示词
    - tool_gene: 使用的工具列表
    - memory_gene: 记忆访问模式
    - safety_gene: 安全约束
    - version_gene: 版本历史
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================
# 技能相关枚举
# ============================================================

class SkillStatus(str, Enum):
    DRAFT = "draft"  # 草稿
    VALIDATING = "validating"  # 验证中
    VALIDATED = "validated"  # 已验证
    PUBLISHED = "published"  # 已发布
    DEPRECATED = "deprecated"  # 已废弃
    FAILED = "failed"  # 验证失败

class SkillCategory(str, Enum):
    CODING = "coding"  # 代码编写
    RESEARCH = "research"  # 研究分析
    DATA = "data"  # 数据处理
    COMMUNICATION = "communication"  # 沟通交流
    AUTOMATION = "automation"  # 自动化
    REASONING = "reasoning"  # 逻辑推理
    CREATIVE = "creative"  # 创意生成
    SECURITY = "security"  # 安全审计
    OPTIMIZATION = "optimization"  # 性能优化
    SYSTEM = "system"  # 系统操作

# ============================================================
# 技能基因 (Evolver GEP)
# ============================================================

@dataclass
class SkillGene:
    """技能基因 — 技能的最小可进化单元"""

    gene_id: str
    gene_type: str  # prompt / tool / memory / safety / logic
    content: str  # 基因内容 (prompt文本、工具名、逻辑片段)
    version: int = 1
    mutations: list[str] = field(default_factory=list)  # 变异历史
    performance_score: float = 0.5
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    parent_gene_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "gene_id": self.gene_id,
            "gene_type": self.gene_type,
            "content": self.content,
            "version": self.version,
            "mutations": self.mutations,
            "performance_score": self.performance_score,
            "created_at": self.created_at,
            "parent_gene_id": self.parent_gene_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillGene:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

# ============================================================
# 技能定义
# ============================================================

@dataclass
class Skill:
    """一个技能 — 完整的可复用能力单元"""

    skill_id: str
    name: str
    description: str
    category: SkillCategory
    status: SkillStatus = SkillStatus.DRAFT

    # 基因序列 (Evolver GEP)
    genes: list[SkillGene] = field(default_factory=list)

    # 版本
    version: str = "1.0.0"
    version_history: list[dict[str, str]] = field(default_factory=list)

    # 元数据
    author: str = "fnixagent"
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # 依赖的其他技能ID
    required_tools: list[str] = field(default_factory=list)  # 需要的工具
    estimated_tokens: int = 0  # 预估token消耗
    token_savings: int = 0  # 相比无技能时的token节省

    # 统计
    usage_count: int = 0
    success_rate: float = 0.0
    avg_rating: float = 0.0
    benchmark_scores: dict[str, float] = field(default_factory=dict)

    # 审计 (Evolver GEP)
    audit_trail: list[str] = field(default_factory=list)  # 审计轨迹
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "status": self.status.value,
            "genes": [g.to_dict() for g in self.genes],
            "version": self.version,
            "version_history": self.version_history,
            "author": self.author,
            "tags": self.tags,
            "dependencies": self.dependencies,
            "required_tools": self.required_tools,
            "estimated_tokens": self.estimated_tokens,
            "token_savings": self.token_savings,
            "usage_count": self.usage_count,
            "success_rate": self.success_rate,
            "avg_rating": self.avg_rating,
            "benchmark_scores": self.benchmark_scores,
            "audit_trail": self.audit_trail,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Skill:
        data["category"] = SkillCategory(data["category"])
        data["status"] = SkillStatus(data["status"])
        data["genes"] = [SkillGene.from_dict(g) for g in data.get("genes", [])]
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

# ============================================================
# 技能市场
# ============================================================

class SkillMarketplace:
    """
    技能市场 — 技能全生命周期管理

    实现:
    - 技能检测与自动创建 (自动技能创建)
    - 技能验证 (沙箱安全测试)
    - 技能版本控制 (语义化版本)
    - 技能进化 (遗传优化优化技能基因)
    - 技能市场 (发现、分发、评分)
    """

    def __init__(self, storage_dir: str = "data/skills"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 技能注册表
        self._skills: dict[str, Skill] = {}

        # 索引
        self._category_index: dict[str, list[str]] = {}
        self._tag_index: dict[str, list[str]] = {}

        # 加载
        self._load_all()

    # ============================================================
    # 技能注册
    # ============================================================

    def register(self, skill: Skill) -> Skill:
        """注册技能"""
        self._skills[skill.skill_id] = skill
        self._update_indexes(skill, add=True)
        self._save(skill)
        logger.info(f"注册技能: {skill.name} ({skill.skill_id}) v{skill.version}")
        return skill

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def delete(self, skill_id: str) -> bool:
        skill = self._skills.pop(skill_id, None)
        if skill:
            self._update_indexes(skill, add=False)
            (self.storage_dir / f"{skill_id}.json").unlink(missing_ok=True)
            return True
        return False

    # ============================================================
    # 自动技能创建 (自动技能创建)
    # ============================================================

    def detect_and_create(
        self,
        task_description: str,
        execution_trace: str,
        success: bool,
        token_saved: int = 0,
    ) -> Skill | None:
        """
        从成功任务中自动检测可复用模式并创建技能

        GenericAgent风格: 执行路径结晶为技能
        触发条件: 3次成功类似操作 (主动知识持久化)
        """
        if not success:
            return None

        # 生成技能ID
        skill_id = self._generate_skill_id(task_description)

        # 如果已存在，更新统计
        if skill_id in self._skills:
            existing = self._skills[skill_id]
            existing.usage_count += 1
            existing.updated_at = datetime.now(UTC).isoformat()
            self._save(existing)
            return existing

        # 创建新技能
        skill = Skill(
            skill_id=skill_id,
            name=self._derive_name(task_description),
            description=task_description[:200],
            category=self._infer_category(task_description),
            status=SkillStatus.DRAFT,
            tags=self._extract_tags(task_description),
            estimated_tokens=len(task_description.split()) * 2,
            token_savings=token_saved,
            genes=[
                SkillGene(
                    gene_id=f"{skill_id}_prompt",
                    gene_type="prompt",
                    content=task_description,
                ),
                SkillGene(
                    gene_id=f"{skill_id}_logic",
                    gene_type="logic",
                    content=execution_trace[:500],
                ),
            ],
            audit_trail=[f"Auto-created from task execution at {datetime.now(UTC).isoformat()}"],
        )

        self.register(skill)
        return skill

    def crystallize_from_memories(
        self,
        memory_entries: list[Any],
        task_name: str,
    ) -> Skill | None:
        """
        GenericAgent式技能结晶: 从多条执行记忆中提取技能

        memory_entries: 多条MemoryEntry
        """
        if len(memory_entries) < 3:
            return None

        # 提取共性模式
        common_patterns = self._extract_common_patterns(memory_entries)

        skill_id = self._generate_skill_id(task_name)
        skill = Skill(
            skill_id=skill_id,
            name=task_name,
            description=f"从 {len(memory_entries)} 条执行记忆中结晶: {common_patterns[:200]}",
            category=SkillCategory.AUTOMATION,
            status=SkillStatus.DRAFT,
            tags=["crystallized", "auto"],
            estimated_tokens=len(common_patterns.split()) * 2,
            token_savings=500,  # 估计节省
            genes=[
                SkillGene(
                    gene_id=f"{skill_id}_pattern",
                    gene_type="logic",
                    content=common_patterns,
                ),
            ],
            audit_trail=[
                f"Crystallized from {len(memory_entries)} memories at {datetime.now(UTC).isoformat()}"
            ],
        )

        self.register(skill)
        return skill

    # ============================================================
    # 技能验证 (Evolver GEP审计)
    # ============================================================

    def validate(self, skill_id: str) -> tuple[bool, str]:
        """
        验证技能: 沙箱安全检查 + 功能测试

        Evolver GEP风格: 协议约束验证 + 审计轨迹
        """
        skill = self.get(skill_id)
        if not skill:
            return False, "技能不存在"

        skill.status = SkillStatus.VALIDATING

        # 1. 安全检查
        safety_issues = []
        for gene in skill.genes:
            if gene.gene_type == "safety":
                continue  # 安全基因
            # 检查危险模式
            dangerous_patterns = ["rm -rf", "sudo", "eval(", "exec(", "subprocess"]
            for pattern in dangerous_patterns:
                if pattern in gene.content.lower():
                    safety_issues.append(f"基因 {gene.gene_id} 包含危险模式: {pattern}")

        if safety_issues:
            skill.status = SkillStatus.FAILED
            skill.audit_trail.append(f"验证失败: {', '.join(safety_issues)}")
            self._save(skill)
            return False, f"安全验证失败: {safety_issues}"

        # 2. 依赖检查
        missing_deps = []
        for dep_id in skill.dependencies:
            if dep_id not in self._skills:
                missing_deps.append(dep_id)

        if missing_deps:
            skill.status = SkillStatus.FAILED
            skill.audit_trail.append(f"缺少依赖: {missing_deps}")
            self._save(skill)
            return False, f"缺少依赖技能: {missing_deps}"

        # 3. 通过验证
        skill.status = SkillStatus.VALIDATED
        skill.audit_trail.append(f"验证通过 at {datetime.now(UTC).isoformat()}")
        self._save(skill)
        return True, "验证通过"

    # ============================================================
    # 技能版本控制
    # ============================================================

    def bump_version(self, skill_id: str, bump_type: str = "patch") -> Skill | None:
        """
        语义化版本升级
        patch: 1.0.0 → 1.0.1 (修复)
        minor: 1.0.0 → 1.1.0 (新功能)
        major: 1.0.0 → 2.0.0 (重大变更)
        """
        skill = self.get(skill_id)
        if not skill:
            return None

        parts = skill.version.split(".")
        if bump_type == "major":
            parts[0] = str(int(parts[0]) + 1)
            parts[1] = "0"
            parts[2] = "0"
        elif bump_type == "minor":
            parts[1] = str(int(parts[1]) + 1)
            parts[2] = "0"
        else:
            parts[2] = str(int(parts[2]) + 1)

        new_version = ".".join(parts)
        skill.version_history.append(
            {
                "from": skill.version,
                "to": new_version,
                "type": bump_type,
                "at": datetime.now(UTC).isoformat(),
            }
        )
        skill.version = new_version
        skill.updated_at = datetime.now(UTC).isoformat()
        skill.audit_trail.append(f"版本升级: {skill.version_history[-1]['from']} → {new_version}")
        self._save(skill)
        return skill

    # ============================================================
    # 技能进化 (遗传优化)
    # ============================================================

    def evolve_skill(
        self,
        skill_id: str,
        gene_id: str,
        new_content: str,
        performance_improvement: float = 0.0,
    ) -> Skill | None:
        """
        进化技能基因 (遗传优化遗传帕累托进化)

        对技能的单个基因进行变异, 记录性能变化
        """
        skill = self.get(skill_id)
        if not skill:
            return None

        for gene in skill.genes:
            if gene.gene_id == gene_id:
                old_content = gene.content
                gene.content = new_content
                gene.version += 1
                gene.mutations.append(
                    f"v{gene.version}: {old_content[:30]}... → {new_content[:30]}..."
                )
                gene.performance_score += performance_improvement
                gene.performance_score = max(0.0, min(1.0, gene.performance_score))

                self.bump_version(skill_id, "patch")
                skill.audit_trail.append(
                    f"基因进化 {gene.gene_id} v{gene.version}: score {gene.performance_score:.2f}"
                )
                self._save(skill)
                return skill

        return None

    # ============================================================
    # 技能市场功能
    # ============================================================

    def publish(self, skill_id: str) -> tuple[bool, str]:
        """发布技能到市场"""
        skill = self.get(skill_id)
        if not skill:
            return False, "技能不存在"

        if skill.status != SkillStatus.VALIDATED:
            return False, f"技能状态为 {skill.status.value}, 需要先验证"

        is_valid, msg = self.validate(skill_id)
        if not is_valid:
            return False, msg

        skill.status = SkillStatus.PUBLISHED
        skill.audit_trail.append(f"已发布 at {datetime.now(UTC).isoformat()}")
        self._save(skill)
        return True, "发布成功"

    def deprecate(self, skill_id: str, reason: str = "") -> bool:
        """废弃技能"""
        skill = self.get(skill_id)
        if not skill:
            return False
        skill.status = SkillStatus.DEPRECATED
        skill.audit_trail.append(f"已废弃: {reason}")
        self._save(skill)
        return True

    def search(
        self,
        query: str = "",
        category: SkillCategory | None = None,
        tags: list[str] | None = None,
        top_k: int = 20,
    ) -> list[Skill]:
        """搜索技能市场"""
        candidates = list(self._skills.values())

        if query:
            query_lower = query.lower()
            candidates = [
                s
                for s in candidates
                if query_lower in s.name.lower() or query_lower in s.description.lower()
            ]

        if category:
            candidates = [s for s in candidates if s.category == category]

        if tags:
            candidates = [s for s in candidates if any(t in s.tags for t in tags)]

        # 按评分和用量排序
        candidates.sort(key=lambda s: (s.avg_rating, s.usage_count), reverse=True)
        return candidates[:top_k]

    def get_top_skills(self, top_k: int = 10) -> list[Skill]:
        """获取最受欢迎的技能"""
        skills = sorted(
            self._skills.values(),
            key=lambda s: (s.usage_count * s.success_rate, s.avg_rating),
            reverse=True,
        )
        return skills[:top_k]

    def get_category_stats(self) -> dict[str, int]:
        """获取各分类技能数量"""
        stats = {}
        for cat in SkillCategory:
            mids = self._category_index.get(cat.value, [])
            stats[cat.value] = len(mids)
        return stats

    # ============================================================
    # 统计
    # ============================================================

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_skills": len(self._skills),
            "by_status": {
                status.value: len([s for s in self._skills.values() if s.status == status])
                for status in SkillStatus
            },
            "by_category": self.get_category_stats(),
            "total_token_savings": sum(s.token_savings for s in self._skills.values()),
            "average_success_rate": (
                sum(s.success_rate for s in self._skills.values()) / max(len(self._skills), 1)
            ),
        }

    # ============================================================
    # 内部辅助
    # ============================================================

    def _generate_skill_id(self, task_description: str) -> str:
        raw = f"{task_description}_{time.time()}"
        return f"skill_{hashlib.md5(raw.encode()).hexdigest()[:12]}"

    def _derive_name(self, task_description: str) -> str:
        """从任务描述推导技能名"""
        words = task_description.split()[:5]
        return " ".join(words)[:50] or "Unnamed Skill"

    def _infer_category(self, task_description: str) -> SkillCategory:
        """推断技能分类"""
        text = task_description.lower()
        if any(w in text for w in ["code", "program", "debug", "fix"]):
            return SkillCategory.CODING
        if any(w in text for w in ["research", "analyze", "study", "paper"]):
            return SkillCategory.RESEARCH
        if any(w in text for w in ["data", "extract", "parse", "clean"]):
            return SkillCategory.DATA
        if any(w in text for w in ["security", "audit", "vulnerability"]):
            return SkillCategory.SECURITY
        if any(w in text for w in ["optimize", "speed", "performance"]):
            return SkillCategory.OPTIMIZATION
        return SkillCategory.AUTOMATION

    def _extract_tags(self, task_description: str) -> list[str]:
        """提取标签"""
        words = task_description.lower().split()
        keywords = [
            "agent",
            "ai",
            "llm",
            "code",
            "data",
            "api",
            "research",
            "security",
            "optimize",
            "automate",
            "reasoning",
            "memory",
        ]
        return list(set(w for w in words if w in keywords))[:5]

    def _extract_common_patterns(self, memories: list[Any]) -> str:
        """从记忆中提取共性模式"""
        contents = []
        for mem in memories:
            if hasattr(mem, "content"):
                contents.append(mem.content)
            elif isinstance(mem, str):
                contents.append(mem)
        return " | ".join(contents[:3])

    def _update_indexes(self, skill: Skill, add: bool = True):
        # 分类索引
        if add:
            if skill.category.value not in self._category_index:
                self._category_index[skill.category.value] = []
            if skill.skill_id not in self._category_index[skill.category.value]:
                self._category_index[skill.category.value].append(skill.skill_id)

            for tag in skill.tags:
                if tag not in self._tag_index:
                    self._tag_index[tag] = []
                if skill.skill_id not in self._tag_index[tag]:
                    self._tag_index[tag].append(skill.skill_id)
        else:
            if skill.category.value in self._category_index:
                self._category_index[skill.category.value] = [
                    sid
                    for sid in self._category_index[skill.category.value]
                    if sid != skill.skill_id
                ]
            for tag in skill.tags:
                if tag in self._tag_index:
                    self._tag_index[tag] = [
                        sid for sid in self._tag_index[tag] if sid != skill.skill_id
                    ]

    def _save(self, skill: Skill):
        file_path = self.storage_dir / f"{skill.skill_id}.json"
        file_path.write_text(
            json.dumps(skill.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _load_all(self):
        for file_path in self.storage_dir.glob("*.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                skill = Skill.from_dict(data)
                self._skills[skill.skill_id] = skill
                self._update_indexes(skill, add=True)
            except Exception as e:
                logger.warning(f"加载技能失败 {file_path}: {e}")

        logger.info(f"加载 {len(self._skills)} 个技能")

# ============================================================
# 技能进化工厂
# ============================================================

class SkillEvolutionFactory:
    """技能进化工厂 — 系统预装核心技能"""

    SYSTEM_SKILLS = [
        {
            "name": "情报采集",
            "description": "从多源采集最新AI情报，语义去重后入库",
            "category": SkillCategory.RESEARCH,
            "tags": ["intelligence", "collection", "research"],
        },
        {
            "name": "知识合成",
            "description": "LLM深度分析采集情报，生成结构化洞察和升级建议",
            "category": SkillCategory.RESEARCH,
            "tags": ["synthesis", "knowledge", "analysis"],
        },
        {
            "name": "代码生成",
            "description": "根据需求描述生成高质量代码实现",
            "category": SkillCategory.CODING,
            "tags": ["code", "generation", "implementation"],
        },
        {
            "name": "代码审查",
            "description": "审查代码质量，检测安全漏洞和性能问题",
            "category": SkillCategory.SECURITY,
            "tags": ["review", "security", "quality"],
        },
        {
            "name": "性能优化",
            "description": "分析Agent执行效率，优化token消耗和响应速度",
            "category": SkillCategory.OPTIMIZATION,
            "tags": ["performance", "optimization", "token"],
        },
        {
            "name": "错误恢复",
            "description": "检测错误模式，自动生成恢复策略",
            "category": SkillCategory.SYSTEM,
            "tags": ["error", "recovery", "resilience"],
        },
        {
            "name": "记忆管理",
            "description": "管理Agent三层记忆，执行巩固和清理",
            "category": SkillCategory.SYSTEM,
            "tags": ["memory", "management", "consolidation"],
        },
        {
            "name": "模型路由",
            "description": "根据任务复杂度自动选择最优模型",
            "category": SkillCategory.OPTIMIZATION,
            "tags": ["routing", "model", "cost"],
        },
    ]

    @classmethod
    def create_system_skills(cls, marketplace: SkillMarketplace) -> list[Skill]:
        """创建系统预装技能"""
        created = []
        for skill_def in cls.SYSTEM_SKILLS:
            skill_id = f"sys_{hashlib.md5(skill_def['name'].encode()).hexdigest()[:12]}"
            if marketplace.get(skill_id):
                continue

            skill = Skill(
                skill_id=skill_id,
                name=skill_def["name"],
                description=skill_def["description"],
                category=skill_def["category"],
                status=SkillStatus.PUBLISHED,
                tags=skill_def["tags"],
                author="system",
                audit_trail=["System pre-installed skill"],
            )
            marketplace.register(skill)
            created.append(skill)

        return created
