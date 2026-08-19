"""
密钥泄露扫描 (Secret Leak Scanner) - P2 安全模块。

参考 Gitleaks + TruffleHog + detect-secrets:
  - 正则规则集(AWS Key / GCP / Stripe / GitHub PAT / 私钥 / 数据库连接串等)
  - 香农熵阈值(>4.5 可疑)
  - 扫描文本/文件/目录
  - 命中即审计 + 自动脱敏
  - 白名单机制(已知安全的字符串,前缀匹配)

特性:
  1. 内置 10 条高精度正则规则
  2. 通用高熵字符串检测(配合熵阈值,捕获未知密钥形态)
  3. 脱敏:matched_text[:4] + "..." + matched_text[-4:]
  4. 扫描目录:os.walk,跳过 .git/.venv/__pycache__
  5. 命中即审计:secret.leak_detected

设计原则:
  - 所有异常不外泄,捕获后返回空结果
  - 不修改 office/base.py 与其他现有源文件
  - 仅依赖标准库(re/math/os/collections)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
import math
import os
import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 审计钩子(异常吞掉)
# ---------------------------------------------------------------------------


def _audit_secret_leak(finding: SecretFinding) -> None:
    """将密钥泄露命中写入审计日志(异常吞掉)。"""
    try:
        from fnixagent.core.audit import AuditLogger

        AuditLogger().log(
            action="secret.leak_detected",
            detail={
                "rule_id": finding.rule_id,
                "rule_name": finding.rule_name,
                "severity": finding.severity,
                "entropy": round(finding.entropy, 4),
                "file_path": finding.file_path,
                "line_number": finding.line_number,
                "matched_text": finding.matched_text,  # 已脱敏
            },
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class SecretFinding:
    """单条密钥扫描命中。

    Attributes:
        rule_name:   命中的规则名
        rule_id:     规则 ID
        matched_text: 匹配到的文本(已脱敏)
        file_path:   文件路径(扫描目录时)
        line_number: 行号(扫描文件时)
        entropy:     香农熵
        severity:    严重程度 info/low/medium/high/critical
    """

    rule_name: str
    rule_id: str
    matched_text: str
    file_path: str | None = None
    line_number: int | None = None
    entropy: float = 0.0
    severity: str = "high"


@dataclass
class ScanResult:
    """扫描结果汇总。

    Attributes:
        total_findings:      命中总数
        findings:            命中详情列表
        scanned_files:       扫描文件数
        scanned_text_length: 扫描文本总长度
        duration_ms:         耗时(毫秒)
    """

    total_findings: int = 0
    findings: list[SecretFinding] = field(default_factory=list)
    scanned_files: int = 0
    scanned_text_length: int = 0
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# SecretScanner
# ---------------------------------------------------------------------------


class SecretScanner:
    """密钥泄露扫描器。

    用法:
        scanner = SecretScanner()
        findings = scanner.scan_text("AKIAIOSFODNN7EXAMPLE")
        result = scanner.scan_directory("./src")
        redacted = scanner.redact("token=AKIAIOSFODNN7EXAMPLE")
    """

    # 内置规则集
    BUILTIN_RULES: dict[str, str] = {
        "aws_access_key": r"AKIA[0-9A-Z]{16}",
        "aws_secret_key": r"aws_secret_access_key\s*=\s*[A-Za-z0-9/+=]{40}",
        "github_pat": r"gh[pousr]_[A-Za-z0-9]{36}",
        "google_api_key": r"AIza[0-9A-Za-z\-_]{35}",
        "stripe_key": r"sk_live_[0-9a-zA-Z]{24}",
        "private_key": r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
        "jwt_token": r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
        "database_url": r"(postgres|mysql|mongodb)://[^\s]+:[^\s]+@[^\s]+",
        "slack_token": r"xox[baprs]-[A-Za-z0-9-]{10,}",
        "generic_high_entropy": r"[A-Za-z0-9+/=]{32,}",
    }

    # 规则名映射(用于 SecretFinding.rule_name)
    _RULE_NAMES: dict[str, str] = {
        "aws_access_key": "AWS Access Key",
        "aws_secret_key": "AWS Secret Access Key",
        "github_pat": "GitHub Personal Access Token",
        "google_api_key": "Google API Key",
        "stripe_key": "Stripe Live Secret Key",
        "private_key": "Private Key",
        "jwt_token": "JWT Token",
        "database_url": "Database Connection URL",
        "slack_token": "Slack Token",
        "generic_high_entropy": "Generic High Entropy String",
    }

    # 默认严重程度
    _RULE_SEVERITY: dict[str, str] = {
        "aws_access_key": "critical",
        "aws_secret_key": "critical",
        "github_pat": "critical",
        "google_api_key": "high",
        "stripe_key": "critical",
        "private_key": "critical",
        "jwt_token": "high",
        "database_url": "high",
        "slack_token": "high",
        "generic_high_entropy": "medium",
    }

    # 香农熵阈值(>4.5 视为可疑)
    ENTROPY_THRESHOLD: float = 4.5

    # 扫描目录时跳过的目录名
    _SKIP_DIRS: tuple[str, ...] = (
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        ".pytest_cache",
        "dist",
        "build",
        ".idea",
        ".vscode",
    )

    # 默认扫描的文件扩展名
    _DEFAULT_EXTENSIONS: tuple[str, ...] = (
        ".py",
        ".js",
        ".ts",
        ".yaml",
        ".yml",
        ".json",
        ".env",
        ".txt",
        ".md",
        ".toml",
        ".cfg",
        ".ini",
        ".sh",
    )

    def __init__(
        self,
        custom_rules: dict[str, str] | None = None,
        whitelist: list[str] | None = None,
    ) -> None:
        # 合并内置规则与自定义规则
        self._rules: dict[str, str] = dict(self.BUILTIN_RULES)
        if custom_rules:
            self._rules.update(custom_rules)
        # 自定义规则的严重程度(可通过 add_rule 设置)
        self._severity: dict[str, str] = dict(self._RULE_SEVERITY)
        # 白名单(前缀匹配)
        self._whitelist: list[str] = list(whitelist) if whitelist else []
        # 预编译正则(提升性能)
        self._compiled: dict[str, re.Pattern[str]] = {}
        self._compile_rules()
        self._lock = threading.Lock()

    # -- 公开接口 ----------------------------------------------------------

    def scan_text(self, text: str) -> list[SecretFinding]:
        """扫描文本,返回命中列表。

        Args:
            text: 待扫描文本

        Returns:
            SecretFinding 列表(已脱敏 + 已审计)
        """
        if not text or not isinstance(text, str):
            return []
        findings: list[SecretFinding] = []
        try:
            for rule_id, pattern in self._rules.items():
                hits = self._match_rule(text, rule_id, pattern)
                findings.extend(hits)
            # 去重(同一文本同一规则可能多次命中,保留全部但去重相同 matched_text)
            findings = self._dedupe(findings)
            # 命中即审计
            for f in findings:
                _audit_secret_leak(f)
        except Exception as exc:
            logger.warning("[secret_scan] 扫描文本异常: %s", exc)
        return findings

    def scan_file(self, file_path: str) -> list[SecretFinding]:
        """扫描单个文件,返回命中列表。"""
        try:
            if not os.path.isfile(file_path):
                return []
            # 跳过二进制文件(简单判断:扩展名)
            ext = os.path.splitext(file_path)[1].lower()
            if ext in (
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".pdf",
                ".zip",
                ".tar",
                ".gz",
                ".exe",
                ".dll",
                ".so",
                ".pyc",
            ):
                return []
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
            findings = self.scan_text(content)
            # 填充文件路径与行号
            for match_idx, finding in enumerate(findings):
                finding.file_path = file_path
                finding.line_number = self._find_line_number(
                    content, finding.matched_text, match_idx
                )
            return findings
        except Exception as exc:
            logger.warning("[secret_scan] 扫描文件异常 %s: %s", file_path, exc)
            return []

    def scan_directory(
        self,
        dir_path: str,
        extensions: list[str] | None = None,
    ) -> ScanResult:
        """扫描目录,返回汇总结果。

        Args:
            dir_path:    目录路径
            extensions:  扫描的扩展名列表(默认内置列表)

        Returns:
            ScanResult 汇总
        """
        start = datetime.utcnow()
        result = ScanResult()
        try:
            if not os.path.isdir(dir_path):
                return result
            allowed_ext = tuple(extensions if extensions else self._DEFAULT_EXTENSIONS)
            for root, dirs, files in os.walk(dir_path):
                # 跳过黑名单目录(原地修改 dirs 阻止递归)
                dirs[:] = [d for d in dirs if d not in self._SKIP_DIRS]
                for fname in files:
                    ext = os.path.splitext(fname)[1].lower()
                    if allowed_ext and ext not in allowed_ext:
                        continue
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        result.scanned_text_length += len(content)
                        result.scanned_files += 1
                        for rule_id, pattern in self._rules.items():
                            hits = self._match_rule(content, rule_id, pattern)
                            for finding in hits:
                                finding.file_path = fpath
                                result.findings.append(finding)
                    except Exception:
                        continue
            # 去重并审计
            result.findings = self._dedupe(result.findings)
            for f in result.findings:
                _audit_secret_leak(f)
            result.total_findings = len(result.findings)
        except Exception as exc:
            logger.warning("[secret_scan] 扫描目录异常 %s: %s", dir_path, exc)
        # 计算耗时
        elapsed = (datetime.utcnow() - start).total_seconds() * 1000.0
        result.duration_ms = round(elapsed, 2)
        return result

    def add_rule(self, rule_id: str, pattern: str, severity: str = "high") -> None:
        """添加自定义规则。"""
        try:
            with self._lock:
                self._rules[rule_id] = pattern
                self._severity[rule_id] = severity
                self._compiled[rule_id] = re.compile(pattern)
        except Exception as exc:
            logger.warning("[secret_scan] 添加规则失败 %s: %s", rule_id, exc)

    def add_to_whitelist(self, value: str) -> None:
        """添加白名单值(前缀匹配)。"""
        with self._lock:
            if value and value not in self._whitelist:
                self._whitelist.append(value)

    def redact(self, text: str) -> str:
        """脱敏文本:将所有命中的密钥替换为 [REDACTED]。"""
        if not text or not isinstance(text, str):
            return text
        try:
            redacted = text
            for rule_id, pattern in self._rules.items():
                regex = self._compiled.get(rule_id)
                if regex is None:
                    continue
                redacted = regex.sub("[REDACTED]", redacted)
            return redacted
        except Exception:
            return text

    # -- 内部:规则匹配 ---------------------------------------------------

    def _match_rule(self, text: str, rule_id: str, pattern: str) -> list[SecretFinding]:
        """用单条规则匹配文本,返回命中列表。"""
        findings: list[SecretFinding] = []
        regex = self._compiled.get(rule_id)
        if regex is None:
            return findings
        try:
            for match in regex.finditer(text):
                matched = match.group(0)
                # 白名单检查(前缀匹配)
                if self._is_whitelisted(matched):
                    continue
                # 通用高熵规则需配合熵阈值
                entropy = self._shannon_entropy(matched)
                if rule_id == "generic_high_entropy":
                    if entropy < self.ENTROPY_THRESHOLD:
                        continue
                    # 避免与已命中规则重复(高熵串可能是已知密钥的一部分)
                    if self._overlaps_known(matched, text):
                        continue
                # 脱敏
                redacted = self._redact_value(matched)
                findings.append(
                    SecretFinding(
                        rule_name=self._RULE_NAMES.get(rule_id, rule_id),
                        rule_id=rule_id,
                        matched_text=redacted,
                        entropy=round(entropy, 4),
                        severity=self._severity.get(rule_id, "high"),
                    )
                )
        except Exception as exc:
            logger.warning("[secret_scan] 规则匹配异常 %s: %s", rule_id, exc)
        return findings

    def _is_whitelisted(self, value: str) -> bool:
        """检查是否在白名单中(前缀匹配)。"""
        for wl in self._whitelist:
            if value.startswith(wl) or wl.startswith(value):
                return True
        return False

    def _overlaps_known(self, candidate: str, full_text: str) -> bool:
        """检查高熵候选串是否为已知密钥的子串(避免重复报告)。"""
        # 简化策略:若候选串包含已知规则的特征前缀,视为重叠
        known_prefixes = (
            "AKIA",
            "ghp_",
            "gho_",
            "ghs_",
            "ghr_",
            "ghu_",
            "AIza",
            "sk_live_",
            "xox",
            "eyJ",
        )
        for prefix in known_prefixes:
            if prefix in candidate:
                return True
        return False

    # -- 内部:香农熵 -----------------------------------------------------

    @staticmethod
    def _shannon_entropy(data: str) -> float:
        """计算香农熵:-sum(p * log2(p))。"""
        if not data:
            return 0.0
        try:
            counts = Counter(data)
            length = len(data)
            entropy = 0.0
            for count in counts.values():
                p = count / length
                if p > 0:
                    entropy -= p * math.log2(p)
            return entropy
        except Exception:
            return 0.0

    # -- 内部:脱敏 -------------------------------------------------------

    @staticmethod
    def _redact_value(value: str) -> str:
        """脱敏:保留首尾各 4 字符,中间用 ... 替换。"""
        if not value:
            return ""
        if len(value) <= 8:
            return value[:2] + "..." + value[-2:] if len(value) > 4 else "***"
        return value[:4] + "..." + value[-4:]

    # -- 内部:辅助 -------------------------------------------------------

    @staticmethod
    def _find_line_number(content: str, matched_text: str, fallback_idx: int = 0) -> int | None:
        """查找脱敏后文本对应的行号(近似)。"""
        try:
            # 脱敏文本无法直接定位,用首 4 字符匹配
            prefix = matched_text.split("...")[0][:4] if "..." in matched_text else matched_text[:4]
            if not prefix:
                return 1
            lines = content.splitlines()
            for i, line in enumerate(lines, start=1):
                if prefix in line:
                    return i
            return 1
        except Exception:
            return None

    @staticmethod
    def _dedupe(findings: list[SecretFinding]) -> list[SecretFinding]:
        """去重:同 rule_id + 同 matched_text + 同 file_path 仅保留一条。"""
        seen: set[tuple[str, str, str | None]] = set()
        result: list[SecretFinding] = []
        for f in findings:
            key = (f.rule_id, f.matched_text, f.file_path)
            if key in seen:
                continue
            seen.add(key)
            result.append(f)
        return result

    def _compile_rules(self) -> None:
        """预编译所有正则规则。"""
        for rule_id, pattern in self._rules.items():
            try:
                self._compiled[rule_id] = re.compile(pattern)
            except re.error as exc:
                logger.warning("[secret_scan] 规则编译失败 %s: %s", rule_id, exc)


# ---------------------------------------------------------------------------
# 全局单例(懒加载)
# ---------------------------------------------------------------------------

_scanner_instance: SecretScanner | None = None
_scanner_lock = threading.Lock()


def get_secret_scanner() -> SecretScanner:
    """获取全局 SecretScanner 单例。"""
    global _scanner_instance
    if _scanner_instance is None:
        with _scanner_lock:
            if _scanner_instance is None:
                _scanner_instance = SecretScanner()
    return _scanner_instance


def reset_secret_scanner() -> None:
    """重置单例(主要用于测试)。"""
    global _scanner_instance
    with _scanner_lock:
        _scanner_instance = None
