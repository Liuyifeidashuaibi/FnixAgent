"""L2 办公生态连接器基类(P2-10)。

设计原则(对应用户偏好:可插拔第三方服务接口):
  - 所有 Connector 是抽象接口,不绑定具体厂商
  - 具体厂商实现(Feishu/WeChatWork/DingTalk/Exchange/Gmail)通过 register_provider 注册
  - 运行时按 config.provider 选择具体实现
  - 默认 StubProvider:本地开发用,返回占位数据,不调用真实 API
  - 全部方法返回 ConnectorResult(成功/数据/错误)

可插拔架构:
  - Provider 注册表为 dict(O(1) 查找),按 provider.name 索引
  - 注册/激活/切换 Provider 全程加锁(_lock),保证并发安全
  - 切换 Provider 时,旧 active_provider 会先调用 close() 释放连接(SMTP/HTTP 会话等),
    避免连接泄漏(修复"Provider 切换时旧连接未关闭"BUG)

StubProvider 降级策略:
  - 每个 Connector 实例化时自动注册 StubProvider(name='stub')
  - config.provider 未配置或对应厂商不可用时,可显式切回 'stub' 实现降级
  - StubProvider.is_available() 恒为 True,保证本地开发零配置可用
  - StubProvider 返回值统一通过 _stub_result() 构造,metadata.stub=True 标记
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import abc
import threading
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 统一返回结构
# ---------------------------------------------------------------------------

@dataclass
class ConnectorResult:
    """Connector 方法统一返回结构。

    Note: 不实现 __bool__,避免与"失败结果作为错误哨兵"的用法冲突
        (历史 BUG: 早期版本实现 __bool__ 后,`if result:` 在失败时也走入成功分支)。
        显式检查用 `result.success` / `result.error`。
    """

    success: bool = True
    data: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

@dataclass
class ConnectorConfig:
    """Connector 配置(厂商无关)。

    Note: api_token/api_secret 为敏感字段,日志/异常中不得直接打印明文。
    """

    provider: str = "stub"  # stub / feishu / wechat_work / dingtalk / exchange / gmail / ...
    api_url: str = ""
    api_token: str = ""  # 敏感:日志脱敏
    api_secret: str = ""  # 敏感:日志脱敏
    user_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

# ---------------------------------------------------------------------------
# 抽象 Provider(具体厂商实现此接口)
# ---------------------------------------------------------------------------

class BaseProvider(abc.ABC):
    """具体厂商 Provider 抽象基类。

    每个 Connector 内部持有一个 Provider 实例处理实际 API 调用。
    Provider 类按 Connector 类型分别定义(如 MailProvider / ScheduleProvider)。

    生命周期:
      - is_available(): 配置/网络/凭据检查(连接前调用)
      - close(): 释放底层资源(SMTP/IMAP 会话、HTTP keep-alive 连接等);
                 默认 no-op,具体 Provider 按需 override
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Provider 标识(如 'feishu'/'gmail')。"""
        ...

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Provider 是否可用(配置/网络/凭据检查)。"""
        ...

    def close(self) -> None:
        """释放底层资源(SMTP/IMAP 会话、HTTP 连接等)。

        默认 no-op。具体 Provider 若持有需显式关闭的资源(如 smtplib.SMTP、
        imaplib.IMAP4、requests.Session),应 override 此方法。
        在 Provider 切换/Connector 断开时由 Connector 调用。
        """
        return None

# ---------------------------------------------------------------------------
# Connector 抽象基类
# ---------------------------------------------------------------------------

class WorkspaceConnector(abc.ABC):
    """办公生态 Connector 抽象基类。

    子类(MailConnector/ScheduleConnector/...)需实现:
      - name 属性:连接器类型名(如 'mail'/'schedule')
      - 业务方法:每个抽象方法对应一项能力

    通用能力:
      - connect()/disconnect()/is_connected():连接生命周期
      - register_provider()/get_provider():Provider 注册与查询

    线程安全:
      - _lock 保护 _connected / _active_provider / _providers / _config
      - connect/disconnect/register_provider/config setter 持锁执行
      - is_connected() 持锁读取,避免并发 disconnect 中途读到中间态
    """

    def __init__(self, config: ConnectorConfig | None = None) -> None:
        self._config = config or ConnectorConfig()
        self._connected = False
        self._providers: dict[str, BaseProvider] = {}
        self._active_provider: BaseProvider | None = None
        # 全局锁:保护连接状态/Provider 注册表的并发访问
        self._lock = threading.Lock()
        # 注册内置 stub provider(降级策略:零配置即可用)
        self._register_default_stub()

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """连接器类型名(如 'mail'/'schedule'/'meeting')。"""
        ...

    # ------------------------------------------------------------------
    # 连接生命周期(connect/disconnect 加锁,避免并发切换)
    # ------------------------------------------------------------------

    def connect(self) -> ConnectorResult:
        """建立连接(选择并初始化 provider)。

        修复 BUG「Provider 切换时旧连接未关闭」:
          若当前已有 active_provider 且与新选定的不同,先调用旧 provider.close()
          释放底层资源(SMTP/IMAP 会话、HTTP keep-alive 连接等),再切换。
        """
        with self._lock:
            provider_name = self._config.provider
            provider = self._providers.get(provider_name)
            if provider is None:
                return ConnectorResult(
                    success=False,
                    error=f"provider '{provider_name}' not registered for {self.name}",
                )
            if not provider.is_available():
                return ConnectorResult(
                    success=False,
                    error=f"provider '{provider_name}' is not available "
                    f"(check config/credentials/network)",
                )
            # 旧 provider 资源释放(若切换到不同 provider)
            old = self._active_provider
            if old is not None and old is not provider:
                try:
                    old.close()
                except Exception:
                    # 关闭旧连接失败不应阻塞新连接建立,忽略
                    pass
            self._active_provider = provider
            self._connected = True
            return ConnectorResult(
                success=True,
                data={"provider": provider_name, "connector": self.name},
            )

    def disconnect(self) -> ConnectorResult:
        """断开连接:释放 active_provider 资源并清空状态。"""
        with self._lock:
            old = self._active_provider
            if old is not None:
                try:
                    old.close()
                except Exception:
                    # 关闭失败不阻塞状态清理
                    pass
            self._active_provider = None
            self._connected = False
            return ConnectorResult(success=True)

    def is_connected(self) -> bool:
        """是否已连接(持锁读取,避免并发 disconnect 中间态)。"""
        with self._lock:
            return self._connected and self._active_provider is not None

    # ------------------------------------------------------------------
    # Provider 管理(注册加锁,O(1) 查找)
    # ------------------------------------------------------------------

    def register_provider(self, provider: BaseProvider) -> ConnectorResult:
        """注册一个具体厂商 Provider(同名覆盖)。

        Returns:
            ConnectorResult(data={registered, replaced})
            replaced 为被覆盖的旧 provider 名(首次注册为 None)
        """
        with self._lock:
            replaced = None
            if provider.name in self._providers:
                replaced = provider.name
            self._providers[provider.name] = provider
            return ConnectorResult(
                success=True,
                data={"registered": provider.name, "replaced": replaced},
            )

    def list_providers(self) -> list[str]:
        """列出所有已注册 provider。"""
        with self._lock:
            return list(self._providers.keys())

    def get_provider(self, name: str | None = None) -> BaseProvider | None:
        """获取指定 provider;None 返回当前 active。"""
        with self._lock:
            if name is None:
                return self._active_provider
            return self._providers.get(name)

    @property
    def config(self) -> ConnectorConfig:
        return self._config

    @config.setter
    def config(self, value: ConnectorConfig) -> None:
        with self._lock:
            self._config = value

    # ------------------------------------------------------------------
    # 内置 stub provider(子类必须实现此方法注册默认 stub)
    # ------------------------------------------------------------------

    def _register_default_stub(self) -> None:
        """注册默认 stub provider。子类必须实现。"""
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _register_default_stub()",
        )

    def _ensure_connected(self) -> ConnectorResult | None:
        """检查连接状态,未连接返回失败 ConnectorResult。

        Returns:
            None 表示已连接;非 None 表示未连接(返回值即错误结果)。
        """
        if not self.is_connected():
            return ConnectorResult(
                success=False,
                error=f"{self.name} connector is not connected, call connect() first",
            )
        return None

    def __repr__(self) -> str:
        # 不打印 token/secret,避免敏感信息泄露到日志
        return f"<{self.__class__.__name__} name={self.name} provider={self._config.provider}>"

# ---------------------------------------------------------------------------
# StubProvider 基类(本地开发默认实现)
# ---------------------------------------------------------------------------

class StubProvider(BaseProvider):
    """默认 stub provider:不调用真实 API,返回占位数据。

    用于:
      - 本地开发/测试
      - 未配置真实厂商时的降级
      - 接口演示

    返回值一致性约定(BUG 修复):
      - 所有方法均返回 ConnectorResult,success=True,metadata.stub=True
      - 列表类方法(list/search/list_*)空结果时返回 data=[],不返回 None
      - 占位 ID 形如 'stub-xxx-<generated>',避免与真实 ID 冲突
      - 子类(StubMailProvider 等)应通过 _stub_result() 构造返回值,保证一致性
    """

    @property
    def name(self) -> str:
        return "stub"

    def is_available(self) -> bool:
        # StubProvider 恒可用:保证本地开发零配置降级
        return True

    def _stub_result(self, data: Any = None, **metadata: Any) -> ConnectorResult:
        """构造 stub 返回结果(metadata 标注 stub=true)。

        所有 Stub 子类应统一使用此方法构造返回值,保证:
          - success 恒为 True
          - metadata.stub 恒为 True
          - 列表空结果传 data=[] 而非 None
        """
        meta = {"stub": True}
        meta.update(metadata)
        return ConnectorResult(success=True, data=data, metadata=meta)
