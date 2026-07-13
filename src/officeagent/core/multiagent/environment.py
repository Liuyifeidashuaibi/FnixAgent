"""Environment —— 多 Agent 共享环境 —— P3-4。

借鉴 MetaGPT 的 Environment 概念:多个 Role 在共享环境中协作。
  - Environment 持有多个 Role + 共享历史(history)
  - publish(msg):将消息路由到目标 Role(通过 MessageBus)
  - step():驱动一轮 Watch-Think-Act,返回产出消息
  - get_state():获取当前环境状态快照

设计要点:
  1. Environment 不直接调用 Role,通过 MessageBus 解耦
  2. publish 根据 msg.send_to 路由(定向);send_to=None 广播
  3. step() 从每个 Role 的 inbox 取消息,触发 reply(),将产出 publish 回 bus
  4. 循环终止:无新消息 / 达到 max_steps / 显式 stop

与 P3-1 Handoff 集成:
  - Environment 持有 HandoffRegistry,Role 可通过 handoff 转交任务
  - step() 中检测 handoff 请求,转交到目标 Role

用例:
    bus = InMemoryMessageBus()
    role1 = Role("researcher", watch_actions=["search"], bus=bus)
    role2 = Role("writer", watch_actions=["write"], bus=bus)
    env = Environment(bus=bus, roles=[role1, role2])

    env.publish(user_msg("帮我写论文", send_to="researcher"))
    for _ in range(5):
        msg = env.step()
        if msg is None:
            break
"""
from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Optional

from officeagent.core.types_msg import Msg
from officeagent.core.multiagent.messagebus import InMemoryMessageBus, MessageBus
from officeagent.core.multiagent.role import Role

logger = logging.getLogger(__name__)

# step() 循环上限下限(防止 max_steps 过小导致无法完成任务)
_MIN_MAX_STEPS = 1
# Handoff 链深度上限(防止 A→B→A→B 死循环)
_DEFAULT_HANDOFF_MAX_DEPTH = 5


# ---------------------------------------------------------------------------
# EnvironmentState
# ---------------------------------------------------------------------------


@dataclass
class EnvironmentState:
    """环境状态快照。

    Attributes:
        roles:        Role 名 → Role 实例
        history:      共享消息历史(全部 publish 过的消息)
        current_role: 当前活跃 Role 名(step() 正在处理的)
        step_count:   已执行的 step 数
    """

    roles: dict[str, Any] = field(default_factory=dict)
    history: list[Msg] = field(default_factory=list)
    current_role: Optional[str] = None
    step_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "roles": list(self.roles.keys()),
            "history_count": len(self.history),
            "current_role": self.current_role,
            "step_count": self.step_count,
        }


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


class Environment:
    """多 Agent 共享环境。

    管理:
      - 多个 Role 实例
      - 共享 MessageBus
      - 共享消息历史(history)
      - Watch-Think-Act 循环驱动

    用法:
        env = Environment(bus=bus, roles=[role1, role2])
        env.publish(user_msg("hello", send_to="role1"))
        msg = env.step()
    """

    def __init__(
        self,
        bus: Optional[MessageBus] = None,
        roles: Optional[list[Role]] = None,
        max_steps: int = 20,
    ) -> None:
        """初始化环境。

        Args:
            bus:      MessageBus 实例;None 时创建 InMemoryMessageBus
            roles:    初始 Role 列表;None 时为空,后续 add_role 添加
            max_steps: step() 循环上限(防止无限循环),必须 >= 1

        Raises:
            ValueError: max_steps < 1
        """
        # 参数校验:max_steps 必须 >= 1(防止无法运行 step)
        if not isinstance(max_steps, int) or max_steps < _MIN_MAX_STEPS:
            raise ValueError(
                f"max_steps must be int >= {_MIN_MAX_STEPS}, got {max_steps!r}"
            )
        self._bus = bus if bus is not None else InMemoryMessageBus()
        self._roles: dict[str, Role] = {}
        self._history: list[Msg] = []
        self._current_role: Optional[str] = None
        # 边界:max_steps 为 step() 循环硬上限,达到后 step() 返回 None
        # 防止单次 run() 无限循环(BUG 排查项:Environment max_steps 边界)
        self._step_count = int(max_steps)
        self._steps_taken = 0

        # 并发安全:step/astep 加锁,避免多线程同时 step 导致
        #   - _steps_taken 计数错乱
        #   - 同一 Role 的 inbox 被并发 pop
        #   - _current_role 状态不一致
        # RLock 允许同线程嵌套(step 内部调用其他持锁方法)
        self._lock = threading.RLock()

        # Handoff 死循环防护:记录当前 handoff 链深度
        # (A→B→A→B... 检测;每次 handoff 检查 depth < max_depth)
        self._handoff_depth: int = 0
        self._handoff_max_depth: int = _DEFAULT_HANDOFF_MAX_DEPTH

        # 注册初始 roles
        for role in (roles or []):
            self.add_role(role)

    # -- 属性 --------------------------------------------------------------

    @property
    def bus(self) -> MessageBus:
        """共享 MessageBus。"""
        return self._bus

    @property
    def max_steps(self) -> int:
        """step 循环上限。"""
        return self._step_count

    @property
    def steps_taken(self) -> int:
        """已执行步数。"""
        return self._steps_taken

    # -- Role 管理 ---------------------------------------------------------

    def add_role(self, role: Role) -> None:
        """添加一个 Role 到环境。

        自动:
          - 注册到 _roles 字典
          - 调用 role.subscribe_bus() 订阅 MessageBus
        """
        if role.name in self._roles:
            logger.warning("role '%s' already exists, replacing", role.name)
            old = self._roles[role.name]
            old.unsubscribe_bus()
        self._roles[role.name] = role
        # 若 role 未绑定 bus,绑定到环境的 bus
        if role.bus is None:
            role._bus = self._bus  # type: ignore[attr-defined]
        role.subscribe_bus()
        logger.info("added role '%s' to environment", role.name)

    def remove_role(self, name: str) -> bool:
        """移除 Role,返回是否成功。"""
        role = self._roles.pop(name, None)
        if role is None:
            return False
        role.unsubscribe_bus()
        logger.info("removed role '%s' from environment", name)
        return True

    def get_role(self, name: str) -> Optional[Role]:
        """按名获取 Role。"""
        return self._roles.get(name)

    def list_roles(self) -> list[str]:
        """列出全部 Role 名。"""
        return sorted(self._roles.keys())

    # -- 消息路由 ----------------------------------------------------------

    def publish(self, msg: Msg) -> int:
        """发布消息到环境。

        根据 msg.send_to 路由:
          - send_to 非空:定向发送到 topic "role.{send_to}" + 记录历史
          - send_to 为空:广播(订阅 "*" 的 Role 收到)+ 记录历史

        Args:
            msg: 待发布消息

        Returns:
            投递到的订阅者数量
        """
        # 记录到共享历史
        self._history.append(msg)

        # 路由
        if msg.send_to:
            # 定向:发布到 role 专属 topic
            topic = f"role.{msg.send_to}"
            count = self._bus.publish(topic, msg)
            # 同时广播(让 watch 全部的 role 也能收到)
            # 注:这里不广播,避免重复处理;watch 全部的 role 应订阅 role.* topic
            return count
        else:
            # 广播:发布到通用 topic
            return self._bus.publish("message.broadcast", msg)

    # -- Watch-Think-Act 驱动 ---------------------------------------------

    def step(self) -> Optional[Msg]:
        """驱动一轮 Watch-Think-Act。

        流程:
          1. 遍历所有 Role,检查 inbox 是否有消息
          2. 找到第一个有消息的 Role,取出消息
          3. 调用 role.watch() 判断是否关注
          4. 若关注,调用 role.reply(ctx) 执行 Think-Act-Reflect
          5. 将 reply 产出 publish 回环境
          6. 返回产出消息(无产出返回 None)

        边界:
          - _steps_taken >= _step_count 时返回 None(max_steps 上限,防无限循环)
          - 无消息可处理时返回 None(不消耗步数计数,但 step 仍占用一次调用)

        并发安全:加 self._lock,避免多线程同时 step 导致计数错乱 / inbox 并发 pop。
        注:RLock 允许同线程嵌套(step 内部调用 publish 等持锁方法)。

        Returns:
            Role 产出的消息;无 Role 处理返回 None

        Note:
            本方法是同步入口,内部调用异步 role.reply()。
            若在异步上下文中,请用 astep()。
        """
        with self._lock:
            # 边界检查:达到 max_steps 上限,停止(防无限循环)
            if self._steps_taken >= self._step_count:
                logger.warning(
                    "max_steps reached (%d), stopping", self._step_count
                )
                return None

            self._steps_taken += 1

            # 找到有消息的 role(按名排序保证确定性)
            active_role: Optional[Role] = None
            active_msg: Optional[Msg] = None
            for name in sorted(self._roles.keys()):
                role = self._roles[name]
                msg = role.pop_message()
                if msg is not None:
                    active_role = role
                    active_msg = msg
                    self._current_role = name
                    break

            if active_role is None or active_msg is None:
                # 无消息可处理(不回退 _steps_taken,保持步数语义)
                self._current_role = None
                return None

        # 构造 ctx(锁外,避免长时间持锁)
        from officeagent.core.agent import AgentContext
        ctx = AgentContext(
            goal=getattr(active_msg, "text_content", "") or "",
            history=self._history.copy(),
            extra={"incoming_msg": active_msg},
        )

        # 调用 reply(异步 → 同步包装,锁外执行避免阻塞其他 step)
        try:
            output = self._run_async(active_role.reply(ctx))
        except Exception as e:
            logger.error(
                "role '%s' reply failed: %s", active_role.name, e, exc_info=True
            )
            return None

        if output is None:
            return None

        # 标记发送方
        output.sent_from = active_role.name
        # publish 回环境(publish 内部会记录历史)
        self.publish(output)
        return output

    async def astep(self) -> Optional[Msg]:
        """异步版 step()。

        并发安全:加 self._lock 保护 _steps_taken / _current_role / inbox pop。
        注:reply() 在锁外执行(避免长 IO 阻塞其他协程)。
        """
        with self._lock:
            # 边界检查:达到 max_steps 上限
            if self._steps_taken >= self._step_count:
                return None

            self._steps_taken += 1

            active_role: Optional[Role] = None
            active_msg: Optional[Msg] = None
            for name in sorted(self._roles.keys()):
                role = self._roles[name]
                msg = role.pop_message()
                if msg is not None:
                    active_role = role
                    active_msg = msg
                    self._current_role = name
                    break

            if active_role is None or active_msg is None:
                self._current_role = None
                return None

        from officeagent.core.agent import AgentContext
        ctx = AgentContext(
            goal=getattr(active_msg, "text_content", "") or "",
            history=self._history.copy(),
            extra={"incoming_msg": active_msg},
        )

        # reply 在锁外执行(async IO 不应持锁)
        try:
            output = await active_role.reply(ctx)
        except Exception as e:
            logger.error("role '%s' reply failed: %s", active_role.name, e)
            return None

        if output is None:
            return None

        output.sent_from = active_role.name
        self.publish(output)
        return output

    def run(self, initial_msg: Optional[Msg] = None) -> list[Msg]:
        """运行环境直到无消息或达到 max_steps。

        Args:
            initial_msg: 初始消息(若提供,publish 到环境)

        Returns:
            全部产出消息列表
        """
        if initial_msg is not None:
            self.publish(initial_msg)

        outputs: list[Msg] = []
        for _ in range(self._step_count):
            msg = self.step()
            if msg is None:
                break
            outputs.append(msg)
        return outputs

    # -- Handoff 死循环防护 ------------------------------------------------

    def check_handoff_depth(self, target_depth: Optional[int] = None) -> None:
        """检查 handoff 深度是否超限(防 A→B→A→B 死循环)。

        在 Environment 层提供 handoff 深度守卫,与 HandoffRegistry 的
        max_depth 检查互补(双层防护):
          - HandoffRegistry.exec_handoff:单次 handoff 的 max_depth 校验
          - Environment.check_handoff_depth:环境级累计深度校验

        Args:
            target_depth: 检查的目标深度;None 表示检查当前深度是否已达上限

        Raises:
            RuntimeError: 深度超限,提示可能存在 handoff 死循环
        """
        check_depth = target_depth if target_depth is not None else self._handoff_depth
        if check_depth >= self._handoff_max_depth:
            raise RuntimeError(
                f"handoff depth {check_depth} exceeds environment max "
                f"{self._handoff_max_depth}; possible handoff loop "
                f"(A→B→A→B...)"
            )

    def enter_handoff(self) -> int:
        """进入 handoff(深度 +1),返回新深度。

        Returns:
            进入后的 handoff 深度

        Raises:
            RuntimeError: 深度超限(防死循环)
        """
        with self._lock:
            new_depth = self._handoff_depth + 1
            # 检查是否超限(防死循环)
            self.check_handoff_depth(new_depth)
            self._handoff_depth = new_depth
            return new_depth

    def exit_handoff(self) -> int:
        """退出 handoff(深度 -1,不低于 0),返回新深度。"""
        with self._lock:
            self._handoff_depth = max(0, self._handoff_depth - 1)
            return self._handoff_depth

    def reset_handoff_depth(self) -> None:
        """重置 handoff 深度(新任务开始时调用)。"""
        with self._lock:
            self._handoff_depth = 0

    # -- 状态 --------------------------------------------------------------

    def get_state(self) -> EnvironmentState:
        """获取当前环境状态快照。"""
        return EnvironmentState(
            roles=dict(self._roles),
            history=list(self._history),
            current_role=self._current_role,
            step_count=self._steps_taken,
        )

    def reset(self) -> None:
        """重置环境(清空历史 + 步数 + handoff 深度,保留 roles)。"""
        with self._lock:
            self._history.clear()
            self._steps_taken = 0
            self._current_role = None
            self._handoff_depth = 0
        for role in self._roles.values():
            role.clear_inbox()

    # -- 内部 --------------------------------------------------------------

    @staticmethod
    def _run_async(coro: Any) -> Any:
        """运行协程(兼容同步上下文)。

        若已有运行中的 loop,创建新线程跑;
        否则用 asyncio.run。
        """
        try:
            asyncio.get_running_loop()
            # 已有 loop,在新线程跑
            import threading

            result_box: list[Any] = [None]
            error_box: list[BaseException] = []

            def _run() -> None:
                new_loop = asyncio.new_event_loop()
                try:
                    result_box[0] = new_loop.run_until_complete(coro)
                except BaseException as e:
                    error_box.append(e)
                finally:
                    new_loop.close()

            t = threading.Thread(target=_run)
            t.start()
            t.join()
            if error_box:
                raise error_box[0]
            return result_box[0]
        except RuntimeError:
            # 无运行中的 loop
            return asyncio.run(coro)


__all__ = ["Environment", "EnvironmentState"]
