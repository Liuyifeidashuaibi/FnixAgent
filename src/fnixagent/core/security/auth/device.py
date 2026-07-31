"""
设备指纹(Phase 0.4)。

实现「一设备一令牌」绑定,防止 Refresh Token 在不同设备被复用。

指纹构成:
    device_fp = SHA256(
        client_uuid +             # 客户端生成的 UUID(持久化在 safeStorage)
        user_agent +              # 浏览器/Electron User-Agent
        ip_segment                # IP 段(/24 IPv4 或 /64 IPv6,避免 NAT 漂移)
    )

设计:
    - 客户端首次登录时生成 UUID,持久化到 safeStorage(Electron)
      或 localStorage(Web),后续每次登录都带上同一 UUID
    - 服务端把 device_fp 写入 Access Token,校验时比对
    - IP 段使用 /24(避免移动网络切换 /24 时频繁失效)
"""

from __future__ import annotations

import hashlib
import re

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# UUID v4 正则(简化版,允许大小写)
_UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# IP 段掩码长度
_IPV4_PREFIX_LEN = 24  # /24(256 个 IP)
_IPV6_PREFIX_LEN = 64  # /64


# ---------------------------------------------------------------------------
# IP 段提取(避免 NAT/移动网络漂移)
# ---------------------------------------------------------------------------


def _extract_ip_segment(ip: str) -> str:
    """提取 IP 段(IPv4 取 /24,IPv6 取 /64)。

    Args:
        ip: 客户端 IP 地址

    Returns:
        IP 段字符串(如 "192.168.1.0/24"),无效 IP 返回 "0.0.0.0/0"
    """
    if not ip:
        return "0.0.0.0/0"

    # 处理 IPv4
    if ":" not in ip and ip.count(".") == 3:
        parts = ip.split(".")
        # 取前 3 段作为 /24 段
        return f"{'.'.join(parts[:3])}.0/{_IPV4_PREFIX_LEN}"

    # 处理 IPv6(简化:取前 4 组作为 /64 段)
    if ":" in ip:
        groups = ip.split(":")
        if len(groups) >= 4:
            return f"{':'.join(groups[:4])}::/{_IPV6_PREFIX_LEN}"
        return ip

    # 未知格式
    return "unknown"


# ---------------------------------------------------------------------------
# 指纹计算
# ---------------------------------------------------------------------------


def compute_device_fingerprint(
    client_uuid: str,
    user_agent: str,
    ip_address: str,
) -> str:
    """计算设备指纹。

    Args:
        client_uuid: 客户端生成的 UUID v4
        user_agent:  HTTP User-Agent 头
        ip_address:  客户端 IP 地址

    Returns:
        64 字符十六进制指纹(SHA-256)
    """
    if not client_uuid:
        client_uuid = "unknown"
    if not user_agent:
        user_agent = "unknown"

    ip_segment = _extract_ip_segment(ip_address)

    # 拼接并哈希
    raw = f"{client_uuid}|{user_agent}|{ip_segment}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_device_fingerprint(
    token_fp: str,
    client_uuid: str,
    user_agent: str,
    ip_address: str,
) -> bool:
    """校验 Token 中的设备指纹是否与当前请求匹配。

    Args:
        token_fp:     Token payload 中的 device_fp
        client_uuid:  当前请求的客户端 UUID
        user_agent:   当前请求的 User-Agent
        ip_address:   当前请求的 IP

    Returns:
        是否匹配
    """
    if not token_fp:
        # Token 未绑定设备指纹(向后兼容旧 Token)→ 放行
        return True

    current_fp = compute_device_fingerprint(client_uuid, user_agent, ip_address)
    return _constant_time_compare(token_fp, current_fp)


def is_valid_client_uuid(uuid_str: str) -> bool:
    """校验客户端 UUID 格式是否合法。"""
    if not uuid_str:
        return False
    return bool(_UUID_PATTERN.match(uuid_str))


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _constant_time_compare(a: str, b: str) -> bool:
    """常量时间字符串比较(防侧信道)。"""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0
