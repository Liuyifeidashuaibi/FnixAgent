"""Work artifact openability / structure scoring (Day 61–90)."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any


def _score_text_like(data: bytes, *, min_len: int = 8) -> tuple[float, str]:
    if len(data) < min_len:
        return 0.0, "too small"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            return 0.2, "undecodable"
    if not text.strip():
        return 0.0, "empty"
    return 1.0, "text ok"


def _score_html(data: bytes) -> tuple[float, str]:
    s, msg = _score_text_like(data)
    if s < 1:
        return s, msg
    low = data.decode("utf-8", errors="replace").lower()
    if "<html" in low or "<!doctype" in low or "<body" in low:
        return 1.0, "html structure"
    if "<div" in low or "<p" in low:
        return 0.85, "html fragments"
    return 0.5, "html weak"


def _score_json(data: bytes) -> tuple[float, str]:
    try:
        json.loads(data.decode("utf-8"))
        return 1.0, "json parse"
    except Exception as exc:
        return 0.0, f"json fail: {exc}"


def _score_zip_office(path: Path, required: set[str]) -> tuple[float, str]:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = set(zf.namelist())
    except Exception as exc:
        return 0.0, f"zip fail: {exc}"
    if not required.issubset(names) and not any(r in n for n in names for r in required):
        # soft: any required prefix present
        hit = sum(1 for r in required if any(n.startswith(r) or r in n for n in names))
        if hit == 0:
            return 0.2, "office zip missing parts"
        return 0.7, f"office zip partial ({hit}/{len(required)})"
    return 1.0, "office zip ok"


def score_artifact(path: Path) -> dict[str, Any]:
    """Return openability score 0–1 for a single file."""
    p = Path(path)
    if not p.is_file():
        return {"path": str(p), "score": 0.0, "ok": False, "reason": "missing"}

    ext = p.suffix.lower()
    data = p.read_bytes()[:2_000_000]

    if ext in {".md", ".txt", ".csv", ".css", ".js", ".ts"}:
        score, reason = _score_text_like(data)
    elif ext in {".html", ".htm"}:
        score, reason = _score_html(data)
    elif ext == ".json":
        score, reason = _score_json(data)
    elif ext == ".pdf":
        ok = data.startswith(b"%PDF")
        score, reason = (1.0, "pdf magic") if ok else (0.0, "not pdf")
    elif ext == ".docx":
        score, reason = _score_zip_office(p, {"[Content_Types].xml", "word/"})
    elif ext == ".xlsx":
        score, reason = _score_zip_office(p, {"[Content_Types].xml", "xl/"})
    elif ext == ".pptx":
        score, reason = _score_zip_office(p, {"[Content_Types].xml", "ppt/"})
    elif ext in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        score, reason = (1.0, "image") if len(data) > 32 else (0.0, "image tiny")
    else:
        score, reason = _score_text_like(data, min_len=1)
        score = min(score, 0.6)
        reason = f"unknown ext ({reason})"

    return {
        "path": str(p),
        "ext": ext,
        "score": round(float(score), 3),
        "ok": score >= 0.8,
        "reason": reason,
        "bytes": p.stat().st_size,
    }


def score_artifacts(paths: list[Path], *, min_score: float = 0.8) -> dict[str, Any]:
    items = [score_artifact(p) for p in paths]
    if not items:
        return {
            "count": 0,
            "mean": 0.0,
            "openable": 0,
            "ok": False,
            "min_score": min_score,
            "items": [],
        }
    mean = sum(i["score"] for i in items) / len(items)
    openable = sum(1 for i in items if i["ok"])
    return {
        "count": len(items),
        "mean": round(mean, 3),
        "openable": openable,
        "ok": mean >= min_score and openable == len(items),
        "min_score": min_score,
        "items": items,
    }
