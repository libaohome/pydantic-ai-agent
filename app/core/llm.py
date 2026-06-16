"""LLM 管理器 — 统一大语言模型路由、别名解析与成本追踪。

本模块位于 ``app/core/`` 包内，封装了项目中所有 LLM 相关的配置与调用约定。

职责概览：
    - 维护 ``MODEL_REGISTRY``：别名 → 提供商、模型 ID、定价等
    - ``LlmManager``：将别名解析为 pydantic-ai 可识别的 model 字符串
    - 按 token 用量累计各模型的调用成本

在项目中的位置::

    app/
    └── core/
        ├── llm.py         ← 当前文件
        ├── config.py      ← default_model 默认模型配置
        └── ...

    app/agents/            ← 各 Agent 通过 get_llm_manager() 获取模型
"""

from __future__ import annotations

from dataclasses import dataclass, field
# ``Literal`` 限制类型为若干固定字符串之一，IDE 和类型检查器可自动补全
from typing import Literal

from pydantic_ai import Agent

from app.core.config import get_settings

# ─── 模型别名 ────────────────────────────────────

# 类型别名：只允许列出的字符串作为模型别名，写错会在静态检查时报错
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
    """单个 LLM 模型的完整配置记录。

    Attributes:
        alias: 项目内使用的简短别名（与 MODEL_REGISTRY 的键一致）。
        provider: pydantic-ai 内部 provider 名称（如 openai、deepseek）。
        model_id: 提供商 API 中的实际模型 ID。
        base_url: 自定义 API 端点（本地 Ollama 等自部署场景）。
        api_key_env: 对应的环境变量名，供 provider 读取密钥。
        reasoning: 是否支持推理/思维链模式。
        cost_per_1m_input: 每百万 input token 的美元单价。
        cost_per_1m_output: 每百万 output token 的美元单价。
    """

    alias: ModelAlias
    provider: str          # pydantic-ai 内部 provider 名
    model_id: str          # 模型 ID
    base_url: str | None = None   # 自定义端点
    api_key_env: str = ""         # 环境变量名
    reasoning: bool = False
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0


# ─── 预注册模型表 ────────────────────────────────

# ``dict[ModelAlias, ModelConfig]``：键为别名，值为配置对象
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
    """LLM 管理器 — 负责模型路由、成本追踪与动态切换。

    不直接调用 LLM API，而是为 Pydantic AI 的 ``Agent`` 提供正确格式的
    model 字符串（如 ``deepseek:deepseek-chat``）。
    """

    def __init__(self) -> None:
        """初始化管理器，加载配置并创建空的成本追踪字典。"""
        self._settings = get_settings()
        # 下划线前缀表示「内部使用」的实例属性（Python 命名约定，非强制私有）
        self._cost_tracker: dict[str, float] = {}

    def resolve_model_string(self, alias: ModelAlias | None = None) -> str:
        """将模型别名解析为 pydantic-ai 的 model 字符串。

        pydantic-ai 约定格式：
            - 标准：``provider:model_id``，如 ``deepseek:deepseek-chat``
            - 自定义端点：``provider:model_id@base_url``

        Args:
            alias: 模型别名；为 ``None`` 时使用配置中的默认模型。

        Returns:
            str: 可直接传给 ``Agent(model=...)`` 的字符串。
        """
        # ``alias or self._default_alias()``：alias 为 None/空时用默认值
        cfg = MODEL_REGISTRY[alias or self._default_alias()]
        model_str = f"{cfg.provider}:{cfg.model_id}"

        # Ollama 等自部署模型需通过 @ 后缀指定 base_url
        if cfg.base_url:
            model_str += f"@{cfg.base_url}"

        return model_str

    def get_config(self, alias: ModelAlias) -> ModelConfig:
        """根据别名获取完整的模型配置对象。

        Args:
            alias: 已注册的模型别名。

        Returns:
            ModelConfig: 对应的配置记录。
        """
        return MODEL_REGISTRY[alias]

    def track_cost(self, alias: ModelAlias, input_tokens: int, output_tokens: int) -> float:
        """追踪单次 LLM 调用的成本并累加到内部计数器。

        Args:
            alias: 使用的模型别名。
            input_tokens: 输入 token 数量。
            output_tokens: 输出 token 数量。

        Returns:
            float: 本次调用的美元成本。
        """
        cfg = MODEL_REGISTRY[alias]
        cost = (
            input_tokens / 1_000_000 * cfg.cost_per_1m_input
            + output_tokens / 1_000_000 * cfg.cost_per_1m_output
        )
        # ``dict.get(key, default)`` 键不存在时返回 default，避免 KeyError
        self._cost_tracker[alias] = self._cost_tracker.get(alias, 0.0) + cost
        return cost

    def get_cost_report(self) -> dict[str, float]:
        """获取各模型累计成本的快照副本。

        Returns:
            dict[str, float]: 别名 → 累计美元成本。
        """
        # ``dict(...)`` 浅拷贝，防止外部直接修改内部 _cost_tracker
        return dict(self._cost_tracker)

    def _default_alias(self) -> ModelAlias:
        """从配置项 ``default_model`` 反查对应的模型别名。

        配置格式为 ``provider:model_id``，需在注册表中按 model_id 匹配。

        Returns:
            ModelAlias: 匹配到的别名；无法匹配时回退到 ``deepseek-chat``。
        """
        default = self._settings.default_model
        # 从 "deepseek:deepseek-chat" 提取 model_id 部分
        if ":" in default:
            _, model_id = default.split(":", 1)
            for alias, cfg in MODEL_REGISTRY.items():
                if cfg.model_id == model_id:
                    return alias
        return "deepseek-chat"


# ─── 全局单例 ─────────────────────────────────────

_llm_manager: LlmManager | None = None


def get_llm_manager() -> LlmManager:
    """获取 LLM 管理器全局单例（懒加载）。

    首次调用时创建 ``LlmManager`` 实例，后续调用返回同一对象。

    Returns:
        LlmManager: 全局 LLM 管理器实例。
    """
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LlmManager()
    return _llm_manager
