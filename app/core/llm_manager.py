"""LLM 管理器 — 统一大语言模型路由、别名解析与成本追踪。"""

from __future__ import annotations

import os
from dataclasses import dataclass

from pydantic_ai.models.openai import OpenAIChatModel

from app.core.config import get_settings

ModelAlias = str


class UnknownModelAliasError(ValueError):
    """模型别名不存在于当前注册表。"""


@dataclass
class ModelConfig:
    """单个 LLM 模型的完整配置记录。"""

    alias: str
    model_name: str
    provider: str
    model_id: str
    credential_group: str | None = None
    reasoning: bool = False
    multimodal: bool = False
    image_generation: bool = False
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0


class LlmManager:
    """LLM 管理器 — 负责模型路由、成本追踪与动态切换。"""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._cost_tracker: dict[str, float] = {}
        self._registry: dict[str, ModelConfig] = {}
        self._credentials: dict[str, tuple[str, str, str]] = {}

    def apply_registry(
        self,
        registry: dict[str, ModelConfig],
        credentials: dict[str, tuple[str, str, str]],
    ) -> None:
        self._registry = dict(registry)
        self._credentials = dict(credentials)
        self._sync_provider_env()

    def _sync_provider_env(self) -> None:
        """将 DeepSeek 等原生 Provider 凭证同步到环境变量，供 pydantic-ai 读取。"""
        deepseek = self._credentials.get("deepseek")
        if deepseek and deepseek[0]:
            os.environ["DEEPSEEK_API_KEY"] = deepseek[0]

    @property
    def registry(self) -> dict[str, ModelConfig]:
        return dict(self._registry)

    def has_alias(self, alias: str) -> bool:
        return alias in self._registry

    def list_aliases(self) -> list[str]:
        return sorted(self._registry.keys())

    def get_credentials(self, group_key: str) -> tuple[str, str]:
        """返回凭证组的 (api_key, base_url)。"""
        cred = self._credentials.get(group_key)
        if not cred:
            return "", ""
        return cred[0], cred[1]

    def get_credential_group_name(self, group_key: str) -> str:
        cred = self._credentials.get(group_key)
        return cred[2] if cred else group_key

    def default_alias(self) -> ModelAlias:
        """返回当前默认模型别名（来自配置或注册表首项）。"""
        preferred = self._settings.default_model.strip()
        if preferred in self._registry:
            return preferred
        if self._registry:
            return next(iter(self._registry))
        raise RuntimeError("LLM model registry is empty")

    def get_config(self, alias: str) -> ModelConfig:
        return self._require_config(alias)

    def resolve_model_string(self, alias: str | None = None) -> str:
        """将模型别名解析为可读的 model 字符串（日志/展示用）。"""
        return self._format_model_string(self._require_config(alias or self.default_alias()))

    def resolve_model(self, alias: str | None = None) -> str | OpenAIChatModel:
        """将模型别名解析为 pydantic-ai Agent 可接受的 model 对象或字符串。"""
        cfg = self._require_config(alias or self.default_alias())
        if cfg.provider == "deepseek":
            return f"deepseek:{cfg.model_id}"
        return self._build_openai_compat_model(cfg)

    def track_cost(self, alias: str, input_tokens: int, output_tokens: int) -> float:
        cfg = self._require_config(alias)
        cost = (
            input_tokens / 1_000_000 * cfg.cost_per_1m_input
            + output_tokens / 1_000_000 * cfg.cost_per_1m_output
        )
        self._cost_tracker[alias] = self._cost_tracker.get(alias, 0.0) + cost
        return cost

    def get_cost_report(self) -> dict[str, float]:
        return dict(self._cost_tracker)

    def _require_config(self, alias: str) -> ModelConfig:
        try:
            return self._registry[alias]
        except KeyError as exc:
            raise UnknownModelAliasError(f"Unknown model alias: {alias}") from exc

    def _format_model_string(self, cfg: ModelConfig) -> str:
        if cfg.provider == "deepseek":
            return f"deepseek:{cfg.model_id}"
        _, base_url = self.get_credentials(cfg.credential_group) if cfg.credential_group else ("", "")
        suffix = f"@{base_url}" if base_url else ""
        return f"openai:{cfg.model_id}{suffix}"

    def _build_openai_compat_model(self, cfg: ModelConfig) -> OpenAIChatModel:
        from pydantic_ai.providers.openai import OpenAIProvider

        api_key, base_url = self.get_credentials(cfg.credential_group)
        provider = OpenAIProvider(base_url=base_url or None, api_key=api_key or None)
        return OpenAIChatModel(cfg.model_id, provider=provider)


_llm_manager: LlmManager | None = None


def get_llm_manager() -> LlmManager:
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LlmManager()
    return _llm_manager


async def reload_llm_registry() -> None:
    """从数据库重新加载模型注册表（管理 API 变更后可调用）。"""
    from app.core.deps import db_session_scope
    from app.core.llm_registry import fetch_llm_registry

    async with db_session_scope() as session:
        registry, credentials = await fetch_llm_registry(session)
    get_llm_manager().apply_registry(registry, credentials)
