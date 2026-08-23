"""
服务层 - 核心调度器构建与单例管理。

负责:
  1. 组装 OrchestratorContext(注入所有引擎)— 传统模式
  2. 创建 AgentScheduler 单例 — 传统模式
  3. 注册业务工具
  4. 提供 API 层调用的统一接口
  5. 组装 LangGraph 图 + KTG + STP + MFP 全链路 — 自进化模式

设计: 应用启动时调用 build_scheduler() 或 build_graph() 一次,后续全局复用。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from fnixagent.core.config import CoreConfig, get_config
from fnixagent.core.llm.base import BaseLLMProvider
from fnixagent.core.llm.providers.openai import (
    GLMProvider,
    MockLLMProvider,
    OpenAIProvider,
    QwenProvider,
)
from fnixagent.core.llm.router import LLMRouter, RouteStrategy
from fnixagent.core.memory.manager import MemoryManager
from fnixagent.core.orchestrator.context import OrchestratorContext
from fnixagent.core.orchestrator.scheduler import AgentScheduler
from fnixagent.core.prompt.manager import PromptManager
from fnixagent.core.reasoning.selector import ReasoningSelector
from fnixagent.core.reflection.replanner import Replanner
from fnixagent.core.reflection.validator import ResultValidator
from fnixagent.core.security.engine import SecurityEngine
from fnixagent.core.tools.executor import ToolExecutor
from fnixagent.core.tools.registry import ToolRegistry

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM Provider 工厂
# ---------------------------------------------------------------------------


def _create_llm_providers() -> list[tuple[BaseLLMProvider, float]]:
    """
    根据环境变量创建 LLM Provider 列表。

    优先级: DeepSeek > GLM > OpenAI > Qwen > Mock
    无任何 API Key 时回退到 MockLLMProvider。
    """
    providers: list[tuple[BaseLLMProvider, float]] = []

    # DeepSeek V4(自进化 Agent 推荐)
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
    if deepseek_key:
        try:
            from fnixagent.core.llm.providers.deepseek import DeepSeekProvider

            model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
            providers.append((DeepSeekProvider(api_key=deepseek_key, model_name=model), 2.5))
        except ImportError:
            pass  # DeepSeekProvider 不可用时跳过

    glm_key = os.getenv("GLM_API_KEY", "")
    if glm_key:
        providers.append((GLMProvider(api_key=glm_key), 2.0))

    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key:
        providers.append((OpenAIProvider(api_key=openai_key), 1.0))

    qwen_key = os.getenv("QWEN_API_KEY", "") or os.getenv("DASHSCOPE_API_KEY", "")
    if qwen_key:
        model = os.getenv("QWEN_MODEL") or os.getenv("LLM_MODEL") or "qwen-plus"
        base = os.getenv("QWEN_BASE_URL") or os.getenv("DASHSCOPE_BASE_URL") or ""
        try:
            from fnixagent.core.llm.providers.openai import OpenAICompatibleProvider

            kwargs = {"name": "qwen", "model_name": model, "api_key": qwen_key}
            if base:
                kwargs["base_url"] = base.rstrip("/") + "/"
            else:
                kwargs["base_url"] = "https://dashscope.aliyuncs.com/compatible-mode/v1/"
            providers.append((OpenAICompatibleProvider(**kwargs), 2.0))
        except Exception:
            try:
                providers.append((QwenProvider(api_key=qwen_key), 1.0))
            except Exception:
                _logger.debug('Unhandled exception', exc_info=True)

    # 无可用 Provider 时回退到 Mock
    if not providers:
        providers.append((MockLLMProvider(), 1.0))

    return providers


# ---------------------------------------------------------------------------
# 业务工具注册
# ---------------------------------------------------------------------------


def _register_business_tools(registry: ToolRegistry) -> int:
    """注册所有业务工具到注册中心,返回注册数量。"""
    count = 0

    # 论文检索工具
    try:
        from fnixagent.business.search import register_search_tools

        register_search_tools(registry)
        count += 3
    except Exception as e:
        print(f"[services] 注册论文检索工具失败: {e}")

    # Word 编辑工具
    try:
        from fnixagent.business.word import register_word_tools

        register_word_tools(registry)
        count += 3
    except Exception as e:
        print(f"[services] 注册 Word 工具失败: {e}")

    # 格式转换工具
    try:
        from fnixagent.business.converter import register_converter_tools

        register_converter_tools(registry)
        count += 1
    except Exception as e:
        print(f"[services] 注册格式转换工具失败: {e}")

    return count


# ---------------------------------------------------------------------------
# 核心调度器构建
# ---------------------------------------------------------------------------


def build_scheduler(config: CoreConfig | None = None) -> AgentScheduler:
    """
    构建完整的 AgentScheduler 实例。

    组装流程:
      1. 创建 LLM Router 并注册 Provider
      2. 创建三层记忆管理器
      3. 创建工具注册中心 + 执行器
      4. 创建安全引擎
      5. 创建 Prompt 管理器
      6. 创建推理选择器 / 校验器 / 重规划器
      7. 组装 OrchestratorContext
      8. 创建 AgentScheduler

    Args:
        config: 核心配置(默认从环境变量加载)

    Returns:
        AgentScheduler 实例
    """
    cfg = config or get_config()
    print("[services] 正在构建 AgentScheduler...")

    # 1. LLM Router
    llm_router = LLMRouter(
        config=cfg.llm,
        strategy=RouteStrategy.WEIGHTED,
    )
    for provider, weight in _create_llm_providers():
        llm_router.register(provider, weight=weight)
        print(f"[services]   LLM Provider: {provider.name} (weight={weight})")

    # 2. 记忆管理器
    memory_manager = MemoryManager(config=cfg.memory)

    # 3. 工具注册中心 + 执行器
    tool_registry = ToolRegistry()
    tool_count = _register_business_tools(tool_registry)
    print(f"[services]   已注册 {tool_count} 个业务工具")
    tool_executor = ToolExecutor(tool_registry, config=cfg.tool)

    # 4. 安全引擎
    security_engine = SecurityEngine(config=cfg.security)

    # 5. Prompt 管理器
    prompt_manager = PromptManager()

    # 6. 推理选择器 / 校验器 / 重规划器
    reasoning_selector = ReasoningSelector(config=cfg.reasoning)
    validator = ResultValidator(llm=llm_router)
    replanner = Replanner(llm=llm_router, max_replans=cfg.reasoning.reflection_max_replans)

    # 7. 组装上下文
    ctx = OrchestratorContext(
        llm_router=llm_router,
        memory_manager=memory_manager,
        tool_registry=tool_registry,
        tool_executor=tool_executor,
        security_engine=security_engine,
        prompt_manager=prompt_manager,
        reasoning_selector=reasoning_selector,
        validator=validator,
        replanner=replanner,
        config=cfg,
    )

    # 8. 创建调度器
    scheduler = AgentScheduler(ctx)
    print("[services] AgentScheduler 构建完成")
    return scheduler


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_scheduler_instance: AgentScheduler | None = None


def get_scheduler() -> AgentScheduler:
    """获取全局 AgentScheduler 单例(懒加载)。"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = build_scheduler()
    return _scheduler_instance


def reset_scheduler() -> None:
    """重置调度器单例(用于测试)。"""
    global _scheduler_instance
    _scheduler_instance = None


# ===========================================================================
# 自进化 Agent 图装配(KTG + STP + MFP + LangGraph)
# ===========================================================================


@dataclass
class GraphComponents:
    """自进化 Agent 全部组件容器。

    由 build_graph() 产出,包含:
        - LangGraph 编译图(编排层)
        - KTG 拓扑图 + 搜索引擎(结构化记忆层)
        - STP 绑定协议 + 调度器 + 权限策略 + 反馈处理器(技能层)
        - MFP 四飞轮(自进化层)
        - 轨迹存储(飞轮 ① 产出 → 飞轮 ②③④ 消费)
        - LLM 路由器(推理层)
        - 工具注册表 + 执行器(接入层)
    """

    # 编排层
    graph: object  # 编译后的 LangGraph
    graph_builder: object = None  # GraphBuilder 实例

    # 结构化记忆层(KTG)
    topology_graph: object = None  # TopologyGraph
    search_engine: object = None  # TopologySearch

    # 技能层(STP)
    binding_protocol: object = None  # SkillBindingProtocol
    permission_policy: object = None  # SkillPermissionPolicy
    scheduler: object = None  # SkillScheduler
    feedback_handler: object = None  # SkillFeedbackHandler

    # 自进化层(MFP)
    flywheel_perception: object = None  # 飞轮 ①
    flywheel_solidification: object = None  # 飞轮 ②
    flywheel_reflection: object = None  # 飞轮 ③
    flywheel_climbing: object = None  # 飞轮 ④
    trace_store: object = None  # 轨迹存储

    # 推理层
    llm_router: object = None  # LLMRouter

    # 接入层
    tool_registry: object = None  # ToolRegistry
    tool_executor: object = None  # ToolExecutor


def build_graph(config: CoreConfig | None = None) -> GraphComponents:
    """
    构建自进化 Agent 的 LangGraph 全链路。

    组装流程:
      1. 创建 LLM Router(含 DeepSeekProvider)
      2. 创建 KTG 拓扑图 + 搜索引擎
      3. 创建工具注册中心 + 执行器 + 注册业务工具
      4. 创建 STP 绑定协议 + 权限策略 + 调度器 + 反馈处理器
      5. 创建 LangGraph 图装配器 + 编译图
      6. 创建 MFP 四飞轮 + 轨迹存储
      7. 返回 GraphComponents 容器

    Args:
        config: 核心配置(默认从环境变量加载)

    Returns:
        GraphComponents 容器(含全部组件引用)
    """
    cfg = config or get_config()
    print("[services] 正在构建自进化 Agent Graph...")

    # 1. LLM Router
    llm_router = LLMRouter(config=cfg.llm, strategy=RouteStrategy.WEIGHTED)
    for provider, weight in _create_llm_providers():
        llm_router.register(provider, weight=weight)
        print(f"[services]   LLM Provider: {provider.name} (weight={weight})")

    # 2. KTG 拓扑图 + 搜索引擎
    from fnixagent.core.topology.graph import TopologyGraph
    from fnixagent.core.topology.search import TopologySearch

    topology_graph = TopologyGraph()
    search_engine = TopologySearch(
        graph=topology_graph,
        top_k=cfg.topology.search_top_k,
        max_depth=cfg.topology.search_max_depth,
        min_weight=cfg.topology.search_min_weight,
    )
    print(f"[services]   KTG 拓扑图已创建(search_top_k={cfg.topology.search_top_k})")

    # 3. 工具注册中心 + 执行器
    tool_registry = ToolRegistry()
    tool_count = _register_business_tools(tool_registry)
    # 办公 Work 工具（Excel/PPT/PDF）一并进入自进化图
    try:
        from fnixagent.services.work_agent import register_office_work_tools

        workspace = os.getenv("FNIXAGENT_WORKSPACE", os.getcwd())
        before = len(tool_registry._tools)
        register_office_work_tools(tool_registry, workspace)
        tool_count = len(tool_registry._tools)
        print(f"[services]   业务+办公工具: {before} → {tool_count}")
    except Exception as e:
        print(f"[services]   办公工具注册跳过: {e}")
    print(f"[services]   已注册 {tool_count} 个业务工具")
    tool_executor = ToolExecutor(tool_registry, config=cfg.tool)

    # 4. STP 绑定协议 + 权限策略 + 调度器 + 反馈处理器
    from fnixagent.core.skills.feedback import SkillFeedbackHandler
    from fnixagent.core.skills.levels import SkillPermissionPolicy
    from fnixagent.core.skills.protocol import SkillBindingProtocol
    from fnixagent.core.skills.scheduler import SkillScheduler

    binding_protocol = SkillBindingProtocol(graph=topology_graph)
    permission_policy = SkillPermissionPolicy()
    skill_scheduler = SkillScheduler(
        registry=tool_registry,
        binding_protocol=binding_protocol,
        permission_policy=permission_policy,
    )
    feedback_handler = SkillFeedbackHandler(graph=topology_graph)
    print("[services]   STP 技能调度系统已创建")

    # 4b. KTG 持久化加载 → 若空则播种办公拓扑 + STP
    topology_store_mgr = None
    try:
        from fnixagent.core.topology.store import JSONFileStore, TopologyStoreManager

        topo_dir = os.getenv("FNIXAGENT_TOPOLOGY_DIR", "data/topology")
        topology_store_mgr = TopologyStoreManager(
            topology_graph,
            JSONFileStore(topo_dir),
        )
        try:
            topology_store_mgr.load_from_store()
            print(f"[services]   KTG 已从 {topo_dir} 加载快照")
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)
    except Exception as e:
        print(f"[services]   KTG 持久化初始化跳过: {e}")

    try:
        from fnixagent.services.evolution_seed import seed_office_topology

        seed_stats = seed_office_topology(topology_graph, binding_protocol)
        print(
            f"[services]   KTG 种子: nodes={seed_stats['nodes']} "
            f"edges={seed_stats['edges']} bindings={seed_stats['bindings']}"
        )
    except Exception as e:
        print(f"[services]   KTG 播种失败: {e}")

    if topology_store_mgr is not None:
        try:
            snap = topology_store_mgr.save_snapshot("boot")
            print(f"[services]   KTG 启动快照: {snap}")
        except Exception as e:
            print(f"[services]   KTG 快照保存跳过: {e}")

    # 5. LangGraph 图装配器 + 编译图
    from fnixagent.graph.builder import GraphBuilder

    graph_builder = GraphBuilder(
        search_engine=search_engine,
        scheduler=skill_scheduler,
        registry=tool_registry,
        binding_protocol=binding_protocol,
        executor=tool_executor,
    )
    compiled_graph = graph_builder.build()
    print("[services]   LangGraph 图已编译")

    # 6. MFP 四飞轮 + 轨迹存储
    from fnixagent.core.flywheel.climbing import HillClimbingFlywheel
    from fnixagent.core.flywheel.knowledge import KnowledgeSolidificationFlywheel
    from fnixagent.core.flywheel.perception import PerceptionFlywheel
    from fnixagent.core.flywheel.reflection import MetaReflectionFlywheel
    from fnixagent.core.flywheel.trace import TraceStore

    # 轨迹存储目录(可配置)
    trace_dir = os.getenv("fnixagent_TRACE_DIR", "data/traces")
    trace_store = TraceStore(base_dir=trace_dir)

    flywheel_perception = PerceptionFlywheel(graph=compiled_graph)
    flywheel_solidification = KnowledgeSolidificationFlywheel(
        graph=topology_graph,
        llm_router=llm_router,
    )
    flywheel_reflection = MetaReflectionFlywheel(
        graph=topology_graph,
        trace_store=trace_store,
        llm_router=llm_router,
        trigger_interval=cfg.flywheel.meta_reflection_interval,
    )
    flywheel_climbing = HillClimbingFlywheel(
        graph=topology_graph,
        trace_store=trace_store,
        evolution_interval=cfg.flywheel.evolution_check_interval,
    )
    print("[services]   MFP 四阶飞轮已创建")
    print("[services] 自进化 Agent Graph 构建完成")

    return GraphComponents(
        graph=compiled_graph,
        graph_builder=graph_builder,
        topology_graph=topology_graph,
        search_engine=search_engine,
        binding_protocol=binding_protocol,
        permission_policy=permission_policy,
        scheduler=skill_scheduler,
        feedback_handler=feedback_handler,
        flywheel_perception=flywheel_perception,
        flywheel_solidification=flywheel_solidification,
        flywheel_reflection=flywheel_reflection,
        flywheel_climbing=flywheel_climbing,
        trace_store=trace_store,
        llm_router=llm_router,
        tool_registry=tool_registry,
        tool_executor=tool_executor,
    )


# ---------------------------------------------------------------------------
# 全局单例(Graph 模式)
# ---------------------------------------------------------------------------

_graph_instance: GraphComponents | None = None


def get_graph() -> GraphComponents:
    """获取全局 GraphComponents 单例(懒加载)。"""
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = build_graph()
    return _graph_instance


def reset_graph() -> None:
    """重置 Graph 单例(用于测试)。"""
    global _graph_instance
    _graph_instance = None


def process_with_graph(
    user_input: str,
    components: GraphComponents | None = None,
    session_id: str | None = None,
) -> dict:
    """使用 LangGraph 处理用户输入(飞轮闭环入口)。

    完整闭环:
        飞轮 ① 感知-执行 → 飞轮 ② 知识固化 → (可选)飞轮 ③ 元反思

    Args:
        user_input: 用户输入
        components: GraphComponents 容器(默认用全局单例)
        session_id: 会话 ID(用于检查点恢复)

    Returns:
        {
            "answer": str,           最终答案
            "trace": TraceRecord,    执行轨迹
            "solidified": dict,      知识固化统计
            "reflected": Optional[dict],  元反思结果(若触发)
        }
    """
    if components is None:
        components = get_graph()

    # 飞轮 ① 感知-执行
    trace = components.flywheel_perception.run(
        user_input=user_input,
        session_id=session_id,
    )

    # 持久化轨迹
    try:
        components.trace_store.append(trace)
    except Exception:
        _logger.debug('Unhandled exception', exc_info=True)  # 轨迹持久化失败不影响主流程

    # 飞轮 ② 知识固化(实时,每次对话后触发)
    solidified = components.flywheel_solidification.process(trace)

    # 飞轮 ③ 元反思(准实时,每 N 次对话触发)
    reflected = None
    if components.flywheel_reflection.should_trigger():
        reflected = components.flywheel_reflection.run()

    # 飞轮 ④ 爬坡进化(后台异步,每 N 次对话触发)
    if components.flywheel_climbing.should_trigger():
        try:
            components.flywheel_climbing.run()
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)  # 进化失败不影响主流程

    return {
        "answer": (
            (trace.metadata or {}).get("answer") if getattr(trace, "metadata", None) else None
        )
        or (f"已完成: {user_input[:80]}" if trace.success else f"未完成: {user_input[:80]}"),
        "trace": trace,
        "solidified": solidified,
        "reflected": reflected,
    }
