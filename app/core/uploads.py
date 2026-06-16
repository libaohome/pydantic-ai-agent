"""用户上传文件存储 — 保存到 data/upload 并按 file_id 索引。

上传文件以 UUID 命名落盘，保留原始扩展名；``file_id`` 即为存储文件名
（如 ``f47ac10b-58cc-4372-a567-0e02b2c3d479.py``），供 Agent 与 UI 引用。
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import UPLOAD_DIR

# file_id 仅允许 UUID + 可选扩展名，防止路径穿越
_FILE_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(\.[A-Za-z0-9._-]+)?$"
)


@dataclass
class UploadedFileMeta:
    """已上传文件的元数据。"""

    file_id: str
    original_name: str
    size: int
    uploaded_at: str
    content_type: str = ""

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


class UploadStore:
    """管理 data/upload 目录下的用户上传文件。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or UPLOAD_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def _meta_path(self, file_id: str) -> Path:
        return self.root / f"{file_id}.meta.json"

    def _validate_file_id(self, file_id: str) -> None:
        if not _FILE_ID_PATTERN.match(file_id):
            raise ValueError(f"Invalid file_id: {file_id}")

    def _resolve_checked(self, file_id: str) -> Path:
        self._validate_file_id(file_id)
        path = (self.root / file_id).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError(f"Invalid file_id path: {file_id}")
        return path

    def _build_file_id(self, original_name: str) -> str:
        suffix = Path(original_name).suffix.lower()
        return f"{uuid.uuid4()}{suffix}"

    def save_from_path(self, source_path: str | Path, original_name: str | None = None) -> str:
        """从本地临时路径复制到 upload 目录，返回 file_id。"""
        src = Path(source_path)
        if not src.is_file():
            raise FileNotFoundError(f"Upload source not found: {source_path}")

        orig = original_name or src.name
        file_id = self._build_file_id(orig)
        target = self.root / file_id
        shutil.copy2(src, target)

        meta = UploadedFileMeta(
            file_id=file_id,
            original_name=orig,
            size=target.stat().st_size,
            uploaded_at=datetime.now(timezone.utc).isoformat(),
        )
        self._meta_path(file_id).write_text(
            json.dumps(meta.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return file_id

    def save_bytes(self, data: bytes, original_name: str) -> str:
        """将字节内容写入 upload 目录，返回 file_id。"""
        file_id = self._build_file_id(original_name)
        target = self.root / file_id
        target.write_bytes(data)

        meta = UploadedFileMeta(
            file_id=file_id,
            original_name=original_name,
            size=len(data),
            uploaded_at=datetime.now(timezone.utc).isoformat(),
        )
        self._meta_path(file_id).write_text(
            json.dumps(meta.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return file_id

    def exists(self, file_id: str) -> bool:
        try:
            return self._resolve_checked(file_id).is_file()
        except ValueError:
            return False

    def get_path(self, file_id: str) -> Path:
        """解析 file_id 为绝对路径；不存在时抛出 FileNotFoundError。"""
        path = self._resolve_checked(file_id)
        if not path.is_file():
            raise FileNotFoundError(f"Uploaded file not found: {file_id}")
        return path

    def get_metadata(self, file_id: str) -> UploadedFileMeta:
        path = self.get_path(file_id)
        meta_path = self._meta_path(file_id)
        if meta_path.is_file():
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            return UploadedFileMeta(
                file_id=data.get("file_id", file_id),
                original_name=data.get("original_name", file_id),
                size=int(data.get("size", path.stat().st_size)),
                uploaded_at=data.get("uploaded_at", ""),
                content_type=data.get("content_type", ""),
            )
        return UploadedFileMeta(
            file_id=file_id,
            original_name=file_id,
            size=path.stat().st_size,
            uploaded_at="",
        )

    def read_text(self, file_id: str, max_chars: int = 200_000) -> str:
        """读取文本类上传文件；超出 max_chars 时截断并附加提示。"""
        path = self.get_path(file_id)
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars:
            return f"{text[:max_chars]}\n\n...[已截断，共 {len(text)} 字符]"
        return text


_upload_store: UploadStore | None = None


def get_upload_store() -> UploadStore:
    """获取上传存储单例。"""
    global _upload_store
    if _upload_store is None:
        _upload_store = UploadStore()
    return _upload_store
