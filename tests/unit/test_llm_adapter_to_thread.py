"""LLMAdapter.chat must not block the asyncio event loop (sync httpx offload)."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import time

import pytest

from fnixagent.core.llm.adapter import LLMAdapter
from fnixagent.core.llm.base import LLMRequest
from fnixagent.core.llm.providers.openai import MockLLMProvider
from fnixagent.core.types import LLMResponse, TokenUsage


class _SlowProvider(MockLLMProvider):
    def chat(self, request: LLMRequest) -> LLMResponse:  # type: ignore[override]
        time.sleep(0.35)
        return LLMResponse(
            content="ok",
            model=self._model_name,
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )


@pytest.mark.asyncio
async def test_adapter_chat_keeps_event_loop_responsive() -> None:
    adapter = LLMAdapter.__new__(LLMAdapter)
    adapter._provider = _SlowProvider()
    adapter._provider_name = "mock"
    adapter._model_name = "mock"
    adapter._api_key = "x"
    adapter._base_url = ""
    adapter._configured = True

    async def ping() -> str:
        await asyncio.sleep(0.05)
        return "pong"

    chat_task = asyncio.create_task(
        adapter.chat([{"role": "user", "content": "hi"}]),
    )
    # If chat blocked the loop, ping would stall until chat finishes (~0.35s).
    t0 = time.perf_counter()
    assert await ping() == "pong"
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.2, f"event loop blocked during LLMAdapter.chat ({elapsed:.3f}s)"

    result = await chat_task
    assert result["choices"][0]["message"]["content"] == "ok"
