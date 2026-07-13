"""
LangGraph 图节点定义。

将原 7 步流水线映射为 LangGraph 节点函数:
    1. perceive_node:    感知节点,理解用户意图 → 写入 current_goal/intent_keywords
    2. search_node:      检索节点,KTG 路径搜索 → 写入 concept_path/topology_paths
    3. skill_select_node: 技能选择节点,STP 调度 → 写入 selected_skills
    4. execute_node:     执行节点,调用工具 → 写入 tool_results
    5. reflect_node:     反思节点,评估结果 → 决定 should_continue

每个节点函数签名: (state: GraphState) -> dict(部分字段更新)
LangGraph 会将返回的 dict 合并到全局 State。
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from fnixagent.core.tools.protocol import validate_arguments
from fnixagent.graph.state import GraphState

# 节点名称常量(供 builder 与 edges 引用)
NODE_PERCEIVE = "perceive"
NODE_SEARCH = "search"
NODE_SKILL_SELECT = "skill_select"
NODE_EXECUTE = "execute"
NODE_REFLECT = "reflect"


def perceive_node(state: GraphState) -> dict:
    """感知节点: 理解用户意图,提取目标与关键词。

    在实际部署中,这里会调用 LLM 做意图解析。
    当前实现: 简单地将 user_input 作为 goal,提取关键词(空格分词)。

    Returns:
        部分状态更新: {current_goal, intent_keywords, trace}
    """
    user_input = state.get("user_input", "")
    # 简单关键词提取(实际由 LLM 完成)
    keywords = [w for w in user_input.split() if len(w) > 1]

    # 更新轨迹
    trace = state.get("trace", {})
    if not trace:
        trace = {
            "trace_id": str(uuid.uuid4()),
            "task_id": str(uuid.uuid4()),
            "goal": user_input,
            "mode": "react",
            "concept_path": [],
            "tool_calls": [],
            "success": False,
            "duration_ms": 0.0,
            "usage_tokens": 0,
            "reflection_score": 0.0,
            "created_at": time.time(),
        }
    trace["goal"] = user_input

    return {
        "current_goal": user_input,
        "intent_keywords": keywords,
        "trace": trace,
    }


def make_search_node(search_engine, llm_router=None):
    """创建检索节点(闭包,注入 TopologySearch 依赖)。

    Args:
        search_engine: TopologySearch 实例
        llm_router:    可选的 LLM 路由器(用于意图解析增强)

    Returns:
        节点函数
    """
    def search_node(state: GraphState) -> dict:
        """检索节点: KTG 路径搜索,匹配 L2 概念节点。"""
        query = state.get("current_goal", state.get("user_input", ""))
        keywords = state.get("intent_keywords", None)

        # 拓扑路径搜索(捕获异常, 避免检索失败导致整图崩溃)
        try:
            paths = search_engine.search(query, keywords=keywords)
        except Exception as e:
            # 检索失败: 返回空路径并记录错误, 不抛异常(让 reflect 节点决策)
            return {
                "concept_path": [],
                "topology_paths": [],
                "trace": {**state.get("trace", {}), "search_error": str(e)},
                "error": f"search_failed: {type(e).__name__}",
            }

        # 提取概念路径(L2 节点 ID 序列)
        concept_path = []
        for path in paths:
            for node_id in path.nodes:
                concept_path.append(node_id)

        # 序列化路径供 State 存储
        serialized_paths = [
            {
                "nodes": p.nodes,
                "edges": p.edges,
                "total_weight": p.total_weight,
                "depth": p.depth,
            }
            for p in paths
        ]

        # 更新轨迹
        trace = state.get("trace", {})
        trace["concept_path"] = concept_path

        return {
            "concept_path": concept_path,
            "topology_paths": serialized_paths,
            "trace": trace,
        }

    return search_node


def make_skill_select_node(scheduler, binding_protocol=None):
    """创建技能选择节点(闭包,注入 SkillScheduler 依赖)。

    Args:
        scheduler:        SkillScheduler 实例
        binding_protocol: 可选的 SkillBindingProtocol 实例

    Returns:
        节点函数
    """
    def skill_select_node(state: GraphState) -> dict:
        """技能选择节点: STP 调度,基于拓扑权重选择 Top-K 技能。"""
        from fnixagent.core.types import TopologyPath

        # 从状态重建 TopologyPath(取第一条路径)
        topology_paths = state.get("topology_paths", [])
        path = None
        if topology_paths:
            p_data = topology_paths[0]
            path = TopologyPath(
                nodes=p_data.get("nodes", []),
                edges=p_data.get("edges", []),
                total_weight=p_data.get("total_weight", 0.0),
                depth=p_data.get("depth", 0),
            )

        # 调度技能(捕获异常, 避免调度失败导致整图崩溃)
        try:
            selected = scheduler.select_skills(path=path, top_k=5)
        except Exception as e:
            return {
                "selected_skills": [],
                "skill_priorities": {},
                "error": f"skill_select_failed: {type(e).__name__}: {e}",
            }

        # 计算优先级
        priorities = {}
        for tool_meta in selected:
            if binding_protocol:
                try:
                    pri = binding_protocol.compute_priority(tool_meta.name, path)
                except Exception:
                    pri = getattr(tool_meta, "priority", 0.0)
            else:
                pri = tool_meta.priority
            priorities[tool_meta.name] = pri

        skill_names = [t.name for t in selected]

        return {
            "selected_skills": skill_names,
            "skill_priorities": priorities,
        }

    return skill_select_node


def make_execute_node(registry, executor=None):
    """创建执行节点(闭包,注入 ToolRegistry 与 ToolExecutor 依赖)。

    Args:
        registry: ToolRegistry 实例
        executor: 可选的 ToolExecutor 实例(并行执行)

    Returns:
        节点函数
    """
    def execute_node(state: GraphState) -> dict:
        """执行节点: 调用选中的技能(工具)。

        当前实现: 简单地调用第一个选中技能(无参数)。
        实际部署中,这里会解析 LLM 的 tool_calls 并执行。
        """
        selected_skills = state.get("selected_skills", [])
        if not selected_skills:
            return {"tool_results": [], "error": "无可用技能"}

        tool_results = []
        tool_calls = []

        for skill_name in selected_skills:
            if not registry.has(skill_name):
                tool_results.append({
                    "name": skill_name,
                    "status": "failed",
                    "error": f"技能 {skill_name} 未注册",
                })
                continue

            tool = registry.get(skill_name)
            # 简单执行: 空参数(实际由 LLM 决定参数)
            # 入参校验
            valid, errors = validate_arguments(tool.metadata, {})
            if not valid:
                tool_results.append({
                    "name": skill_name,
                    "status": "failed",
                    "error": f"入参校验失败: {errors}",
                })
                continue

            # 执行工具
            try:
                if executor is not None:
                    result = executor.execute(skill_name, {})
                else:
                    result = tool.func({})
                tool_results.append({
                    "name": skill_name,
                    "status": "success",
                    "output": result,
                    "duration_ms": 0.0,
                })
                tool_calls.append({
                    "name": skill_name,
                    "args": {},
                    "status": "success",
                })
            except Exception as e:
                tool_results.append({
                    "name": skill_name,
                    "status": "failed",
                    "error": str(e),
                })
                tool_calls.append({
                    "name": skill_name,
                    "args": {},
                    "status": "failed",
                    "error": str(e),
                })

        # 更新轨迹
        trace = state.get("trace", {})
        trace["tool_calls"] = tool_calls

        return {
            "tool_results": tool_results,
            "trace": trace,
        }

    return execute_node


def reflect_node(state: GraphState) -> dict:
    """反思节点: 评估执行结果,决定是否继续循环。

    判断逻辑:
        - 若所有工具调用成功 → should_continue=False,生成最终答案
        - 若有失败且迭代 < 上限 → should_continue=True,重试
        - 若迭代达到上限 → should_continue=False,返回错误
    """
    iteration = state.get("iteration", 0)
    tool_results = state.get("tool_results", [])
    max_iterations = 10  # 可配置

    # 检查工具执行结果
    all_success = all(r.get("status") == "success" for r in tool_results) if tool_results else False
    has_error = any(r.get("status") == "failed" for r in tool_results)

    if all_success:
        # 全部成功 → 生成答案,停止循环
        outputs = [str(r.get("output", "")) for r in tool_results]
        final_answer = "\n".join(outputs) if outputs else "任务完成"
        trace = state.get("trace", {})
        trace["success"] = True
        return {
            "should_continue": False,
            "final_answer": final_answer,
            "trace": trace,
        }

    if iteration >= max_iterations:
        # 达到上限 → 停止循环
        trace = state.get("trace", {})
        trace["success"] = False
        return {
            "should_continue": False,
            "final_answer": f"达到最大迭代次数 {max_iterations},任务未完成",
            "error": "max_iterations_exceeded",
            "trace": trace,
        }

    # 有失败但未达上限 → 继续循环
    return {
        "should_continue": True,
        "iteration": iteration + 1,
    }
