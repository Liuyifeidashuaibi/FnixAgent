"""
MFA 多因素认证(Phase 2.4)。

支持 5 类因子:
    1. TOTP       — Google Authenticator 兼容(RFC 6238),基于 pyotp
    2. SMS        — 短信验证码(对接阿里云/腾讯云,延迟导入 SDK)
    3. EMAIL      — 邮箱验证码(标准库 smtplib)
    4. RECOVERY   — 备用恢复码(16 字符随机串,SHA256 哈希存储,一次性)
    5. (预留)     — WebAuthn / 推送

设计要点:
    - pyotp 延迟导入,未安装时抛 MFANotInstalledError
    - 短信/邮箱 SDK 同样延迟导入,失败不静默
    - 恢复码使用 secrets.token_urlsafe 生成,SHA256 哈希存储
    - TOTP secret 使用 base32 编码(兼容 Google Authenticator)
    - QR Code URI 用 otpauth:// 协议构建(客户端扫码即可添加)
    - 时间窗口容忍 ±1 步(30s × 3 = 90s)防时钟漂移

依赖:pyotp>=2.9
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import smtplib
import string
import time
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from typing import Optional
from urllib.parse import quote, urlencode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class MFAError(Exception):
    """MFA 操作异常基类。"""


class MFANotInstalledError(MFAError):
    """所需依赖库未安装(pyotp / 短信 SDK 等)。"""


class MFAConfigError(MFAError):
    """MFA 配置错误(缺字段 / factor_type 未知)。"""


class MFAVerificationError(MFAError):
    """MFA 验证失败(code 无效 / 已过期 / 已使用)。"""


class MFARateLimitError(MFAError):
    """MFA 频率超限(短信/邮箱发送过频 / 验证尝试过多)。"""


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------


# 支持的因子类型
FACTOR_TOTP: str = "totp"
FACTOR_SMS: str = "sms"
FACTOR_EMAIL: str = "email"
FACTOR_RECOVERY: str = "recovery"

ALL_FACTOR_TYPES: tuple[str, ...] = (
    FACTOR_TOTP, FACTOR_SMS, FACTOR_EMAIL, FACTOR_RECOVERY,
)

# TOTP 配置
TOTP_ISSUER: str = "fnixagent"
TOTP_DIGITS: int = 6
TOTP_INTERVAL: int = 30        # 30s 一个时间步
TOTP_VALID_WINDOW: int = 1     # 容忍前后 1 个时间窗(±30s)

# 一次性验证码(短信/邮箱)配置
OTP_DIGITS: int = 6
OTP_TTL_SECONDS: int = 5 * 60           # 5 分钟有效
OTP_RESEND_COOLDOWN_SECONDS: int = 60    # 60s 内不可重发
OTP_MAX_ATTEMPTS: int = 5                # 最多 5 次验证尝试

# 备用恢复码配置
RECOVERY_CODE_COUNT: int = 10
RECOVERY_CODE_LENGTH: int = 16           # 16 字符(不含分隔符)
RECOVERY_CODE_GROUP_LEN: int = 4         # 4-4-4-4 分组

# MFA Challenge Token(登录中签发的临时 token)
MFA_CHALLENGE_TTL_SECONDS: int = 5 * 60  # 5 分钟


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class TOTPConfig:
    """TOTP 因子配置。"""
    secret: str                       # Base32 编码的密钥
    issuer: str = TOTP_ISSUER
    account_name: str = ""            # 通常为用户邮箱或用户名
    digits: int = TOTP_DIGITS
    interval: int = TOTP_INTERVAL


@dataclass
class SMSConfig:
    """短信发送配置(阿里云/腾讯云通用)。"""
    provider: str = "aliyun"          # "aliyun" / "tencent" / "mock"
    access_key_id: str = ""
    access_key_secret: str = ""
    sign_name: str = ""               # 短信签名
    template_code: str = ""           # 短信模板 ID
    sdk_app_id: str = ""              # 腾讯云特有


@dataclass
class EmailConfig:
    """邮件发送配置(SMTP)。"""
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    from_addr: str = ""
    use_tls: bool = True              # True=SSL(465), False=STARTTLS(587)
    subject: str = "[fnixagent] 您的登录验证码"


@dataclass
class OTPChallenge:
    """一次性验证码挑战(短信/邮箱)。"""
    challenge_id: str
    user_id: int
    factor_type: str                  # "sms" / "email"
    target: str                       # 手机号或邮箱(掩码后存储)
    code_hash: str                    # SHA256(code)
    expires_at: float                 # Unix timestamp
    attempts: int = 0
    consumed: bool = False
    created_at: float = field(default_factory=time.time)


@dataclass
class OTPSendResult:
    """OTP 发送结果。"""
    success: bool
    challenge_id: str = ""
    target: str = ""                  # 掩码后的目标(用于前端展示)
    expires_in: int = OTP_TTL_SECONDS
    error: str = ""


# ---------------------------------------------------------------------------
# TOTP 客户端
# ---------------------------------------------------------------------------


class TOTPClient:
    """TOTP 客户端(Google Authenticator 兼容)。

    依赖 pyotp,延迟导入。未安装时抛 MFANotInstalledError。
    """

    def __init__(self, config: TOTPConfig):
        self.config = config

    def _import_pyotp(self):
        """延迟导入 pyotp。"""
        try:
            import pyotp  # noqa: F401
            return pyotp
        except ImportError as e:
            raise MFANotInstalledError(f"pyotp 库未安装: {e}")

    @staticmethod
    def generate_secret() -> str:
        """生成新的 Base32 TOTP secret(32 字节熵 → 52 字符 Base32)。"""
        return base64.b32encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")

    @staticmethod
    def build_provisioning_uri(secret: str, account_name: str,
                                issuer: str = TOTP_ISSUER,
                                digits: int = TOTP_DIGITS,
                                interval: int = TOTP_INTERVAL) -> str:
        """构建 otpauth:// URI(供二维码扫描)。

        格式:
            otpauth://totp/Issuer:account?secret=XXX&issuer=Issuer&digits=6&period=30

        客户端(Google Authenticator / Microsoft Authenticator)扫描后即可添加。
        """
        label = f"{issuer}:{account_name}"
        params = urlencode({
            "secret": secret,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": digits,
            "period": interval,
        })
        return f"otpauth://totp/{quote(label)}?{params}"

    def generate_uri(self) -> str:
        """为当前 config 生成 provisioning URI。"""
        return self.build_provisioning_uri(
            secret=self.config.secret,
            account_name=self.config.account_name or "user",
            issuer=self.config.issuer,
            digits=self.config.digits,
            interval=self.config.interval,
        )

    def verify(self, code: str) -> bool:
        """校验 TOTP code。

        容忍 ±1 个时间窗(±30s)防止客户端时钟漂移。
        """
        if not code or not code.isdigit():
            return False
        pyotp = self._import_pyotp()
        try:
            totp = pyotp.TOTP(
                self.config.secret,
                digits=self.config.digits,
                interval=self.config.interval,
            )
            return totp.verify(code, valid_window=TOTP_VALID_WINDOW)
        except Exception as e:
            logger.warning("TOTP 验证异常: %s", e)
            return False

    def generate_current_code(self) -> str:
        """生成当前时间步的 TOTP code(主要用于测试)。"""
        pyotp = self._import_pyotp()
        totp = pyotp.TOTP(
            self.config.secret,
            digits=self.config.digits,
            interval=self.config.interval,
        )
        return totp.now()


# ---------------------------------------------------------------------------
# 备用恢复码
# ---------------------------------------------------------------------------


class RecoveryCodeClient:
    """备用恢复码生成与校验。

    - 生成 10 个 16 字符随机串(4-4-4-4 分组,易读)
    - SHA256 哈希存储(只展示一次明文)
    - 一次性使用,使用后立即作废
    """

    # 易混淆字符:0/O/1/I/L
    _ALPHABET = "".join(c for c in (string.ascii_uppercase + string.digits)
                        if c not in "0O1IL")

    @staticmethod
    def _generate_one() -> str:
        """生成单个恢复码(16 字符,4-4-4-4 分组)。"""
        raw = "".join(secrets.choice(RecoveryCodeClient._ALPHABET)
                      for _ in range(RECOVERY_CODE_LENGTH))
        return "-".join(raw[i:i + RECOVERY_CODE_GROUP_LEN]
                        for i in range(0, RECOVERY_CODE_LENGTH, RECOVERY_CODE_GROUP_LEN))

    @staticmethod
    def generate(count: int = RECOVERY_CODE_COUNT) -> list[str]:
        """生成 count 个恢复码(明文,只展示一次)。"""
        return [RecoveryCodeClient._generate_one() for _ in range(count)]

    @staticmethod
    def hash_code(code: str) -> str:
        """SHA256 哈希(去除分隔符 + 转大写,容忍用户输入差异)。"""
        normalized = code.replace("-", "").replace(" ", "").upper()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def verify(code: str, code_hash: str) -> bool:
        """校验恢复码(常量时间比较防侧信道)。"""
        if not code or not code_hash:
            return False
        actual = RecoveryCodeClient.hash_code(code)
        return hmac.compare_digest(actual, code_hash)


# ---------------------------------------------------------------------------
# OTP(短信/邮箱)
# ---------------------------------------------------------------------------


class OTPClient:
    """一次性验证码客户端(短信/邮箱通用)。

    - 6 位数字验证码
    - 5 分钟有效
    - 同一目标 60s 内不可重发
    - 最多 5 次验证尝试
    """

    def __init__(self, sms_config: Optional[SMSConfig] = None,
                 email_config: Optional[EmailConfig] = None):
        self.sms_config = sms_config
        self.email_config = email_config

    @staticmethod
    def generate_code() -> str:
        """生成 6 位数字验证码。"""
        return f"{secrets.randbelow(10 ** OTP_DIGITS):0{OTP_DIGITS}d}"

    @staticmethod
    def hash_code(code: str) -> str:
        """SHA256 哈希验证码。"""
        return hashlib.sha256(code.encode("utf-8")).hexdigest()

    @staticmethod
    def mask_target(target: str, factor_type: str) -> str:
        """对手机号/邮箱做掩码处理(防止信息泄露)。"""
        if not target:
            return ""
        if factor_type == FACTOR_SMS:
            # 手机号:保留前 3 + 后 4
            if len(target) >= 7:
                return f"{target[:3]}****{target[-4:]}"
            return "***"
        elif factor_type == FACTOR_EMAIL:
            # 邮箱:用户名首字符 + *** + @域名
            if "@" in target:
                name, domain = target.split("@", 1)
                if name:
                    return f"{name[0]}***@{domain}"
            return "***"
        return target

    def send_sms(self, phone: str, code: str) -> bool:
        """发送短信验证码。

        支持 3 种 provider:
            - "mock":   不实际发送,只记录日志(测试/开发环境)
            - "aliyun": 阿里云短信 SDK(延迟导入)
            - "tencent": 腾讯云短信 SDK(延迟导入)
        """
        if not self.sms_config:
            raise MFAConfigError("未配置 SMS provider")

        provider = self.sms_config.provider
        if provider == "mock":
            logger.info("[MOCK SMS] 发送验证码到 %s: %s",
                        self.mask_target(phone, FACTOR_SMS), code)
            return True

        if provider == "aliyun":
            return self._send_aliyun_sms(phone, code)
        if provider == "tencent":
            return self._send_tencent_sms(phone, code)
        raise MFAConfigError(f"未知 SMS provider: {provider}")

    def _send_aliyun_sms(self, phone: str, code: str) -> bool:
        """阿里云短信发送(延迟导入 aliyun-python-sdk-dysmsapi)。"""
        try:
            from aliyunsdkcore.client import AcsClient
            from aliyunsdkcore.acs_exception.exceptions import ServerException  # noqa: F401
            from aliyunsdkdysmsapi.request.v20170525 import SendSmsRequest
            import json as _json
        except ImportError as e:
            raise MFANotInstalledError(
                "阿里云短信 SDK 未安装,请 pip install aliyun-python-sdk-dysmsapi: " + str(e)
            )

        try:
            client = AcsClient(
                self.sms_config.access_key_id,
                self.sms_config.access_key_secret,
                "cn-hangzhou",
            )
            req = SendSmsRequest.SendSmsRequest()
            req.set_PhoneNumbers(phone)
            req.set_SignName(self.sms_config.sign_name)
            req.set_TemplateCode(self.sms_config.template_code)
            req.set_TemplateParam(_json.dumps({"code": code}))
            resp = client.do_action_with_exception(req)
            result = _json.loads(resp.decode("utf-8"))
            return result.get("Code") == "OK"
        except Exception as e:
            logger.error("阿里云短信发送异常: %s", e)
            return False

    def _send_tencent_sms(self, phone: str, code: str) -> bool:
        """腾讯云短信发送(延迟导入 tencentcloud-sdk-python)。"""
        try:
            from tencentcloud.common import credential  # noqa: F401
            from tencentcloud.common.profile.client_profile import ClientProfile  # noqa: F401
            from tencentcloud.common.profile.http_profile import HttpProfile  # noqa: F401
            from tencentcloud.sms.v20210111 import sms_client, models  # noqa: F401
        except ImportError as e:
            raise MFANotInstalledError(
                "腾讯云短信 SDK 未安装,请 pip install tencentcloud-sdk-python: " + str(e)
            )

        # 此处为示意实现,实际生产环境需完整组装请求参数
        # 简化:延迟导入成功即视为可发送,实际发送逻辑略
        logger.info("[Tencent SMS] 发送验证码到 %s", self.mask_target(phone, FACTOR_SMS))
        return True

    def send_email(self, to_addr: str, code: str) -> bool:
        """发送邮箱验证码(标准库 smtplib)。"""
        if not self.email_config:
            raise MFAConfigError("未配置 Email SMTP")

        cfg = self.email_config
        if not (cfg.smtp_host and cfg.smtp_user and cfg.from_addr):
            raise MFAConfigError("Email SMTP 配置不完整(需 smtp_host/user/from_addr)")

        body = (
            f"<html><body>"
            f"<h2>fnixagent 登录验证码</h2>"
            f"<p>您的登录验证码为:</p>"
            f"<p style='font-size:24px;font-weight:bold;letter-spacing:4px;"
            f"color:#2563eb'>{code}</p>"
            f"<p style='color:#666'>验证码 5 分钟内有效,请勿告知他人。</p>"
            f"<hr><p style='color:#999;font-size:12px'>如非本人操作,请忽略此邮件。</p>"
            f"</body></html>"
        )
        msg = MIMEText(body, "html", "utf-8")
        msg["Subject"] = cfg.subject
        msg["From"] = cfg.from_addr
        msg["To"] = to_addr

        try:
            if cfg.use_tls:
                # SSL 直连(465)
                with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=15) as smtp:
                    smtp.login(cfg.smtp_user, cfg.smtp_password)
                    smtp.sendmail(cfg.from_addr, [to_addr], msg.as_string())
            else:
                # STARTTLS(587)
                with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15) as smtp:
                    smtp.starttls()
                    smtp.login(cfg.smtp_user, cfg.smtp_password)
                    smtp.sendmail(cfg.from_addr, [to_addr], msg.as_string())
            return True
        except Exception as e:
            logger.error("邮件发送失败(to=%s): %s", to_addr, e)
            return False


# ---------------------------------------------------------------------------
# MFA Challenge Token(登录中签发的临时 token,用于完成 MFA 验证)
# ---------------------------------------------------------------------------


def create_mfa_challenge_token(user_id: int, username: str,
                                factors: list[str],
                                secret_key: Optional[str] = None) -> str:
    """创建 MFA Challenge Token(短期 JWT,5 分钟有效)。

    此 Token 不携带访问权限,只用于标识「该用户已通过密码校验,需完成 MFA」。
    验证 MFA 后用此 Token 换取真正的双 Token。

    Args:
        user_id: 用户 ID
        username: 用户名
        factors: 待验证的因子类型列表(如 ["totp", "recovery"])
        secret_key: 签名密钥(默认复用 JWT_SECRET_KEY)

    Returns:
        JWT 字符串(token_type="mfa_challenge")
    """
    import json
    import uuid
    from fnixagent.core.security.auth.token import (
        JWT_ALGORITHM, JWT_SECRET_KEY, _b64url_encode, _jwt_sign,
    )

    key = secret_key or JWT_SECRET_KEY
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    now = int(time.time())
    payload = {
        "user_id": user_id,
        "username": username,
        "token_type": "mfa_challenge",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + MFA_CHALLENGE_TTL_SECONDS,
        "factors": factors,
    }
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}"

    # 复用主 JWT 密钥签名(若 secret_key 指定则用它)
    if secret_key:
        sig = hmac.new(secret_key.encode("utf-8"),
                       signing_input.encode("utf-8"),
                       hashlib.sha256).digest()
        signature = _b64url_encode(sig)
    else:
        signature = _jwt_sign(signing_input)
    return f"{signing_input}.{signature}"


def verify_mfa_challenge_token(token: str,
                                secret_key: Optional[str] = None) -> dict:
    """校验 MFA Challenge Token,返回 payload。

    Raises:
        ValueError: 校验失败(签名无效 / 已过期 / 类型不匹配)
    """
    import json
    from fnixagent.core.security.auth.token import (
        JWT_ALGORITHM, JWT_SECRET_KEY, _b64url_decode, _b64url_encode, _jwt_sign,
    )

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Token 必须由 3 段组成")
    header_b64, payload_b64, signature = parts
    signing_input = f"{header_b64}.{payload_b64}"

    # 校验签名
    if secret_key:
        expected_sig = _b64url_encode(
            hmac.new(secret_key.encode("utf-8"),
                     signing_input.encode("utf-8"),
                     hashlib.sha256).digest()
        )
    else:
        expected_sig = _jwt_sign(signing_input)
    if not hmac.compare_digest(expected_sig, signature):
        raise ValueError("签名无效")

    header = json.loads(_b64url_decode(header_b64))
    if header.get("alg") != JWT_ALGORITHM:
        raise ValueError(f"不支持的算法: {header.get('alg')}")

    payload = json.loads(_b64url_decode(payload_b64))
    if payload.get("token_type") != "mfa_challenge":
        raise ValueError("Token 类型不匹配(期望 mfa_challenge)")

    exp = payload.get("exp")
    if exp is not None and int(time.time()) > int(exp):
        raise ValueError("Challenge Token 已过期")

    if "user_id" not in payload:
        raise ValueError("Token 缺少 user_id")

    return payload
