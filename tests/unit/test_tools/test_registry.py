"""
单元测试 - Tool Registry 测试。

测试真实接口:
  - registry.register(metadata, func)
  - registry.get(name) / registry.has(name)
  - registry.list_tools(category)
  - registry.list_for_llm()
  - registry.unregister(name)
  - registry.count
"""

import pytest

from fnixagent.core.exceptions import ToolNotFoundError
from fnixagent.core.tools.protocol import ToolMetadata
from fnixagent.core.tools.registry import ToolRegistry


def test_registry_init():
    """测试注册中心初始化。"""
    registry = ToolRegistry()
    assert registry.count == 0


def test_registry_register():
    """测试工具注册。"""
    registry = ToolRegistry()

    metadata = ToolMetadata(
        name="test_tool",
        description="测试工具",
        category="test",
        input_schema={"type": "object"},
    )

    def test_func(args: dict) -> dict:
        return {"result": "success"}

    registry.register(metadata, test_func)

    assert registry.count == 1
    assert registry.has("test_tool")


def test_registry_decorator():
    """测试装饰器注册。"""
    registry = ToolRegistry()

    @registry.tool("decorated_tool", "装饰器工具", category="test")
    def decorated_func(args: dict) -> dict:
        return {"decorated": True}

    assert registry.has("decorated_tool")
    tool = registry.get("decorated_tool")
    result = tool.func({})
    assert result["decorated"] is True


def test_registry_get():
    """测试工具获取。"""
    registry = ToolRegistry()

    metadata = ToolMetadata(name="get_tool", description="获取测试", category="test")
    registry.register(metadata, lambda x: x)

    tool = registry.get("get_tool")
    assert tool is not None
    assert tool.metadata.name == "get_tool"


def test_registry_not_found():
    """测试工具不存在。"""
    registry = ToolRegistry()

    with pytest.raises(ToolNotFoundError):
        registry.get("unknown_tool")


def test_registry_list_tools_by_category():
    """测试按分类查询 (list_tools)。"""
    registry = ToolRegistry()

    for i in range(5):
        metadata = ToolMetadata(
            name=f"tool_{i}",
            description=f"工具{i}",
            category="search" if i < 3 else "word",
        )
        registry.register(metadata, lambda x: x)

    search_tools = registry.list_tools(category="search")
    assert len(search_tools) == 3

    word_tools = registry.list_tools(category="word")
    assert len(word_tools) == 2

    all_tools = registry.list_tools()
    assert len(all_tools) == 5


def test_registry_list_for_llm():
    """测试生成 LLM 工具描述 (list_for_llm)。"""
    registry = ToolRegistry()

    metadata1 = ToolMetadata(
        name="search",
        description="搜索工具",
        category="search",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    metadata2 = ToolMetadata(
        name="create",
        description="创建工具",
        category="word",
        input_schema={"type": "object"},
    )

    registry.register(metadata1, lambda x: x)
    registry.register(metadata2, lambda x: x)

    descriptions = registry.list_for_llm()

    assert len(descriptions) == 2
    names = [d["function"]["name"] for d in descriptions]
    assert "search" in names
    assert "create" in names


def test_registry_unregister():
    """测试工具注销。"""
    registry = ToolRegistry()

    metadata = ToolMetadata(name="unregister_tool", description="注销测试", category="test")
    registry.register(metadata, lambda x: x)

    result = registry.unregister("unregister_tool")
    assert result is True
    assert not registry.has("unregister_tool")


def test_registry_count():
    """测试 count 属性。"""
    registry = ToolRegistry()

    assert registry.count == 0

    for i in range(10):
        metadata = ToolMetadata(name=f"tool_{i}", description=f"工具{i}", category="test")
        registry.register(metadata, lambda x: x)

    assert registry.count == 10


def test_registry_clear():
    """测试清空。"""
    registry = ToolRegistry()

    for i in range(5):
        metadata = ToolMetadata(name=f"tool_{i}", description=f"工具{i}", category="test")
        registry.register(metadata, lambda x: x)

    registry.clear()
    assert registry.count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
