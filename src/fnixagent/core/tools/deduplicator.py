"""请求指纹与去重系统(借鉴 zhua scheduler/kernel.py 的 FNV-64a + Simhash)。

两层去重:
  1. 精确去重: FNV-64a 哈希(方法+规范化URL/工具名+参数),完全相同视为重复
  2. 近似去重: Simhash 汉明距离 ≤ 3 视为重复(可选,默认关闭)

URL 规范化(借鉴 zhua):
  - scheme/host 小写
  - 去掉默认端口(http:80, https:443)
  - 去掉 fragment(#...)
  - query 参数排序

设计要点:
  - FNV-64a 纯 Python 实现,零依赖(不依赖 hashlib 也不依赖 mmh3)
  - 线程安全: 所有共享状态访问加 threading.Lock
  - 有界内存: max_fingerprints 控制,超限 FIFO 淘汰
  - dont_filter 标志: 重试场景可跳过去重
  - logging 记录关键事件,不引入 loguru
"""
from __future__ import annotations

import json
import logging
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import (
    parse_qsl,
    urlencode,
    urlsplit,
    urlunsplit,
)

logger = logging.getLogger(__name__)

# P1-06: Rust PyO3 扩展探测(可选加速,不可用时回退到下方纯 Python 实现)
# 不直接 import Rust 模块,通过 probe 统一探测,避免本模块对扩展的硬依赖。
try:
    from fnixagent.core.rust_ext.probe import try_rust_fnv64a as _try_rust_fnv64a
except ImportError:  # pragma: no cover - 探测模块自身不应失败,兜底防御
    _try_rust_fnv64a = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# FNV-64a 哈希(纯 Python,零依赖)
# ---------------------------------------------------------------------------

_FNV64_OFFSET_BASIS = 0xCBF29CE484222325
_FNV64_PRIME = 0x100000001B3
_FNV64_MASK = (1 << 64) - 1


def _fnv64a_pure_python(data: str) -> int:
    """FNV-64a 哈希(纯 Python 实现,作为 Rust 扩展的 fallback)。

    算法:
      hash = offset_basis
      for each byte:
          hash ^= byte
          hash *= prime
          hash &= mask   # 保留 64 位

    Args:
        data: 输入字符串(UTF-8 编码后逐字节处理)。

    Returns:
        64 位无符号整数哈希值(0 ~ 2^64-1)。
    """
    h = _FNV64_OFFSET_BASIS
    for b in data.encode("utf-8"):
        h ^= b
        h = (h * _FNV64_PRIME) & _FNV64_MASK
    return h


def fnv64a(data: str) -> int:
    """FNV-64a 哈希。

    P1-06: 优先使用 Rust PyO3 扩展(``fnixagent_rust.fnv64a``),
    扩展不可用时回退到 :func:`_fnv64a_pure_python`。
    行为与原纯 Python 实现完全等价,调用方无感知。

    Args:
        data: 输入字符串(UTF-8 编码后逐字节处理)。

    Returns:
        64 位无符号整数哈希值(0 ~ 2^64-1)。
    """
    # P1-06: Rust 扩展探测 — 可选快速路径
    if _try_rust_fnv64a is not None:
        return _try_rust_fnv64a(data, python_fallback=_fnv64a_pure_python)
    return _fnv64a_pure_python(data)


# ---------------------------------------------------------------------------
# URL 规范化(借鉴 zhua)
# ---------------------------------------------------------------------------

_DEFAULT_PORTS = {
    "http": 80,
    "https": 443,
    "ftp": 21,
    "ws": 80,
    "wss": 443,
}


def normalize_url(url: str) -> str:
    """URL 规范化。

    处理步骤:
      1. scheme / host 小写
      2. 去掉默认端口(http:80, https:443 等)
      3. 去掉 fragment(#...)
      4. query 参数按 key 排序(同 key 多值保持原顺序)
      5. path 为空时补 "/"

    非法 URL 原样返回(不抛异常,避免阻断主流程)。

    Args:
        url: 待规范化的 URL 字符串。

    Returns:
        规范化后的 URL 字符串。若 url 为空或非法,原样返回。
    """
    if not url or not isinstance(url, str):
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return url

    scheme = parts.scheme.lower()
    host = parts.hostname.lower() if parts.hostname else ""
    port = parts.port

    # 去掉默认端口
    default_port = _DEFAULT_PORTS.get(scheme)
    if port is not None and default_port == port:
        port = None

    # 重建 netloc(含 userinfo 极少见,简化处理)
    if port is not None:
        netloc = f"{host}:{port}" if host else f":{port}"
    else:
        netloc = host

    # query 排序
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    query_pairs.sort(key=lambda kv: kv[0])
    query = urlencode(query_pairs)

    # path 空时补 "/"
    path = parts.path or "/"
    if not path.startswith("/") and host:
        path = "/" + path

    # fragment 丢弃
    return urlunsplit((scheme, netloc, path, query, ""))


# ---------------------------------------------------------------------------
# Simhash 近似去重(64 位)
# ---------------------------------------------------------------------------

# 简单分词: 连续的字母/数字/下划线 或 中文字符为一个 token
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


@dataclass
class Simhash:
    """Simhash 近似去重(64 位)。

    算法:
      1. 将文本分词
      2. 每个词计算 FNV-64a 哈希(作为该词的 64 位特征)
      3. 对 64 位的每一位: 该位为 1 则 +1, 为 0 则 -1
      4. 最终每位 > 0 设 1, 否则设 0

    性质: 相似文本的 Simhash 汉明距离较小。
    """

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """简单分词: 字母数字下划线连续段 + 单字中文。

        Args:
            text: 输入文本。

        Returns:
            token 列表(可能为空)。
        """
        if not text:
            return []
        return _TOKEN_RE.findall(text)

    @staticmethod
    def compute(text: str) -> int:
        """计算文本的 Simhash 值。

        Args:
            text: 输入文本。

        Returns:
            64 位无符号整数 Simhash 值。空文本返回 0。
        """
        tokens = Simhash._tokenize(text)
        if not tokens:
            return 0
        # 64 位累加器
        v = [0] * 64
        for token in tokens:
            h = fnv64a(token)
            for i in range(64):
                bit = (h >> i) & 1
                v[i] += 1 if bit else -1
        # 转换为 64 位整数
        result = 0
        for i in range(64):
            if v[i] > 0:
                result |= (1 << i)
        return result

    @staticmethod
    def hamming_distance(a: int, b: int) -> int:
        """计算两个 Simhash 的汉明距离(不同位数)。

        Args:
            a: 第一个 Simhash 值。
            b: 第二个 Simhash 值。

        Returns:
            汉明距离(0 ~ 64)。
        """
        x = (a ^ b) & _FNV64_MASK
        # Brian Kernighan 算法
        dist = 0
        while x:
            x &= x - 1
            dist += 1
        return dist


# ---------------------------------------------------------------------------
# 请求指纹
# ---------------------------------------------------------------------------

@dataclass
class RequestFingerprint:
    """请求指纹。

    封装方法、目标(URL 或工具名)与参数,提供:
      - fingerprint(): 精确指纹(FNV-64a),用于精确去重
      - content_hash(): Simhash,用于近似去重

    Attributes:
        method: HTTP 方法("GET"/"POST") 或 "TOOL"。
        target: URL 或工具名。
        arguments: 参数字典(可为空)。
    """
    method: str
    target: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def _normalized_target(self) -> str:
        """规范化 target:若以 http/https 开头则按 URL 规范化,否则原样小写。"""
        if self.target.startswith(("http://", "https://")):
            return normalize_url(self.target)
        return self.target.strip().lower()

    def _canonical_payload(self) -> str:
        """生成确定性的参数字符串(排序后的 JSON)。

        嵌套 dict / list 也会被 sort_keys 递归排序,
        保证语义相同的参数产生相同的字符串。
        """
        if not self.arguments:
            return "{}"
        try:
            return json.dumps(
                self.arguments,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            # 兜底:str(arguments) 不一定稳定,但比抛异常好
            return repr(self.arguments)

    def _fingerprint_string(self) -> str:
        """组装用于精确哈希的字符串。"""
        return (
            f"{self.method.upper()}|{self._normalized_target()}|"
            f"{self._canonical_payload()}"
        )

    def fingerprint(self) -> int:
        """计算 FNV-64a 精确指纹。

        Returns:
            64 位无符号整数哈希值。
        """
        return fnv64a(self._fingerprint_string())

    def content_text(self) -> str:
        """组装用于近似哈希的文本(方法 + target + 参数值拼接)。"""
        parts = [self.method.upper(), self._normalized_target()]
        try:
            # 拼接所有叶子值(排序保证稳定)
            leaf_values: list[str] = []

            def _walk(obj: Any) -> None:
                if isinstance(obj, dict):
                    for k in sorted(obj.keys()):
                        _walk(obj[k])
                elif isinstance(obj, (list, tuple)):
                    for item in obj:
                        _walk(item)
                else:
                    leaf_values.append(str(obj))

            _walk(self.arguments)
            parts.extend(leaf_values)
        except Exception:
            parts.append(self._canonical_payload())
        return " ".join(parts)

    def content_hash(self) -> int:
        """计算 Simhash(用于近似去重)。

        Returns:
            64 位无符号整数 Simhash 值。
        """
        return Simhash.compute(self.content_text())


# ---------------------------------------------------------------------------
# 请求去重器
# ---------------------------------------------------------------------------

class RequestDeduplicator:
    """请求去重器。

    两层去重:
      1. 精确去重(fingerprint set): 完全相同的请求直接跳过
      2. 近似去重(simhash set, 可选): Simhash 汉明距离 ≤ threshold 视为重复

    线程安全: 所有共享集合的读写均加锁。
    有界内存: 超过 max_fingerprints 时按 FIFO 淘汰最早记录。

    用法:
        deduper = RequestDeduplicator(enable_simhash=True)
        if deduper.is_duplicate(method="TOOL", target="search_paper", arguments={"q": "AI"}):
            return cached_result
        result = execute(...)
        deduper.record(method="TOOL", target="search_paper", arguments={"q": "AI"})
    """

    def __init__(
        self,
        enable_simhash: bool = False,
        simhash_threshold: int = 3,
        max_fingerprints: int = 10000,
    ) -> None:
        """初始化去重器。

        Args:
            enable_simhash: 是否启用近似去重(默认关闭)。
            simhash_threshold: Simhash 汉明距离阈值, ≤ 视为重复。
            max_fingerprints: 指纹集合上限, 超限 FIFO 淘汰。

        Raises:
            TypeError: 参数类型错误。
            ValueError: 参数非法(threshold < 0 或 max_fingerprints <= 0)。
        """
        if not isinstance(enable_simhash, bool):
            raise TypeError(
                f"enable_simhash must be bool, got {type(enable_simhash).__name__}"
            )
        if isinstance(simhash_threshold, bool) or not isinstance(simhash_threshold, int):
            raise TypeError(
                f"simhash_threshold must be int, got {type(simhash_threshold).__name__}"
            )
        if isinstance(max_fingerprints, bool) or not isinstance(max_fingerprints, int):
            raise TypeError(
                f"max_fingerprints must be int, got {type(max_fingerprints).__name__}"
            )
        if simhash_threshold < 0:
            raise ValueError(
                f"simhash_threshold must be >= 0, got {simhash_threshold}"
            )
        if max_fingerprints <= 0:
            raise ValueError(
                f"max_fingerprints must be positive, got {max_fingerprints}"
            )

        self._enable_simhash = enable_simhash
        self._simhash_threshold = simhash_threshold
        self._max_fingerprints = max_fingerprints

        # FIFO 容器: 同时保存指纹与 simhash,便于同步淘汰
        # OrderedDict: key=fingerprint, value=content_hash(0 表示未启用近似)
        self._fingerprints: OrderedDict[int, int] = OrderedDict()
        self._lock = threading.Lock()

        # 统计
        self._total_checked = 0
        self._total_duplicates = 0
        self._total_near_duplicates = 0
        self._total_evicted = 0

    # -- 内部辅助 ----------------------------------------------------------

    def _evict_if_needed(self) -> None:
        """FIFO 淘汰最旧记录(调用者需持锁)。"""
        while len(self._fingerprints) > self._max_fingerprints:
            self._fingerprints.popitem(last=False)
            self._total_evicted += 1

    def _is_duplicate_locked(
        self, fp: int, content_hash: int
    ) -> tuple[bool, str]:
        """在持锁状态下检查重复(不写入)。

        Returns:
            (是否重复, 命中类型) 命中类型: "exact" / "near" / "" (无重复)
        """
        # 精确命中
        if fp in self._fingerprints:
            return True, "exact"
        # 近似命中
        if self._enable_simhash and content_hash != 0:
            for existing_hash in self._fingerprints.values():
                if existing_hash == 0:
                    continue
                if Simhash.hamming_distance(content_hash, existing_hash) <= self._simhash_threshold:
                    return True, "near"
        return False, ""

    # -- 公共 API ----------------------------------------------------------

    def is_duplicate(
        self,
        method: str,
        target: str,
        arguments: dict[str, Any] | None = None,
        dont_filter: bool = False,
    ) -> bool:
        """检查是否重复(不记录)。

        Args:
            method: 方法("GET"/"POST"/"TOOL"等)。
            target: URL 或工具名。
            arguments: 参数。
            dont_filter: True 表示跳过去重检查(重试场景)。

        Returns:
            True 表示重复(应跳过), False 表示新请求。
        """
        if dont_filter:
            return False
        rf = RequestFingerprint(
            method=method,
            target=target,
            arguments=arguments or {},
        )
        fp = rf.fingerprint()
        ch = rf.content_hash() if self._enable_simhash else 0

        with self._lock:
            self._total_checked += 1
            dup, kind = self._is_duplicate_locked(fp, ch)
            if dup:
                self._total_duplicates += 1
                if kind == "near":
                    self._total_near_duplicates += 1
            return dup

    def record(
        self,
        method: str,
        target: str,
        arguments: dict[str, Any] | None = None,
    ) -> None:
        """记录请求指纹(执行后调用)。

        重复调用同一请求会刷新其在 FIFO 中的位置(先删后插,置于尾部)。

        Args:
            method: 方法。
            target: URL 或工具名。
            arguments: 参数。
        """
        rf = RequestFingerprint(
            method=method,
            target=target,
            arguments=arguments or {},
        )
        fp = rf.fingerprint()
        ch = rf.content_hash() if self._enable_simhash else 0

        with self._lock:
            if fp in self._fingerprints:
                # 已存在: 刷新到尾部(FIFO 最新)
                self._fingerprints.move_to_end(fp)
                self._fingerprints[fp] = ch
                return
            self._fingerprints[fp] = ch
            self._evict_if_needed()

    def check_and_record(
        self,
        method: str,
        target: str,
        arguments: dict[str, Any] | None = None,
        dont_filter: bool = False,
    ) -> bool:
        """检查并记录(原子操作)。

        在同一锁内完成"检查 + 记录",避免并发场景下的 TOCTOU 竞态。
        重复请求不会被记录(只统计计数)。

        Args:
            method: 方法。
            target: URL 或工具名。
            arguments: 参数。
            dont_filter: True 表示跳过去重检查并直接记录。

        Returns:
            True 表示是新请求(已记录), False 表示重复(未记录)。
        """
        if dont_filter:
            # 重试场景: 直接记录,不视为重复
            self.record(method, target, arguments)
            return True

        rf = RequestFingerprint(
            method=method,
            target=target,
            arguments=arguments or {},
        )
        fp = rf.fingerprint()
        ch = rf.content_hash() if self._enable_simhash else 0

        with self._lock:
            self._total_checked += 1
            dup, kind = self._is_duplicate_locked(fp, ch)
            if dup:
                self._total_duplicates += 1
                if kind == "near":
                    self._total_near_duplicates += 1
                logger.debug(
                    "请求被去重: method=%s target=%s kind=%s",
                    method, target, kind,
                )
                return False
            # 新请求: 记录
            self._fingerprints[fp] = ch
            self._evict_if_needed()
            return True

    def clear(self) -> int:
        """清空去重集合。

        Returns:
            清除的指纹数量。
        """
        with self._lock:
            count = len(self._fingerprints)
            self._fingerprints.clear()
            return count

    def get_stats(self) -> dict[str, Any]:
        """返回统计信息。

        Returns:
            包含以下字段的字典:
              - enable_simhash: 是否启用近似去重
              - simhash_threshold: 近似阈值
              - max_fingerprints: 容量上限
              - current_size: 当前指纹数
              - total_checked: 累计检查次数
              - total_duplicates: 累计重复命中(含近似)
              - total_near_duplicates: 近似命中次数
              - total_evicted: FIFO 淘汰次数
        """
        with self._lock:
            return {
                "enable_simhash": self._enable_simhash,
                "simhash_threshold": self._simhash_threshold,
                "max_fingerprints": self._max_fingerprints,
                "current_size": len(self._fingerprints),
                "total_checked": self._total_checked,
                "total_duplicates": self._total_duplicates,
                "total_near_duplicates": self._total_near_duplicates,
                "total_evicted": self._total_evicted,
            }

    def reset(self) -> None:
        """重置到初始状态(清空集合 + 统计)。"""
        with self._lock:
            self._fingerprints.clear()
            self._total_checked = 0
            self._total_duplicates = 0
            self._total_near_duplicates = 0
            self._total_evicted = 0


# ---------------------------------------------------------------------------
# 模块级单例
# ---------------------------------------------------------------------------

_deduplicator_singleton: Optional[RequestDeduplicator] = None
_singleton_lock = threading.Lock()


def get_deduplicator(
    enable_simhash: bool = False,
    simhash_threshold: int = 3,
    max_fingerprints: int = 10000,
) -> RequestDeduplicator:
    """获取全局请求去重器单例(惰性创建)。

    首次调用按传入参数创建实例;后续调用忽略参数,直接返回已存在实例。
    若需重新配置,请先调用 reset_deduplicator()。

    Args:
        enable_simhash: 是否启用近似去重(仅首次创建时生效)。
        simhash_threshold: Simhash 汉明距离阈值(仅首次创建时生效)。
        max_fingerprints: 指纹集合上限(仅首次创建时生效)。

    Returns:
        全局唯一的 RequestDeduplicator 实例。
    """
    global _deduplicator_singleton
    with _singleton_lock:
        if _deduplicator_singleton is None:
            _deduplicator_singleton = RequestDeduplicator(
                enable_simhash=enable_simhash,
                simhash_threshold=simhash_threshold,
                max_fingerprints=max_fingerprints,
            )
        return _deduplicator_singleton


def reset_deduplicator() -> None:
    """重置全局去重器单例(主要用于测试)。

    清空单例引用,下次调用 get_deduplicator() 将按新参数创建实例。
    """
    global _deduplicator_singleton
    with _singleton_lock:
        _deduplicator_singleton = None
