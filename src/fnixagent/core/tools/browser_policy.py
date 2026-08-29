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

# L1（接管用户浏览器）的偏好记忆（N1：首次引导后记住，不反复问）。
#   ""             未选择——每次启动仍会探测调试端口
#   "user_browser" 用户希望复用登录态：优先探测并引导开启调试端口
#   "managed_only" 用户选择独立托管浏览器：永远跳过探测（不打扰用户浏览器）
L1_CHOICE_UNSET = ""
L1_CHOICE_USER_BROWSER = "user_browser"
L1_CHOICE_MANAGED_ONLY = "managed_only"
L1_CHOICES = (L1_CHOICE_UNSET, L1_CHOICE_USER_BROWSER, L1_CHOICE_MANAGED_ONLY)

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
    # L1 偏好（首次引导后记住，见本模块 L1_CHOICE_* 常量）
    l1_choice: str = L1_CHOICE_UNSET

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            self.mode = MODE_ASK_NEW
        if self.l1_choice not in L1_CHOICES:
            self.l1_choice = L1_CHOICE_UNSET

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
            "l1_choice": self.l1_choice,
        }


# ── N1 引导：让用户一条命令把自己的浏览器开成可接管 ─────────────────────
#
# L1 复用登录态的前提是浏览器开着调试端口，而 99% 的用户不知道怎么开。
# 引导层把"一键命令"准备好交给前端弹层，而不是让用户自己查文档。两条纪律：
#   1. 一律用**独立 user-data-dir**——调试端口直接开在日常 profile 上，等于
#      把登录态暴露给本机任意进程，安全上不可接受（Chrome 136+ 也默认禁止
#      在默认 profile 上开调试端口，独立目录是唯一既安全又能用的做法）；
#   2. 命令按 浏览器 × 操作系统 给出，不猜用户装的是哪个。
def debug_port_guide(port: int = 9222) -> dict:
    """生成"开启浏览器调试端口"的一键命令指引（只读，不改任何状态）。"""
    profile_win = "$env:LOCALAPPDATA\\FnixAgent\\browser-profile"
    profile_mac = "$HOME/Library/Application Support/FnixAgent/browser-profile"
    profile_linux = "$HOME/.local/share/fnixagent/browser-profile"
    flag = f"--remote-debugging-port={int(port)}"
    return {
        "port": int(port),
        "why": "复用你浏览器里的登录态需要开启调试端口。下面的命令会用"
               "独立配置目录启动浏览器，不影响你的日常使用；开着它，AI 就能"
               "直接在你已登录的浏览器里干活。",
        "browsers": {
            "chrome": {
                "windows": (
                    f'Start-Process "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
                    f'-ArgumentList "{flag}","--user-data-dir={profile_win}"'
                ),
                "macos": (
                    f'open -na "Google Chrome" --args {flag} '
                    f'--user-data-dir="{profile_mac}"'
                ),
                "linux": f'google-chrome {flag} --user-data-dir="{profile_linux}" &',
            },
            "edge": {
                "windows": (
                    f'Start-Process "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" '
                    f'-ArgumentList "{flag}","--user-data-dir={profile_win}"'
                ),
                "macos": (
                    f'open -na "Microsoft Edge" --args {flag} '
                    f'--user-data-dir="{profile_mac}"'
                ),
                "linux": f'microsoft-edge {flag} --user-data-dir="{profile_linux}" &',
            },
        },
        "note": "端口被占用时换一个（如 9223）；命令里的配置目录是独立的，"
                "删掉它等于重置这个调试浏览器。",
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
                l1_choice=str(data.get("l1_choice", L1_CHOICE_UNSET)),
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
