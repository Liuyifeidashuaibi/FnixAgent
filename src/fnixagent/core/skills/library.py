"""HERA SkillLibrary — Voyager-style 自动技能捕获（Spec 6）。

借鉴 MineDojo/Voyager 的 SkillManager.add_new_skill + retrieve_skills 模式:
- 任务成功后自动捕获解决方案为技能
- 下次类似任务前召回 top-K 历史技能注入 prompt
- 存储为 JSON + 简单关键词检索（无 Chroma 依赖，零外部依赖）

与 harness/skills_loader.py 互补:
- skills_loader: 用户手动写的 .fnix/skills/*.md（静态）
- SkillLibrary: 系统自动捕获的成功轨迹（动态，持续演进）

参考:
  - voyager/agents/skill.py 的 add_new_skill + retrieve_skills
  - letta/schemas/memory.py 的 Block 模型（核心记忆 + 归档记忆分层）
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class CapturedSkill:
    """一个自动捕获的技能（来自成功任务）。

    对标 Voyager SkillManager 的 skill entry:
      - program_name → skill_id
      - program_code → solution_summary + tool_calls
      - description → task_signature

    user_feedback 字段对标 Cursor Bugbot Learning 的反馈信号回路:
      用户对 Agent 回复点 👍/👎, 信号回流到技能评分, 影响下次召回权重。
    """

    skill_id: str
    task_signature: str  # 用户输入前 100 字符
    task_hash: str  # 用于去重的 hash
    solution_summary: str  # 解决方案摘要（response 前 500 字符）
    tool_calls: list[dict]  # 工具调用序列（name + success）
    workspace_kind: str  # 任务类型（code/general/research/...）
    success: bool
    created_at: float
    usage_count: int = 0
    last_used_at: float = 0.0
    # 用户反馈信号 (对标 Cursor Bugbot Learning)
    # "up"=有帮助 / "down"=没帮助 / "none"=未反馈
    user_feedback: str = "none"
    feedback_comment: str = ""  # 用户可选的文字反馈
    feedback_at: float = 0.0  # 反馈时间戳
    # 技能来源标记 (修复 VMAO 反思污染 failure_rate 的正反馈回路):
    # "task"=真实任务产物 (默认, 计入 DAAO failure_rate)
    # "vmao_reflection"=VMAO 反思过程的中间失败 (不计入 failure_rate,
    #   因为这是正常调试行为, 不是任务级失败。否则会形成正反馈回路:
    #   反思→failure_skill→failure_rate↑→DAAO 切保守模式→更多步数→
    #   更多失败机会→更多反思→failure_rate 进一步↑)
    source: str = "task"


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
    """简单分词：英文按 \\w+，中文按字符。"""
    if not text:
        return set()
    tokens: set[str] = set()
    # 英文 token
    for m in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{1,}", text.lower()):
        if m not in _STOPWORDS and len(m) >= 2:
            tokens.add(m)
    # 中文 token（按 2-3 字符滑窗）
    chinese = re.findall(r"[\u4e00-\u9fff]+", text)
    for seg in chinese:
        if len(seg) >= 2:
            tokens.add(seg[:2])
            if len(seg) >= 3:
                tokens.add(seg[:3])
    return tokens


class SkillLibrary:
    """Voyager-style 自动技能库（HERA 持续演进层）。

    线程安全。无外部依赖。存储路径: {workspace}/.fnix/skill_library/skills.json
    """

    def __init__(self, workspace: str, *, max_skills: int = 200):
        self.workspace = str(Path(workspace).expanduser().resolve())
        self.max_skills = max_skills
        self.skills_dir = Path(self.workspace) / ".fnix" / "skill_library"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.skills_file = self.skills_dir / "skills.json"
        self.skills: list[CapturedSkill] = []
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        with self._lock:
            if not self.skills_file.exists():
                self.skills = []
                return
            try:
                data = json.loads(self.skills_file.read_text(encoding="utf-8"))
                self.skills = [CapturedSkill(**s) for s in data if isinstance(s, dict)]
            except Exception:
                self.skills = []

    def _save(self) -> None:
        try:
            self.skills_file.write_text(
                json.dumps(
                    [asdict(s) for s in self.skills],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    def add_new_skill(
        self,
        *,
        user_input: str,
        response: str,
        tool_calls: list[dict],
        workspace_kind: str = "general",
        success: bool = True,
        source: str = "task",
    ) -> CapturedSkill | None:
        """捕获技能（Voyager.add_new_skill 模式）。

        成功技能: 保存为可召回的正向经验。
        失败技能: 保存为可召回的反面经验（标注 success=False），供 DAAO
        计算真实失败率、避免下次重复踩坑。借鉴 Cursor Bugbot Learning
        的"开发者是否 acted on report"反馈信号思路——失败轨迹同样
        是有效训练信号。

        source 字段区分技能来源 (修复 VMAO 反思污染 failure_rate):
          "task"=真实任务产物 (默认, 计入 DAAO failure_rate)
          "vmao_reflection"=VMAO 反思中间失败 (不计入 failure_rate,
            避免正反馈回路)

        去重策略: 相同 task_hash + 7 天内不重复捕获。
        """
        if not user_input or not user_input.strip():
            return None
        task_signature = user_input.strip()[:100]
        task_hash = hashlib.md5(user_input.strip()[:200].encode("utf-8")).hexdigest()[:12]
        now = time.time()
        with self._lock:
            # 去重：相同任务 7 天内不重复捕获
            for s in self.skills:
                if s.task_hash == task_hash and (now - s.created_at) < 7 * 86400:
                    return None
            skill = CapturedSkill(
                skill_id=f"skill_{int(now * 1000)}",
                task_signature=task_signature,
                task_hash=task_hash,
                solution_summary=(response or "")[:500],
                tool_calls=[
                    {
                        "name": str(tc.get("name", "")),
                        "success": bool(tc.get("success", True)),
                    }
                    for tc in (tool_calls or [])[:10]
                ],
                workspace_kind=workspace_kind,
                success=success,
                created_at=now,
                source=source,
            )
            self.skills.append(skill)
            # 保留最近 max_skills 个
            if len(self.skills) > self.max_skills:
                self.skills = self.skills[-self.max_skills :]
            self._save()
            return skill

    def add_feedback(
        self,
        *,
        task_hash: str,
        feedback: str,
        comment: str = "",
    ) -> bool:
        """用户反馈信号回流 (对标 Cursor Bugbot Learning)。

        用户对 Agent 回复点 👍/👎, 信号回流到对应技能的 user_feedback 字段,
        影响 retrieve_skills 下次召回权重:
          - "up": 该技能下次召回权重 *1.3 (用户验证过的可靠路径)
          - "down": 该技能下次召回权重 *0.2 (用户否定的路径, 优先避开)

        匹配策略: 按 task_hash 精确匹配。若找不到精确匹配, 按 task_signature
        前缀模糊匹配 (用户可能对同一任务的不同 run 反馈)。

        Returns:
            True 如果找到并更新了技能, False 如果未找到匹配技能。
        """
        if feedback not in ("up", "down", "none"):
            return False
        now = time.time()
        with self._lock:
            # 策略 1: task_hash 精确匹配
            for s in self.skills:
                if s.task_hash == task_hash:
                    s.user_feedback = feedback
                    s.feedback_comment = (comment or "")[:500]
                    s.feedback_at = now
                    self._save()
                    return True
            # 策略 2: 无匹配, 静默返回 False (不阻断前端 UI)
            return False

    def retrieve_skills(
        self,
        query: str,
        *,
        top_k: int = 3,
        workspace_kind: str = "",
        topology_weight_provider: Callable[[str], float] | None = None,
    ) -> list[CapturedSkill]:
        """召回相关历史技能（Voyager.retrieve_skills 模式）。

        使用 Jaccard 相似度（无向量依赖）。workspace_kind 匹配的技能加分。
        失败技能以较低权重召回（作为反面经验，避免重蹈覆辙）。

        拓扑权重驱动召回（Spec 6 闭环修复，论文创新点 2）:
            topology_weight_provider(skill_signature) 返回该技能在 KTG 中
            绑定概念节点的权重 (0.0-1.0)。爬坡阶段调的权重通过此通道
            进入召回决策, 闭环 MFP 第 4 阶 → 第 5 阶 (下次召回)。
            权重 0.5 (默认初始) → score × 1.0 (中性)
            权重 1.0 (高频强化) → score × 1.25 (升权)
            权重 0.1 (弱化/废弃) → score × 0.625 (降权)
            None 或不可用 → 不影响原 score (向后兼容)
        """
        if not self.skills or not query or not query.strip():
            return []
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        with self._lock:
            scored: list[tuple[float, CapturedSkill]] = []
            for skill in self.skills:
                sig_tokens = _tokenize(skill.task_signature)
                if not sig_tokens:
                    continue
                # Jaccard 相似度
                intersection = len(query_tokens & sig_tokens)
                if intersection == 0:
                    continue
                union = len(query_tokens | sig_tokens)
                score = intersection / max(union, 1)
                # workspace_kind 匹配加分
                if workspace_kind and skill.workspace_kind == workspace_kind:
                    score *= 1.2
                # 使用次数加权（频繁使用的技能更可信）
                score *= 1.0 + 0.1 * min(skill.usage_count, 10)
                # 时间衰减（30 天半衰期）
                age_days = (time.time() - skill.created_at) / 86400
                score *= 0.5 ** (age_days / 30.0)
                # 失败技能降权（作为反面经验召回，但权重低于成功技能，
                # 避免失败案例占满 top-K 挤掉成功路径）
                if not skill.success:
                    score *= 0.6
                # 用户反馈信号 (对标 Cursor Bugbot Learning):
                # 👍 有帮助 → 微加分 (用户验证过的可靠路径)
                # 👎 没帮助 → 大幅降权 (用户否定的路径, 下次优先避开)
                if skill.user_feedback == "up":
                    score *= 1.3
                elif skill.user_feedback == "down":
                    score *= 0.2
                # 拓扑权重驱动召回 (Spec 6 闭环修复, 论文创新点 2):
                # 让 MFP 第 4 阶 (爬坡) 调的拓扑权重真正进入召回决策,
                # 闭环 KTG 权重 → skill 召回 → 下次任务感知。
                # 设计: topo_weight 0.5 为中性 (默认初始权重), 线性映射到 [0.5, 1.5]
                # 即 score *= 0.5 + topo_weight, 避免拓扑权重为 0 时把分数清零。
                if topology_weight_provider is not None:
                    try:
                        topo_weight = float(topology_weight_provider(skill.task_signature) or 0.0)
                        topo_weight = max(0.0, min(1.0, topo_weight))
                        score *= 0.5 + topo_weight
                    except Exception:
                        pass  # 拓扑查询失败不影响原召回
                scored.append((score, skill))
            scored.sort(key=lambda x: -x[0])
            result = [s for _, s in scored[:top_k]]
            # 增加使用计数
            now = time.time()
            for s in result:
                s.usage_count += 1
                s.last_used_at = now
            if result:
                self._save()
            return result

    def format_skills_for_prompt(self, skills: list[CapturedSkill]) -> str:
        """格式化为 system prompt 注入块。

        成功技能与失败技能分组展示——失败技能作为"反面经验"标注，
        驱动 LLM 避开已验证行不通的路径（对标 Reflexion 的 episodic
        memory buffer：失败轨迹的文字反思同样作为下轮输入）。
        """
        if not skills:
            return ""
        success_skills = [s for s in skills if s.success]
        failed_skills = [s for s in skills if not s.success]
        lines: list[str] = []
        if success_skills:
            lines.append("\n\n## 历史成功技能（HERA SkillLibrary · 自动捕获）")
            for i, s in enumerate(success_skills, 1):
                lines.append(f"### 技能 {i}: {s.task_signature}")
                summary = s.solution_summary[:200].replace("\n", " ")
                lines.append(f"解决方案摘要: {summary}")
                if s.tool_calls:
                    tool_seq = " → ".join(
                        tc["name"] + ("" if tc.get("success") else "✗") for tc in s.tool_calls[:5]
                    )
                    lines.append(f"工具序列: {tool_seq}")
        if failed_skills:
            lines.append("\n\n## 历史失败经验（HERA · 避免重蹈覆辙）")
            for i, s in enumerate(failed_skills, 1):
                lines.append(f"### 失败案例 {i}: {s.task_signature}")
                summary = s.solution_summary[:200].replace("\n", " ")
                lines.append(f"失败方案摘要: {summary}")
                if s.tool_calls:
                    failed_tools = [tc["name"] for tc in s.tool_calls if not tc.get("success")]
                    if failed_tools:
                        lines.append(f"失败工具: {', '.join(failed_tools[:5])}")
        if success_skills or failed_skills:
            lines.append("参考上述历史经验，复用成功路径，避免重复尝试已失败的方法。")
        return "\n".join(lines)

    def stats(self) -> dict:
        """技能库统计信息（用于 UI 展示）。"""
        with self._lock:
            return {
                "total": len(self.skills),
                "by_kind": {
                    kind: sum(1 for s in self.skills if s.workspace_kind == kind)
                    for kind in {s.workspace_kind for s in self.skills}
                },
                "recent_24h": sum(1 for s in self.skills if (time.time() - s.created_at) < 86400),
            }
