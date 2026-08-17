"""L2 引擎健康快照：KTG/STP/MFP + fnix-local 降级 + BYOK 策略。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from typing import Any


def collect_engine_status(app_state: Any = None) -> dict[str, Any]:
    """汇总底层引擎可观测状态（供 /work/status 与报告验收）。"""
    from fnixagent.harness.local_bridge import get_local_bridge
    from fnixagent.services.llm_policy import api_only_mode, server_llm_configured

    graph = getattr(app_state, "graph_components", None) if app_state is not None else None
    topology: dict[str, Any] = {}
    if graph is not None:
        try:
            topology = graph.topology_graph.stats()
        except Exception as e:
            topology = {"error": str(e)}

    bridge = get_local_bridge()
    sidecar = bridge.health()
    sidecar_offline = not sidecar.available
    # sidecar 离线时 Work/Code 仍可用 Python workspace 工具（降级，非失败）
    degraded = sidecar_offline

    layers = {
        "ktg": graph is not None,
        "stp": graph is not None,
        "mfp": graph is not None,
        "memory": bool(getattr(app_state, "memory_manager", None)) if app_state else False,
        "security": bool(getattr(app_state, "security_engine", None)) if app_state else False,
        "reasoning": bool(getattr(app_state, "reasoning_selector", None)) if app_state else False,
    }

    return {
        "ok": True,
        "layer": "L2-engine",
        "api_only": api_only_mode(),
        "server_llm": server_llm_configured(),
        "degraded": degraded,
        "degradation": {
            "fnix_local_offline": sidecar_offline,
            "message": (sidecar.message if sidecar_offline else "fnix-local 就绪；PDG 索引可用"),
            "fallback": "python-workspace-tools" if sidecar_offline else None,
        },
        "layers": layers,
        "topology": topology,
        "mode": getattr(app_state, "mode", None) if app_state else None,
        "sidecar": {
            "available": sidecar.available,
            "url": sidecar.url,
            "version": sidecar.version,
            "message": sidecar.message,
        },
    }


def merge_work_status(
    app_state: Any,
    *,
    is_admin: bool = False,
) -> dict[str, Any]:
    """兼容旧 /work/status 字段 + 新引擎快照。"""
    snap = collect_engine_status(app_state)
    layers = snap["layers"]
    return {
        "ok": True,
        "ktg": layers["ktg"],
        "stp": layers["stp"],
        "mfp": layers["mfp"],
        "memory": layers["memory"],
        "security": layers["security"],
        "reasoning": layers["reasoning"],
        "topology": snap["topology"],
        "mode": snap["mode"],
        "server_llm": snap["server_llm"],
        "is_admin": is_admin,
        "api_only": snap["api_only"],
        "degraded": snap["degraded"],
        "degradation": snap["degradation"],
        "sidecar": snap["sidecar"],
        "engine": snap,
    }
