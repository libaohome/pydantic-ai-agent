"""单元测试 — LLM 注册表数据库加载。"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.llm_manager import get_llm_manager
from app.models.schema import LlmCredentialGroup, LlmModel
from tests.fixtures.llm_registry_fixture import _TEST_MODELS


@pytest.mark.asyncio
async def test_init_db_loads_llm_models_from_db():
    llm = get_llm_manager()
    assert llm.has_alias("deepseek-chat")
    assert llm.has_alias("sensenova-u1-fast")
    assert len(llm.list_aliases()) == len(_TEST_MODELS)

    cfg = llm.get_config("cohere-command-a-plus")
    assert cfg.multimodal is True
    assert cfg.model_name == "Cohere Command A Plus"
    assert llm.get_credential_group_name("deepseek") == "DeepSeek"

    import app.core.deps as deps_module

    factory = deps_module._session_factory
    assert factory is not None
    async with factory() as session:
        cred = await session.scalar(
            select(LlmCredentialGroup).where(LlmCredentialGroup.group_key == "deepseek")
        )
        model = await session.scalar(
            select(LlmModel).where(LlmModel.alias == "deepseek-chat")
        )
    assert cred is not None and cred.create_time is not None and cred.update_time is not None
    assert model is not None and model.create_time is not None and model.update_time is not None
