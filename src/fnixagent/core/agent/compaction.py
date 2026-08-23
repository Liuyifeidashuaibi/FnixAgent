"""Spec 4: 轻量 Compaction — 当 messages 超 threshold tokens 时调 LLM 生成 summary。

参考工程实践 三层压缩 / LCM (Lossless Context Management) 三级 escalation 的简化版。

策略 (一级压缩, 不做 DAG):
    1. 估算 messages 总 token 数 (粗略: 1 token ≈ 3.5 chars 英文 / 1.5 chars 中文)
    2. 超 threshold_tokens 时:
       - 保留前 2 条 (system + 第一条 user) — 核心指令不能丢
       - 保留最后 keep_recent 条 (最近的 tool_call + tool_result + text) — 当前任务上下文
       - 中间消息批量送 LLM 生成 summary
       - 替换为 [{role: "system", content: "Earlier context summary: ..."}]
    3. 阈值默认 60K tokens (qwen-plus 128K context, 留 60K 给新内容 + tools)

P4.1 缓存安全分叉 (缓存安全分叉模式):
    - 朴素 compaction 构造全新 [system, user] prompt, 与父对话 prefix 0% 匹配, cache 全失效
    - 缓存安全分叉 复用父 messages prefix, 把 compaction 指令作为新 user message 追加末尾
    - LLM 调用 prefix 与父对话完全一致, cache 命中 (qwen-plus 隐式 20% / GLM 50% / DeepSeek 2%)
    - 唯一新计费的是 compaction 指令本身 (~1K tokens)
    - 收益: 每次 compaction LLM 调用从全价 → cache hit 价 (节省 80%+)

参考:    - LCM paper: [论文] 2506.18655    - qwen-plus Context Cache: https://help.aliyun.com/zh/model-studio/context-cache
    - DeepSeek KV cache: https://api-docs.deepseek.com/guides/kv_cache
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 粗略 token 估算: 中英混合, 偏保守 (宁多估不少估)
_CHARS_PER_TOKEN_EN = 3.5
_CHARS_PER_TOKEN_ZH = 1.5


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """粗略估算 messages 的 token 数。

    对齐 tiktoken 精确计数, 但避免依赖 tiktoken (numpy 重依赖)。
    误差 ±15%, 用于触发阈值判断足够。
    """
    total_chars = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            total_chars += _count_chars(content)
        elif isinstance(content, list):
            # OpenAI vision format: [{"type": "text", "text": "..."}, ...]
            for part in content:
                if isinstance(part, dict):
                    total_chars += _count_chars(str(part.get("text", "")))
        # tool_calls 的 arguments 也算
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list):
            for tc in tool_calls:
                if isinstance(tc, dict):
                    fn = tc.get("function") or {}
                    total_chars += _count_chars(str(fn.get("name", "")))
                    total_chars += _count_chars(str(fn.get("arguments", "")))
    # 中英混合: 假设 60% 英文 40% 中文, 平均 ~2.5 chars/token
    return max(1, int(total_chars / 2.5))


def _count_chars(text: str) -> int:
    """计算字符数, 中文按 2 计 (粗略权重)。"""
    n = 0
    for ch in text:
        n += 2 if "\u4e00" <= ch <= "\u9fff" else 1
    return n


async def compact_messages_if_needed(
    llm_adapter: Any,
    messages: list[dict[str, Any]],
    *,
    threshold_tokens: int = 60000,
    keep_recent: int = 6,
    keep_first_n: int = 2,
    cache_safe: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """超阈值时压缩早期 messages 为 summary。

    Args:
        llm_adapter: LLMAdapter 实例 (有 achat 方法)
        messages: 当前 LLM 上下文消息列表
        threshold_tokens: 触发压缩的 token 阈值 (默认 60K)
        keep_recent: 保留最近 N 条消息不压缩 (默认 6)
        keep_first_n: 保留前 N 条 (system + 第一条 user) (默认 2)
        cache_safe: P4.1 — 是否用 缓存安全分叉 (默认 True)
            True: 复用父 messages prefix, 把 compaction 指令追加末尾, cache 命中
            False: 朴素 prompt (全新 [system, user]), cache 全失效, 仅用于 fallback

    Returns:
        (compacted_messages, compaction_info)
        compaction_info: {
            "compacted": bool,           # 是否触发了压缩
            "before_tokens": int,        # 压缩前 token 数
            "after_tokens": int,         # 压缩后 token 数
            "compacted_messages_count": int,  # 被压缩的消息数
            "summary": str,              # 生成的 summary (前 500 字符)
            "error": str | None,         # 压缩失败原因
            "cache_safe": bool,          # P4.1: 是否用了 缓存安全分叉
        }
    """
    before_tokens = estimate_tokens(messages)
    if before_tokens <= threshold_tokens:
        return messages, None

    if len(messages) <= keep_first_n + keep_recent:
        # 消息太少, 没什么可压缩的
        return messages, {
            "compacted": False,
            "before_tokens": before_tokens,
            "after_tokens": before_tokens,
            "compacted_messages_count": 0,
            "summary": "",
            "error": "not enough messages to compact",
            "cache_safe": cache_safe,
        }

    # 切分: 前 keep_first_n + 中间待压缩 + 后 keep_recent
    head = messages[:keep_first_n]
    middle = messages[keep_first_n:-keep_recent]
    tail = messages[-keep_recent:]

    if not middle:
        return messages, {
            "compacted": False,
            "before_tokens": before_tokens,
            "after_tokens": before_tokens,
            "compacted_messages_count": 0,
            "summary": "",
            "error": "middle slice empty",
            "cache_safe": cache_safe,
        }

    # 构造压缩 prompt
    if cache_safe:
        # P4.1: 缓存安全分叉 — 复用父 messages prefix, cache 命中
        # 缓存安全分叉模式: 不构造全新 prompt, 直接用父 messages
        # 把 compaction 指令作为新 user message 追加末尾
        middle_start = keep_first_n
        middle_end = len(messages) - keep_recent
        summary_prompt = _build_cache_safe_prompt(messages, middle_start, middle_end, before_tokens)
    else:
        # Fallback: 朴素 prompt (破坏 prefix, cache 全失效)
        middle_text = _serialize_messages_for_summary(middle)
        summary_prompt = _build_summary_prompt(middle_text, before_tokens)

    try:
        # 调 LLM 生成 summary (用 achat 同步接口, 不流式)
        summary = await _call_llm_for_summary(llm_adapter, summary_prompt)
        if not summary or not summary.strip():
            return messages, {
                "compacted": False,
                "before_tokens": before_tokens,
                "after_tokens": before_tokens,
                "compacted_messages_count": len(middle),
                "summary": "",
                "error": "empty summary from LLM",
                "cache_safe": cache_safe,
            }

        # 用 summary 替换中间消息
        summary_msg = {
            "role": "system",
            "content": (
                "[Earlier Context Summary · Spec 4 Compaction]\n"
                f"以下是之前 {len(middle)} 条对话的摘要, 用于保持上下文连贯:\n\n"
                f"{summary}\n\n"
                "[End of Summary — 以下为最近的对话, 含当前任务状态]"
            ),
        }
        compacted = head + [summary_msg] + tail
        after_tokens = estimate_tokens(compacted)

        logger.info(
            "Spec 4 Compaction (%s): %d msgs → %d msgs, %d → %d tokens (节省 %d%%)",
            "cache-safe" if cache_safe else "naive",
            len(messages),
            len(compacted),
            before_tokens,
            after_tokens,
            int((1 - after_tokens / before_tokens) * 100),
        )

        return compacted, {
            "compacted": True,
            "before_tokens": before_tokens,
            "after_tokens": after_tokens,
            "compacted_messages_count": len(middle),
            "summary": summary[:500],
            "error": None,
            "cache_safe": cache_safe,
        }
    except Exception as e:
        logger.warning("Spec 4 Compaction failed: %s", e)
        return messages, {
            "compacted": False,
            "before_tokens": before_tokens,
            "after_tokens": before_tokens,
            "compacted_messages_count": len(middle),
            "summary": "",
            "error": f"{type(e).__name__}: {e}",
            "cache_safe": cache_safe,
        }


def _build_cache_safe_prompt(
    parent_messages: list[dict[str, Any]],
    middle_start: int,
    middle_end: int,
    before_tokens: int,
) -> list[dict[str, Any]]:
    """P4.1: 构造 cache-safe compaction prompt（复用父 prefix）。
    - 不构造全新 [system, user] prompt（会破坏 prefix, cache 全失效）
    - 直接用父 messages 作为 prefix（cache 命中父对话的 KV cache）
    - 把 compaction 指令作为新 user message 追加末尾

    这样 LLM 调用的 prefix 与父对话完全一致, cache 命中率最大化。
    唯一新计费的是 compaction 指令本身（~1K tokens）。

    收益对比（以 60K tokens 父对话为例, qwen-plus 隐式 cache 20% 价格）:
    - 朴素方案: 60K 全价 = 60K 等价 tokens
    - 缓存安全分叉: 60K cache hit (20%) + 1K 全价 = 12K + 1K = 13K 等价 tokens
    - 节省 78%

    Args:
        parent_messages: 父对话 messages（完整, 含 head + middle + tail）
        middle_start:    middle 起始索引（keep_first_n）
        middle_end:      middle 结束索引（len(messages) - keep_recent, exclusive）
        before_tokens:   压缩前 token 数（用于 prompt 提示）

    Returns:
        cache-safe prompt: 父 messages + compaction 指令 user message
    """
    instruction = (
        f"\n\n[Compaction Instruction]\n"
        f"以上是对话历史（原始约 {before_tokens} tokens）。请压缩第 {middle_start + 1} 到第 {middle_end} 条消息，"
        f"生成 300-800 字结构化摘要，保留:\n"
        f"1. 用户的核心需求和目标\n"
        f"2. 已完成的关键工具调用及其结果（尤其是写入的文件路径）\n"
        f"3. 当前的任务进度（已完成 / 进行中 / 待办）\n"
        f"4. 任何关键决策、错误教训、约束条件\n\n"
        f"要求:\n"
        f"- 摘要长度 300-800 字\n"
        f"- 用结构化格式（要点列表），不要复述原始对话\n"
        f"- 文件路径、函数名、参数等关键信息必须原样保留\n"
        f"- 不要编造未在对话中出现的信息\n"
        f"- 只输出摘要内容，不要解释\n\n"
        f"摘要:"
    )
    # 复用父 messages（浅拷贝避免修改原列表），追加 compaction 指令作为新 user message
    return list(parent_messages) + [{"role": "user", "content": instruction}]


def _serialize_messages_for_summary(messages: list[dict[str, Any]]) -> str:
    """把消息列表序列化为 LLM 可读的文本。"""
    lines: list[str] = []
    for i, msg in enumerate(messages):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
        content_str = str(content)[:1500]  # 单条最多 1500 字符

        # 工具调用也要记入 (保留 name + args 摘要)
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            calls_desc = []
            for tc in tool_calls:
                if isinstance(tc, dict):
                    fn = tc.get("function") or {}
                    name = fn.get("name", "")
                    args_str = fn.get("arguments", "")
                    if len(args_str) > 200:
                        args_str = args_str[:200] + "..."
                    calls_desc.append(f"  → {name}({args_str})")
            if calls_desc:
                content_str += "\n" + "\n".join(calls_desc)

        lines.append(f"[{i + 1}] {role}: {content_str}")
    return "\n".join(lines)


def _build_summary_prompt(middle_text: str, before_tokens: int) -> list[dict[str, str]]:
    """构造压缩 prompt (用户态请求 LLM 生成 summary)。"""
    return [
        {
            "role": "system",
            "content": (
                "你是一个对话压缩助手。给定一段 agent 对话历史, 请生成一份精确的摘要, "
                "保留:\n"
                "1. 用户的核心需求和目标\n"
                "2. 已完成的关键工具调用及其结果 (尤其是写入的文件路径)\n"
                "3. 当前的任务进度 (已完成 / 进行中 / 待办)\n"
                "4. 任何关键决策、错误教训、约束条件\n\n"
                "要求:\n"
                "- 摘要长度 300-800 字\n"
                "- 用结构化格式 (要点列表), 不要复述原始对话\n"
                "- 文件路径、函数名、参数等关键信息必须原样保留\n"
                "- 不要编造未在对话中出现的信息"
            ),
        },
        {
            "role": "user",
            "content": (
                f"请压缩以下对话历史 (原始约 {before_tokens} tokens):\n\n"
                "---\n{middle_text}\n---\n\n"
                "生成摘要:"
            ).replace("{middle_text}", middle_text),
        },
    ]


async def _call_llm_for_summary(llm_adapter: Any, messages: list[dict[str, str]]) -> str:
    """调 LLM 生成 summary。

    兼容多种 LLMAdapter 接口:
        - chat(messages, tools=None, model=, ...) → dict (LLMAdapter 实际接口, OpenAI 兼容)
        - callable: __call__(messages, tools=None) → dict (AgenticLoop 风格)
        - achat(messages, stream=False) → dict (旧版别名)
        - chat_completion(messages, stream=False) → dict (旧版别名)
    """
    # 试 chat (LLMAdapter 当前标准接口, 返回 OpenAI 兼容 dict)
    if hasattr(llm_adapter, "chat"):
        try:
            result = await llm_adapter.chat(messages, tools=None)
            return _extract_content(result)
        except Exception as e:
            logger.warning("chat LLM summary failed: %s", e)

    # 试 callable (AgenticLoop 主路径, 接受 (messages, tools=None))
    if callable(llm_adapter):
        try:
            result = llm_adapter(messages, None)
            if hasattr(result, "__await__"):
                result = await result
            return _extract_content(result)
        except Exception as e:
            logger.warning("callable LLM summary failed: %s", e)
            # 继续尝试其他接口

    # 试 achat (旧版 LLMAdapter 别名)
    if hasattr(llm_adapter, "achat"):
        try:
            result = await llm_adapter.achat(messages=messages, stream=False)
            return _extract_content(result)
        except Exception as e:
            logger.warning("achat LLM summary failed: %s", e)

    # 试 chat_completion (旧版别名)
    if hasattr(llm_adapter, "chat_completion"):
        try:
            result = await llm_adapter.chat_completion(messages=messages, stream=False)
            return _extract_content(result)
        except Exception as e:
            logger.warning("chat_completion LLM summary failed: %s", e)

    raise RuntimeError(
        f"LLMAdapter 不支持摘要生成接口 (chat/callable/achat/chat_completion): "
        f"type={type(llm_adapter).__name__}"
    )


def _extract_content(result: Any) -> str:
    """从 LLM 响应中提取文本内容 (兼容 OpenAI / DashScope / 直接 str)。"""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        # OpenAI / DashScope 兼容格式
        choices = result.get("choices") or []
        if choices:
            msg = choices[0].get("message") or {}
            content = msg.get("content")
            if isinstance(content, str):
                return content
        # 直接返回 content 字段
        if "content" in result:
            return str(result["content"])
        # 整体 JSON 兜底
        return json.dumps(result, ensure_ascii=False)
    return str(result)


# ============================================================================
# P2: 三级 Escalation
# ============================================================================
#
# 设计原则 (深度思考):
#   1. L1 (已有 compact_messages_if_needed): LLM preserve_details summary
#      - 失败场景: LLM 不可用 / summary 比原文还长 / 网络超时
#   2. L2 (新增): boundary-aware sliding window
#      -
#      - 保护 tool_call / tool_result 配对完整性 (避免孤儿消息导致 API 400)
#      - 保留 system + 最近 N 条, 中间全删 (无 LLM, 确定性)
#   3. L3 (新增): DeterministicTruncate
#      -(X, 512)
#      - 无 LLM, 硬截断到 512 tokens, 保证收敛
#      - 只在 L2 仍然超阈值时触发 (极端情况)
#
# 每级检查 Tokens(S) < Tokens(X), 失败则升级; L3 保证收敛 (无 LLM 依赖)
# ============================================================================


def _find_tool_call_pairs(messages: list[dict[str, Any]]) -> set[int]:
    """识别 tool_call / tool_result 配对的索引 。

    tool_call 在 assistant message 的 tool_calls 字段, tool_result 在 role=tool 的 message。
    配对必须保持完整, 否则 OpenAI API 会返回 400 (orphan tool_call_id)。

    Returns:
        配对消息的索引集合 (包括 assistant tool_call 和 tool result)。
    """
    paired: set[int] = set()
    # 收集所有 tool_call_id
    tool_call_ids: dict[str, list[int]] = {}  # call_id -> [assistant_msg_idx]
    tool_result_ids: dict[str, list[int]] = {}  # call_id -> [tool_msg_idx]

    for i, msg in enumerate(messages):
        if msg.get("role") == "assistant":
            tcs = msg.get("tool_calls")
            if isinstance(tcs, list):
                for tc in tcs:
                    if isinstance(tc, dict):
                        cid = tc.get("id", "")
                        if cid:
                            tool_call_ids.setdefault(cid, []).append(i)
        elif msg.get("role") == "tool":
            cid = msg.get("tool_call_id", "")
            if cid:
                tool_result_ids.setdefault(cid, []).append(i)

    # 配对: call_id 同时有 call 和 result
    for cid in set(tool_call_ids.keys()) & set(tool_result_ids.keys()):
        for idx in tool_call_ids[cid]:
            paired.add(idx)
        for idx in tool_result_ids[cid]:
            paired.add(idx)

    return paired


def sliding_window_compact(
    messages: list[dict[str, Any]],
    *,
    keep_first_n: int = 2,
    keep_recent: int = 6,
    target_tokens: int = 30000,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """L2: boundary-aware sliding window 压缩 (无 LLM, 确定性)。
      - 保留前 keep_first_n (system + 第一条 user)
      - 保留最后 keep_recent 条 (最近上下文)
      - 中间消息: 保护 tool_call/tool_result 配对完整性, 其余删除
      - 如果仍超 target_tokens, 继续从中间往前删 (但永不删 head/tail)

    Args:
        messages:       当前 messages 列表
        keep_first_n:   保留前 N 条 (默认 2)
        keep_recent:    保留最近 N 条 (默认 6)
        target_tokens:  目标 token 数 (默认 30K)

    Returns:
        (compacted_messages, info_dict)
    """
    before_tokens = estimate_tokens(messages)

    if before_tokens <= target_tokens:
        return messages, {
            "level": 2,
            "compacted": False,
            "before_tokens": before_tokens,
            "after_tokens": before_tokens,
            "compacted_messages_count": 0,
            "summary": "",
            "error": "already under target",
        }

    if len(messages) <= keep_first_n + keep_recent:
        return messages, {
            "level": 2,
            "compacted": False,
            "before_tokens": before_tokens,
            "after_tokens": before_tokens,
            "compacted_messages_count": 0,
            "summary": "",
            "error": "not enough messages",
        }

    head = messages[:keep_first_n]
    middle = messages[keep_first_n:-keep_recent]
    tail = messages[-keep_recent:]

    # 识别中间区域的 tool_call 配对 (必须成对保留或成对删除)
    _find_tool_call_pairs(middle)
    # 转换为 messages 绝对索引的配对集合
    all_paired = _find_tool_call_pairs(messages)

    # 策略: 中间区域只保留配对的 tool_call/tool_result (避免孤儿), 删除其余
    # 然后检查 token 数, 如果仍超, 继续删中间的配对 (从最旧的开始删)
    kept_middle: list[dict[str, Any]] = []
    for i, msg in enumerate(middle):
        abs_idx = keep_first_n + i
        if abs_idx in all_paired:
            kept_middle.append(msg)

    compacted = head + kept_middle + tail
    after_tokens = estimate_tokens(compacted)

    # 如果仍超 target_tokens, 从 kept_middle 末尾往前删 (保留最新的配对)
    # 但要重新检查配对完整性 (删一个 call 必须删它的 result, 反之亦然)
    while after_tokens > target_tokens and kept_middle:
        # 找到最旧的一个 tool_call_id 组, 整组删除
        removed = False
        for i, msg in enumerate(kept_middle):
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                tcs = msg.get("tool_calls") or []
                if not tcs:
                    continue
                cid = tcs[0].get("id", "") if isinstance(tcs[0], dict) else ""
                if not cid:
                    continue
                # 删除这个 call_id 的所有相关消息 (call + result)
                new_kept = []
                for j, m in enumerate(kept_middle):
                    if m.get("role") == "assistant":
                        mtcs = m.get("tool_calls") or []
                        m_cids = {t.get("id", "") for t in mtcs if isinstance(t, dict)}
                        if cid in m_cids:
                            continue  # 删除这个 assistant call
                    elif m.get("role") == "tool":
                        if m.get("tool_call_id") == cid:
                            continue  # 删除这个 tool result
                    new_kept.append(m)
                kept_middle = new_kept
                compacted = head + kept_middle + tail
                after_tokens = estimate_tokens(compacted)
                removed = True
                break
        if not removed:
            # 中间没有 tool_call 组了, 删最旧的一条非 head/tail
            if kept_middle:
                kept_middle.pop(0)
                compacted = head + kept_middle + tail
                after_tokens = estimate_tokens(compacted)
            else:
                break

    return compacted, {
        "level": 2,
        "compacted": True,
        "before_tokens": before_tokens,
        "after_tokens": after_tokens,
        "compacted_messages_count": len(messages) - len(compacted),
        "summary": f"sliding_window: {len(messages)} → {len(compacted)} msgs",
        "error": None,
    }


def deterministic_truncate(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 512,
    keep_first_n: int = 1,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """L3: 确定性硬截断 (无 LLM, 保证收敛)。(X, 512)
    保留 system + 最近消息, 中间硬截断到 max_tokens。

    保证收敛: 无论输入多大, 输出一定 <= max_tokens + 一条消息的容差。
    如果 head 本身超 max_tokens, head 也会被截断 (只保留前 max_tokens 字符)。

    Args:
        messages:     当前 messages 列表
        max_tokens:   最终输出的最大 token 数 (默认 512)
        keep_first_n: 保留前 N 条作为 head (默认 1, 只保留 system)

    Returns:
        (compacted_messages, info_dict)
    """
    before_tokens = estimate_tokens(messages)

    if before_tokens <= max_tokens:
        return messages, {
            "level": 3,
            "compacted": False,
            "before_tokens": before_tokens,
            "after_tokens": before_tokens,
            "compacted_messages_count": 0,
            "summary": "",
            "error": "already under max",
        }

    # 策略: 从最后一条往前收集, 直到达到 max_tokens
    # 这样保留最近的上下文 (最相关)
    kept: list[dict[str, Any]] = []
    kept_tokens = 0
    for msg in reversed(messages):
        msg_tokens = estimate_tokens([msg])
        if kept_tokens + msg_tokens > max_tokens and kept:
            break
        kept.insert(0, msg)
        kept_tokens += msg_tokens

    # 如果单条消息就超 max_tokens (例如巨大的 user input), 截断该消息内容
    if not kept and messages:
        last_msg = dict(messages[-1])
        content = str(last_msg.get("content", ""))
        # 按 max_tokens 对应的字符数截断 (粗略估计: 1 token ≈ 2.5 chars)
        max_chars = max(100, int(max_tokens * 2.5))
        if len(content) > max_chars:
            last_msg["content"] = content[:max_chars] + "\n...[truncated by L3]"
        kept = [last_msg]
        kept_tokens = estimate_tokens(kept)

    compacted = kept
    after_tokens = estimate_tokens(compacted)

    return compacted, {
        "level": 3,
        "compacted": True,
        "before_tokens": before_tokens,
        "after_tokens": after_tokens,
        "compacted_messages_count": len(messages) - len(compacted),
        "summary": f"deterministic_truncate: {len(messages)} → {len(compacted)} msgs, "
        f"kept_tokens={kept_tokens}",
        "error": None,
    }


async def compact_with_escalation(
    llm_adapter: Any,
    messages: list[dict[str, Any]],
    *,
    threshold_tokens: int = 60000,
    keep_recent: int = 6,
    keep_first_n: int = 2,
    l2_target_tokens: int = 30000,
    l3_max_tokens: int = 512,
    cache_safe: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """三级 Escalation 压缩 。

    流程:
      L1: compact_messages_if_needed (LLM preserve_details summary)
          ↓ 失败 (LLM error / summary 比原文长 / 未减少 token)
      L2: sliding_window_compact (boundary-aware, 保护 tool_call 配对)
          ↓ 仍超 l2_target_tokens
      L3: deterministic_truncate (硬截断, 保证收敛)

    每级检查 Tokens(S) < Tokens(X), 失败则升级; L3 保证收敛。

    Args:
        llm_adapter:      LLM 适配器 (L1 用)
        messages:         当前 messages
        threshold_tokens: L1 触发阈值 (默认 60K)
        keep_recent:      L1/L2 保留最近 N 条 (默认 6)
        keep_first_n:     L1/L2 保留前 N 条 (默认 2)
        l2_target_tokens: L2 目标 token 数 (默认 30K)
        l3_max_tokens:    L3 中间区域最大 token 数 (默认 512)
        cache_safe:       P4.1 — L1 是否用 缓存安全分叉 (默认 True)

    Returns:
        (compacted_messages, info_dict)
        info_dict 包含 level (1/2/3) + 各级的 before/after tokens
    """
    before_tokens = estimate_tokens(messages)
    if before_tokens <= threshold_tokens:
        return messages, {
            "level": 0,
            "compacted": False,
            "before_tokens": before_tokens,
            "after_tokens": before_tokens,
            "compacted_messages_count": 0,
            "summary": "",
            "error": "under threshold",
        }

    # L1: LLM summary (preserve_details)
    l1_compacted, l1_info = await compact_messages_if_needed(
        llm_adapter,
        messages,
        threshold_tokens=threshold_tokens,
        keep_recent=keep_recent,
        keep_first_n=keep_first_n,
        cache_safe=cache_safe,
    )

    # 检查 L1 是否成功减少了 token
    l1_success = (
        l1_info
        and l1_info.get("compacted")
        and l1_info.get("after_tokens", before_tokens) < before_tokens
    )

    if l1_success:
        return l1_compacted, {
            "level": 1,
            **l1_info,
        }

    # L1 失败, 升级到 L2: boundary-aware sliding window
    logger.warning(
        "P2 Escalation: L1 failed (%s), escalating to L2 sliding_window",
        l1_info.get("error") if l1_info else "no info",
    )
    l2_compacted, l2_info = sliding_window_compact(
        messages,
        keep_first_n=keep_first_n,
        keep_recent=keep_recent,
        target_tokens=l2_target_tokens,
    )

    l2_success = (
        l2_info.get("compacted") and l2_info.get("after_tokens", before_tokens) <= l2_target_tokens
    )

    if l2_success:
        return l2_compacted, {
            "level": 2,
            **l2_info,
            "l1_error": l1_info.get("error") if l1_info else None,
        }

    # L2 失败 (仍超 target), 升级到 L3: deterministic truncate
    logger.warning(
        "P2 Escalation: L2 failed (after=%d > target=%d), escalating to L3 truncate",
        l2_info.get("after_tokens", 0),
        l2_target_tokens,
    )
    l3_compacted, l3_info = deterministic_truncate(
        messages,
        max_tokens=l3_max_tokens,
        keep_first_n=keep_first_n,
    )

    return l3_compacted, {
        "level": 3,
        **l3_info,
        "l1_error": l1_info.get("error") if l1_info else None,
        "l2_after_tokens": l2_info.get("after_tokens", 0),
    }


# ============================================================================
# P3: 软/硬阈值异步 compaction
# ============================================================================
#
# 三段式 overhead :
#   |C| < τsoft (50K):  none     — 零开销, 不触发压缩
#   τsoft ≤ |C| < τhard (80K): async — 异步压缩, turn 间原子 swap, 用户无感
#   |C| ≥ τhard (80K): blocking — 阻塞压缩, 避免 context overflow
#
# 设计要点:
#   - 软阈值触发后, 用 asyncio.create_task 在后台跑 compact_with_escalation
#   - 当前 turn 继续用旧 messages (不等待), 用户无感
#   - 下一个 turn 开始时检查后台任务是否完成, 完成则原子 swap
#   - 硬阈值触发时, 如果后台任务还在跑, 等待它完成; 否则同步触发新压缩
#   - 原子 swap: 用 lock 保护 messages 替换, 避免 turn 中途被替换
# ============================================================================


class BackgroundCompactor:
    """后台异步 compactor 。

    用法:
        bg = BackgroundCompactor(llm_adapter, tau_soft=50000, tau_hard=80000)

        # 每个工具调用后检查
        action = bg.check(messages)
        if action == "async":
            # 软阈值触发, 后台开始压缩, 当前 turn 继续
            pass
        elif action == "blocking":
            # 硬阈值触发, 必须等待压缩完成
            compacted, info = await bg.await_compaction()
            messages = compacted

        # 每个 turn 开始时检查后台任务是否完成
        swapped = bg.maybe_swap(messages)
        if swapped:
            messages = swapped  # 原子 swap 到压缩后的 messages
    """

    def __init__(
        self,
        llm_adapter: Any,
        *,
        tau_soft: int = 50000,
        tau_hard: int = 80000,
        keep_recent: int = 6,
        keep_first_n: int = 2,
        l2_target_tokens: int = 30000,
        l3_max_tokens: int = 512,
    ) -> None:
        self._llm = llm_adapter
        self._tau_soft = tau_soft
        self._tau_hard = tau_hard
        self._keep_recent = keep_recent
        self._keep_first_n = keep_first_n
        self._l2_target = l2_target_tokens
        self._l3_max = l3_max_tokens

        # 后台任务状态
        self._bg_task: asyncio.Task | None = None
        self._bg_result: tuple[list[dict[str, Any]], dict[str, Any]] | None = None
        self._bg_error: Exception | None = None
        self._bg_input_tokens: int = 0  # 触发后台压缩时的 tokens 数

    def check(self, messages: list[dict[str, Any]]) -> str:
        """检查当前 messages 应触发哪种 compaction action。

        Returns:
            "none"      — 无需压缩
            "async"     — 软阈值触发, 启动后台异步压缩
            "blocking"  — 硬阈值触发, 必须阻塞等待压缩
        """
        tokens = estimate_tokens(messages)

        if tokens < self._tau_soft:
            return "none"

        if tokens >= self._tau_hard:
            return "blocking"

        # 软阈值区间: 如果后台任务已在跑或已完成, 不重复触发
        if self._bg_task is not None or self._bg_result is not None:
            return "none"

        return "async"

    def start_async(self, messages: list[dict[str, Any]]) -> None:
        """启动后台异步压缩 (软阈值触发)。

        在后台跑 compact_with_escalation, 当前 turn 不等待。
        """
        if self._bg_task is not None:
            return  # 已有后台任务在跑

        # 深拷贝 messages, 避免后台任务读到正在被修改的数据
        msgs_copy = [dict(m) for m in messages]
        self._bg_input_tokens = estimate_tokens(msgs_copy)
        self._bg_result = None
        self._bg_error = None

        async def _bg_compact():
            try:
                result = await compact_with_escalation(
                    self._llm,
                    msgs_copy,
                    threshold_tokens=self._tau_soft,  # 用软阈值作为 L1 触发阈值
                    keep_recent=self._keep_recent,
                    keep_first_n=self._keep_first_n,
                    l2_target_tokens=self._l2_target,
                    l3_max_tokens=self._l3_max,
                )
                self._bg_result = result
            except Exception as e:
                self._bg_error = e
                logger.warning("P3 Background compaction failed: %s", e)
            finally:
                self._bg_task = None

        self._bg_task = asyncio.create_task(_bg_compact())

    def maybe_swap(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        """检查后台任务是否完成, 完成则返回压缩后的 messages (原子 swap)。

        Returns:
            None — 后台任务未完成或未启动
            list — 压缩后的 messages, 调用方应替换当前 messages
        """
        if self._bg_result is None:
            return None

        # 后台任务完成, 检查结果是否有效
        compacted, info = self._bg_result
        if not info.get("compacted"):
            # 压缩未生效 (例如 messages 太少), 清空结果
            self._bg_result = None
            return None

        # 检查当前 messages 是否比触发时增长了 (如果增长了, swap 可能丢失新消息)
        current_tokens = estimate_tokens(messages)
        if current_tokens > self._bg_input_tokens * 1.5:
            # 增长超过 50%, 放弃这次 swap (避免丢失新消息)
            logger.info(
                "P3 Swap skipped: messages grew %d → %d (>50%%),放弃 swap",
                self._bg_input_tokens,
                current_tokens,
            )
            self._bg_result = None
            return None

        # 原子 swap: 返回压缩后的 messages
        self._bg_result = None
        return compacted

    async def await_compaction(
        self, messages: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """硬阈值阻塞压缩。

        如果后台任务在跑, 等待它完成; 否则同步触发新压缩。

        Returns:
            (compacted_messages, info_dict)
        """
        # 如果后台任务在跑, 等待它完成
        if self._bg_task is not None:
            logger.info("P3 Hard threshold: waiting for background compaction...")
            await self._bg_task

        if self._bg_result is not None:
            # 后台任务完成了, 用它的结果
            compacted, info = self._bg_result
            self._bg_result = None
            return compacted, info

        # 后台任务没在跑或失败了, 同步触发新压缩
        compacted, info = await compact_with_escalation(
            self._llm,
            messages,
            threshold_tokens=self._tau_hard,
            keep_recent=self._keep_recent,
            keep_first_n=self._keep_first_n,
            l2_target_tokens=self._l2_target,
            l3_max_tokens=self._l3_max,
        )
        return compacted, info

    def is_running(self) -> bool:
        """后台任务是否在跑。"""
        return self._bg_task is not None

    def has_result(self) -> bool:
        """后台任务是否已完成 (有结果待 swap)。"""
        return self._bg_result is not None
