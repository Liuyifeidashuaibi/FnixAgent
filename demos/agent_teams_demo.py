# -*- coding: utf-8 -*-
"""AgentTeams 演示 — 一条命令看懂多角色协作。

用法:
    python demos/agent_teams_demo.py            # 自动: 有 API Key 走真实 LLM, 否则 Mock
    python demos/agent_teams_demo.py --mock     # 强制离线 Mock
    python demos/agent_teams_demo.py --real     # 强制真实 LLM

场景: 主 Agent 接到"调研并评审快速排序资料"的任务,
      fan_out 并行派发 → 工人执行 → 黑板落盘 → critic 交叉评审。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from fnixagent.core.teams import AgentTeam, read_handover  # noqa: E402


def build_llm_factory(force_mock: bool):
    """优先真实 LLM(复用主程序 .env 配置), 否则 Mock。"""
    if not force_mock:
        try:
            from fnixagent.services.work_agent import adapter_from_llm_override

            adapter = adapter_from_llm_override(None)
            if adapter.is_configured:
                print(f"[llm] 使用真实 LLM: {adapter.provider_name} / {adapter.model_name}")

                def make_real():
                    def llm_call(messages, tools=None):
                        import asyncio

                        return asyncio.run(
                            adapter.chat(messages, tools=tools, temperature=0.5)
                        )

                    return llm_call, None

                return make_real
        except Exception as exc:  # noqa: BLE001
            print(f"[llm] 真实 LLM 不可用({exc}), 回退 Mock")

    def make_mock():
        def llm_call(messages, tools=None):
            last = messages[-1]["content"][:40]
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": f"[Mock 结论] 针对「{last}」: 要点1 / 要点2 / 来源已核对。",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"total_tokens": 42},
            }

        return llm_call, None

    print("[llm] 使用离线 Mock")
    return make_mock


def main() -> None:
    import asyncio

    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--real", action="store_true")
    args = ap.parse_args()

    workspace = tempfile.mkdtemp(prefix="fnix_teams_demo_")
    team = AgentTeam(workspace, build_llm_factory(args.mock), max_parallel=3)

    print(f"[team] 团队目录: {team.team_dir}\n")
    specs = [
            {
                "role": "researcher",
                "subject": "调研快速排序原理",
                "prompt": "用要点说明快排的分治思想与复杂度，150 字内。",
            },
            {
                "role": "researcher",
                "subject": "调研归并排序对比",
                "prompt": "给出快排 vs 归并的稳定性与最坏复杂度对比，100 字内。",
            },
            {
                "role": "critic",
                "subject": "评审调研质量",
                "prompt": (
                    "材料A: 快排分治、平均 O(n log n)、不稳定。\n"
                    "材料B: 归并稳定、最坏 O(n log n)、需 O(n) 辅助空间。\n"
                    "请按 ISSUES/SCORE/VERDICT 格式评审以上两条材料是否准确。"
                ),
            },
        ]
    result = asyncio.run(team.fan_out(specs))

    print("\n========== 执行结果 ==========")
    for r in result["results"]:
        icon = "[PASS]" if r["status"] == "success" else "[FAIL]"
        print(f"{icon} [{r['task_id']}] {r['role']:<10} {r['status']}")
        if r["summary"]:
            print(f"   └ {r['summary'][:80]}...")
        if r["artifact_path"]:
            meta, body = read_handover(r["artifact_path"])
            print(f"   └ 黑板文档: {Path(r['artifact_path']).name} "
                  f"(status={meta['status']}, {len(body)}字)")

    print("\n========== 共享任务清单 ==========")
    print(json.dumps(result["stats"], ensure_ascii=False))

    print("\n========== 进度账本(Magentic 式五问) ==========")
    print(json.dumps(result["progress"], ensure_ascii=False, indent=1))

    print(f"\n[tip] 黑板全文在 {team.team_dir}{chr(92)}outputs{chr(92)}*.md")


if __name__ == "__main__":
    main()
