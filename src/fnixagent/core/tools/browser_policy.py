"""浏览器域名信任策略（对标 Trae「配置受信任的域」）。

## 为什么要单独一层策略

改造前只有一条"接管模式下首访新域名要确认"的闸：

  - 只在 cdp-attach 生效，托管沙箱（managed）**完全不拦**——AI 想去哪去哪，
    用户全程看不见
  - 已批准域名只存在会话内存里，重启即忘
  - 用户无法表达"这个域名永远别去"

调研对标时发现 Trae 把这件事做成了**用户可配置的受信任域列表**，安装扩展
之前就能配。这是产品级的安全能力，不是实现细节：AI 操作浏览器时，用户最
想知道的两件事是"它能去哪"和"它去过哪"，前者就是这个模块。

## 四种模式

| 模式 | 含义 | 适用 |
|---|---|---|
| `ask_new` | 新域询问，批准后记住（**默认**，保持改造前行为） | 大多数用户 |
| `allowlist` | 仅白名单放行，其余一律拒绝 | 只让 AI 碰内部系统 |
| `denylist` | 黑名单拒绝，其余新域询问 | 默认开放但要挡几个站 |
| `open` | 除黑名单外全部放行，不询问 | 完全信任的场景 |

白名单/黑名单都支持 `*.example.com` 匹配子域。

## 两条硬规则

1. **本机地址永不拦截**。`localhost` / `127.0.0.1` 是本地开发与跑基准用的，
   任何模式都直接放行——否则基准测试会全军覆没。
2. **黑名单在所有模式下都生效**，包括 `open`。拒绝列表表达的是"绝不去"，
   不该被某个模式放过。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

_logger = logging.getLogger(__name__)

ALLOW = "allow"
DENY = "deny"
ASK = "ask"

MODE_ASK_NEW = "ask_new"
MODE_ALLOWLIST = "allowlist"
MODE_DENYLIST = "denylist"
MODE_OPEN = "open"

MODES = (MODE_ASK_NEW, MODE_ALLOWLIST, MODE_DENYLIST, MODE_OPEN)

MODE_LABELS = {
    MODE_ASK_NEW: "新域名询问，批准后记住",
    MODE_ALLOWLIST: "仅允许列表内的域名",
    MODE_DENYLIST: "拒绝列表内的域名，其余新域名询问",
    MODE_OPEN: "除拒绝列表外全部放行",
}

# 本机地址：本地开发与基准测试都在这些地址上，任何模式都不得拦截
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"})

_POLICY_FILE = Path.home() / ".local" / "share" / "fnixagent" / "browser_policy.json"


def _strip_port(host: str) -> str:
    host = (host or "").strip().lower()
    if host.startswith("["):  # IPv6 字面量
        return host.split("]")[0] + "]"
    return host.split(":")[0]


def is_local_host(host: str) -> bool:
    return _strip_port(host) in _LOCAL_HOSTS


def _match(pattern: str, domain: str) -> bool:
    """域名与规则是否匹配。支持 `*.example.com` 前缀通配。"""
    p = (pattern or "").strip().lower()
    d = (domain or "").strip().lower()
    if not p or not d:
        return False
    if p.startswith("*."):
        tail = p[1:]  # ".example.com"
        return d == p[2:] or d.endswith(tail)
    return d == p or d.endswith("." + p)


@dataclass
class BrowserPolicy:
    """域名信任策略。纯数据 + 纯判定，便于单测。"""

    mode: str = MODE_ASK_NEW
    allowed: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)
    # 批准过的域名要不要持久化。默认记住——每次重启都重问一遍，用户只会
    # 无脑点"允许"，询问就失去了意义。
    persist_approvals: bool = True
    # 会话内已批准的域名（不落盘那部分）由调用方维护，这里只存持久化的
    approved: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            self.mode = MODE_ASK_NEW

    # -- 判定 ---------------------------------------------------------

    def decide(self, host: str, session_approved: set[str] | None = None) -> tuple[str, str]:
        """判定一个 host 该放行、拒绝还是询问。

        返回 (ALLOW | DENY | ASK, 理由)。理由会直接进审计事件，所以要能
        让人一眼看懂为什么被拦。
        """
        domain = _strip_port(host)
        if not domain:
            return DENY, "空域名"
        if is_local_host(domain):
            return ALLOW, "本机地址"

        for pattern in self.denied:
            if _match(pattern, domain):
                return DENY, f"域名命中拒绝列表（{pattern}）"

        if domain in (session_approved or set()):
            return ALLOW, "本次会话已批准"
        if domain in self.approved:
            return ALLOW, "此前已批准"

        if self.mode == MODE_ALLOWLIST:
            for pattern in self.allowed:
                if _match(pattern, domain):
                    return ALLOW, f"命中允许列表（{pattern}）"
            return DENY, "不在允许列表内"

        if self.mode == MODE_OPEN:
            return ALLOW, "开放模式"

        # denylist / ask_new：到这里都是"没见过的域名"
        if self.mode == MODE_DENYLIST:
            return ASK, "新域名，需确认"
        return ASK, "新域名，需确认"

    # -- 变更 ---------------------------------------------------------

    def approve(self, domain: str) -> None:
        """记住一次批准。域名去重，空值忽略。"""
        d = _strip_port(domain)
        if not d or d in self.approved:
            return
        self.approved.append(d)

    def revoke(self, domain: str) -> bool:
        d = _strip_port(domain)
        if d in self.approved:
            self.approved.remove(d)
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "allowed": list(self.allowed),
            "denied": list(self.denied),
            "persist_approvals": self.persist_approvals,
            "approved": list(self.approved),
        }


def load_policy() -> BrowserPolicy:
    """从磁盘加载策略；文件缺失或损坏时回落到默认（绝不因此打不开浏览器）。"""
    try:
        if _POLICY_FILE.exists():
            data = json.loads(_POLICY_FILE.read_text(encoding="utf-8"))
            return BrowserPolicy(
                mode=str(data.get("mode", MODE_ASK_NEW)),
                allowed=list(data.get("allowed") or []),
                denied=list(data.get("denied") or []),
                persist_approvals=bool(data.get("persist_approvals", True)),
                approved=list(data.get("approved") or []),
            )
    except Exception as e:  # noqa: BLE001
        _logger.warning("browser policy load failed, using default: %s", e)
    return BrowserPolicy()


def save_policy(policy: BrowserPolicy) -> None:
    try:
        _POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _POLICY_FILE.write_text(
            json.dumps(policy.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:  # noqa: BLE001
        _logger.warning("browser policy save failed: %s", e)
