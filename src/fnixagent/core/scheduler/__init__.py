"""调度核心 (Scheduler) — 自适应并发治理 + 优先级任务队列。

P0-05: 提供 AutoscaledPool —— 根据系统负载(CPU / 内存 / 平均响应延迟)
动态调整并发槽位数的自适应并发池。与固定 ThreadPoolExecutor 不同,本池在
过载时主动降级、空闲时逐步升级,实现"按压力伸缩"的并发治理。

设计要点:
  - 信号量限流 + 滚动延迟窗口 + 惰性调整(无后台线程)
  - psutil 可选依赖(缺失时仅依赖延迟指标)
  - 模块级惰性单例 get_autoscaled_pool() / reset_autoscaled_pool()

与 core.governance(多层限流)互补: governance 面向 QPS/并发上限的硬限制,
本模块面向"按负载弹性伸缩"的软调度。

P1-05: 提供 PriorityTaskQueue —— 优先级任务队列(借鉴 zhua ScheduleItem +
优先级队列设计),支持优先级调度、forefront 插队、Redis ZSet 持久化、
崩溃恢复(active 超时回收)与 fingerprint 去重。

  - 内存堆(heapq 大顶堆) + 可选 Redis ZSet 双写,跨进程可见
  - threading.Condition 实现阻塞 get,线程安全
  - 模块级惰性单例 get_priority_queue() / reset_priority_queue()
"""
from fnixagent.core.scheduler.autoscale import (
    AutoscaledPool,
    AutoscaledPoolConfig,
    get_autoscaled_pool,
    reset_autoscaled_pool,
)
from fnixagent.core.scheduler.priority_queue import (
    PriorityTaskQueue,
    ScheduleItem,
    get_priority_queue,
    reset_priority_queue,
)

__all__ = [
    "AutoscaledPool",
    "AutoscaledPoolConfig",
    "get_autoscaled_pool",
    "reset_autoscaled_pool",
    "PriorityTaskQueue",
    "ScheduleItem",
    "get_priority_queue",
    "reset_priority_queue",
]
