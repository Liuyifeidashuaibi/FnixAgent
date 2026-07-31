"""Standalone profile 单元测试。"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_profile_env(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("FNIXAGENT_PROFILE", "standalone")


def test_get_profile_default_standalone():
    from fnixagent.core.profile import DeployProfile, get_profile

    assert get_profile() == DeployProfile.STANDALONE


def test_apply_profile_defaults_no_database_url(monkeypatch):
    from fnixagent.core.profile import apply_profile_defaults, profile_info

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("FNIXAGENT_PROFILE", "standalone")
    apply_profile_defaults()
    info = profile_info()
    assert info["profile"] == "standalone"
    assert info["storage"] == "local-json"


def test_cloud_profile_sets_production_env(monkeypatch):
    from fnixagent.core.profile import DeployProfile, apply_profile_defaults, get_profile

    monkeypatch.setenv("FNIXAGENT_PROFILE", "cloud")
    monkeypatch.delenv("SERVICE_ENV", raising=False)
    apply_profile_defaults()
    assert get_profile() == DeployProfile.CLOUD
    assert os.getenv("SERVICE_ENV") == "production"
