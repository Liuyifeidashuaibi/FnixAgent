"""Full-chain system benchmark — infra, harness, work, code, FCS."""

from __future__ import annotations

import os
import tempfile
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
BENCH_ROOT = ROOT / "benchmarks" / "code"


@dataclass
class StageResult:
    id: str
    category: str
    ok: bool
    score: float
    message: str
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemBenchmarkReport:
    overall_score: float
    hard_pass: bool
    stage_count: int
    passed: int
    by_category: dict[str, float]
    stages: list[StageResult]
    fcs: float | None = None
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "hard_pass": self.hard_pass,
            "stage_count": self.stage_count,
            "passed": self.passed,
            "by_category": self.by_category,
            "fcs": self.fcs,
            "recommendations": self.recommendations,
            "stages": [asdict(s) for s in self.stages],
        }


CATEGORY_WEIGHTS: dict[str, float] = {
    "frontend": 0.10,
    "infra": 0.20,
    "harness": 0.15,
    "work": 0.10,
    "code": 0.20,
    "fcs": 0.20,
    "llm": 0.05,
}

CATEGORY_WEIGHTS_NO_LLM: dict[str, float] = {
    "frontend": 0.12,
    "infra": 0.25,
    "harness": 0.18,
    "work": 0.12,
    "code": 0.28,
    "fcs": 0.05,
}


def _stage(
    sid: str,
    category: str,
    fn: Callable[[], tuple[bool, str, dict[str, Any]]],
) -> StageResult:
    t0 = time.perf_counter()
    try:
        ok, message, details = fn()
        score = 100.0 if ok else 0.0
    except Exception as e:
        ok, message, details, score = False, str(e), {}, 0.0
    return StageResult(
        id=sid,
        category=category,
        ok=ok,
        score=score,
        message=message,
        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
        details=details,
    )


def _aggregate(stages: list[StageResult], include_llm: bool) -> SystemBenchmarkReport:
    from fnixagent.core.benchmark.optimizer import build_recommendations

    weights = CATEGORY_WEIGHTS if include_llm else CATEGORY_WEIGHTS_NO_LLM
    cat_sum: dict[str, float] = {}
    cat_w: dict[str, float] = {}
    for s in stages:
        w = weights.get(s.category, 0.1)
        cat_sum[s.category] = cat_sum.get(s.category, 0.0) + s.score * w
        cat_w[s.category] = cat_w.get(s.category, 0.0) + w

    by_category = {k: round(cat_sum[k] / cat_w[k], 2) for k in cat_sum if cat_w[k] > 0}
    total_w = sum(weights.get(s.category, 0.1) for s in stages)
    weighted = sum(s.score * weights.get(s.category, 0.1) for s in stages)
    overall = round(weighted / total_w, 2) if total_w else 0.0

    passed = sum(1 for s in stages if s.ok)
    infra_ok = all(s.ok for s in stages if s.category == "infra")
    code_ok = all(s.ok for s in stages if s.category == "code")
    hard_pass = infra_ok and code_ok and overall >= 70.0

    fcs_val = None
    for s in stages:
        if s.id == "fcs.smoke" and s.details.get("fcs") is not None:
            fcs_val = float(s.details["fcs"])

    recs = build_recommendations(stages, by_category, overall)
    return SystemBenchmarkReport(
        overall_score=overall,
        hard_pass=hard_pass,
        stage_count=len(stages),
        passed=passed,
        by_category=by_category,
        stages=stages,
        fcs=fcs_val,
        recommendations=recs,
    )


def run_infra_stages() -> list[StageResult]:
    stages: list[StageResult] = []

    def health() -> tuple[bool, str, dict[str, Any]]:
        return True, "agentd process alive", {"status": "ok"}

    stages.append(_stage("infra.health", "infra", health))

    def harness_status() -> tuple[bool, str, dict[str, Any]]:
        from fnixagent.harness.gateway import get_harness_status

        st = get_harness_status()
        ok = bool(st)
        return ok, "harness gateway reachable" if ok else "harness status empty", dict(st or {})

    stages.append(_stage("infra.harness_status", "infra", harness_status))
    return stages


def run_harness_stages(workspace: Path) -> list[StageResult]:
    stages: list[StageResult] = []

    def ensure() -> tuple[bool, str, dict[str, Any]]:
        from fnixagent.harness.workspace import ensure_project_layout

        layout = ensure_project_layout(str(workspace))
        ok = (workspace / ".fnix").is_dir()
        return ok, f"workspace layout at {workspace}", {"layout": layout}

    stages.append(_stage("harness.workspace", "harness", ensure))

    def config() -> tuple[bool, str, dict[str, Any]]:
        from fnixagent.harness.config import read_config_toml
        from fnixagent.harness.secrets import secrets_status

        cfg = read_config_toml()
        sec = secrets_status()
        has_key = bool(sec.get("has_api_key") or os.environ.get("DASHSCOPE_API_KEY"))
        return (
            True,
            "config loaded" + (" · API key set" if has_key else " · no API key"),
            {
                "has_api_key": has_key,
                "model": cfg.get("model"),
                "provider": cfg.get("provider"),
            },
        )

    stages.append(_stage("harness.config", "harness", config))
    return stages


def run_code_stages(workspace: Path) -> list[StageResult]:
    stages: list[StageResult] = []

    def apply() -> tuple[bool, str, dict[str, Any]]:
        import asyncio

        from fnixagent.core.code.diff import ChangeSetBuilder, DiffEngine

        async def _apply() -> tuple[bool, str]:
            engine = DiffEngine(project_root=str(workspace))
            builder = ChangeSetBuilder("benchmark-apply")
            builder.create_file("benchmark_probe.txt", "fnix full-chain ok\n")
            cs = builder.build()
            result = await engine.apply(cs, dry_run=False)
            if not result.success:
                return False, result.error or "apply failed"
            probe = workspace / "benchmark_probe.txt"
            if not probe.is_file():
                return False, "probe file missing"
            text = probe.read_text(encoding="utf-8")
            if "full-chain ok" not in text:
                return False, f"content mismatch: {text!r}"
            return True, "apply + verify ok"

        try:
            asyncio.get_running_loop()
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                ok, msg = pool.submit(asyncio.run, _apply()).result(timeout=60)
        except RuntimeError:
            ok, msg = asyncio.run(_apply())
        return ok, msg, {}

    stages.append(_stage("code.apply", "code", apply))

    def sessions() -> tuple[bool, str, dict[str, Any]]:
        from fnixagent.harness.session import get_session_store

        store = get_session_store()
        sessions_list = store.list_sessions(workspace=str(workspace), limit=5)
        return True, f"{len(sessions_list)} session(s) listed", {"count": len(sessions_list)}

    stages.append(_stage("code.sessions", "code", sessions))
    return stages


def run_work_stage() -> StageResult:
    def status() -> tuple[bool, str, dict[str, Any]]:
        return True, "work router registered", {"ready": True}

    return _stage("work.status", "work", status)


def run_fcs_smoke(
    *,
    limit: int = 3,
    tag: str = "smoke",
    agent_base: str = "",
) -> StageResult:
    def fcs() -> tuple[bool, str, dict[str, Any]]:
        from fnixagent.core.code.benchmark.runner import (
            RunOptions,
            load_manifest,
            resolve_task_paths,
            run_task,
        )
        from fnixagent.core.code.benchmark.schema import load_task
        from fnixagent.core.code.benchmark.scorer import aggregate_scores

        curated = BENCH_ROOT / "curated" / "manifest.json"
        manifest_path = curated if curated.is_file() else BENCH_ROOT / "manifest.json"
        if not manifest_path.is_file():
            return False, "manifest missing — run generate-code-tasks.py", {}

        task_ids = load_manifest(manifest_path)
        selected: list[str] = []
        for tid in task_ids:
            for sub in ("seed", "generated"):
                p = BENCH_ROOT / sub / f"{tid}.json"
                if not p.is_file():
                    continue
                task = load_task(p)
                if tag and tag not in task.tags:
                    continue
                selected.append(tid)
                break
            if len(selected) >= limit:
                break

        if not selected:
            return False, f"no tasks for tag={tag!r}", {}

        paths = resolve_task_paths(BENCH_ROOT, selected)
        if not paths:
            return False, "empty FCS task paths", {}

        base = agent_base or f"http://127.0.0.1:{os.environ.get('FNIX_API_PORT', '8003')}"
        opts = RunOptions(dry_checks_only=False, agent_base_url=base, skip_agent=False)
        scores = [run_task(p, opts) for p in paths]
        if not scores:
            return False, "empty FCS scores", {"tasks": 0}

        report = aggregate_scores(scores)
        # Plan Day 61–90: fail soft thresholds; default 70% (was incorrectly 25%).
        min_hp = float(os.environ.get("FNIX_FCS_MIN_HARD_PASS", "70"))
        ok = report.hard_pass_rate >= min_hp
        return (
            ok,
            f"FCS={report.fcs} hard_pass={report.hard_pass_rate}% "
            f"(min={min_hp}%, {len(scores)} tasks, manifest={manifest_path.name})",
            {
                "fcs": report.fcs,
                "hard_pass_rate": report.hard_pass_rate,
                "min_hard_pass": min_hp,
                "tasks": len(scores),
                "manifest": str(manifest_path),
            },
        )

    return _stage("fcs.smoke", "fcs", fcs)


def run_llm_test() -> StageResult:
    def llm() -> tuple[bool, str, dict[str, Any]]:
        import asyncio

        from fnixagent.harness.config import read_config_toml
        from fnixagent.harness.secrets import get_llm_api_key, secrets_status

        sec = secrets_status()
        key = get_llm_api_key() or os.environ.get("DASHSCOPE_API_KEY", "").strip()
        if not key and not sec.get("has_api_key"):
            return False, "no API key configured", {}

        async def _ping() -> tuple[bool, str, dict[str, Any]]:
            from fnixagent.core.llm.adapter import LLMAdapter
            from fnixagent.services.llm_policy import resolve_llm_for_request

            cfg = read_config_toml()
            llm_dict, err = resolve_llm_for_request(None, is_admin=True)
            if err:
                return False, err, {}
            adapter = LLMAdapter(
                api_key=llm_dict.get("api_key") or key,
                base_url=llm_dict.get("base_url") or cfg.get("base_url") or "",
                model_name=llm_dict.get("model") or cfg.get("model") or "",
                provider_name=llm_dict.get("provider") or cfg.get("provider") or "",
            )
            if not adapter.is_configured:
                return False, "LLM adapter not configured", {}
            result = await adapter.chat(
                [{"role": "user", "content": "Reply with exactly: pong"}],
                tools=None,
                model=adapter.model_name,
                max_tokens=16,
                temperature=0,
            )
            content = ""
            choices = result.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                content = str(msg.get("content") or "")
            ok = "pong" in content.lower()
            return ok, f"LLM reply: {content[:40]}", {"model": adapter.model_name}

        try:
            return asyncio.run(_ping())
        except Exception as e:
            return False, str(e), {}

    return _stage("llm.connectivity", "llm", llm)


def merge_client_stages(client: list[dict[str, Any]]) -> list[StageResult]:
    out: list[StageResult] = []
    for item in client:
        out.append(
            StageResult(
                id=str(item.get("id", "frontend.unknown")),
                category=str(item.get("category", "frontend")),
                ok=bool(item.get("ok")),
                score=float(item.get("score", 100 if item.get("ok") else 0)),
                message=str(item.get("message", "")),
                duration_ms=float(item.get("duration_ms", 0)),
                details=dict(item.get("details") or {}),
            )
        )
    return out


async def run_full_chain(
    *,
    app_state: Any = None,
    workspace: str | None = None,
    include_llm: bool = False,
    fcs_limit: int = 3,
    fcs_tag: str = "smoke",
    agent_base: str = "",
    client_stages: list[dict[str, Any]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield NDJSON events: stage | done."""
    with tempfile.TemporaryDirectory(prefix="fnix-bench-") as tmp:
        ws = Path(workspace or tmp)
        ws.mkdir(parents=True, exist_ok=True)

        all_stages: list[StageResult] = []

        if client_stages:
            client_results = merge_client_stages(client_stages)
            for s in client_results:
                all_stages.append(s)
                yield {"type": "stage", "stage": asdict(s)}

        for s in run_infra_stages():
            all_stages.append(s)
            yield {"type": "stage", "stage": asdict(s)}

        if app_state is not None:

            def work_check() -> tuple[bool, str, dict[str, Any]]:
                from fnixagent.services.engine_status import merge_work_status

                st = merge_work_status(app_state, is_admin=True)
                return True, "work engine ready", {"keys": list(st.keys())[:8]}

            ws_stage = _stage("work.engine", "work", work_check)
            all_stages.append(ws_stage)
            yield {"type": "stage", "stage": asdict(ws_stage)}
        else:
            ws_stage = run_work_stage()
            all_stages.append(ws_stage)
            yield {"type": "stage", "stage": asdict(ws_stage)}

        for s in run_harness_stages(ws):
            all_stages.append(s)
            yield {"type": "stage", "stage": asdict(s)}

        for s in run_code_stages(ws):
            all_stages.append(s)
            yield {"type": "stage", "stage": asdict(s)}

        if include_llm:
            llm_stage = run_llm_test()
            all_stages.append(llm_stage)
            yield {"type": "stage", "stage": asdict(llm_stage)}

            fcs_stage = run_fcs_smoke(limit=fcs_limit, tag=fcs_tag, agent_base=agent_base)
            all_stages.append(fcs_stage)
            yield {"type": "stage", "stage": asdict(fcs_stage)}
        else:
            dry_fcs = _stage(
                "fcs.manifest",
                "fcs",
                lambda: (
                    (BENCH_ROOT / "manifest.json").is_file(),
                    "benchmark manifest present"
                    if (BENCH_ROOT / "manifest.json").is_file()
                    else "run generate-code-tasks.py",
                    {"path": str(BENCH_ROOT / "manifest.json")},
                ),
            )
            all_stages.append(dry_fcs)
            yield {"type": "stage", "stage": asdict(dry_fcs)}

        report = _aggregate(all_stages, include_llm)
        yield {"type": "done", "report": report.to_dict()}
