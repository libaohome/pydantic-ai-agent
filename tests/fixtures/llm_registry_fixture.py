"""测试专用 — 空库时写入 LLM 凭证组与模型（非应用 seed）。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schema import LlmCredentialGroup, LlmModel

_TEST_CREDENTIAL_GROUPS: tuple[tuple[str, str, str, str], ...] = (
    ("deepseek", "DeepSeek", "test-key-for-unit-tests", ""),
    ("longcat", "LongCat", "", "https://api.longcat.chat/openai"),
    ("agnesai", "Agnes AI", "", "https://apihub.agnes-ai.com/v1"),
    ("sensenova", "商汤日日新", "", "https://token.sensenova.cn/v1"),
    ("cohere", "Cohere", "", "https://api.cohere.ai/compatibility/v1"),
    (
        "cloudflare",
        "Cloudflare Workers AI",
        "",
        "https://api.cloudflare.com/client/v4/accounts/test/ai/v1",
    ),
)

_TEST_MODELS: tuple[dict, ...] = (
    {
        "alias": "deepseek-chat",
        "model_name": "DeepSeek Chat",
        "provider": "deepseek",
        "model_id": "deepseek-chat",
        "credential_group_key": "deepseek",
        "reasoning": True,
        "cost_per_1m_input": 0.27,
        "cost_per_1m_output": 1.10,
        "sort_order": 10,
    },
    {
        "alias": "deepseek-reasoner",
        "model_name": "DeepSeek Reasoner",
        "provider": "deepseek",
        "model_id": "deepseek-reasoner",
        "credential_group_key": "deepseek",
        "reasoning": True,
        "cost_per_1m_input": 0.55,
        "cost_per_1m_output": 2.19,
        "sort_order": 20,
    },
    {
        "alias": "longcat-2.0-preview",
        "model_name": "LongCat 2.0 Preview",
        "provider": "openai",
        "model_id": "LongCat-2.0-Preview",
        "credential_group_key": "longcat",
        "sort_order": 30,
    },
    {
        "alias": "agnes-2.0-flash",
        "model_name": "Agnes 2.0 Flash",
        "provider": "openai",
        "model_id": "agnes-2.0-flash",
        "credential_group_key": "agnesai",
        "sort_order": 40,
    },
    {
        "alias": "sensenova-6.7-flash-lite",
        "model_name": "商汤日日新 6.7 Flash Lite",
        "provider": "openai",
        "model_id": "sensenova-6.7-flash-lite",
        "credential_group_key": "sensenova",
        "multimodal": True,
        "sort_order": 50,
    },
    {
        "alias": "sensenova-u1-fast",
        "model_name": "商汤日日新 U1 Fast（生图）",
        "provider": "openai",
        "model_id": "sensenova-u1-fast",
        "credential_group_key": "sensenova",
        "image_generation": True,
        "sort_order": 60,
    },
    {
        "alias": "cohere-command-a-plus",
        "model_name": "Cohere Command A Plus",
        "provider": "openai",
        "model_id": "command-a-plus-05-2026",
        "credential_group_key": "cohere",
        "multimodal": True,
        "sort_order": 70,
    },
    {
        "alias": "cf-glm-5.2",
        "model_name": "Cloudflare GLM 5.2",
        "provider": "openai",
        "model_id": "@cf/zai-org/glm-5.2",
        "credential_group_key": "cloudflare",
        "sort_order": 80,
    },
)


async def ensure_test_llm_registry(session: AsyncSession) -> bool:
    """若 llm_models 为空则写入测试数据，返回是否新插入。"""
    count = await session.scalar(select(func.count()).select_from(LlmModel))
    if count:
        return False

    for group_key, group_name, api_key, base_url in _TEST_CREDENTIAL_GROUPS:
        session.add(
            LlmCredentialGroup(
                group_key=group_key,
                group_name=group_name,
                api_key=api_key,
                base_url=base_url,
                enabled=True,
            )
        )

    for item in _TEST_MODELS:
        session.add(
            LlmModel(
                alias=item["alias"],
                model_name=item["model_name"],
                provider=item["provider"],
                model_id=item["model_id"],
                credential_group_key=item["credential_group_key"],
                reasoning=item.get("reasoning", False),
                multimodal=item.get("multimodal", False),
                image_generation=item.get("image_generation", False),
                cost_per_1m_input=item.get("cost_per_1m_input", 0.0),
                cost_per_1m_output=item.get("cost_per_1m_output", 0.0),
                enabled=True,
                sort_order=item["sort_order"],
            )
        )
    return True
