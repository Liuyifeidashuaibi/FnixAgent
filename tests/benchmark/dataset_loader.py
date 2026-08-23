"""
Dataset loader for all benchmark datasets.
Loads and normalizes tasks from: web-bench, workbuddy-bench, vibe-code-bench,
prototypebench, swe-bench Lite.
"""

import json
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import yaml


@dataclass
class BenchmarkTask:
    """A single benchmark task."""

    dataset: str  # web-bench / workbuddy-bench / vibe-code-bench / prototypebench / swe-bench-lite
    task_id: str  # unique within dataset
    prompt: str  # raw prompt, unmodified
    subset: str = ""  # e.g. code/web/office/sec for workbuddy
    metadata: dict = field(default_factory=dict)

    @property
    def unique_id(self) -> str:
        return f"{self.dataset}::{self.task_id}"


DATASETS_DIR = Path("E:/FNIX/FnixAgent/test-results/benchmark/datasets")


def load_web_bench() -> list[BenchmarkTask]:
    """Load web-bench tasks from projects/*/tasks.jsonl."""
    tasks: list[BenchmarkTask] = []
    base = DATASETS_DIR / "web-bench" / "projects"
    if not base.exists():
        return tasks

    for project_dir in sorted(base.iterdir()):
        if not project_dir.is_dir():
            continue
        project_name = project_dir.name
        tasks_file = project_dir / "tasks.jsonl"
        yml_file = project_dir / "tasks.yml"
        if tasks_file.exists():
            with open(tasks_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        task_id = obj.get("id", f"{project_name}-unknown")
                        prompt = obj.get("description", "")
                        if not prompt:
                            continue
                        tasks.append(
                            BenchmarkTask(
                                dataset="web-bench",
                                task_id=f"{project_name}/{task_id}",
                                prompt=prompt,
                                subset=project_name,
                                metadata={
                                    "level": obj.get("level", ""),
                                    "date": obj.get("date", ""),
                                },
                            )
                        )
                    except json.JSONDecodeError:
                        continue
        elif yml_file.exists():
            try:
                entries = yaml.safe_load(yml_file.read_text(encoding="utf-8")) or []
            except Exception:
                continue
            for obj in entries:
                if not isinstance(obj, dict):
                    continue
                task_id = obj.get("id", f"{project_name}-unknown")
                prompt = (obj.get("description") or "").strip()
                if not prompt:
                    continue
                tasks.append(
                    BenchmarkTask(
                        dataset="web-bench",
                        task_id=f"{project_name}/{task_id}",
                        prompt=prompt,
                        subset=project_name,
                        metadata={
                            "level": obj.get("level", ""),
                            "date": str(obj.get("date", "")),
                        },
                    )
                )
    return tasks


def load_workbuddy_bench() -> list[BenchmarkTask]:
    """Load workbuddy-bench tasks from datasets/wb-bench-*/tasks/*/instruction.md."""
    tasks: list[BenchmarkTask] = []
    base = DATASETS_DIR / "workbuddy-bench" / "datasets"

    subset_map = {
        "wb-bench-code-v1.0": "code",
        "wb-bench-web-v1.0": "web",
        "wb-bench-office-v1.0": "office",
        "wb-bench-sec-v1.0": "sec",
    }

    for dir_name, subset in subset_map.items():
        subset_dir = base / dir_name / "tasks"
        if not subset_dir.exists():
            continue
        for task_dir in sorted(subset_dir.iterdir()):
            if not task_dir.is_dir():
                continue
            instruction_file = task_dir / "instruction.md"
            if not instruction_file.exists():
                continue
            prompt = instruction_file.read_text(encoding="utf-8").strip()
            if not prompt:
                continue
            tasks.append(
                BenchmarkTask(
                    dataset="workbuddy-bench",
                    task_id=task_dir.name,
                    prompt=prompt,
                    subset=subset,
                    metadata={},
                )
            )
    return tasks


def load_vibe_code_bench() -> list[BenchmarkTask]:
    """Load vibe-code-bench tasks from eval_cases/case_*/spec.md."""
    tasks: list[BenchmarkTask] = []
    base = DATASETS_DIR / "vibe-code-bench" / "eval_cases"
    if not base.exists():
        return tasks

    for case_dir in sorted(base.iterdir()):
        if not case_dir.is_dir():
            continue
        spec_file = case_dir / "spec.md"
        if not spec_file.exists():
            continue
        prompt = spec_file.read_text(encoding="utf-8").strip()
        if not prompt:
            continue
        tasks.append(
            BenchmarkTask(
                dataset="vibe-code-bench",
                task_id=case_dir.name,
                prompt=prompt,
                subset="",
                metadata={},
            )
        )
    return tasks


def load_prototypebench() -> list[BenchmarkTask]:
    """Load prototypebench tasks from tasks/instances*.jsonl."""
    tasks: list[BenchmarkTask] = []
    base = DATASETS_DIR / "prototypebench" / "tasks"
    if not base.exists():
        return tasks

    for jsonl_file in sorted(base.glob("instances*.jsonl")):
        with open(jsonl_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    task_id = obj.get("instance_id", "")
                    prompt = obj.get("problem_statement", "")
                    if not prompt or not task_id:
                        continue
                    tasks.append(
                        BenchmarkTask(
                            dataset="prototypebench",
                            task_id=task_id,
                            prompt=prompt,
                            subset=obj.get("stack_domain", ""),
                            metadata={
                                "repo": obj.get("repo", ""),
                                "pr_number": obj.get("pr_number", ""),
                            },
                        )
                    )
                except json.JSONDecodeError:
                    continue
    return tasks


def load_swe_bench_lite() -> list[BenchmarkTask]:
    """Load SWE-bench Lite tasks from HF parquet."""
    tasks: list[BenchmarkTask] = []
    parquet_file = DATASETS_DIR / "swe-bench-lite-hf" / "data" / "test-00000-of-00001.parquet"
    if not parquet_file.exists():
        return tasks

    df = pd.read_parquet(str(parquet_file))
    for _, row in df.iterrows():
        task_id = str(row.get("instance_id", ""))
        prompt = str(row.get("problem_statement", ""))
        if not prompt or not task_id:
            continue
        tasks.append(
            BenchmarkTask(
                dataset="swe-bench-lite",
                task_id=task_id,
                prompt=prompt,
                subset="",
                metadata={
                    "repo": str(row.get("repo", "")),
                    "version": str(row.get("version", "")),
                    "difficulty": str(row.get("difficulty", "")),
                },
            )
        )
    return tasks


def load_all_datasets() -> dict[str, list[BenchmarkTask]]:
    """Load all available datasets. Returns dict keyed by dataset name."""
    loaders = {
        "web-bench": load_web_bench,
        "workbuddy-bench": load_workbuddy_bench,
        "vibe-code-bench": load_vibe_code_bench,
        "prototypebench": load_prototypebench,
        "swe-bench-lite": load_swe_bench_lite,
    }

    result = {}
    for name, loader in loaders.items():
        try:
            tasks = loader()
            result[name] = tasks
            print(f"  {name}: {len(tasks)} tasks loaded")
        except Exception as e:
            print(f"  {name}: FAILED to load - {e}")
            result[name] = []

    total = sum(len(v) for v in result.values())
    print(f"  TOTAL: {total} tasks across {len(result)} datasets")
    return result


if __name__ == "__main__":
    datasets = load_all_datasets()
    for name, tasks in datasets.items():
        if tasks:
            print(f"\n{name} sample task:")
            t = tasks[0]
            print(f"  ID: {t.task_id}")
            print(f"  Prompt (first 200): {t.prompt[:200]}")
