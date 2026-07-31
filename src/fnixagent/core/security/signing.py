"""
数字签名 (Document Signer) - P1 安全模块。

为所有生成的 docx/xlsx/pptx 文件嵌入数字签名,验证文件未被篡改。

签名算法:
  - 主路径:RSA-2048 + SHA256(用 cryptography 库)
  - 降级路径:cryptography 缺失时用 SHA256 校验和(algorithm="SHA256-checksum")

签名嵌入:所有 OOXML 格式(docx/xlsx/pptx)本质是 ZIP 包,
在 ZIP 内 docProps/custom.xml 写入 "oa_signature" 字段(JSON),
该方式与 python-docx / openpyxl / python-pptx 兼容(不影响文档内容)。

验签流程:
  1. 读取 ZIP 内 docProps/custom.xml 提取签名 JSON
  2. 重新计算文件哈希(排除 docProps/custom.xml 条目)
  3. RSA 公钥验签 / 校验和比对

密钥管理:
  - 默认 keystore 路径:assets/keys/
  - 私钥用 AES-256 加密存储(密码从环境变量 OA_SIGNING_KEY_PASSWORD 读取)
  - 与 JWT 密钥分离,独立 KMS 管理(本模块用本地 keystore)
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

# 可选依赖:cryptography(RSA 签名)
try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    _HAS_CRYPTO = True
except ImportError:  # pragma: no cover
    _HAS_CRYPTO = False


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 签名嵌入位置(ZIP 内路径)
_SIGNATURE_ZIP_PATH = "docProps/custom.xml"
# custom.xml 模板(OOXML 规范)
_CUSTOM_XML_TEMPLATE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    "<Properties "
    'xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" '
    'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
    "{properties}</Properties>"
)
# 单个 property 模板
_PROPERTY_TEMPLATE = (
    '<property fmtid="{{D5CDD505-2E9C-101B-9397-08002B2CF9AE}}" pid="{pid}" '
    'name="{name}"><vt:lpwstr>{value}</vt:lpwstr></property>'
)

# 签名字段名
_SIGNATURE_FIELD = "oa_signature"

# 密钥派生参数
_PBKDF2_ITERATIONS = 100_000
_SALT = b"fnixagent-signing-salt-v1"  # 固定盐(密码本身应为高熵)

# 默认 keystore 路径(相对于项目根)
_DEFAULT_KEYSTORE = os.path.join("assets", "keys")


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class SignatureInfo:
    """签名信息(嵌入文件 custom properties)。

    signed_at/signed_by/key_id/algorithm/file_hash/signature 分别为
    签名时间(ISO 8601)、签名者、密钥 ID、算法("RSA-2048-SHA256" /
    "SHA256-checksum")、文件 SHA256、base64 签名。
    """

    signed_at: str
    signed_by: str
    key_id: str
    algorithm: str
    file_hash: str
    signature: str


@dataclass
class VerifyResult:
    """验签结果。

    valid/signed 标记签名有效性与是否存在签名;
    signed_at/signed_by 在有签名时填充;reason 为判定原因。
    """

    valid: bool
    signed: bool
    signed_at: str | None = None
    signed_by: str | None = None
    reason: str = ""


# ---------------------------------------------------------------------------
# DocumentSigner
# ---------------------------------------------------------------------------


class DocumentSigner:
    """OOXML 文档数字签名器。

    支持 docx/xlsx/pptx 三种格式的签名嵌入与验证。
    密钥独立于 JWT,从本地 keystore 加载(可用 generate_keypair 生成)。
    """

    SUPPORTED_EXTS = ("docx", "xlsx", "pptx")

    def __init__(self, keystore_path: str | None = None):
        """初始化签名器。

        Args:
            keystore_path: keystore 目录路径(默认 assets/keys/)
        """
        self.keystore_path = keystore_path or _DEFAULT_KEYSTORE
        # 当前激活的密钥 ID 与私钥/公钥对象
        self._active_key_id: str = "default"
        self._private_key = None  # cryptography 私钥对象
        self._public_key = None  # cryptography 公钥对象

    # -- 公开 API ---------------------------------------------------------

    def sign(self, file_path: str, signed_by: str = "system") -> bool:
        """对文件签名(嵌入签名到 custom properties)。

        Args:
            file_path: 文件路径(必须是 docx/xlsx/pptx)
            signed_by: 签名者标识

        Returns:
            True 表示签名成功;False 表示失败(格式不支持 / 密钥缺失 / IO 异常)
        """
        if not self._is_supported(file_path):
            return False
        try:
            # 确保密钥可用
            if not self._ensure_key():
                return False

            # 1. 读取文件字节
            with open(file_path, "rb") as f:
                file_bytes = f.read()

            # 2. 计算文件哈希(排除已有签名)
            file_hash = self._compute_file_hash(file_bytes)

            # 3. 生成签名
            signature, algorithm = self._sign_hash(file_hash)

            # 4. 构建 SignatureInfo
            sig_info = SignatureInfo(
                signed_at=datetime.now(UTC).isoformat(),
                signed_by=signed_by,
                key_id=self._active_key_id,
                algorithm=algorithm,
                file_hash=file_hash,
                signature=signature,
            )

            # 5. 嵌入到 ZIP 的 docProps/custom.xml
            return self._inject_signature(file_path, sig_info)
        except Exception:
            # 任何异常不外泄,返回 False
            return False

    def verify(self, file_path: str) -> VerifyResult:
        """验证文件签名。

        Args:
            file_path: 文件路径

        Returns:
            VerifyResult:含 valid / signed / signed_at / signed_by / reason
        """
        if not self._is_supported(file_path):
            return VerifyResult(
                valid=False,
                signed=False,
                reason=f"不支持的文件格式(仅 {self.SUPPORTED_EXTS})",
            )
        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()

            # 1. 提取签名 JSON
            sig_json = self._extract_signature(file_bytes)
            if not sig_json:
                return VerifyResult(
                    valid=False,
                    signed=False,
                    reason="文件未包含签名",
                )

            sig_info = SignatureInfo(
                signed_at=sig_json.get("signed_at", ""),
                signed_by=sig_json.get("signed_by", ""),
                key_id=sig_json.get("key_id", ""),
                algorithm=sig_json.get("algorithm", ""),
                file_hash=sig_json.get("file_hash", ""),
                signature=sig_json.get("signature", ""),
            )

            # 复用构造函数(避免重复传 signed_at/signed_by)
            def _result(valid: bool, reason: str) -> VerifyResult:
                return VerifyResult(
                    valid=valid,
                    signed=True,
                    signed_at=sig_info.signed_at,
                    signed_by=sig_info.signed_by,
                    reason=reason,
                )

            # 2. 重新计算文件哈希(排除签名字段)并比对
            current_hash = self._compute_file_hash(file_bytes)
            if current_hash != sig_info.file_hash:
                return _result(False, "文件内容已被篡改(哈希不匹配)")

            # 3. SHA256-checksum 模式跳过 RSA 验签
            if sig_info.algorithm == "SHA256-checksum":
                return _result(True, "校验和验证通过(SHA256-checksum 模式)")

            # 4. RSA 验签
            if not _HAS_CRYPTO:
                return _result(False, "cryptography 库不可用,无法验证 RSA 签名")
            if not self._verify_rsa(sig_info):
                return _result(False, "RSA 签名验证失败")
            return _result(True, "签名验证通过")
        except Exception as e:
            return VerifyResult(
                valid=False,
                signed=False,
                reason=f"验签异常: {type(e).__name__}: {e}",
            )

    def generate_keypair(self, key_id: str = "default") -> bool:
        """生成新的 RSA-2048 密钥对并保存到 keystore。

        Args:
            key_id: 密钥 ID(用于区分多套密钥)

        Returns:
            True 成功;False 失败(库不可用 / IO 错误)
        """
        if not _HAS_CRYPTO:
            # 降级模式:不生成密钥,使用 SHA256-checksum
            self._active_key_id = key_id
            return True
        try:
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend(),
            )
            self._private_key = private_key
            self._public_key = private_key.public_key()
            self._active_key_id = key_id
            return self._save_keypair(key_id, private_key)
        except Exception:
            return False

    def list_keys(self) -> list[str]:
        """列出 keystore 中所有密钥 ID。"""
        keys: list[str] = []
        try:
            if not os.path.isdir(self.keystore_path):
                return keys
            for name in os.listdir(self.keystore_path):
                if name.endswith(".private.pem"):
                    keys.append(name[: -len(".private.pem")])
        except Exception:
            pass
        return keys

    def rotate_key(self, key_id: str) -> bool:
        """轮换密钥(生成新密钥覆盖旧密钥)。

        Args:
            key_id: 要轮换的密钥 ID

        Returns:
            True 成功;False 失败
        """
        return self.generate_keypair(key_id)

    # -- 内部辅助:文件格式与哈希 -----------------------------------------

    def _is_supported(self, file_path: str) -> bool:
        """检查文件扩展名是否受支持。"""
        ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        return ext in self.SUPPORTED_EXTS

    def _compute_file_hash(self, file_bytes: bytes) -> str:
        """计算文件 SHA256(排除 docProps/custom.xml 签名字段)。

        将 ZIP 内所有条目(除签名字段外)按名称排序后拼接,计算 SHA256。
        这样签名字段本身的变更不会影响哈希值。
        """
        sha = hashlib.sha256()
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as zf:
                names = sorted(n for n in zf.namelist() if n != _SIGNATURE_ZIP_PATH)
                for name in names:
                    # 写入条目名 + 内容,确保唯一性
                    sha.update(name.encode("utf-8"))
                    sha.update(zf.read(name))
        except zipfile.BadZipFile:
            # 非 ZIP 文件,直接哈希原始字节
            sha.update(file_bytes)
        return sha.hexdigest()

    # -- 内部辅助:签名嵌入与提取 -----------------------------------------

    def _inject_signature(self, file_path: str, sig_info: SignatureInfo) -> bool:
        """将签名 JSON 注入 ZIP 的 docProps/custom.xml。

        实现:读取原 ZIP 所有条目 → 重写为新 ZIP,替换 custom.xml。
        """
        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()

            # 序列化签名信息为 JSON
            sig_json = json.dumps(asdict(sig_info), ensure_ascii=False)
            # XML 转义
            sig_xml_escaped = (
                sig_json.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )

            # 构建 custom.xml 内容
            custom_xml = _CUSTOM_XML_TEMPLATE.format(
                properties=_PROPERTY_TEMPLATE.format(
                    pid=2,
                    name=_SIGNATURE_FIELD,
                    value=sig_xml_escaped,
                )
            )

            # 重写 ZIP:保留所有原条目,替换/新增 custom.xml
            output_buf = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as src:
                with zipfile.ZipFile(output_buf, "w", zipfile.ZIP_DEFLATED) as dst:
                    for item in src.infolist():
                        if item.filename == _SIGNATURE_ZIP_PATH:
                            continue  # 跳过旧签名
                        dst.writestr(item, src.read(item.filename))
                    # 写入新签名
                    dst.writestr(_SIGNATURE_ZIP_PATH, custom_xml)

            # 写回原文件
            with open(file_path, "wb") as f:
                f.write(output_buf.getvalue())
            return True
        except Exception:
            return False

    def _extract_signature(self, file_bytes: bytes) -> dict | None:
        """从 ZIP 内 docProps/custom.xml 提取签名 JSON。"""
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as zf:
                if _SIGNATURE_ZIP_PATH not in zf.namelist():
                    return None
                xml_content = zf.read(_SIGNATURE_ZIP_PATH).decode("utf-8")
            # 简易提取:找 name="oa_signature" 的 property,取 <vt:lpwstr>...</vt:lpwstr> 内容
            import re

            m = re.search(
                r'name="' + _SIGNATURE_FIELD + r'".*?<vt:lpwstr>(.*?)</vt:lpwstr>',
                xml_content,
                re.DOTALL,
            )
            if not m:
                return None
            # XML 反转义
            sig_json = (
                m.group(1)
                .replace("&quot;", '"')
                .replace("&gt;", ">")
                .replace("&lt;", "<")
                .replace("&amp;", "&")
            )
            return json.loads(sig_json)
        except Exception:
            return None

    # -- 内部辅助:密钥管理 -----------------------------------------------

    def _ensure_key(self) -> bool:
        """确保有可用密钥(已加载 / 加载 / 生成;降级模式直接放行)。"""
        # 降级模式:cryptography 不可用,用 SHA256-checksum
        if not _HAS_CRYPTO:
            self._active_key_id = self._active_key_id or "default"
            return True
        # 已加载
        if self._private_key is not None:
            return True
        # 尝试加载已有密钥,失败则生成
        return self._load_keypair(self._active_key_id) or self.generate_keypair(self._active_key_id)

    def _load_keypair(self, key_id: str) -> bool:
        """从 keystore 加载密钥对(私钥解密后注入)。"""
        if not _HAS_CRYPTO:
            return False
        try:
            priv_path = os.path.join(self.keystore_path, f"{key_id}.private.pem")
            if not os.path.exists(priv_path):
                return False
            with open(priv_path, "rb") as f:
                encrypted_pem = f.read()
            private_key = serialization.load_pem_private_key(
                self._decrypt_private_key(encrypted_pem, self._get_keystore_password()),
                password=None,
                backend=default_backend(),
            )
            self._private_key = private_key
            self._public_key = private_key.public_key()
            self._active_key_id = key_id
            return True
        except Exception:
            return False

    def _save_keypair(self, key_id: str, private_key) -> bool:
        """保存密钥对到 keystore(私钥 AES-256 加密,公钥明文)。"""
        try:
            os.makedirs(self.keystore_path, exist_ok=True)
            # 私钥:PEM 序列化 → AES-256-GCM 加密
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            encrypted = self._encrypt_private_key(private_pem, self._get_keystore_password())
            with open(os.path.join(self.keystore_path, f"{key_id}.private.pem"), "wb") as f:
                f.write(encrypted)
            # 公钥:明文存储
            public_pem = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            with open(os.path.join(self.keystore_path, f"{key_id}.public.pem"), "wb") as f:
                f.write(public_pem)
            return True
        except Exception:
            return False

    def _get_keystore_password(self) -> bytes:
        """获取 keystore 加密密码(从环境变量,与 JWT 密钥分离)。"""
        return os.getenv(
            "OA_SIGNING_KEY_PASSWORD",
            "fnixagent-signing-default-change-me",
        ).encode("utf-8")

    def _encrypt_private_key(self, pem_bytes: bytes, password: bytes) -> bytes:
        """AES-256-GCM 加密私钥 PEM。"""
        # 派生密钥(PBKDF2)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_SALT,
            iterations=_PBKDF2_ITERATIONS,
            backend=default_backend(),
        )
        key = kdf.derive(password)
        # 生成随机 IV
        iv = os.urandom(12)  # GCM 推荐 12 字节
        cipher = Cipher(algorithms.AES(key), modes.GCM(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(pem_bytes) + encryptor.finalize()
        # 拼接 IV + tag + ciphertext
        return iv + encryptor.tag + ciphertext

    def _decrypt_private_key(self, encrypted: bytes, password: bytes) -> bytes:
        """AES-256-GCM 解密私钥 PEM。"""
        iv = encrypted[:12]
        tag = encrypted[12:28]
        ciphertext = encrypted[28:]
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_SALT,
            iterations=_PBKDF2_ITERATIONS,
            backend=default_backend(),
        )
        key = kdf.derive(password)
        cipher = Cipher(algorithms.AES(key), modes.GCM(iv, tag), backend=default_backend())
        decryptor = cipher.decryptor()
        return decryptor.update(ciphertext) + decryptor.finalize()

    # -- 内部辅助:RSA 签名与验签 -----------------------------------------

    def _sign_hash(self, file_hash: str) -> tuple[str, str]:
        """对文件哈希签名,返回 (base64 签名, 算法名)。"""
        if not _HAS_CRYPTO or self._private_key is None:
            # 降级:用密码做 HMAC-SHA256 作为校验和
            password = self._get_keystore_password()
            import hmac

            sig = hmac.new(password, file_hash.encode("utf-8"), hashlib.sha256).hexdigest()
            return sig, "SHA256-checksum"

        # RSA-2048 + SHA256 签名
        signature = self._private_key.sign(
            file_hash.encode("utf-8"),
            rsa_padding.PSS(
                mgf=rsa_padding.MGF1(hashes.SHA256()),
                salt_length=rsa_padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("ascii"), "RSA-2048-SHA256"

    def _verify_rsa(self, sig_info: SignatureInfo) -> bool:
        """RSA 公钥验签。"""
        if not _HAS_CRYPTO or self._public_key is None:
            # 尝试从 keystore 加载公钥
            if not self._load_public_key(sig_info.key_id):
                return False
        try:
            signature = base64.b64decode(sig_info.signature)
            self._public_key.verify(
                signature,
                sig_info.file_hash.encode("utf-8"),
                rsa_padding.PSS(
                    mgf=rsa_padding.MGF1(hashes.SHA256()),
                    salt_length=rsa_padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            return True
        except Exception:
            return False

    def _load_public_key(self, key_id: str) -> bool:
        """从 keystore 加载公钥(用于验签)。"""
        try:
            pub_path = os.path.join(self.keystore_path, f"{key_id}.public.pem")
            if not os.path.exists(pub_path):
                return False
            with open(pub_path, "rb") as f:
                public_pem = f.read()
            self._public_key = serialization.load_pem_public_key(
                public_pem, backend=default_backend()
            )
            return True
        except Exception:
            return False
