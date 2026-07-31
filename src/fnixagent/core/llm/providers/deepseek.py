"""
DeepSeek LLM Provider。

基于 DeepSeek V4 系列(deepseek-v4-flash / deepseek-v4-pro),
完全兼容 OpenAI Chat Completions API。

模型选型:
  - deepseek-v4-flash: 284B MoE(13B active), 高速低成本, 适合日常对话/工具调用
  - deepseek-v4-pro:   1.6T MoE(49B active), 旗舰推理, 适合复杂逻辑/数学/代码

注意:
  - base_url: https://api.deepseek.com (无需 /v1 后缀,SDK 内部处理)
  - legacy 别名 deepseek-chat / deepseek-reasoner 将于 2026/07/24 退役
  - 支持 Function Calling / JSON Mode / Streaming / Thinking 推理模式

用法:
    provider = DeepSeekProvider(
        api_key="your-key",
        model_name="deepseek-v4-flash",
    )
    router.register(provider, weight=2.0)
"""

from __future__ import annotations

from fnixagent.core.llm.providers.openai import OpenAICompatibleProvider


class DeepSeekProvider(OpenAICompatibleProvider):
    """
    DeepSeek V4 Provider。

    继承 OpenAICompatibleProvider 的全部能力(重试/熔断/缓存),
    仅覆写 base_url 与默认模型名。
    """

    def __init__(
        self,
        api_key: str = "",
        model_name: str = "deepseek-v4-flash",
        **kwargs,
    ):
        """初始化 DeepSeek Provider。

        Args:
            api_key: DeepSeek API Key(从 platform.deepseek.com 获取)。
            model_name: 模型名,deepseek-v4-flash(默认) 或 deepseek-v4-pro。
            **kwargs: 透传给 OpenAICompatibleProvider(timeout/max_retries 等)。

        Raises:
            TypeError: kwargs 中 timeout/max_retries 类型错误。
            ValueError: timeout 非正或 max_retries 为负。
        """
        super().__init__(
            name="deepseek",
            model_name=model_name,
            api_key=api_key,
            base_url="https://api.deepseek.com",
            **kwargs,
        )
