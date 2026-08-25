"""OTLP/HTTP JSON 导出器 —— 把自研 Span 转为 OTLP 格式上报。

将 fnixagent 自研 tracing 的不可变 Span 快照(span.Span)序列化为
OTLP/HTTP JSON(protobuf JSON 编码)格式,POST 到兼容 OpenTelemetry
Collector / Jaeger / SigNoz 等后端的 ``{endpoint}/v1/traces`` 接口。

请求体结构(resourceSpans → scopeSpans → spans):

    {
      "resourceSpans": [
        {
          "resource": {"attributes": [{"key": "service.name",
                                       "value": {"stringValue": "fnixagent"}}]},
          "scopeSpans": [
            {
              "scope": {"name": "fnixagent.tracing", "version": "1.0.0"},
              "spans": [
                {
                  "traceId": "<hex>",
                  "spanId": "<hex>",
                  "parentSpanId": "<hex>",       # 根 Span 省略
                  "name": "...",
                  "kind": 1,                     # SpanKind 枚举值
                  "startTimeUnixNano": "1719999999000000000",
                  "endTimeUnixNano":   "1719999999123456789",
                  "attributes": [{"key": ..., "value": {...}}],
                  "status": {"code": 1}
                }
              ]
            }
          ]
        }
      ]
    }

启用方式(默认关闭,零开销):
    设置环境变量 ``FNIX_OTEL_EXPORTER_OTLP_ENDPOINT``(如
    ``http://localhost:4318``)后,get_provider() 首次初始化时会自动
    创建并挂接本导出器;也可手动实例化后调用
    ``provider.add_span_exporter(exporter)``。

可靠性约定:
    - 批量发送:内存队列 + 后台线程,每 5 秒或满 32 条触发一次 flush;
      进程退出时通过 atexit 强制 flush。
    - 任何失败(HTTP 错误/网络异常/序列化异常)静默处理,仅以限频
      warning 记录(默认 60 秒最多一条),绝不影响主流程。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import atexit
import json
import logging
import os
import threading
import time
from typing import Any

from fnixagent.core.observability.tracing.span import Span

_logger = logging.getLogger(__name__)

# OTLP 端点环境变量(对齐 OTEL 官方命名,加 FNIX_ 前缀避免误伤其他 SDK)
_ENV_ENDPOINT = "FNIX_OTEL_EXPORTER_OTLP_ENDPOINT"

# OTLP SpanKind 枚举(protobuf Span.SpanKind)
_SPANK_KIND_INTERNAL = 1
_SPANK_KIND_CLIENT = 3

# OTLP StatusCode 枚举(protobuf Status.Code)
_STATUS_CODE_OK = 1
_STATUS_CODE_ERROR = 2


def _id_to_hex(raw: str | None) -> str | None:
    """把自研 ID(uuid hex 片段)规范化为小写 hex 字符串。

    本项目 span_id/trace_id 由 uuid4().hex[:16] 生成,本身就是合法 hex;
    此处仍做防御性校验:非法 hex 时回退为 UTF-8 字节 hex,保证输出恒为
    合法 hex 字符串(OTLP 要求)。空值返回 None(parentSpanId 省略场景)。
    """
    if not raw:
        return None
    try:
        return bytes.fromhex(raw).hex()
    except ValueError:
        return raw.encode("utf-8").hex()


def _ts_unix_nano(ts: float | None) -> str | None:
    """float 秒时间戳 → UnixNano 整数字符串(OTLP 以字符串承载 int64)。"""
    if ts is None:
        return None
    return str(int(ts * 1_000_000_000))


def _to_any_value(value: Any) -> dict[str, Any]:
    """Python 值 → OTLP AnyValue 单键包装(dict/list/标量递归转换)。"""
    if value is None:
        return {"stringValue": ""}
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}  # protobuf JSON 中 int64 用字符串
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, (list, tuple)):
        return {"arrayValue": {"values": [_to_any_value(v) for v in value]}}
    if isinstance(value, dict):
        return {"kvlistValue": {"values": _dict_to_kv(value)}}
    # 兜底:未知类型转字符串,绝不因序列化失败影响导出
    return {"stringValue": str(value)}


def _dict_to_kv(data: dict) -> list[dict[str, Any]]:
    """扁平 dict → OTLP KeyValue 数组([{"key","value"}])。"""
    out: list[dict[str, Any]] = []
    for k, v in data.items():
        out.append({"key": str(k), "value": _to_any_value(v)})
    return out


class OtlpHttpExporter:
    """把自研 Span 批量导出为 OTLP/HTTP JSON 的后台导出器。

    用法(通常无需手动创建——设置 FNIX_OTEL_EXPORTER_OTLP_ENDPOINT 后
    get_provider() 自动挂接):

        exporter = OtlpHttpExporter(endpoint="http://localhost:4318")
        provider.add_span_exporter(exporter)   # 实例可调用(__call__)
        ...
        provider.shutdown()                    # 进程退出时强制 flush
    """

    def __init__(
        self,
        endpoint: str = "",
        timeout: float = 5.0,
        flush_interval: float = 5.0,
        max_batch_size: int = 32,
        service_name: str = "fnixagent",
        warn_interval: float = 60.0,
    ):
        """初始化导出器。

        Args:
            endpoint: OTLP 基础地址(如 http://localhost:4318);
                为空时读环境变量 FNIX_OTEL_EXPORTER_OTLP_ENDPOINT,
                两者都为空则导出器处于禁用状态(所有调用零开销 no-op)。
            timeout: 单次 HTTP POST 超时秒数。
            flush_interval: 后台线程两次 flush 的最大间隔秒数。
            max_batch_size: 触发立即 flush 的队列长度阈值。
            service_name: resource.service.name 属性值。
            warn_interval: 失败 warning 限频间隔秒数。
        """
        self._endpoint = (endpoint or os.getenv(_ENV_ENDPOINT, "") or "").rstrip("/")
        self._timeout = float(timeout)
        self._flush_interval = float(flush_interval)
        self._max_batch_size = int(max_batch_size)
        self._service_name = service_name
        self._warn_interval = float(warn_interval)

        # 内存批量队列 + 锁;后台线程仅在启用时启动
        self._queue: list[dict[str, Any]] = []
        self._queue_lock = threading.Lock()
        self._wake = threading.Event()
        self._closed = False
        self._last_warn_ts = 0.0

        self.enabled = bool(self._endpoint)
        self._thread: threading.Thread | None = None
        if self.enabled:
            self._thread = threading.Thread(
                target=self._run,
                name="fnixagent-otlp-exporter",
                daemon=True,
            )
            self._thread.start()
            # 进程退出时尽力 flush 残留数据(daemon 线程不会自动收尾)
            atexit.register(self.shutdown)

    # -- 导出器协议(SpanExporter: Callable[[Span], None])--------------------

    def __call__(self, span: Span) -> None:
        """Span 结束回调:序列化并入队(满批唤醒后台线程)。"""
        self.export(span)

    def export(self, span: Span) -> None:
        """序列化单个 Span 快照并加入内存队列。

        序列化失败静默丢弃(限频 warning),不影响主流程;
        禁用状态下直接返回。
        """
        if not self.enabled or self._closed:
            return
        try:
            otlp_span = self._serialize_span(span)
        except Exception as exc:
            self._warn(f"otlp serialize failed: {exc}")
            return
        wake = False
        with self._queue_lock:
            self._queue.append(otlp_span)
            if len(self._queue) >= self._max_batch_size:
                wake = True
        if wake:
            self._wake.set()

    # -- flush / shutdown ----------------------------------------------------

    def flush(self, timeout: float = 10.0) -> bool:
        """同步把当前队列中的全部 Span POST 出去。

        Args:
            timeout: 本次发送的总超时秒数(仅用于 join 提示,HTTP 层
                使用构造时的 timeout)。

        Returns:
            是否全部发送成功(禁用/空队列视为成功)。
        """
        if not self.enabled:
            return True
        with self._queue_lock:
            batch = self._queue
            self._queue = []
        if not batch:
            return True
        return self._post_batch(batch)

    def shutdown(self, timeout: float = 5.0) -> None:
        """停止后台线程并 flush 残留数据(幂等,atexit 兜底调用)。"""
        if not self.enabled or self._closed:
            return
        self._closed = True
        self._wake.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        try:
            self.flush()
        except Exception as exc:  # atexit 阶段绝不允许抛异常
            self._warn(f"otlp shutdown flush failed: {exc}")

    # -- 内部实现 --------------------------------------------------------------

    def _run(self) -> None:
        """后台线程主循环:每 flush_interval 或被唤醒时 flush 一次。"""
        while not self._closed:
            self._wake.wait(self._flush_interval)
            self._wake.clear()
            if self._closed:
                break
            try:
                self.flush()
            except Exception as exc:
                self._warn(f"otlp periodic flush failed: {exc}")

    def _post_batch(self, batch: list[dict[str, Any]]) -> bool:
        """把一批已序列化的 Span 组装为 OTLP JSON 并同步 POST。"""
        body = self._build_request_body(batch)
        url = f"{self._endpoint}/v1/traces"
        try:
            import httpx

            resp = httpx.post(
                url,
                content=json.dumps(body, ensure_ascii=False),
                headers={"Content-Type": "application/json"},
                timeout=self._timeout,
            )
            if resp.status_code >= 400:
                self._warn(f"otlp export HTTP {resp.status_code} ({url})")
                return False
            return True
        except Exception as exc:
            # 网络/超时/依赖缺失等一切失败:静默降级,只留限频 warning
            self._warn(f"otlp export failed ({url}): {exc}")
            return False

    @staticmethod
    def _build_request_body(spans: list[dict[str, Any]]) -> dict[str, Any]:
        """组装 OTLP ExportTraceServiceRequest JSON(resourceSpans 结构)。"""
        return {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": _dict_to_kv(
                            {
                                "service.name": "fnixagent",
                                "telemetry.sdk.name": "fnixagent",
                                "telemetry.sdk.language": "python",
                            }
                        )
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "fnixagent.tracing", "version": "1.0.0"},
                            "spans": spans,
                        }
                    ],
                }
            ]
        }

    def _serialize_span(self, span: Span) -> dict[str, Any]:
        """自研 Span 快照 → OTLP span JSON dict。

        字段映射:
            span_id     → spanId(hex)
            trace_id    → traceId(hex)
            parent_id   → parentSpanId(hex,根 Span 省略该键)
            name        → name
            started_at  → startTimeUnixNano(纳秒字符串)
            ended_at    → endTimeUnixNano(纳秒字符串,未结束省略)
            status/data → attributes + status(code/message)
        """
        attributes: dict[str, Any] = {}
        if span.data is not None:
            # SpanData 结构化数据平铺为属性(带 fnix.span.type 类型标记)
            data_dict = getattr(span.data, "__dict__", {})
            for k, v in data_dict.items():
                if k == "span_type":
                    continue
                attributes[f"fnix.span.{k}"] = v
            attributes["fnix.span.type"] = getattr(span.data, "span_type", "custom")
        for k, v in (span.attributes or {}).items():
            # 用户显式 attributes 优先级更高(不覆盖已有键)
            attributes.setdefault(str(k), v)

        otlp: dict[str, Any] = {
            "traceId": _id_to_hex(span.trace_id),
            "spanId": _id_to_hex(span.span_id),
            "name": span.name,
            # llm 调用视为 CLIENT(3),其余(agent/tool/guardrail/handoff/custom)
            # 视为 INTERNAL(1),对齐 OpenTelemetry SpanKind 语义
            "kind": _SPANK_KIND_CLIENT if span.data is not None and getattr(span.data, "span_type", "") == "llm" else _SPANK_KIND_INTERNAL,
            "startTimeUnixNano": _ts_unix_nano(span.started_at),
            "attributes": _dict_to_kv(attributes),
        }
        parent_hex = _id_to_hex(span.parent_id)
        if parent_hex:
            otlp["parentSpanId"] = parent_hex
        end_nano = _ts_unix_nano(span.ended_at)
        if end_nano is not None:
            otlp["endTimeUnixNano"] = end_nano

        # status:failed → ERROR(2) + message;其余 → OK(1)
        if span.status == "failed":
            otlp["status"] = {"code": _STATUS_CODE_ERROR, "message": span.error or ""}
        else:
            otlp["status"] = {"code": _STATUS_CODE_OK}
        return otlp

    def _warn(self, message: str) -> None:
        """限频 warning:任何导出失败只记日志,绝不向上抛。

        logging 默认不因格式化异常抛错(仅打印到 stderr),无需额外兜底。
        """
        now = time.monotonic()
        if now - self._last_warn_ts < self._warn_interval:
            return
        self._last_warn_ts = now
        _logger.warning("OtlpHttpExporter: %s", message)


__all__ = ["OtlpHttpExporter"]
