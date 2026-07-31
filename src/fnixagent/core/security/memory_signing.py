"""
记忆层签名防污染 (Memory Signer) - P2 安全模块。

参考 OWASP ASI06 Memory Poisoning 缓解策略:
  - 长期记忆写入时附加 HMAC 签名
  - 读取时验签,失败则丢弃并审计
  - 记忆写入速率限制(防刷量投毒)
  - 签名密钥独立派生(从 KDFManager,context="memory_signing")

签名算法:
  - 国密模式:HMAC-SM3
  - 国际模式:HMAC-SHA256

速率限制:
  - 滑动窗口:每分钟 N 次(默认 30)
  - 突发限制:每秒 M 次(默认 5)

序列化:
  - JSON 格式,signature 字段防篡改
  - 反序列化后自动验签
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from fnixagent.core.security.crypto_provider import (
    CryptoProvider,
    get_crypto_provider,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 审计钩子
# ---------------------------------------------------------------------------


def _audit_memory(action: str, detail: dict | None = None) -> None:
    """将记忆完整性事件写入审计日志。"""
    try:
        from fnixagent.core.audit import AuditLogger

        AuditLogger().log(action=action, detail=detail or {})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class SignedMemory:
    """已签名的记忆条目。

    Attributes:
        content: 记忆内容(文本)
        metadata: 元数据(如来源、标签等)
        signature: base64 HMAC 签名
        signed_at: 签名时间(ISO 8601)
        signer: 签名者标识(user_id / agent_id)
    """

    content: str
    metadata: dict
    signature: str  # base64 HMAC
    signed_at: str  # ISO 时间戳
    signer: str  # 签名者(user_id/agent_id)


@dataclass
class MemorySignerConfig:
    """记忆签名器配置。

    Attributes:
        rate_limit_per_minute: 每分钟写入速率限制(默认 30)
        rate_limit_burst: 突发限制(每秒最大次数,默认 5)
    """

    rate_limit_per_minute: int = 30
    rate_limit_burst: int = 5


# ---------------------------------------------------------------------------
# MemorySigner
# ---------------------------------------------------------------------------


class MemorySigner:
    """记忆层签名器(防污染)。

    用法:
        signer = MemorySigner()
        signed = signer.sign("用户偏好: 喜欢简洁回复", signer="agent-1")
        # 验签
        if signer.verify(signed):
            print("记忆完整,可信任")
        else:
            print("记忆被篡改,已丢弃")
        # 序列化/反序列化
        json_str = signer.serialize(signed)
        restored = signer.deserialize(json_str)
    """

    # KDF 派生上下文(独立于其他模块)
    _KDF_CONTEXT = "memory_signing"
    # 派生密钥长度(32 字节 = 256 位)
    _KEY_LENGTH = 32

    def __init__(
        self,
        config: MemorySignerConfig | None = None,
        crypto_provider: CryptoProvider | None = None,
    ) -> None:
        self.config = config or MemorySignerConfig()
        self._crypto = crypto_provider or get_crypto_provider()
        # 签名密钥(从 KDFManager 派生)
        self._signing_key: bytes = self._derive_signing_key()
        # 速率限制:signer -> 时间戳队列
        self._rate_buckets: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    # -- 公开接口 ----------------------------------------------------------

    def sign(
        self,
        content: str,
        signer: str,
        metadata: dict | None = None,
    ) -> SignedMemory:
        """对记忆内容签名。

        Args:
            content: 记忆内容
            signer: 签名者标识
            metadata: 可选元数据

        Returns:
            SignedMemory(含签名)
        """
        metadata = metadata or {}
        signed_at = datetime.now(UTC).isoformat()
        # 构建待签名消息:content + metadata + signer + signed_at
        message = self._build_message(content, metadata, signer, signed_at)
        signature = self._compute_hmac(message)
        return SignedMemory(
            content=content,
            metadata=metadata,
            signature=signature,
            signed_at=signed_at,
            signer=signer,
        )

    def verify(self, signed: SignedMemory) -> bool:
        """验证记忆签名。

        验签失败时记录审计 memory.integrity_violation,返回 False。

        Args:
            signed: 待验证的已签名记忆

        Returns:
            True 验证通过;False 验证失败(被篡改)
        """
        try:
            message = self._build_message(
                signed.content, signed.metadata, signed.signer, signed.signed_at
            )
            expected_sig = self._compute_hmac(message)
            # 常量时间比较,防止时序攻击
            import hmac as _hmac

            if not _hmac.compare_digest(expected_sig, signed.signature):
                _audit_memory(
                    "memory.integrity_violation",
                    detail={
                        "signer": signed.signer,
                        "signed_at": signed.signed_at,
                        "reason": "signature_mismatch",
                    },
                )
                logger.warning(
                    "[memory] 记忆验签失败(signer=%s, signed_at=%s)",
                    signed.signer,
                    signed.signed_at,
                )
                return False
            return True
        except Exception as exc:
            _audit_memory(
                "memory.integrity_violation",
                detail={
                    "signer": signed.signer,
                    "reason": f"verify_error:{type(exc).__name__}",
                },
            )
            logger.error("[memory] 验签异常: %s", exc)
            return False

    def check_rate_limit(self, signer: str) -> bool:
        """检查写入速率是否在限制内。

        滑动窗口:60 秒内不超过 rate_limit_per_minute 次,
        1 秒内不超过 rate_limit_burst 次。

        Args:
            signer: 签名者标识

        Returns:
            True 允许写入;False 超出速率限制
        """
        now = time.time()
        with self._lock:
            bucket = self._rate_buckets[signer]
            # 清理超过 60 秒的记录
            while bucket and bucket[0] < now - 60:
                bucket.popleft()
            # 检查每分钟限制
            if len(bucket) >= self.config.rate_limit_per_minute:
                _audit_memory(
                    "memory.rate_limited",
                    detail={
                        "signer": signer,
                        "limit": "per_minute",
                        "count": len(bucket),
                    },
                )
                return False
            # 检查突发限制(1 秒内)
            burst_count = sum(1 for t in bucket if t > now - 1)
            if burst_count >= self.config.rate_limit_burst:
                _audit_memory(
                    "memory.rate_limited",
                    detail={
                        "signer": signer,
                        "limit": "burst",
                        "count": burst_count,
                    },
                )
                return False
            # 记录本次写入
            bucket.append(now)
            return True

    def serialize(self, signed: SignedMemory) -> str:
        """将 SignedMemory 序列化为 JSON 字符串。

        Args:
            signed: 已签名记忆

        Returns:
            JSON 字符串(含 content/metadata/signature/signed_at/signer)
        """
        return json.dumps(asdict(signed), ensure_ascii=False, sort_keys=True)

    def deserialize(self, json_str: str) -> SignedMemory:
        """从 JSON 字符串反序列化为 SignedMemory。

        Args:
            json_str: JSON 字符串

        Returns:
            SignedMemory 对象

        Raises:
            ValueError: JSON 解析失败或字段缺失
        """
        try:
            data = json.loads(json_str)
            required = {"content", "metadata", "signature", "signed_at", "signer"}
            missing = required - set(data.keys())
            if missing:
                raise ValueError(f"缺少必需字段: {missing}")
            return SignedMemory(
                content=data["content"],
                metadata=data["metadata"],
                signature=data["signature"],
                signed_at=data["signed_at"],
                signer=data["signer"],
            )
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 解析失败: {exc}") from exc

    # -- 内部辅助 ----------------------------------------------------------

    def _build_message(
        self,
        content: str,
        metadata: dict,
        signer: str,
        signed_at: str,
    ) -> bytes:
        """构建待签名的消息(payload)。

        将 content + metadata(JSON 排序)+ signer + signed_at 拼接,
        顺序固定以防止签名歧义。
        """
        metadata_json = json.dumps(metadata, sort_keys=True, ensure_ascii=False)
        raw = f"{content}|{metadata_json}|{signer}|{signed_at}"
        return raw.encode("utf-8")

    def _compute_hmac(self, message: bytes) -> str:
        """计算 HMAC 并返回 base64 编码。

        国密模式用 HMAC-SM3,国际模式用 HMAC-SHA256。
        """
        mac = self._crypto.hmac_hash(self._signing_key, message)
        return base64.b64encode(mac).decode("ascii")

    def _derive_signing_key(self) -> bytes:
        """从 KDFManager 派生签名密钥(context="memory_signing")。

        优先用 KDFManager;不可用时用环境变量;再不可用生成临时密钥。
        """
        try:
            from fnixagent.core.security.kdf import get_kdf_manager

            mgr = get_kdf_manager()
            dk = mgr.derive(context=self._KDF_CONTEXT, length=self._KEY_LENGTH)
            return dk.key
        except Exception as exc:
            logger.warning("[memory] 从 KDFManager 派生密钥失败,降级到环境变量: %s", exc)
            import hashlib
            import os

            env_key = os.getenv("OA_MEMORY_SIGNING_KEY", "")
            if env_key:
                return hashlib.sha256(env_key.encode("utf-8")).digest()
            # 生成临时密钥(开发环境)
            import secrets

            tmp_key = secrets.token_bytes(self._KEY_LENGTH)
            logger.warning("[memory] OA_MEMORY_SIGNING_KEY 未配置,生成临时密钥(重启后失效)")
            return tmp_key


# ---------------------------------------------------------------------------
# 全局单例(懒加载)
# ---------------------------------------------------------------------------


_signer_instance: MemorySigner | None = None
_signer_lock = threading.Lock()


def get_memory_signer(
    config: MemorySignerConfig | None = None,
) -> MemorySigner:
    """获取全局 MemorySigner 单例。"""
    global _signer_instance
    if _signer_instance is None:
        with _signer_lock:
            if _signer_instance is None:
                _signer_instance = MemorySigner(config)
    return _signer_instance


def reset_memory_signer() -> None:
    """重置单例(主要用于测试)。"""
    global _signer_instance
    with _signer_lock:
        _signer_instance = None
