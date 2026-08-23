"""Harness 本地密钥 — ~/.fnix/secrets.json（CLI 与 Desktop 共享，本机 BYOK）。

密钥保护策略（生产加固）:
    - 文件权限: POSIX 上原子写入后 chmod 0600（仅属主可读写）。
    - Windows DPAPI: 若可用，``llm_api_key`` 以 DPAPI(CryptProtectData,
      用户作用域) 加密后存入 ``llm_api_key_enc``（base64），落盘时不落明文。
      解密失败 / 跨机迁移 / 跨用户场景自动回退到明文键，保证不锁死用户。
    - 兼容旧版本: 读取时优先解密密文，失败回退明文 ``llm_api_key``。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import base64
import json
import os
import stat
from pathlib import Path
from typing import Any

from fnixagent.harness.paths import fnix_home
from fnixagent.harness.workspace import ensure_home_layout

_KEY_PLAIN = "llm_api_key"
_KEY_ENC = "llm_api_key_enc"


# ---------------------------------------------------------------------------
# Windows DPAPI（用户作用域，CryptProtectData / CryptUnprotectData）
# ---------------------------------------------------------------------------


def _dpapi_protect(plaintext: bytes) -> bytes | None:
    """用 Windows DPAPI 加密；非 Windows 或失败返回 None。"""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes.wintypes import DWORD

        class _DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        buf = ctypes.create_string_buffer(plaintext, len(plaintext))
        blob_in = _DATA_BLOB(len(plaintext), buf)
        blob_out = _DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        )
        if not ok:
            return None
        result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return result
    except Exception:
        return None


def _dpapi_unprotect(ciphertext: bytes) -> bytes | None:
    """用 Windows DPAPI 解密；失败返回 None。"""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes.wintypes import DWORD

        class _DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        buf = ctypes.create_string_buffer(ciphertext, len(ciphertext))
        blob_in = _DATA_BLOB(len(ciphertext), buf)
        blob_out = _DATA_BLOB()
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        )
        if not ok:
            return None
        result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return result
    except Exception:
        return None


def _encrypt_key(plain: str) -> str | None:
    """加密 API Key 为 base64 密文；不可用返回 None。"""
    if not plain:
        return None
    protected = _dpapi_protect(plain.encode("utf-8"))
    if protected is None:
        return None
    return base64.b64encode(protected).decode("ascii")


def _decrypt_key(enc_b64: str) -> str | None:
    """解密 base64 密文为明文；失败返回 None。"""
    if not enc_b64:
        return None
    try:
        raw = base64.b64decode(enc_b64.encode("ascii"), validate=True)
    except Exception:
        return None
    plain = _dpapi_unprotect(raw)
    if plain is None:
        return None
    try:
        return plain.decode("utf-8")
    except UnicodeDecodeError:
        return None


# ---------------------------------------------------------------------------
# 读写
# ---------------------------------------------------------------------------


def secrets_path() -> Path:
    return fnix_home() / "secrets.json"


def read_secrets() -> dict[str, Any]:
    ensure_home_layout()
    path = secrets_path()
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_secrets(data: dict[str, Any]) -> None:
    ensure_home_layout()
    path = secrets_path()
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    try:
        if os.name != "nt":
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# LLM API Key（公共 API，向后兼容明文键）
# ---------------------------------------------------------------------------


def get_llm_api_key() -> str:
    """读取 LLM API Key。

    优先解密 DPAPI 密文(llm_api_key_enc)；失败或不存在时回退明文
    (llm_api_key)，保证升级 / 跨机迁移不锁死用户。
    """
    data = read_secrets()

    enc = str(data.get(_KEY_ENC) or "").strip()
    if enc:
        plain = _decrypt_key(enc)
        if plain:
            return plain.strip()

    # 回退:明文键（旧版本 / 非 Windows / DPAPI 解密失败）
    return str(data.get(_KEY_PLAIN) or "").strip()


def set_llm_api_key(api_key: str) -> None:
    """写入 LLM API Key。Windows + DPAPI 可用时仅落盘密文。"""
    data = read_secrets()
    key = (api_key or "").strip()

    if key:
        enc = _encrypt_key(key)
        if enc is not None:
            # 加密可用:只保留密文，删除明文
            data[_KEY_ENC] = enc
            data.pop(_KEY_PLAIN, None)
        else:
            # 无 DPAPI:保留明文键
            data[_KEY_PLAIN] = key
            data.pop(_KEY_ENC, None)
    else:
        # 清空:两个字段都移除
        data.pop(_KEY_PLAIN, None)
        data.pop(_KEY_ENC, None)

    write_secrets(data)


def secrets_status() -> dict[str, Any]:
    key = get_llm_api_key()
    data = read_secrets()
    encrypted = bool(str(data.get(_KEY_ENC) or "").strip())
    return {
        "has_api_key": bool(key),
        "key_hint": _mask_key(key),
        "encrypted_at_rest": encrypted,
    }


def _mask_key(key: str) -> str:
    k = (key or "").strip()
    if not k:
        return ""
    if len(k) <= 8:
        return "****"
    return f"{k[:4]}...{k[-4:]}"
