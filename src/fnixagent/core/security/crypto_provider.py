"""
国密双栈密码学提供者 (CryptoProvider) - P2 安全模块。

参考 GmSSL + pyca/cryptography 双栈设计,实现国密 / 国际算法的运行时切换。

设计要点:
  - 抽象 CryptoProvider 接口,支持运行时切换国密(SM2/SM3/SM4)与国际(RSA/SHA256/AES)
  - 国密实现优先用 gmssl 库,缺失时降级到纯 Python 实现(SM3/SM4 纯 Python,SM2 用
    cryptography 的 EC 曲线 prime256v1 近似,标记 approximate=True)
  - 默认国内场景使用国密,跨境场景使用国际算法
  - 所有签名验证用常量时间比较(hmac.compare_digest)
  - 支持 hash/sign/verify/encrypt/decrypt/key_agree 五类操作

算法标准:
  - SM3: GB/T 32905-2016(256 位哈希,64 字节块,32 字节输出)
  - SM4: GB/T 32907-2016(128 位分组密码,CBC/GCM 模式)
  - SM2: GB/T 32950-2016(椭圆曲线,本模块用 prime256v1 近似)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import struct
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)
_logger = logger

# 可选依赖:gmssl(国密原生实现)
try:
    from gmssl import sm2, sm3, sm4  # noqa: F401  # type: ignore

    _HAS_GMSSL = True
except ImportError:  # pragma: no cover
    _HAS_GMSSL = False

# 可选依赖:cryptography(国际栈 + SM2 近似)
try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa
    from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    _HAS_CRYPTO = True
except ImportError:  # pragma: no cover
    _HAS_CRYPTO = False

# ---------------------------------------------------------------------------
# 审计钩子(失败不影响主流程)
# ---------------------------------------------------------------------------


def _audit_crypto(action: str, detail: dict | None = None) -> None:
    """将密码学操作写入审计日志(仅记录元信息,不记录密钥/明文)。"""
    try:
        from fnixagent.core.audit import AuditLogger

        AuditLogger().log(action=action, detail=detail or {})
    except Exception:
        _logger.debug('Unhandled exception', exc_info=True)


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


class AlgorithmSuite(Enum):
    """算法栈枚举。"""

    SM = "sm"  # 国密栈(SM2/SM3/SM4)
    INTERNATIONAL = "intl"  # 国际栈(RSA/SHA256/AES)


@dataclass
class CryptoConfig:
    """密码学配置。

    Attributes:
        suite: 算法栈(默认国密)
        sm_crypto: 是否启用国密
        fallback_to_intl: 国密不可用时是否降级到国际算法
    """

    suite: AlgorithmSuite = AlgorithmSuite.SM
    sm_crypto: bool = True
    fallback_to_intl: bool = True


# ---------------------------------------------------------------------------
# SM3 纯 Python 实现(GB/T 32905-2016)
# ---------------------------------------------------------------------------

# SM3 初始值 IV
_SM3_IV = (
    0x7380166F,
    0x4914B2B9,
    0x172442D7,
    0xDA8A0600,
    0xA96F30BC,
    0x163138AA,
    0xE38DEE4D,
    0xB0FB0E4E,
)

# SM3 常量 T_j
_SM3_T = tuple((0x79CC4519 if j < 16 else 0x7A879D8A) for j in range(64))


def _sm3_rotl(x: int, n: int) -> int:
    """32 位循环左移。"""
    n &= 31
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _sm3_ff(j: int, x: int, y: int, z: int) -> int:
    """布尔函数 FF_j。"""
    if j < 16:
        return x ^ y ^ z
    return (x & y) | (x & z) | (y & z)


def _sm3_gg(j: int, x: int, y: int, z: int) -> int:
    """布尔函数 GG_j。"""
    if j < 16:
        return x ^ y ^ z
    return (x & y) | ((~x & 0xFFFFFFFF) & z)


def _sm3_p0(x: int) -> int:
    """置换函数 P_0。"""
    return x ^ _sm3_rotl(x, 9) ^ _sm3_rotl(x, 17)


def _sm3_p1(x: int) -> int:
    """置换函数 P_1。"""
    return x ^ _sm3_rotl(x, 15) ^ _sm3_rotl(x, 23)


def _sm3_pad(msg: bytes) -> bytes:
    """SM3 消息填充(类似 SHA-256,但长度域为 64 位大端)。"""
    length = len(msg)
    # 填充 1 bit + 0 bits
    padded = msg + b"\x80"
    # 填充至 56 mod 64
    while len(padded) % 64 != 56:
        padded += b"\x00"
    # 64 位大端长度(bit 长度)
    padded += struct.pack(">Q", length * 8)
    return padded


def _sm3_compress(v: list, w: list) -> list:
    """SM3 压缩函数(单块)。"""
    # 扩展 W'[0..63]
    w1 = [w[j] ^ w[j + 4] for j in range(64)]

    a, b, c, d, e, f, g, h = v
    for j in range(64):
        ss1 = _sm3_rotl(
            (_sm3_rotl(a, 12) + e + _sm3_rotl(_SM3_T[j], j % 32)) & 0xFFFFFFFF,
            7,
        )
        ss2 = ss1 ^ _sm3_rotl(a, 12)
        tt1 = (_sm3_ff(j, a, b, c) + d + ss2 + w1[j]) & 0xFFFFFFFF
        tt2 = (_sm3_gg(j, e, f, g) + h + ss1 + w[j]) & 0xFFFFFFFF
        d = c
        c = _sm3_rotl(b, 9)
        b = a
        a = tt1
        h = g
        g = _sm3_rotl(f, 19)
        f = e
        e = _sm3_p0(tt2)
    return [a, b, c, d, e, f, g, h]


def sm3_hash(data: bytes) -> bytes:
    """SM3 哈希(纯 Python 实现,GB/T 32905-2016)。

    Args:
        data: 原始数据

    Returns:
        32 字节哈希值
    """
    padded = _sm3_pad(data)
    v = list(_SM3_IV)
    # 逐块处理:V_(i+1) = ABCDEFGH(compress 输出) ^ V_i
    for i in range(0, len(padded), 64):
        block = padded[i : i + 64]
        # 消息扩展 W[0..67]
        w = list(struct.unpack(">16I", block))
        for j in range(16, 68):
            w.append(
                _sm3_p1(w[j - 16] ^ w[j - 9] ^ _sm3_rotl(w[j - 3], 15))
                ^ _sm3_rotl(w[j - 13], 7)
                ^ w[j - 6]
            )
        # 压缩函数返回新的 ABCDEFGH,V_(i+1) = new_v ^ V_i
        new_v = _sm3_compress(v, w)
        v = [(v[k] ^ new_v[k]) for k in range(8)]
    return struct.pack(">8I", *v)


# ---------------------------------------------------------------------------
# SM4 纯 Python 实现(GB/T 32907-2016)
# ---------------------------------------------------------------------------

# SM4 S 盒
_SM4_SBOX = (
    0xD6,
    0x90,
    0xE9,
    0xFE,
    0xCC,
    0xE1,
    0x3D,
    0xB7,
    0x16,
    0xB6,
    0x14,
    0xC2,
    0x28,
    0xFB,
    0x2C,
    0x05,
    0x2B,
    0x67,
    0x9A,
    0x76,
    0x2A,
    0xBE,
    0x04,
    0xC3,
    0xAA,
    0x44,
    0x13,
    0x26,
    0x49,
    0x86,
    0x06,
    0x99,
    0x9C,
    0x42,
    0x50,
    0xF4,
    0x91,
    0xEF,
    0x98,
    0x7A,
    0x33,
    0x54,
    0x0B,
    0x43,
    0xED,
    0xCF,
    0xAC,
    0x62,
    0xE4,
    0xB3,
    0x1C,
    0xA9,
    0xC9,
    0x08,
    0xE8,
    0x95,
    0x80,
    0xDF,
    0x94,
    0xFA,
    0x75,
    0x8F,
    0x3F,
    0xA6,
    0x47,
    0x07,
    0xA7,
    0xFC,
    0xF3,
    0x73,
    0x17,
    0xBA,
    0x83,
    0x59,
    0x3C,
    0x19,
    0xE6,
    0x85,
    0x4F,
    0xA8,
    0x68,
    0x6B,
    0x81,
    0xB2,
    0x71,
    0x64,
    0xDA,
    0x8B,
    0xF8,
    0xEB,
    0x0F,
    0x4B,
    0x70,
    0x56,
    0x9D,
    0x35,
    0x1E,
    0x24,
    0x0E,
    0x5E,
    0x63,
    0x58,
    0xD1,
    0xA2,
    0x25,
    0x22,
    0x7C,
    0x3B,
    0x01,
    0x21,
    0x78,
    0x87,
    0xD4,
    0x00,
    0x46,
    0x57,
    0x9F,
    0xD3,
    0x27,
    0x52,
    0x4C,
    0x36,
    0x02,
    0xE7,
    0xA0,
    0xC4,
    0xC8,
    0x9E,
    0xEA,
    0xBF,
    0x8A,
    0xD2,
    0x40,
    0xC7,
    0x38,
    0xB5,
    0xA3,
    0xF7,
    0xF2,
    0xCE,
    0xF9,
    0x61,
    0x15,
    0xA1,
    0xE0,
    0xAE,
    0x5D,
    0xA4,
    0x9B,
    0x34,
    0x1A,
    0x55,
    0xAD,
    0x93,
    0x32,
    0x30,
    0xF5,
    0x8C,
    0xB1,
    0xE3,
    0x1D,
    0xF6,
    0xE2,
    0x2E,
    0x82,
    0x66,
    0xCA,
    0x60,
    0xC0,
    0x29,
    0x23,
    0xAB,
    0x0D,
    0x53,
    0x4E,
    0x6F,
    0xD5,
    0xDB,
    0x37,
    0x45,
    0xDE,
    0xFD,
    0x8E,
    0x2F,
    0x03,
    0xFF,
    0x6A,
    0x72,
    0x6D,
    0x6C,
    0x5B,
    0x51,
    0x8D,
    0x1B,
    0xAF,
    0x92,
    0xBB,
    0xDD,
    0xBC,
    0x7F,
    0x11,
    0xD9,
    0x5C,
    0x41,
    0x1F,
    0x10,
    0x5A,
    0xD8,
    0x0A,
    0xC1,
    0x31,
    0x88,
    0xA5,
    0xCD,
    0x7B,
    0xBD,
    0x2D,
    0x74,
    0xD0,
    0x12,
    0xB8,
    0xE5,
    0xB4,
    0xB0,
    0x89,
    0x69,
    0x97,
    0x4A,
    0x0C,
    0x96,
    0x77,
    0x7E,
    0x65,
    0xB9,
    0xF1,
    0x09,
    0xC5,
    0x6E,
    0xC6,
    0x84,
    0x18,
    0xF0,
    0x7D,
    0xEC,
    0x3A,
    0xDC,
    0x4D,
    0x20,
    0x79,
    0xEE,
    0x5F,
    0x3E,
    0xD7,
    0xCB,
    0x39,
    0x48,
)

# SM4 系统参数 FK
_SM4_FK = (0xA3B1BAC6, 0x56AA3350, 0x677D9197, 0xB27022DC)

# SM4 固定参数 CK:ck[i,j] = (4i+j) * 7 mod 256
_SM4_CK = tuple(
    (
        ((4 * i + 0) * 7 % 256) << 24
        | ((4 * i + 1) * 7 % 256) << 16
        | ((4 * i + 2) * 7 % 256) << 8
        | ((4 * i + 3) * 7 % 256)
    )
    & 0xFFFFFFFF
    for i in range(32)
)


def _sm4_tau(a: int) -> int:
    """SM4 非线性变换 τ(4 字节并行 S 盒替换)。"""
    return (
        (_SM4_SBOX[(a >> 24) & 0xFF] << 24)
        | (_SM4_SBOX[(a >> 16) & 0xFF] << 16)
        | (_SM4_SBOX[(a >> 8) & 0xFF] << 8)
        | _SM4_SBOX[a & 0xFF]
    )


def _sm4_t(x: int) -> int:
    """SM4 合成置换 T = L(τ(X))。"""
    b = _sm4_tau(x)
    # 线性变换 L: B ^ (B<<<2) ^ (B<<<10) ^ (B<<<18) ^ (B<<<24)
    return (
        b
        ^ ((b << 2) | (b >> 30)) & 0xFFFFFFFF
        ^ ((b << 10) | (b >> 22)) & 0xFFFFFFFF
        ^ ((b << 18) | (b >> 14)) & 0xFFFFFFFF
        ^ ((b << 24) | (b >> 8)) & 0xFFFFFFFF
    ) & 0xFFFFFFFF


def _sm4_t_prime(x: int) -> int:
    """SM4 合成置换 T'(密钥扩展用)= L'(τ(X))。"""
    b = _sm4_tau(x)
    # 线性变换 L': B ^ (B<<<13) ^ (B<<<23)
    return (
        b ^ ((b << 13) | (b >> 19)) & 0xFFFFFFFF ^ ((b << 23) | (b >> 9)) & 0xFFFFFFFF
    ) & 0xFFFFFFFF


def _sm4_rotl32(x: int, n: int) -> int:
    """32 位循环左移。"""
    n &= 31
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _sm4_key_expand(key: bytes) -> list:
    """SM4 密钥扩展,返回 32 个轮密钥。

    K[i+4] = K[i] ^ T'(K[i+1] ^ K[i+2] ^ K[i+3] ^ CK[i])
    rk[i] = K[i+4]
    """
    mk = struct.unpack(">4I", key)
    k = [mk[i] ^ _SM4_FK[i] for i in range(4)]
    rk = []
    for i in range(32):
        # T' 已包含 L' 变换,无需额外旋转
        new_k = k[i] ^ _sm4_t_prime(k[i + 1] ^ k[i + 2] ^ k[i + 3] ^ _SM4_CK[i])
        k.append(new_k)
        rk.append(new_k)
    return rk


def _sm4_crypt_block(block: bytes, rk: list, decrypt: bool = False) -> bytes:
    """SM4 单块加密/解密(16 字节)。"""
    x = list(struct.unpack(">4I", block))
    rounds = rk if not decrypt else list(reversed(rk))
    for i in range(32):
        tmp = x[i] ^ _sm4_t(x[i + 1] ^ x[i + 2] ^ x[i + 3] ^ rounds[i])
        x.append(tmp)
    # 反序变换 R
    return struct.pack(">4I", x[35], x[34], x[33], x[32])


def _sm4_pkcs7_pad(data: bytes) -> bytes:
    """PKCS#7 填充到 16 字节倍数。"""
    pad_len = 16 - (len(data) % 16)
    return data + bytes([pad_len] * pad_len)


def _sm4_pkcs7_unpad(data: bytes) -> bytes:
    """PKCS#7 去填充。"""
    if not data or len(data) % 16 != 0:
        raise ValueError("无效的填充数据")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 16:
        raise ValueError("无效的填充长度")
    return data[:-pad_len]


def sm4_cbc_encrypt(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    """SM4-CBC 加密(纯 Python 实现)。

    Args:
        plaintext: 明文
        key: 16 字节密钥
        iv: 16 字节 IV

    Returns:
        密文(含 PKCS#7 填充)
    """
    if len(key) != 16 or len(iv) != 16:
        raise ValueError("SM4 密钥和 IV 必须为 16 字节")
    rk = _sm4_key_expand(key)
    padded = _sm4_pkcs7_pad(plaintext)
    ciphertext = b""
    prev = iv
    for i in range(0, len(padded), 16):
        block = padded[i : i + 16]
        # XOR with previous ciphertext block (or IV)
        xored = bytes(a ^ b for a, b in zip(block, prev))
        encrypted = _sm4_crypt_block(xored, rk, decrypt=False)
        ciphertext += encrypted
        prev = encrypted
    return ciphertext


def sm4_cbc_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    """SM4-CBC 解密(纯 Python 实现)。"""
    if len(key) != 16 or len(iv) != 16:
        raise ValueError("SM4 密钥和 IV 必须为 16 字节")
    if len(ciphertext) % 16 != 0:
        raise ValueError("密文长度必须是 16 的倍数")
    rk = _sm4_key_expand(key)
    plaintext = b""
    prev = iv
    for i in range(0, len(ciphertext), 16):
        block = ciphertext[i : i + 16]
        decrypted = _sm4_crypt_block(block, rk, decrypt=True)
        plaintext += bytes(a ^ b for a, b in zip(decrypted, prev))
        prev = block
    return _sm4_pkcs7_unpad(plaintext)


def sm3_hmac(key: bytes, data: bytes) -> bytes:
    """HMAC-SM3(基于纯 Python SM3,参考 RFC 2104)。"""
    block_size = 64  # SM3 块大小
    if len(key) > block_size:
        key = sm3_hash(key)
    if len(key) < block_size:
        key = key + b"\x00" * (block_size - len(key))
    o_key_pad = bytes(k ^ 0x5C for k in key)
    i_key_pad = bytes(k ^ 0x36 for k in key)
    return sm3_hash(o_key_pad + sm3_hash(i_key_pad + data))


# ---------------------------------------------------------------------------
# CryptoProvider
# ---------------------------------------------------------------------------


class CryptoProvider:
    """统一密码学接口(双栈)。

    用法:
        provider = CryptoProvider()  # 默认国密
        h = provider.hash(b"data")  # SM3
        sig = provider.sign(data, priv_key)
        ok = provider.verify(data, sig, pub_key)
        # 切换到国际栈
        provider = CryptoProvider(CryptoConfig(suite=AlgorithmSuite.INTERNATIONAL))
    """

    # SM2 近似标记(用 prime256v1 替代 sm2p256v1)
    _SM2_APPROXIMATE = True
    _SM2_CURVE = "prime256v1"

    def __init__(self, config: CryptoConfig | None = None) -> None:
        self.config = config or CryptoConfig()
        # 检测国密可用性
        self._sm_available = self._check_sm_availability()
        if not self._sm_available and self.config.fallback_to_intl:
            logger.warning("[crypto] 国密栈不可用(gmssl 缺失且纯 Python 降级受限),切换到国际算法栈")
            self.config.suite = AlgorithmSuite.INTERNATIONAL
            self.config.sm_crypto = False
        # 缓存密钥对(内部使用)
        self._key_cache: dict[str, tuple] = {}

    # -- 公开接口 ----------------------------------------------------------

    def hash(self, data: bytes) -> bytes:
        """计算哈希(SM3 或 SHA256)。"""
        try:
            if self._use_sm():
                if _HAS_GMSSL:
                    # gmssl 的 sm3_hash 接受整数列表,非 bytes
                    return bytes.fromhex(sm3.sm3_hash(list(data)))
                return sm3_hash(data)
            return hashlib.sha256(data).digest()
        except Exception as exc:
            logger.error("[crypto] hash 失败: %s", exc)
            # 降级到 SHA256
            return hashlib.sha256(data).digest()

    def hmac_hash(self, key: bytes, data: bytes) -> bytes:
        """计算 HMAC(SM3-HMAC 或 HMAC-SHA256)。"""
        try:
            if self._use_sm():
                if _HAS_GMSSL:
                    # gmssl 的 sm3 hmac 接口可能不同,用纯 Python 实现
                    return sm3_hmac(key, data)
                return sm3_hmac(key, data)
            return hmac.new(key, data, hashlib.sha256).digest()
        except Exception as exc:
            logger.error("[crypto] hmac 失败: %s", exc)
            return hmac.new(key, data, hashlib.sha256).digest()

    def sign(self, data: bytes, private_key: bytes) -> bytes:
        """对数据签名(SM2 或 RSA-2048-SHA256)。

        Args:
            data: 待签名数据
            private_key: 私钥(PEM 格式,或国密原始字节)

        Returns:
            签名字节
        """
        try:
            if self._use_sm():
                return self._sign_sm2(data, private_key)
            return self._sign_rsa(data, private_key)
        except Exception as exc:
            logger.error("[crypto] sign 失败: %s", exc)
            raise

    def verify(self, data: bytes, signature: bytes, public_key: bytes) -> bool:
        """验证签名(常量时间比较)。

        Args:
            data: 原始数据
            signature: 签名
            public_key: 公钥(PEM 格式,或国密原始字节)

        Returns:
            True 验证通过;False 验证失败
        """
        try:
            if self._use_sm():
                # SM2 验签:用 EC 公钥验证(常量时间比较)
                return self._verify_sm2(data, signature, public_key)
            return self._verify_rsa(data, signature, public_key)
        except Exception as exc:
            logger.warning("[crypto] verify 失败: %s", exc)
            _audit_crypto(
                "crypto.verify_failed",
                detail={
                    "suite": self.get_suite_name(),
                    "reason": type(exc).__name__,
                },
            )
            return False

    def encrypt(self, plaintext: bytes, key: bytes) -> bytes:
        """对称加密(SM4-CBC 或 AES-256-GCM)。

        Args:
            plaintext: 明文
            key: 密钥(SM4 为 16 字节,AES 为 32 字节)

        Returns:
            密文(格式:IV(12/16 字节) + ciphertext)
        """
        try:
            if self._use_sm():
                return self._encrypt_sm4(plaintext, key)
            return self._encrypt_aes_gcm(plaintext, key)
        except Exception as exc:
            logger.error("[crypto] encrypt 失败: %s", exc)
            raise

    def decrypt(self, ciphertext: bytes, key: bytes) -> bytes:
        """对称解密(SM4-CBC 或 AES-256-GCM)。"""
        try:
            if self._use_sm():
                return self._decrypt_sm4(ciphertext, key)
            return self._decrypt_aes_gcm(ciphertext, key)
        except Exception as exc:
            logger.error("[crypto] decrypt 失败: %s", exc)
            raise

    def generate_keypair(self) -> tuple[bytes, bytes]:
        """生成密钥对。

        Returns:
            (private_key, public_key),均为 PEM 格式字节
        """
        try:
            if self._use_sm() and _HAS_CRYPTO:
                # SM2 近似:用 EC prime256v1
                return self._generate_ec_keypair()
            if _HAS_CRYPTO:
                return self._generate_rsa_keypair()
            # 无 cryptography:返回随机字节占位(仅开发环境)
            priv = os.urandom(32)
            pub = os.urandom(32)
            logger.warning("[crypto] cryptography 不可用,返回随机占位密钥(仅开发环境)")
            return priv, pub
        except Exception as exc:
            logger.error("[crypto] generate_keypair 失败: %s", exc)
            raise

    def key_agree(self, private_key: bytes, peer_public_key: bytes) -> bytes:
        """密钥协商(ECDH,SM2 近似用 prime256v1)。"""
        if not _HAS_CRYPTO:
            raise RuntimeError("cryptography 库不可用,无法执行密钥协商")
        try:
            priv = serialization.load_pem_private_key(
                private_key, password=None, backend=default_backend()
            )
            peer_pub = serialization.load_pem_public_key(peer_public_key, backend=default_backend())
            shared_key = priv.exchange(ec.ECDH(), peer_pub)
            return shared_key
        except Exception as exc:
            logger.error("[crypto] key_agree 失败: %s", exc)
            raise

    def get_suite_name(self) -> str:
        """返回当前算法栈名称。"""
        if self._use_sm():
            if _HAS_GMSSL:
                return "SM(gmssl)"
            return "SM(pure-python)"
        return "INTERNATIONAL"

    # -- 内部:算法栈选择 --------------------------------------------------

    def _use_sm(self) -> bool:
        """判断是否使用国密栈。"""
        return (
            self.config.sm_crypto and self.config.suite == AlgorithmSuite.SM and self._sm_available
        )

    def _check_sm_availability(self) -> bool:
        """检测国密栈是否可用。"""
        # SM3/SM4 有纯 Python 实现,始终可用
        # SM2 需要 cryptography 的 EC 支持(近似)
        if not self.config.sm_crypto:
            return False
        if _HAS_GMSSL:
            return True
        # 纯 Python:SM3/SM4 可用,SM2 需 cryptography
        return True  # SM3/SM4 可用,SM2 在使用时降级

    # -- 内部:SM2 实现(近似)---------------------------------------------

    def _sign_sm2(self, data: bytes, key: bytes) -> bytes:
        """SM2 签名(近似:用 EC prime256v1 替代 sm2p256v1)。

        由于 cryptography 原生不支持 SM2/SM3,使用 EC prime256v1 + SHA256 近似。
        标记 approximate=True。

        Args:
            data: 待签名数据
            key: 私钥(PEM 格式)

        Returns:
            签名字节(DER 编码)
        """
        if not _HAS_CRYPTO:
            # 无 cryptography:用 HMAC-SM3 降级(仅开发环境)
            logger.warning("[crypto] SM2 不可用,用 HMAC-SM3 降级签名")
            return sm3_hmac(key, data)

        # 近似:用 EC prime256v1 + SHA256(cryptography 不支持自定义哈希)
        priv = serialization.load_pem_private_key(key, password=None, backend=default_backend())
        # 对数据先做 SM3 哈希,再用 EC-SHA256 签名(双层近似)
        data_hash = self.hash(data)
        signature = priv.sign(
            data_hash,
            ec.ECDSA(hashes.SHA256()),
        )
        return signature

    def _verify_sm2(self, data: bytes, signature: bytes, public_key: bytes) -> bool:
        """SM2 验签(近似:用 EC prime256v1)。"""
        if not _HAS_CRYPTO:
            # 降级:HMAC 比对(常量时间)
            if not isinstance(public_key, bytes):
                return False
            expected = sm3_hmac(public_key, data)
            return hmac.compare_digest(expected, signature)

        pub = serialization.load_pem_public_key(public_key, backend=default_backend())
        data_hash = self.hash(data)
        try:
            pub.verify(signature, data_hash, ec.ECDSA(hashes.SHA256()))
            return True
        except Exception:
            return False

    def _generate_ec_keypair(self) -> tuple[bytes, bytes]:
        """生成 EC 密钥对(prime256v1,SM2 近似)。"""
        priv = ec.generate_private_key(ec.SECP256R1(), backend=default_backend())
        priv_pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pub_pem = priv.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return priv_pem, pub_pem

    # -- 内部:RSA 实现 ----------------------------------------------------

    def _sign_rsa(self, data: bytes, private_key: bytes) -> bytes:
        """RSA-2048-SHA256 签名。"""
        if not _HAS_CRYPTO:
            # 降级:HMAC-SHA256
            return hmac.new(private_key, data, hashlib.sha256).digest()
        priv = serialization.load_pem_private_key(
            private_key, password=None, backend=default_backend()
        )
        signature = priv.sign(
            data,
            rsa_padding.PSS(
                mgf=rsa_padding.MGF1(hashes.SHA256()),
                salt_length=rsa_padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return signature

    def _verify_rsa(self, data: bytes, signature: bytes, public_key: bytes) -> bool:
        """RSA-2048-SHA256 验签。"""
        if not _HAS_CRYPTO:
            # 降级:HMAC 比对(常量时间)
            if not isinstance(public_key, bytes):
                return False
            expected = hmac.new(public_key, data, hashlib.sha256).digest()
            return hmac.compare_digest(expected, signature)
        pub = serialization.load_pem_public_key(public_key, backend=default_backend())
        try:
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

    def _generate_rsa_keypair(self) -> tuple[bytes, bytes]:
        """生成 RSA-2048 密钥对。"""
        priv = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )
        priv_pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pub_pem = priv.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return priv_pem, pub_pem

    # -- 内部:SM4 加解密 --------------------------------------------------

    def _encrypt_sm4(self, plaintext: bytes, key: bytes) -> bytes:
        """SM4-CBC 加密。

        返回格式:IV(16 字节) + ciphertext
        """
        if len(key) != 16:
            # 密钥长度不是 16 字节,用 SM3 派生
            key = self.hash(key)[:16]
        iv = os.urandom(16)
        if _HAS_GMSSL:
            try:
                crypt = sm4.CryptSM4()
                crypt.set_key(key, sm4.SM4_ENCRYPT)
                ciphertext = crypt.crypt_cbc(iv, plaintext)
                return iv + ciphertext
            except Exception as exc:
                logger.warning("[crypto] gmssl SM4 加密失败,降级到纯 Python: %s", exc)
        ciphertext = sm4_cbc_encrypt(plaintext, key, iv)
        return iv + ciphertext

    def _decrypt_sm4(self, ciphertext: bytes, key: bytes) -> bytes:
        """SM4-CBC 解密。

        输入格式:IV(16 字节) + ciphertext
        """
        if len(key) != 16:
            key = self.hash(key)[:16]
        if len(ciphertext) < 16:
            raise ValueError("密文过短(需包含 16 字节 IV)")
        iv = ciphertext[:16]
        ct = ciphertext[16:]
        if _HAS_GMSSL:
            try:
                crypt = sm4.CryptSM4()
                crypt.set_key(key, sm4.SM4_DECRYPT)
                plaintext = crypt.crypt_cbc(iv, ct)
                return plaintext
            except Exception as exc:
                logger.warning("[crypto] gmssl SM4 解密失败,降级到纯 Python: %s", exc)
        return sm4_cbc_decrypt(ct, key, iv)

    # -- 内部:AES-GCM 加解密 ---------------------------------------------

    def _encrypt_aes_gcm(self, plaintext: bytes, key: bytes) -> bytes:
        """AES-256-GCM 加密。

        返回格式:nonce(12 字节) + tag(16 字节) + ciphertext
        """
        if not _HAS_CRYPTO:
            raise RuntimeError("cryptography 库不可用,无法执行 AES 加密")
        if len(key) != 32:
            key = hashlib.sha256(key).digest()
        nonce = os.urandom(12)
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce), backend=default_backend())
        encryptor = cipher.encryptor()
        ct = encryptor.update(plaintext) + encryptor.finalize()
        return nonce + encryptor.tag + ct

    def _decrypt_aes_gcm(self, data: bytes, key: bytes) -> bytes:
        """AES-256-GCM 解密。

        输入格式:nonce(12 字节) + tag(16 字节) + ciphertext
        """
        if not _HAS_CRYPTO:
            raise RuntimeError("cryptography 库不可用,无法执行 AES 解密")
        if len(key) != 32:
            key = hashlib.sha256(key).digest()
        if len(data) < 28:
            raise ValueError("密文过短(需包含 nonce + tag)")
        nonce = data[:12]
        tag = data[12:28]
        ct = data[28:]
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag), backend=default_backend())
        decryptor = cipher.decryptor()
        return decryptor.update(ct) + decryptor.finalize()


# ---------------------------------------------------------------------------
# 全局单例(懒加载)
# ---------------------------------------------------------------------------

_provider_instance: CryptoProvider | None = None
_provider_lock = None


def _get_lock():
    """延迟导入 threading.Lock(避免模块加载时副作用)。"""
    global _provider_lock
    if _provider_lock is None:
        import threading

        _provider_lock = threading.Lock()
    return _provider_lock


def get_crypto_provider(config: CryptoConfig | None = None) -> CryptoProvider:
    """获取全局 CryptoProvider 单例。

    Args:
        config: 可选配置(仅首次调用生效)

    Returns:
        CryptoProvider 实例
    """
    global _provider_instance
    if _provider_instance is None:
        with _get_lock():
            if _provider_instance is None:
                _provider_instance = CryptoProvider(config)
    return _provider_instance


def reset_crypto_provider() -> None:
    """重置单例(主要用于测试)。"""
    global _provider_instance
    with _get_lock():
        _provider_instance = None
