"""
多模型路由器 (LLM Router)。

职责:
  1. 注册多个 LLM Provider, 按策略选择 provider 路由请求
  2. 负载均衡: 轮询 / 加权 / 最少负载
  3. 故障转移: 当前 provider 熔断或超时自动切下一个
  4. 集成限流、熔断、缓存、计费(装饰链式调用)
  5. P2-9: 多级降级链(借鉴 open-fnix-agent),支持主→备1→备2 链式降级

路由流程:
  请求到达 → 限流检查 → 缓存检查 → 选 provider → 熔断检查
  → 调用 provider.chat() → 记录计费 → 更新统计
  → 异常? → 熔断记录 + 按降级链逐级 failover(最多 max_failovers 次)

P2-9 降级链示例(借鉴 open-fnix-agent 的 3 级降级):
  router.set_fallback_chain([
      primary_provider,    # 主模型(如 gemini-2.5-flash)
      fallback_provider,   # 降级1(如 gemini-2.5-flash-lite)
      groq_provider,       # 降级2(如 llama-3.3-70b)
  ])
  # chat() 调用时:主失败→降级1→降级2,逐级尝试,全部失败才抛异常
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from enum import Enum

from fnixagent.core.config import LLMConfig
from fnixagent.core.exceptions import (
    LLMCircuitOpenError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from fnixagent.core.llm.base import BaseLLMProvider, LLMRequest
from fnixagent.core.llm.billing import BillingMeter
from fnixagent.core.llm.cache import ResponseCache
from fnixagent.core.llm.capability import (
    CapabilityRequirement,
    ModelCapability,
    ModelCapabilityFlag,
)
from fnixagent.core.llm.circuit import CircuitBreaker
from fnixagent.core.llm.limiter import TokenBucketRateLimiter
from fnixagent.core.types import LLMResponse

# ---------------------------------------------------------------------------
# 路由策略
# ---------------------------------------------------------------------------


class RouteStrategy(str, Enum):
    ROUND_ROBIN = "round_robin"  # 轮询
    WEIGHTED = "weighted"  # 加权
    LEAST_LOAD = "least_load"  # 最少负载(最低平均延迟)
    FAILOVER = "failover"  # 故障转移(主→备)


@dataclass
class RouterStats:
    """单个 provider 的路由统计。"""

    provider_name: str
    total_calls: int = 0
    success_count: int = 0
    fail_count: int = 0
    total_latency_ms: float = 0.0
    last_error: str = ""
    avg_latency_ms: float = 0.0

    def record_success(self, latency_ms: float) -> None:
        """记录一次成功调用, 累加延迟用于平均延迟统计。"""
        self.total_calls += 1
        self.success_count += 1
        self.total_latency_ms += latency_ms
        self.avg_latency_ms = self.total_latency_ms / self.total_calls

    def record_failure(self, error: str) -> None:
        """记录一次失败调用, 保存最近一次错误信息。"""
        self.total_calls += 1
        self.fail_count += 1
        self.last_error = error

    @property
    def success_rate(self) -> float:
        """成功率, 无调用记录时返回 1.0(视为健康)。"""
        if self.total_calls == 0:
            return 1.0
        return self.success_count / self.total_calls


# ---------------------------------------------------------------------------
# Provider 注册项
# ---------------------------------------------------------------------------


@dataclass
class _ProviderEntry:
    provider: BaseLLMProvider
    weight: float = 1.0
    circuit: CircuitBreaker = field(default_factory=CircuitBreaker)
    stats: RouterStats | None = field(default=None)  # 在 __post_init__ 初始化
    # P2-8: 模型能力描述
    capabilities: ModelCapability = field(default_factory=ModelCapability)

    def __post_init__(self):
        if self.stats is None:
            self.stats = RouterStats(provider_name=self.provider.name)


# ---------------------------------------------------------------------------
# 路由器
# ---------------------------------------------------------------------------


class LLMRouter:
    """
    多模型路由器。

    用法:
        router = LLMRouter(config=llm_config)
        router.register(glm_provider, weight=2.0)
        router.register(qwen_provider, weight=1.0)
        response = router.chat(request)
    """

    def __init__(
        self,
        config: LLMConfig | None = None,
        strategy: RouteStrategy = RouteStrategy.WEIGHTED,
    ):
        self._config = config or LLMConfig()
        self._strategy = strategy
        self._entries: list[_ProviderEntry] = []
        self._rr_index = 0  # 轮询游标
        self._lock = threading.Lock()

        # 子组件
        self._rate_limiter = TokenBucketRateLimiter(
            capacity=self._config.rate_capacity,
            refill_per_sec=self._config.rate_refill_per_sec,
        )
        self._cache = (
            ResponseCache(
                max_size=self._config.cache_max_size,
                ttl=self._config.cache_ttl,
            )
            if self._config.cache_enabled
            else None
        )
        self._billing = BillingMeter() if self._config.billing_enabled else None
        # P0-2: 可选的 Guardrail 管道(通过 set_guardrail_pipeline 注入,避免分层依赖)
        self._guardrail_pipeline = None

    # -- 注册 --------------------------------------------------------------

    def set_guardrail_pipeline(self, pipeline) -> None:
        """P0-2: 注入 Guardrail 管道(可选)。

        通过依赖注入而非直接 import,避免 LLM 层依赖 Security 层(保持分层)。
        注入后,每次 chat() 调用前后自动执行输入/输出 Guardrail。

        Args:
            pipeline: GuardrailPipeline 实例(来自 SecurityEngine.guardrail_pipeline)
        """
        self._guardrail_pipeline = pipeline

    def register(
        self,
        provider: BaseLLMProvider,
        weight: float = 1.0,
        capabilities: ModelCapability | None = None,
    ) -> None:
        """注册一个 provider。

        Args:
            provider: BaseLLMProvider 实例。
            weight: 路由权重(加权策略下使用),必须 > 0。
            capabilities: P2-8 模型能力描述(None 表示无特殊能力,默认 LOW_COST)。

        Raises:
            TypeError: provider 不是 BaseLLMProvider 或 weight 不是数值。
            ValueError: weight 非正数。
        """
        if not isinstance(provider, BaseLLMProvider):
            raise TypeError(f"provider must be BaseLLMProvider, got {type(provider).__name__}")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise TypeError(f"weight must be numeric, got {type(weight).__name__}")
        if weight <= 0:
            raise ValueError(f"weight must be positive, got {weight}")
        entry = _ProviderEntry(
            provider=provider,
            weight=weight,
            circuit=CircuitBreaker(
                failure_threshold=self._config.circuit_failure_threshold,
                recovery_timeout=self._config.circuit_recovery_timeout,
                success_threshold=self._config.circuit_success_threshold,
            ),
            capabilities=capabilities
            or ModelCapability(
                model_name=provider.model_name,
                flags=ModelCapabilityFlag.LOW_COST | ModelCapabilityFlag.STREAMING,
            ),
        )
        with self._lock:
            self._entries.append(entry)

    def unregister(self, name: str) -> None:
        """按 name 注销指定 provider。"""
        with self._lock:
            self._entries = [e for e in self._entries if e.provider.name != name]

    @property
    def providers(self) -> list[str]:
        """当前已注册的 provider 名称列表。"""
        return [e.provider.name for e in self._entries]

    # -- 路由选择 ----------------------------------------------------------

    def _select(self) -> _ProviderEntry | None:
        """根据策略选择一个可用的 provider(无能力筛选,向后兼容)。"""
        with self._lock:
            available = [e for e in self._entries if e.circuit.allow_request()]
            if not available:
                return None
            return self._pick_by_strategy(available)

    def _select_for(self, request: LLMRequest) -> _ProviderEntry | None:
        """P2-8: 根据 request 的能力需求筛选 provider,再按策略选择。

        筛选流程:
          1. 由 request.think_mode 与 request.cost_preference 构造 CapabilityRequirement
          2. 过滤 available providers,仅保留满足 requirement 的
          3. 若无可用的,回退到全部 available(避免思考模式请求被全部拒绝)
          4. 按 strategy 选 provider,优先选 capability_score 高的

        Args:
            request: LLMRequest(读取 think_mode / cost_preference)

            Returns:
                选中的 _ProviderEntry,或 None(全部熔断)
        """
        # 构造能力需求
        requirement = self._build_requirement(request)
        with self._lock:
            all_available = [e for e in self._entries if e.circuit.allow_request()]
            if not all_available:
                return None
            # 按能力筛选
            if requirement is not None:
                matched = [e for e in all_available if requirement.matches(e.capabilities)]
                if matched:
                    # 在 matched 中按 capability score 排序,优先高分
                    if self._strategy == RouteStrategy.WEIGHTED:
                        # 加权随机,但 score 作为额外权重
                        weights = [
                            e.weight * max(requirement.score(e.capabilities), 0.1) for e in matched
                        ]
                        return random.choices(matched, weights=weights, k=1)[0]
                    elif self._strategy == RouteStrategy.LEAST_LOAD:
                        # 最少负载 + 能力加分
                        return min(
                            matched,
                            key=lambda e: (
                                e.stats.avg_latency_ms - requirement.score(e.capabilities) * 100
                            ),
                        )
                    else:
                        # ROUND_ROBIN / FAILOVER:仍按 strategy,但限定在 matched 内
                        return self._pick_by_strategy(matched)
            # 回退:无 requirement 或无匹配时,按 strategy 选
            return self._pick_by_strategy(all_available)

    def _build_requirement(self, request: LLMRequest) -> CapabilityRequirement | None:
        """由 request 构造 CapabilityRequirement(无特殊需求返回 None)。"""
        if not request.think_mode and request.cost_preference == "auto":
            return None
        req = CapabilityRequirement()
        if request.think_mode:
            req.required |= ModelCapabilityFlag.THINK_MODE
        if request.cost_preference == "cheap":
            req.preferred |= ModelCapabilityFlag.LOW_COST
            req.forbidden |= ModelCapabilityFlag.HIGH_QUALITY
        elif request.cost_preference == "quality":
            req.preferred |= ModelCapabilityFlag.HIGH_QUALITY
        return req

    def _pick_by_strategy(self, available: list[_ProviderEntry]) -> _ProviderEntry | None:
        """按 self._strategy 从 available 列表选一个(已持有 _lock)。"""
        if not available:
            return None
        if self._strategy == RouteStrategy.ROUND_ROBIN:
            idx = self._rr_index % len(available)
            self._rr_index = (self._rr_index + 1) % max(len(self._entries), 1)
            return available[idx]
        elif self._strategy == RouteStrategy.LEAST_LOAD:
            return min(available, key=lambda e: e.stats.avg_latency_ms)
        elif self._strategy == RouteStrategy.FAILOVER:
            return available[0]
        else:  # WEIGHTED
            weights = [e.weight for e in available]
            return random.choices(available, weights=weights, k=1)[0]

    def _select_fallback(self, exclude_name: str) -> _ProviderEntry | None:
        """排除已失败的 provider,选下一个可用项。"""
        with self._lock:
            available = [
                e
                for e in self._entries
                if e.provider.name != exclude_name and e.circuit.allow_request()
            ]
            if not available:
                return None
            return available[0]

    def _select_fallback_excluding(self, tried_names: set[str]) -> _ProviderEntry | None:
        """P2-9: 排除多个已尝试的 provider,选下一个可用项(支持多级降级)。

        策略:
          - 排除 tried_names 中所有 provider(避免重复尝试同一 provider)
          - 仅选 circuit 处于允许请求状态的 provider
          - 按注册顺序选第一个可用的(FAILOVER 语义)

        Args:
            tried_names: 已尝试过的 provider 名集合

        Returns:
            下一个可用的 _ProviderEntry;无可用项返回 None
        """
        with self._lock:
            available = [
                e
                for e in self._entries
                if e.provider.name not in tried_names and e.circuit.allow_request()
            ]
            if not available:
                return None
            return available[0]

    def set_fallback_chain(
        self,
        providers: list[BaseLLMProvider],
        capabilities: list[ModelCapability | None] | None = None,
    ) -> None:
        """P2-9: 一键配置多级降级链(借鉴 open-fnix-agent 的 3 级降级)。

        将多个 provider 按顺序注册,启用 FAILOVER 策略,自动设置
        max_failovers = len(providers) - 1,使 chat() 按链路逐级降级。

        典型用法(open-fnix-agent 的 3 级链):
            router.set_fallback_chain([
                primary_provider,    # 主模型(如 gemini-2.5-flash)
                fallback_provider,   # 降级1(如 gemini-2.5-flash-lite)
                groq_provider,       # 降级2(如 llama-3.3-70b)
            ])
            # 此后 chat() 调用:主失败→降级1→降级2,逐级尝试

        Args:
            providers: provider 列表,按优先级降序排列(至少 2 个)
            capabilities: 各 provider 的能力描述;None 表示全部用默认能力

        Raises:
            ValueError: providers 少于 2 个(无法构成降级链)
            TypeError: providers 中存在非 BaseLLMProvider 实例
        """
        if not isinstance(providers, list) or len(providers) < 2:
            raise ValueError(
                f"fallback chain requires at least 2 providers, got {len(providers) if isinstance(providers, list) else 0}"
            )
        caps_list = capabilities or [None] * len(providers)
        if len(caps_list) != len(providers):
            raise ValueError(
                f"capabilities length {len(caps_list)} != providers length {len(providers)}"
            )
        # 清空现有注册,按链路顺序重新注册
        with self._lock:
            self._entries.clear()
            self._rr_index = 0
        for prov, caps in zip(providers, caps_list):
            self.register(prov, weight=1.0, capabilities=caps)
        # 切换到 FAILOVER 策略 + 调整 max_failovers
        self._strategy = RouteStrategy.FAILOVER
        # frozen dataclass 不能直接改字段,通过 __dict__ 绕过(运行期配置覆盖)
        # 注:若 LLMConfig 未来支持 mutable,可改为 self._config = replace(...)
        object.__setattr__(self._config, "max_failovers", len(providers) - 1)

    # -- 主入口 ------------------------------------------------------------

    def chat(self, request: LLMRequest) -> LLMResponse:
        """路由调用入口。

        完整链路:限流 → (输入 Guardrail) → 缓存 → 选 provider → 熔断 →
        调用 → 计费 → (输出 Guardrail) → 异常 failover。

        Args:
            request: LLM 调用请求(读取 user_id/trace_id/think_mode/cost_preference 等)。

        Returns:
            LLMResponse: 命中缓存则直接返回(cached=True),否则调用 provider 后返回。

        Raises:
            LLMRateLimitError: 触发限流。
            LLMCircuitOpenError: 全部 provider 熔断或 failover 仍失败。
            LLMError: provider 调用失败(含 failover 后仍失败)。
            GuardrailBlockedError: 输入/输出 Guardrail 拦截。
        """
        user_key = request.user_id or "default"

        # 1. 限流检查
        if not self._rate_limiter.acquire(user_key):
            raise LLMRateLimitError(f"rate limit exceeded for user '{user_key}'")

        # P0-2: 输入 Guardrail(对最后一条用户消息校验)
        if self._guardrail_pipeline is not None:
            last_user_text = ""
            for msg in reversed(request.messages):
                if msg.role.value == "user":
                    last_user_text = msg.content
                    break
            if last_user_text:
                in_result = self._guardrail_pipeline.run_input(
                    last_user_text, user_id=request.user_id
                )
                if not in_result.passed:
                    # tripwire 或软拦截:返回拦截响应(不调用 LLM)
                    from fnixagent.core.exceptions import GuardrailBlockedError

                    raise GuardrailBlockedError(
                        in_result.blocked_reason,
                        risk_score=in_result.risk_score,
                        tripwire=in_result.tripwire_triggered,
                    )

        # 2. 缓存检查(缓存键只计算一次,避免重复开销)
        # 注:必须把 tools/stop/max_tokens/think_mode/tool_choice 纳入键,
        # 否则不同 tools 或不同思考模式的请求会命中同一缓存(键冲突)
        cache_key = None
        if self._cache and not request.stream:
            cache_key = ResponseCache.make_key(
                [m.to_llm_dict() for m in request.messages],
                model=request.model or "",
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                tool_choice=request.tool_choice,
                # stop/tools 需用可 JSON 序列化且确定性的表示(list/排序后的字符串)
                stop=list(request.stop),
                tools_sig=sorted(
                    (t.get("name", "") if isinstance(t, dict) else str(t)) for t in request.tools
                ),
                think_mode=request.think_mode,
            )
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        # 3. 选 provider 并调用(P2-8: 用 _select_for 按能力筛选)
        # P2-9: 多级降级链(借鉴 open-fnix-agent),按 max_failovers 循环重试
        entry = self._select_for(request)
        if entry is None:
            raise LLMCircuitOpenError("all providers circuit-open, no available LLM")

        # 记录本次调用已尝试过的 provider 名称,避免同一 provider 被重复尝试
        tried_names: set[str] = {entry.provider.name}
        response: LLMResponse | None = None
        try:
            response = self._call_provider(entry, request)
        except (LLMError, LLMTimeoutError, LLMCircuitOpenError) as exc:
            entry.circuit.record_failure()
            entry.stats.record_failure(str(exc))
            # P2-9: 多级降级循环(默认 max_failovers=1 向后兼容单次 failover)
            max_failovers = max(self._config.max_failovers, 0)
            fallback = self._select_fallback_excluding(tried_names)
            attempts = 0
            last_exc: Exception | None = exc
            while attempts < max_failovers and fallback is not None:
                tried_names.add(fallback.provider.name)
                attempts += 1
                try:
                    response = self._call_provider(fallback, request)
                    break
                except (LLMError, LLMTimeoutError, LLMCircuitOpenError) as fb_exc:
                    fallback.circuit.record_failure()
                    fallback.stats.record_failure(str(fb_exc))
                    last_exc = fb_exc
                    fallback = self._select_fallback_excluding(tried_names)
            if response is None:
                # 全部 fallback 都失败,抛出最后一个异常
                raise (
                    last_exc
                    if last_exc is not None
                    else LLMError("all providers failed in fallback chain")
                )

        # 4. 写缓存(复用已计算的 cache_key)
        if cache_key is not None:
            self._cache.set(cache_key, response)

        # P0-2: 输出 Guardrail(内容审核 + PII 脱敏)
        if self._guardrail_pipeline is not None and response.content:
            out_result = self._guardrail_pipeline.run_output(
                response.content, user_id=request.user_id
            )
            if not out_result.passed:
                from fnixagent.core.exceptions import GuardrailBlockedError

                raise GuardrailBlockedError(
                    out_result.blocked_reason,
                    risk_score=out_result.risk_score,
                    tripwire=out_result.tripwire_triggered,
                )
            # 用脱敏后的文本替换原输出
            if out_result.sanitized_text:
                response.content = out_result.sanitized_text

        return response

    def _call_provider(self, entry: _ProviderEntry, request: LLMRequest) -> LLMResponse:
        """调用单个 provider,处理超时与计费。"""
        # P1-1: 若有 active trace,创建 LLMSpan(无 trace 时跳过,零开销)
        trace = None
        try:
            from fnixagent.core.observability.tracing import get_provider

            trace = get_provider().get_current_trace()
        except Exception:
            pass

        if trace is not None:
            from fnixagent.core.observability.tracing import LLMSpanData

            llm_span_data = LLMSpanData(
                provider=entry.provider.name,
                model=request.model or "",
            )
            with trace.start_span("llm_call", llm_span_data, cached=False) as span:
                response = self._call_provider_inner(entry, request)
                # 回填 token 信息到 Span
                if hasattr(response, "usage") and response.usage:
                    llm_span_data.prompt_tokens = getattr(response.usage, "prompt_tokens", 0) or 0
                    llm_span_data.completion_tokens = (
                        getattr(response.usage, "completion_tokens", 0) or 0
                    )
                    llm_span_data.total_tokens = getattr(response.usage, "total_tokens", 0) or 0
                llm_span_data.latency_ms = span.duration_ms or 0.0
                return response
        return self._call_provider_inner(entry, request)

    def _call_provider_inner(self, entry: _ProviderEntry, request: LLMRequest) -> LLMResponse:
        """实际调用 provider(被 _call_provider 包裹 Span)。"""
        t0 = time.monotonic()
        try:
            response = entry.provider.chat(request)
        except Exception as exc:
            # Phase 2.10: 记录 LLM 调用错误指标
            try:
                from fnixagent.core.observability.metrics import record_llm_error

                record_llm_error(provider=entry.provider.name, error_type=type(exc).__name__)
            except Exception:
                pass
            raise
        latency_ms = (time.monotonic() - t0) * 1000

        # Phase 2.10: 记录 LLM 调用指标
        try:
            from fnixagent.core.observability.metrics import record_llm_call, record_llm_tokens

            provider_name = entry.provider.name
            model_name = request.model or "default"
            record_llm_call(
                provider=provider_name, model=model_name, duration_seconds=latency_ms / 1000
            )
            if hasattr(response, "usage") and response.usage:
                prompt_tokens = getattr(response.usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(response.usage, "completion_tokens", 0) or 0
                if prompt_tokens or completion_tokens:
                    record_llm_tokens(
                        provider=provider_name,
                        model=model_name,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                    )
        except Exception:
            pass

        # 记录成功
        entry.circuit.record_success()
        entry.stats.record_success(latency_ms)

        # 计费
        if self._billing and request.user_id:
            self._billing.record(
                user_id=request.user_id,
                model=response.model,
                usage=response.usage,
                trace_id=request.trace_id,
            )
        return response

    # -- 统计 --------------------------------------------------------------

    def get_stats(self) -> dict:
        """获取所有 provider 的路由统计。"""
        with self._lock:
            return {
                "strategy": self._strategy.value,
                "providers": {
                    e.provider.name: {
                        "total_calls": e.stats.total_calls,
                        "success_count": e.stats.success_count,
                        "fail_count": e.stats.fail_count,
                        "avg_latency_ms": round(e.stats.avg_latency_ms, 2),
                        "success_rate": round(e.stats.success_rate, 4),
                        "circuit_state": e.circuit.get_state().value,
                        "last_error": e.stats.last_error,
                    }
                    for e in self._entries
                },
                "cache": self._cache.stats() if self._cache else None,
                "rate_limiter": self._rate_limiter.stats(),
            }

    @property
    def billing(self) -> BillingMeter | None:
        """计费器实例(未启用计费时为 None)。"""
        return self._billing

    @property
    def cache(self) -> ResponseCache | None:
        """响应缓存实例(未启用缓存时为 None)。"""
        return self._cache

    # -- P2-8: 能力查询 ---------------------------------------------------

    def list_capabilities(self) -> list[ModelCapability]:
        """列出全部已注册 provider 的能力描述(P2-8)。"""
        with self._lock:
            return [e.capabilities for e in self._entries]

    def get_provider_capabilities(self, name: str) -> ModelCapability | None:
        """按 name 获取 provider 的能力描述(不存在返回 None)。"""
        with self._lock:
            for e in self._entries:
                if e.provider.name == name:
                    return e.capabilities
            return None

    def has_capability(
        self,
        flag: ModelCapabilityFlag,
        name: str | None = None,
    ) -> bool:
        """检查是否有任意 provider(name 指定时为该 provider)具备指定能力。"""
        with self._lock:
            entries = self._entries
            if name is not None:
                entries = [e for e in entries if e.provider.name == name]
            return any(e.capabilities.has(flag) for e in entries)

    def find_providers_with(
        self,
        flag: ModelCapabilityFlag,
    ) -> list[str]:
        """返回具备指定能力的 provider 名列表。"""
        with self._lock:
            return [e.provider.name for e in self._entries if e.capabilities.has(flag)]
