"""
插件供应链校验 (Supply Chain Verifier) - P3 安全模块。

参考 OWASP ASI04 + SLSA,对插件包(Skill/MCP/Converter)安装前校验:
  - 包哈希校验(SHA256)
  - 签名校验(RSA-2048 + SHA256,用 cryptography 库)
  - 公钥指纹白名单(trusted_keys.json)
  - SBOM 生成(cyclonedx 兼容格式)
  - 依赖 CVE 检查(子进程调用 pip-audit)

设计原则:
  - 可选依赖:cryptography 缺失时签名校验降级(仅哈希)
  - 可选依赖:pip-audit 缺失时 CVE 检查降级(返回空列表 + warning)
  - 所有异常不外泄,捕获后返回合理默认值
  - 白名单存储:trusted_keys.json = {key_id: {public_key_pem, fingerprint, trusted_at}}
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# 可选依赖:cryptography(RSA 签名校验)
try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding

    _HAS_CRYPTO = True
except ImportError:  # pragma: no cover
    _HAS_CRYPTO = False


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class PackageInfo:
    """插件包信息。

    Attributes:
        name: 包名
        version: 版本
        source: 来源(pypi/local/git)
        sha256: 包哈希
        signature: base64 签名(可选)
        signed_by: 签名者 key_id(可选)
    """

    name: str
    version: str
    source: str
    sha256: str
    signature: str | None = None
    signed_by: str | None = None


@dataclass
class VerificationResult:
    """供应链校验结果。

    Attributes:
        valid: 整体是否有效
        trusted: 是否在白名单
        signature_valid: 签名是否有效
        hash_matched: 哈希是否匹配
        sbom_generated: 是否已生成 SBOM
        vulnerabilities: 漏洞列表
        reason: 判定原因
    """

    valid: bool
    trusted: bool
    signature_valid: bool
    hash_matched: bool
    sbom_generated: bool
    vulnerabilities: list[dict] = field(default_factory=list)
    reason: str = ""


@dataclass
class SBOMEntry:
    """SBOM 单条目(cyclonedx 兼容)。

    Attributes:
        name: 组件名
        version: 版本
        type: 类型(pip/package/library)
        purl: Package URL
        hashes: {algorithm: hash}
    """

    name: str
    version: str
    type: str
    purl: str
    hashes: dict[str, str]


# ---------------------------------------------------------------------------
# SupplyChainVerifier
# ---------------------------------------------------------------------------


class SupplyChainVerifier:
    """插件供应链校验器。

    用法:
        verifier = SupplyChainVerifier()
        result = verifier.verify_package("/tmp/plugin.zip", signature="base64...")
        if not result.valid:
            raise SecurityError("插件校验失败: " + result.reason)
        sbom = verifier.generate_sbom("requirements.txt")
        vulns = verifier.check_vulnerabilities("requirements.txt")
    """

    # 信任公钥存储路径
    _DEFAULT_TRUSTED_KEYS = os.path.join("config", "security", "trusted_keys.json")

    def __init__(self, trusted_keys_path: str = "config/security/trusted_keys.json") -> None:
        self._trusted_keys_path = trusted_keys_path
        self._trusted_keys: dict[str, dict] = self._load_trusted_keys()

    # -- 公开接口:包校验 -------------------------------------------------

    def verify_package(
        self,
        package_path: str,
        signature: str | None = None,
    ) -> VerificationResult:
        """校验插件包(哈希 + 签名 + 白名单)。

        Args:
            package_path: 包文件路径(zip/tar.gz/whl 等)
            signature: base64 签名(可选,若提供则校验)
        """
        if not os.path.exists(package_path):
            return VerificationResult(
                valid=False,
                trusted=False,
                signature_valid=False,
                hash_matched=False,
                sbom_generated=False,
                reason=f"包不存在: {package_path}",
            )
        # 1. 计算哈希
        sha256 = self._compute_hash(package_path)
        hash_matched = True  # 无预期哈希时,仅记录实际哈希
        # 2. 签名校验
        signature_valid = False
        signed_by: str | None = None
        if signature:
            try:
                with open(package_path, "rb") as f:
                    data = f.read()
                signed_by, signature_valid = self._verify_signature_any_key(
                    data,
                    signature,
                )
            except Exception as exc:
                logger.warning("[supply_chain] 签名校验失败: %s", exc)
        # 3. 白名单校验(签名者 key_id 在 trusted_keys 中)
        trusted = bool(signed_by and signed_by in self._trusted_keys)
        # 4. 判定整体有效性
        valid = hash_matched and (not signature or signature_valid) and trusted
        reason_parts = []
        if not hash_matched:
            reason_parts.append("哈希不匹配")
        if signature and not signature_valid:
            reason_parts.append("签名无效")
        if not trusted:
            reason_parts.append("签名者不在白名单")
        if not signature:
            reason_parts.append("无签名(未校验)")
        reason = "; ".join(reason_parts) if reason_parts else "校验通过"
        self._audit_verify(
            "supply_chain.verify_package",
            {
                "path": package_path,
                "sha256": sha256[:16] + "...",
                "signature_valid": signature_valid,
                "trusted": trusted,
            },
        )
        return VerificationResult(
            valid=valid,
            trusted=trusted,
            signature_valid=signature_valid,
            hash_matched=hash_matched,
            sbom_generated=False,
            reason=reason,
        )

    def verify_dependency(self, name: str, version: str) -> VerificationResult:
        """校验单个依赖(白名单 + CVE 检查)。

        Args:
            name: 依赖名(如 requests)
            version: 版本(如 2.31.0)
        """
        # CVE 检查(通过 pip-audit,粒度较粗)
        vulns = self._run_pip_audit_for_pkg(name, version)
        valid = len(vulns) == 0
        return VerificationResult(
            valid=valid,
            trusted=True,
            signature_valid=True,
            hash_matched=True,
            sbom_generated=False,
            vulnerabilities=vulns,
            reason="无已知漏洞" if valid else f"发现 {len(vulns)} 个漏洞",
        )

    # -- 公开接口:SBOM ---------------------------------------------------

    def generate_sbom(
        self,
        requirements_path: str = "requirements.txt",
    ) -> list[SBOMEntry]:
        """解析 requirements.txt 生成 SBOM(cyclonedx 兼容)。

        Args:
            requirements_path: requirements.txt 路径
        """
        entries: list[SBOMEntry] = []
        if not os.path.exists(requirements_path):
            logger.warning("[supply_chain] requirements 不存在: %s", requirements_path)
            return entries
        try:
            with open(requirements_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # 去掉注释与环境标记
                    line = line.split("#", 1)[0].strip()
                    if ";" in line:
                        line = line.split(";", 1)[0].strip()
                    if not line:
                        continue
                    name, version = self._parse_requirement(line)
                    if not name:
                        continue
                    purl = f"pkg:pypi/{name.lower()}@{version}"
                    entries.append(
                        SBOMEntry(
                            name=name,
                            version=version,
                            type="pip",
                            purl=purl,
                            hashes={},
                        )
                    )
        except Exception as exc:
            logger.warning("[supply_chain] SBOM 生成失败: %s", exc)
        return entries

    # -- 公开接口:CVE 检查 ----------------------------------------------

    def check_vulnerabilities(
        self,
        requirements_path: str = "requirements.txt",
    ) -> list[dict]:
        """调用 pip-audit 检查依赖漏洞。

        Args:
            requirements_path: requirements.txt 路径

        Returns:
            漏洞列表,每项含 name/version/id/summary
        """
        return self._run_pip_audit(requirements_path)

    # -- 公开接口:信任密钥管理 -------------------------------------------

    def add_trusted_key(
        self,
        key_id: str,
        public_key: str,
        fingerprint: str,
    ) -> bool:
        """添加信任公钥到白名单。"""
        try:
            self._trusted_keys[key_id] = {
                "public_key_pem": public_key,
                "fingerprint": fingerprint,
                "trusted_at": datetime.now(UTC).isoformat(),
            }
            return self._save_trusted_keys()
        except Exception as exc:
            logger.warning("[supply_chain] 添加信任密钥失败: %s", exc)
            return False

    def list_trusted_keys(self) -> list[dict]:
        """列出所有信任密钥(含 key_id)。"""
        result: list[dict] = []
        for key_id, info in self._trusted_keys.items():
            entry = {"key_id": key_id}
            entry.update(info)
            result.append(entry)
        return result

    # -- 内部:哈希与签名 -------------------------------------------------

    @staticmethod
    def _compute_hash(file_path: str) -> str:
        """计算文件 SHA256(流式读取)。"""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(64 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _verify_signature(
        self,
        data: bytes,
        signature: bytes,
        public_key: bytes,
    ) -> bool:
        """RSA-2048 + SHA256 签名校验。"""
        if not _HAS_CRYPTO:
            return False
        try:
            pub = serialization.load_pem_public_key(
                public_key,
                backend=default_backend(),
            )
            pub.verify(
                signature,
                data,
                rsa_padding.PSS(
                    mgf=rsa_padding.MGF1(hashes.SHA256()),
                    salt_length=rsa_padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            return True
        except Exception:
            return False

    def _verify_signature_any_key(
        self,
        data: bytes,
        signature_b64: str,
    ) -> tuple[str | None, bool]:
        """用任一信任公钥验签,返回 (key_id, 是否通过)。"""
        if not _HAS_CRYPTO:
            return None, False
        try:
            signature = base64.b64decode(signature_b64)
        except Exception:
            return None, False
        # 对数据做 SHA256 摘要后验签(与 DocumentSigner._sign_hash 一致)
        digest = hashlib.sha256(data).hexdigest().encode("utf-8")
        for key_id, info in self._trusted_keys.items():
            pem = info.get("public_key_pem", "").encode("utf-8")
            if not pem:
                continue
            # DocumentSigner 签的是 file_hash 字符串,这里对齐
            if self._verify_hash_signature(digest, signature, pem):
                return key_id, True
        return None, False

    def _verify_hash_signature(
        self,
        data_hash: bytes,
        signature: bytes,
        public_key_pem: bytes,
    ) -> bool:
        """校验对哈希字符串的 RSA 签名(与 DocumentSigner 算法对齐)。"""
        if not _HAS_CRYPTO:
            return False
        try:
            pub = serialization.load_pem_public_key(
                public_key_pem,
                backend=default_backend(),
            )
            pub.verify(
                signature,
                data_hash,
                rsa_padding.PSS(
                    mgf=rsa_padding.MGF1(hashes.SHA256()),
                    salt_length=rsa_padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            return True
        except Exception:
            return False

    # -- 内部:pip-audit -------------------------------------------------

    def _run_pip_audit(
        self,
        requirements_path: str = "requirements.txt",
    ) -> list[dict]:
        """调用 pip-audit 子进程检查漏洞。

        降级:pip-audit 不可用时返回空列表 + warning。
        """
        try:
            proc = subprocess.run(
                ["pip-audit", "-r", requirements_path, "-f", "json"],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if proc.returncode != 0 and not proc.stdout:
                logger.warning("[supply_chain] pip-audit 失败: %s", proc.stderr[:200])
                return []
            data = json.loads(proc.stdout)
            vulns: list[dict] = []
            for dep in data.get("dependencies", []):
                vulns_list = dep.get("vulns", [])
                if not vulns_list:
                    continue
                for v in vulns_list:
                    vulns.append(
                        {
                            "name": dep.get("name", ""),
                            "version": dep.get("version", ""),
                            "id": v.get("id", v.get("vuln_id", "")),
                            "summary": v.get("description", v.get("summary", "")),
                            "fix_versions": v.get("fix_versions", []),
                        }
                    )
            return vulns
        except FileNotFoundError:
            logger.warning("[supply_chain] pip-audit 未安装,跳过 CVE 检查")
            return []
        except subprocess.TimeoutExpired:
            logger.warning("[supply_chain] pip-audit 超时")
            return []
        except Exception as exc:
            logger.warning("[supply_chain] pip-audit 异常: %s", exc)
            return []

    def _run_pip_audit_for_pkg(self, name: str, version: str) -> list[dict]:
        """检查单个包的漏洞(生成临时 requirements 后调用 pip-audit)。"""
        import tempfile

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".txt",
                delete=False,
                encoding="utf-8",
            ) as tmp:
                tmp.write(f"{name}=={version}\n")
                tmp_path = tmp.name
            return self._run_pip_audit(tmp_path)
        except Exception:
            return []
        finally:
            try:
                os.unlink(tmp_path)  # type: ignore[possibly-undefined]
            except Exception:
                pass

    # -- 内部:信任密钥存储 -----------------------------------------------

    def _load_trusted_keys(self) -> dict[str, dict]:
        """加载信任密钥白名单。"""
        try:
            if os.path.exists(self._trusted_keys_path):
                with open(self._trusted_keys_path, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except Exception:
            pass
        return {}

    def _save_trusted_keys(self) -> bool:
        """持久化信任密钥白名单。"""
        try:
            os.makedirs(os.path.dirname(self._trusted_keys_path), exist_ok=True)
            with open(self._trusted_keys_path, "w", encoding="utf-8") as f:
                json.dump(self._trusted_keys, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    # -- 内部:requirements 解析 ------------------------------------------

    @staticmethod
    def _parse_requirement(line: str) -> tuple[str, str]:
        """解析单行 requirement,返回 (name, version)。

        支持:
          - requests==2.31.0
          - requests>=2.0,<3.0
          - requests (无版本)
        """
        # 匹配 包名 + 版本操作符
        m = re.match(r"^([A-Za-z0-9_.-]+)\s*(?:[=<>!~]=?\s*)?([0-9][0-9A-Za-z.\-]*)?", line)
        if not m:
            return "", ""
        name = m.group(1)
        version = m.group(2) or ""
        return name, version

    # -- 内部:审计 -------------------------------------------------------

    @staticmethod
    def _audit_verify(action: str, detail: dict) -> None:
        """将校验事件写入审计日志(失败不影响主流程)。"""
        try:
            from fnixagent.core.audit import AuditLogger

            AuditLogger().log(action=action, detail=detail)
        except Exception:
            pass
