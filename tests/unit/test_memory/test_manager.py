"""
单元测试 - Memory 测试。

测试真实接口:
  - ShortTermMemory.add(message) / get_messages()
  - EntityMemory.upsert(entity) / get(type, name) / list_by_type(type)
  - MemoryManager.save() / load_context()
"""

import pytest

from fnixagent.core.memory.entity import EntityMemory
from fnixagent.core.memory.manager import MemoryManager
from fnixagent.core.memory.short_term import ShortTermMemory
from fnixagent.core.types import Entity, Message, MessageRole

# ---------------------------------------------------------------------------
# ShortTermMemory
# ---------------------------------------------------------------------------


def test_short_term_add_and_get():
    """测试短期记忆添加与获取。"""
    stm = ShortTermMemory(max_tokens=6000, max_messages=20)

    msg1 = Message(role=MessageRole.USER, content="帮我搜论文")
    msg2 = Message(role=MessageRole.ASSISTANT, content="已找到3篇论文")

    stm.add(msg1)
    stm.add(msg2)

    messages = stm.get_messages()
    assert len(messages) == 2
    assert messages[0].content == "帮我搜论文"
    assert messages[1].content == "已找到3篇论文"


def test_short_term_sliding_window():
    """测试短期记忆滑动窗口(超限时裁剪)。"""
    stm = ShortTermMemory(max_tokens=100, max_messages=3)

    for i in range(10):
        stm.add(Message(role=MessageRole.USER, content=f"消息{i}"))

    messages = stm.get_messages()
    # 应只保留最近 3 条(max_messages)
    assert len(messages) <= 3


def test_short_term_set_messages():
    """测试替换全部消息。"""
    stm = ShortTermMemory()

    msgs = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="hello"),
    ]
    stm.set_messages(msgs)

    assert len(stm.get_messages()) == 2


# ---------------------------------------------------------------------------
# EntityMemory
# ---------------------------------------------------------------------------


def test_entity_upsert_and_get():
    """测试实体记忆写入与查询。"""
    em = EntityMemory()

    em.upsert(
        Entity(
            entity_type="paper",
            name="paper_001",
            attributes={"title": "Deep Learning", "year": 2023},
        )
    )

    result = em.get("paper", "paper_001")
    assert result is not None
    assert result.attributes["title"] == "Deep Learning"
    assert result.attributes["year"] == 2023


def test_entity_list_by_type():
    """测试按类型列出实体。"""
    em = EntityMemory()

    em.upsert(Entity(entity_type="paper", name="p1", attributes={"title": "A"}))
    em.upsert(Entity(entity_type="paper", name="p2", attributes={"title": "B"}))
    em.upsert(Entity(entity_type="note", name="n1", attributes={"title": "N"}))

    papers = em.list_by_type("paper")
    assert len(papers) == 2

    notes = em.list_by_type("note")
    assert len(notes) == 1


def test_entity_update():
    """测试实体更新(upsert 同名覆盖)。"""
    em = EntityMemory()

    em.upsert(Entity(entity_type="paper", name="p1", attributes={"title": "Old"}))
    em.upsert(Entity(entity_type="paper", name="p1", attributes={"title": "New"}))

    result = em.get("paper", "p1")
    assert result.attributes["title"] == "New"


def test_entity_not_found():
    """测试查询不存在的实体。"""
    em = EntityMemory()
    assert em.get("paper", "nonexistent") is None


# ---------------------------------------------------------------------------
# MemoryManager
# ---------------------------------------------------------------------------


def test_memory_manager_init():
    """测试记忆管理器初始化。"""
    mgr = MemoryManager()
    assert mgr._short is not None
    assert mgr._long is not None
    assert mgr._entity is not None


def test_memory_manager_save_and_load():
    """测试记忆管理器保存与加载。"""
    mgr = MemoryManager()

    msg = Message(role=MessageRole.USER, content="帮我搜索论文")
    mgr.save(session_id="test_session", message=msg, user_id="test_user")

    # 加载上下文
    context = mgr.load_context(
        query="论文",
        user_id="test_user",
    )

    assert "short_term" in context
    assert len(context["short_term"]) >= 1


def test_memory_manager_reset():
    """测试记忆重置。"""
    mgr = MemoryManager()

    mgr.save(
        session_id="s1",
        message=Message(role=MessageRole.USER, content="test"),
        user_id="u1",
    )

    mgr.reset()

    # 重置后短期记忆应为空
    assert len(mgr._short.get_messages()) == 0


def test_memory_manager_stats():
    """测试记忆管理器统计。"""
    mgr = MemoryManager()

    for i in range(5):
        mgr.save(
            session_id="s1",
            message=Message(role=MessageRole.USER, content=f"msg{i}"),
            user_id="u1",
        )

    stats = mgr.get_stats()
    assert isinstance(stats, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
