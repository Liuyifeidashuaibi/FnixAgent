"""Work 产品 9 步流水线 — 对齐 README「一次完整请求」。

用户输入
  → 1. 安全校验
  → 2. 短期记忆 + 长期向量检索
  → 3. 实体记忆（用户画像）
  → 4. 意图识别 → ReasoningSelector
  → 5. KTG 路径 + STP 技能计划
  → 6. 推理循环（AgenticLoop + 工具）
  → 7. 反思校验（可选）
  → 8. 输出审核 / 脱敏
  → 9. 记忆更新 + MFP 固化 + KTG 快照 + 审计 TraceId
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fnixagent.core.types import Message, MessageRole, ReasoningMode

_ARTIFACT_EXTS = {
    ".html",
    ".htm",
    ".css",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".md",
    ".txt",
    ".csv",
    ".docx",
    ".xlsx",
    ".pptx",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".py",
}


def normalize_artifact_path(path: str, workspace: str = "") -> str:
    """统一产物路径为 workspace 相对路径，便于去重。"""
    p = (path or "").strip().replace("\\", "/").rstrip(".,;")
    if not p:
        return ""
    # 收起连续斜杠(模型输出/目录拼接偶发 `.fnix//artifacts//x` 形式)
    while "//" in p:
        p = p.replace("//", "/")
    ws = str(Path(workspace or "").expanduser().resolve()).replace("\\", "/")
    if ws and p.startswith(ws):
        p = p[len(ws) :].lstrip("/")
    # 绝对 Windows 盘符路径 → 尽量保留 .fnix/ 后缀
    if len(p) > 2 and p[1] == ":":
        idx = p.lower().find(".fnix/")
        if idx >= 0:
            p = p[idx:]
    if p and not p.startswith(".") and ".fnix/artifacts/" in p:
        idx = p.lower().find(".fnix/artifacts/")
        p = p[idx:]
    return p


def normalize_evolution_event(
    data: dict[str, Any] | None,
    *,
    prev: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge evolution NDJSON snapshots so UI always sees stable KTG/STP/MFP fields."""
    out: dict[str, Any] = {}
    if isinstance(prev, dict):
        out.update(prev)
    if isinstance(data, dict):
        out.update(data)

    if "ktg_paths" in out:
        try:
            out["ktg_paths"] = int(out["ktg_paths"])
        except (TypeError, ValueError):
            out["ktg_paths"] = 0
    if "ktg_nodes" in out:
        try:
            out["ktg_nodes"] = int(out["ktg_nodes"])
        except (TypeError, ValueError):
            out["ktg_nodes"] = 0

    paths = out.get("ktg_paths")
    if isinstance(paths, int) and paths > 0:
        out["ktg"] = True
        out["stp"] = True
    else:
        out.setdefault("ktg", bool(out.get("concepts")))
        out.setdefault("stp", bool(out.get("ktg")))

    if out.get("mfp_result") is not None:
        out["mfp"] = True
    else:
        out.setdefault("mfp", False)

    return out


def merge_artifact(existing: list[dict[str, str]], path: str, workspace: str = "") -> None:
    rel = normalize_artifact_path(path, workspace)
    if not rel:
        return
    rel_key = rel.lower().replace("\\", "/")
    existing_keys = {a["path"].lower().replace("\\", "/") for a in existing}

    # 完整路径优先：丢弃仅有文件名的重复项
    if "/" in rel_key:
        base = os.path.basename(rel)
        existing[:] = [
            a for a in existing if not ("/" not in a["path"] and a["path"].lower() == base.lower())
        ]
        existing_keys = {a["path"].lower().replace("\\", "/") for a in existing}
    else:
        # 仅有 basename 时，若已有 .fnix/artifacts/.../basename 则跳过
        for ek in existing_keys:
            if ek.endswith("/" + rel_key) or ek.endswith("\\" + rel_key):
                return

    if rel_key in existing_keys:
        return
    existing.append({"path": rel, "name": os.path.basename(rel)})


def scan_recent_artifacts(
    workspace: str, *, since_ts: float, limit: int = 40
) -> list[dict[str, str]]:
    """扫描 `{workspace}/.fnix/artifacts` 下本次任务新写入的文件。"""
    root = Path(workspace or "").expanduser()
    art_root = root / ".fnix" / "artifacts"
    if not art_root.is_dir():
        return []
    found: list[dict[str, str]] = []
    try:
        for path in art_root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in _ARTIFACT_EXTS:
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime + 0.5 < since_ts:
                continue
            try:
                rel = str(path.relative_to(root)).replace("\\", "/")
            except ValueError:
                rel = str(path)
            found.append({"path": rel, "name": path.name})
    except OSError:
        return []
    found.sort(key=lambda x: x["path"])
    return found[:limit]


def _build_topo_weight_provider(graph_components: Any):
    """构建拓扑权重查询闭包 (Spec 6 闭环修复, 论文创新点 2)。

    从 graph_components.topology_graph 的 L2_CONCEPT 节点构建
    {name_lower: weight} 索引, 供 SkillLibrary.retrieve_skills
    查询技能绑定概念的拓扑权重。

    闭环路径: MFP 第 4 阶 (爬坡) 调权 → topology_graph.node.weight
    → 此处 provider → retrieve_skills score *= (0.5 + topo_weight)
    → 下次任务召回受拓扑权重影响 → 闭环成立。

    Returns:
        Callable[[str], float] 或 None (无拓扑图时降级, 不影响原召回)
    """
    if graph_components is None:
        return None
    topology_graph = getattr(graph_components, "topology_graph", None)
    if topology_graph is None:
        return None
    try:
        from fnixagent.core.types import NodeType, TopologyLayer

        concept_nodes = topology_graph.list_nodes(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
        )
        # 构建 name_lower → weight 索引 (O(n) 一次构建, 查询 O(1))
        weight_index: dict[str, float] = {}
        for node in concept_nodes:
            if not node.name:
                continue
            key = node.name.lower().strip()
            if key:
                weight_index[key] = float(getattr(node, "weight", 0.5))
    except Exception:
        return None

    if not weight_index:
        return None  # 拓扑图空, 降级为原召回逻辑

    def provider(skill_signature: str) -> float:
        """返回 skill_signature 在拓扑图中匹配到的最大概念权重。

        匹配策略: 用 skill_signature 的 token 去权重索引查,
        取最大权重 (代表该技能最相关的概念强度)。
        无匹配 → 0.5 (中性, 不影响原 score)。
        """
        if not skill_signature:
            return 0.5
        sig_lower = skill_signature.lower()
        max_weight = 0.0
        # 精确匹配优先
        for name, weight in weight_index.items():
            if name in sig_lower:
                if weight > max_weight:
                    max_weight = weight
        # 无匹配返回中性权重 (0.5), 让 score *= 1.0 不影响原排序
        return max_weight if max_weight > 0.0 else 0.5

    return provider


def build_mission_schema(user_input: str, work_mode: str = "craft") -> dict[str, Any]:
    """把自然语言任务映射为受控的动态工作空间协议。

    模型不能直接生成前端代码；它只选择受信任的 block 类型。前端据此切换
    文档、数据、演示、调研、代码或通用任务工作区。
    """
    text = user_input.strip()
    lowered = text.lower()
    mode = (work_mode or "craft").strip().lower()
    kind_rules = [
        ("spreadsheet", ("excel", "xlsx", "表格", "数据分析", "数据挖掘", "统计")),
        ("presentation", ("ppt", "pptx", "演示", "幻灯片", "路演")),
        ("research", ("调研", "研究", "检索", "论文", "综述", "资料")),
        ("document", ("word", "docx", "报告", "周报", "文档", "方案", "总结")),
        (
            "code",
            (
                "代码",
                "编程",
                "bug",
                "接口",
                "重构",
                "仓库",
                "项目",
                "html",
                "css",
                "javascript",
                "typescript",
                "前端",
                "网站",
                "网页",
                "mbti",
                "测验",
                "小程序",
                "脚本",
                "函数",
                "组件",
                "api",
                "创建",
                "生成页面",
                "落地页",
                "dashboard",
                "看板",
                "应用",
                "index.html",
                "style.css",
                "script.js",
                "vue",
                "react",
                "写一个",
            ),
        ),
    ]
    workspace_kind = "general"
    for kind, keywords in kind_rules:
        if any(keyword in lowered for keyword in keywords):
            workspace_kind = kind
            break

    # Ask/Plan：解释类问题不因 MBTI/网站等关键词误判为 code（对齐工程实践）
    if mode in ("ask", "plan"):
        explain_hints = ("解释", "什么是", "是什么", "介绍", "含义", "区别", "为什么", "如何理解")
        build_hints = (
            "做一个",
            "创建",
            "生成",
            "写一份",
            "落地",
            "build",
            "create",
            "write_file",
            ".fnix/artifacts",
            "index.html",
        )
        if workspace_kind == "code" and any(h in lowered for h in explain_hints):
            if not any(h in lowered for h in build_hints):
                workspace_kind = "research" if mode == "plan" else "general"

    block_map = {
        "spreadsheet": ["mission", "data_preview", "analysis", "artifacts"],
        "presentation": ["mission", "outline", "slide_preview", "artifacts"],
        "research": ["mission", "sources", "evidence", "synthesis", "artifacts"],
        "document": ["mission", "outline", "document_preview", "artifacts"],
        "code": ["mission", "plan", "changes", "verification", "artifacts"],
        "general": ["mission", "plan", "timeline", "artifacts"],
    }
    deliverable_map = {
        "spreadsheet": ["xlsx", "分析结论"],
        "presentation": ["pptx", "演示大纲"],
        "research": ["研究报告", "来源清单"],
        "document": ["专业文档", "可编辑源文件"],
        "code": ["可运行源码 / 静态站", "产物路径"],
        "general": ["任务结果", "执行摘要"],
    }
    acceptance_map = {
        "spreadsheet": ["数据已读取并校验", "结论包含可追溯依据", "交付可编辑表格"],
        "presentation": ["结构完整且叙事连贯", "页面内容可直接演示", "交付可编辑演示文稿"],
        "research": ["来源可追溯", "观点与证据分离", "结论覆盖用户目标"],
        "document": ["内容覆盖任务目标", "结构与格式专业", "交付文件可正常打开"],
        "code": ["源码已写入磁盘", "可直接打开/运行验收", "回复中列出产物路径"],
        "general": ["目标已完成", "关键过程可追溯", "结果可验收"],
    }

    title = text.splitlines()[0][:48] or "新任务"
    return {
        "schema_version": "1.0",
        "title": title,
        "intent": text[:500],
        "workspace_kind": workspace_kind,
        "blocks": block_map[workspace_kind],
        "expected_deliverables": deliverable_map[workspace_kind],
        "acceptance_criteria": acceptance_map[workspace_kind],
        "execution_policy": {
            # 目前支持中断；跨文件事务回滚将在 checkpoint 接入后开启。
            "reversible": False,
            "artifact_first": True,
            "human_can_interrupt": True,
        },
    }


@dataclass
class WorkPipelineContext:
    """单次 Work 请求上下文。"""

    trace_id: str
    user_input: str
    workspace: str
    session_id: str = ""
    user_id: str = "desktop"
    llm: dict | None = None
    reasoning_mode: ReasoningMode = ReasoningMode.REACT
    max_steps: int = 30
    memory_context: dict = field(default_factory=dict)
    ktg_paths: list = field(default_factory=list)
    concept_ids: list = field(default_factory=list)
    skills_block: str = ""
    todos_block: str = ""  # load-bearing state (任务状态外化)
    stp_selected_count: int = 0  # STP 真接入: 拓扑调度选中的技能数 (论文 ablation 指标)
    stp_skipped_reason: str = ""  # STP 降级原因 (fail-soft-with-signal, 对齐 Critic 模式)
    workspace_kind: str = "general"
    work_mode: str = "craft"  # ask | plan | craft（工作台）
    security_blocked: bool = False
    block_reason: str = ""
    memory_budget: dict = field(default_factory=dict)
    # Spec 7+: DAAO 真路由决策结果（由 daao_router.route() 写入）
    max_reflect_rounds: int = 2
    difficulty_score: float = 0.0
    hera_hit_rate: float = 0.0
    recent_failure_rate: float = 0.0
    daao_confidence: float = 1.0
    # Spec 7 fail-soft-with-signal 闭环: Critic 审查是否被跳过
    # (LLM 故障/解析失败/异常), step9 持久化时写入 TraceRecord
    critic_skipped: bool = False


class WorkPipeline:
    """README 对齐的 Work 编排器。"""

    def __init__(
        self,
        graph_components: Any = None,
        memory_manager: Any = None,
        security_engine: Any = None,
        reasoning_selector: Any = None,
        topology_store_mgr: Any = None,
    ) -> None:
        self.graph = graph_components
        self.memory = memory_manager
        self.security = security_engine
        self.selector = reasoning_selector
        self.topology_store = topology_store_mgr

    # ------------------------------------------------------------------
    # 步骤实现
    # ------------------------------------------------------------------

    def step1_security_input(self, ctx: WorkPipelineContext) -> WorkPipelineContext:
        if self.security is None:
            return ctx
        try:
            result = self.security.check_input(ctx.user_input)
            if not result.passed:
                ctx.security_blocked = True
                ctx.block_reason = result.blocked_reason or "input_blocked"
            elif result.sanitized_text:
                ctx.user_input = result.sanitized_text
        except Exception:
            pass
        return ctx

    def step2_3_memory_load(self, ctx: WorkPipelineContext) -> WorkPipelineContext:
        if self.memory is None:
            return ctx
        try:
            ctx.memory_context = self.memory.load_context(
                query=ctx.user_input,
                user_id=ctx.user_id,
            )
        except Exception:
            ctx.memory_context = {}
        return ctx

    def step4_select_reasoning(
        self, ctx: WorkPipelineContext, tool_count: int = 8
    ) -> WorkPipelineContext:
        mode = (ctx.work_mode or "craft").lower()
        # Ask 模式：少步、只问答
        if mode == "ask":
            ctx.reasoning_mode = ReasoningMode.REACT
            ctx.max_steps = min(ctx.max_steps, 8)
            return ctx
        # Plan 模式：必须先规划
        if mode == "plan":
            ctx.reasoning_mode = ReasoningMode.PLAN_EXECUTE
            ctx.max_steps = max(ctx.max_steps, 20)
            return ctx
        # Craft + 编码/建站：Plan&Execute + 更多步数
        if ctx.workspace_kind == "code":
            # Prefer ReAct with fewer steps so craft/website doesn't burn 45 LLM rounds.
            ctx.reasoning_mode = ReasoningMode.REACT
            ctx.max_steps = max(min(ctx.max_steps, 16), 12)
            return ctx
        if self.selector is None:
            return ctx
        try:
            mode = self.selector.select(ctx.user_input, available_tools=tool_count)
            ctx.reasoning_mode = mode
            # Plan&Execute / 复杂任务多给步数
            if mode == ReasoningMode.PLAN_EXECUTE:
                ctx.max_steps = max(ctx.max_steps, 40)
            elif mode == ReasoningMode.SELF_REFLECT:
                ctx.max_steps = max(ctx.max_steps, 35)
            elif mode == ReasoningMode.REACT:
                ctx.max_steps = min(ctx.max_steps, 20) if tool_count < 3 else ctx.max_steps
        except Exception:
            pass
        return ctx

    def step5_ktg_stp_plan(self, ctx: WorkPipelineContext) -> WorkPipelineContext:
        if self.graph is None:
            return ctx
        try:
            paths = self.graph.search_engine.search(ctx.user_input)
            ctx.ktg_paths = paths or []
            for p in ctx.ktg_paths:
                for n in getattr(p, "nodes", []) or []:
                    nid = n if isinstance(n, str) else getattr(n, "node_id", "")
                    if nid and str(nid).startswith("L2:"):
                        ctx.concept_ids.append(str(nid))
        except Exception:
            ctx.ktg_paths = []
        return ctx

    def step5b_stp_select(self, ctx: WorkPipelineContext) -> WorkPipelineContext:
        """STP 基于拓扑权重选择技能 (论文核心创新 - 真正接入主路径)。

        基于 step5 KTG 推理路径,用 SkillBindingProtocol.compute_priority
        换算每个绑定技能的优先级,取 Top-K 注入 skills_block 前缀。

        与 harness_loader/builtin/HERA 融合 (非替代):
          STP 权重排序 (拓扑命中) > HERA (历史捕获) > builtin (内置) > harness (用户手动)

        论文 ablation: 关闭此步即退化为"无 STP 调度"基线。
        """
        if self.graph is None:
            return ctx
        scheduler = getattr(self.graph, "scheduler", None)
        binding = getattr(self.graph, "binding_protocol", None)
        if scheduler is None or binding is None:
            return ctx

        try:
            from fnixagent.core.types import TopologyPath

            # 构造推理路径 (从 KTG paths 提取节点序列)
            path_nodes: list[str] = []
            for p in ctx.ktg_paths:
                nodes = getattr(p, "nodes", []) or []
                for n in nodes:
                    nid = n if isinstance(n, str) else getattr(n, "node_id", "")
                    if nid:
                        path_nodes.append(str(nid))
            # 补充 concept_ids (L2 命中)
            for cid in ctx.concept_ids:
                if cid not in path_nodes:
                    path_nodes.append(cid)

            path = TopologyPath(nodes=path_nodes) if path_nodes else None

            # STP 调度: 基于拓扑权重选择 Top-K 技能
            selected = scheduler.select_skills(path=path, top_k=5, auto_invoke_only=True)
            if not selected:
                return ctx

            # 格式化为 prompt 块 (前缀,优先级最高)
            lines = ["\n\n## STP 拓扑调度技能 (基于 KTG 推理路径权重)"]
            for tool in selected[:5]:
                # 计算优先级用于展示
                priority = binding.compute_priority(tool.name, path)
                desc = (tool.description or "")[:200]
                lines.append(f"- **{tool.name}** [权重={priority:.2f}]: {desc}")
            lines.append("上述技能经拓扑权重排序, 优先调用。")
            stp_block = "\n".join(lines)

            # STP 结果前缀到 skills_block (最高优先级)
            ctx.skills_block = stp_block + (ctx.skills_block or "")
            ctx.stp_selected_count = len(selected)
        except Exception as stp_exc:
            # fail-soft-with-signal: 记录降级原因, 让调用方 emit 信号
            # (对齐 Critic 的 fail-soft-with-signal 模式, 不静默吞噬)
            ctx.stp_skipped_reason = f"{type(stp_exc).__name__}: {stp_exc}"
        return ctx

    def _format_memory_block(self, ctx: WorkPipelineContext) -> str:
        from fnixagent.harness.context_budget import MEMORY_MAX, trim_text

        parts: list[str] = []
        mem = ctx.memory_context or {}
        short = mem.get("short_term") or []
        if short:
            lines = []
            for m in short[-6:]:
                role = getattr(getattr(m, "role", None), "value", None) or getattr(
                    m, "role", "user"
                )
                content = getattr(m, "content", str(m))
                lines.append(f"- {role}: {str(content)[:200]}")
            parts.append("## 短期记忆\n" + "\n".join(lines))
        long_items = mem.get("long_term") or []
        if long_items:
            lines = []
            for item in long_items[:5]:
                text = getattr(item, "content", None) or getattr(item, "text", None) or str(item)
                lines.append(f"- {str(text)[:200]}")
            parts.append("## 长期记忆召回\n" + "\n".join(lines))
        entity = mem.get("entity")
        if entity is not None:
            name = getattr(entity, "name", "")
            attrs = getattr(entity, "attributes", {}) or {}
            parts.append(f"## 用户画像\n- {name}: {attrs}")
        raw = ("\n\n" + "\n\n".join(parts)) if parts else ""
        trimmed, report = trim_text(raw, MEMORY_MAX)
        ctx.memory_budget = report.to_dict()
        return trimmed

    def _format_mode_block(self, ctx: WorkPipelineContext) -> str:
        mode = ctx.reasoning_mode
        tip = {
            ReasoningMode.REACT: "使用 ReAct：边想边调工具，小步迭代。",
            ReasoningMode.PLAN_EXECUTE: "使用 Plan&Execute：先列出简短计划，再逐步执行工具。",
            ReasoningMode.SELF_REFLECT: "使用 Self-Reflection：完成后自检完整性，不足则补工具。",
        }.get(mode, "")
        return f"\n\n## 推理模式\n{mode.value if hasattr(mode, 'value') else mode}: {tip}"

    async def step6_run_agent_stream(
        self,
        ctx: WorkPipelineContext,
        *,
        resume_from: dict | None = None,
        task_id: str | None = None,
    ) -> AsyncIterator[dict]:
        """流式执行 AgenticLoop，产出统一事件 dict。

        P0-1: task_id 透传到 AgenticLoop, 激活 CheckpointManager.append_messages
              持久化通道 。
        P0-2: Reflexion 修复循环调用本方法时, 传 resume_from 包含第一轮 messages,
              让 LLM 在修复时能看到完整上下文。
        """
        from fnixagent.services.work_agent import (
            build_work_agent_loop,
            format_ask_prompt,
            format_code_task_prompt,
            format_plan_prompt,
            normalize_work_mode,
            wrap_code_user_input,
        )

        work_mode = normalize_work_mode(ctx.work_mode)
        extra_prompt = self._format_memory_block(ctx) + self._format_mode_block(ctx)
        if work_mode == "ask":
            extra_prompt += format_ask_prompt()
        elif work_mode == "plan":
            extra_prompt += format_plan_prompt()
        elif ctx.workspace_kind == "code":
            extra_prompt += format_code_task_prompt()
        if ctx.skills_block:
            extra_prompt = extra_prompt + ctx.skills_block
        # load-bearing state 注入 (任务状态外化):
        # compaction 后此块仍会重新注入, 确保长程任务不失忆
        if ctx.todos_block:
            extra_prompt = extra_prompt + ctx.todos_block
        agent = build_work_agent_loop(
            workspace_root=ctx.workspace,
            llm=ctx.llm,
            max_steps=ctx.max_steps,
            graph_components=self.graph,
            user_input=ctx.user_input,
            prompt_extra=extra_prompt,
            work_mode=work_mode,
            max_reflect_rounds=ctx.max_reflect_rounds,
        )
        if agent is None:
            yield {"type": "error", "data": "无法初始化 Work Agent"}
            return

        agent._trace_id = ctx.trace_id
        agent._ktg_concept_path = list(ctx.concept_ids)
        agent._work_user_input = ctx.user_input

        yield {
            "type": "pipeline",
            "data": {
                "trace_id": ctx.trace_id,
                "step": 6,
                "workspace_kind": ctx.workspace_kind,
                "work_mode": work_mode,
                "reasoning_mode": (
                    ctx.reasoning_mode.value
                    if hasattr(ctx.reasoning_mode, "value")
                    else str(ctx.reasoning_mode)
                ),
                "concepts": ctx.concept_ids,
                "memory": {
                    "short": len(ctx.memory_context.get("short_term") or []),
                    "long": len(ctx.memory_context.get("long_term") or []),
                    "entity": ctx.memory_context.get("entity") is not None,
                },
            },
        }

        run_input = (
            wrap_code_user_input(ctx.user_input)
            if work_mode == "craft" and ctx.workspace_kind == "code"
            else ctx.user_input
        )
        # Unified RunEngine: Work NDJSON + SQLite checkpoint sink.
        from fnixagent.core.run import RunCheckpointStore, RunEngine
        from fnixagent.core.run.engine import work_loop_source

        # P0-1: 用 ctx.trace_id 作为 task_id (唯一任务标识), 激活 checkpoint messages 持久化
        effective_task_id = task_id or ctx.trace_id
        engine = RunEngine(store=RunCheckpointStore())
        async for event in engine.run_stream(
            work_loop_source(
                agent,
                run_input,
                resume_from=resume_from,
                task_id=effective_task_id,
            ),
            channel="work",
            run_id=ctx.trace_id,
            session_id=getattr(ctx, "session_id", None),
            # Spec 4: meta 持久化到 runs 表, resume 时用于恢复 LLM config / workspace / work_mode
            meta={
                "user_input": ctx.user_input[:500],
                "workspace": ctx.workspace,
                "work_mode": ctx.work_mode,
                "workspace_kind": ctx.workspace_kind,
                "llm": ctx.llm,
                "user_id": ctx.user_id,
            },
        ):
            yield event.to_work_dict()

        # 挂到 ctx 供后续步骤
        ctx._agent = agent  # type: ignore[attr-defined]

    def step8_security_output(self, text: str) -> str:
        if self.security is None or not text:
            return text
        try:
            reviewed = self.security.review_output(text)
            if not reviewed.passed:
                return "[内容审核:该回复包含违规内容,已被系统拦截]"
            out = reviewed.sanitized_text or text
            return self.security.desensitize(out)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning("security output review skipped: %s", exc)
            return text

    def step9_persist(
        self,
        ctx: WorkPipelineContext,
        answer: str,
        success: bool,
        tool_calls: list[dict],
        duration_ms: float,
    ) -> dict:
        """记忆保存 + MFP + KTG 快照 + 审计摘要。"""
        result: dict[str, Any] = {
            "trace_id": ctx.trace_id,
            "memory_saved": False,
            "mfp": {},
            "ktg_snapshot": None,
        }

        if self.memory is not None:
            try:
                self.memory.save(
                    ctx.session_id or ctx.trace_id,
                    Message(role=MessageRole.USER, content=ctx.user_input),
                    user_id=ctx.user_id,
                )
                self.memory.save(
                    ctx.session_id or ctx.trace_id,
                    Message(role=MessageRole.ASSISTANT, content=answer[:8000]),
                    user_id=ctx.user_id,
                )
                result["memory_saved"] = True
            except Exception as e:
                result["memory_error"] = str(e)

        if self.graph is not None:
            try:
                from fnixagent.services.work_agent import run_mfp_after_task

                result["mfp"] = run_mfp_after_task(
                    self.graph,
                    user_input=ctx.user_input,
                    success=success,
                    tool_calls=tool_calls,
                    duration_ms=duration_ms,
                    concept_path=ctx.concept_ids,
                    workspace=ctx.workspace,
                    critic_skipped=ctx.critic_skipped,
                )
            except Exception as e:
                result["mfp"] = {"error": str(e)}

        if self.topology_store is not None:
            try:
                name = self.topology_store.save_snapshot(f"work_{ctx.trace_id[:8]}")
                result["ktg_snapshot"] = name
            except Exception as e:
                result["ktg_snapshot_error"] = str(e)

        # 轻量审计
        try:
            from loguru import logger

            logger.info(
                "work_pipeline_done trace_id={} success={} tools={} mode={}",
                ctx.trace_id,
                success,
                len(tool_calls),
                ctx.reasoning_mode,
            )
        except Exception:
            pass

        try:
            from fnixagent.core.observability.metrics import record_chat_message

            record_chat_message(mode="work")
        except Exception:
            pass

        return result


def create_work_pipeline(app_state: Any = None) -> WorkPipeline:
    """从 app.state / 单例装配流水线。"""
    from fnixagent.core.config import get_config
    from fnixagent.core.memory.manager import MemoryManager
    from fnixagent.core.reasoning.selector import ReasoningSelector
    from fnixagent.core.security.engine import SecurityEngine
    from fnixagent.core.topology.store import JSONFileStore, TopologyStoreManager
    from fnixagent.services.engine import get_graph

    cfg = get_config()
    graph = None
    if app_state is not None:
        graph = getattr(app_state, "graph_components", None)
    if graph is None:
        try:
            graph = get_graph()
            if app_state is not None:
                app_state.graph_components = graph
        except Exception:
            graph = None

    memory = getattr(app_state, "memory_manager", None) if app_state else None
    if memory is None:
        memory = MemoryManager(config=cfg.memory)
        if app_state is not None:
            app_state.memory_manager = memory

    security = getattr(app_state, "security_engine", None) if app_state else None
    if security is None:
        security = SecurityEngine(config=cfg.security)
        if app_state is not None:
            app_state.security_engine = security

    selector = getattr(app_state, "reasoning_selector", None) if app_state else None
    if selector is None:
        selector = ReasoningSelector(config=cfg.reasoning)
        if app_state is not None:
            app_state.reasoning_selector = selector

    topo_mgr = getattr(app_state, "topology_store_mgr", None) if app_state else None
    if topo_mgr is None and graph is not None:
        base = os.getenv("FNIXAGENT_TOPOLOGY_DIR", "data/topology")
        store = JSONFileStore(base)
        topo_mgr = TopologyStoreManager(graph.topology_graph, store)
        try:
            topo_mgr.load_from_store()
        except Exception:
            pass
        if app_state is not None:
            app_state.topology_store_mgr = topo_mgr

    return WorkPipeline(
        graph_components=graph,
        memory_manager=memory,
        security_engine=security,
        reasoning_selector=selector,
        topology_store_mgr=topo_mgr,
    )


async def run_work_stream(
    user_input: str,
    workspace: str,
    llm: dict | None = None,
    session_id: str | None = None,
    user_id: str = "desktop",
    app_state: Any = None,
    work_mode: str = "craft",
    resume_from: dict | None = None,
    run_id_override: str | None = None,
    disabled_skills: list[str] | None = None,
) -> AsyncIterator[dict]:
    """对外统一流式入口：产出 {chunk_type, content, done, trace_id} 风格事件前的原始事件。

    Spec 4: resume_from 参数透传到 AgenticLoop.run_stream，支持长程任务从 checkpoint 恢复。
    Spec 4+: run_id_override 参数让 resume 时复用原 run_id, 实现"同一 run 续写",
             避免原 run 永远停留在 interrupted/failed 状态。
    disabled_skills: 前端技能开关传入的禁用内置技能名列表（builtin skills 注入时跳过）。
    """
    from fnixagent.harness.session import get_session_store
    from fnixagent.harness.skills_loader import format_skills_block, load_workspace_skills
    from fnixagent.harness.workspace import ensure_project_layout
    from fnixagent.services.work_agent import normalize_work_mode

    pipeline = create_work_pipeline(app_state)
    # Spec 4+: resume 时复用原 run_id, 让"同一 run 续写"语义成立
    trace_id = run_id_override or str(uuid.uuid4())
    sid = session_id or trace_id[:16]
    exec_mode = normalize_work_mode(work_mode)

    # Harness: workspace 布局 + skills
    layout: dict[str, Any] = {}
    skills_block = ""
    local_block = ""
    try:
        layout = ensure_project_layout(workspace)
        skills = load_workspace_skills(workspace)
        skills_block = format_skills_block(skills)
    except Exception:
        layout = {}

    # 产品内置技能注入（渐进式披露：索引行 + trigger 命中时展开完整 SKILL.md）
    builtin_block = ""
    try:
        from fnixagent.core.skills import format_builtin_skills_block

        builtin_block = format_builtin_skills_block(
            user_input,
            disabled=set(disabled_skills or []),
        )
    except Exception:
        builtin_block = ""
    if builtin_block:
        skills_block = skills_block + builtin_block

    context_budget: dict[str, Any] = {}
    try:
        from fnixagent.harness.local_context import local_context_prompt

        local_block = local_context_prompt(
            workspace,
            query=user_input[:500],
            session_id=sid if sid else None,
            budget_out=context_budget,
        )
    except Exception:
        local_block = ""

    mission = build_mission_schema(user_input, work_mode=exec_mode)
    mission["work_mode"] = exec_mode
    title = mission.get("title") or user_input[:48] or "新任务"

    store = get_session_store()
    existing = store.get(sid)
    if existing is None:
        store.create(
            session_id=sid,
            user_id=user_id or "desktop",
            workspace=workspace,
            title=title,
            description=user_input,
        )
    else:
        store.update(
            sid,
            status="running",
            trace_id=trace_id,
            mission=mission,
        )

    ctx = WorkPipelineContext(
        trace_id=trace_id,
        user_input=user_input,
        workspace=workspace,
        session_id=sid,
        user_id=user_id or "desktop",
        llm=llm,
        skills_block=skills_block + local_block,
        workspace_kind=str(mission.get("workspace_kind") or "general"),
        work_mode=exec_mode,
    )

    memory_summary: dict[str, Any] = {}
    try:
        from fnixagent.harness.memory import memory_injection_summary

        memory_summary = memory_injection_summary(extra=local_block)
    except Exception:
        memory_summary = {"ok": False, "blocks": []}

    yield {
        "type": "mission",
        "data": {
            "trace_id": trace_id,
            "session_id": sid,
            "harness": {
                "artifacts_dir": layout.get("artifacts_dir"),
                "skills_loaded": bool(skills_block),
                "local_index": bool(local_block),
            },
            "memory_injection": memory_summary,
            "context_budget": context_budget,
            **mission,
        },
    }

    store.update(sid, trace_id=trace_id, mission=mission, status="running")

    evo_state: dict[str, Any] = {}
    evo_state = normalize_evolution_event(
        {
            "trace_id": trace_id,
            "step": "boot",
            "ktg": pipeline.graph is not None,
            "stp": pipeline.graph is not None,
            "mfp": pipeline.graph is not None,
            "memory": pipeline.memory is not None,
            "security": pipeline.security is not None,
            "reasoning_selector": pipeline.selector is not None,
        },
        prev=evo_state,
    )
    yield {"type": "evolution", "data": evo_state}

    # 1
    ctx = pipeline.step1_security_input(ctx)
    if ctx.security_blocked:
        store.update(sid, status="failed", result=f"安全拦截: {ctx.block_reason}")
        yield {"type": "error", "data": f"安全拦截: {ctx.block_reason}"}
        return

    # 2-3
    ctx = pipeline.step2_3_memory_load(ctx)
    # 4
    tool_count = 8
    if pipeline.graph is not None:
        try:
            tool_count = len(pipeline.graph.tool_registry._tools)
        except Exception:
            pass
    ctx = pipeline.step4_select_reasoning(ctx, tool_count=tool_count)

    # Spec 7+ 四维闭环: HERA 提前到 DAAO 之前, 让命中率反馈给 DAAO 路由
    #
    hera_retrieved_count = 0
    hera_library_ref = None
    try:
        from fnixagent.core.skills import SkillLibrary

        skill_lib = SkillLibrary(workspace)
        hera_library_ref = skill_lib

        # Spec 6 闭环修复 (论文创新点 2): 拓扑权重驱动 skill 召回
        # 让 MFP 第 4 阶 (爬坡) 调的拓扑权重真正进入召回决策,
        # 闭环 KTG 权重 → skill 召回 → 下次任务感知。
        # provider 闭包: 从 pipeline.graph.topology_graph 按 skill_signature
        # 的 token 匹配同名 L2_CONCEPT 节点, 返回最大权重。
        topo_weight_provider = _build_topo_weight_provider(pipeline.graph)

        retrieved = skill_lib.retrieve_skills(
            user_input,
            top_k=3,
            workspace_kind=ctx.workspace_kind,
            topology_weight_provider=topo_weight_provider,
        )
        hera_retrieved_count = len(retrieved or [])
        if retrieved:
            skills_block_hera = skill_lib.format_skills_for_prompt(retrieved)
            if skills_block_hera:
                ctx.skills_block = (ctx.skills_block or "") + skills_block_hera
            yield {
                "type": "skill_retrieved",
                "data": {
                    "skills": [
                        {
                            "task_signature": s.task_signature,
                            "solution_summary": s.solution_summary[:200],
                            "usage_count": s.usage_count,
                            "workspace_kind": s.workspace_kind,
                        }
                        for s in retrieved
                    ],
                    "total_in_library": len(skill_lib.skills),
                },
            }
    except Exception:
        pass

    # Spec 7+ DAAO: 真路由决策器（替换原 emit-only 空壳）
    #
    # 反馈回路: HERA 高命中率 → 减少反思轮数; HERA 低命中率+高难度 → 增加反思轮数;
    #          最近失败率高 → 切换到 plan_execute
    try:
        from fnixagent.core.flywheel.daao_router import (
            compute_hera_hit_rate,
            compute_recent_failure_rate,
        )
        from fnixagent.core.flywheel.daao_router import (
            route as daao_route,
        )

        hera_hit_rate = compute_hera_hit_rate(
            retrieved_count=hera_retrieved_count,
            requested_top_k=3,
        )
        recent_failure_rate = compute_recent_failure_rate(
            workspace_kind=ctx.workspace_kind,
            library=hera_library_ref,
        )

        decision = daao_route(
            user_input=user_input,
            workspace_kind=ctx.workspace_kind,
            work_mode=ctx.work_mode,
            tool_count=tool_count,
            hera_hit_rate=hera_hit_rate,
            recent_failure_rate=recent_failure_rate,
        )

        # 真路由: 覆盖 step4 的默认选择（DAAO 是更高级的元决策层）
        mode_map = {
            "react": ReasoningMode.REACT,
            "plan_execute": ReasoningMode.PLAN_EXECUTE,
            "self_reflect": ReasoningMode.SELF_REFLECT,
        }
        new_mode = mode_map.get(decision.reasoning_mode)
        if new_mode is not None:
            ctx.reasoning_mode = new_mode
        ctx.max_steps = decision.max_steps
        ctx.max_reflect_rounds = decision.max_reflect_rounds
        ctx.difficulty_score = decision.difficulty_score
        ctx.hera_hit_rate = decision.hera_hit_rate
        ctx.recent_failure_rate = decision.recent_failure_rate
        ctx.daao_confidence = decision.confidence

        yield {
            "type": "route_decision",
            "data": {
                "route": decision.reasoning_mode,
                "max_steps": decision.max_steps,
                "max_reflect_rounds": decision.max_reflect_rounds,
                "workspace_kind": ctx.workspace_kind,
                "work_mode": (ctx.work_mode or "craft").lower(),
                "reason": decision.route_reason,
                "tool_count": tool_count,
                "difficulty_score": round(decision.difficulty_score, 3),
                "hera_hit_rate": round(decision.hera_hit_rate, 3),
                "recent_failure_rate": round(decision.recent_failure_rate, 3),
                "confidence": round(decision.confidence, 3),
            },
        }
    except Exception:
        # 降级: 退回旧 emit-only 行为
        try:
            route_reason = ""
            mode = (ctx.work_mode or "craft").lower()
            if mode == "ask":
                route_reason = "Ask 模式：少步 ReAct，专注问答，不写文件"
            elif mode == "plan":
                route_reason = "Plan 模式：Plan&Execute，先规划再执行"
            elif ctx.workspace_kind == "code":
                route_reason = f"Craft 编码任务：ReAct + {ctx.max_steps} 步上限"
            else:
                route_reason = f"通用任务：{ctx.reasoning_mode} + {ctx.max_steps} 步"
            yield {
                "type": "route_decision",
                "data": {
                    "route": (
                        ctx.reasoning_mode.value
                        if hasattr(ctx.reasoning_mode, "value")
                        else str(ctx.reasoning_mode)
                    ),
                    "max_steps": ctx.max_steps,
                    "max_reflect_rounds": ctx.max_reflect_rounds,
                    "workspace_kind": ctx.workspace_kind,
                    "work_mode": mode,
                    "reason": route_reason,
                    "tool_count": tool_count,
                    # 降级分支补齐 schema 字段 (对齐成功分支, 避免前端解析 undefined)
                    "difficulty_score": round(ctx.difficulty_score, 3),
                    "hera_hit_rate": round(ctx.hera_hit_rate, 3),
                    "recent_failure_rate": round(ctx.recent_failure_rate, 3),
                    "confidence": round(ctx.daao_confidence, 3),
                    "fallback": True,
                },
            }
        except Exception:
            pass

    # Spec 6 Self-Optimizing: few-shot 示例召回（DSPy BootstrapFewShot 风格）
    # 与 HERA SkillLibrary 互补：HERA 提供"做过类似任务"，Self-Optimizing 提供"具体怎么做"
    # 从离线沉淀的成功轨迹中召回 top-2 few-shot 示例，注入 prompt
    try:
        from fnixagent.core.intelligence.self_optimizing import SelfOptimizingLibrary

        fewshot_lib = SelfOptimizingLibrary(workspace)
        retrieved_examples = fewshot_lib.retrieve(
            user_input,
            top_k=2,
            workspace_kind=ctx.workspace_kind,
        )
        if retrieved_examples:
            fewshot_block = fewshot_lib.format_for_prompt(retrieved_examples)
            if fewshot_block:
                ctx.skills_block = (ctx.skills_block or "") + fewshot_block
            yield {
                "type": "fewshot_retrieved",
                "data": {
                    "examples": [
                        {
                            "task_signature": ex.task_signature,
                            "score": ex.score,
                            "usage_count": ex.usage_count,
                            "workspace_kind": ex.workspace_kind,
                            "tool_sequence": ex.tool_sequence[:6],
                        }
                        for ex in retrieved_examples
                    ],
                    "total_in_library": len(fewshot_lib.examples),
                },
            }
    except Exception:
        pass

    # Intelligence 七层: 执行前 Nudge 注入 (L1 循环工程层 + L5 记忆层)
    # 把记忆召回 + Nudge 推动注入 skills_block, 失败不阻塞主路径
    try:
        from fnixagent.core.intelligence.integration import IntelligenceIntegrator

        integrator = IntelligenceIntegrator(workspace)
        nudge = integrator.pre_task_nudge(
            user_input,
            {
                "workspace_kind": ctx.workspace_kind,
                "reasoning_mode": str(ctx.reasoning_mode),
            },
        )
        if nudge:
            # 截断防止 nudge 膨胀 LLM 上下文 (上限 2000 字符)
            ctx.skills_block = (ctx.skills_block or "") + nudge[:2000]
            yield {"type": "intelligence_nudge", "data": {"nudge": nudge[:200]}}
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("intelligence nudge skipped: %s", exc, exc_info=True)

    # load-bearing state 外化 (任务状态外化):
    # 从 .fnix/todos.json 加载未完成待办, 注入 prompt_extra。
    # compaction 后此块仍会重新注入, 确保长程任务不失忆。
    # , 而是快速理解当前状态"
    try:
        from fnixagent.core.skills.todos import TodoStore

        todo_store = TodoStore(workspace)
        todos_block = todo_store.format_for_prompt()
        if todos_block:
            ctx.todos_block = todos_block
            yield {
                "type": "todos_loaded",
                "data": todo_store.stats(),
            }
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("todos load skipped: %s", exc, exc_info=True)

    # 5
    ctx = pipeline.step5_ktg_stp_plan(ctx)
    # 5b: STP 真接入主路径 — 基于 KTG 推理路径用拓扑权重选择技能 (论文核心)
    ctx = pipeline.step5b_stp_select(ctx)
    if ctx.stp_selected_count > 0:
        yield {
            "type": "stp_selected",
            "data": {
                "count": ctx.stp_selected_count,
                "path_nodes": len(ctx.concept_ids),
                "ktg_paths": len(ctx.ktg_paths),
                "stp_active": True,
            },
        }
    elif ctx.stp_skipped_reason:
        # STP 降级信号 (fail-soft-with-signal, 对齐 Critic 模式)
        yield {
            "type": "stp_skipped",
            "data": {"reason": ctx.stp_skipped_reason},
        }

    evo_state = normalize_evolution_event(
        {
            "trace_id": trace_id,
            "step": "planned",
            "reasoning_mode": (
                ctx.reasoning_mode.value
                if hasattr(ctx.reasoning_mode, "value")
                else str(ctx.reasoning_mode)
            ),
            "concepts": ctx.concept_ids,
            "ktg_paths": len(ctx.ktg_paths),
            "stp_selected": ctx.stp_selected_count,
            "ktg_nodes": (
                pipeline.graph.topology_graph.stats().get("active_nodes") if pipeline.graph else 0
            ),
            "memory": {
                "short": len(ctx.memory_context.get("short_term") or []),
                "long": len(ctx.memory_context.get("long_term") or []),
                "entity": ctx.memory_context.get("entity") is not None,
            },
        },
        prev=evo_state,
    )
    yield {"type": "evolution", "data": evo_state}

    # Spec 5: 决策上下文面板 (Context Graph 范式) — 让 AI 决策可见
    # 在执行 step6 前先发出 decision_context chunk，让用户看到 AI"凭什么这么决策"
    # 三大支柱：目标 + 已知概念(KTG命中) + 风险检测(MUTEX边)
    try:
        decision_ctx = {
            "goal": ctx.user_input[:200] if ctx.user_input else "",
            "concepts": [
                {
                    "id": cid,
                    "label": cid.split(":", 1)[-1] if ":" in cid else cid,
                    "layer": "L2_CONCEPT",
                }
                for cid in ctx.concept_ids[:8]  # 最多 8 个，避免溢出
            ],
            "concept_edges": [],  # KTG 命中路径里的边（CAUSAL/DEPENDS_ON/DERIVES）
            "reasoning_mode": (
                ctx.reasoning_mode.value
                if hasattr(ctx.reasoning_mode, "value")
                else str(ctx.reasoning_mode)
            ),
            "memory_short_count": len(ctx.memory_context.get("short_term") or []),
            "memory_long_count": len(ctx.memory_context.get("long_term") or []),
            "risks": [],  # MUTEX 边检测（如果有）
        }
        # 从 ktg_paths 提取边
        for p in ctx.ktg_paths[:3]:  # 最多 3 条路径
            getattr(p, "nodes", []) or []
            edges = getattr(p, "edges", []) or []
            for e in edges:
                if isinstance(e, dict):
                    decision_ctx["concept_edges"].append(
                        {
                            "from": str(e.get("from") or e.get("source") or ""),
                            "to": str(e.get("to") or e.get("target") or ""),
                            "type": str(e.get("type") or e.get("edge_type") or "DEPENDS_ON"),
                        }
                    )
                elif hasattr(e, "from_node") and hasattr(e, "to_node"):
                    decision_ctx["concept_edges"].append(
                        {
                            "from": str(getattr(e, "from_node", "")),
                            "to": str(getattr(e, "to_node", "")),
                            "type": str(getattr(e, "edge_type", "DEPENDS_ON")),
                        }
                    )
            # MUTEX 风险检测
            for e in edges if isinstance(edges, list) else []:
                etype = ""
                if isinstance(e, dict):
                    etype = str(e.get("type") or e.get("edge_type") or "")
                elif hasattr(e, "edge_type"):
                    etype = str(getattr(e, "edge_type", ""))
                if etype == "MUTEX":
                    decision_ctx["risks"].append(
                        {
                            "type": "MUTEX",
                            "between": [
                                str(e.get("from") or e.get("source") or "")
                                if isinstance(e, dict)
                                else str(getattr(e, "from_node", "")),
                                str(e.get("to") or e.get("target") or "")
                                if isinstance(e, dict)
                                else str(getattr(e, "to_node", "")),
                            ],
                        }
                    )
        yield {"type": "decision_context", "data": decision_ctx}
    except Exception:
        pass

    # 6
    start = time.time()
    answer = ""
    tool_calls: list[dict] = []
    success = True
    artifacts: list[dict] = []

    # 提取产物路径
    async for event in pipeline.step6_run_agent_stream(ctx, resume_from=resume_from):
        et = event.get("type", "")
        data = event.get("data", "")
        if et == "text":
            answer = pipeline.step8_security_output(str(data))
            # 步骤 7：Self-Reflect 模式下追加轻量完整性提示（已在 prompt 注入；此处再审核）
            if ctx.reasoning_mode == ReasoningMode.SELF_REFLECT and answer:
                if len(answer) < 20:
                    answer = answer + "\n\n[反思] 回复过短，建议补充产物路径与验收说明。"
            yield {"type": "text", "data": answer}
        elif et == "tool_call":
            if isinstance(data, dict):
                tool_calls.append(
                    {
                        "name": data.get("name") or data.get("tool"),
                        "args": data.get("args") or data.get("arguments"),
                        "status": "running",
                    }
                )
                # write_file / edit_file 参数里的路径也记为产物
                name = str(data.get("name") or data.get("tool") or "")
                args = data.get("args") or data.get("arguments") or {}
                if name in ("write_file", "edit_file") and isinstance(args, dict):
                    p = str(
                        args.get("path") or args.get("rel_path") or args.get("file_path") or ""
                    ).strip()
                    if p:
                        merge_artifact(artifacts, p, ctx.workspace)
            yield event
        elif et == "tool_result":
            if tool_calls:
                tool_calls[-1]["status"] = "success"
            # Craft 才从工具输出解析路径；Ask/Plan 正文里的文件名不算产物
            if exec_mode == "craft":
                text = str(data)
                import re as _re

                for m in _re.finditer(
                    r"([^\s\"']+\.(?:docx|xlsx|pptx|pdf|md|csv|txt|png|jpg|jpeg|html|htm|css|js|json|svg|py))",
                    text,
                    _re.I,
                ):
                    merge_artifact(artifacts, m.group(1), ctx.workspace)
                for m in _re.finditer(r"已写入:\s*([^\s(]+)", text):
                    merge_artifact(artifacts, m.group(1).strip(), ctx.workspace)
            yield event
        elif et == "error":
            success = False
            err_text = str(data)
            store.update(sid, status="failed", result=err_text)
            if not answer:
                answer = f"执行失败：{err_text}"
            yield event
        elif et == "done":
            continue
        elif et == "reflection":
            # Spec 7+ 四维闭环: VMAO 反思 → HERA 写入"失败技能"
            #
            #   反思结果作为"失败经验"沉淀, 下次类似任务 retrieve 时召回,
            #   让 Agent 看到上次怎么失败的, 避免重复试错。
            try:
                from fnixagent.core.skills import SkillLibrary

                refl_data = data if isinstance(data, dict) else {}
                failure_skill_lib = SkillLibrary(workspace)
                # 把反思+失败工具调用作为"失败技能"写入 HERA
                # (success=False, 让 retrieve_skills 也能召回失败经验)
                failure_tool_calls = [
                    {
                        "name": f.get("name", "unknown"),
                        "success": False,
                    }
                    for f in (refl_data.get("previous_failures") or [])[:5]
                ]
                failure_skill_lib.add_new_skill(
                    user_input=f"[VMAO REFLECTION] {ctx.user_input[:200]}",
                    response=f"反思: {refl_data.get('reflection', '')[:400]}",
                    tool_calls=failure_tool_calls,
                    workspace_kind=ctx.workspace_kind,
                    success=False,
                    source="vmao_reflection",  # 标记来源, 不计入 DAAO failure_rate
                )
                yield {
                    "type": "reflection_to_skill",
                    "data": {
                        "saved": True,
                        "round": refl_data.get("round", 0),
                        "library_total": len(failure_skill_lib.skills),
                    },
                }
            except Exception:
                pass
            yield event
        else:
            yield event

    # ── 史诗级优化: Artifact Guardrail + Reflexion 修复循环 ──────────────
    #
    # 解决测试发现的 P0 问题:
    #   1. craft 模式 LLM 直接文字回答, 未调用 write_file (B1/C2/E3)
    #   2. .py 文件 AST 语法错误 (D6-1)
    #   3. HTML 任务未分离 CSS/JS (A1/A2)
    # 修复策略: guardrail 检测问题 → Reflexion prompt 反馈 → 重跑 step6 (最多 1 轮)
    if exec_mode == "craft" and success and not resume_from:
        try:
            from fnixagent.core.agent.artifact_guardrail import (
                build_reflexion_repair_prompt,
                enforce_craft_deliverables,
                should_route_short_explanation_to_ask,
            )

            guard_report = enforce_craft_deliverables(
                exec_mode=exec_mode,
                workspace_kind=ctx.workspace_kind,
                artifacts=artifacts,
                tool_calls=tool_calls,
                workspace=workspace,
            )

            yield {
                "type": "guardrail",
                "data": {
                    "passed": guard_report.passed,
                    "summary": guard_report.summary,
                    "missing": guard_report.missing_artifacts,
                    "issues": [v.issues for v in guard_report.validation_results if v.issues],
                    "validation_count": len(guard_report.validation_results),
                },
            }

            # 短任务 + 解释类 → 提示用户切到 ask 模式 (不强制重跑)
            if should_route_short_explanation_to_ask(
                user_input=ctx.user_input, work_mode=exec_mode
            ):
                tip = (
                    "\n\n💡 检测到这是一个解释类问题, 建议切换到 **Ask 模式** (问一问) "
                    "获得更快的回答; Craft 模式适合需要落盘交付的任务."
                )
                if tip.strip() not in answer:
                    answer = (answer or "") + tip
                    yield {"type": "text", "data": tip}

            # guardrail 未通过 → Reflexion 修复重跑 (最多 1 轮, 避免无限循环)
            if not guard_report.passed and not artifacts:
                repair_prompt = build_reflexion_repair_prompt(
                    user_input=ctx.user_input,
                    workspace_kind=ctx.workspace_kind,
                    report=guard_report,
                    artifacts=artifacts,
                )

                # 临时覆盖 ctx.user_input 为修复 prompt, 重跑 step6
                original_input = ctx.user_input
                ctx.user_input = repair_prompt
                # 清空上一轮的工具调用和产物, 重新收集
                prev_tool_calls = list(tool_calls)
                prev_artifacts = list(artifacts)
                tool_calls = []
                artifacts = []

                yield {
                    "type": "text",
                    "data": "\n\n🔧 Guardrail 检测到产物缺失, 触发 Reflexion 修复...",
                }

                # P0-2 修复: 从 CheckpointManager 构建 resume_from, 保留第一轮完整上下文
                # 原缺陷: 硬编码 resume_from=None 丢弃第一轮对话, LLM 修复时不知:
                #   1) 用户原始需求是什么  2) 之前生成了什么  3) 为什么失败
                # 修复策略: 从 checkpoint 读取第一轮 messages, 追加 repair_prompt 作为新 user
                #
                # _ckpt_offset: 告诉 AgenticLoop 前 N 条已在 checkpoint, 只 flush 新增的
                #   repair_prompt + 后续 assistant/tool messages
                repair_resume_from: dict | None = None
                try:
                    from fnixagent.core.checkpoint.manager import get_checkpoint_manager

                    _ckpt_mgr = get_checkpoint_manager()
                    # P1-1: 用 async 接口避免 event loop 阻塞
                    _history_msgs = await _ckpt_mgr.aget_messages(ctx.trace_id)
                    if _history_msgs:
                        # 追加 repair_prompt (ctx.user_input 已被覆盖为 repair_prompt) 作为新 user
                        _history_with_repair = list(_history_msgs) + [
                            {"role": "user", "content": ctx.user_input}
                        ]
                        repair_resume_from = {
                            "messages": _history_with_repair,
                            "completed_steps": len(_history_msgs),
                            "artifacts": [
                                {"path": a.get("path", ""), "name": a.get("name", "")}
                                for a in prev_artifacts
                            ],
                            # P0-1: 前 len(_history_msgs) 条已在 checkpoint, 不重复写
                            "_ckpt_offset": len(_history_msgs),
                        }
                except Exception as _resume_err:
                    import logging as _logging

                    _logging.getLogger(__name__).warning(
                        "P0-2: 构建 Reflexion repair resume_from 失败, 降级为空上下文: %s",
                        _resume_err,
                    )

                async for event in pipeline.step6_run_agent_stream(
                    ctx, resume_from=repair_resume_from
                ):
                    et = event.get("type", "")
                    data = event.get("data", "")
                    if et == "text":
                        repair_answer = pipeline.step8_security_output(str(data))
                        if repair_answer and repair_answer.strip():
                            answer = repair_answer
                        yield {"type": "text", "data": repair_answer}
                    elif et == "tool_call":
                        if isinstance(data, dict):
                            tool_calls.append(
                                {
                                    "name": data.get("name") or data.get("tool"),
                                    "args": data.get("args") or data.get("arguments"),
                                    "status": "running",
                                }
                            )
                            name = str(data.get("name") or data.get("tool") or "")
                            args = data.get("args") or data.get("arguments") or {}
                            if name in ("write_file", "edit_file") and isinstance(args, dict):
                                p = str(
                                    args.get("path")
                                    or args.get("rel_path")
                                    or args.get("file_path")
                                    or ""
                                ).strip()
                                if p:
                                    merge_artifact(artifacts, p, ctx.workspace)
                        yield event
                    elif et == "tool_result":
                        if tool_calls:
                            tool_calls[-1]["status"] = "success"
                        if exec_mode == "craft":
                            text = str(data)
                            import re as _re2

                            for m in _re2.finditer(
                                r"([^\s\"']+\.(?:docx|xlsx|pptx|pdf|md|csv|txt|png|jpg|jpeg|html|htm|css|js|json|svg|py))",
                                text,
                                _re2.I,
                            ):
                                merge_artifact(artifacts, m.group(1), ctx.workspace)
                        yield event
                    elif et == "error":
                        success = False
                        yield event
                    elif et == "done":
                        continue
                    else:
                        yield event

                # 恢复 ctx.user_input
                ctx.user_input = original_input

                # 二次 guardrail 校验
                guard_report2 = enforce_craft_deliverables(
                    exec_mode=exec_mode,
                    workspace_kind=ctx.workspace_kind,
                    artifacts=artifacts,
                    tool_calls=tool_calls,
                    workspace=workspace,
                )
                yield {
                    "type": "guardrail",
                    "data": {
                        "passed": guard_report2.passed,
                        "summary": f"Reflexion 修复后: {guard_report2.summary}",
                        "repair_attempt": True,
                        "artifacts_after": len(artifacts),
                    },
                }
                # 合并历史工具调用 (保留完整轨迹)
                tool_calls = prev_tool_calls + tool_calls
        except Exception as _g_exc:
            import traceback as _tb

            _tb_text = _tb.format_exc()
            print(f"[guardrail ERROR] {_g_exc.__class__.__name__}: {_g_exc}")
            print(_tb_text)
            # 仍然发一个 guardrail 事件, 让前端看到失败
            try:
                yield {
                    "type": "guardrail",
                    "data": {
                        "passed": False,
                        "summary": f"guardrail 异常: {_g_exc.__class__.__name__}: {str(_g_exc)[:200]}",
                        "missing": [],
                        "issues": [[_tb_text[:500]]],
                        "validation_count": 0,
                        "error": True,
                    },
                }
            except Exception:
                pass  # guardrail 失败不阻断主流程

    # Spec 5 独立 Critic Agent: craft 模式 + 有产物 → 语义审查
    # 解决 VMAO 盲点: "工具调用成功但产物语义错误" (如生成了错误代码但 write_file 成功)
    #
    #   Critic 是独立第三方视角, 不是 self-reflect
    if exec_mode == "craft" and success and artifacts and not resume_from:
        try:
            from fnixagent.core.agent.critic import CriticAgent

            critic = CriticAgent(llm_config=ctx.llm)
            tool_calls_summary = [
                {
                    "name": tc.get("name", ""),
                    "success": tc.get("status") == "success",
                }
                for tc in tool_calls[:15]
            ]
            # 心跳保活: critic LLM 审查可能数十秒静默, 每 10s emit 一条
            # heartbeat 事件, 避免 NDJSON 长连接在长静默中被传输层重置
            # (Windows teardown 竞态); 前端与门禁脚本忽略该事件类型。
            critic_task = asyncio.ensure_future(
                critic.review(
                    user_input=ctx.user_input,
                    artifacts=artifacts,
                    tool_calls_summary=tool_calls_summary,
                    answer=answer,
                )
            )
            while not critic_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(critic_task), timeout=10.0)
                except TimeoutError:
                    yield {"type": "heartbeat", "data": {"phase": "critic"}}
            verdict = await critic_task
            if verdict is not None:
                # Spec 7 fail-soft-with-signal: 检测哨兵值, emit 可观测信号
                # score==-1.0 表示审查未完成 (LLM 故障/解析失败),
                # 不阻断主流程但 emit critic_skipped 事件, 避免静默漏检。
                # MFP 第 3 阶 (元反思) 可消费此信号统计 critic.skip_rate。
                if verdict.score == -1.0:
                    ctx.critic_skipped = True  # Spec 7 闭环: 记录到 ctx, step9 写入 TraceRecord
                    yield {
                        "type": "critic_skipped",
                        "data": {
                            "reason": "review_incomplete",
                            "issues": verdict.issues[:3],
                        },
                    }
                else:
                    yield {
                        "type": "critic_verdict",
                        "data": {
                            "passed": verdict.passed,
                            "score": verdict.score,
                            "issues": verdict.issues[:5],
                            "suggestions": verdict.suggestions[:5],
                        },
                    }
                    if not verdict.passed and verdict.suggestions:
                        # 注入修改建议到 answer, 让用户看到 Critic 的反馈
                        suggestions_text = "\n".join(f"- {s}" for s in verdict.suggestions[:3])
                        critic_note = f"\n\n**Critic 审查建议（独立第三方）:**\n{suggestions_text}"
                        answer = (answer or "") + critic_note
                        yield {"type": "text", "data": critic_note}
        except Exception as critic_exc:
            # Spec 7 fail-soft-with-signal: Critic 异常时 emit 信号, 不静默
            # 原设计 except: pass 会吞掉所有异常, 形成静默漏检。
            # 现改为 emit critic_skipped 事件, 让"未审查率"可观测。
            ctx.critic_skipped = True  # Spec 7 闭环: 记录到 ctx, step9 写入 TraceRecord
            yield {
                "type": "critic_skipped",
                "data": {
                    "reason": "review_exception",
                    "error": f"{type(critic_exc).__name__}: {critic_exc}",
                },
            }

    # 磁盘扫描兜底：仅 Craft 模式
    if exec_mode == "craft":
        for art in scan_recent_artifacts(workspace, since_ts=start):
            n_before = len(artifacts)
            merge_artifact(artifacts, art["path"], workspace)
            if len(artifacts) > n_before:
                yield {"type": "artifact", "data": artifacts[-1]}

    # Artifact-first 交付判定(生产 UX 保障): Craft 模式以交付物为验收标准。
    # 执行循环未自主终止(超过步数上限)但产物已真实落盘时, 降级为交付成功,
    # 避免「任务实际完成却判失败」的用户可见回归; 回复中如实标注未终止原因。
    if (
        exec_mode == "craft"
        and artifacts
        and success is False
        and isinstance(answer, str)
        and answer.startswith("执行失败：")
        and "超过最大步数" in answer
    ):
        success = True
        delivered_paths = "\n".join(
            f"- {a.get('path', '')}" for a in artifacts[:10] if isinstance(a, dict)
        )
        reason = answer[len("执行失败：") :].strip()
        answer = (
            f"产物已交付（{reason}，但交付物已生成，不影响结果）。\n\n交付物:\n{delivered_paths}"
        )
        yield {"type": "text", "data": answer}

    duration_ms = (time.time() - start) * 1000
    # 编码任务若未落盘，明确提示（对齐工程实践 Craft 必须交付）
    wrote_code = any(str(t.get("name") or "") in ("write_file", "edit_file") for t in tool_calls)
    if (
        exec_mode == "craft"
        and ctx.workspace_kind == "code"
        and success
        and not artifacts
        and not wrote_code
    ):
        tip = (
            "\n\n⚠️ 未检测到写入文件。Craft 编码任务应调用 write_file 落盘到 "
            "`.fnix/artifacts/`。可重试；已 Open project 时同一 Chat 内可 preview → Accept。"
        )
        if tip.strip() not in answer:
            answer = (answer or "") + tip
            yield {"type": "text", "data": tip}

    # 有工具轨迹但无最终正文时，用摘要兜底（错误文案已在上方写入 answer）
    if not answer:
        if success and tool_calls:
            names = ", ".join(
                str(t.get("name") or "?") for t in tool_calls[-5:] if isinstance(t, dict)
            )
            answer = f"已执行工具：{names}" if names else "任务已完成"
        else:
            answer = "任务已完成" if success else "任务未完成"
        yield {"type": "text", "data": answer}
    elif success is False and answer.startswith("执行失败："):
        # 错误路径已有 answer，再发一条 text 供前端展示（若前面只发了 error 事件）
        yield {"type": "text", "data": answer}

    # 9
    persist = pipeline.step9_persist(
        ctx,
        answer=answer,
        success=success,
        tool_calls=tool_calls,
        duration_ms=duration_ms,
    )

    # Spec 6 HERA: 任务成功后自动捕获技能（Voyager SkillManager.add_new_skill 模式）
    # 把成功的解决方案存入技能库，下次类似任务可召回复用
    try:
        from fnixagent.core.skills import SkillLibrary

        skill_lib = SkillLibrary(workspace)
        new_skill = skill_lib.add_new_skill(
            user_input=ctx.user_input,
            response=answer,
            tool_calls=tool_calls,
            workspace_kind=ctx.workspace_kind,
            success=success,
        )
        if new_skill:
            yield {
                "type": "skill_saved",
                "data": {
                    "skill_id": new_skill.skill_id,
                    "task_signature": new_skill.task_signature,
                    "saved": True,
                    "library_total": len(skill_lib.skills),
                },
            }
    except Exception:
        pass

    # Spec 6 Self-Optimizing: 离线轨迹沉淀（DSPy BootstrapFewShot 精简版）
    # 把成功轨迹的 (input, output, tool_sequence, score) 沉淀为 few-shot 示例
    # score >= 0.6 才入库
    try:
        from fnixagent.core.intelligence.self_optimizing import (
            SelfOptimizingLibrary,
            extract_examples_from_trace,
        )

        fewshot_lib = SelfOptimizingLibrary(workspace)
        new_example = extract_examples_from_trace(
            user_input=ctx.user_input,
            response=answer,
            tool_calls=tool_calls,
            success=success,
            duration_ms=duration_ms,
            workspace_kind=ctx.workspace_kind,
        )
        if new_example:
            added = fewshot_lib.add(new_example)
            if added:
                yield {
                    "type": "fewshot_saved",
                    "data": {
                        "example_id": new_example.example_id,
                        "task_signature": new_example.task_signature,
                        "score": new_example.score,
                        "saved": True,
                        "library_total": len(fewshot_lib.examples),
                    },
                }
    except Exception:
        pass

    # Intelligence 七层: MFP 之后的深度进化 (L3安全 + L7审判 + L2进化 + L6技能 + L5记忆)
    # 协调七层闭环, 失败不阻塞主路径
    try:
        from fnixagent.core.intelligence.integration import IntelligenceIntegrator

        integrator = IntelligenceIntegrator(workspace)
        intel_result = integrator.post_evolution(
            trace_record={
                "user_input": ctx.user_input,
                "tool_calls": tool_calls,
                "success": success,
                "duration_ms": duration_ms,
                "workspace_kind": ctx.workspace_kind,
            },
            mfp_result=persist.get("mfp") or {},
        )
        if intel_result:
            yield {"type": "intelligence_evolved", "data": intel_result}
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning(
            "intelligence post_evolution skipped: %s", exc, exc_info=True
        )

    evo_state = normalize_evolution_event(
        {
            "trace_id": trace_id,
            "step": "done",
            "mfp_result": persist.get("mfp"),
            "persist": persist,
        },
        prev=evo_state,
    )
    yield {"type": "evolution", "data": evo_state}
    yield {
        "type": "done",
        "data": {
            "result": answer,
            "artifacts": artifacts,
            "workspace_kind": ctx.workspace_kind,
            "trace_id": trace_id,
            "session_id": sid,
            "mfp": persist.get("mfp"),
            "persist": persist,
        },
    }

    store.update(
        sid,
        status="completed" if success else "failed",
        trace_id=trace_id,
        result=answer,
        artifacts=artifacts,
    )


__all__ = [
    "WorkPipeline",
    "WorkPipelineContext",
    "create_work_pipeline",
    "normalize_artifact_path",
    "normalize_evolution_event",
    "run_work_stream",
]
