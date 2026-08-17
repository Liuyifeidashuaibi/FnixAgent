"""Spec 5 独立 Critic Agent — 任务产物语义审查（精简版）。

借鉴:
  - noahshinn/reflexion (NeurIPS 2023): Actor + Evaluator + Self-Reflection
  - LangGraph Reflexion: Actor agent + External evaluator
  - CRITIC 框架: LLM 用工具做外判批判
  - OpenAI Swarm handoff: 轻量 agent 委托
  - H4 史诗级优化: OpenAI Agents SDK Pydantic output_type 强约束

设计:
  - 独立 LLM 调用（不是 self-reflect）
  - 不带 tools（避免递归）
  - craft 模式 + 产物已生成 + 任务完成前触发
  - 最多触发 1 次（避免无限循环）
  - 失败静默降级（不阻断主流程）
  - H4: Pydantic BaseModel 严格解析, 移除启发式降级

解决 VMAO 盲点:
  VMAO 只在工具调用失败时反思, 但"工具调用成功但产物语义错误"
  (如生成了错误代码但 write_file 成功) 无法感知。
  CriticAgent 以独立第三方视角对产物做语义审查。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# H4: Pydantic BaseModel 强约束 (借鉴 OpenAI Agents SDK output_type)
# 替代原 dataclass, 让 LLM 输出有结构化校验
class CriticVerdict(BaseModel):
    """Critic 审查结论 (Pydantic BaseModel, 借鉴 OpenAI Agents SDK output_type).

    用 model_validate_json 严格解析 LLM 输出,
    解析失败时记录 warning, 不再退化为启发式判断.

    score 语义 (Spec 7 fail-soft-with-signal 改造):
      - 0.0-1.0: 正常审查分数 (LLM 审查成功)
      - -1.0: 哨兵值, 表示"审查未完成" (LLM 调用失败/JSON 解析失败)
        passed=True 不阻断主流程, 但调用方可通过 score==-1.0 emit
        可观测信号 (critic.skipped), 避免静默漏检。
        借鉴 LangGraph Reflexion Evaluator 的 fail-soft-with-signal 模式:
        fail-closed 会被 except 吞掉形成"假装阻断实则静默放行"的最差组合,
        fail-soft-with-signal 取折中——不阻断但不静默。
    """

    passed: bool = Field(description="是否通过审查")
    score: float = Field(
        default=0.5, ge=-1.0, le=1.0, description="0.0-1.0 分数; -1.0=审查未完成哨兵"
    )
    issues: list[str] = Field(default_factory=list, description="发现的问题")
    suggestions: list[str] = Field(default_factory=list, description="修改建议")
    raw_response: str = Field(default="", description="LLM 原始响应", exclude=True)

    model_config = {"extra": "ignore"}  # 允许 LLM 输出多余字段, 忽略即可

class CriticAgent:
    """Spec 5 独立 Critic Agent。

    用法（在 AgenticLoop 任务完成前调用）:
        critic = CriticAgent(llm_config=ctx.llm)
        verdict = await critic.review(
            user_input=ctx.user_input,
            artifacts=[{"path": "...", "name": "..."}],
            tool_calls_summary=tool_calls_summary,
            answer=answer,
        )
        if not verdict.passed:
            # 注入 critic_feedback 到下轮 LLM, 让 Agent 修改产物
            ...

    设计原则:
      - 独立 LLM 调用 (系统消息明确"你是独立审查者, 不是执行者")
      - 不带 tools (避免 Critic 自己又调用工具)
      - 失败静默降级 (Critic 不可用时, 任务照常完成)
      - H4: Pydantic 强约束解析, JSON 提取更鲁棒
    """

    SYSTEM_PROMPT = """你是 FnixAgent 的独立 Critic 审查者，不是执行者。

你的职责:
  1. 评估 AI 生成的产物是否真正满足用户的原始需求
  2. 发现"工具调用成功但产物语义错误"的盲点
  3. 给出明确的通过/不通过结论 + 修改建议

审查维度:
  - 需求覆盖: 产物是否真正解决了用户问题
  - 完整性: 是否有遗漏的关键内容
  - 正确性: 代码/文档内容是否正确（语法、逻辑、引用）
  - 可用性: 产物是否可以直接打开/运行/查看
  - 路径合规: 文件是否落在 `.fnix/artifacts/` 下

输出格式（严格 JSON, 不要包装在 markdown 代码块中）:
{
  "passed": true/false,
  "score": 0.0-1.0,
  "issues": ["问题1", "问题2"],
  "suggestions": ["建议1", "建议2"]
}

注意:
  - 你不是执行者, 不要建议调用工具, 不要写代码
  - 你只做评价, 不修改产物
  - 严格 JSON 输出, 不要任何额外文字
"""

    def __init__(self, llm_config: dict | None = None):
        """初始化 CriticAgent。

        Args:
            llm_config: LLM 配置 dict, 支持以下键:
                - api_key / key: API Key (为空时自动检测环境变量)
                - base_url: API 基础 URL
                - model / model_name: 模型名
                - provider / provider_name: 提供商名 (openai/glm/qwen/deepseek/custom)
                为空时由 LLMAdapter 自动检测环境变量。
        """
        self.llm_config = llm_config or {}

    async def review(
        self,
        *,
        user_input: str,
        artifacts: list[dict] = None,
        tool_calls_summary: list[dict] = None,
        answer: str = "",
    ) -> CriticVerdict | None:
        """对产物做语义审查。

        Args:
            user_input: 用户原始请求
            artifacts: 产物列表 [{"path": "...", "name": "..."}]
            tool_calls_summary: 工具调用摘要 [{"name": "write_file", "success": True, ...}]
            answer: AI 的最终回答文本

        Returns:
            CriticVerdict 或 None (调用失败时)
        """
        artifacts = artifacts or []
        tool_calls_summary = tool_calls_summary or []

        if not artifacts and not answer:
            return None  # 无产物可审查

        try:
            user_msg = self._build_user_message(
                user_input=user_input,
                artifacts=artifacts,
                tool_calls_summary=tool_calls_summary,
                answer=answer,
            )
            raw = await self._call_llm(user_msg)
            if not raw:
                return None
            return self._parse_verdict(raw)
        except Exception as e:
            logger.warning("CriticAgent.review failed: %s", e)
            return None

    def _build_user_message(
        self,
        *,
        user_input: str,
        artifacts: list[dict],
        tool_calls_summary: list[dict],
        answer: str,
    ) -> str:
        """构造给 Critic 的用户消息。"""
        lines = ["# 任务审查请求", ""]
        lines.append(f"## 用户原始需求\n{user_input[:500]}")
        lines.append("")

        if artifacts:
            lines.append("## 生成的产物")
            for i, art in enumerate(artifacts[:10], 1):
                lines.append(f"{i}. {art.get('name', '')} ({art.get('path', '')})")
            lines.append("")

        if tool_calls_summary:
            lines.append("## 工具调用序列")
            for tc in tool_calls_summary[:15]:
                name = tc.get("name", "")
                success = "✓" if tc.get("success", True) else "✗"
                lines.append(f"- [{success}] {name}")
            lines.append("")

        if answer:
            lines.append(f"## AI 最终回答（节选）\n{answer[:1000]}")
            lines.append("")

        lines.append("## 请按系统提示的 JSON 格式输出审查结论")
        return "\n".join(lines)

    async def _call_llm(self, user_message: str) -> str:
        """调用 LLM (使用 LLMAdapter)。

        LLMAdapter 实际 API:
          - 构造: LLMAdapter(api_key, base_url, model_name, provider_name)
          - 调用: await adapter.chat(messages, tools=None, model="", temperature=0.7, max_tokens=4096)
          - 返回: OpenAI 兼容 dict {"choices": [{"message": {"content": "..."}}], "usage": {...}}
        """
        try:
            from fnixagent.core.llm.adapter import LLMAdapter

            # llm_config 键名兼容: api_key/key, model/model_name, provider/provider_name
            cfg = self.llm_config or {}
            adapter = LLMAdapter(
                api_key=cfg.get("api_key", "") or cfg.get("key", ""),
                base_url=cfg.get("base_url", ""),
                model_name=cfg.get("model", "") or cfg.get("model_name", ""),
                provider_name=cfg.get("provider", "") or cfg.get("provider_name", ""),
            )
            response = await adapter.chat(
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.2,  # Critic 用低温度保证稳定
                max_tokens=800,
            )
            # response 是 OpenAI 兼容格式 dict
            if isinstance(response, dict):
                choices = response.get("choices") or []
                if choices and isinstance(choices[0], dict):
                    msg = choices[0].get("message", {}) or {}
                    if isinstance(msg, dict):
                        content = msg.get("content", "") or ""
                        if content:
                            return content
                # 兜底: 某些自定义 provider 可能直接返回 content/text 字段
                return response.get("content") or response.get("text") or ""
            return str(response or "")
        except Exception as e:
            logger.warning("CriticAgent LLM call failed: %s", e)
            return ""

    def _parse_verdict(self, raw: str) -> CriticVerdict | None:
        """H4: 用 Pydantic BaseModel 严格解析 LLM 输出.

        借鉴 OpenAI Agents SDK output_type:
          - 先尝试整体 model_validate_json
          - 失败则提取 JSON 块 (```json ... ``` 或 { ... })
          - 再用 model_validate_json 严格解析
          - 解析失败记录 warning, 返回一个 fail-safe verdict (而非启发式猜测)

        移除了原 _parse_verdict 的启发式降级 (基于关键字 passed/failed 猜测),
        因为它会让"JSON 解析失败"伪装成"通过/不通过", 误导后续流程.
        """
        raw = (raw or "").strip()
        if not raw:
            return None

        # 策略 1: 直接整体解析 (LLM 严格遵守 JSON 输出时)
        try:
            return CriticVerdict.model_validate_json(raw)
        except (ValidationError, ValueError):
            pass

        # 策略 2: 提取 ```json ... ``` 代码块
        m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
        if m:
            try:
                return CriticVerdict.model_validate_json(m.group(1).strip())
            except (ValidationError, ValueError):
                pass

        # 策略 3: 提取第一个 { ... } JSON 对象 (贪婪到最深嵌套)
        # 用括号配平法, 避免正则误匹配嵌套 JSON
        json_str = self._extract_first_json_object(raw)
        if json_str:
            try:
                return CriticVerdict.model_validate_json(json_str)
            except (ValidationError, ValueError):
                pass

        # 策略 4: 全部失败, 返回 fail-soft-with-signal verdict
        # (Spec 7 改造: 修复"假装 fail-closed 实则静默 fail-open"的 bug)
        #
        # 原设计 (passed=False) 的问题:
        #   work_pipeline 的 except Exception: pass 会吞掉所有异常,
        #   passed=False 的 fail-closed 信号被吞掉后, 等于静默放行,
        #   既没有阻断也没有信号, 是最差组合。
        #
        # 新设计 (passed=True, score=-1.0):
        #   - passed=True: 不阻断主流程 (Critic 坏了不应卡死所有任务)
        #   - score=-1.0: 哨兵值, 让调用方可观测地知道"本次未审查"
        #   - 调用方 (work_pipeline) 检测 score==-1.0 时 emit critic_skipped 事件
        #   - MFP 第 3 阶 (元反思) 可统计 critic.skip_rate 作为健康度指标
        #
        # 借鉴 LangGraph Reflexion Evaluator 的 fail-soft-with-signal 模式。
        logger.warning(
            "CriticAgent JSON 解析失败 (已尝试 4 种策略), "
            "返回 fail-soft verdict (passed=True, score=-1.0 哨兵). raw[:200]=%s",
            raw[:200],
        )
        return CriticVerdict(
            passed=True,  # 不阻断主流程 (Critic 故障不应雪崩)
            score=-1.0,  # 哨兵值: 表示审查未完成, 调用方可 emit 信号
            issues=["Critic 响应解析失败, 审查未完成"],
            suggestions=[],
            raw_response=raw,
        )

    @staticmethod
    def _extract_first_json_object(text: str) -> str:
        """用括号配平法提取第一个完整 JSON 对象.

        比 regex 更鲁棒, 能处理嵌套 {} 和字符串中的 {}.
        """
        depth = 0
        start = -1
        in_string = False
        escape = False
        for i, ch in enumerate(text):
            if escape:
                escape = False
                continue
            if ch == "\\" and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start >= 0:
                    return text[start : i + 1]
        return ""

__all__ = ["CriticAgent", "CriticVerdict"]
