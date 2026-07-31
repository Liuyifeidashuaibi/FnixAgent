"""
集成测试 - 端到端 Agent 调度流程。

验证 services.build_scheduler() 构建的完整调度器能否:
  1. 正常初始化所有引擎
  2. 注册业务工具
  3. 处理用户请求(使用 MockLLMProvider)
  4. 返回 AgentResponse
"""

import os
import sys

import pytest

# 确保无 API Key 时使用 MockLLMProvider
os.environ.pop("GLM_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("QWEN_API_KEY", None)

# 确保 src 在路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from fnixagent.core.orchestrator.scheduler import AgentResponse, AgentScheduler
from fnixagent.services import build_scheduler, reset_scheduler


@pytest.fixture
def scheduler(monkeypatch):
    """构建测试用调度器(每次测试重建)。

    防止加载 .env 文件污染测试环境(避免注册真实 LLM provider)。
    """
    try:
        import dotenv

        monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **kw: None)
    except ImportError:
        pass
    reset_scheduler()
    s = build_scheduler()
    yield s
    reset_scheduler()


class TestSchedulerBuild:
    """测试调度器构建。"""

    def test_build_returns_scheduler(self, scheduler):
        """build_scheduler 应返回 AgentScheduler 实例。"""
        assert isinstance(scheduler, AgentScheduler)

    def test_scheduler_has_engines(self, scheduler):
        """调度器应包含所有核心引擎。"""
        ctx = scheduler._ctx
        assert ctx.llm_router is not None
        assert ctx.memory_manager is not None
        assert ctx.tool_registry is not None
        assert ctx.tool_executor is not None
        assert ctx.security_engine is not None
        assert ctx.prompt_manager is not None
        assert ctx.reasoning_selector is not None
        assert ctx.validator is not None
        assert ctx.replanner is not None

    def test_llm_has_mock_provider(self, scheduler):
        """无 API Key 时应回退到 MockLLMProvider。"""
        ctx = scheduler._ctx
        assert "mock" in ctx.llm_router.providers

    def test_business_tools_registered(self, scheduler):
        """业务工具应已注册。"""
        ctx = scheduler._ctx
        # 至少注册了论文检索 + Word + 格式转换
        assert ctx.tool_registry.count >= 7

        # 检查关键工具
        assert ctx.tool_registry.has("search_arxiv")
        assert ctx.tool_registry.has("search_paper")
        assert ctx.tool_registry.has("create_docx")
        assert ctx.tool_registry.has("convert_document")


class TestSchedulerProcess:
    """测试调度器处理请求。"""

    def test_process_returns_response(self, scheduler):
        """process 应返回 AgentResponse。"""
        response = scheduler.process(
            user_input="你好",
            session_id="test_session",
            user_id="test_user",
        )

        assert isinstance(response, AgentResponse)
        assert response.final_answer  # 非空
        assert response.duration_ms > 0

    def test_process_with_tool_query(self, scheduler):
        """包含工具意图的请求应能处理。"""
        response = scheduler.process(
            user_input="帮我搜索深度学习论文",
            session_id="test_session_2",
            user_id="test_user",
        )

        assert isinstance(response, AgentResponse)
        # MockLLM 会返回包含 [Mock LLM] 的响应
        assert len(response.final_answer) > 0

    def test_process_stats(self, scheduler):
        """调度器应返回统计信息。"""
        stats = scheduler.get_stats()
        assert "llm" in stats
        assert "memory" in stats
        assert "tools" in stats
        assert stats["tools"]["count"] >= 7


class TestSchedulerSession:
    """测试会话管理。"""

    def test_reset_session(self, scheduler):
        """重置会话应清空短期记忆。"""
        ctx = scheduler._ctx

        # 先保存一些记忆
        from fnixagent.core.types import Message, MessageRole

        ctx.memory_manager.save(
            session_id="s1",
            message=Message(role=MessageRole.USER, content="test"),
            user_id="u1",
        )

        # 重置
        scheduler.reset_session()

        # 短期记忆应清空
        assert len(ctx.memory_manager._short.get_messages()) == 0


class TestArxivParser:
    """测试 arXiv XML 解析器。"""

    def test_parse_empty_xml(self):
        """空 XML 应返回空列表。"""
        from fnixagent.business.search.arxiv import parse_arxiv_response

        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom"></feed>"""
        papers = parse_arxiv_response(xml)
        assert papers == []

    def test_parse_single_paper(self):
        """解析单篇论文。"""
        from fnixagent.business.search.arxiv import parse_arxiv_response

        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/2301.00001v1</id>
            <title>Deep Learning for NLP</title>
            <author><name>Alice</name></author>
            <author><name>Bob</name></author>
            <summary>This paper presents a novel approach.</summary>
            <published>2023-01-15T00:00:00Z</published>
            <link href="http://arxiv.org/pdf/2301.00001v1" title="pdf" type="application/pdf"/>
          </entry>
        </feed>"""

        papers = parse_arxiv_response(xml)
        assert len(papers) == 1

        p = papers[0]
        assert p["id"] == "2301.00001"
        assert p["title"] == "Deep Learning for NLP"
        assert p["authors"] == ["Alice", "Bob"]
        assert p["abstract"] == "This paper presents a novel approach."
        assert p["published"] == "2023-01-15"
        assert p["pdf_url"] == "http://arxiv.org/pdf/2301.00001v1"

    def test_parse_multiple_papers(self):
        """解析多篇论文。"""
        from fnixagent.business.search.arxiv import parse_arxiv_response

        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/2301.00001v1</id>
            <title>Paper One</title>
            <summary>Abstract one</summary>
          </entry>
          <entry>
            <id>http://arxiv.org/abs/2301.00002v1</id>
            <title>Paper Two</title>
            <summary>Abstract two</summary>
          </entry>
        </feed>"""

        papers = parse_arxiv_response(xml)
        assert len(papers) == 2
        assert papers[0]["title"] == "Paper One"
        assert papers[1]["title"] == "Paper Two"


class TestDeduplication:
    """测试论文去重。"""

    def test_dedup_by_title(self):
        """标题相同应去重。"""
        from fnixagent.business.search.arxiv import deduplicate_papers

        papers = [
            {"id": "1", "title": "Deep Learning", "source": "arxiv", "abstract": "A"},
            {"id": "2", "title": "Deep Learning", "source": "semantic_scholar", "year": 2023},
        ]

        result = deduplicate_papers(papers)
        assert len(result) == 1
        # 应合并信息
        assert result[0].get("abstract") == "A"
        assert result[0].get("year") == 2023
        assert len(result[0]["sources"]) == 2

    def test_dedup_by_id(self):
        """ID 相同应去重。"""
        from fnixagent.business.search.arxiv import deduplicate_papers

        papers = [
            {"id": "2301.00001", "title": "Paper A", "source": "arxiv"},
            {"id": "2301.00001", "title": "Paper A Updated", "source": "semantic_scholar"},
        ]

        result = deduplicate_papers(papers)
        assert len(result) == 1

    def test_no_dedup_different_papers(self):
        """不同论文不应被去重。"""
        from fnixagent.business.search.arxiv import deduplicate_papers

        papers = [
            {"id": "1", "title": "Paper A", "source": "arxiv"},
            {"id": "2", "title": "Paper B", "source": "arxiv"},
        ]

        result = deduplicate_papers(papers)
        assert len(result) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
