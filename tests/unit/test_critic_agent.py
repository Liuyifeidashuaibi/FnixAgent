"""CriticAgent 单元测试。

覆盖:
- _parse_verdict 四种策略 (整体/json块/括号配平/fail-safe)
- fail-soft-with-signal: 解析失败时 passed=True + score=-1.0 哨兵 (Spec 7 改造)
- _extract_first_json_object 嵌套处理
- _build_user_message 构造
- review 端到端 (mock LLM)

设计原则: 纯本地逻辑, LLM 调用用 mock。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from fnixagent.core.agent.critic import CriticAgent, CriticVerdict


class TestParseVerdict:
    def setup_method(self):
        self.critic = CriticAgent()

    def test_strategy1_plain_json(self):
        """策略 1: LLM 直接返回纯 JSON。"""
        raw = '{"passed": true, "score": 0.8, "issues": [], "suggestions": ["增加注释"]}'
        verdict = self.critic._parse_verdict(raw)
        assert verdict is not None
        assert verdict.passed is True
        assert verdict.score == 0.8
        assert verdict.suggestions == ["增加注释"]

    def test_strategy2_json_code_block(self):
        """策略 2: JSON 包装在 ```json ... ``` 中。"""
        raw = """```json
{"passed": false, "score": 0.3, "issues": ["语法错误"], "suggestions": []}
```"""
        verdict = self.critic._parse_verdict(raw)
        assert verdict is not None
        assert verdict.passed is False
        assert verdict.score == 0.3
        assert verdict.issues == ["语法错误"]

    def test_strategy3_json_embedded_in_text(self):
        """策略 3: JSON 嵌在自然语言中,用括号配平提取。"""
        raw = """审查完成。以下是结论:
{"passed": true, "score": 0.9, "issues": [], "suggestions": []}
以上是审查结果。"""
        verdict = self.critic._parse_verdict(raw)
        assert verdict is not None
        assert verdict.passed is True
        assert verdict.score == 0.9

    def test_strategy3_nested_json(self):
        """策略 3: 嵌套 JSON 对象,括号配平应正确提取。

        嵌套对象放在 extra field (model_config extra=ignore 会忽略),
        保持 issues/suggestions 为 list[str] 符合 Pydantic 类型校验。
        """
        raw = """结论:
{"passed": false, "score": 0.2, "issues": ["问题1"], "suggestions": [], "metadata": {"detail": "嵌套对象"}}
结束"""
        verdict = self.critic._parse_verdict(raw)
        assert verdict is not None
        assert verdict.passed is False
        assert verdict.score == 0.2
        assert verdict.issues == ["问题1"]

    def test_strategy4_failsafe_returns_soft_signal(self):
        """Spec 7 fail-soft-with-signal: 解析全失败时 passed=True + score=-1.0 哨兵。

        原 fail-closed (passed=False) 会被 work_pipeline 的 except 吞掉,
        形成"假装阻断实则静默放行"的最差组合。
        新设计: passed=True 不阻断, score=-1.0 让调用方可观测地知道"未审查"。
        """
        raw = "这不是 JSON, 也不是代码块, 就是普通文本"
        verdict = self.critic._parse_verdict(raw)
        assert verdict is not None
        assert verdict.passed is True, "fail-soft 应返回 passed=True (不阻断)"
        assert verdict.score == -1.0, "哨兵值 score=-1.0 表示审查未完成"
        assert "解析失败" in verdict.issues[0] or "审查未完成" in verdict.issues[0]

    def test_empty_raw_returns_none(self):
        assert self.critic._parse_verdict("") is None
        assert self.critic._parse_verdict("   ") is None
        assert self.critic._parse_verdict(None) is None

    def test_extra_fields_ignored(self):
        """Pydantic extra=ignore: LLM 输出多余字段应被忽略。"""
        raw = '{"passed": true, "score": 0.8, "extra_field": "ignored", "reasoning": "..."}'
        verdict = self.critic._parse_verdict(raw)
        assert verdict is not None
        assert verdict.passed is True

    def test_score_out_of_range_clamped(self):
        """Pydantic ge=-1.0 le=1.0: 超范围应验证失败,走 fail-soft。"""
        raw = '{"passed": true, "score": 1.5}'
        verdict = self.critic._parse_verdict(raw)
        # score=1.5 违反 le=1.0, 策略 1 失败; 无其他 JSON, 走 fail-soft
        assert verdict is not None
        assert verdict.passed is True  # fail-soft (不阻断)
        assert verdict.score == -1.0  # 哨兵值


class TestExtractFirstJsonObject:
    def test_simple_object(self):
        text = 'prefix {"a": 1} suffix'
        result = CriticAgent._extract_first_json_object(text)
        assert result == '{"a": 1}'

    def test_nested_object(self):
        text = '{"a": {"b": {"c": 1}}}'
        result = CriticAgent._extract_first_json_object(text)
        assert result == '{"a": {"b": {"c": 1}}}'

    def test_brace_in_string(self):
        """字符串中的 { } 不应影响括号配平。"""
        text = '{"note": "this has {braces} inside"}'
        result = CriticAgent._extract_first_json_object(text)
        assert result == '{"note": "this has {braces} inside"}'

    def test_escaped_quote_in_string(self):
        """转义引号不应结束字符串。"""
        text = '{"note": "say \\"hello\\""}'
        result = CriticAgent._extract_first_json_object(text)
        assert result == '{"note": "say \\"hello\\""}'

    def test_no_object(self):
        assert CriticAgent._extract_first_json_object("no json here") == ""
        assert CriticAgent._extract_first_json_object("") == ""

    def test_incomplete_object(self):
        """不完整的 { 应返回空。"""
        assert CriticAgent._extract_first_json_object('{"a": 1') == ""


class TestBuildUserMessage:
    def test_full_message(self):
        critic = CriticAgent()
        msg = critic._build_user_message(
            user_input="生成月度报告",
            artifacts=[{"path": "/tmp/report.docx", "name": "report.docx"}],
            tool_calls_summary=[{"name": "write_file", "success": True}],
            answer="已生成报告",
        )
        assert "月度报告" in msg
        assert "report.docx" in msg
        assert "write_file" in msg
        assert "已生成报告" in msg
        assert "JSON" in msg

    def test_minimal_message(self):
        critic = CriticAgent()
        msg = critic._build_user_message(
            user_input="测试",
            artifacts=[],
            tool_calls_summary=[],
            answer="",
        )
        assert "测试" in msg

    def test_long_input_truncated(self):
        critic = CriticAgent()
        long_input = "x" * 1000
        msg = critic._build_user_message(
            user_input=long_input,
            artifacts=[],
            tool_calls_summary=[],
            answer="",
        )
        # user_input 截断到 500
        assert msg.count("x") <= 500 + 10  # 允许少量额外 (如标题)


class TestReviewEndToEnd:
    @pytest.mark.asyncio
    async def test_review_with_mock_llm_success(self):
        """端到端: mock LLM 返回合法 JSON, review 应返回 verdict。"""
        critic = CriticAgent(llm_config={"api_key": "test", "model": "test"})
        mock_raw = '{"passed": true, "score": 0.85, "issues": [], "suggestions": ["很好"]}'
        with patch.object(critic, "_call_llm", new=AsyncMock(return_value=mock_raw)):
            verdict = await critic.review(
                user_input="生成报告",
                artifacts=[{"path": "/tmp/r.docx", "name": "r.docx"}],
                tool_calls_summary=[],
                answer="报告已生成",
            )
        assert verdict is not None
        assert verdict.passed is True
        assert verdict.score == 0.85

    @pytest.mark.asyncio
    async def test_review_with_mock_llm_parse_fail(self):
        """Spec 7: 端到端 mock LLM 返回非 JSON, review 应返回 fail-soft (passed=True, score=-1.0)。"""
        critic = CriticAgent(llm_config={"api_key": "test"})
        with patch.object(critic, "_call_llm", new=AsyncMock(return_value="这不是JSON")):
            verdict = await critic.review(
                user_input="生成报告",
                artifacts=[{"path": "/tmp/r.docx", "name": "r.docx"}],
                tool_calls_summary=[],
                answer="报告已生成",
            )
        assert verdict is not None
        assert verdict.passed is True, "fail-soft: 解析失败不阻断 (passed=True)"
        assert verdict.score == -1.0, "哨兵值 score=-1.0 表示审查未完成"

    @pytest.mark.asyncio
    async def test_review_no_artifacts_no_answer_returns_none(self):
        """无产物无回答时不审查。"""
        critic = CriticAgent()
        verdict = await critic.review(
            user_input="test",
            artifacts=[],
            tool_calls_summary=[],
            answer="",
        )
        assert verdict is None

    @pytest.mark.asyncio
    async def test_review_llm_exception_returns_none(self):
        """LLM 调用异常时返回 None, 不抛出。"""
        critic = CriticAgent(llm_config={"api_key": "test"})
        with patch.object(critic, "_call_llm", new=AsyncMock(side_effect=Exception("LLM down"))):
            verdict = await critic.review(
                user_input="test",
                artifacts=[{"path": "/x", "name": "x"}],
                tool_calls_summary=[],
                answer="x",
            )
        assert verdict is None

    @pytest.mark.asyncio
    async def test_review_empty_llm_response_returns_none(self):
        """LLM 返回空字符串时返回 None。"""
        critic = CriticAgent(llm_config={"api_key": "test"})
        with patch.object(critic, "_call_llm", new=AsyncMock(return_value="")):
            verdict = await critic.review(
                user_input="test",
                artifacts=[{"path": "/x", "name": "x"}],
                tool_calls_summary=[],
                answer="x",
            )
        assert verdict is None


class TestCriticVerdictModel:
    def test_required_fields(self):
        """passed 是必填字段 (无默认值), score/issues/suggestions 有默认值。"""
        v = CriticVerdict(passed=True)
        assert v.passed is True
        assert v.score == 0.5  # 默认值
        assert v.issues == []
        assert v.suggestions == []

    def test_score_boundary(self):
        """Spec 7: score 约束 ge=-1.0 le=1.0 (允许 -1.0 哨兵值)。"""
        CriticVerdict(passed=True, score=0.0)
        CriticVerdict(passed=True, score=1.0)
        CriticVerdict(passed=True, score=-1.0)  # 哨兵值, Spec 7 改造后允许
        with pytest.raises(Exception):
            CriticVerdict(passed=True, score=-1.1)  # 低于 -1.0 仍违法
        with pytest.raises(Exception):
            CriticVerdict(passed=True, score=1.1)

    def test_passed_required(self):
        """passed 字段必填, 不传应报错。"""
        with pytest.raises(Exception):
            CriticVerdict()

    def test_extra_fields_ignored(self):
        v = CriticVerdict.model_validate({"passed": True, "score": 0.8, "extra": "x"})
        assert v.passed is True
