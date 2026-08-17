"""三层护栏注册中心 (Guardrail Registry)。

借鉴 kaoyan-ai-platform 的护栏注册中心设计,扩展为完整的三层护栏体系:
  1. 输入护栏 (Input):      用户输入进入 Agent 前的注入/敏感词/越权检测
  2. 执行护栏 (Execution):  工具调用执行前的权限/参数/高危操作校验
  3. 输出护栏 (Output):     Agent 输出返回用户前的格式/脱敏/合规审核

核心设计:
  - BaseGuardrailGate:  抽象基类,子类实现 check(ctx) 返回 GuardrailCheckResult
  - InputGuardrailGate / ExecutionGuardrailGate / OutputGuardrailGate: 三层基类
  - GuardrailRegistry:  注册中心,管理三层护栏,按 priority 排序执行

执行规则:
  - 按 priority 升序执行(数值小的先执行)
  - BLOCK  : 立即短路,停止后续护栏,返回已有结果
  - WARN   : 记录警告,继续执行
  - MODIFY : 更新上下文数据后继续执行
  - PASS   : 继续执行

线程安全: register/unregister/enable/disable 与执行均使用 threading.Lock。
仅依赖标准库 (abc/dataclasses/enum/threading/logging)。

与 core/security/guardrail.py 的关系:
  - security/guardrail.py 的 GuardrailPipeline 面向 LLM 调用粒度的输入/输出管道(细粒度)
  - 本模块面向 Agent 全链路的三层护栏(粗粒度,可插拔,含执行层)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import abc
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "BaseGuardrailGate",
    "ExecutionGuardrail",
    "ExecutionGuardrailGate",
    "GuardrailAction",
    "GuardrailCheckResult",
    "GuardrailContext",
    "GuardrailRegistry",
    "InputGuardrailGate",
    "OutputGuardrailGate",
    "get_guardrail_registry",
    "reset_guardrail_registry",
]

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 动作枚举
# ---------------------------------------------------------------------------

class GuardrailAction(str, Enum):
    """护栏执行结果动作。"""

    PASS = "pass"  # 通过,继续执行
    WARN = "warn"  # 警告,记录但继续
    BLOCK = "block"  # 拦截,停止执行
    MODIFY = "modify"  # 修改,使用修改后的数据继续

# ---------------------------------------------------------------------------
# 上下文与结果
# ---------------------------------------------------------------------------

@dataclass
class GuardrailContext:
    """护栏执行上下文。

    贯穿单次护栏链路,各护栏可读取/修改上下文。

    Attributes:
        user_id: 用户标识
        session_id: 会话标识
        tool_name: 当前调用的工具名(执行层护栏使用)
        tool_arguments: 工具参数(执行层护栏使用,MODIFY 可更新)
        content: 文本内容(输入/输出方向,MODIFY 可更新)
        metadata: 额外元数据(如 confirmed 标记、用户角色等)
    """

    user_id: str | None = None
    session_id: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] = field(default_factory=dict)
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class GuardrailCheckResult:
    """单个护栏检查结果。

    Attributes:
        guardrail_name: 护栏名称(用于审计/日志)
        action: 执行动作(PASS/WARN/BLOCK/MODIFY)
        message: 说明信息
        modified_data: MODIFY 动作时的新数据
            (str 更新 ctx.content,dict 更新 ctx.tool_arguments)
        risk_score: 风险评分 0~1(0=安全,1=高危)
        details: 额外详情
    """

    guardrail_name: str
    action: GuardrailAction = GuardrailAction.PASS
    message: str = ""
    modified_data: Any = None
    risk_score: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

# ---------------------------------------------------------------------------
# 护栏闸门基类
# ---------------------------------------------------------------------------

class BaseGuardrailGate(abc.ABC):
    """护栏闸门基类。

    子类实现 check(ctx) 返回 GuardrailCheckResult。
    priority 越小越先执行;enabled=False 时由注册中心跳过。

    设计:
      - name/priority/enabled 在构造时确定
      - enable()/disable() 运行时切换开关
      - check() 为抽象方法,由子类实现具体检查逻辑
    """

    def __init__(self, name: str, priority: int = 0, enabled: bool = True) -> None:
        self._name = name
        self._priority = priority
        self._enabled = enabled

    @property
    def name(self) -> str:
        return self._name

    @property
    def priority(self) -> int:
        return self._priority

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    @abc.abstractmethod
    def check(self, ctx: GuardrailContext) -> GuardrailCheckResult:
        """子类实现具体检查逻辑。"""
        ...

class InputGuardrailGate(BaseGuardrailGate):
    """输入护栏基类 - 用户输入进入 Agent 前。

    典型子类: 注入检测 / 敏感词检测 / 输入内容审核 / 越权检测
    """

    pass

class ExecutionGuardrailGate(BaseGuardrailGate):
    """执行护栏基类 - 工具调用执行前。

    典型子类: 工具权限检查 / 参数校验 / 高危操作确认
    """

    pass

# 别名: 兼容 __init__ 导出的 ExecutionGuardrail 名称
ExecutionGuardrail = ExecutionGuardrailGate

class OutputGuardrailGate(BaseGuardrailGate):
    """输出护栏基类 - Agent 输出返回用户前。

    典型子类: 输出格式校验 / 敏感信息检测 / 合规审核 / 脱敏
    """

    pass

# ---------------------------------------------------------------------------
# 三层护栏注册中心
# ---------------------------------------------------------------------------

class GuardrailRegistry:
    """三层护栏注册中心。

    管理三层护栏:
      1. 输入护栏:   敏感词/注入/越权检测
      2. 执行护栏:   工具权限/参数校验/高危操作确认
      3. 输出护栏:   格式校验/脱敏/合规审核

    执行顺序: 按 priority 升序执行(数值小的先执行)
    短路规则: BLOCK 立即停止, WARN 继续, MODIFY 更新数据后继续

    线程安全: register/unregister/enable/disable 与执行均使用 threading.Lock。

    用法:
        registry = get_guardrail_registry()
        registry.register(ToolPermissionGuardrail(tool_registry))
        registry.register(HighRiskOperationGuardrail())

        ctx = GuardrailContext(tool_name="delete_file", tool_arguments={...})
        results = registry.run_execution(ctx)
        if any(r.action == GuardrailAction.BLOCK for r in results):
            return results[-1].message  # 拦截
    """

    def __init__(self) -> None:
        self._input_guardrails: list[InputGuardrailGate] = []
        self._execution_guardrails: list[ExecutionGuardrailGate] = []
        self._output_guardrails: list[OutputGuardrailGate] = []
        self._lock = threading.Lock()
        self._stats: dict[str, dict[str, int]] = {
            "input": {"runs": 0, "passes": 0, "warns": 0, "blocks": 0, "modifies": 0},
            "execution": {"runs": 0, "passes": 0, "warns": 0, "blocks": 0, "modifies": 0},
            "output": {"runs": 0, "passes": 0, "warns": 0, "blocks": 0, "modifies": 0},
        }

    # -- 注册管理 ----------------------------------------------------------

    def register(self, guardrail: BaseGuardrailGate) -> None:
        """注册护栏(自动归入对应层,按 priority 排序)。

        若同名护栏已存在(跨层),先移除旧的再注册新的。

        Args:
            guardrail: 护栏实例(必须继承 InputGuardrailGate /
                ExecutionGuardrailGate / OutputGuardrailGate 之一)

        Raises:
            TypeError: guardrail 不是三层基类的子类
        """
        with self._lock:
            self._remove_locked(guardrail.name)
            target = self._get_layer_list_locked(guardrail)
            target.append(guardrail)
            target.sort(key=lambda g: g.priority)
        _logger.info("注册护栏: %s (priority=%d)", guardrail.name, guardrail.priority)

    def unregister(self, name: str) -> bool:
        """注销护栏。

        Args:
            name: 护栏名称

        Returns:
            是否成功删除(False 表示不存在)
        """
        with self._lock:
            removed = self._remove_locked(name)
        if removed:
            _logger.info("注销护栏: %s", name)
        return removed

    def enable(self, name: str) -> None:
        """启用指定护栏。

        Args:
            name: 护栏名称(不存在时静默忽略)
        """
        with self._lock:
            g = self._find_locked(name)
            if g is not None:
                g.enable()
                _logger.info("启用护栏: %s", name)

    def disable(self, name: str) -> None:
        """禁用指定护栏。

        Args:
            name: 护栏名称(不存在时静默忽略)
        """
        with self._lock:
            g = self._find_locked(name)
            if g is not None:
                g.disable()
                _logger.info("禁用护栏: %s", name)

    # -- 执行 --------------------------------------------------------------

    def run_input(self, ctx: GuardrailContext) -> list[GuardrailCheckResult]:
        """执行输入层护栏。

        Args:
            ctx: 护栏上下文(应填充 content/user_id 等)

        Returns:
            各护栏检查结果列表(BLOCK 时截至拦截护栏)
        """
        return self._run_layer(self._input_guardrails, ctx, "input")

    def run_execution(self, ctx: GuardrailContext) -> list[GuardrailCheckResult]:
        """执行执行层护栏。

        Args:
            ctx: 护栏上下文(应填充 tool_name/tool_arguments/metadata 等)

        Returns:
            各护栏检查结果列表(BLOCK 时截至拦截护栏)
        """
        return self._run_layer(self._execution_guardrails, ctx, "execution")

    def run_output(self, ctx: GuardrailContext) -> list[GuardrailCheckResult]:
        """执行输出层护栏。

        Args:
            ctx: 护栏上下文(应填充 content 等)

        Returns:
            各护栏检查结果列表(BLOCK 时截至拦截护栏)
        """
        return self._run_layer(self._output_guardrails, ctx, "output")

    # -- 查询 --------------------------------------------------------------

    def list_guardrails(self, layer: str | None = None) -> list[str]:
        """列出护栏名称。

        Args:
            layer: 层名(input/execution/output);None 表示全部

        Returns:
            护栏名称列表(按 priority 排序)
        """
        with self._lock:
            names: list[str] = []
            if layer is None or layer == "input":
                names.extend(g.name for g in self._input_guardrails)
            if layer is None or layer == "execution":
                names.extend(g.name for g in self._execution_guardrails)
            if layer is None or layer == "output":
                names.extend(g.name for g in self._output_guardrails)
            return names

    def get_stats(self) -> dict[str, Any]:
        """返回运行统计。

        Returns:
            统计字典,含各层 runs/passes/warns/blocks/modifies 计数
            与已注册护栏数(input/execution/output/total)
        """
        with self._lock:
            stats: dict[str, Any] = {k: dict(v) for k, v in self._stats.items()}
            stats["registered"] = {
                "input": len(self._input_guardrails),
                "execution": len(self._execution_guardrails),
                "output": len(self._output_guardrails),
                "total": (
                    len(self._input_guardrails)
                    + len(self._execution_guardrails)
                    + len(self._output_guardrails)
                ),
            }
            return stats

    # -- 内部辅助 ----------------------------------------------------------

    def _get_layer_list_locked(self, guardrail: BaseGuardrailGate) -> list[BaseGuardrailGate]:
        """根据护栏类型返回对应层列表(调用方需持锁)。"""
        if isinstance(guardrail, InputGuardrailGate):
            return self._input_guardrails  # type: ignore[return-value]
        if isinstance(guardrail, ExecutionGuardrailGate):
            return self._execution_guardrails  # type: ignore[return-value]
        if isinstance(guardrail, OutputGuardrailGate):
            return self._output_guardrails  # type: ignore[return-value]
        raise TypeError(
            f"不支持的护栏类型: {type(guardrail).__name__}, "
            "必须继承 InputGuardrailGate/ExecutionGuardrailGate/OutputGuardrailGate"
        )

    def _find_locked(self, name: str) -> BaseGuardrailGate | None:
        """按名查找护栏(调用方需持锁)。"""
        for layer in (
            self._input_guardrails,
            self._execution_guardrails,
            self._output_guardrails,
        ):
            for g in layer:
                if g.name == name:
                    return g
        return None

    def _remove_locked(self, name: str) -> bool:
        """按名移除护栏(调用方需持锁)。"""
        for layer in (
            self._input_guardrails,
            self._execution_guardrails,
            self._output_guardrails,
        ):
            for i, g in enumerate(layer):
                if g.name == name:
                    layer.pop(i)
                    return True
        return False

    def _run_layer(
        self,
        guardrails: list[BaseGuardrailGate],
        ctx: GuardrailContext,
        layer_name: str,
    ) -> list[GuardrailCheckResult]:
        """执行单层护栏链路。

        短路规则:
          - BLOCK  → 立即停止,返回已有结果
          - WARN   → 记录日志,继续
          - MODIFY → 更新 ctx 后继续
          - PASS   → 继续

        异常隔离: 单个护栏抛异常降级为 WARN,不中断链路。
        """
        # 快照,避免迭代期间被修改
        with self._lock:
            snapshot = list(guardrails)

        results: list[GuardrailCheckResult] = []
        for g in snapshot:
            if not g.enabled:
                results.append(
                    GuardrailCheckResult(
                        guardrail_name=g.name,
                        action=GuardrailAction.PASS,
                        message="护栏已禁用,跳过",
                    )
                )
                continue

            try:
                r = g.check(ctx)
            except Exception as e:
                r = GuardrailCheckResult(
                    guardrail_name=g.name,
                    action=GuardrailAction.WARN,
                    message=f"护栏内部错误: {e}",
                    risk_score=0.5,
                    details={"exception": type(e).__name__},
                )
            results.append(r)

            # 更新统计
            with self._lock:
                self._stats[layer_name]["runs"] += 1
                if r.action == GuardrailAction.BLOCK:
                    self._stats[layer_name]["blocks"] += 1
                elif r.action == GuardrailAction.WARN:
                    self._stats[layer_name]["warns"] += 1
                elif r.action == GuardrailAction.MODIFY:
                    self._stats[layer_name]["modifies"] += 1
                else:
                    self._stats[layer_name]["passes"] += 1

            # 处理动作
            if r.action == GuardrailAction.BLOCK:
                _logger.warning("[%s] 护栏 '%s' 拦截: %s", layer_name, g.name, r.message)
                break
            elif r.action == GuardrailAction.WARN:
                _logger.warning("[%s] 护栏 '%s' 警告: %s", layer_name, g.name, r.message)
            elif r.action == GuardrailAction.MODIFY:
                self._apply_modify(ctx, r)
                _logger.info("[%s] 护栏 '%s' 修改数据", layer_name, g.name)
        return results

    @staticmethod
    def _apply_modify(ctx: GuardrailContext, result: GuardrailCheckResult) -> None:
        """将 MODIFY 结果应用到上下文。

        - modified_data 为 str → 更新 ctx.content
        - modified_data 为 dict → 更新 ctx.tool_arguments
        """
        if result.modified_data is None:
            return
        if isinstance(result.modified_data, str):
            ctx.content = result.modified_data
        elif isinstance(result.modified_data, dict):
            ctx.tool_arguments = result.modified_data

# ---------------------------------------------------------------------------
# 模块级单例
# ---------------------------------------------------------------------------

_registry_singleton: GuardrailRegistry | None = None
_singleton_lock = threading.Lock()

def get_guardrail_registry() -> GuardrailRegistry:
    """获取全局护栏注册中心单例(惰性创建)。

    Returns:
        全局唯一的 GuardrailRegistry 实例
    """
    global _registry_singleton
    with _singleton_lock:
        if _registry_singleton is None:
            _registry_singleton = GuardrailRegistry()
        return _registry_singleton

def reset_guardrail_registry() -> None:
    """重置全局护栏注册中心单例(主要用于测试)。

    清空单例引用,下次调用 get_guardrail_registry() 将创建新实例。
    """
    global _registry_singleton
    with _singleton_lock:
        _registry_singleton = None
