"""BYOK 解析链：请求 override → llm_policy → harness secrets 可读。"""

from __future__ import annotations

from pathlib import Path

import pytest

from fnixagent.services import llm_policy


def test_resolve_prefers_client_key_over_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FNIX_API_ONLY", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-server-should-not-use")
    llm, err = llm_policy.resolve_llm_for_request(
        {"api_key": "sk-client", "provider": "openai", "model": "gpt-4o"},
        is_admin=True,
    )
    assert err is None
    assert llm is not None
    assert llm["api_key"] == "sk-client"


def test_harness_secrets_feed_adapter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FNIX_HOME", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    from fnixagent.harness.config import write_config_toml
    from fnixagent.harness.secrets import get_llm_api_key, set_llm_api_key
    from fnixagent.harness.workspace import ensure_home_layout

    ensure_home_layout()
    write_config_toml({"provider": "openai", "model": "gpt-4o-mini", "base_url": ""})
    set_llm_api_key("sk-harness-home-key")
    assert get_llm_api_key() == "sk-harness-home-key"

    from fnixagent.core.llm.adapter import LLMAdapter

    adapter = LLMAdapter()
    adapter._auto_detect()
    assert adapter._api_key == "sk-harness-home-key"
    assert adapter._provider_name == "openai"
