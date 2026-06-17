"""单元测试 — ChatModelAgent 多模态输入构建。"""

from app.agents.chat_media import (
    build_chat_user_prompt,
    get_chat_builtin_tools,
    supports_image_generation,
    supports_multimodal_input,
)
from pydantic_ai.messages import BinaryContent


def test_build_chat_user_prompt_text_only():
    prompt = build_chat_user_prompt("你好", model_alias="deepseek-chat")
    assert prompt == "你好"


def test_get_chat_builtin_tools_empty():
    assert get_chat_builtin_tools("deepseek-chat") == []


def test_sensenova_multimodal_and_image_flags():
    assert supports_multimodal_input("sensenova-6.7-flash-lite")
    assert supports_image_generation("sensenova-u1-fast")
    assert not supports_image_generation("deepseek-chat")


def test_build_chat_user_prompt_with_text_file(tmp_path, monkeypatch):
    from app.core.uploads import UploadStore

    store = UploadStore(root=tmp_path)
    monkeypatch.setattr("app.agents.chat_media.get_upload_store", lambda: store)

    txt = tmp_path / "note.txt"
    txt.write_text("hello data", encoding="utf-8")
    file_id = store.save_from_path(str(txt), "note.txt")

    prompt = build_chat_user_prompt("分析附件", [file_id], model_alias="deepseek-chat")
    assert isinstance(prompt, str)
    assert "hello data" in prompt


def test_build_chat_user_prompt_with_image_multimodal(tmp_path, monkeypatch):
    from app.core.uploads import UploadStore

    store = UploadStore(root=tmp_path)
    monkeypatch.setattr("app.agents.chat_media.get_upload_store", lambda: store)

    img = tmp_path / "a.jpg"
    img.write_bytes(b"fake")
    file_id = store.save_from_path(str(img), "a.jpg")

    prompt = build_chat_user_prompt("看", [file_id], model_alias="sensenova-6.7-flash-lite")
    assert isinstance(prompt, list)
    assert any(isinstance(p, BinaryContent) for p in prompt)


def test_build_chat_user_prompt_with_image_hint(tmp_path, monkeypatch):
    from app.core.uploads import UploadStore

    store = UploadStore(root=tmp_path)
    monkeypatch.setattr("app.agents.chat_media.get_upload_store", lambda: store)

    img = tmp_path / "a.jpg"
    img.write_bytes(b"fake")
    file_id = store.save_from_path(str(img), "a.jpg")

    prompt = build_chat_user_prompt("看", [file_id], model_alias="deepseek-chat")
    assert isinstance(prompt, str)
    assert "不支持该媒体类型" in prompt
