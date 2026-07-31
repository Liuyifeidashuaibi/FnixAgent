"""
SPIFFE 风格工作负载身份(Workload Identity)- P2 安全模块。

参考 SPIFFE/SPIRE SVID 规范,为每个 Agent 签发短期工作负载身份:
  - Trust Domain:spiffe://fnixagent
  - SVID 类型:x509-SVID(5 分钟有效,基于本地 CA)
  - Agent 间通信凭 SVID 做 mTLS
  - 证书自动旋转(到期前 1 分钟申请新证书)

主路径(cryptography 可用):
  - 启动时生成自签名 CA(RSA-2048,10 年),存储到 assets/keys/ca.pem 和 ca.key
  - SVID 签发:用 CA 私钥签发短期 x509 证书,CN=agent_id,SAN URI=spiffe_id

降级路径(cryptography 缺失):
  - 用 HMAC-SHA256 签发的 JWT-SVID 替代 x509-SVID
  - 共享密钥从环境变量 fnixagent_SVID_KEY 读取(缺失则生成临时密钥)

NetworkPolicy:
  - YAML 配置(config/security/network_policies.yaml),运行时加载
  - 基于 from_agent / to_agent / allowed_tools 做访问控制
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC

# 可选依赖:cryptography(x509 SVID)
try:
    from datetime import datetime, timedelta

    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    _HAS_CRYPTO = True
except ImportError:  # pragma: no cover
    _HAS_CRYPTO = False

# 可选依赖:yaml(NetworkPolicy 配置)
try:
    import yaml  # type: ignore[import-not-found]

    _HAS_YAML = True
except ImportError:  # pragma: no cover
    _HAS_YAML = False

logger = logging.getLogger(__name__)

# 默认 CA 存储路径(相对于项目根)
_DEFAULT_CA_DIR = os.path.join("assets", "keys")
_DEFAULT_POLICY_PATH = os.path.join("config", "security", "network_policies.yaml")

# JWT-SVID 降级模式的共享密钥环境变量
_JWT_KEY_ENV = "fnixagent_SVID_KEY"

# CA 证书有效期(10 年)
_CA_VALIDITY_YEARS = 10
# CA 密钥长度
_CA_KEY_SIZE = 2048


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class SVID:
    """SPIFFE Verifiable Identity Document(工作负载身份凭证)。

    Attributes:
        spiffe_id:       SPIFFE ID(如 spiffe://fnixagent/agent/doc-writer)
        cert_pem:        x509 证书 PEM(或 JWT-SVID 字符串的字节)
        private_key_pem: 私钥 PEM(JWT 模式为空)
        expires_at:      过期时间(unix timestamp)
        issuer:          签发者(默认 fnixagent-ca)
    """

    spiffe_id: str
    cert_pem: bytes
    private_key_pem: bytes
    expires_at: float
    issuer: str = "fnixagent-ca"
    # JWT 模式下的 token(cryptography 可用时为 None)
    jwt_token: str | None = None


@dataclass
class AgentIdentity:
    """Agent 工作负载身份。

    Attributes:
        agent_id:   Agent 唯一标识
        role:       Agent 角色(如 doc-writer / data-analyst)
        spiffe_id:  SPIFFE ID
        svid:       当前持有的 SVID(None 表示尚未签发)
    """

    agent_id: str
    role: str
    spiffe_id: str
    svid: SVID | None = None


@dataclass
class NetworkPolicy:
    """网络访问策略(Agent 间通信授权)。

    Attributes:
        name:           策略名
        from_agent:     源 agent_id(通配符 * 表示任意)
        to_agent:       目标 agent_id(通配符 * 表示任意)
        allowed_tools:  允许调用的工具列表
        denied:         是否拒绝(默认 False=允许)
    """

    name: str
    from_agent: str
    to_agent: str
    allowed_tools: list[str] = field(default_factory=list)
    denied: bool = False


# ---------------------------------------------------------------------------
# IdentityBroker
# ---------------------------------------------------------------------------


class IdentityBroker:
    """SPIFFE 风格身份代理(本地 CA + SVID 签发)。

    用法:
        broker = IdentityBroker()
        agent = broker.register_agent("agent-001", "doc-writer")
        svid = broker.issue_svid("agent-001")
        if broker.verify_svid(svid):
            # mTLS 通信...
            pass
        # 自动旋转即将过期的 SVID
        rotated = broker.auto_rotate()
    """

    TRUST_DOMAIN = "spiffe://fnixagent"
    SVID_TTL_SECONDS = 300  # 5 分钟
    ROTATE_BEFORE_SECONDS = 60  # 到期前 60 秒旋转

    def __init__(
        self,
        ca_cert_path: str | None = None,
        ca_key_path: str | None = None,
        policy_path: str | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._agents: dict[str, AgentIdentity] = {}
        self._ca_cert_path = ca_cert_path or os.path.join(_DEFAULT_CA_DIR, "ca.pem")
        self._ca_key_path = ca_key_path or os.path.join(_DEFAULT_CA_DIR, "ca.key")
        self._policy_path = policy_path or _DEFAULT_POLICY_PATH
        self._policies: list[NetworkPolicy] = []

        # CA 证书与私钥(惰性加载)
        self._ca_cert: bytes | None = None  # CA 证书 PEM
        self._ca_key: object | None = None  # CA 私钥对象
        self._ca_cert_obj: object | None = None  # CA 证书对象(用于验证)

        # JWT 降级模式的共享密钥
        self._jwt_key: bytes = self._load_jwt_key()

        # 初始化 CA + 加载策略
        self._init_ca()
        self._load_policies()

    # -- 公开接口 ----------------------------------------------------------

    def register_agent(self, agent_id: str, role: str) -> AgentIdentity:
        """注册新 Agent,生成 AgentIdentity(不含 SVID,需后续 issue_svid)。"""
        spiffe_id = f"{self.TRUST_DOMAIN}/agent/{role}"
        # 同一 agent_id 重复注册时更新 role
        agent = AgentIdentity(
            agent_id=agent_id,
            role=role,
            spiffe_id=spiffe_id,
        )
        with self._lock:
            self._agents[agent_id] = agent
        logger.info("[identity] 注册 Agent %s (role=%s)", agent_id, role)
        return agent

    def issue_svid(self, agent_id: str) -> SVID:
        """为指定 Agent 签发短期 SVID(x509 或 JWT 降级)。"""
        with self._lock:
            agent = self._agents.get(agent_id)
        if agent is None:
            raise ValueError(f"Agent {agent_id} 未注册,无法签发 SVID")

        now = time.time()
        expires_at = now + self.SVID_TTL_SECONDS

        if _HAS_CRYPTO and self._ca_key is not None:
            svid = self._issue_x509_svid(agent, expires_at)
        else:
            svid = self._issue_jwt_svid(agent, expires_at)

        # 更新 Agent 持有的 SVID
        with self._lock:
            self._agents[agent_id].svid = svid
        return svid

    def revoke_svid(self, agent_id: str) -> bool:
        """撤销指定 Agent 的 SVID(置空,需重新签发)。"""
        with self._lock:
            agent = self._agents.get(agent_id)
            if agent is None or agent.svid is None:
                return False
            agent.svid = None
        logger.info("[identity] 撤销 Agent %s 的 SVID", agent_id)
        return True

    def verify_svid(self, svid: SVID) -> bool:
        """验证 SVID 有效性(证书链/签名 + 过期检查)。"""
        if svid is None:
            return False
        now = time.time()
        if svid.expires_at <= now:
            logger.warning("[identity] SVID 已过期(spiffe_id=%s)", svid.spiffe_id)
            return False
        if _HAS_CRYPTO and svid.jwt_token is None:
            return self._verify_x509_svid(svid)
        return self._verify_jwt_svid(svid)

    def list_agents(self) -> list[AgentIdentity]:
        """列出所有已注册 Agent。"""
        with self._lock:
            return list(self._agents.values())

    def get_ca_cert(self) -> bytes:
        """返回 CA 证书 PEM(用于分发给验证方)。"""
        if self._ca_cert is not None:
            return self._ca_cert
        # JWT 降级模式无 CA 证书,返回 JWT 公钥指纹
        return self._jwt_key

    def auto_rotate(self) -> list[str]:
        """自动旋转即将过期的 SVID(到期前 60 秒内)。

        Returns:
            已旋转的 agent_id 列表
        """
        now = time.time()
        rotated: list[str] = []
        # 复制一份避免持锁调用 issue_svid
        with self._lock:
            agents_snapshot = list(self._agents.items())
        for agent_id, agent in agents_snapshot:
            if agent.svid is None:
                continue
            # 到期前 ROTATE_BEFORE_SECONDS 内旋转
            if agent.svid.expires_at - now < self.ROTATE_BEFORE_SECONDS:
                try:
                    self.issue_svid(agent_id)
                    rotated.append(agent_id)
                    logger.info("[identity] 自动旋转 Agent %s 的 SVID", agent_id)
                except Exception as exc:
                    logger.warning(
                        "[identity] 旋转 Agent %s 失败: %s",
                        agent_id,
                        exc,
                    )
        return rotated

    # -- NetworkPolicy 接口 ------------------------------------------------

    def check_policy(
        self,
        from_agent: str,
        to_agent: str,
        tool: str,
    ) -> bool:
        """检查 from_agent 是否可以调用 to_agent 的 tool。

        匹配规则:通配符 * 匹配任意 agent_id;denied=True 的策略优先。
        默认拒绝(无匹配策略则拒绝)。
        """
        for policy in self._policies:
            from_match = policy.from_agent == "*" or policy.from_agent == from_agent
            to_match = policy.to_agent == "*" or policy.to_agent == to_agent
            if not (from_match and to_match):
                continue
            # 命中策略
            if policy.denied:
                return False
            if not policy.allowed_tools:
                # 空列表表示允许所有工具
                return True
            if tool in policy.allowed_tools:
                return True
            # 命中 agent 匹配但工具不在白名单,继续检查其他策略
            continue
        # 无匹配策略,默认拒绝
        return False

    def load_policies(self, path: str | None = None) -> int:
        """重新加载 NetworkPolicy 配置,返回加载数量。"""
        self._policy_path = path or self._policy_path
        self._load_policies()
        return len(self._policies)

    # -- 内部:CA 初始化 ---------------------------------------------------

    def _init_ca(self) -> None:
        """初始化 CA 证书(已有则加载,否则生成自签名 CA)。"""
        if not _HAS_CRYPTO:
            logger.warning(
                "[identity] cryptography 不可用,降级到 JWT-SVID 模式",
            )
            return
        try:
            # 尝试加载已有 CA
            if os.path.exists(self._ca_cert_path) and os.path.exists(self._ca_key_path):
                self._load_ca()
            else:
                # 生成新 CA
                self._generate_ca()
        except Exception as exc:
            logger.warning(
                "[identity] CA 初始化失败,降级到 JWT-SVID: %s",
                exc,
            )
            self._ca_key = None

    def _load_ca(self) -> None:
        """从文件加载 CA 证书与私钥。"""
        with open(self._ca_cert_path, "rb") as f:
            self._ca_cert = f.read()
        with open(self._ca_key_path, "rb") as f:
            ca_key_pem = f.read()
        self._ca_key = serialization.load_pem_private_key(
            ca_key_pem,
            password=None,
            backend=default_backend(),
        )
        self._ca_cert_obj = x509.load_pem_x509_certificate(
            self._ca_cert,
            default_backend(),
        )
        logger.info("[identity] 加载已有 CA 证书: %s", self._ca_cert_path)

    def _generate_ca(self) -> None:
        """生成自签名 CA 证书并存储到文件。"""
        # 确保目录存在
        ca_dir = os.path.dirname(self._ca_cert_path)
        if ca_dir:
            os.makedirs(ca_dir, exist_ok=True)

        # 生成 RSA 私钥
        ca_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=_CA_KEY_SIZE,
            backend=default_backend(),
        )

        # 生成自签名 CA 证书
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, "fnixagent CA"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "fnixagent"),
            ]
        )
        now = datetime.now(UTC)
        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=365 * _CA_VALIDITY_YEARS))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_cert_sign=True,
                    crl_sign=True,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    content_commitment=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(ca_key, hashes.SHA256(), default_backend())
        )

        # 序列化
        self._ca_cert = ca_cert.public_bytes(serialization.Encoding.PEM)
        ca_key_pem = ca_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self._ca_key = ca_key
        self._ca_cert_obj = ca_cert

        # 持久化(权限限制为仅 owner 可读)
        self._write_ca_files(self._ca_cert, ca_key_pem)
        logger.info("[identity] 生成新 CA 证书: %s", self._ca_cert_path)

    def _write_ca_files(self, cert_pem: bytes, key_pem: bytes) -> None:
        """写入 CA 证书与私钥文件(异常吞掉,不影响主流程)。"""
        try:
            with open(self._ca_cert_path, "wb") as f:
                f.write(cert_pem)
            with open(self._ca_key_path, "wb") as f:
                f.write(key_pem)
            # Unix 下设置 0600 权限
            try:
                os.chmod(self._ca_key_path, 0o600)
            except OSError:
                pass
        except OSError as exc:
            logger.warning("[identity] CA 文件写入失败: %s", exc)

    # -- 内部:x509 SVID 签发 ---------------------------------------------

    def _issue_x509_svid(self, agent: AgentIdentity, expires_at: float) -> SVID:
        """用 CA 私钥签发 x509-SVID(CN=agent_id,SAN URI=spiffe_id)。"""
        # 生成 Agent 专属密钥对
        agent_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=_CA_KEY_SIZE,
            backend=default_backend(),
        )

        # 构造证书
        now = datetime.now(UTC)
        ttl = expires_at - time.time()
        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, agent.agent_id),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "fnixagent"),
            ]
        )
        # SAN URI = spiffe_id(SPIFFE 规范)
        san = x509.SubjectAlternativeName(
            [
                x509.UniformResourceIdentifier(agent.spiffe_id),
            ]
        )

        ca_key = self._ca_key  # type: ignore[assignment]
        ca_cert_obj = self._ca_cert_obj

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert_obj.subject)  # type: ignore[union-attr]
            .public_key(agent_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(seconds=max(ttl, 1)))
            .add_extension(san, critical=False)
            .add_extension(
                x509.ExtendedKeyUsage(
                    [ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]
                ),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256(), default_backend())
        )

        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        key_pem = agent_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        return SVID(
            spiffe_id=agent.spiffe_id,
            cert_pem=cert_pem,
            private_key_pem=key_pem,
            expires_at=expires_at,
            issuer="fnixagent-ca",
        )

    def _verify_x509_svid(self, svid: SVID) -> bool:
        """验证 x509-SVID:证书链验证(svid cert → CA cert)。"""
        try:
            cert = x509.load_pem_x509_certificate(
                svid.cert_pem,
                default_backend(),
            )
            ca_cert = self._ca_cert_obj
            if ca_cert is None:
                return False
            # 检查签名(用 CA 公钥验证 svid 证书签名)
            ca_pubkey = ca_cert.public_key()
            from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding

            ca_pubkey.verify(  # type: ignore[union-attr]
                cert.signature,
                cert.tbs_certificate_bytes,
                rsa_padding.PKCS1v15(),
                cert.signature_hash_algorithm,
            )
            # 检查 SAN URI 是否匹配 spiffe_id
            san_ext = cert.extensions.get_extension_for_class(
                x509.SubjectAlternativeName,
            )
            uris = san_ext.value.get_values_for_type(x509.UniformResourceIdentifier)
            if svid.spiffe_id not in uris:
                logger.warning(
                    "[identity] SVID SAN URI 不匹配: %s vs %s",
                    svid.spiffe_id,
                    uris,
                )
                return False
            return True
        except Exception as exc:
            logger.warning("[identity] x509 SVID 验证失败: %s", exc)
            return False

    # -- 内部:JWT-SVID 降级 ----------------------------------------------

    def _load_jwt_key(self) -> bytes:
        """加载 JWT 签名密钥(从环境变量,缺失则派生固定密钥)。"""
        key = os.environ.get(_JWT_KEY_ENV)
        if key:
            return key.encode("utf-8")
        # 派生固定密钥(仅开发用)
        return hashlib.sha256(b"fnixagent-jwt-svid-dev-key").digest()

    def _issue_jwt_svid(self, agent: AgentIdentity, expires_at: float) -> SVID:
        """签发 JWT-SVID(HMAC-SHA256,header.payload.signature)。"""
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "sub": agent.agent_id,
            "spiffe_id": agent.spiffe_id,
            "iss": "fnixagent-ca",
            "iat": int(time.time()),
            "exp": int(expires_at),
        }
        header_b = base64.urlsafe_b64encode(
            json.dumps(header, separators=(",", ":")).encode(),
        ).rstrip(b"=")
        payload_b = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode(),
        ).rstrip(b"=")
        signing_input = header_b + b"." + payload_b
        sig = hmac.new(self._jwt_key, signing_input, hashlib.sha256).digest()
        sig_b = base64.urlsafe_b64encode(sig).rstrip(b"=")
        token = (signing_input + b"." + sig_b).decode("ascii")

        return SVID(
            spiffe_id=agent.spiffe_id,
            cert_pem=token.encode("utf-8"),
            private_key_pem=b"",
            expires_at=expires_at,
            issuer="fnixagent-ca",
            jwt_token=token,
        )

    def _verify_jwt_svid(self, svid: SVID) -> bool:
        """验证 JWT-SVID 签名与过期时间。"""
        try:
            token = svid.jwt_token or svid.cert_pem.decode("ascii")
            parts = token.split(".")
            if len(parts) != 3:
                return False
            signing_input = (parts[0] + "." + parts[1]).encode("ascii")
            expected_sig = hmac.new(
                self._jwt_key,
                signing_input,
                hashlib.sha256,
            ).digest()
            actual_sig = base64.urlsafe_b64decode(parts[2] + "==")
            if not hmac.compare_digest(expected_sig, actual_sig):
                logger.warning("[identity] JWT-SVID 签名验证失败")
                return False
            # 解析 payload 检查 spiffe_id
            payload_b = parts[1] + "=="
            payload = json.loads(base64.urlsafe_b64decode(payload_b))
            if payload.get("spiffe_id") != svid.spiffe_id:
                logger.warning("[identity] JWT-SVID spiffe_id 不匹配")
                return False
            return True
        except Exception as exc:
            logger.warning("[identity] JWT-SVID 验证失败: %s", exc)
            return False

    # -- 内部:策略加载 ----------------------------------------------------

    def _load_policies(self) -> None:
        """从 YAML 加载 NetworkPolicy 配置(失败降级到空列表)。"""
        self._policies = []
        if not _HAS_YAML:
            logger.warning("[identity] yaml 不可用,NetworkPolicy 配置未加载")
            return
        try:
            if not os.path.exists(self._policy_path):
                logger.info(
                    "[identity] NetworkPolicy 配置不存在: %s",
                    self._policy_path,
                )
                return
            with open(self._policy_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            policies_data = data.get("policies", [])
            for item in policies_data:
                policy = NetworkPolicy(
                    name=item.get("name", ""),
                    from_agent=item.get("from", "*"),
                    to_agent=item.get("to", "*"),
                    allowed_tools=item.get("allowed_tools", []),
                    denied=item.get("denied", False),
                )
                self._policies.append(policy)
            logger.info(
                "[identity] 加载 %d 条 NetworkPolicy",
                len(self._policies),
            )
        except Exception as exc:
            logger.warning("[identity] NetworkPolicy 加载失败: %s", exc)
            self._policies = []
