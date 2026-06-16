"""单元测试 — LLM 管理器（LlmManager）。

测试目的：
- 验证模型别名（如 ``deepseek-chat``）能正确解析为 pydantic-ai 所需的模型字符串
- 验证不同提供商（DeepSeek、Ollama、OpenAI）的 URL / 前缀格式
- 验证 token 成本统计与费用报告
- 验证 ``MODEL_REGISTRY`` 包含预期的全部模型别名

依赖说明：
- ``conftest.py`` 会在每个测试前重置 ``LlmManager`` 单例，本文件无需手动清理
"""

import pytest
from app.core.llm import LlmManager, MODEL_REGISTRY, ModelAlias


class TestLlmManager:
    """LlmManager 核心功能的单元测试集合。"""

    def test_resolve_deepseek_chat(self):
        """DeepSeek 聊天模型应解析为 ``deepseek:`` 前缀格式。"""
        llm = LlmManager()
        model_str = llm.resolve_model_string("deepseek-chat")
        # 断言：别名 deepseek-chat → pydantic-ai 模型 ID
        assert model_str == "deepseek:deepseek-chat"

    def test_resolve_ollama_with_base_url(self):
        """本地 Ollama 模型应带 ``ollama:`` 前缀和 ``@base_url`` 后缀。"""
        llm = LlmManager()
        model_str = llm.resolve_model_string("qwen-local")
        # Ollama 需要指定服务地址，默认 localhost:11434
        assert "ollama:" in model_str
        assert "@http://localhost:11434" in model_str

    def test_resolve_openai_model(self):
        """OpenAI 兼容模型应解析为 ``openai:`` 前缀格式。"""
        llm = LlmManager()
        model_str = llm.resolve_model_string("gpt-5.2")
        assert model_str == "openai:gpt-5.2"

    def test_track_cost(self):
        """调用 track_cost 后，费用应大于 0 且出现在成本报告中。"""
        llm = LlmManager()
        # 模拟 1000 输入 token + 500 输出 token 的计费
        cost = llm.track_cost("deepseek-chat", input_tokens=1000, output_tokens=500)
        assert cost > 0

        report = llm.get_cost_report()
        # 报告字典的 key 应包含刚统计过的模型别名
        assert "deepseek-chat" in report

    def test_all_aliases_in_registry(self):
        """MODEL_REGISTRY 应恰好包含项目支持的全部模型别名。"""
        expected = {"deepseek-chat", "deepseek-reasoner", "gpt-5.2",
                    "gpt-5.2-mini", "claude-sonnet", "claude-haiku",
                    "gemini-2.5-pro", "qwen-local"}
        # 用集合比较，顺序无关，只关心「有哪些别名」
        assert set(MODEL_REGISTRY.keys()) == expected

    def test_get_config(self):
        """get_config 应返回正确的提供商与 reasoning 等配置字段。"""
        llm = LlmManager()
        cfg = llm.get_config("claude-sonnet")
        assert cfg.provider == "anthropic"
        # claude-sonnet 在注册表中标记为支持推理模式
        assert cfg.reasoning is True
