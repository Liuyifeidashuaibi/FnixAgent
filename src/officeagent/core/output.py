"""LLM 输出处理器(借鉴 PydanticAI OutputProcessor)。

提供通用的输出校验 + 重试 + 降级框架:
  - OutputSchema:     包装 Pydantic Model,提供 validate 方法
  - OutputProcessor:  处理 LLM 输出文本(校验 + 错误反馈 + 重试)
  - OutputValidationError: 校验失败异常

工作流(在 reasoning/base.py 的 _call_llm 中使用):
  1. LLM 调用,返回 text
  2. OutputProcessor.process(text) 尝试校验
  3. 校验失败 → format_error_feedback(error) 生成反馈
  4. 将反馈追加到 prompt,重试 LLM 调用(最多 N 次)
  5. N 次仍失败 → 降级为 text 模式 + 告警

与 core/reasoning/schemas.py 关系:
  - schemas.py 定义具体的 Pydantic Model(ToolCallDecision/PlanOutput/FinalAnswer)
  - output.py 提供通用的校验/重试/降级框架

性能/健壮性优化:
  - _extract_json 用栈式括号匹配,正确处理嵌套 JSON
  - 字符串内的括号不参与计数(避免 "key": "}" 误判闭合)
  - process_with_retry 封装"LLM 调用 + 校验 + 重试"完整循环
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Generic, Optional, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------

class OutputValidationError(Exception):
    """LLM 输出校验失败异常。

    携带原始文本与校验错误详情,供重试逻辑使用。
    """

    def __init__(
        self,
        message: str,
        *,
        raw_text: str = "",
        validation_error: Optional[ValidationError] = None,
    ) -> None:
        self.raw_text = raw_text
        self.validation_error = validation_error
        super().__init__(message)


# ---------------------------------------------------------------------------
# OutputSchema
# ---------------------------------------------------------------------------

@dataclass
class OutputSchema(Generic[T]):
    """输出 Schema 包装器(包装 Pydantic Model)。

    提供统一的 validate 接口,内部处理 JSON 解析 + Pydantic 校验。

    用法:
        schema = OutputSchema(model_type=ToolCallDecision)
        result = schema.validate(llm_output_text)  # → ToolCallDecision 或抛异常
    """
    model_type: type[T]

    def validate(self, text: str) -> T:
        """校验 LLM 输出文本。

        步骤:
          1. 尝试 JSON 解析(text → dict)
          2. Pydantic 校验(dict → model_type 实例)

        Args:
            text: LLM 输出文本(应为 JSON 格式)

        Returns:
            校验成功的 Model 实例

        Raises:
            OutputValidationError: JSON 解析失败或 Pydantic 校验失败
        """
        # 参数校验(public API)
        if not isinstance(text, str):
            raise OutputValidationError(
                f"text 必须为 str,实际: {type(text).__name__}",
                raw_text=text if isinstance(text, str) else "",
            )

        # 尝试提取 JSON(LLM 可能在 JSON 外包裹 markdown ```json ... ```)
        json_text = self._extract_json(text)
        if json_text is None:
            raise OutputValidationError(
                f"无法从 LLM 输出中提取 JSON: {text[:200]}",
                raw_text=text,
            )

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            raise OutputValidationError(
                f"JSON 解析失败: {e}",
                raw_text=text,
            )

        try:
            return self.model_type.model_validate(data)
        except ValidationError as e:
            raise OutputValidationError(
                f"Pydantic 校验失败: {e}",
                raw_text=text,
                validation_error=e,
            )

    def safe_validate(self, text: str) -> Optional[T]:
        """安全校验(不抛异常,失败返回 None)。"""
        try:
            return self.validate(text)
        except OutputValidationError:
            return None

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """从 LLM 输出中提取 JSON 文本。

        处理以下情况:
          1. 纯 JSON: {"key": "value"}
          2. markdown 包裹: ```json\n{...}\n```
          3. markdown 包裹(无语言): ```\n{...}\n```
          4. JSON 前后有多余文本: 提取第一个 {...} 块

        优化(BUG 修复):
          原实现在情况 4 用括号计数,但未跳过字符串内的括号,
          导致 {"k": "}"} 这类字符串含闭合括号的 JSON 提前截断。
          现加入字符串扫描(跳过 "..." 内的字符),正确处理嵌套与转义。
        """
        if not text:
            return None
        text = text.strip()

        # 情况 2: ```json ... ```
        if text.startswith("```json"):
            lines = text.split("\n")
            if len(lines) >= 2:
                # 去掉首行 ```json 和末行 ```
                inner = "\n".join(lines[1:])
                if inner.endswith("```"):
                    inner = inner[:-3].strip()
                return inner

        # 情况 3: ``` ... ```
        if text.startswith("```"):
            lines = text.split("\n")
            if len(lines) >= 2:
                inner = "\n".join(lines[1:])
                if inner.endswith("```"):
                    inner = inner[:-3].strip()
                return inner

        # 情况 1: 纯 JSON
        if text.startswith("{") or text.startswith("["):
            return text

        # 情况 4: 提取第一个 {...} 或 [...] 块(栈式匹配,跳过字符串内括号)
        for i, ch in enumerate(text):
            if ch in "{[":
                open_ch = ch
                close_ch = "}" if ch == "{" else "]"
                depth = 0
                in_string = False
                escape = False
                for j in range(i, len(text)):
                    c = text[j]
                    if in_string:
                        if escape:
                            escape = False
                        elif c == "\\":
                            escape = True
                        elif c == '"':
                            in_string = False
                        # 字符串内的其他字符(含括号)一律跳过
                        continue
                    # 非字符串状态
                    if c == '"':
                        in_string = True
                    elif c == open_ch:
                        depth += 1
                    elif c == close_ch:
                        depth -= 1
                        if depth == 0:
                            return text[i:j + 1]
                break

        return None


# ---------------------------------------------------------------------------
# OutputProcessor
# ---------------------------------------------------------------------------

@dataclass
class OutputProcessor(Generic[T]):
    """输出处理器:校验 + 错误反馈 + 重试协调。

    与 ReasoningEngine._call_llm 配合:
      1. LLM 调用 → text
      2. processor.process(text) → T 或 OutputValidationError
      3. 失败时 processor.format_error_feedback(error) → 反馈文本
      4. 反馈追加到 prompt,重试 LLM 调用

    用法(手动重试):
        processor = OutputProcessor(model_type=ToolCallDecision)
        for attempt in range(max_retries):
            text = llm.chat(prompt)
            try:
                result = processor.process(text)
                break
            except OutputValidationError as e:
                feedback = processor.format_error_feedback(e)
                prompt += f"\\n\\n上次输出有误: {feedback}"
        else:
            # 降级为 text 模式
            result = None

    用法(自动重试,推荐):
        result = processor.process_with_retry(
            llm_call=lambda prompt: llm.chat(prompt),
            initial_prompt=prompt,
            max_retries=3,
        )
    """
    model_type: type[T]

    def process(self, text: str) -> T:
        """处理 LLM 输出文本(校验)。"""
        schema = OutputSchema(model_type=self.model_type)
        return schema.validate(text)

    def safe_process(self, text: str) -> Optional[T]:
        """安全处理(失败返回 None)。"""
        schema = OutputSchema(model_type=self.model_type)
        return schema.safe_validate(text)

    def format_error_feedback(self, error: OutputValidationError) -> str:
        """生成错误反馈文本(供重试时追加到 prompt)。

        包含:
          - 错误类型(JSON 解析失败 / 字段缺失 / 类型错误等)
          - 具体校验错误(来自 Pydantic ValidationError)
          - 原始输出预览(前 200 字符)
        """
        lines: list[str] = [
            "你的上次输出格式有误,请重新返回严格符合 Schema 的 JSON:",
            f"错误: {error}",
        ]
        if error.validation_error is not None:
            for err in error.validation_error.errors():
                loc = ".".join(str(x) for x in err.get("loc", []))
                msg = err.get("msg", "")
                lines.append(f"  - 字段 '{loc}': {msg}")
        if error.raw_text:
            preview = error.raw_text[:200]
            if len(error.raw_text) > 200:
                preview += "..."
            lines.append(f"原始输出预览: {preview}")
        return "\n".join(lines)

    def process_with_retry(
        self,
        llm_call: Callable[[str], str],
        initial_prompt: str,
        max_retries: int = 3,
    ) -> Optional[T]:
        """带重试的输出处理(封装"LLM 调用 + 校验 + 反馈"完整循环)。

        Args:
            llm_call: 同步 LLM 调用函数,接收 prompt,返回 text
            initial_prompt: 初始 prompt
            max_retries: 最大重试次数(总调用次数 = max_retries + 1)

        Returns:
            校验成功的 Model 实例;全部重试失败返回 None(降级)
        """
        if max_retries < 0:
            raise ValueError(
                f"max_retries 不能为负,实际: {max_retries}"
            )
        prompt = initial_prompt
        last_error: Optional[OutputValidationError] = None
        for attempt in range(max_retries + 1):
            try:
                text = llm_call(prompt)
            except Exception:
                # LLM 调用本身失败,直接降级(不重试 LLM 异常)
                return None
            try:
                return self.process(text)
            except OutputValidationError as e:
                last_error = e
                # 把错误反馈追加到 prompt,供下一轮 LLM 修正
                feedback = self.format_error_feedback(e)
                prompt = (
                    f"{initial_prompt}\n\n"
                    f"上次输出有误(第 {attempt + 1} 次): {feedback}"
                )
        # 全部重试失败,降级返回 None(上层可记录 last_error 用于告警)
        _ = last_error  # 保留引用供未来扩展(如日志/告警)
        return None


# ---------------------------------------------------------------------------
# 便捷别名
# ---------------------------------------------------------------------------

class ObjectOutputProcessor(OutputProcessor[T]):
    """对象输出处理器(OutputProcessor 的语义化别名)。

    用于校验返回单个 Pydantic Model 对象的 LLM 输出。
    """
    pass


# ---------------------------------------------------------------------------
# 预定义处理器(对应 schemas.py 的 4 个 Model)
# ---------------------------------------------------------------------------

def tool_call_decision_processor() -> ObjectOutputProcessor:
    """ReAct 单步决策处理器。"""
    from officeagent.core.reasoning.schemas import ToolCallDecision
    return ObjectOutputProcessor(model_type=ToolCallDecision)


def plan_output_processor() -> ObjectOutputProcessor:
    """Plan&Execute 计划处理器。"""
    from officeagent.core.reasoning.schemas import PlanOutput
    return ObjectOutputProcessor(model_type=PlanOutput)


def final_answer_processor() -> ObjectOutputProcessor:
    """最终答案处理器。"""
    from officeagent.core.reasoning.schemas import FinalAnswer
    return ObjectOutputProcessor(model_type=FinalAnswer)
