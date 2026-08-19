"""Self-Optimizing — 离线轨迹分析 → few-shot 示例库（Spec 6 第 4 维）。

DAAO/VMAO/HERA 都是在线优化（执行前/中），Self-Optimizing 是离线优化：
任务完成后分析整条轨迹，提取 (input, output, trace) 三元组，沉淀为
few-shot 示例；下次类似任务前召回注入 prompt，让 Agent "见多识广"。

与 HERA SkillLibrary 的分工（避免重叠）:
  - SkillLibrary  存任务签名 + solution_summary（粗粒度，"做过类似任务"）
  - SelfOptimizing 存完整 input/output + tool_sequence + score（细粒度，"具体怎么做的"）
两者可并存：SkillLibrary 提供"是否做过"召回，SelfOptimizing 提供"怎么做"的 few-shot。
  - dspy/teleprompt/bootstrap.py: BootstrapFewShot._bootstrap_one_example
    核心：metric(example, prediction, trace) → bool 决定是否沉淀
    精简：success_score 替代 metric，extract_examples_from_trace 替代 _bootstrap
  - reflexion/alfworld_runs/generate_reflections.py: update_memory
    核心：失败时调 LLM 生成反思，存入 env['memory']
    精简：本模块仅做"成功轨迹"沉淀，失败反思由 VMAO Reflexion 负责
  - voyager/agents/skill.py: SkillManager.add_new_skill 的版本号覆盖
    核心：同名技能新版本覆盖旧版本
    精简：相同 task_hash 超 7 天则覆盖（V2 模式）

存储路径: {workspace}/.fnix/self_optimizing/examples.json
零外部依赖（无向量化、无 LLM 调用、无 Chroma）。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class FewShotExample:
    """一条 few-shot 示例（来自成功轨迹）。

    对齐 DSPy Example(augmented=True, **inputs, **outputs)：
      - example_id → DSPy example.id
      - input_text/output_text → DSPy Example 的 inputs/outputs
      - tool_sequence → DSPy trace 的 predictor 序列
      - score → DSPy metric 返回值
    """

    example_id: str
    task_signature: str  # 用户输入前 100 字符（用于召回展示）
    task_hash: str  # 去重 hash（md5 前 12 位）
    input_text: str  # 完整用户输入（截断 2000）
    output_text: str  # 完整 agent 回答（截断 2000）
    tool_sequence: list[str]  # 工具名序列，如 ["read_file", "edit_file"]
    score: float  # success_score 0.0-1.0
    workspace_kind: str  # 任务类型
    created_at: float
    usage_count: int = 0
    last_used_at: float = 0.0


# ，保持一致
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "to",
        "of",
        "and",
        "or",
        "in",
        "on",
        "for",
        "with",
        "by",
        "at",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "的",
        "了",
        "和",
        "是",
        "在",
        "我",
        "你",
        "他",
        "她",
        "它",
        "们",
        "个",
        "用",
        "把",
        "给",
        "对",
        "向",
        "从",
        "到",
        "于",
        "为",
        "与",
        "及",
        "或",
        "一",
        "二",
        "三",
        "这",
        "那",
        "有",
        "无",
        "要",
        "会",
        "能",
        "可",
        "可以",
    }
)


def _tokenize(text: str) -> set[str]:
    """简单分词：英文按 \\w+，中文按 2-3 字符滑窗。与 SkillLibrary 一致。"""
    if not text:
        return set()
    tokens: set[str] = set()
    for m in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{1,}", text.lower()):
        if m not in _STOPWORDS and len(m) >= 2:
            tokens.add(m)
    chinese = re.findall(r"[\u4e00-\u9fff]+", text)
    for seg in chinese:
        if len(seg) >= 2:
            tokens.add(seg[:2])
            if len(seg) >= 3:
                tokens.add(seg[:3])
    return tokens


def success_score(
    *,
    success: bool,
    tool_calls: list[dict],
    duration_ms: int,
    error_count: int,
) -> float:
    """轨迹评分（DSPy.metric 的轻量替代）。。

    维度加权:
      - 成功 0.5（基础分，失败即 0）
      - 工具成功率 0.2（成功工具数 / 总工具数）
      - 速度 0.15（30s 内满分，5min 衰减到 0）
      - 稳定性 0.15（无错误满分，3 次错误清零）
    """
    if not success:
        return 0.0
    base = 0.5
    if tool_calls:
        ok = sum(1 for t in tool_calls if t.get("success", True))
        base += 0.2 * (ok / len(tool_calls))
    secs = max(0, duration_ms) / 1000.0
    base += 0.15 * max(0.0, 1.0 - secs / 300.0)
    base += 0.15 * max(0.0, 1.0 - max(0, error_count) / 3.0)
    return round(min(base, 1.0), 3)


def extract_examples_from_trace(
    *,
    user_input: str,
    response: str,
    tool_calls: list[dict],
    success: bool,
    duration_ms: int,
    error_count: int = 0,
    workspace_kind: str = "general",
    score_threshold: float = 0.6,
) -> FewShotExample | None:
    """从一条执行轨迹提取 few-shot 示例（DSPy._bootstrap_one_example 精简版）。

    对齐 DSPy BootstrapFewShot._bootstrap_one_example:
      - 跑一次 teacher → 用 metric 判定 success → 成功则把 trace 沉淀为 demo
    精简：本函数不跑 teacher，直接用已有轨迹；用 success_score 替代 metric。
    """
    if not user_input or not response:
        return None
    score = success_score(
        success=success,
        tool_calls=tool_calls,
        duration_ms=duration_ms,
        error_count=error_count,
    )
    if score < score_threshold:
        return None
    now = time.time()
    return FewShotExample(
        example_id=f"ex_{int(now * 1000)}",
        task_signature=user_input.strip()[:100],
        task_hash=hashlib.md5(user_input.strip()[:200].encode("utf-8")).hexdigest()[:12],
        input_text=user_input[:2000],
        output_text=response[:2000],
        tool_sequence=[str(t.get("name", "")) for t in (tool_calls or [])[:15]],
        score=score,
        workspace_kind=workspace_kind,
        created_at=now,
    )


class SelfOptimizingLibrary:
    """few-shot 示例库（与 SkillLibrary 互补，HERA Self-Optimizing 维度）。

    存储路径: {workspace}/.fnix/self_optimizing/examples.json
    线程安全，零外部依赖。

    使用:
      >>> lib = SelfOptimizingLibrary(workspace)
      >>> lib.add(example)               # 沉淀
      >>> retrieved = lib.retrieve(query, top_k=2)  # 召回
      >>> block = lib.format_for_prompt(retrieved)  # 注入 prompt
    """

    def __init__(self, workspace: str, *, max_examples: int = 100):
        self.workspace = str(Path(workspace or "").expanduser().resolve())
        self.dir = Path(self.workspace) / ".fnix" / "self_optimizing"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.file = self.dir / "examples.json"
        self.max_examples = max_examples
        self.examples: list[FewShotExample] = []
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        with self._lock:
            if not self.file.exists():
                self.examples = []
                return
            try:
                data = json.loads(self.file.read_text(encoding="utf-8"))
                if not isinstance(data, list):
                    self.examples = []
                    return
                examples: list[FewShotExample] = []
                for e in data:
                    if not isinstance(e, dict):
                        continue
                    try:
                        examples.append(FewShotExample(**e))
                    except TypeError:
                        continue
                self.examples = examples
            except (OSError, ValueError):
                self.examples = []

    def _save(self) -> None:
        try:
            self.file.write_text(
                json.dumps(
                    [asdict(e) for e in self.examples],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def add(self, ex: FewShotExample | None) -> bool:
        """添加示例，去重 + 容量限制。

        - 相同 task_hash 7 天内不重复捕获（同 SkillLibrary 策略）
        - 相同 task_hash 超 7 天：覆盖旧的（Voyager V2 模式）
        - 按 score 降序保留 top-K
        """
        if ex is None:
            return False
        with self._lock:
            now = time.time()
            for e in self.examples:
                if e.task_hash == ex.task_hash and (now - e.created_at) < 7 * 86400:
                    return False
            self.examples = [e for e in self.examples if e.task_hash != ex.task_hash]
            self.examples.append(ex)
            self.examples.sort(key=lambda e: (-e.score, -e.created_at))
            if len(self.examples) > self.max_examples:
                self.examples = self.examples[: self.max_examples]
            self._save()
            return True

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 2,
        workspace_kind: str = "",
    ) -> list[FewShotExample]:
        """召回 top-K 示例（Jaccard 相似度 + score 加权 + 时间衰减）。

        对齐 DSPy._train 取 demo：高分 demo 优先；同时
        时间衰减（30 天半衰期）+ workspace_kind 加分。
        """
        if not self.examples or not query.strip():
            return []
        qt = _tokenize(query)
        if not qt:
            return []
        with self._lock:
            scored: list[tuple[float, FewShotExample]] = []
            for ex in self.examples:
                et = _tokenize(ex.task_signature)
                inter = len(qt & et)
                if inter == 0:
                    continue
                sim = inter / max(len(qt | et), 1)
                sim *= 0.5 + 0.5 * ex.score
                if workspace_kind and ex.workspace_kind == workspace_kind:
                    sim *= 1.2
                age_days = (time.time() - ex.created_at) / 86400.0
                sim *= 0.5 ** (age_days / 30.0)
                scored.append((sim, ex))
            scored.sort(key=lambda x: -x[0])
            result = [e for _, e in scored[:top_k]]
            now = time.time()
            for e in result:
                e.usage_count += 1
                e.last_used_at = now
            if result:
                self._save()
            return result

    def format_for_prompt(self, examples: list[FewShotExample]) -> str:
        """格式化为 system prompt 注入块（与 SkillLibrary 区分标签）。"""
        if not examples:
            return ""
        lines = ["\n\n## few-shot 示例（Self-Optimizing · 离线沉淀）"]
        for i, ex in enumerate(examples, 1):
            lines.append(f"### 示例 {i} [score={ex.score}]: {ex.task_signature}")
            lines.append(f"输入: {ex.input_text[:300]}")
            lines.append(f"输出: {ex.output_text[:300]}")
            if ex.tool_sequence:
                lines.append(f"工具链: {' -> '.join(ex.tool_sequence[:8])}")
        lines.append("参考上述示例的解决路径，保持一致风格。")
        return "\n".join(lines)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total": len(self.examples),
                "avg_score": (
                    sum(e.score for e in self.examples) / len(self.examples)
                    if self.examples
                    else 0.0
                ),
                "by_kind": {
                    k: sum(1 for e in self.examples if e.workspace_kind == k)
                    for k in {e.workspace_kind for e in self.examples}
                },
            }


__all__ = [
    "FewShotExample",
    "SelfOptimizingLibrary",
    "extract_examples_from_trace",
    "success_score",
]
