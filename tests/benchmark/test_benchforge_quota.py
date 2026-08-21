"""BenchForge 配额感知回归测试。

锁住三类关键行为，防止功能退化（零配额消耗，全部走伪造 Agent/判定）：
  1. 判定器：配额/鉴权错误必须归为 infra_skip，且与 run.status 是否为 FAILURE 无关
  2. 统计口径：infra_skip 不计能力失败，成功率分母 = 成功 + 失败
  3. 断点续跑：配额跳过任务不锁入 completed，可重试；已成功任务跳过
  4. 配额熔断：连续 infra 错误超阈值提前停止，不再空转
"""
from __future__ import annotations

import json

from fnixagent.bench.judge import Judge
from fnixagent.bench.runner import BenchRunner
from fnixagent.bench.schema import BenchTask, RunSummary, TaskRun, TaskStatus

# ---------------------------------------------------------------------------
# 1) 判定器：配额错误归类
# ---------------------------------------------------------------------------

def test_quota_error_maps_to_infra_skip_even_when_status_pending():
    """agent 返回失败时 status 仍是 PENDING，配额错误必须照样识别。"""
    run = TaskRun(dataset="d", task_id="t", prompt="p")
    run.error = "LLM 调用失败: [qwen] request failed: HTTP 403 (Free quota exhausted.)"
    assert run.status == TaskStatus.PENDING
    verdict = Judge()._heuristic_inner(
        BenchTask(dataset="d", task_id="t", prompt="p"), run
    )
    assert verdict is not None
    assert verdict.status == TaskStatus.INFRA_SKIP


def test_insufficient_quota_variant_also_infra_skip():
    run = TaskRun(dataset="d", task_id="t", prompt="p")
    run.error = "upstream returned insufficient_quota"
    verdict = Judge()._heuristic_inner(
        BenchTask(dataset="d", task_id="t", prompt="p"), run
    )
    assert verdict is not None and verdict.status == TaskStatus.INFRA_SKIP


def test_normal_failure_not_infra():
    """普通崩溃不能误判成配额跳过。"""
    run = TaskRun(dataset="d", task_id="t", prompt="p")
    run.error = "Traceback (most recent call last): KeyError: 'foo'"
    verdict = Judge()._heuristic_inner(
        BenchTask(dataset="d", task_id="t", prompt="p"), run
    )
    assert verdict is None or verdict.status != TaskStatus.INFRA_SKIP


# ---------------------------------------------------------------------------
# 2) 统计口径
# ---------------------------------------------------------------------------

def test_summary_excludes_infra_from_failure_and_rate_denominator():
    s = RunSummary(run_id="x", model="m", started_at=0)
    s.add_run(TaskRun(dataset="d", task_id="a", prompt="", status=TaskStatus.SUCCESS))
    s.add_run(TaskRun(dataset="d", task_id="b", prompt="", status=TaskStatus.INFRA_SKIP))
    s.add_run(TaskRun(dataset="d", task_id="c", prompt="",
                      status=TaskStatus.FAILURE, failure_type="crash"))
    t = s.totals
    assert t["total"] == 3
    assert t["success"] == 1 and t["failure"] == 1
    assert t["infra_skip"] == 1
    # 成功率分母 = 成功+失败 = 2，故 1/2
    assert t["success_rate"] == 0.5


# ---------------------------------------------------------------------------
# 3) 断点续跑：配额跳过可重试
# ---------------------------------------------------------------------------

def test_checkpoint_keeps_quota_tasks_retryable(tmp_path):
    results = tmp_path / "results.jsonl"
    rows = [
        {"dataset": "d", "task_id": "ok1", "prompt": "p",
         "status": "success", "failure_type": ""},
        {"dataset": "d", "task_id": "q1", "prompt": "p",
         "status": "infra_skip", "failure_type": ""},
    ]
    results.write_text("\n".join(json.dumps(r) for r in rows), "utf-8")
    runner = BenchRunner(output_dir=tmp_path, model="m")
    assert "d/ok1" in runner._completed
    assert "d/q1" not in runner._completed  # 配额跳过必须保持可重跑
    assert runner._summary.totals["success"] == 1
    assert runner._summary.totals["infra_skip"] == 0  # 载入时不计入，留待重跑


# ---------------------------------------------------------------------------
# 4) 配额熔断
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, success=False, error="", response=""):
        self.success = success
        self.error = error
        self.response = response
        self.total_tokens = 0


class _FakeQuotaAgent:
    """模拟每次都因配额耗尽而失败的 Agent。"""

    def __init__(self):
        self.traces = []

    def reset(self):
        pass

    async def run(self, prompt):
        return _FakeResult(success=False,
                           error="HTTP 403 (Free quota exhausted.)")


def test_quota_circuit_breaker_aborts_early(tmp_path):
    tasks = [BenchTask(dataset="d", task_id=f"t{i}", prompt="p") for i in range(10)]
    runner = BenchRunner(
        output_dir=tmp_path, model="m",
        agent_builder=lambda ws: _FakeQuotaAgent(),
        max_concurrency=1, quota_abort_threshold=3,
    )
    judge = Judge(llm_call=None, use_llm_for_ambiguous=False)
    summary = runner.run_all(tasks, judge=judge)
    assert runner._quota_aborted is True
    # 只消耗了阈值条就熔断，而不是把 10 条全部空转
    assert summary.totals["infra_skip"] == 3
    assert summary.totals["failure"] == 0
    # 熔断的任务都没被锁成 completed，全部可重跑
    assert len(runner._completed) == 0
    assert "熔断" in (summary.note or "")
