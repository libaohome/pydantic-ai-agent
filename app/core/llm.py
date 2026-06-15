"""LLM 管理器 — 统一模型路由与配置"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic_ai import Agent

from app.core.config import get_settings

# ─── 模型别名 ────────────────────────────────────

ModelAlias = Literal[
    "deepseek-chat",
    "deepseek-reasoner",
    "gpt-5.2",
    "gpt-5.2-mini",
    "claude-sonnet",
    "claude-haiku",
    "gemini-2.5-pro",
    "qwen-local",
]


@dataclass
class ModelConfig:
    """单模型配置"""

    alias: ModelAlias
    provider: str          # pydantic-ai 内部 provider 名
    model_id: str          # 模型 ID
    base_url: str | None = None   # 自定义端点
    api_key_env: str = ""         # 环境变量名
    reasoning: bool = False
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0


# ─── 预注册模型表 ────────────────────────────────

MODEL_REGISTRY: dict[ModelAlias, ModelConfig] = {
    "deepseek-chat": ModelConfig(
        alias="deepseek-chat",
        provider="deepseek",
        model_id="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
        reasoning=True,
        cost_per_1m_input=0.27,
        cost_per_1m_output=1.10,
    ),
    "deepseek-reasoner": ModelConfig(
        alias="deepseek-reasoner",
        provider="deepseek",
        model_id="deepseek-reasoner",
        api_key_env="DEEPSEEK_API_KEY",
        reasoning=True,
        cost_per_1m_input=0.55,
        cost_per_1m_output=2.19,
    ),
    "gpt-5.2": ModelConfig(
        alias="gpt-5.2",
        provider="openai",
        model_id="gpt-5.2",
        api_key_env="OPENAI_API_KEY",
        cost_per_1m_input=2.0,
        cost_per_1m_output=8.0,
    ),
    "gpt-5.2-mini": ModelConfig(
        alias="gpt-5.2-mini",
        provider="openai",
        model_id="gpt-5.2-mini",
        api_key_env="OPENAI_API_KEY",
        cost_per_1m_input=0.15,
        cost_per_1m_output=0.60,
    ),
    "claude-sonnet": ModelConfig(
        alias="claude-sonnet",
        provider="anthropic",
        model_id="claude-sonnet-4-20250514",
        api_key_env="ANTHROPIC_API_KEY",
        reasoning=True,
        cost_per_1m_input=3.0,
        cost_per_1m_output=15.0,
    ),
    "claude-haiku": ModelConfig(
        alias="claude-haiku",
        provider="anthropic",
        model_id="claude-haiku-4-20250506",
        api_key_env="ANTHROPIC_API_KEY",
        cost_per_1m_input=0.80,
        cost_per_1m_output=4.0,
    ),
    "gemini-2.5-pro": ModelConfig(
        alias="gemini-2.5-pro",
        provider="google",
        model_id="gemini-2.5-pro",
        api_key_env="GOOGLE_API_KEY",
        reasoning=True,
        cost_per_1m_input=1.25,
        cost_per_1m_output=10.0,
    ),
    "qwen-local": ModelConfig(
        alias="qwen-local",
        provider="ollama",
        model_id="qwen2.5-coder:7b",
        base_url="http://localhost:11434",
        reasoning=False,
    ),
}


class LlmManager:
    """LLM 管理器 — 模型路由、成本追踪、动态切换"""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._cost_tracker: dict[str, float] = {}

    def resolve_model_string(self, alias: ModelAlias | None = None) -> str:
        """将模型别名解析为 pydantic-ai 的 model 字符串

        格式: provider:model_id 或 openai:model_id@base_url
        """
        cfg = MODEL_REGISTRY[alias or self._default_alias()]
        model_str = f"{cfg.provider}:{cfg.model_id}"

        # Ollama 等自部署模型需指定 base_url
        if cfg.base_url:
            model_str += f"@{cfg.base_url}"

        return model_str

    def get_config(self, alias: ModelAlias) -> ModelConfig:
        return MODEL_REGISTRY[alias]

    def track_cost(self, alias: ModelAlias, input_tokens: int, output_tokens: int) -> float:
        """追踪单次调用的成本"""
        cfg = MODEL_REGISTRY[alias]
        cost = (
            input_tokens / 1_000_000 * cfg.cost_per_1m_input
            + output_tokens / 1_000_000 * cfg.cost_per_1m_output
        )
        self._cost_tracker[alias] = self._cost_tracker.get(alias, 0.0) + cost
        return cost

    def get_cost_report(self) -> dict[str, float]:
        return dict(self._cost_tracker)

    def _default_alias(self) -> ModelAlias:
        default = self._settings.default_model
        # 从 "deepseek:deepseek-chat" 提取 alias
        if ":" in default:
            _, model_id = default.split(":", 1)
            for alias, cfg in MODEL_REGISTRY.items():
                if cfg.model_id == model_id:
                    return alias
        return "deepseek-chat"


# ─── 全局单例 ─────────────────────────────────────

_llm_manager: LlmManager | None = None


def get_llm_manager() -> LlmManager:
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LlmManager()
    return _llm_manager
