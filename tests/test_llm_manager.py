"""单元测试 — LLM 管理器"""

import pytest
from app.core.llm import LlmManager, MODEL_REGISTRY, ModelAlias


class TestLlmManager:

    def test_resolve_deepseek_chat(self):
        llm = LlmManager()
        model_str = llm.resolve_model_string("deepseek-chat")
        assert model_str == "deepseek:deepseek-chat"

    def test_resolve_ollama_with_base_url(self):
        llm = LlmManager()
        model_str = llm.resolve_model_string("qwen-local")
        assert "ollama:" in model_str
        assert "@http://localhost:11434" in model_str

    def test_resolve_openai_model(self):
        llm = LlmManager()
        model_str = llm.resolve_model_string("gpt-5.2")
        assert model_str == "openai:gpt-5.2"

    def test_track_cost(self):
        llm = LlmManager()
        cost = llm.track_cost("deepseek-chat", input_tokens=1000, output_tokens=500)
        assert cost > 0
        report = llm.get_cost_report()
        assert "deepseek-chat" in report

    def test_all_aliases_in_registry(self):
        expected = {"deepseek-chat", "deepseek-reasoner", "gpt-5.2",
                    "gpt-5.2-mini", "claude-sonnet", "claude-haiku",
                    "gemini-2.5-pro", "qwen-local"}
        assert set(MODEL_REGISTRY.keys()) == expected

    def test_get_config(self):
        llm = LlmManager()
        cfg = llm.get_config("claude-sonnet")
        assert cfg.provider == "anthropic"
        assert cfg.reasoning is True
