"""单元测试 — 生图 API 响应解析（url / b64_json）。"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.image_gen import _resolve_generated_image_bytes, normalize_image_size, run_image_generation


@pytest.mark.asyncio
async def test_resolve_generated_image_from_b64_json():
    png_bytes = b"\x89PNG fake image"
    item = {"b64_json": base64.standard_b64encode(png_bytes).decode("ascii")}

    data, mime, url = await _resolve_generated_image_bytes(item, AsyncMock())

    assert data == png_bytes
    assert mime == "image/png"
    assert url is None


@pytest.mark.asyncio
async def test_resolve_generated_image_from_url():
    png_bytes = b"\x89PNG from url"
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.content = png_bytes
    mock_resp.headers = {"content-type": "image/png"}

    client = AsyncMock()
    client.get = AsyncMock(return_value=mock_resp)
    item = {"url": "https://cdn.example.com/img.png"}

    data, mime, url = await _resolve_generated_image_bytes(item, client)

    assert data == png_bytes
    assert mime == "image/png"
    assert url == "https://cdn.example.com/img.png"


@pytest.mark.asyncio
async def test_resolve_generated_image_from_data_uri():
    png_bytes = b"\x89PNG data uri"
    b64 = base64.standard_b64encode(png_bytes).decode("ascii")
    item = {"url": f"data:image/jpeg;base64,{b64}"}

    data, mime, url = await _resolve_generated_image_bytes(item, AsyncMock())

    assert data == png_bytes
    assert mime == "image/jpeg"
    assert url is None


def test_normalize_image_size_defaults_invalid():
    assert normalize_image_size("2752x1536") == "1024x1024"
    assert normalize_image_size(None) == "1024x1024"
    assert normalize_image_size("1792x1024") == "1792x1024"


def test_image_original_name_from_url():
    from app.agents.image_gen import _image_original_name

    item = {
        "url": "https://cdn.example.com/path/768f13af-ba13-4a1e-b841-a24fd0c92f4f_0",
    }
    assert _image_original_name(item, 0, ".png") == "768f13af-ba13-4a1e-b841-a24fd0c92f4f_0.png"


@pytest.mark.asyncio
async def test_run_image_generation_b64_json(tmp_path, monkeypatch):
    from app.core.llm_manager import ModelConfig
    from app.core.uploads import UploadStore

    store = UploadStore(root=tmp_path)
    monkeypatch.setattr("app.agents.image_gen.get_download_store", lambda: store)
    monkeypatch.setattr(
        "app.agents.image_gen.get_llm_manager",
        lambda: type(
            "L",
            (),
            {
                "get_config": lambda _self, _a: ModelConfig(
                    alias="sensenova-u1-fast",
                    model_name="sensenova-u1-fast",
                    provider="openai",
                    model_id="sensenova-u1-fast",
                    credential_group="sensenova",
                ),
                "get_credentials": lambda _self, _g: ("k", "https://api.example.com/v1"),
            },
        )(),
    )

    png_bytes = b"\x89PNG generated"
    mock_resp = MagicMock()
    mock_resp.is_error = False
    mock_resp.json.return_value = {
        "data": [{"b64_json": base64.standard_b64encode(png_bytes).decode("ascii")}],
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.agents.image_gen.httpx.AsyncClient", return_value=mock_client):
        result = await run_image_generation("画一只猫", "sensenova-u1-fast")

    assert mock_client.post.await_args.kwargs["json"]["size"] == "1024x1024"
    assert result["artifacts"]
    assert (tmp_path / result["artifacts"][0]["file_id"]).read_bytes() == png_bytes
    assert "原图 URL" not in result["text"]
