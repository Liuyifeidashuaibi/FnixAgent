"""
device 模块单元测试(验收标准 ④ 设备指纹不匹配时拒绝 Refresh - 单元层)。

覆盖:
    - compute_device_fingerprint 返回 SHA-256 hex
    - 相同输入产生相同指纹(确定性)
    - 不同 client_uuid 产生不同指纹
    - 不同 user_agent 产生不同指纹
    - 不同 IP 段(/24)产生不同指纹
    - 同 /24 段内不同 IP 产生相同指纹(避免 NAT 漂移)
    - IPv6 取 /64 段
    - 空输入回退到 "unknown"
    - verify_device_fingerprint 匹配/不匹配
    - 旧 Token 无 device_fp 时放行(向后兼容)
    - is_valid_client_uuid 格式校验
"""
import hashlib

import pytest

from fnixagent.core.security.auth.device import (
    _extract_ip_segment,
    compute_device_fingerprint,
    is_valid_client_uuid,
    verify_device_fingerprint,
)


# ---------------------------------------------------------------------------
# IP 段提取
# ---------------------------------------------------------------------------

class TestExtractIpSegment:
    """IP 段提取(避免 NAT/移动网络漂移)。"""

    def test_ipv4_takes_24_segment(self):
        """IPv4 取 /24 段(前三段 + .0)。"""
        seg = _extract_ip_segment("192.168.1.100")
        assert seg == "192.168.1.0/24"

    def test_ipv4_same_24_segment_collapsed(self):
        """同一 /24 段的不同 IP 被归一化。"""
        assert _extract_ip_segment("10.0.0.1") == _extract_ip_segment("10.0.0.254")
        assert _extract_ip_segment("10.0.0.1") == "10.0.0.0/24"

    def test_ipv4_different_24_segment_differs(self):
        """不同 /24 段的 IP 不同。"""
        assert _extract_ip_segment("10.0.0.5") != _extract_ip_segment("10.0.1.5")

    def test_ipv6_takes_64_segment(self):
        """IPv6 取 /64 段(前 4 组)。"""
        seg = _extract_ip_segment("2001:db8:abcd:1234:5678:9abc:def0:1234")
        assert seg == "2001:db8:abcd:1234::/64"

    def test_ipv6_same_64_segment_collapsed(self):
        """同一 /64 段的不同 IPv6 被归一化。"""
        s1 = _extract_ip_segment("2001:db8:abcd:1234::1")
        s2 = _extract_ip_segment("2001:db8:abcd:1234:ffff:ffff:ffff:ffff")
        assert s1 == s2

    def test_empty_ip_returns_zero(self):
        """空 IP 返回 0.0.0.0/0。"""
        assert _extract_ip_segment("") == "0.0.0.0/0"

    def test_unknown_format_returns_unknown(self):
        """未知格式返回 'unknown'。"""
        assert _extract_ip_segment("not_an_ip") == "unknown"


# ---------------------------------------------------------------------------
# 指纹计算
# ---------------------------------------------------------------------------

class TestComputeDeviceFingerprint:
    """设备指纹计算。"""

    def test_returns_sha256_hex(self):
        """返回 64 字符十六进制 SHA-256。"""
        fp = compute_device_fingerprint(
            client_uuid="550e8400-e29b-41d4-a716-446655440000",
            user_agent="Mozilla/5.0",
            ip_address="192.168.1.100",
        )
        assert isinstance(fp, str)
        assert len(fp) == 64
        # 全部是十六进制字符
        assert all(c in "0123456789abcdef" for c in fp)

    def test_deterministic_same_input(self):
        """相同输入产生相同指纹。"""
        kwargs = {
            "client_uuid": "550e8400-e29b-41d4-a716-446655440000",
            "user_agent": "Mozilla/5.0",
            "ip_address": "192.168.1.100",
        }
        assert compute_device_fingerprint(**kwargs) == compute_device_fingerprint(**kwargs)

    def test_different_uuid_produces_different_fp(self):
        """不同 client_uuid 产生不同指纹。"""
        common = {"user_agent": "Mozilla/5.0", "ip_address": "192.168.1.100"}
        fp1 = compute_device_fingerprint("uuid-1", **common)
        fp2 = compute_device_fingerprint("uuid-2", **common)
        assert fp1 != fp2

    def test_different_user_agent_produces_different_fp(self):
        """不同 User-Agent 产生不同指纹。"""
        common = {
            "client_uuid": "550e8400-e29b-41d4-a716-446655440000",
            "ip_address": "192.168.1.100",
        }
        fp1 = compute_device_fingerprint(user_agent="UA1", **common)
        fp2 = compute_device_fingerprint(user_agent="UA2", **common)
        assert fp1 != fp2

    def test_different_ip_segment_produces_different_fp(self):
        """不同 IP 段(/24)产生不同指纹。"""
        common = {
            "client_uuid": "550e8400-e29b-41d4-a716-446655440000",
            "user_agent": "Mozilla/5.0",
        }
        fp1 = compute_device_fingerprint(ip_address="10.0.0.5", **common)
        fp2 = compute_device_fingerprint(ip_address="10.0.1.5", **common)
        assert fp1 != fp2

    def test_same_24_segment_same_fp(self):
        """同一 /24 段的不同 IP 产生相同指纹(NAT 漂移容忍)。"""
        common = {
            "client_uuid": "550e8400-e29b-41d4-a716-446655440000",
            "user_agent": "Mozilla/5.0",
        }
        fp1 = compute_device_fingerprint(ip_address="192.168.1.10", **common)
        fp2 = compute_device_fingerprint(ip_address="192.168.1.200", **common)
        assert fp1 == fp2

    def test_empty_inputs_use_unknown_placeholder(self):
        """空 client_uuid / user_agent 回退到 'unknown'(不报错)。"""
        fp = compute_device_fingerprint("", "", "")
        assert isinstance(fp, str)
        assert len(fp) == 64
        # 与显式 "unknown" 等价
        expected = hashlib.sha256("unknown|unknown|0.0.0.0/0".encode()).hexdigest()
        assert fp == expected


# ---------------------------------------------------------------------------
# 指纹校验
# ---------------------------------------------------------------------------

class TestVerifyDeviceFingerprint:
    """设备指纹校验。"""

    def test_verify_matching_fingerprint(self):
        """Token 中指纹与当前请求一致 → True。"""
        client_uuid = "550e8400-e29b-41d4-a716-446655440000"
        ua = "Mozilla/5.0"
        ip = "192.168.1.50"
        token_fp = compute_device_fingerprint(client_uuid, ua, ip)
        assert verify_device_fingerprint(token_fp, client_uuid, ua, ip) is True

    def test_verify_mismatched_uuid(self):
        """Token 中指纹与当前 client_uuid 不一致 → False(验收标准 ④)。"""
        ua = "Mozilla/5.0"
        ip = "192.168.1.50"
        token_fp = compute_device_fingerprint("uuid-original", ua, ip)
        assert verify_device_fingerprint(token_fp, "uuid-attacker", ua, ip) is False

    def test_verify_mismatched_user_agent(self):
        """User-Agent 变化(不同浏览器) → False。"""
        client_uuid = "550e8400-e29b-41d4-a716-446655440000"
        ip = "192.168.1.50"
        token_fp = compute_device_fingerprint(client_uuid, "Original-UA", ip)
        assert verify_device_fingerprint(token_fp, client_uuid, "Attacker-UA", ip) is False

    def test_verify_mismatched_ip_segment(self):
        """IP 段变化(不同 /24 段) → False。"""
        client_uuid = "550e8400-e29b-41d4-a716-446655440000"
        ua = "Mozilla/5.0"
        token_fp = compute_device_fingerprint(client_uuid, ua, "10.0.0.5")
        assert verify_device_fingerprint(token_fp, client_uuid, ua, "10.0.1.5") is False

    def test_verify_same_24_segment_passes(self):
        """同一 /24 段内 IP 变化(NAT 漂移) → True。"""
        client_uuid = "550e8400-e29b-41d4-a716-446655440000"
        ua = "Mozilla/5.0"
        token_fp = compute_device_fingerprint(client_uuid, ua, "192.168.1.10")
        # 用户在同一局域网内换了 IP(/24 段相同)
        assert verify_device_fingerprint(token_fp, client_uuid, ua, "192.168.1.200") is True

    def test_verify_empty_token_fp_passes_backward_compat(self):
        """Token 无 device_fp 字段(旧 Token)→ True(向后兼容)。"""
        assert verify_device_fingerprint("", "any_uuid", "any_ua", "any_ip") is True
        assert verify_device_fingerprint(None, "any_uuid", "any_ua", "any_ip") is True

    def test_verify_different_length_returns_false(self):
        """长度不同的指纹返回 False(常量时间比较前先判长度)。"""
        assert verify_device_fingerprint("short", "uuid", "ua", "ip") is False


# ---------------------------------------------------------------------------
# UUID 格式校验
# ---------------------------------------------------------------------------

class TestIsValidClientUuid:
    """客户端 UUID 格式校验。"""

    def test_valid_uuid_v4(self):
        """合法 UUID v4 通过。"""
        assert is_valid_client_uuid("550e8400-e29b-41d4-a716-446655440000") is True

    def test_valid_uuid_uppercase(self):
        """大写 UUID 也合法。"""
        assert is_valid_client_uuid("550E8400-E29B-41D4-A716-446655440000") is True

    def test_invalid_uuid_missing_segment(self):
        """缺少一段的 UUID 非法。"""
        assert is_valid_client_uuid("550e8400-e29b-41d4-446655440000") is False

    def test_invalid_uuid_extra_chars(self):
        """含额外字符的 UUID 非法。"""
        assert is_valid_client_uuid("550e8400-e29b-41d4-a716-446655440000X") is False

    def test_empty_uuid_returns_false(self):
        """空字符串非法。"""
        assert is_valid_client_uuid("") is False
        assert is_valid_client_uuid(None) is False

    def test_random_string_returns_false(self):
        """非 UUID 字符串非法。"""
        assert is_valid_client_uuid("not-a-uuid") is False
        assert is_valid_client_uuid("12345") is False
