"""
全局配置中心。

通过环境变量与 pydantic-settings 加载,所有模块共享同一份配置单例。
设计原则: 类型安全 + 环境隔离 + 热更新友好。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any


# ---------------------------------------------------------------------------
# 基础数据类配置块 (避免巨型 dataclass, 按域拆分)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LLMConfig:
    """LLM 基础服务配置。"""
    default_provider: str = "glm"                       # 默认走哪个 provider
    request_timeout: float = 120.0                      # 单次请求超时(秒)
    max_retries: int = 3                                # 网络层重试
    retry_backoff: float = 0.8                          # 指数退避基数
    cache_enabled: bool = True                          # 精确缓存开关
    cache_max_size: int = 2048                          # LRU 条目上限
    cache_ttl: int = 86400                              # 缓存存活秒数
    # 熔断器
    circuit_failure_threshold: int = 5                  # 触发熔断的连续失败数
    circuit_recovery_timeout: float = 30.0              # 半开探测间隔(秒)
    circuit_success_threshold: int = 2                  # 半开→关闭所需成功数
    # 限流 (令牌桶)
    rate_capacity: int = 60                             # 桶容量(每窗口)
    rate_refill_per_sec: float = 10.0                   # 每秒补充令牌
    # 计费
    billing_enabled: bool = True
    # P2-9: 模型降级链(借鉴 open-office-agent 的 3 级降级)
    # max_failovers 控制单次 chat() 调用最多尝试多少个 fallback provider
    # 默认 1 表示主→备(向后兼容);设为 2 表示主→备1→备2(三级降级)
    max_failovers: int = 1


@dataclass(frozen=True)
class MemoryConfig:
    """三层记忆配置。"""
    # 短期记忆
    short_term_max_tokens: int = 6000                   # 滑动窗口 token 上限
    short_term_max_messages: int = 20                   # 最多保留消息条数
    # 长期记忆
    long_term_top_k: int = 5                            # 检索召回数
    long_term_score_threshold: float = 0.35             # 相似度阈值过滤
    long_term_chunk_size: int = 512                     # 分块字符数
    long_term_chunk_overlap: int = 64                   # 分块重叠
    long_term_ttl_days: int = 90                        # 记忆过期天数
    # 实体记忆
    entity_max_per_user: int = 1000


@dataclass(frozen=True)
class ToolConfig:
    """工具执行平台配置。"""
    max_parallel: int = 4                               # 最大并行工具数
    default_timeout: float = 30.0                       # 默认超时(秒)
    max_total_steps: int = 15                           # 单任务最大工具调用轮次
    sandbox_enabled: bool = True                        # 启用安全沙箱
    sandbox_max_cpu_seconds: float = 5.0                # 沙箱 CPU 时限
    sandbox_max_memory_mb: int = 256                    # 沙箱内存上限
    sandbox_network_whitelist: tuple = ()               # 允许访问的网络白名单


@dataclass(frozen=True)
class ReasoningConfig:
    """推理引擎配置。"""
    # 模式自动选择阈值
    plan_threshold_tools: int = 3                       # 工具数 >= 该值用 Plan&Execute
    plan_threshold_complexity: float = 0.6              # 复杂度评分 >= 该值用 Plan&Execute
    max_reasoning_iterations: int = 10                  # ReAct 最大循环次数
    reflection_enabled: bool = True                     # 是否启用反思
    reflection_max_replans: int = 2                     # 最大重规划次数
    reflection_score_threshold: float = 0.7             # 通过阈值


@dataclass(frozen=True)
class RetrievalConfig:
    """向量检索配置。"""
    embedding_dim: int = 1024                           # 向量维度
    embedding_batch_size: int = 32
    hybrid_bm25_weight: float = 0.3                     # 混合检索 BM25 权重
    hybrid_vector_weight: float = 0.7                   # 向量权重
    normalize_vectors: bool = True                      # 入库前 L2 归一化


@dataclass(frozen=True)
class SecurityConfig:
    """合规与安全配置。"""
    sensitive_enabled: bool = True
    injection_enabled: bool = True
    moderation_enabled: bool = True
    desensitize_enabled: bool = True
    sensitive_mask_char: str = "*"


@dataclass(frozen=True)
class TopologyConfig:
    """知识拓扑图(KTG)配置。

    KTG 采用 4 层固定结构: L1 目标 / L2 概念 / L3 规则 / L4 事实,
    通过权重路径搜索替代向量相似度,避免高维向量召回的"语义漂移"问题。
    """
    max_nodes: int = 50000                                # 节点总数上限(防止图膨胀)
    max_edges_per_node: int = 32                          # 单节点最大边数(防止度爆炸)
    # 权重系统
    weight_decay_days: int = 30                           # 权重衰减周期(天),每周期 ×decay_factor
    weight_decay_factor: float = 0.95                     # 衰减因子(<1 长期不用则淡化)
    weight_reinforce_increment: float = 0.1               # 命中时权重增量
    weight_max: float = 1.0                               # 权重上限
    weight_min: float = 0.01                              # 权重下限(避免完全丢失)
    # 路径搜索
    search_max_depth: int = 6                             # BFS/DFS 最大深度
    search_top_k: int = 5                                 # 返回候选路径数
    search_min_weight: float = 0.1                        # 路径权重阈值过滤
    # 持久化
    snapshot_interval: int = 100                           # 每 N 次写入触发快照
    storage_backend: str = "json"                          # json / sqlite


@dataclass(frozen=True)
class SkillsConfig:
    """技能系统(STP)配置。

    技能绑定到 L2 概念节点,拓扑权重决定调度优先级,
    形成"概念→技能"的突触式连接(权重越高越容易被激活)。
    """
    max_skills_per_concept: int = 8                       # 单概念节点绑定技能上限
    # 优先级换算
    priority_min: float = 0.1                             # 最低调度优先级
    priority_max: float = 1.0                             # 最高调度优先级
    priority_weight_exponent: float = 1.5                 # 权重→优先级指数曲线(>1 偏向高频)
    # 三级权限
    auto_invoke_levels: tuple = ("basic",)                # 自动调用(basic 无副作用)
    confirm_levels: tuple = ("reasoning",)                # 需用户确认(reasoning 调用外部)
    forbidden_levels: tuple = ("meta",)                   # 默认禁用(meta 自我修改需授权)
    # 反馈
    feedback_success_bonus: float = 0.05                  # 成功调用反馈权重增量
    feedback_failure_penalty: float = 0.1                 # 失败调用反馈权重惩罚
    feedback_window: int = 50                              # 反馈窗口(最近 N 次调用)


@dataclass(frozen=True)
class FlywheelConfig:
    """四阶段进化飞轮(MFP)配置。

    四个飞轮循环执行: ① 感知-执行 ② 知识固化 ③ 元反思 ④ 爬山进化
    形成自驱动闭环,无需人工标注即可持续优化。
    """
    # 飞轮总开关
    enabled: bool = True
    # 飞轮 1: 感知-执行
    perception_max_iterations: int = 10                   # 单任务最大迭代数
    perception_auto_continue: bool = True                 # 是否自动继续下一轮
    # 飞轮 2: 知识固化
    solidification_min_cases: int = 3                     # 触发固化的最小案例数
    solidification_similarity_threshold: float = 0.75     # 案例相似度阈值(>=该值归并)
    solidification_extract_max_rules: int = 5             # 单次提取规则上限
    # 飞轮 3: 元反思
    meta_reflection_interval: int = 10                    # 每 N 个任务触发一次元反思
    meta_reflection_score_threshold: float = 0.7          # 反思通过阈值
    meta_reflection_max_replans: int = 2                  # 单任务最大重规划数
    # 飞轮 4: 爬山进化
    evolution_check_interval: int = 50                    # 进化检查间隔(任务数)
    evolution_improvement_threshold: float = 0.05         # 提升阈值(<该值视为噪声)
    evolution_rollback_on_regression: bool = True         # 性能回退是否回滚
    evolution_max_history: int = 100                      # 进化历史保留长度


@dataclass(frozen=True)
class CoreConfig:
    """内核总配置。"""
    llm: LLMConfig = field(default_factory=LLMConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    tool: ToolConfig = field(default_factory=ToolConfig)
    reasoning: ReasoningConfig = field(default_factory=ReasoningConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    topology: TopologyConfig = field(default_factory=TopologyConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    flywheel: FlywheelConfig = field(default_factory=FlywheelConfig)
    debug: bool = False


# ---------------------------------------------------------------------------
# 从环境变量加载 (支持嵌套覆盖, 如 OFFICEAGENT_LLM__CACHE_ENABLED)
# ---------------------------------------------------------------------------

def _coerce(value: str, annotation: Any) -> Any:
    """根据类型注解把字符串环境变量强制转换。

    Args:
        value:      环境变量原始字符串
        annotation: 目标类型注解(bool/int/float/tuple/str)

    Returns:
        转换后的值

    Raises:
        ValueError: value 为空字符串(int/float 类型), 或数值转换失败
    """
    # 配置键非空校验: 数值类型(int/float)不接受空字符串
    # bool/tuple 允许空字符串(空 tuple 合法, 空 bool 视为 False)
    if annotation in (int, float) and (value is None or value == ""):
        raise ValueError(f"配置值为空, 无法转换为 {annotation}")

    if annotation is bool:
        return value.lower() in ("1", "true", "yes", "on")
    if annotation is int:
        try:
            return int(value)
        except ValueError as e:
            raise ValueError(f"无法将 '{value}' 转换为 int") from e
    if annotation is float:
        try:
            return float(value)
        except ValueError as e:
            raise ValueError(f"无法将 '{value}' 转换为 float") from e
    if annotation is tuple:
        # 空字符串 → 空 tuple(合法)
        return tuple(v.strip() for v in value.split(",") if v.strip())
    return value


def _build_config_from_env() -> CoreConfig:
    """从 OFFICEAGENT_ 前缀的环境变量构造配置。"""
    import dataclasses

    def _build_block(block_cls: type, prefix: str):
        kwargs = {}
        for f in dataclasses.fields(block_cls):
            key = f"{prefix}__{f.name.upper()}"
            raw = os.environ.get(key)
            if raw is not None:
                kwargs[f.name] = _coerce(raw, f.type if isinstance(f.type, type) else str)
        return block_cls(**kwargs)

    return CoreConfig(
        llm=_build_block(LLMConfig, "OFFICEAGENT_LLM"),
        memory=_build_block(MemoryConfig, "OFFICEAGENT_MEMORY"),
        tool=_build_block(ToolConfig, "OFFICEAGENT_TOOL"),
        reasoning=_build_block(ReasoningConfig, "OFFICEAGENT_REASONING"),
        retrieval=_build_block(RetrievalConfig, "OFFICEAGENT_RETRIEVAL"),
        security=_build_block(SecurityConfig, "OFFICEAGENT_SECURITY"),
        topology=_build_block(TopologyConfig, "OFFICEAGENT_TOPOLOGY"),
        skills=_build_block(SkillsConfig, "OFFICEAGENT_SKILLS"),
        flywheel=_build_block(FlywheelConfig, "OFFICEAGENT_FLYWHEEL"),
        debug=os.environ.get("OFFICEAGENT_DEBUG", "").lower() in ("1", "true"),
    )


@lru_cache(maxsize=1)
def get_config() -> CoreConfig:
    """获取全局配置单例。"""
    return _build_config_from_env()
