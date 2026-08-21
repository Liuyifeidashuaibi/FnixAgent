"""BenchForge — 六大数据集获取与解析器。

职责：
  1. 从 GitHub / HuggingFace 拉取原始数据（缓存到本地，断网可复用）
  2. 解析 json / jsonl / parquet，提取原始 prompt（严禁改写）
  3. 统一成 BenchTask 流，供 BenchRunner 逐条消费
  4. 下载 / 解析异常：记录错误，返回空列表，绝不中断整体流程

缓存目录：benchmarks/benchforge/datasets/{dataset}/
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import logging
import re
import urllib.request
import zipfile
import io
from pathlib import Path
from typing import Any, Callable, Iterator

from fnixagent.bench.schema import BenchTask

_logger = logging.getLogger(__name__)

_HF_RESOLVE = "https://huggingface.co/datasets/{repo}/resolve/main/{path}"
_GH_RAW = "https://raw.githubusercontent.com/{repo}/HEAD/{path}"


class DatasetFetchError(Exception):
    """数据集下载 / 解析失败（记录后继续，不中断评测）。"""


def _http_get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "fnixagent-benchforge/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _read_jsonl(raw: bytes | str) -> list[dict[str, Any]]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    out: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as exc:
            _logger.warning("jsonl 行解析失败（已跳过该行）: %s", exc)
    return out


def _extract_prompt(record: dict[str, Any], candidates: list[str]) -> str:
    """按候选字段顺序提取原始 prompt；取不到时退回最长字符串字段。"""
    for key in candidates:
        val = record.get(key)
        if isinstance(val, str) and val.strip():
            return val          # 原样返回，不做任何清洗 / 改写
    best = ""
    for val in record.values():
        if isinstance(val, str) and len(val) > len(best):
            best = val
    return best


# ---------------------------------------------------------------------------
# 各数据集解析器（每个返回 Iterator[BenchTask]）
# ---------------------------------------------------------------------------

def _local_clone(repo_dirname: str) -> Path | None:
    """本地 git clone 优先：data/bench-datasets/<repo_dirname>/。"""
    repo_root = Path(__file__).resolve().parents[2]
    for cand in (repo_root / "data" / "bench-datasets" / repo_dirname,
                 Path("data/bench-datasets") / repo_dirname):
        if cand.is_dir():
            return cand.resolve()
    return None


def _load_web_bench(cache: Path) -> list[BenchTask]:
    """Web-Bench: projects 目录下 tasks.jsonl → description。"""
    tasks: list[BenchTask] = []
    local = _local_clone("web-bench")
    if local is not None:
        entries: list[tuple[str, str]] = []
        for jf in sorted((local / "projects").glob("*/tasks.jsonl")):
            entries.append((jf.parent.name, jf.read_text(encoding="utf-8")))
        if not entries:
            raise DatasetFetchError(f"本地 web-bench 无 tasks.jsonl: {local}")
    else:
        zip_url = "https://github.com/bytedance/web-bench/archive/refs/heads/main.zip"
        raw = _http_get(zip_url, timeout=180)
        zf = zipfile.ZipFile(io.BytesIO(raw))
        jsonl_names = [n for n in zf.namelist() if re.search(r"projects/.*/tasks\.jsonl$", n)]
        if not jsonl_names:
            jsonl_names = [n for n in zf.namelist() if n.endswith("tasks.jsonl")]
        entries = [(n.split("/")[-2], zf.read(n).decode("utf-8", errors="replace"))
                   for n in sorted(jsonl_names)]
    for project, text in entries:
        for i, rec in enumerate(_read_jsonl(text)):
            prompt = _extract_prompt(rec, ["description", "prompt", "task"])
            if not prompt:
                continue
            # web-bench 每个项目共享 task-1..task-20 同一 id 空间，
            # 必须前缀项目名保证数据集内唯一（否则 checkpoint 去重冲突、轨迹互相覆盖）
            base_id = str(rec.get("id") or rec.get("task_id") or f"task-{i+1}")
            tasks.append(BenchTask(
                dataset="web-bench",
                task_id=f"{project}--{base_id}",
                prompt=prompt, subset=project, expected=rec.get("test") or rec.get("tests"),
                meta=rec,
            ))
    return tasks


def _load_hf_jsonl(repo: str, candidates: list[str], cache: Path) -> list[dict[str, Any]]:
    """从 HF datasets 仓库逐个尝试候选 jsonl 文件。"""
    for path in candidates:
        url = _HF_RESOLVE.format(repo=repo, path=path)
        try:
            raw = _http_get(url)
        except Exception as exc:
            _logger.warning("HF 文件不可达 %s: %s", url, exc)
            continue
        records = _read_jsonl(raw)
        if records:
            return records
    raise DatasetFetchError(f"HF 仓库 {repo} 所有候选文件均不可用: {candidates}")


def _load_hf_parquet(repo: str, config: str, split: str, cache: Path) -> list[dict[str, Any]]:
    """通过 HF parquet 转换 API 拉取（GAIA / SWE-bench 等 parquet 格式）。"""
    import pandas as pd  # noqa: PLC0415

    urls = [
        f"https://huggingface.co/api/datasets/{repo}/parquet/{config}/{split}",
        f"https://huggingface.co/api/datasets/{repo}/parquet",
    ]
    for url in urls:
        try:
            listing = json.loads(_http_get(url).decode("utf-8"))
        except Exception as exc:
            _logger.warning("parquet 列表不可达 %s: %s", url, exc)
            continue
        files = listing if isinstance(listing, list) else listing.get("parquet_files", [])
        records: list[dict[str, Any]] = []
        for item in files:
            file_url = item if isinstance(item, str) else item.get("url", "")
            if not file_url:
                continue
            try:
                df = pd.read_parquet(io.BytesIO(_http_get(file_url, timeout=300)))
                records.extend(df.to_dict("records"))
            except Exception as exc:
                _logger.warning("parquet 文件读取失败 %s: %s", file_url, exc)
        if records:
            return records
    raise DatasetFetchError(f"HF parquet 不可用: {repo} ({config}/{split})")


def _load_workbuddy(cache: Path) -> list[BenchTask]:
    """WorkBuddy-Bench: HF tarball (web70/code/office/sec) -> tasks/*/instruction.md。"""
    import tarfile

    local = _local_clone("workbuddy-bench")
    raw_dir = (local / "raw") if local else None
    subsets = [
        ("web", "wb-bench-web-v1.0.tar.gz"),
        ("code", "wb-bench-code-v1.0.tar.gz"),
        ("office", "wb-bench-office-v1.0.tar.gz"),
        ("sec", "wb-bench-sec-v1.0.tar.gz"),
    ]
    tasks: list[BenchTask] = []
    missing: list[str] = []
    for subset, fname in subsets:
        tar_path = (raw_dir / fname) if raw_dir else None
        if tar_path is None or not tar_path.is_file():
            cache.mkdir(parents=True, exist_ok=True)
            tar_path = cache / fname
            if not tar_path.is_file():
                url = _HF_RESOLVE.format(repo="tencent/workbuddy-bench", path=fname)
                try:
                    tar_path.write_bytes(_http_get(url, timeout=600))
                except Exception as exc:
                    missing.append(f"{subset}: {exc}")
                    continue
        try:
            with tarfile.open(tar_path, "r:gz") as tf:
                for member in tf.getmembers():
                    if not member.name.endswith("/instruction.md"):
                        continue
                    # 各子集内任务目录名可能重名（如 task-01），前缀 subset 保证全库唯一
                    task_id = f"{subset}--{member.name.split('/')[-2]}"
                    fh = tf.extractfile(member)
                    if fh is None:
                        continue
                    prompt = fh.read().decode("utf-8", errors="replace").strip()
                    if not prompt:
                        continue
                    tasks.append(BenchTask(
                        dataset="workbuddy-bench",
                        task_id=task_id,
                        prompt=prompt,
                        subset=subset,
                        expected=None,
                        meta={"tarball": fname},
                    ))
        except Exception as exc:
            missing.append(f"{subset}: 解析失败 {exc}")
    # 硬去重：同一 subset 中若仍重名（深层嵌套目录同 parents），追加序号，
    # 保证全量任务都运行、checkpoint 互不覆盖 —— 不重跑也不丢弃任何任务
    seen_ids: dict[str, int] = {}
    for t in tasks:
        n = seen_ids.get(t.task_id, 0)
        seen_ids[t.task_id] = n + 1
        if n:
            t.task_id = f"{t.task_id}-{n + 1}"
    if not tasks:
        raise DatasetFetchError(
            "workbuddy-bench 无可用任务: " + ("; ".join(missing) or "缺文件"))
    if missing:
        _logger.warning("workbuddy 部分子集缺失（记录后继续）: %s", missing)
    return tasks


def _load_vibe_code_bench(cache: Path) -> list[BenchTask]:
    """VCB: eval_cases/case_XX_*/spec.md 为原始 prompt，tests.py 为 expected。

    本地 clone 优先；否则回退 GitHub zip 中 jsonl/json 搜索。
    """
    local = _local_clone("vibe-code-bench")
    if local is not None:
        cases_dir = local / "eval_cases"
        tasks: list[BenchTask] = []
        for case in sorted(cases_dir.iterdir()):
            spec = case / "spec.md"
            if not spec.is_file():
                continue
            prompt = spec.read_text(encoding="utf-8", errors="replace").strip()
            if not prompt:
                continue
            tests = case / "tests.py"
            tasks.append(BenchTask(
                dataset="vibe-code-bench",
                task_id=case.name,
                prompt=prompt,
                subset="eval",
                expected=tests.read_text(encoding="utf-8", errors="replace") if tests.is_file() else None,
                meta={"case_dir": str(case)},
            ))
        if tasks:
            return tasks
        raise DatasetFetchError(f"本地 vibe-code-bench 无 eval_cases: {local}")
    zip_url = "https://github.com/ArjunDivecha/vibe-code-bench/archive/refs/heads/main.zip"
    try:
        raw = _http_get(zip_url, timeout=180)
        zf = zipfile.ZipFile(io.BytesIO(raw))
        records: list[dict[str, Any]] = []
        for name in zf.namelist():
            low = name.lower()
            if low.endswith(".jsonl"):
                records.extend({**r, "_file": name} for r in _read_jsonl(zf.read(name)))
            elif low.endswith(".json"):
                try:
                    obj = json.loads(zf.read(name).decode("utf-8", errors="replace"))
                    if isinstance(obj, list):
                        records.extend({**r, "_file": name} for r in obj if isinstance(r, dict))
                except json.JSONDecodeError:
                    continue
        tasks: list[BenchTask] = []
        for i, rec in enumerate(records):
            prompt = _extract_prompt(rec, ["prompt", "description", "task"])
            if not prompt:
                continue
            subset = "validation" if "val" in rec.get("_file", "").lower() else \
                     "test" if "test" in rec.get("_file", "").lower() else ""
            tasks.append(BenchTask(
                dataset="vibe-code-bench",
                task_id=str(rec.get("id") or rec.get("task_id") or f"vcb-{i+1}"),
                prompt=prompt, subset=str(rec.get("split") or subset),
                expected=rec.get("expected") or rec.get("tests"), meta=rec,
            ))
        if tasks:
            return tasks
    except Exception as exc:
        _logger.warning("VCB GitHub zip 失败，尝试 HF: %s", exc)
    raise DatasetFetchError("vibe-code-bench 无可用数据源")


def _load_prototypebench(cache: Path) -> list[BenchTask]:
    """PrototypeBench: HF instances.jsonl（123 道，52 前端 + 71 后端）。"""
    records: list[dict[str, Any]] = []
    cache.mkdir(parents=True, exist_ok=True)
    inst = cache / "instances.jsonl"
    if inst.is_file():
        records = _read_jsonl(inst.read_text("utf-8", errors="replace"))
    if not records:
        url = _HF_RESOLVE.format(repo="banyaaiofficial/prototypebench-v1", path="instances.jsonl")
        try:
            raw = _http_get(url, timeout=300)
            inst.write_bytes(raw)
            records = _read_jsonl(raw)
        except Exception as exc:
            # 本地 clone 的 tasks/instances.jsonl 为兜底样本
            local = _local_clone("prototypebench")
            sample = local / "tasks" / "instances.jsonl" if local else None
            if sample and sample.is_file():
                records = _read_jsonl(sample.read_text("utf-8", errors="replace"))
            if not records:
                raise DatasetFetchError(f"prototypebench instances.jsonl 不可用: {exc}") from exc
    tasks: list[BenchTask] = []
    for i, rec in enumerate(records):
        prompt = _extract_prompt(rec, ["problem_statement", "description", "prompt", "requirement"])
        if not prompt:
            continue
        # meta 体积瘦身：巨型 patch / test_patch 不进入缓存 jsonl
        meta = {k: v for k, v in rec.items()
                if k not in {"patch", "test_patch", "test_patch_backend", "test_patch_frontend"}}
        tasks.append(BenchTask(
            dataset="prototypebench",
            task_id=str(rec.get("instance_id") or rec.get("id") or f"pb-{i+1}"),
            prompt=prompt,
            subset=str(rec.get("stack_domain") or ""),
            expected=rec.get("patch"), meta=meta,
        ))
    return tasks


def _load_gaia(cache: Path) -> list[BenchTask]:
    """GAIA: 公开验证集 166 道 → Question。"""
    records: list[dict[str, Any]] = []
    err: Exception | None = None
    for config, split in [("2023_all", "validation"), ("2023_level1", "validation"),
                          ("default", "validation")]:
        try:
            records = _load_hf_parquet("gaia-benchmark/GAIA", config, split, cache)
            break
        except Exception as exc:  # noqa: PERF203
            err = exc
    if not records:
        raise DatasetFetchError(f"GAIA 不可用: {err}")
    tasks: list[BenchTask] = []
    for i, rec in enumerate(records):
        prompt = _extract_prompt(rec, ["Question", "question", "prompt"])
        if not prompt:
            continue
        tasks.append(BenchTask(
            dataset="gaia",
            task_id=str(rec.get("task_id") or rec.get("id") or f"gaia-{i+1}"),
            prompt=prompt,
            subset=f"level{rec.get('Level') or rec.get('level') or '?'}",
            expected=rec.get("Final answer") or rec.get("final_answer") or rec.get("answer"),
            meta={k: v for k, v in rec.items() if k != "file_path"},
        ))
    return tasks


def _load_swe_bench(cache: Path) -> list[BenchTask]:
    """SWE-bench Lite: 300 道 → problem_statement。本地缓存/直接 resolve 优先。"""
    import pandas as pd  # noqa: PLC0415

    cache.mkdir(parents=True, exist_ok=True)
    pq = cache / "test.parquet"
    if not pq.is_file():
        # 优先本地 bench-datasets 下降到的副本
        local_pq = _local_clone("..")
        cand = Path(__file__).resolve().parents[2] / "data" / "bench-datasets" / "swe-bench-lite-test.parquet"
        if cand.is_file():
            import shutil as _sh
            _sh.copyfile(cand, pq)
    if not pq.is_file():
        url = (
            "https://huggingface.co/datasets/princeton-nlp/SWE-bench_Lite"
            "/resolve/main/data/test-00000-of-00001.parquet"
        )
        last: Exception | None = None
        for _ in range(3):
            try:
                pq.write_bytes(_http_get(url, timeout=600))
                break
            except Exception as exc:
                last = exc
        if not pq.is_file():
            raise DatasetFetchError(f"SWE-bench Lite parquet 下载失败: {last}")
    df = pd.read_parquet(pq)
    records = df.to_dict("records")
    tasks: list[BenchTask] = []
    for i, rec in enumerate(records):
        prompt = _extract_prompt(rec, ["problem_statement", "description", "prompt"])
        if not prompt:
            continue
        tasks.append(BenchTask(
            dataset="swe-bench-lite",
            task_id=str(rec.get("instance_id") or f"swe-{i+1}"),
            prompt=prompt, subset=str(rec.get("repo", "")),
            expected=rec.get("patch"), meta=rec,
        ))
    return tasks


# ---------------------------------------------------------------------------
# 注册表 + 缓存装载
# ---------------------------------------------------------------------------

_LOADERS: dict[str, Callable[[Path], list[BenchTask]]] = {
    "web-bench": _load_web_bench,
    "workbuddy-bench": _load_workbuddy,
    "vibe-code-bench": _load_vibe_code_bench,
    "prototypebench": _load_prototypebench,
    "gaia": _load_gaia,
    "swe-bench-lite": _load_swe_bench,
}


class DatasetManager:
    """数据集管理：拉取、缓存、统一迭代。"""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.errors: dict[str, str] = {}   # dataset → 下载/解析错误信息

    def tasks_path(self, dataset: str) -> Path:
        return self.root / dataset / "tasks.jsonl"

    def load(self, dataset: str, refresh: bool = False) -> Iterator[BenchTask]:
        """加载单个数据集；优先缓存，异常时记录并返回空迭代。"""
        cached = self.tasks_path(dataset)
        if cached.exists() and not refresh:
            for rec in _read_jsonl(cached.read_text("utf-8")):
                yield BenchTask.from_dict(rec)
            return
        loader = _LOADERS.get(dataset)
        if loader is None:
            self.errors[dataset] = f"未注册的数据集: {dataset}"
            return
        try:
            tasks = loader(self.root / dataset)
        except Exception as exc:
            self.errors[dataset] = f"下载/解析异常: {exc}"
            _logger.error("数据集 %s 载入失败: %s", dataset, exc)
            return
        # 写缓存
        (self.root / dataset).mkdir(parents=True, exist_ok=True)
        with cached.open("w", encoding="utf-8") as fh:
            for t in tasks:
                fh.write(json.dumps(t.to_dict(), ensure_ascii=False) + "\n")
        yield from tasks

    def load_all(self, datasets: list[str] | None = None,
                 refresh: bool = False) -> Iterator[BenchTask]:
        """遍历全部指定数据集（默认六大集全量）。"""
        for name in (datasets or list(_LOADERS)):
            yield from self.load(name, refresh=refresh)
