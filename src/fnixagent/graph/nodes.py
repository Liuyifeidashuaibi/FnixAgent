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

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
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


def _normalize_llm_response(resp: Any) -> tuple[str, list[dict]]:
    """归一化 LLM 返回为 (content, tool_calls)。

    兼容两种形态:
      - LLMResponse 对象(.content/.tool_calls 属性, Router.chat 返回)
      - OpenAI choices 风格 dict({"choices":[{"message":{...}}]})
    """
    if isinstance(resp, dict):
        choice = (resp.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        return str(msg.get("content") or ""), list(msg.get("tool_calls") or [])
    content = getattr(resp, "content", "")
    tool_calls = getattr(resp, "tool_calls", None) or []
    return str(content or ""), list(tool_calls)


def _build_llm_messages(state: GraphState, registry: Any) -> list[dict]:
    """构造执行节点的 LLM 消息(目标 + STP 技能 + KTG 概念上下文)。"""
    goal = state.get("current_goal", state.get("user_input", ""))
    skills = state.get("selected_skills", [])[:8]
    priorities = state.get("skill_priorities", {})
    concepts = state.get("concept_path", [])[:8]

    lines = [
        "你是任务执行器: 围绕当前目标决定调用工具或直接回答。",
        f"\n## 当前目标\n{goal}",
    ]
    if skills:
        skill_lines = [
            f"- {name}" + (f" (priority={priorities.get(name):.2f})" if name in priorities else "")
            for name in skills
            if registry.has(name)
        ]
        if skill_lines:
            lines.append("\n## 推荐技能(STP 调度)\n" + "\n".join(skill_lines))
    if concepts:
        lines.append("\n## KTG 命中概念路径\n" + " → ".join(concepts))
    lines.append(
        "\n规则:\n"
        "1. 优先用工具完成目标; 无合适技能时直接给出结构化答案\n"
        "2. 工具参数必须符合 schema; 不要臆造参数\n"
        "3. 完成即停, 不做多余调用"
    )
    return [
        {"role": "system", "content": "\n".join(lines)},
        {"role": "user", "content": goal},
    ]


def _run_single_tool(registry: Any, executor: Any, name: str, args: dict) -> dict:
    """执行单个工具并返回结果记录(含入参校验与策略门)。"""
    if not registry.has(name):
        return {"name": name, "status": "failed", "error": f"技能 {name} 未注册"}
    tool = registry.get(name)
    valid, errors = validate_arguments(tool.metadata, args)
    if not valid:
        return {"name": name, "status": "failed", "error": f"入参校验失败: {errors}"}
    try:
        started = time.time()
        if executor is not None:
            result = executor.execute(name, args)
        else:
            result = registry.execute(name, args)  # 走 ToolPolicy 门
        duration_ms = (time.time() - started) * 1000.0
        return {
            "name": name,
            "status": "success",
            "output": result,
            "duration_ms": round(duration_ms, 1),
        }
    except Exception as e:  # noqa: BLE001 — 工具失败不炸整图
        return {"name": name, "status": "failed", "error": str(e)}


def make_execute_node(registry, executor=None, llm_call=None):
    """创建执行节点(闭包,注入 ToolRegistry / ToolExecutor / LLM 依赖)。

    Args:
        registry: ToolRegistry 实例
        executor: 可选的 ToolExecutor 实例(并行执行)
        llm_call: 可选的同步 LLM 调用 (messages, tools) -> resp。
            提供时走真 ReAct 回合(LLM 决定是否调工具及参数);
            为 None 时保留旧版盲调行为(向后兼容/离线测试)。
    """

    def execute_node_llm(state: GraphState) -> dict:
        """执行节点(LLM 驱动): 模型决定工具调用与参数。"""
        messages = _build_llm_messages(state, registry)
        try:
            resp = llm_call(messages, registry.list_for_llm())
        except Exception as e:  # noqa: BLE001 — LLM 失败不炸整图,交给 reflect 决策
            trace = state.get("trace", {})
            trace["llm_error"] = f"{type(e).__name__}: {e}"
            return {
                "tool_results": [],
                "error": f"llm_call_failed: {type(e).__name__}",
                "trace": trace,
            }

        content, raw_calls = _normalize_llm_response(resp)

        # 无工具调用 → 直答
        if not raw_calls:
            trace = state.get("trace", {})
            return {"tool_results": [], "llm_answer": content, "trace": trace}

        # 解析并执行工具调用(OpenAI function-calling 格式)
        tool_results = []
        executed_calls = []
        for call in raw_calls:
            fn = call.get("function") or {}
            name = str(call.get("name") or fn.get("name") or "")
            raw_args = call.get("arguments") if "arguments" in call else fn.get("arguments")
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args) if raw_args.strip() else {}
                except json.JSONDecodeError:
                    args = {}
            elif isinstance(raw_args, dict):
                args = raw_args
            else:
                args = {}

            result_rec = _run_single_tool(registry, executor, name, args)
            ok = result_rec.get("status") == "success"
            tool_results.append(result_rec)
            executed_calls.append(
                {
                    "name": name,
                    "args": args,
                    "status": result_rec["status"],
                    **({} if ok else {"error": result_rec.get("error", "")}),
                }
            )

        trace = state.get("trace", {})
        trace["tool_calls"] = executed_calls

        # 工具结果回填后若模型已有正文,一并保存供 reflect 参考
        updates: dict[str, Any] = {"tool_results": tool_results, "trace": trace}
        if content:
            updates["llm_answer"] = content
        return updates

    def execute_node_legacy(state: GraphState) -> dict:
        """执行节点(legacy): 盲调选中技能(空参数), 离线/测试兼容路径。"""
        selected_skills = state.get("selected_skills", [])
        if not selected_skills:
            return {"tool_results": [], "error": "无可用技能"}

        tool_results = []
        tool_calls = []

        for skill_name in selected_skills:
            result_rec = _run_single_tool(registry, executor, skill_name, {})
            ok = result_rec.get("status") == "success"
            tool_results.append(result_rec)
            record = {"name": skill_name, "args": {}, "status": result_rec["status"]}
            if not ok:
                record["error"] = result_rec.get("error", "")
            tool_calls.append(record)

        # 更新轨迹
        trace = state.get("trace", {})
        trace["tool_calls"] = tool_calls

        return {
            "tool_results": tool_results,
            "trace": trace,
        }

    if llm_call is not None:
        return execute_node_llm
    return execute_node_legacy


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

    # LLM 直答优先: 模型未调工具直接给出答案 → 视为完成
    llm_answer = state.get("llm_answer", "")
    if llm_answer:
        trace = state.get("trace", {})
        trace["success"] = True
        return {
            "should_continue": False,
            "final_answer": llm_answer,
            "trace": trace,
        }

    # 检查工具执行结果
    all_success = all(r.get("status") == "success" for r in tool_results) if tool_results else False
    any(r.get("status") == "failed" for r in tool_results)

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
