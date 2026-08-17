"""
数据脱敏 (Desensitizer)。

对文本中的敏感个人信息做掩码处理:
  - 手机号: 138****5678
  - 邮箱:   a***@example.com
  - 身份证: 110***********1234
  - 银行卡: 6222**********1234
  - IP地址: 192.***.***.1
全部基于正则实现,零依赖。

性能优化: 所有正则在类级预编译一次(模块加载时),避免每次脱敏重复编译。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import re


class Desensitizer:
    """数据脱敏器(PII 掩码)。

    所有正则在类级预编译,实例方法直接使用,无需重复编译。
    """

    # 手机号: 1[3-9] 开头的 11 位数字(前后不能有更多数字)
    _PHONE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")

    # 邮箱: 用户名@域名
    _EMAIL = re.compile(r"([\w.+-]+)(@[\w.-]+\.\w+)")

    # 身份证: 17位数字+校验位(共18位,前3后4保留)
    _ID_CARD = re.compile(r"(?<!\d)(\d{3})\d{11}(\d{3}[\dXx])(?!\d)")

    # 银行卡: 16-19 位连续数字(前4后4保留)
    _BANK_CARD = re.compile(r"(?<!\d)(\d{4})\d{8,12}(\d{4})(?!\d)")

    # IP 地址: 4 段点分十进制(首尾段保留,中间掩码)
    _IP = re.compile(r"(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})")

    # -- 各类型脱敏方法 ----------------------------------------------------

    def mask_phone(self, text: str) -> str:
        """手机号脱敏: 保留前3后4。

        Args:
            text: 原始文本

        Returns:
            脱敏后文本(如 "138****5678")
        """
        return self._PHONE.sub(r"\1****\2", text)

    def mask_email(self, text: str) -> str:
        """邮箱脱敏: 保留首字符和域名。

        Args:
            text: 原始文本

        Returns:
            脱敏后文本(如 "a***@example.com")
        """

        def _replace(m: re.Match) -> str:
            name = m.group(1)
            domain = m.group(2)
            if len(name) <= 1:
                return name + domain
            return name[0] + "*" * (len(name) - 1) + domain

        return self._EMAIL.sub(_replace, text)

    def mask_id_card(self, text: str) -> str:
        """身份证脱敏: 保留前3后4。

        Args:
            text: 原始文本

        Returns:
            脱敏后文本(如 "110***********1234")
        """
        return self._ID_CARD.sub(r"\1***********\2", text)

    def mask_bank_card(self, text: str) -> str:
        """银行卡脱敏: 保留前4后4。

        Args:
            text: 原始文本

        Returns:
            脱敏后文本(如 "6222**********1234")
        """
        return self._BANK_CARD.sub(r"\1**********\2", text)

    def mask_ip(self, text: str) -> str:
        """IP 地址脱敏: 保留首尾段。

        Args:
            text: 原始文本

        Returns:
            脱敏后文本(如 "192.***.***.1")
        """

        def _replace(m: re.Match) -> str:
            return f"{m.group(1)}.***.***.{m.group(4)}"

        return self._IP.sub(_replace, text)

    def mask_all(self, text: str) -> str:
        """一键全部脱敏(手机号/邮箱/身份证/银行卡/IP)。

        Args:
            text: 原始文本

        Returns:
            所有 PII 均脱敏后的文本
        """
        text = self.mask_phone(text)
        text = self.mask_email(text)
        text = self.mask_id_card(text)
        text = self.mask_bank_card(text)
        text = self.mask_ip(text)
        return text
