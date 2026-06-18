"""单元测试 — 用户上传文件存储。"""

from __future__ import annotations

import pytest

from app.core.uploads import UploadStore


@pytest.fixture
def upload_store(tmp_path):
    return UploadStore(root=tmp_path / "upload")


class TestUploadStore:
  def test_save_from_path_generates_file_id(self, upload_store, tmp_path):
      source = tmp_path / "sample.py"
      source.write_text("print('hello')\n", encoding="utf-8")

      file_id = upload_store.save_from_path(source, "sample.py")

      assert upload_store.exists(file_id)
      assert file_id.endswith(".py")
      assert upload_store.get_path(file_id).read_text(encoding="utf-8") == "print('hello')\n"

  def test_get_metadata(self, upload_store, tmp_path):
      source = tmp_path / "data.csv"
      source.write_text("a,b\n1,2\n", encoding="utf-8")

      file_id = upload_store.save_from_path(source, "data.csv")
      meta = upload_store.get_metadata(file_id)

      assert meta.file_id == file_id
      assert meta.original_name == "data.csv"
      assert meta.size > 0
      assert meta.mime_type == "text/csv"

  def test_save_from_bytes_stores_mime_type(self, upload_store):
      file_id = upload_store.save_from_bytes(b"\x89PNG\r\n", "shot.png", mime_type="image/png")
      meta = upload_store.get_metadata(file_id)
      assert meta.mime_type == "image/png"
      assert file_id.endswith(".png")

  def test_read_text(self, upload_store, tmp_path):
      source = tmp_path / "note.txt"
      source.write_text("hello upload", encoding="utf-8")

      file_id = upload_store.save_from_path(source, "note.txt")
      assert upload_store.read_text(file_id) == "hello upload"

  def test_invalid_file_id_rejected(self, upload_store):
      with pytest.raises(ValueError):
          upload_store.get_path("../escape.txt")

  def test_save_bytes(self, upload_store):
      file_id = upload_store.save_from_bytes(b"binary", "blob.bin")
      meta = upload_store.get_metadata(file_id)
      assert meta.mime_type == "application/octet-stream"
      assert upload_store.exists(file_id)
      assert upload_store.get_path(file_id).read_bytes() == b"binary"


def test_guess_image_extension_from_magic_bytes():
    from app.core.uploads import guess_image_extension

    png = b"\x89PNG\r\n\x1a\n" + b"rest"
    assert guess_image_extension("application/octet-stream", png) == ".png"
    assert guess_image_extension("image/png", png) == ".png"
