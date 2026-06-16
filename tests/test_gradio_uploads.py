"""单元测试 — Gradio 多模态上传解析。"""

from app.ui.gradio_app import _resolve_gradio_file_ref, _save_multimodal_uploads


def test_resolve_gradio_file_ref_from_string_path(tmp_path):
    source = tmp_path / "Demo.java"
    source.write_text("class Demo {}", encoding="utf-8")

    resolved = _resolve_gradio_file_ref(str(source))

    assert resolved == (str(source), "Demo.java")


def test_save_multimodal_uploads_with_string_files(tmp_path, monkeypatch):
    from app.core import uploads as uploads_module

    upload_root = tmp_path / "upload"
    monkeypatch.setattr(uploads_module, "UPLOAD_DIR", upload_root)
    monkeypatch.setattr(uploads_module, "_upload_store", None)

    source = tmp_path / "Hello.java"
    source.write_text("class Hello {}", encoding="utf-8")

    text, file_ids = _save_multimodal_uploads(
        {"text": "请审查代码", "files": [str(source)]},
    )

    assert text == "请审查代码"
    assert len(file_ids) == 1
    assert (upload_root / file_ids[0]).is_file()
