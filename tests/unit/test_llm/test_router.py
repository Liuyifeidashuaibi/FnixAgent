"""
单元测试 - LLM Router 测试。

测试真实接口:
  - router.register(provider, weight)
  - router.chat(request)  (非 route)
  - router.providers (property)
"""
import pytest

from officeagent.core.llm.base import BaseLLMProvider, LLMRequest
from officeagent.core.llm.router import LLMRouter, RouteStrategy
from officeagent.core.llm.providers.openai_compat import MockLLMProvider
from officeagent.core.types import LLMResponse, Message, MessageRole, TokenUsage


def test_router_register():
    """测试路由器注册。"""
    router = LLMRouter()
    provider = MockLLMProvider()

    router.register(provider, weight=1.0)

    assert "mock" in router.providers
    assert len(router.providers) == 1


def test_router_chat():
    """测试路由器调用 chat。"""
    router = LLMRouter()
    provider = MockLLMProvider()
    router.register(provider)

    request = LLMRequest(
        messages=[Message(role=MessageRole.USER, content="你好")],
    )
    response = router.chat(request)

    assert isinstance(response, LLMResponse)
    assert response.content  # 非空
    assert response.usage.total_tokens > 0


def test_router_multiple_providers():
    """测试多 Provider 注册。"""
    router = LLMRouter(strategy=RouteStrategy.ROUND_ROBIN)

    p1 = MockLLMProvider(name="mock1", model_name="m1")
    p2 = MockLLMProvider(name="mock2", model_name="m2")
    router.register(p1, weight=2.0)
    router.register(p2, weight=1.0)

    assert len(router.providers) == 2
    assert "mock1" in router.providers
    assert "mock2" in router.providers


def test_router_get_stats():
    """测试路由器统计。"""
    router = LLMRouter()
    provider = MockLLMProvider()
    router.register(provider)

    request = LLMRequest(
        messages=[Message(role=MessageRole.USER, content="测试")],
    )
    router.chat(request)

    stats = router.get_stats()
    assert "strategy" in stats
    assert "providers" in stats
    assert "mock" in stats["providers"]
    assert stats["providers"]["mock"]["total_calls"] == 1


def test_router_no_provider():
    """测试无 Provider 时抛异常。"""
    router = LLMRouter()

    request = LLMRequest(
        messages=[Message(role=MessageRole.USER, content="test")],
    )
    # 没有 provider, _select 返回 None, 应抛 LLMCircuitOpenError
    from officeagent.core.exceptions import LLMCircuitOpenError
    with pytest.raises(LLMCircuitOpenError):
        router.chat(request)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
