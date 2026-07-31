from fnixagent.services.llm_policy import normalize_llm_model


def test_normalize_qwen37_alias() -> None:
    assert normalize_llm_model("qwen3.7-plus", "qwen") == "qwen-plus"
    assert normalize_llm_model("qwen-plus-2025-07-28", "qwen") == "qwen-plus-2025-07-28"
    assert normalize_llm_model("qwen-plus", "qwen") == "qwen-plus"
