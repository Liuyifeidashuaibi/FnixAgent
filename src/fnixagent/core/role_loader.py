"""声明式角色配置 —— P3-2。
  - MetaGPT:Role 概念,通过配置定义角色的目标/约束/工具
  - OpenAI Agents SDK:Agent 配置化(tools/instructions/model)
  - LangGraph:声明式节点配置

设计要点:
  1. 角色配置存放在 config/roles/*.yaml,声明式定义
  2. RoleConfig dataclass 承载角色全部属性(可序列化)
  3. RoleLoader 负责发现/加载/校验/缓存角色配置
  4. 与 P3-1 Handoff 集成:RoleConfig.handoffs 自动注册到 HandoffRegistry
  5. 与 P2-6 推理策略集成:RoleConfig.reasoning_strategy 选择策略
  6. 与 P2-8 思考模式集成:RoleConfig.think_mode 控制是否启用思考模式

角色与 Agent 的关系:
  - RoleConfig 是"声明",Agent 是"实例"
  - Runner 启动时根据 RoleConfig 配置 Agent(工具/策略/模型偏好)
  - 一个 Agent 实例对应一个 RoleConfig(1:1)
  - 多 Agent 场景:每个 RoleConfig 对应一个 Agent 实例

用例:
    loader = RoleLoader(config_dir="config/roles")
    loader.list_roles()  # ["office-expert", "doc-writer", ...]
    cfg = loader.load("office-expert")
    # cfg.name / cfg.display_name / cfg.tools / cfg.reasoning_strategy ...
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 尝试导入 yaml(Python 标准库不含 PyYAML,需安装)
try:
    import yaml  # type: ignore

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False
    yaml = None  # type: ignore

# ---------------------------------------------------------------------------
# RoleConfig dataclass
# ---------------------------------------------------------------------------


@dataclass
class HandoffSpec:
    """角色配置中的 handoff 声明(对应 P3-1 Handoff)。

    Attributes:
        target:      目标角色名
        description: 描述(供 LLM 决策何时 handoff)
        max_depth:   防死循环上限(必须 >= 1)

    Raises:
        ValueError: target 为空或 max_depth < 1
        TypeError:  max_depth 不是 int
    """

    target: str
    description: str = ""
    max_depth: int = 5

    def __post_init__(self) -> None:
        # 参数校验:target 必须非空(否则 handoff 无法路由)
        if not isinstance(self.target, str) or not self.target.strip():
            raise ValueError("HandoffSpec.target must be a non-empty string")
        # 参数校验:max_depth 必须 >= 1(防死循环;与 Handoff.max_depth 一致)
        if not isinstance(self.max_depth, int):
            raise TypeError(f"max_depth must be int, got {type(self.max_depth).__name__}")
        if self.max_depth < 1:
            raise ValueError(f"HandoffSpec.max_depth must be >= 1, got {self.max_depth}")


@dataclass
class ModelPreference:
    """模型偏好配置。

    Attributes:
        primary:     首选模型名(如 glm-4 / deepseek-chat / qwen-plus)
        fallback:    备选模型名(主模型不可用时降级)
        temperature: 采样温度
        max_tokens:  最大生成 token 数(可选)
    """

    primary: str = ""
    fallback: str = ""
    temperature: float = 0.5
    max_tokens: int | None = None


@dataclass
class RoleConfig:
    """角色配置(从 YAML 加载)。

    与 config/roles/*.yaml 字段一一对应。

    Attributes:
        name:              角色名(唯一标识,对应 Handoff.target_agent)
        display_name:      显示名(供 UI 展示)
        goal:              角色目标(供 system prompt)
        backstory:         背景故事(供 system prompt)
        constraints:       约束列表(供 system prompt)
        tools:             可用工具列表(对应 ToolRegistry 中的工具名)
        reasoning_strategy: 推理策略名(fast/cheap/precise/compliance,对应 P2-6)
        max_iterations:    ReAct 循环上限
        think_mode:        是否启用思考模式(对应 P2-8)
        handoffs:          可移交目标列表(对应 P3-1 Handoff)
        model_preference:  模型偏好(主模型/备选/温度)
        extra:             扩展字段(YAML 中未识别的字段)
    """

    name: str = ""
    display_name: str = ""
    goal: str = ""
    backstory: str = ""
    constraints: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    reasoning_strategy: str = "fast"
    max_iterations: int = 10
    think_mode: bool = False
    handoffs: list[HandoffSpec] = field(default_factory=list)
    model_preference: ModelPreference = field(default_factory=ModelPreference)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转为字典(用于日志/调试/序列化)。"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "goal": self.goal[:100],
            "backstory": self.backstory[:100],
            "constraints": list(self.constraints),
            "tools": list(self.tools),
            "reasoning_strategy": self.reasoning_strategy,
            "max_iterations": self.max_iterations,
            "think_mode": self.think_mode,
            "handoffs": [
                {"target": h.target, "description": h.description, "max_depth": h.max_depth}
                for h in self.handoffs
            ],
            "model_preference": {
                "primary": self.model_preference.primary,
                "fallback": self.model_preference.fallback,
                "temperature": self.model_preference.temperature,
                "max_tokens": self.model_preference.max_tokens,
            },
            "extra": dict(self.extra),
        }

    def to_system_prompt(self) -> str:
        """根据角色配置构造 system prompt。

        包含:角色名/目标/背景故事/约束,供 LLM 作为 system 消息。
        """
        parts: list[str] = []
        if self.display_name:
            parts.append(f"你是「{self.display_name}」。")
        if self.goal:
            parts.append(f"\n## 目标\n{self.goal}")
        if self.backstory:
            parts.append(f"\n## 背景\n{self.backstory}")
        if self.constraints:
            parts.append("\n## 约束")
            for c in self.constraints:
                parts.append(f"- {c}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# RoleLoader
# ---------------------------------------------------------------------------

# 合法的推理策略名(对应 P2-6 StrategyType)
_VALID_STRATEGIES = {"fast", "cheap", "precise", "compliance"}

# RoleConfig 必填字段
_REQUIRED_FIELDS = {"name"}

# RoleConfig 已知字段(其余归入 extra)
_KNOWN_FIELDS = {
    "name",
    "display_name",
    "goal",
    "backstory",
    "constraints",
    "tools",
    "reasoning_strategy",
    "max_iterations",
    "think_mode",
    "handoffs",
    "model_preference",
}


class RoleLoader:
    """角色配置加载器。

    负责从 config/roles/ 目录加载 YAML 角色配置,校验并缓存。

    用法:
        loader = RoleLoader("config/roles")
        names = loader.list_roles()
        cfg = loader.load("office-expert")
        cfg.to_system_prompt()  # 构造 system prompt
    """

    def __init__(self, config_dir: str = "config/roles") -> None:
        """初始化加载器。

        Args:
            config_dir: 角色配置目录(含 *.yaml 文件)
        """
        self._config_dir = Path(config_dir)
        self._cache: dict[str, RoleConfig] = {}
        self._loaded = False

    # -- 加载 --------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """懒加载:首次访问时扫描目录并加载全部角色。"""
        if self._loaded:
            return
        self._load_all()
        self._loaded = True

    def _load_all(self) -> None:
        """扫描配置目录,加载全部 *.yaml 角色文件。"""
        if not self._config_dir.exists():
            logger.warning("role config dir not found: %s", self._config_dir)
            self._loaded = True
            return

        if not _HAS_YAML:
            logger.warning(
                "PyYAML not installed; role loading disabled. Install with: pip install pyyaml"
            )
            self._loaded = True
            return

        for yfile in sorted(self._config_dir.glob("*.yaml")):
            try:
                cfg = self._load_file(yfile)
                if cfg is not None and cfg.name:
                    self._cache[cfg.name] = cfg
                    logger.info("loaded role '%s' from %s", cfg.name, yfile.name)
            except Exception as exc:
                logger.error("failed to load role from %s: %s", yfile, exc)

    def _load_file(self, path: Path) -> RoleConfig | None:
        """加载单个 YAML 文件为 RoleConfig。"""
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)  # type: ignore
        except Exception as exc:
            logger.error("failed to read %s: %s", path, exc)
            return None

        if not isinstance(data, dict):
            logger.warning("%s: top-level is not a dict, skipped", path)
            return None

        return self._dict_to_role_config(data, source=str(path))

    def _dict_to_role_config(
        self,
        data: dict[str, Any],
        source: str = "",
    ) -> RoleConfig | None:
        """将 dict 转为 RoleConfig(含校验)。"""
        if not self.validate(data):
            logger.warning("%s: role config validation failed, skipped", source)
            return None

        # handoffs
        handoffs: list[HandoffSpec] = []
        for h in data.get("handoffs", []) or []:
            if not isinstance(h, dict):
                continue
            target = str(h.get("target", "")).strip()
            if not target:
                continue
            # max_depth 容错:非法值(<=0 / 非整数)降级为默认 5,而非崩溃
            try:
                max_depth = int(h.get("max_depth", 5))
                if max_depth < 1:
                    logger.warning(
                        "role '%s': handoff max_depth %d < 1, using default 5",
                        data.get("name", "?"),
                        max_depth,
                    )
                    max_depth = 5
            except (TypeError, ValueError):
                logger.warning(
                    "role '%s': handoff max_depth invalid (%r), using default 5",
                    data.get("name", "?"),
                    h.get("max_depth"),
                )
                max_depth = 5
            try:
                handoffs.append(
                    HandoffSpec(
                        target=target,
                        description=str(h.get("description", "")),
                        max_depth=max_depth,
                    )
                )
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "role '%s': failed to create HandoffSpec to '%s': %s",
                    data.get("name", "?"),
                    target,
                    exc,
                )

        # model_preference
        mp_data = data.get("model_preference", {}) or {}
        model_pref = ModelPreference(
            primary=str(mp_data.get("primary", "")),
            fallback=str(mp_data.get("fallback", "")),
            temperature=float(mp_data.get("temperature", 0.5)),
            max_tokens=mp_data.get("max_tokens"),
        )

        # extra(未识别字段)
        extra = {k: v for k, v in data.items() if k not in _KNOWN_FIELDS}

        return RoleConfig(
            name=str(data["name"]).strip(),
            display_name=str(data.get("display_name", "")),
            goal=str(data.get("goal", "")),
            backstory=str(data.get("backstory", "")),
            constraints=list(data.get("constraints", []) or []),
            tools=[str(t) for t in (data.get("tools", []) or [])],
            reasoning_strategy=str(data.get("reasoning_strategy", "fast")),
            max_iterations=int(data.get("max_iterations", 10)),
            think_mode=bool(data.get("think_mode", False)),
            handoffs=handoffs,
            model_preference=model_pref,
            extra=extra,
        )

    # -- 公共 API ----------------------------------------------------------

    def load(self, role_name: str) -> RoleConfig | None:
        """按名加载角色配置。

        Args:
            role_name: 角色名(对应 YAML 中的 name 字段)

        Returns:
            RoleConfig;未找到返回 None
        """
        self._ensure_loaded()
        return self._cache.get(role_name)

    def list_roles(self) -> list[str]:
        """列出全部已加载的角色名。"""
        self._ensure_loaded()
        return sorted(self._cache.keys())

    def list_all(self) -> list[RoleConfig]:
        """返回全部已加载的 RoleConfig。"""
        self._ensure_loaded()
        return [self._cache[k] for k in sorted(self._cache.keys())]

    def reload(self) -> None:
        """清空缓存并重新加载(配置文件变更后调用)。"""
        self._cache.clear()
        self._loaded = False
        self._ensure_loaded()

    def validate(self, role_config: dict[str, Any]) -> bool:
        """校验角色配置 dict 是否合法。

        校验规则:
          1. 必须包含 name 字段(非空字符串)
          2. reasoning_strategy(若提供)必须在 _VALID_STRATEGIES 中
          3. max_iterations(若提供)必须 > 0
          4. handoffs(若提供)每项必须有 target 字段
          5. tools(若提供)必须是列表

        Args:
            role_config: 从 YAML 加载的 dict

        Returns:
            合法返回 True,否则 False
        """
        # 1. name 必填
        name = role_config.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            logger.warning("role config missing required field 'name'")
            return False

        # 2. reasoning_strategy 合法性
        strategy = role_config.get("reasoning_strategy")
        if strategy is not None and strategy not in _VALID_STRATEGIES:
            logger.warning(
                "role '%s': invalid reasoning_strategy '%s' (must be one of %s)",
                name,
                strategy,
                sorted(_VALID_STRATEGIES),
            )
            return False

        # 3. max_iterations > 0
        mi = role_config.get("max_iterations")
        if mi is not None:
            try:
                if int(mi) <= 0:
                    logger.warning("role '%s': max_iterations must be > 0", name)
                    return False
            except (TypeError, ValueError):
                logger.warning("role '%s': max_iterations not an int", name)
                return False

        # 4. handoffs 校验
        handoffs = role_config.get("handoffs")
        if handoffs is not None:
            if not isinstance(handoffs, list):
                logger.warning("role '%s': handoffs must be a list", name)
                return False
            for i, h in enumerate(handoffs):
                if not isinstance(h, dict) or not h.get("target"):
                    logger.warning("role '%s': handoffs[%d] missing 'target'", name, i)
                    return False
                # 自循环检测:A→A 是立即死循环
                if str(h.get("target")).strip() == str(name).strip():
                    logger.warning(
                        "role '%s': handoffs[%d] target == self (self-loop)",
                        name,
                        i,
                    )
                    return False
                # max_depth 校验(若提供):必须 >= 1
                md = h.get("max_depth")
                if md is not None:
                    try:
                        if int(md) < 1:
                            logger.warning(
                                "role '%s': handoffs[%d] max_depth must be >= 1",
                                name,
                                i,
                            )
                            return False
                    except (TypeError, ValueError):
                        logger.warning(
                            "role '%s': handoffs[%d] max_depth not an int",
                            name,
                            i,
                        )
                        return False

        # 5. tools 校验
        tools = role_config.get("tools")
        if tools is not None and not isinstance(tools, list):
            logger.warning("role '%s': tools must be a list", name)
            return False

        return True

    # -- 与 P3-1 Handoff 集成 ---------------------------------------------

    def register_handoffs(
        self,
        registry: Any,
        role_name: str | None = None,
    ) -> int:
        """将角色配置中的 handoffs 注册到 HandoffRegistry。

        防死循环策略:
          1. 自循环检测:target == 自身名时跳过(A→A 是立即死循环)
          2. max_depth 强制 >= 1:HandoffSpec.__post_init__ 已校验,
             此处额外用 try-except 兜底
          3. 与 HandoffRegistry.exec_handoff 的 depth 校验互补(双层防护)

        Args:
            registry:  HandoffRegistry 实例
            role_name:  只注册指定角色的 handoffs;None 表示注册全部角色

        Returns:
            注册的 handoff 数量
        """
        from fnixagent.core.handoff import make_handoff

        # 参数校验
        if registry is None:
            raise ValueError("registry must not be None")

        self._ensure_loaded()
        count = 0
        roles = (
            [self._cache[role_name]]
            if role_name and role_name in self._cache
            else list(self._cache.values())
        )
        for cfg in roles:
            for spec in cfg.handoffs:
                # 自循环检测:A→A 是立即死循环,跳过
                if spec.target == cfg.name:
                    logger.warning(
                        "skip self-handoff: role '%s' → '%s' (would loop)",
                        cfg.name,
                        spec.target,
                    )
                    continue
                try:
                    # make_handoff 内部会再次校验 max_depth >= 1
                    h = make_handoff(
                        target=spec.target,
                        description=spec.description,
                        max_depth=spec.max_depth,
                    )
                    registry.register(cfg.name, h)
                    count += 1
                except (ValueError, TypeError) as exc:
                    # 参数校验失败(max_depth 非法 / target 空)
                    logger.error(
                        "failed to register handoff %s→%s: %s",
                        cfg.name,
                        spec.target,
                        exc,
                    )
                except Exception as exc:
                    logger.error(
                        "failed to register handoff %s→%s: %s",
                        cfg.name,
                        spec.target,
                        exc,
                    )
        return count


__all__ = [
    "HandoffSpec",
    "ModelPreference",
    "RoleConfig",
    "RoleLoader",
]
