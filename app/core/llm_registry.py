"""LLM 模型注册表 — 从 SQLite 加载凭证组与模型配置。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schema import LlmCredentialGroup, LlmModel

async def fetch_llm_registry(session: AsyncSession) -> tuple[dict, dict[str, tuple[str, str, str]]]:
    """从数据库加载启用的凭证组与模型，供 LlmManager 使用。"""
    from app.core.llm_manager import ModelConfig

    cred_rows = (
        await session.execute(
            select(LlmCredentialGroup).where(LlmCredentialGroup.enabled.is_(True))
        )
    ).scalars().all()
    credentials = {
        row.group_key: (row.api_key or "", (row.base_url or "").rstrip("/"), row.group_name or row.group_key)
        for row in cred_rows
    }

    model_rows = (
        await session.execute(
            select(LlmModel)
            .where(LlmModel.enabled.is_(True))
            .order_by(LlmModel.sort_order, LlmModel.alias)
        )
    ).scalars().all()

    registry: dict[str, ModelConfig] = {}
    for row in model_rows:
        registry[row.alias] = ModelConfig(
            alias=row.alias,
            model_name=row.model_name or row.alias,
            provider=row.provider,
            model_id=row.model_id,
            credential_group=row.credential_group_key,
            reasoning=row.reasoning,
            multimodal=row.multimodal,
            image_generation=row.image_generation,
            cost_per_1m_input=row.cost_per_1m_input,
            cost_per_1m_output=row.cost_per_1m_output,
        )
    return registry, credentials
