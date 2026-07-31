"""Harness config / MCP 单元测试。"""

from __future__ import annotations

import pytest


@pytest.fixture
def harness_home(tmp_path, monkeypatch):
    monkeypatch.setenv("FNIX_HOME", str(tmp_path / "fnix"))
    return tmp_path / "fnix"


def test_mcp_json_roundtrip(harness_home):
    from fnixagent.harness.config import read_mcp_config, write_mcp_config

    payload = {
        "version": 1,
        "servers": [
            {
                "name": "memory",
                "command": "npx -y @modelcontextprotocol/server-memory",
                "enabled": True,
            },
        ],
    }
    write_mcp_config(payload)
    loaded = read_mcp_config()
    assert loaded["version"] == 1
    assert len(loaded["servers"]) == 1
    assert loaded["servers"][0]["name"] == "memory"


def test_config_toml_write(harness_home):
    from fnixagent.harness.config import read_config_toml, write_config_toml

    write_config_toml({"provider": "deepseek", "model": "deepseek-chat"})
    cfg = read_config_toml()
    assert cfg.get("provider") == "deepseek"
    assert cfg.get("model") == "deepseek-chat"
