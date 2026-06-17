"""单元测试 — Agent 输入附件处理。"""

from app.agents.input_files import (
    enrich_user_input_with_files,
    format_file_ids_hint,
    inject_file_contents,
    prepare_agent_input,
)
from app.agents.registry import AgentName
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


def test_inject_file_contents(tmp_path, monkeypatch):
    store = UploadStore(root=tmp_path / "upload")
    source = tmp_path / "demo.py"
    source.write_text("x = 1\n", encoding="utf-8")
    file_id = store.save_from_path(source, "demo.py")
    monkeypatch.setattr("app.agents.input_files.get_upload_store", lambda: store)

    result = inject_file_contents("请审查代码", [file_id])

    assert "请审查代码" in result
    assert file_id in result
    assert "x = 1" in result


def test_prepare_agent_input_injects_files(tmp_path, monkeypatch):
    store = UploadStore(root=tmp_path / "upload")
    source = tmp_path / "data.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    file_id = store.save_from_path(source, "data.csv")
    monkeypatch.setattr("app.agents.input_files.get_upload_store", lambda: store)

    result = prepare_agent_input(AgentName.data_analyst, "分析数据", [file_id])

    assert "分析数据" in result
    assert "a,b" in result
