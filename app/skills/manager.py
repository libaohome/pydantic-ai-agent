"""
Skill 包管理器 — 负责 ZIP 上传、解压、校验、安全扫描、版本管理。
与 pydantic-ai-skills 的 SkillsToolset 配合，实现完整的动态 Skill 加载。

依赖：pip install pydantic-ai-skills
"""

from __future__ import annotations

import io
import json
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ─── 常量 ──────────────────────────────────────

SKILL_DIR = Path(__file__).parent  # app/skills/
MANIFEST_PATH = SKILL_DIR / "_manifest.json"

# SKILL.md frontmatter 中的必需字段
REQUIRED_FIELDS = {"name", "description"}

# name 合法字符：小写字母、数字、连字符
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

# 危险文件扩展名黑名单
DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".wsf",
    ".msi", ".dll", ".so", ".dylib", ".app", ".deb", ".rpm",
}

# 路径遍历攻击关键词
PATH_TRAVERSAL_PATTERNS = ["../", "..\\", "/etc/", "\\windows\\"]


# ─── 数据模型 ──────────────────────────────────

class SkillMeta(BaseModel):
    """SKILL.md frontmatter 解析结果"""
    name: str = Field(..., description="Skill 唯一标识，小写+连字符")
    description: str = Field(..., max_length=1024)
    version: str = Field(default="1.0.0")
    author: str = Field(default="unknown")
    category: str = Field(default="general")
    tags: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_PATTERN.match(v):
            raise ValueError(
                f"Skill name '{v}' is invalid. "
                "Must be 1-64 chars, lowercase letters, digits, and hyphens only."
            )
        # 保留字检查
        reserved = {"anthropic", "claude", "system", "agent", "tool", "skill"}
        if v.lower() in reserved:
            raise ValueError(f"Skill name '{v}' is reserved.")
        return v


class SkillManifestEntry(BaseModel):
    """manifest.json 中的单条记录"""
    name: str
    version: str
    author: str
    category: str
    uploaded_at: str
    uploaded_by: str
    file_count: int
    has_scripts: bool
    has_resources: bool
    checksum: str = Field(default="", description="ZIP 的 SHA256 校验和")


class UploadResult(BaseModel):
    """上传接口返回结果"""
    success: bool
    skill_name: str
    version: str
    message: str
    file_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class SkillListResult(BaseModel):
    """已安装 Skill 列表"""
    skills: list[SkillManifestEntry]
    total: int


# ─── 安全扫描器 ────────────────────────────────

class SecurityScanner:
    """上传包安全扫描"""

    @staticmethod
    def scan_zip(zip_bytes: bytes) -> list[str]:
        """扫描 ZIP 内容，返回警告列表。空列表 = 安全"""
        warnings: list[str] = []

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for info in zf.infolist():
                # 1. 路径遍历检查
                for pattern in PATH_TRAVERSAL_PATTERNS:
                    if pattern in info.filename:
                        warnings.append(
                            f"Path traversal detected: '{info.filename}' contains '{pattern}'"
                        )

                # 2. 绝对路径检查
                if info.filename.startswith("/") or info.filename.startswith("\\"):
                    warnings.append(f"Absolute path detected: '{info.filename}'")

                # 3. 危险扩展名检查
                suffix = Path(info.filename).suffix.lower()
                if suffix in DANGEROUS_EXTENSIONS:
                    warnings.append(
                        f"Dangerous file extension: '{info.filename}' ({suffix})"
                    )

                # 4. 超大文件检查（单个文件 > 50MB）
                if info.file_size > 50 * 1024 * 1024:
                    warnings.append(
                        f"Oversized file: '{info.filename}' ({info.file_size / 1024 / 1024:.1f} MB)"
                    )

                # 5. ZIP 炸弹检查（压缩比 > 100x）
                if info.compress_size > 0 and info.file_size / info.compress_size > 100:
                    warnings.append(
                        f"Possible zip bomb: '{info.filename}' "
                        f"(ratio: {info.file_size / info.compress_size:.0f}x)"
                    )

        return warnings

    @staticmethod
    def scan_skill_content(skill_dir: Path) -> list[str]:
        """扫描解压后的 Skill 目录内容"""
        warnings: list[str] = []

        # 检查脚本文件是否包含危险命令
        scripts_dir = skill_dir / "scripts"
        if scripts_dir.exists():
            for script_file in scripts_dir.rglob("*"):
                if script_file.is_file() and script_file.suffix == ".py":
                    try:
                        content = script_file.read_text(encoding="utf-8", errors="ignore")
                        dangerous_patterns = [
                            ("os.system(", "os.system() call — use subprocess instead"),
                            ("subprocess.call(", "subprocess.call() — consider subprocess.run()"),
                            ("eval(", "eval() usage — security risk"),
                            ("exec(", "exec() usage — security risk"),
                            ("__import__(", "__import__() usage — security risk"),
                            ("rm -rf", "destructive rm command"),
                            ("shutil.rmtree(", "shutil.rmtree() — verify target path"),
                        ]
                        for pattern, msg in dangerous_patterns:
                            if pattern in content:
                                warnings.append(f"{script_file.name}: {msg}")
                    except Exception:
                        pass

        # 检查总文件大小（> 100MB 警告）
        total_size = sum(f.stat().st_size for f in skill_dir.rglob("*") if f.is_file())
        if total_size > 100 * 1024 * 1024:
            warnings.append(
                f"Total skill size exceeds 100MB ({total_size / 1024 / 1024:.1f} MB)"
            )

        return warnings


# ─── Frontmatter 解析器 ────────────────────────

def parse_skill_md(skill_md_path: Path) -> SkillMeta:
    """解析 SKILL.md 的 YAML frontmatter"""
    content = skill_md_path.read_text(encoding="utf-8")

    if not content.startswith("---"):
        raise ValueError(f"SKILL.md must start with YAML frontmatter (---). Got: {skill_md_path}")

    # 提取 frontmatter
    end = content.find("---", 3)
    if end == -1:
        raise ValueError(f"SKILL.md frontmatter not closed (missing closing ---). Got: {skill_md_path}")

    frontmatter_str = content[3:end].strip()

    # 简易 YAML 解析（避免引入 pyyaml 依赖）
    meta: dict = {}
    for line in frontmatter_str.split("\n"):
        line = line.strip()
        if ":" in line and not line.startswith("-"):
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key in REQUIRED_FIELDS or key in {"version", "author", "category"}:
                meta[key] = value
            elif key == "tags":
                # tags: [tag1, tag2] 格式
                if value.startswith("[") and value.endswith("]"):
                    meta[key] = [t.strip().strip("'\"") for t in value[1:-1].split(",")]
                else:
                    meta[key] = [value]

    # 验证必需字段
    missing = REQUIRED_FIELDS - set(meta.keys())
    if missing:
        raise ValueError(f"SKILL.md missing required fields: {missing}")

    return SkillMeta(**meta)


# ─── Manifest 管理 ─────────────────────────────

def _load_manifest() -> dict[str, SkillManifestEntry]:
    """加载 manifest.json"""
    if not MANIFEST_PATH.exists():
        return {}
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {k: SkillManifestEntry(**v) for k, v in data.items()}


def _save_manifest(entries: dict[str, SkillManifestEntry]) -> None:
    """保存 manifest.json"""
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {k: v.model_dump() for k, v in entries.items()}
    MANIFEST_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ─── 核心：SkillPackageManager ─────────────────

class SkillPackageManager:
    """
    Skill 包管理器 — 处理 ZIP 上传、解压、校验、安装、卸载。
    与 pydantic-ai-skills 的 SkillsToolset 共享同一个 skills/ 目录。
    """

    def __init__(self, skills_dir: Path | None = None):
        self.skills_dir = skills_dir or SKILL_DIR
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.scanner = SecurityScanner()

    async def upload(
        self,
        zip_bytes: bytes,
        uploaded_by: str = "anonymous",
        allow_warnings: bool = True,
    ) -> UploadResult:
        """
        上传并安装一个 Skill ZIP 包。

        ZIP 包必须包含至少一个含 SKILL.md 的目录：
        ┌─ my-skill.zip
        │  └── my-skill/
        │      ├── SKILL.md      (必需)
        │      ├── scripts/      (可选)
        │      └── resources/    (可选)
        """
        all_warnings: list[str] = []

        # 1. 安全扫描 ZIP
        zip_warnings = self.scanner.scan_zip(zip_bytes)
        all_warnings.extend(zip_warnings)

        # 如果有严重安全警告（路径遍历/危险扩展名），直接拒绝
        critical = [w for w in zip_warnings if "traversal" in w.lower() or "dangerous" in w.lower()]
        if critical:
            return UploadResult(
                success=False,
                skill_name="",
                version="",
                message=f"Upload rejected — critical security issues: {critical[0]}",
                warnings=all_warnings,
            )

        # 2. 解压到临时目录
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)

            try:
                with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                    zf.extractall(tmp_dir)
            except zipfile.BadZipFile as e:
                return UploadResult(
                    success=False, skill_name="", version="",
                    message=f"Invalid ZIP file: {e}", warnings=all_warnings,
                )

            # 3. 查找 SKILL.md
            skill_md_files = list(tmp_dir.rglob("SKILL.md"))
            if not skill_md_files:
                return UploadResult(
                    success=False, skill_name="", version="",
                    message="No SKILL.md found in ZIP. A valid skill must contain SKILL.md.",
                    warnings=all_warnings,
                )

            # 取第一个 SKILL.md 所在目录作为 skill root
            skill_md = skill_md_files[0]
            skill_root = skill_md.parent

            # 4. 解析 SKILL.md
            try:
                meta = parse_skill_md(skill_md)
            except ValueError as e:
                return UploadResult(
                    success=False, skill_name="", version="",
                    message=f"Invalid SKILL.md: {e}", warnings=all_warnings,
                )

            # 5. 内容安全扫描
            content_warnings = self.scanner.scan_skill_content(skill_root)
            all_warnings.extend(content_warnings)

            # 6. 检查是否允许有警告的包
            if not allow_warnings and all_warnings:
                return UploadResult(
                    success=False, skill_name=meta.name, version=meta.version,
                    message=f"Upload rejected — {len(all_warnings)} warning(s) found and allow_warnings=False",
                    warnings=all_warnings,
                )

            # 7. 安装到目标目录
            target_dir = self.skills_dir / meta.name

            # 如果已存在同名 Skill，备份旧版本
            if target_dir.exists():
                backup_dir = self.skills_dir / f"_backup_{meta.name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                shutil.move(str(target_dir), str(backup_dir))

            # 复制 skill 目录
            shutil.copytree(str(skill_root), str(target_dir))

            # 8. 计算 checksum
            import hashlib
            checksum = hashlib.sha256(zip_bytes).hexdigest()[:16]

            # 9. 更新 manifest
            file_count = sum(1 for _ in target_dir.rglob("*") if _.is_file())
            manifest = _load_manifest()
            manifest[meta.name] = SkillManifestEntry(
                name=meta.name,
                version=meta.version,
                author=meta.author,
                category=meta.category,
                uploaded_at=datetime.now().isoformat(),
                uploaded_by=uploaded_by,
                file_count=file_count,
                has_scripts=(target_dir / "scripts").exists(),
                has_resources=(target_dir / "resources").exists(),
                checksum=checksum,
            )
            _save_manifest(manifest)

            return UploadResult(
                success=True,
                skill_name=meta.name,
                version=meta.version,
                message=f"Skill '{meta.name}' v{meta.version} installed successfully.",
                file_count=file_count,
                warnings=all_warnings,
            )

    def list_installed(self) -> SkillListResult:
        """列出所有已安装的 Skill"""
        manifest = _load_manifest()
        return SkillListResult(
            skills=list(manifest.values()),
            total=len(manifest),
        )

    def uninstall(self, skill_name: str) -> bool:
        """卸载一个 Skill"""
        skill_dir = self.skills_dir / skill_name

        if not skill_dir.exists():
            return False

        # 安全检查：防止路径遍历
        resolved = skill_dir.resolve()
        if not str(resolved).startswith(str(self.skills_dir.resolve())):
            raise ValueError(f"Path traversal attempt detected: {skill_name}")

        shutil.rmtree(str(skill_dir))

        # 更新 manifest
        manifest = _load_manifest()
        manifest.pop(skill_name, None)
        _save_manifest(manifest)

        return True

    def get_skill_dir(self, skill_name: str) -> Path | None:
        """获取指定 Skill 的目录路径"""
        skill_dir = self.skills_dir / skill_name
        if skill_dir.exists() and (skill_dir / "SKILL.md").exists():
            return skill_dir
        return None

    def get_skills_directory(self) -> Path:
        """获取 skills 根目录，供 SkillsToolset 使用"""
        return self.skills_dir
