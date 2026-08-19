"""
Sigma 风格规则引擎 (Sigma-style Rule Engine) - P2 安全模块。

参考 Sigma 规范 + Wazuh 解码器:
  - YAML 声明式规则,与引擎解耦
  - 规则字段:detection.selection.field_name: value, condition: selection
  - 支持热加载(watchdog 监控 config/security/rules/ 目录)
  - 每条规则带 MITRE ATT&CK 标签
  - 订阅审计日志流,实时匹配

detection 语法:
  - selection.field: value                 → event[field] == value
  - selection.field: [v1, v2]              → event[field] in [v1, v2]
  - selection.field|contains: "keyword"    → keyword in event[field]
  - selection.field|startswith: "prefix"   → event[field].startswith(prefix)
  - selection.field|gte: N                 → event[field] >= N
  - selection.field|lt: N                  → event[field] < N
  - condition: selection                   → 所有字段满足
  - condition: selection1 or selection2    → 任一满足
  - condition: selection1 and not selection2

设计原则:
  - 所有异常不外泄,捕获后返回空匹配
  - watchdog 为可选依赖,缺失时手动 reload
  - 不修改 office/base.py 与其他现有源文件
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# 尝试导入 watchdog(可选依赖,缺失时仅禁用热加载)
try:
    from watchdog.events import FileSystemEventHandler  # type: ignore[import-not-found]
    from watchdog.observers import Observer  # type: ignore[import-not-found]

    _WATCHDOG_AVAILABLE: bool = True
except ImportError:
    _WATCHDOG_AVAILABLE = False
    FileSystemEventHandler = object  # type: ignore[assignment,misc]
    Observer = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# 审计钩子(异常吞掉)
# ---------------------------------------------------------------------------


def _audit_rule_match(rule: SigmaRule, event: dict) -> None:
    """将规则命中写入审计日志(异常吞掉)。"""
    try:
        from fnixagent.core.audit import AuditLogger

        AuditLogger().log(
            action="rule.match",
            detail={
                "rule_id": rule.id,
                "rule_title": rule.title,
                "level": rule.level,
                "mitre": rule.mitre,
                "event_action": event.get("action", ""),
            },
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# SigmaRule
# ---------------------------------------------------------------------------

# 支持的字段修饰符
_FIELD_MODIFIERS: tuple[str, ...] = (
    "contains",
    "startswith",
    "endswith",
    "gte",
    "lte",
    "gt",
    "lt",
)


@dataclass
class SigmaRule:
    """Sigma 风格规则定义。

    Attributes:
        title:           规则标题
        id:              规则唯一 ID(UUID)
        status:          状态 experimental/test/stable
        description:     描述
        author:          作者
        date:            日期(YYYY-MM-DD)
        level:           等级 info/low/medium/high/critical
        detection:       detection 配置(含 selection 与 condition)
        mitre:           MITRE ATT&CK 战术/技术 ID 列表
        falsepositives:  误报场景列表
    """

    title: str
    id: str
    status: str = "experimental"
    description: str = ""
    author: str = "fnixagent"
    date: str = ""
    level: str = "medium"
    detection: dict = field(default_factory=dict)
    mitre: list[str] = field(default_factory=list)
    falsepositives: list[str] = field(default_factory=list)

    def matches(self, event: dict) -> bool:
        """检查事件是否命中本规则。

        Args:
            event: 审计事件字典(含 action/detail/user_id 等字段)

        Returns:
            是否命中
        """
        try:
            if not self.detection or not isinstance(event, dict):
                return False
            condition = self.detection.get("condition", "")
            if not condition:
                return False
            return self._eval_condition(condition, event)
        except Exception:
            return False

    # -- 内部:条件求值 ---------------------------------------------------

    def _eval_condition(self, condition: str, event: dict) -> bool:
        """求值 condition 表达式。

        支持语法:
          - selection
          - selection1 or selection2
          - selection1 and selection2
          - selection1 and not selection2
        """
        cond = condition.strip()
        # 优先级:or -> and -> not(简化处理,从低到高切分)
        # 1. 切分 or
        or_parts = self._split_top_level(cond, " or ")
        if len(or_parts) > 1:
            return any(self._eval_condition(p, event) for p in or_parts)
        # 2. 切分 and(注意 "and not" 特殊处理)
        and_parts = self._split_and(cond)
        if len(and_parts) > 1:
            return all(self._eval_condition(p, event) for p in and_parts)
        # 3. 处理 not
        if cond.startswith("not "):
            return not self._eval_selection(cond[4:].strip(), event)
        # 4. 单个 selection
        return self._eval_selection(cond, event)

    @staticmethod
    def _split_top_level(text: str, sep: str) -> list[str]:
        """按分隔符切分(不做括号嵌套,简单场景足够)。"""
        if sep not in text:
            return [text]
        return [p.strip() for p in text.split(sep) if p.strip()]

    @staticmethod
    def _split_and(text: str) -> list[str]:
        """按 and 切分,保留 not 前缀。

        例如 "a and not b" → ["a", "not b"]
        """
        if " and " not in text:
            return [text]
        parts: list[str] = []
        # 用 and 切分,后续若以 not 开头则合并
        raw = text.split(" and ")
        for p in raw:
            p = p.strip()
            if not p:
                continue
            parts.append(p)
        return parts

    def _eval_selection(self, name: str, event: dict) -> bool:
        """求值单个 selection(所有字段需同时满足)。"""
        selection = self.detection.get(name)
        if not isinstance(selection, dict):
            return False
        for raw_key, expected in selection.items():
            if not self._match_field(raw_key, expected, event):
                return False
        return True

    def _match_field(self, raw_key: str, expected: object, event: dict) -> bool:
        """匹配单个字段(支持修饰符)。

        字段格式:field 或 field|modifier
        支持嵌套:detail.hour_of_day → event["detail"]["hour_of_day"]
        """
        # 解析字段名与修饰符
        if "|" in raw_key:
            field_path, modifier = raw_key.split("|", 1)
            field_path = field_path.strip()
            modifier = modifier.strip()
        else:
            field_path = raw_key.strip()
            modifier = ""

        # 从事件中取值(支持点号嵌套)
        actual = self._get_nested(event, field_path)

        # 无修饰符:相等或包含匹配
        if not modifier:
            if actual is None:
                return False
            if isinstance(expected, list):
                return actual in expected
            return actual == expected

        # 字符串类修饰符
        if modifier == "contains":
            if actual is None:
                return False
            try:
                return str(expected) in str(actual)
            except Exception:
                return False
        if modifier == "startswith":
            if actual is None:
                return False
            try:
                return str(actual).startswith(str(expected))
            except Exception:
                return False
        if modifier == "endswith":
            if actual is None:
                return False
            try:
                return str(actual).endswith(str(expected))
            except Exception:
                return False

        # 数值比较类修饰符
        if modifier in ("gte", "lte", "gt", "lt"):
            try:
                a = float(actual)  # type: ignore[arg-type]
                e = float(expected)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return False
            if modifier == "gte":
                return a >= e
            if modifier == "lte":
                return a <= e
            if modifier == "gt":
                return a > e
            if modifier == "lt":
                return a < e

        # 未知修饰符:降级为相等匹配
        if actual is None:
            return False
        return actual == expected

    @staticmethod
    def _get_nested(event: dict, path: str) -> object:
        """按点号路径取嵌套值(不存在返回 None)。"""
        if not path:
            return None
        cur: object = event
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return None
        return cur


# ---------------------------------------------------------------------------
# RuleMatch
# ---------------------------------------------------------------------------


@dataclass
class RuleMatch:
    """规则命中结果。

    Attributes:
        rule:       命中的 SigmaRule
        event:      触发的事件
        matched_at: 命中时间(ISO 字符串)
        mitre:      MITRE ATT&CK 标签
    """

    rule: SigmaRule
    event: dict
    matched_at: str = ""
    mitre: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# RuleEngine
# ---------------------------------------------------------------------------


class _RuleFileHandler(FileSystemEventHandler):  # type: ignore[misc]
    """watchdog 文件变更处理器(触发 reload)。"""

    def __init__(self, engine: RuleEngine) -> None:
        self._engine = engine

    def on_modified(self, event) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        if not str(event.src_path).endswith((".yaml", ".yml")):
            return
        logger.info("[rules] 检测到规则文件变更,触发 reload: %s", event.src_path)
        self._engine.reload()

    def on_created(self, event) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        if not str(event.src_path).endswith((".yaml", ".yml")):
            return
        logger.info("[rules] 检测到新规则文件,触发 reload: %s", event.src_path)
        self._engine.reload()


class RuleEngine:
    """Sigma 风格规则引擎。

    用法:
        engine = RuleEngine(rules_dir="config/security/rules")
        engine.load_rules()
        matches = engine.match({"action": "data.delete", "detail": {"batch": True}})
        for m in matches:
            print(m.rule.title, m.mitre)
    """

    def __init__(self, rules_dir: str = "config/security/rules") -> None:
        self._rules_dir: str = rules_dir
        self._rules: list[SigmaRule] = []
        self._rules_by_id: dict[str, SigmaRule] = {}
        self._lock = threading.Lock()
        self._observer: object | None = None

    # -- 公开接口 ----------------------------------------------------------

    def load_rules(self) -> int:
        """加载规则目录下所有 *.yaml 规则,返回加载数量。"""
        try:
            import yaml
        except ImportError:
            logger.warning("[rules] PyYAML 不可用,无法加载规则")
            return 0

        rules: list[SigmaRule] = []
        try:
            if not os.path.isdir(self._rules_dir):
                logger.warning("[rules] 规则目录不存在: %s", self._rules_dir)
                with self._lock:
                    self._rules = []
                    self._rules_by_id = {}
                return 0

            for fname in sorted(os.listdir(self._rules_dir)):
                if not fname.endswith((".yaml", ".yml")):
                    continue
                fpath = os.path.join(self._rules_dir, fname)
                try:
                    with open(fpath, encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    if not isinstance(data, dict):
                        continue
                    rule = self._parse_rule(data)
                    if rule is not None:
                        rules.append(rule)
                except Exception as exc:
                    logger.warning("[rules] 解析规则文件失败 %s: %s", fpath, exc)
        except Exception as exc:
            logger.warning("[rules] 加载规则失败: %s", exc)

        with self._lock:
            self._rules = rules
            self._rules_by_id = {r.id: r for r in rules}
        logger.info("[rules] 已加载 %d 条规则", len(rules))
        return len(rules)

    def reload(self) -> int:
        """重新加载所有规则(热加载)。"""
        return self.load_rules()

    def match(self, event: dict) -> list[RuleMatch]:
        """匹配单个事件,返回所有命中的规则。

        Args:
            event: 审计事件字典

        Returns:
            命中的 RuleMatch 列表
        """
        try:
            if not isinstance(event, dict):
                return []
            with self._lock:
                rules_snapshot = list(self._rules)
            matches: list[RuleMatch] = []
            now = datetime.utcnow().isoformat()
            for rule in rules_snapshot:
                if rule.matches(event):
                    match = RuleMatch(
                        rule=rule,
                        event=event,
                        matched_at=now,
                        mitre=list(rule.mitre),
                    )
                    matches.append(match)
                    _audit_rule_match(rule, event)
            return matches
        except Exception as exc:
            logger.warning("[rules] 匹配异常: %s", exc)
            return []

    def match_batch(self, events: list[dict]) -> dict[int, list[RuleMatch]]:
        """批量匹配事件。

        Args:
            events: 事件列表

        Returns:
            dict[event_index, list[RuleMatch]]
        """
        result: dict[int, list[RuleMatch]] = {}
        try:
            for idx, event in enumerate(events):
                ms = self.match(event)
                if ms:
                    result[idx] = ms
        except Exception as exc:
            logger.warning("[rules] 批量匹配异常: %s", exc)
        return result

    def add_rule(self, rule: SigmaRule) -> bool:
        """添加单条规则(运行时,不持久化)。"""
        try:
            with self._lock:
                if rule.id in self._rules_by_id:
                    return False
                self._rules.append(rule)
                self._rules_by_id[rule.id] = rule
            return True
        except Exception:
            return False

    def remove_rule(self, rule_id: str) -> bool:
        """按 ID 移除规则。"""
        try:
            with self._lock:
                rule = self._rules_by_id.pop(rule_id, None)
                if rule is None:
                    return False
                self._rules = [r for r in self._rules if r.id != rule_id]
            return True
        except Exception:
            return False

    def list_rules(self) -> list[SigmaRule]:
        """列出所有已加载规则。"""
        with self._lock:
            return list(self._rules)

    def start_watcher(self) -> bool:
        """启动文件变更监控(watchdog)。

        Returns:
            是否成功启动(watchdog 不可用或目录不存在时返回 False)
        """
        if not _WATCHDOG_AVAILABLE or Observer is None:
            logger.warning("[rules] watchdog 不可用,无法启动热加载")
            return False
        if not os.path.isdir(self._rules_dir):
            logger.warning("[rules] 规则目录不存在,无法启动监控: %s", self._rules_dir)
            return False
        try:
            if self._observer is not None:
                return True  # 已启动
            observer = Observer()  # type: ignore[misc]
            handler = _RuleFileHandler(self)
            observer.schedule(handler, self._rules_dir, recursive=False)  # type: ignore[union-attr]
            observer.start()  # type: ignore[union-attr]
            self._observer = observer
            logger.info("[rules] 文件变更监控已启动: %s", self._rules_dir)
            return True
        except Exception as exc:
            logger.warning("[rules] 启动 watcher 失败: %s", exc)
            return False

    def stop_watcher(self) -> None:
        """停止文件变更监控。"""
        try:
            if self._observer is not None:
                self._observer.stop()  # type: ignore[union-attr]
                self._observer.join(timeout=2.0)  # type: ignore[union-attr]
                self._observer = None
        except Exception as exc:
            logger.warning("[rules] 停止 watcher 失败: %s", exc)

    # -- 内部:规则解析 ---------------------------------------------------

    @staticmethod
    def _parse_rule(data: dict) -> SigmaRule | None:
        """从 YAML 字典解析 SigmaRule。"""
        try:
            title = data.get("title", "")
            rule_id = data.get("id", "")
            if not title or not rule_id:
                return None
            detection = data.get("detection", {})
            if not isinstance(detection, dict):
                detection = {}
            mitre_raw = data.get("mitre", [])
            if not isinstance(mitre_raw, list):
                mitre_raw = [mitre_raw]
            fp_raw = data.get("falsepositives", [])
            if not isinstance(fp_raw, list):
                fp_raw = [fp_raw]
            return SigmaRule(
                title=str(title),
                id=str(rule_id),
                status=str(data.get("status", "experimental")),
                description=str(data.get("description", "")),
                author=str(data.get("author", "fnixagent")),
                date=str(data.get("date", "")),
                level=str(data.get("level", "medium")),
                detection=detection,
                mitre=[str(m) for m in mitre_raw],
                falsepositives=[str(f) for f in fp_raw],
            )
        except Exception as exc:
            logger.warning("[rules] 解析规则失败: %s", exc)
            return None


# ---------------------------------------------------------------------------
# 全局单例(懒加载)
# ---------------------------------------------------------------------------

_engine_instance: RuleEngine | None = None
_engine_lock = threading.Lock()


def get_rule_engine() -> RuleEngine:
    """获取全局 RuleEngine 单例。"""
    global _engine_instance
    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = RuleEngine()
    return _engine_instance


def reset_rule_engine() -> None:
    """重置单例(主要用于测试)。"""
    global _engine_instance
    with _engine_lock:
        if _engine_instance is not None:
            _engine_instance.stop_watcher()
        _engine_instance = None
