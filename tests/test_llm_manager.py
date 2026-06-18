"""单元测试 — LLM 管理器（LlmManager）。"""

from __future__ import annotations

from pydantic_ai.models.openai import OpenAIChatModel

from app.core.llm_manager import get_llm_manager


class TestLlmManager:
    def test_resolve_deepseek_chat(self):
        llm = get_llm_manager()
        assert llm.resolve_model_string("deepseek-chat") == "deepseek:deepseek-chat"

    def test_resolve_deepseek_reasoner(self):
        llm = get_llm_manager()
        assert llm.resolve_model_string("deepseek-reasoner") == "deepseek:deepseek-reasoner"

    def test_resolve_longcat_string(self):
        llm = get_llm_manager()
        s = llm.resolve_model_string("longcat-2.0-preview")
        assert s.startswith("openai:LongCat-2.0-Preview@")
        assert "longcat.chat" in s

    def test_resolve_openai_compat_model(self):
        llm = get_llm_manager()
        model = llm.resolve_model("agnes-2.0-flash")
        assert isinstance(model, OpenAIChatModel)
        assert model.model_name == "agnes-2.0-flash"

    def test_resolve_cohere_model(self):
        llm = get_llm_manager()
        s = llm.resolve_model_string("cohere-command-a-plus")
        assert s.startswith("openai:command-a-plus-05-2026@")
        assert "cohere.ai" in s
        model = llm.resolve_model("cohere-command-a-plus")
        assert isinstance(model, OpenAIChatModel)
        assert model.model_name == "command-a-plus-05-2026"

    def test_resolve_cloudflare_model(self):
        llm = get_llm_manager()
        s = llm.resolve_model_string("cf-glm-5.2")
        assert s.startswith("openai:@cf/zai-org/glm-5.2@")
        assert "cloudflare.com" in s
        model = llm.resolve_model("cf-glm-5.2")
        assert isinstance(model, OpenAIChatModel)
        assert model.model_name == "@cf/zai-org/glm-5.2"

    def test_track_cost(self):
        llm = get_llm_manager()
        cost = llm.track_cost("deepseek-chat", input_tokens=1000, output_tokens=500)
        assert cost > 0
        assert "deepseek-chat" in llm.get_cost_report()

    def test_all_aliases_in_registry(self):
        expected = {
            "deepseek-chat",
            "deepseek-reasoner",
            "longcat-2.0-preview",
            "agnes-2.0-flash",
            "sensenova-6.7-flash-lite",
            "sensenova-u1-fast",
            "cohere-command-a-plus",
            "cf-glm-5.2",
        }
        assert set(get_llm_manager().registry.keys()) == expected

    def test_get_config(self):
        llm = get_llm_manager()
        cfg = llm.get_config("cohere-command-a-plus")
        assert cfg.provider == "openai"
        assert cfg.multimodal is True
