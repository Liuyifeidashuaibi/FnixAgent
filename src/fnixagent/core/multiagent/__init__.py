"""多 Agent 协作模块 —— P3-4 / P0-03。

借鉴:
  - AgentScope:MessageBus + Environment + Role(Watch-Think-Act)
  - MetaGPT:共享黑板 + 消息发布订阅
  - OpenAI Agents SDK:Handoff 协议(P3-1 集成)
  - kaoyan-ai-platform:MoE 专家路由器(P0-03,零 LLM 调用关键词路由)

模块导出:
  - MessageBus:          消息总线抽象基类
  - InMemoryMessageBus:  同进程内存消息总线
  - Role:                Watch-Think-Act 生命周期 Agent 子类
  - Environment:         多 Agent 共享环境
  - EnvironmentState:    环境状态快照
  - topic_for_action:    Action 名 → topic 工具函数
  - topic_for_role:      Role 名 → topic 工具函数
  - ExpertDefinition:    专家定义(P0-03)
  - ExpertRegistry:      专家注册表(P0-03)
  - ExpertRouter:        MoE 专家路由器(P0-03,零 LLM 调用)
  - get_registry:        ExpertRegistry 全局单例
  - get_router:          ExpertRouter 全局单例

用例:
    from fnixagent.core.multiagent import (
        InMemoryMessageBus, Role, Environment, get_router,
    )
    bus = InMemoryMessageBus()
    role1 = MyRole("r1", watch_actions=["search"], bus=bus)
    env = Environment(bus=bus, roles=[role1])
    env.publish(user_msg("hello", send_to="r1"))
    msg = env.step()

    # P0-03 专家路由
    router = get_router()
    expert_key = router.route_by_user_input("帮我检索 arxiv 上的 LLM 综述")
    # expert_key == "search"
"""
from fnixagent.core.multiagent.environment import Environment, EnvironmentState
from fnixagent.core.multiagent.expert_registry import (
    ExpertDefinition,
    ExpertRegistry,
    get_registry,
    register_default_experts,
    reset_registry,
)
from fnixagent.core.multiagent.messagebus import (
    InMemoryMessageBus,
    MessageBus,
    topic_for_action,
    topic_for_role,
)
from fnixagent.core.multiagent.moe_router import (
    ExpertRouter,
    get_router,
    reset_router,
)
from fnixagent.core.multiagent.role import Role

__all__ = [
    "MessageBus",
    "InMemoryMessageBus",
    "Role",
    "Environment",
    "EnvironmentState",
    "topic_for_action",
    "topic_for_role",
    # P0-03 专家路由
    "ExpertDefinition",
    "ExpertRegistry",
    "ExpertRouter",
    "get_registry",
    "get_router",
    "register_default_experts",
    "reset_registry",
    "reset_router",
]
