#!/usr/bin/env python3
"""Offline openability gate — synthetic fixtures, no LLM."""

from __future__ import annotations
# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fnixagent.core.benchmark.work_openability import score_artifact, score_artifacts


def _office_zip(parts: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in parts.items():
            zf.writestr(name, data)
    return buf.getvalue()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="fnix-open-") as tmp:
        root = Path(tmp)
        (root / "ok.md").write_text("# hello\n\nnotes", encoding="utf-8")
        (root / "ok.html").write_text("<!doctype html><html><body>hi</body></html>", encoding="utf-8")
        (root / "ok.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
        (root / "bad.json").write_text("{not-json", encoding="utf-8")
        (root / "ok.pdf").write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        (root / "ok.docx").write_bytes(
            _office_zip(
                {
                    "[Content_Types].xml": b"<Types/>",
                    "word/document.xml": b"<w:document/>",
                }
            )
        )

        good = score_artifacts(
            [root / "ok.md", root / "ok.html", root / "ok.json", root / "ok.pdf", root / "ok.docx"],
            min_score=0.8,
        )
        bad = score_artifact(root / "bad.json")
        if not good["ok"]:
            print("FAIL good set", good)
            return 1
        if bad["ok"]:
            print("FAIL expected bad.json not openable", bad)
            return 1
        print(f"PASS openability offline mean={good['mean']} items={good['count']}")
        out = ROOT / "reports" / "work-openability-offline.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(good, indent=2), encoding="utf-8")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
