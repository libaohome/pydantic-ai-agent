"""LLM 管理器 — 统一大语言模型路由、别名解析与成本追踪。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import get_settings

ModelAlias = Literal[
    "deepseek-chat",
    "deepseek-reasoner",
    "longcat-2.0-preview",
    "agnes-2.0-flash",
    "sensenova-6.7-flash-lite",
    "sensenova-u1-fast",
]

CredentialGroup = Literal["longcat", "agnesai", "sensenova"]


@dataclass
class ModelConfig:
    """单个 LLM 模型的完整配置记录。"""

    alias: ModelAlias
    provider: str
    model_id: str
    api_key_env: str = ""
    credential_group: CredentialGroup | None = None
    reasoning: bool = False
    multimodal: bool = False
    image_generation: bool = False
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0


_CREDENTIAL_FIELDS: dict[CredentialGroup, tuple[str, str]] = {
    "longcat": ("longcat_api_key", "longcat_base_url"),
    "agnesai": ("agnesai_api_key", "agnesai_base_url"),
    "sensenova": ("sensenova_api_key", "sensenova_base_url"),
}

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
    "longcat-2.0-preview": ModelConfig(
        alias="longcat-2.0-preview",
        provider="openai",
        model_id="LongCat-2.0-Preview",
        api_key_env="LONGCAT_API_KEY",
        credential_group="longcat",
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
    ),
    "agnes-2.0-flash": ModelConfig(
        alias="agnes-2.0-flash",
        provider="openai",
        model_id="agnes-2.0-flash",
        api_key_env="AGNESAI_API_KEY",
        credential_group="agnesai",
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
    ),
    "sensenova-6.7-flash-lite": ModelConfig(
        alias="sensenova-6.7-flash-lite",
        provider="openai",
        model_id="sensenova-6.7-flash-lite",
        api_key_env="SENSENOVA_API_KEY",
        credential_group="sensenova",
        multimodal=True,
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
    ),
    "sensenova-u1-fast": ModelConfig(
        alias="sensenova-u1-fast",
        provider="openai",
        model_id="sensenova-u1-fast",
        api_key_env="SENSENOVA_API_KEY",
        credential_group="sensenova",
        image_generation=True,
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
    ),
}


class LlmManager:
    """LLM 管理器 — 负责模型路由、成本追踪与动态切换。"""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._cost_tracker: dict[str, float] = {}

    def resolve_model_string(self, alias: ModelAlias | None = None) -> str:
        """将模型别名解析为可读的 model 字符串（日志/展示用）。"""
        cfg = MODEL_REGISTRY[alias or self._default_alias()]
        if cfg.provider == "deepseek":
            return f"deepseek:{cfg.model_id}"
        base_url = self._get_base_url(cfg.credential_group) if cfg.credential_group else ""
        suffix = f"@{base_url}" if base_url else ""
        return f"openai:{cfg.model_id}{suffix}"

    def resolve_model(self, alias: ModelAlias | None = None) -> str | Any:
        """将模型别名解析为 pydantic-ai Agent 可接受的 model 对象或字符串。"""
        cfg = MODEL_REGISTRY[alias or self._default_alias()]
        if cfg.provider == "deepseek":
            return f"deepseek:{cfg.model_id}"
        return self._build_openai_compat_model(cfg)

    def get_config(self, alias: ModelAlias) -> ModelConfig:
        return MODEL_REGISTRY[alias]

    def track_cost(self, alias: ModelAlias, input_tokens: int, output_tokens: int) -> float:
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
        if ":" in default:
            _, model_id = default.split(":", 1)
            for alias, cfg in MODEL_REGISTRY.items():
                if cfg.model_id == model_id:
                    return alias
        return "deepseek-chat"

    def _get_credentials(self, group: CredentialGroup | None) -> tuple[str, str]:
        if not group:
            return "", ""
        key_field, url_field = _CREDENTIAL_FIELDS[group]
        api_key = getattr(self._settings, key_field, "") or ""
        base_url = getattr(self._settings, url_field, "") or ""
        return api_key, base_url.rstrip("/")

    def _get_base_url(self, group: CredentialGroup | None) -> str:
        _, base_url = self._get_credentials(group)
        return base_url

    def _build_openai_compat_model(self, cfg: ModelConfig) -> Any:
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        api_key, base_url = self._get_credentials(cfg.credential_group)
        provider = OpenAIProvider(base_url=base_url or None, api_key=api_key or None)
        return OpenAIChatModel(cfg.model_id, provider=provider)


_llm_manager: LlmManager | None = None


def get_llm_manager() -> LlmManager:
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LlmManager()
    return _llm_manager
