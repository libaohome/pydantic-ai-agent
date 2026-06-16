"""单元测试 — Agent 输入附件处理。"""

from app.agents.input_files import enrich_user_input_with_files, format_file_ids_hint
from app.core.uploads import UploadStore


def test_format_file_ids_hint(tmp_path):
    store = UploadStore(root=tmp_path / "upload")
    source = tmp_path / "demo.py"
    source.write_text("x = 1\n", encoding="utf-8")
    file_id = store.save_from_path(source, "demo.py")

    hint = format_file_ids_hint([file_id], store=store)

    assert file_id in hint
    assert "demo.py" in hint


def test_enrich_user_input_with_files(tmp_path):
    store = UploadStore(root=tmp_path / "upload")
    source = tmp_path / "demo.py"
    source.write_text("x = 1\n", encoding="utf-8")
    file_id = store.save_from_path(source, "demo.py")

    result = enrich_user_input_with_files("请审查代码", [file_id])

    assert "请审查代码" in result
    assert file_id in result
