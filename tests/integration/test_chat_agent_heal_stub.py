"""Code API：stub 拒绝后应 heal 而非立即失败。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

CALC_SRC = "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n"


class StubThenCalcLLM:
    calls = 0

    async def complete(self, payload: dict) -> str:
        StubThenCalcLLM.calls += 1
        if StubThenCalcLLM.calls == 1:
            return json.dumps(
                {
                    "steps": [
                        {
                            "description": "创建 calc 模块说明文字占位",
                            "action": "write",
                            "target": "calc.py",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        if StubThenCalcLLM.calls == 2:
            return json.dumps(
                {
                    "steps": [
                        {"description": CALC_SRC, "action": "write", "target": "calc.py"},
                    ]
                },
                ensure_ascii=False,
            )
        return json.dumps({"passed": True, "notes": "ok"}, ensure_ascii=False)


@pytest.mark.asyncio
async def test_chat_agent_heals_after_stub_write(monkeypatch):
    StubThenCalcLLM.calls = 0
    with tempfile.TemporaryDirectory() as tmp:
        # 用 monkeypatch 设置,测试结束自动还原,避免污染全局环境
        monkeypatch.setenv("FNIXAGENT_PROFILE", "standalone")
        monkeypatch.setenv("FNIX_CODE_HEAL_ROUNDS", "2")
        from fnixagent.main import app

        client = TestClient(app)
        llm = StubThenCalcLLM()

        with (
            patch(
                "fnixagent.api.routers.chat_agent.get_server",
            ) as mock_get,
            patch(
                "fnixagent.services.llm_policy.resolve_llm_for_request",
                return_value=(None, None),
            ),
        ):
            from fnixagent.core.code.agent import CodingAgent
            from fnixagent.core.code.context import ContextBuilder
            from fnixagent.core.code.tools import CodeTools

            class _StubIndexer:
                async def index_directory(self, *_a, **_k):
                    return None

                async def search_code(self, *_a, **_k):
                    return []

            tools = CodeTools(tmp)
            tools.preview_mode = True
            ctx = ContextBuilder(indexer=_StubIndexer(), project_root=tmp)  # type: ignore[arg-type]
            agent = CodingAgent(tools, ctx, llm)  # type: ignore[arg-type]

            class _FakeServer:
                _agent = agent

                def _ensure_initialized(self) -> None:
                    return None

            mock_get.return_value = _FakeServer()

            body = {
                "messages": [{"role": "user", "content": "创建 calc.py"}],
                "workspace": tmp,
                "preview": True,
            }
            resp = client.post("/api/v1/chat/agent", json=body)
            assert resp.status_code == 200
            lines = [json.loads(ln) for ln in resp.text.strip().splitlines() if ln.strip()]
            done = next((e for e in lines if e.get("type") == "done"), None)
            assert done is not None, resp.text[:500]
            assert done.get("status") == "completed", done
            file_events = [e for e in lines if e.get("type") == "file_change"]
            assert any(
                (e.get("path") == "calc.py" or e.get("path", "").endswith("calc.py"))
                for e in file_events
            ), [e.get("path") for e in file_events]
