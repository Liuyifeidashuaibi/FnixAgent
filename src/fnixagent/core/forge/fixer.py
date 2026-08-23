"""FnixForge — Git 守卫下的自动修复。

修复流程（loop 编排时调用）:
  1. GitGuard.ensure()  — 目标项目必须可回滚（非 git 仓库时自动 git init + 基线提交）
  2. propose_fix()      — 用 FnixAgent 自己的 LLM 读诊断 + 相关源码，输出精确文件编辑
  3. apply_edits()      — 落盘（create / modify-search-replace / rewrite 三种操作）
  4. （loop 负责）复测    — 失败的题重跑 + 全部题回归
  5. keep_or_rollback()  — 有进步且无回归 → git commit；否则 git checkout 全量回滚

LLM 输出契约（强制）:
  模型只能输出若干文件块：
      ===FILE: <相对路径>===
      <该文件修改后的完整内容>
      ===END===
  解析失败 = 本轮修复作废（回滚），不允许半解析落盘。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

_MAX_CONTEXT_FILES = 6
_MAX_FILE_CHARS = 8_000
_MAX_TOTAL_CONTEXT = 48_000

# ---------------------------------------------------------------------------
# Git 守卫
# ---------------------------------------------------------------------------

class GitGuard:
    """保证目标项目在任何修复动作前都可无条件回滚。"""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()

    def _git(self, *args: str, check: bool = False) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=str(self.root), capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=60,
        )

    @property
    def is_repo(self) -> bool:
        return self._git("rev-parse", "--is-inside-work-tree").returncode == 0

    def ensure(self) -> str:
        """准备守卫, 返回基线 commit hash。非仓库 → 初始化并全量提交。"""
        if not self.is_repo:
            self._git("init")
            _logger.info("fnix-forge: 在 %s 初始化 git 用于回滚守卫", self.root)
        dirty = self._git("status", "--porcelain").stdout.strip()
        if dirty:
            self._git("add", "-A")
            self._git("-c", "user.name=FnixForge", "-c", "user.email=forge@fnix.local",
                      "commit", "-m", "fnix-forge: baseline snapshot before fixing", "-q")
        else:
            head = self._git("rev-parse", "--verify", "HEAD")
            if head.returncode != 0:
                self._git("add", "-A")
                self._git("-c", "user.name=FnixForge", "-c", "user.email=forge@fnix.local",
                          "commit", "-m", "fnix-forge: baseline snapshot before fixing", "-q")
        return self.current_head()

    def current_head(self) -> str:
        return self._git("rev-parse", "HEAD").stdout.strip()

    def rollback(self, to: str) -> None:
        """硬回滚到指定 commit（含未跟踪新增文件清理）。"""
        self._git("reset", "--hard", to)
        self._git("clean", "-fd")

    def commit(self, message: str) -> str:
        self._git("add", "-A")
        r = self._git("-c", "user.name=FnixForge", "-c", "user.email=forge@fnix.local",
                      "commit", "-m", message, "-q")
        return self.current_head() if r.returncode == 0 else ""

    def diff_stat(self, base: str) -> str:
        return self._git("diff", "--stat", base).stdout.strip()

# ---------------------------------------------------------------------------
# LLM 修复提案
# ---------------------------------------------------------------------------

FIX_SYSTEM_PROMPT = """你是资深软件修复工程师。一个尚不成熟的 AI Agent 项目刚刚在专业能力测评中暴露出缺陷。
你将收到:
  1. 失败诊断（哪些题失败、失败原因、越界行为）
  2. 该项目中最可能相关的源码文件

你的任务: 修改该项目源码，使其修复这些缺陷，同时**绝不能**破坏其他已通过的题。

输出契约（严格遵守）:
  - 只输出若干文件块，格式:
      ===FILE: <相对路径>===
      <该文件修改后的完整内容>
      ===END===
  - 不要输出任何解释、markdown 围栏或多余文本
  - 文件内容必须是完整文件（不是 diff/片段），可被直接落盘运行
  - 修改遵循最小改动原则"""

def _parse_file_blocks(text: str) -> dict[str, str]:
    pattern = re.compile(r"===FILE:\s*(.+?)\s*===\n(.*?)\n?===END===", re.DOTALL)
    return {m.group(1).strip(): m.group(2) for m in pattern.finditer(text)}

@dataclass
class FixAttempt:
    round: int
    baseline: str
    edits: dict[str, str] = field(default_factory=dict)
    applied_paths: list[str] = field(default_factory=list)
    llm_raw_chars: int = 0
    proposal_error: str = ""
    decision: str = "pending"           # pending | kept | rolled_back | aborted
    committed: str = ""
    note: str = ""
    started_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "round": self.round, "decision": self.decision,
            "applied_paths": self.applied_paths, "committed": self.committed,
            "proposal_error": self.proposal_error, "note": self.note,
            "llm_raw_chars": self.llm_raw_chars,
        }

def _gather_context(target_root: Path, relevant_files: list[dict]) -> str:
    chunks: list[str] = []
    total = 0
    for entry in (relevant_files or [])[:_MAX_CONTEXT_FILES]:
        p = target_root / entry["path"]
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")[:_MAX_FILE_CHARS]
        except OSError:
            continue
        if total + len(text) > _MAX_TOTAL_CONTEXT:
            break
        total += len(text)
        chunks.append(f"# ---- {entry['path']} ----\n{text}")
    return "\n\n".join(chunks)

def create_fixer_llm():
    """复用 FnixAgent 自身配置好的 LLM（BYOK / harness 配置）。"""
    from fnixagent.core.llm.adapter import create_llm_adapter

    adapter = create_llm_adapter()
    return adapter

async def _chat(adapter, messages: list[dict]) -> str:
    result = await adapter.chat(messages, temperature=0.2, max_tokens=8192)
    try:
        return result["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""

def propose_fix_sync(diagnosis: dict, target_root: Path, *, llm=None) -> tuple[dict[str, str], str, str]:
    """返回 (edits, error, raw)。edits 为空且 error 为空表示模型没给出可解析输出。"""
    adapter = llm or create_fixer_llm()
    if not getattr(adapter, "is_configured", lambda: False)():
        return {}, "LLM 未配置（fnixagent setup 或环境变量设置 API Key）", ""

    context = _gather_context(target_root, diagnosis.get("relevant_files") or [])
    import json

    user = (
        "【失败诊断】\n"
        + json.dumps(
            {
                "clusters": diagnosis.get("clusters"),
                "failure_traces": [
                    {
                        "task_id": t["task_id"],
                        "checks": [c for c in t["score"]["checks"] if not c["ok"]],
                        "stdout_tail": t["response"]["stdout_tail"][-400:],
                        "stderr_tail": t["response"]["stderr_tail"][-400:],
                    }
                    for t in (diagnosis.get("failure_traces") or [])[:4]
                ],
            },
            ensure_ascii=False, indent=1,
        )
        + "\n\n【相关源码】\n"
        + (context or "（未能自动定位相关源码, 请根据诊断描述自行判断最小修改）")
    )
    messages = [
        {"role": "system", "content": FIX_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    try:
        raw = asyncio.run(_chat(adapter, messages))
    except RuntimeError:
        # 已有事件循环场景（API 内调用）
        loop = asyncio.new_event_loop()
        try:
            raw = loop.run_until_complete(_chat(adapter, messages))
        finally:
            loop.close()
    except Exception as e:
        return {}, f"LLM 调用失败: {type(e).__name__}: {e}", ""

    edits = _parse_file_blocks(raw)
    if not edits:
        return {}, "", raw
    # 路径净化：禁止绝对路径 / 越界 / .git
    clean: dict[str, str] = {}
    root_resolved = Path(target_root).resolve()
    for rel, content in edits.items():
        rel_norm = rel.replace("\\", "/").lstrip("/")
        target = (Path(target_root) / rel_norm).resolve()
        if root_resolved not in target.parents or rel_norm.startswith(".git"):
            continue
        clean[rel_norm] = content
    return clean, "", raw

def apply_edits(target_root: Path, edits: dict[str, str]) -> list[str]:
    applied: list[str] = []
    for rel, content in edits.items():
        p = Path(target_root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content.rstrip("\n") + "\n", encoding="utf-8")
        applied.append(rel)
    return applied

def decide(before_pass: int, after_pass: int, regressed: bool) -> tuple[str, str]:
    """复测后裁决。返回 (decision, note)。"""
    if regressed:
        return "rolled_back", "出现已通过题目的回归，回滚"
    if after_pass > before_pass:
        return "kept", f"通过数 {before_pass} -> {after_pass}"
    if after_pass == before_pass:
        return "rolled_back", "无净进步，回滚以避免引入无谓变更"
    return "rolled_back", f"通过数下降 {before_pass} -> {after_pass}"
