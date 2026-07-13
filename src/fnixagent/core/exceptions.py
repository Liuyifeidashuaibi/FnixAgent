"""
内核统一异常体系。

按域分组,所有自定义异常均继承 fnixagentError,便于上层统一捕获。

异常域划分:
    - LLM:        LLM 调用/超时/限流/鉴权/熔断
    - Tool:       工具执行/校验/权限/沙箱
    - Memory:     记忆系统/向量库
    - Retrieval:  检索引擎
    - Security:   敏感词/注入/审核/Guardrail
    - Reasoning:  推理/规划/反思
    - Orchestrator: 调度中枢
    - Topology:   知识拓扑图(KTG)
    - Skill:      技能-拓扑突触(STP)
    - Flywheel:   四阶进化飞轮(MFP)
"""
from __future__ import annotations


class fnixagentError(Exception):
    """所有内核异常的基类。

    上层捕获建议:
        try:
            ...
        except fnixagentError as e:
            # 统一处理内核异常
            ...
    """


# ---------------------------------------------------------------------------
# LLM 域
# ---------------------------------------------------------------------------

class LLMError(fnixagentError):
    """LLM 调用通用错误。"""


class LLMTimeoutError(LLMError):
    """请求超时。"""


class LLMRateLimitError(LLMError):
    """触发限流。"""


class LLMAuthError(LLMError):
    """鉴权失败(API Key 无效等)。"""


class LLMCircuitOpenError(LLMError):
    """熔断器处于开启状态,快速失败。"""


# ---------------------------------------------------------------------------
# 工具域
# ---------------------------------------------------------------------------

class ToolError(fnixagentError):
    """工具执行通用错误。"""


class ToolNotFoundError(ToolError):
    """请求的工具未注册。"""


class ToolValidationError(ToolError):
    """工具入参校验失败。"""


class ToolTimeoutError(ToolError):
    """工具执行超时。"""


class ToolPermissionDeniedError(ToolError):
    """权限不足,拒绝调用该工具。"""


class ToolSandboxError(ToolError):
    """沙箱内代码执行被拦截或异常。"""


class ToolCyclicDependencyError(ToolError):
    """工具编排 DAG 出现环。"""


# ---------------------------------------------------------------------------
# 记忆与检索域
# ---------------------------------------------------------------------------

class MemoryError(fnixagentError):
    """记忆系统错误。"""


class VectorStoreError(MemoryError):
    """向量库操作失败。"""


class RetrievalError(fnixagentError):
    """检索引擎错误。"""


# ---------------------------------------------------------------------------
# 安全域
# ---------------------------------------------------------------------------

class SecurityError(fnixagentError):
    """安全拦截基类。"""


class SensitiveContentError(SecurityError):
    """命中敏感词,内容被拦截。"""


class PromptInjectionError(SecurityError):
    """检测到 Prompt 注入。"""


class ContentModerationError(SecurityError):
    """输出内容审核未通过。"""


class GuardrailBlockedError(SecurityError):
    """P0-2: Guardrail 管道拦截异常。

    由 LLMRouter.chat() 在 Guardrail 校验不通过时抛出。
    携带 risk_score 与 tripwire 信息,供上层决策是返回拦截消息还是降级处理。

    Attributes:
        risk_score: 风险评分 0~1
        tripwire: 是否为 tripwire 触发(严重违规)
    """

    def __init__(
        self,
        reason: str,
        *,
        risk_score: float = 0.0,
        tripwire: bool = False,
    ) -> None:
        """初始化 Guardrail 拦截异常。

        Args:
            reason:      拦截原因(人类可读)
            risk_score:  风险评分,范围 [0.0, 1.0];超出范围会被截断
            tripwire:    是否为 tripwire 触发(严重违规,不可降级)

        Raises:
            TypeError: reason 不是 str 或 risk_score 不是数值类型
        """
        if not isinstance(reason, str):
            raise TypeError(
                f"reason must be str, got {type(reason).__name__}"
            )
        if not isinstance(risk_score, (int, float)) or isinstance(risk_score, bool):
            raise TypeError(
                f"risk_score must be float, got {type(risk_score).__name__}"
            )
        # 截断到 [0.0, 1.0],避免上层误传 >1 或 <0 的值
        if risk_score < 0.0:
            risk_score = 0.0
        elif risk_score > 1.0:
            risk_score = 1.0
        self.risk_score = float(risk_score)
        self.tripwire = bool(tripwire)
        prefix = "[tripwire]" if self.tripwire else "[blocked]"
        super().__init__(f"{prefix} {reason}")


# ---------------------------------------------------------------------------
# 推理与规划域
# ---------------------------------------------------------------------------

class ReasoningError(fnixagentError):
    """推理引擎错误。"""


class MaxIterationsExceededError(ReasoningError):
    """超过最大推理循环次数。"""


class ReflectionFailedError(ReasoningError):
    """反思校验多次未通过且重规划耗尽。"""


# ---------------------------------------------------------------------------
# 调度域
# ---------------------------------------------------------------------------

class OrchestratorError(fnixagentError):
    """调度中枢错误。"""


# ---------------------------------------------------------------------------
# 知识拓扑图 (KTG) 域
# ---------------------------------------------------------------------------

class TopologyError(fnixagentError):
    """知识拓扑图通用错误。"""


class TopologyNodeNotFoundError(TopologyError):
    """节点不存在。"""


class TopologyEdgeNotFoundError(TopologyError):
    """边不存在。"""


class TopologyValidationError(TopologyError):
    """节点/边 Schema 校验失败(层级/类型不匹配等)。"""


class TopologyLayerViolationError(TopologyError):
    """违反四层层级约束(跨层连边等)。"""


# ---------------------------------------------------------------------------
# 技能-拓扑突触协议 (STP) 域
# ---------------------------------------------------------------------------

class SkillError(fnixagentError):
    """技能系统通用错误。"""


class SkillNotFoundError(SkillError):
    """技能未注册。"""


class SkillPermissionDeniedError(SkillError):
    """技能权限不足(如 META 级技能未获授权)。"""


class SkillBindingError(SkillError):
    """技能-拓扑绑定失败(概念节点不存在或已绑定)。"""


# ---------------------------------------------------------------------------
# 四阶进化飞轮 (MFP) 域
# ---------------------------------------------------------------------------

class FlywheelError(fnixagentError):
    """进化飞轮通用错误。"""


class FlywheelStageError(FlywheelError):
    """飞轮阶段错误(阶段不存在或执行顺序违规)。"""


class SnapshotError(FlywheelError):
    """快照创建/恢复失败。"""


class EvolutionRollbackError(FlywheelError):
    """进化回滚失败(快照损坏或版本不兼容)。"""
