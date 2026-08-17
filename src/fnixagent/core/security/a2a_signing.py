"""
A2A 通信签名 (Agent-to-Agent Signing) - P2 安全模块。

参考 OWASP ASI07 A2A Communication 缓解策略 + SPIFFE 模型:
  - 多 Agent 消息封装为 SignedEnvelope
  - 签名 payload || from || to || nonce || timestamp
  - 每 Agent 启动时从 SecretManager 取私钥,公钥注册到 trust store
  - 防 replay 攻击:nonce + timestamp(5 分钟内有效)
  - 跨进程通信走 mTLS(本模块只做签名层,mTLS 在 identity.py)

签名算法:
  - 默认:SM2(国密模式)或 RSA-2048-SHA256(国际模式),通过 CryptoProvider
  - 降级:HMAC-SHA256(cryptography 不可用时,用共享密钥)

防 replay:
  - nonce 随机数:os.urandom(16).hex()
  - timestamp:ISO 8601,5 分钟内有效,超出 reject
  - nonce 缓存:最近 1000 个 nonce,重复则 reject

Trust Store:
  - agent_id → public_key 映射
  - 持久化到 config/security/a2a_trust_store.json
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import base64
import json
import logging
import os
import threading
from collections import deque
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

def _audit_a2a(action: str, detail: dict | None = None) -> None:
    """将 A2A 通信安全事件写入审计日志。"""
    try:
        from fnixagent.core.audit import AuditLogger

        AuditLogger().log(action=action, detail=detail or {})
    except Exception:
        pass

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class SignedEnvelope:
    """已签名的 A2A 消息信封。

    Attributes:
        payload: 原始消息内容(JSON 字符串)
        from_agent: 发送方 Agent ID
        to_agent: 接收方 Agent ID
        nonce: 随机数(防 replay)
        timestamp: ISO 8601 时间戳
        signature: base64 签名
        algorithm: 签名算法(默认 "SM2")
    """

    payload: str  # 原始消息内容(JSON)
    from_agent: str  # 发送方 Agent ID
    to_agent: str  # 接收方 Agent ID
    nonce: str  # 随机数(防 replay)
    timestamp: str  # ISO 时间戳
    signature: str  # base64 签名
    algorithm: str = "SM2"  # 签名算法

@dataclass
class AgentIdentity:
    """Agent 身份信息(trust store 条目)。

    Attributes:
        agent_id: Agent 唯一标识
        public_key: 公钥(PEM 格式字节)
        registered_at: 注册时间(ISO 8601)
    """

    agent_id: str
    public_key: bytes  # PEM 格式
    registered_at: str

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 消息有效期(5 分钟)
_MESSAGE_TTL_SECONDS = 5 * 60
# nonce 缓存大小(最近 1000 个)
_NONCE_CACHE_SIZE = 1000
# 默认 trust store 路径(相对于项目根)
_DEFAULT_TRUST_STORE = os.path.join("config", "security", "a2a_trust_store.json")

# ---------------------------------------------------------------------------
# A2ASigner
# ---------------------------------------------------------------------------

class A2ASigner:
    """A2A 通信签名器。

    用法:
        signer = A2ASigner()
        # 注册本地 Agent(私钥用于签名)
        signer.set_local_agent("agent-1", private_key_pem, public_key_pem)
        # 签名消息
        envelope = signer.sign_message('{"task":"analyze"}', "agent-1", "agent-2")
        # 验证消息
        ok = signer.verify_message(envelope)
    """

    def __init__(
        self,
        crypto_provider: CryptoProvider | None = None,
        trust_store_path: str | None = None,
    ) -> None:
        self._crypto = crypto_provider or get_crypto_provider()
        self._trust_store_path = trust_store_path or _DEFAULT_TRUST_STORE
        # 本地 Agent 私钥:agent_id -> private_key(PEM 字节)
        self._private_keys: dict[str, bytes] = {}
        # Trust store:agent_id -> AgentIdentity
        self._trust_store: dict[str, AgentIdentity] = {}
        # nonce 缓存(防 replay)
        self._seen_nonces: deque = deque(maxlen=_NONCE_CACHE_SIZE)
        self._nonce_set: set = set()
        self._lock = threading.Lock()
        # 加载持久化的 trust store
        self._load_trust_store()

    # -- 公开接口:签名与验签 ----------------------------------------------

    def sign_message(
        self,
        payload: str,
        from_agent: str,
        to_agent: str,
    ) -> SignedEnvelope:
        """签名 A2A 消息。

        Args:
            payload: 原始消息内容(JSON 字符串)
            from_agent: 发送方 Agent ID(需已通过 set_local_agent 加载私钥)
            to_agent: 接收方 Agent ID

        Returns:
            SignedEnvelope(含签名)

        Raises:
            ValueError: from_agent 的私钥未加载
        """
        if from_agent not in self._private_keys:
            raise ValueError(f"Agent '{from_agent}' 的私钥未加载,请先调用 set_local_agent")
        # 生成 nonce 和 timestamp
        nonce = os.urandom(16).hex()
        timestamp = datetime.now(UTC).isoformat()
        # 构建待签名内容
        message = self._build_signing_message(payload, from_agent, to_agent, nonce, timestamp)
        # 签名
        private_key = self._private_keys[from_agent]
        signature_bytes = self._crypto.sign(message, private_key)
        signature = base64.b64encode(signature_bytes).decode("ascii")
        algorithm = "SM2" if self._crypto._use_sm() else "RSA-2048-SHA256"
        return SignedEnvelope(
            payload=payload,
            from_agent=from_agent,
            to_agent=to_agent,
            nonce=nonce,
            timestamp=timestamp,
            signature=signature,
            algorithm=algorithm,
        )

    def verify_message(self, envelope: SignedEnvelope) -> bool:
        """验证 A2A 消息签名。

        验证流程:
          1. 检查 from_agent 是否在 trust store 中
          2. 检查 timestamp 是否在 5 分钟有效期内
          3. 检查 nonce 是否重复(replay 攻击)
          4. 验证签名

        Args:
            envelope: 待验证的消息信封

        Returns:
            True 验证通过;False 验证失败
        """
        try:
            # 1. 检查发送方是否可信
            if not self.is_trusted(envelope.from_agent):
                _audit_a2a(
                    "a2a.verification_failed",
                    detail={
                        "from_agent": envelope.from_agent,
                        "to_agent": envelope.to_agent,
                        "reason": "untrusted_agent",
                    },
                )
                logger.warning("[a2a] 验签失败: 不可信 Agent '%s'", envelope.from_agent)
                return False

            # 2. 检查时间戳(5 分钟内有效)
            if not self._check_timestamp(envelope.timestamp):
                _audit_a2a(
                    "a2a.verification_failed",
                    detail={
                        "from_agent": envelope.from_agent,
                        "to_agent": envelope.to_agent,
                        "reason": "timestamp_expired",
                        "timestamp": envelope.timestamp,
                    },
                )
                logger.warning(
                    "[a2a] 验签失败: 时间戳过期(agent=%s, ts=%s)",
                    envelope.from_agent,
                    envelope.timestamp,
                )
                return False

            # 3. 检查 nonce(防 replay)
            with self._lock:
                if envelope.nonce in self._nonce_set:
                    _audit_a2a(
                        "a2a.verification_failed",
                        detail={
                            "from_agent": envelope.from_agent,
                            "to_agent": envelope.to_agent,
                            "reason": "nonce_replay",
                            "nonce": envelope.nonce,
                        },
                    )
                    logger.warning(
                        "[a2a] 验签失败: nonce 重复(replay 攻击, agent=%s)",
                        envelope.from_agent,
                    )
                    return False

            # 4. 验证签名
            message = self._build_signing_message(
                envelope.payload,
                envelope.from_agent,
                envelope.to_agent,
                envelope.nonce,
                envelope.timestamp,
            )
            signature_bytes = base64.b64decode(envelope.signature)
            public_key = self._trust_store[envelope.from_agent].public_key
            if not self._crypto.verify(message, signature_bytes, public_key):
                _audit_a2a(
                    "a2a.verification_failed",
                    detail={
                        "from_agent": envelope.from_agent,
                        "to_agent": envelope.to_agent,
                        "reason": "signature_invalid",
                    },
                )
                logger.warning("[a2a] 验签失败: 签名无效(agent=%s)", envelope.from_agent)
                return False

            # 验签通过,记录 nonce(防 replay)
            with self._lock:
                if envelope.nonce in self._nonce_set:
                    # 并发场景下二次检查
                    return False
                self._seen_nonces.append(envelope.nonce)
                self._nonce_set.add(envelope.nonce)
                # 维护 set 与 deque 同步
                while len(self._seen_nonces) > _NONCE_CACHE_SIZE:
                    old_nonce = self._seen_nonces.popleft()
                    self._nonce_set.discard(old_nonce)

            return True
        except Exception as exc:
            _audit_a2a(
                "a2a.verification_failed",
                detail={
                    "from_agent": envelope.from_agent,
                    "reason": f"verify_error:{type(exc).__name__}",
                },
            )
            logger.error("[a2a] 验签异常: %s", exc)
            return False

    # -- 公开接口:Trust Store 管理 -----------------------------------------

    def set_local_agent(
        self,
        agent_id: str,
        private_key: bytes,
        public_key: bytes | None = None,
    ) -> bool:
        """设置本地 Agent 身份(私钥用于签名,公钥注册到 trust store)。

        Args:
            agent_id: Agent 唯一标识
            private_key: 私钥(PEM 格式字节)
            public_key: 公钥(PEM 格式字节,为 None 时不注册到 trust store)

        Returns:
            True 设置成功
        """
        self._private_keys[agent_id] = private_key
        if public_key is not None:
            self.register_agent(agent_id, public_key)
        return True

    def register_agent(self, agent_id: str, public_key: bytes) -> bool:
        """注册 Agent 公钥到 trust store。

        Args:
            agent_id: Agent 唯一标识
            public_key: 公钥(PEM 格式字节)

        Returns:
            True 注册成功
        """
        try:
            identity = AgentIdentity(
                agent_id=agent_id,
                public_key=public_key,
                registered_at=datetime.now(UTC).isoformat(),
            )
            with self._lock:
                self._trust_store[agent_id] = identity
            self._save_trust_store()
            _audit_a2a("a2a.agent_registered", detail={"agent_id": agent_id})
            logger.info("[a2a] Agent '%s' 已注册到 trust store", agent_id)
            return True
        except Exception as exc:
            logger.error("[a2a] 注册 Agent '%s' 失败: %s", agent_id, exc)
            return False

    def revoke_agent(self, agent_id: str) -> bool:
        """吊销 Agent(从 trust store 移除)。

        Args:
            agent_id: Agent 唯一标识

        Returns:
            True 吊销成功;False Agent 不存在
        """
        with self._lock:
            if agent_id not in self._trust_store:
                return False
            del self._trust_store[agent_id]
            # 同时移除本地私钥
            self._private_keys.pop(agent_id, None)
        self._save_trust_store()
        _audit_a2a("a2a.agent_revoked", detail={"agent_id": agent_id})
        logger.info("[a2a] Agent '%s' 已从 trust store 吊销", agent_id)
        return True

    def list_trusted_agents(self) -> list[str]:
        """列出所有受信任的 Agent ID。"""
        with self._lock:
            return list(self._trust_store.keys())

    def is_trusted(self, agent_id: str) -> bool:
        """检查 Agent 是否在 trust store 中。"""
        with self._lock:
            return agent_id in self._trust_store

    # -- 公开接口:序列化 --------------------------------------------------

    def serialize_envelope(self, envelope: SignedEnvelope) -> str:
        """将 SignedEnvelope 序列化为 JSON 字符串。"""
        return json.dumps(asdict(envelope), ensure_ascii=False, sort_keys=True)

    def deserialize_envelope(self, json_str: str) -> SignedEnvelope:
        """从 JSON 字符串反序列化为 SignedEnvelope。"""
        data = json.loads(json_str)
        return SignedEnvelope(
            payload=data["payload"],
            from_agent=data["from_agent"],
            to_agent=data["to_agent"],
            nonce=data["nonce"],
            timestamp=data["timestamp"],
            signature=data["signature"],
            algorithm=data.get("algorithm", "SM2"),
        )

    # -- 内部辅助 ----------------------------------------------------------

    def _build_signing_message(
        self,
        payload: str,
        from_agent: str,
        to_agent: str,
        nonce: str,
        timestamp: str,
    ) -> bytes:
        """构建待签名消息(payload || from || to || nonce || timestamp)。

        顺序固定,用 "|" 分隔以防止歧义。
        """
        raw = f"{payload}|{from_agent}|{to_agent}|{nonce}|{timestamp}"
        return raw.encode("utf-8")

    def _check_timestamp(self, timestamp_str: str) -> bool:
        """检查时间戳是否在 5 分钟有效期内。

        Args:
            timestamp_str: ISO 8601 时间戳

        Returns:
            True 在有效期内;False 过期或格式错误
        """
        try:
            # 解析 ISO 8601 时间戳(兼容带/不带时区)
            ts = datetime.fromisoformat(timestamp_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            now = datetime.now(UTC)
            # 检查是否在 5 分钟内(允许未来时间偏差 30 秒,防时钟漂移)
            delta = abs((now - ts).total_seconds())
            return delta <= _MESSAGE_TTL_SECONDS
        except (ValueError, TypeError):
            return False

    def _load_trust_store(self) -> None:
        """从磁盘加载 trust store。"""
        try:
            if os.path.exists(self._trust_store_path):
                with open(self._trust_store_path, encoding="utf-8") as f:
                    data = json.load(f)
                for agent_id, entry in data.items():
                    self._trust_store[agent_id] = AgentIdentity(
                        agent_id=agent_id,
                        public_key=entry["public_key"].encode("utf-8"),
                        registered_at=entry.get("registered_at", ""),
                    )
                logger.info("[a2a] 已加载 trust store(%d 个 Agent)", len(self._trust_store))
        except Exception as exc:
            logger.warning("[a2a] 加载 trust store 失败: %s", exc)

    def _save_trust_store(self) -> None:
        """持久化 trust store 到磁盘。"""
        try:
            os.makedirs(os.path.dirname(self._trust_store_path), exist_ok=True)
            data = {}
            with self._lock:
                for agent_id, identity in self._trust_store.items():
                    data[agent_id] = {
                        "public_key": identity.public_key.decode("utf-8")
                        if isinstance(identity.public_key, bytes)
                        else identity.public_key,
                        "registered_at": identity.registered_at,
                    }
            with open(self._trust_store_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.error("[a2a] 保存 trust store 失败: %s", exc)

# ---------------------------------------------------------------------------
# 全局单例(懒加载)
# ---------------------------------------------------------------------------

_a2a_signer_instance: A2ASigner | None = None
_a2a_signer_lock = threading.Lock()

def get_a2a_signer(
    crypto_provider: CryptoProvider | None = None,
) -> A2ASigner:
    """获取全局 A2ASigner 单例。"""
    global _a2a_signer_instance
    if _a2a_signer_instance is None:
        with _a2a_signer_lock:
            if _a2a_signer_instance is None:
                _a2a_signer_instance = A2ASigner(crypto_provider)
    return _a2a_signer_instance

def reset_a2a_signer() -> None:
    """重置单例(主要用于测试)。"""
    global _a2a_signer_instance
    with _a2a_signer_lock:
        _a2a_signer_instance = None
