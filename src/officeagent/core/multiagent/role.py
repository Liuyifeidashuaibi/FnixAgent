"""Role —— Watch-Think-Act 生命周期 Agent 子类 —— P3-4。

借鉴 MetaGPT 的 Role 概念:Agent 在共享环境中按 Watch-Think-Act 生命周期运行。
  - Watch:  监听 MessageBus 上的消息,判断是否关注(基于 cause_by / send_to)
  - Think:  对关注的消息进行推理(复用父类 Agent.think)
  - Act:    执行动作(复用父类 Agent.act)

与 P3-2 RoleConfig 的关系:
  - RoleConfig 是声明(YAML 配置)
  - Role 是实例(Agent 子类,运行时根据 RoleConfig 配置)
  - RoleLoader.load() 返回 RoleConfig;Role.from_config() 工厂创建 Role 实例

设计要点:
  1. Role 继承 Agent,复用 4 步 ReAct(prepare/think/act/reflect)
  2. 增加 watch() 方法:判断是否关注某条消息
  3. watch_actions 列表:Role 关注的 action 名(对应 Msg.cause_by)
  4. subscribe_bus():自动订阅 MessageBus 上的关注 topic
  5. on_message():收到消息时的回调,放入待处理队列

用例:
    role = Role(
        name="researcher",
        watch_actions=["search_paper", "summarize"],
        bus=bus,
    )
    role.subscribe_bus()  # 订阅 action.search_paper 等 topic
    # 当 bus.publish("action.search_paper", msg) 时,role.on_message 被调用
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Optional

from officeagent.core.agent import Agent, AgentContext
from officeagent.core.types_msg import Msg
from officeagent.core.multiagent.messagebus import (
    MessageBus,
    topic_for_action,
)

logger = logging.getLogger(__name__)


class Role(Agent):
    """Watch-Think-Act 生命周期的 Agent 子类。

    在 Agent 基础上增加:
      - watch_actions: 关注的 action 名列表(对应 Msg.cause_by)
      - watch():       判断是否关注某条消息
      - subscribe_bus():订阅 MessageBus
      - on_message():  收到消息的回调

    用法:
        role = Role("researcher", watch_actions=["search"], bus=bus)
        role.subscribe_bus()
        # 当 bus 发布匹配的消息时,role 自动收到
    """

    def __init__(
        self,
        name: str,
        watch_actions: Optional[list[str]] = None,
        bus: Optional[MessageBus] = None,
        **config: Any,
    ) -> None:
        """初始化 Role。

        Args:
            name:           Role 名(与 RoleConfig.name 对应),必须非空
            watch_actions:  关注的 action 名列表;None 表示关注全部
            bus:            MessageBus 实例;None 表示不订阅(手动投递消息)
            **config:       透传给 Agent 基类

        Raises:
            ValueError: name 为空
        """
        # 参数校验:name 必须非空(用于 topic 路由)
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Role name must be a non-empty string")
        super().__init__(name=name, **config)
        # watch_actions 去重 + 去空白(防止配置脏数据)
        self._watch_actions = (
            list(dict.fromkeys(a for a in watch_actions if a))
            if watch_actions else []
        )
        self._bus = bus
        self._sub_ids: list[str] = []
        self._inbox: list[Msg] = []  # 待处理消息队列
        # 并发安全:_inbox 由 MessageBus 回调线程(on_message)和
        # Environment step 线程(pop_message)并发访问,需加锁。
        # _sub_ids 在 subscribe_bus/unsubscribe_bus 间也可能并发,同锁保护。
        # RLock 允许同线程嵌套(inbox_size → 持锁内再调其他持锁方法)。
        self._lock = threading.RLock()

    # -- 属性 --------------------------------------------------------------

    @property
    def watch_actions(self) -> list[str]:
        """关注的 action 名列表。"""
        return list(self._watch_actions)

    @property
    def bus(self) -> Optional[MessageBus]:
        """绑定的 MessageBus。"""
        return self._bus

    @property
    def inbox_size(self) -> int:
        """待处理消息数。"""
        with self._lock:
            return len(self._inbox)

    # -- Watch 阶段 --------------------------------------------------------

    async def watch(self, msg: Msg) -> bool:
        """判断是否关注此消息。

        默认实现:
          - watch_actions 为空 → 关注全部消息
          - msg.cause_by 在 watch_actions 中 → 关注
          - msg.send_to == self.name → 关注(显式定向)
          - 其余 → 不关注

        子类可覆盖实现更复杂的判断(如基于 content 关键词)。

        Args:
            msg: 待判断的消息

        Returns:
            True 表示关注,需进入 think 阶段
        """
        # 显式定向消息
        if msg.send_to and msg.send_to == self._name:
            return True
        # 关注全部
        if not self._watch_actions:
            return True
        # 按 cause_by 匹配
        if msg.cause_by and msg.cause_by in self._watch_actions:
            return True
        return False

    # -- MessageBus 集成 ---------------------------------------------------

    def subscribe_bus(self) -> None:
        """订阅 MessageBus 上的关注 topic。

        若 watch_actions 为空,订阅 "*"（全部）;
        否则订阅每个 action 的 topic（"action.{name}"）。
        """
        if self._bus is None:
            logger.warning("Role '%s': no bus to subscribe", self._name)
            return

        if not self._watch_actions:
            # 订阅全部
            sub_id = self._bus.subscribe("*", self.on_message)
            self._sub_ids.append(sub_id)
        else:
            for action_name in self._watch_actions:
                topic = topic_for_action(action_name)
                sub_id = self._bus.subscribe(topic, self.on_message)
                self._sub_ids.append(sub_id)

        logger.info(
            "Role '%s' subscribed to %d topics",
            self._name, len(self._sub_ids),
        )

    def unsubscribe_bus(self) -> None:
        """取消所有订阅。"""
        if self._bus is None:
            return
        for sub_id in self._sub_ids:
            self._bus.unsubscribe(sub_id)
        self._sub_ids.clear()

    def on_message(self, msg: Msg) -> None:
        """收到消息的回调(由 MessageBus 调用)。

        默认实现:放入 inbox 队列,等待 step() 处理。
        子类可覆盖实现即时处理。

        并发安全:加 self._lock 保护 _inbox,避免与 pop_message/clear_inbox
        并发修改导致列表状态不一致。

        Args:
            msg: 收到的消息
        """
        with self._lock:
            self._inbox.append(msg)
            inbox_count = len(self._inbox)
        logger.debug(
            "Role '%s' received message (cause_by=%s, inbox=%d)",
            self._name, msg.cause_by, inbox_count,
        )

    def pop_message(self) -> Optional[Msg]:
        """从 inbox 取出最早的消息(FIFO)。

        并发安全:加 self._lock,避免与 on_message 并发操作导致
        空列表 pop 或索引错乱。
        """
        with self._lock:
            if not self._inbox:
                return None
            return self._inbox.pop(0)

    def clear_inbox(self) -> int:
        """清空 inbox,返回清空的消息数。

        并发安全:加 self._lock 保护清空操作。
        """
        with self._lock:
            count = len(self._inbox)
            self._inbox.clear()
            return count

    # -- 4 步 ReAct(复用父类,此处仅声明签名)----------------------------

    async def prepare(self, ctx: AgentContext) -> AgentContext:
        """准备阶段:子类实现。"""
        return ctx

    async def think(self, ctx: AgentContext) -> Optional[Msg]:
        """思考阶段:子类实现。"""
        return None

    async def act(self, ctx: AgentContext, thought: Msg) -> Optional[Msg]:
        """行动阶段:子类实现。"""
        return None

    async def reflect(self, ctx: AgentContext, trace: list[Msg]) -> Msg:
        """反思阶段:子类实现。"""
        from officeagent.core.types_msg import assistant_msg
        return assistant_msg(f"[{self._name}] reflect: no implementation")

    # -- 工厂方法 ----------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        role_config: Any,
        bus: Optional[MessageBus] = None,
        **extra: Any,
    ) -> "Role":
        """从 RoleConfig 创建 Role 实例。

        Args:
            role_config: RoleConfig 实例(P3-2)
            bus:         MessageBus 实例
            **extra:     额外配置(透传给 Role 构造函数)

        Returns:
            Role 实例

        用法:
            cfg = role_loader.load("office-expert")
            role = Role.from_config(cfg, bus=bus)
        """
        # 从 RoleConfig 提取 watch_actions(可从 tools 字段或 extra 推导)
        watch_actions = extra.pop("watch_actions", None)
        if watch_actions is None:
            # 默认:RoleConfig.tools 作为 watch_actions
            watch_actions = list(getattr(role_config, "tools", []) or [])

        return cls(
            name=role_config.name,
            watch_actions=watch_actions,
            bus=bus,
            display_name=getattr(role_config, "display_name", ""),
            role_config=role_config,
            **extra,
        )


__all__ = ["Role"]
