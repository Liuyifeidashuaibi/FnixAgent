"""
LLM Token 计费统计。

按模型记录 token 用量与费用,支持多维度查询:
  - 按 tenant / user / model 聚合
  - 按时间窗口查询(最近 N 秒)
  - 价格表可配: dict[model, (input_price_per_1k, output_price_per_1k)]

线程安全: defaultdict + threading.Lock。
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from fnixagent.core.types import TokenUsage


# ---------------------------------------------------------------------------
# 计费记录
# ---------------------------------------------------------------------------

@dataclass
class BillingRecord:
    """单次计费记录。"""
    user_id: str
    model: str
    usage: TokenUsage
    cost: float
    trace_id: str = ""
    timestamp: float = field(default_factory=time.time)


# 默认价格表 (每 1K token 的价格,单位:元)
# 业务层可覆盖
DEFAULT_PRICE_TABLE: dict[str, tuple[float, float]] = {
    "glm-4": (0.05, 0.15),
    "glm-4-flash": (0.01, 0.01),
    "qwen2.5-72b": (0.04, 0.12),
    "qwen2.5-7b": (0.001, 0.002),
    "gpt-4o": (0.0175, 0.07),
    "gpt-4o-mini": (0.00015, 0.0006),
    "default": (0.01, 0.03),   # 未知模型的兜底价格
}


class BillingMeter:
    """Token 计费统计器。

    线程安全: 所有记录与查询操作均通过 self._lock 保护。预聚合索引 _user_stats
    与原始记录 _records 在同一锁内同步更新,保证统计一致。

    用法:
        meter = BillingMeter(price_table=DEFAULT_PRICE_TABLE)
        meter.record("user_1", "glm-4", usage, trace_id="xxx")
        cost = meter.get_cost(user_id="user_1")
    """

    def __init__(
        self,
        price_table: dict[str, tuple[float, float]] | None = None,
        max_records: int = 100_000,
    ):
        """初始化计费器。

        Args:
            price_table: 模型价格表 {model: (input_price_per_1k, output_price_per_1k)};
                         None 时使用 DEFAULT_PRICE_TABLE。
            max_records: 保留的最大原始记录数,超限淘汰最旧记录,必须为正整数。

        Raises:
            TypeError: max_records 类型错误。
            ValueError: max_records 非正数。
        """
        if isinstance(max_records, bool) or not isinstance(max_records, int):
            raise TypeError(f"max_records must be int, got {type(max_records).__name__}")
        if max_records <= 0:
            raise ValueError(f"max_records must be positive, got {max_records}")
        self._price_table = price_table or dict(DEFAULT_PRICE_TABLE)
        self._max_records = max_records
        self._records: list[BillingRecord] = []
        # 预聚合索引: user_id -> {model -> [total_in, total_out, total_cost, count]}
        self._user_stats: dict[str, dict[str, list]] = defaultdict(
            lambda: defaultdict(lambda: [0, 0, 0.0, 0])
        )
        self._lock = threading.Lock()

    # -- 价格查询 ----------------------------------------------------------

    def get_price(self, model: str) -> tuple[float, float]:
        """获取指定模型的 (输入价格/1K, 输出价格/1K)。

        未知模型回退到 "default" 条目,若 default 也缺失则返回 (0.01, 0.03)。
        """
        if model in self._price_table:
            return self._price_table[model]
        return self._price_table.get("default", (0.01, 0.03))

    def set_price(self, model: str, input_price: float, output_price: float) -> None:
        """设置/更新模型价格。

        Args:
            model: 模型名。
            input_price: 每 1K 输入 token 价格。
            output_price: 每 1K 输出 token 价格。
        """
        self._price_table[model] = (input_price, output_price)

    # -- 计费计算 ----------------------------------------------------------

    def calculate_cost(self, model: str, usage: TokenUsage) -> float:
        """计算单次调用费用。

        cost = (input_tokens / 1000) * input_price
             + (output_tokens / 1000) * output_price

        Args:
            model: 模型名(用于查价格表)。
            usage: 本次调用的 token 用量。

        Returns:
            float: 费用(保留 6 位小数)。
        """
        in_price, out_price = self.get_price(model)
        cost = (usage.prompt_tokens / 1000.0) * in_price \
             + (usage.completion_tokens / 1000.0) * out_price
        return round(cost, 6)

    # -- 记录 --------------------------------------------------------------

    def record(
        self,
        user_id: str,
        model: str,
        usage: TokenUsage,
        trace_id: str = "",
    ) -> BillingRecord:
        """记录一次 LLM 调用的 token 用量与费用。

        Args:
            user_id: 用户/租户标识,不能为空。
            model: 模型名,不能为空。
            usage: token 用量。
            trace_id: 可选的链路追踪 ID。

        Returns:
            BillingRecord: 已记录的计费条目。

        Raises:
            TypeError: usage 不是 TokenUsage。
            ValueError: user_id 或 model 为空。
        """
        if not isinstance(usage, TokenUsage):
            raise TypeError(f"usage must be TokenUsage, got {type(usage).__name__}")
        if not user_id:
            raise ValueError("user_id must not be empty")
        if not model:
            raise ValueError("model must not be empty")
        cost = self.calculate_cost(model, usage)
        record = BillingRecord(
            user_id=user_id,
            model=model,
            usage=usage,
            cost=cost,
            trace_id=trace_id,
        )
        with self._lock:
            self._records.append(record)
            # 淘汰超限记录
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records:]
            # 更新预聚合
            stats = self._user_stats[user_id][model]
            stats[0] += usage.prompt_tokens
            stats[1] += usage.completion_tokens
            stats[2] += cost
            stats[3] += 1
        return record

    # -- 查询 --------------------------------------------------------------

    def get_usage(
        self,
        user_id: str | None = None,
        model: str | None = None,
        window_seconds: float | None = None,
    ) -> dict:
        """查询 token 用量统计。

        - user_id / model 为 None 表示不按该维度过滤
        - window_seconds: 只统计最近 N 秒内的记录

        Args:
            user_id: 按用户过滤,None 表示全部。
            model: 按模型过滤,None 表示全部。
            window_seconds: 时间窗口(秒),None 表示不限。

        Returns:
            dict: 含 total_input_tokens / total_output_tokens / total_cost /
                  total_calls / by_model(按模型分项聚合)。
        """
        with self._lock:
            now = time.time()
            total_in = 0
            total_out = 0
            total_cost = 0.0
            count = 0
            models: dict[str, dict] = {}

            for r in self._records:
                if user_id and r.user_id != user_id:
                    continue
                if model and r.model != model:
                    continue
                if window_seconds and (now - r.timestamp) > window_seconds:
                    continue
                total_in += r.usage.prompt_tokens
                total_out += r.usage.completion_tokens
                total_cost += r.cost
                count += 1
                if r.model not in models:
                    models[r.model] = {"input": 0, "output": 0, "cost": 0.0, "calls": 0}
                models[r.model]["input"] += r.usage.prompt_tokens
                models[r.model]["output"] += r.usage.completion_tokens
                models[r.model]["cost"] += r.cost
                models[r.model]["calls"] += 1

            return {
                "total_input_tokens": total_in,
                "total_output_tokens": total_out,
                "total_cost": round(total_cost, 6),
                "total_calls": count,
                "by_model": models,
            }

    def get_cost(self, user_id: str | None = None) -> float:
        """快捷查询总费用(等价于 get_usage(user_id=...)['total_cost'])。"""
        return self.get_usage(user_id=user_id)["total_cost"]

    def get_records(
        self, user_id: str | None = None, limit: int = 100
    ) -> list[BillingRecord]:
        """获取原始记录列表(返回最近 limit 条,顺序为时间正序)。

        Args:
            user_id: 按用户过滤,None 表示全部。
            limit: 返回最近多少条,必须为正。
        """
        with self._lock:
            filtered = [
                r for r in self._records
                if user_id is None or r.user_id == user_id
            ]
            return filtered[-limit:]

    def reset(self) -> None:
        """清空全部计费记录与预聚合索引。"""
        with self._lock:
            self._records.clear()
            self._user_stats.clear()
