"""
Skill 包管理器模块。

负责 Skill ZIP 包的全生命周期管理：
- 上传、解压、校验 SKILL.md 元数据
- 安全扫描（路径遍历、危险扩展名、ZIP 炸弹等）
- 安装到 app/skills/ 目录并维护 _manifest.json 清单
- 列出与卸载已安装 Skill

与第三方库 pydantic-ai-skills 的 SkillsToolset 共用同一 skills 目录，
Agent 安装 Skill 后即可动态加载其中的指令与脚本。

依赖安装: pip install pydantic-ai-skills

面向小白：
- Skill 是一个文件夹，必须包含 SKILL.md（YAML 头 + Markdown 说明）
- ZIP 上传后会解压到 app/skills/<skill-name>/
- manifest 记录每个 Skill 的版本、作者、上传时间等元信息
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

# 本模块所在目录，即 app/skills/
SKILL_DIR = Path(__file__).parent
# 已安装 Skill 的清单文件路径
MANIFEST_PATH = SKILL_DIR / "_manifest.json"

# SKILL.md frontmatter 中必须出现的字段
REQUIRED_FIELDS = {"name", "description"}

# name 合法字符：小写字母、数字、连字符，1~64 字符
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

# 上传包中不允许出现的可执行/脚本扩展名
DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".wsf",
    ".msi", ".dll", ".so", ".dylib", ".app", ".deb", ".rpm",
}

# 用于检测 ZIP 内路径遍历攻击的特征串
PATH_TRAVERSAL_PATTERNS = ["../", "..\\", "/etc/", "\\windows\\"]


# ─── 数据模型 ──────────────────────────────────

class SkillMeta(BaseModel):
    """
    从 SKILL.md 的 YAML frontmatter 解析出的 Skill 元数据。

    字段说明:
            name: 唯一标识，只能用小写字母、数字和连字符
            description: 简短描述，供 Agent 判断何时启用该 Skill
            version / author / category / tags: 可选的扩展信息
    """

    name: str = Field(..., description="Skill 唯一标识，小写+连字符")
    description: str = Field(..., max_length=1024)
    version: str = Field(default="1.0.0")
    author: str = Field(default="unknown")
    category: str = Field(default="general")
    tags: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """校验 name 格式，并拒绝系统保留字。"""
        if not NAME_PATTERN.match(v):
            raise ValueError(
                f"Skill name '{v}' is invalid. "
                "Must be 1-64 chars, lowercase letters, digits, and hyphens only."
            )
        # 保留字不能与框架内置概念冲突
        reserved = {"anthropic", "claude", "system", "agent", "tool", "skill"}
        if v.lower() in reserved:
            raise ValueError(f"Skill name '{v}' is reserved.")
        return v


class SkillManifestEntry(BaseModel):
    """_manifest.json 中每条已安装 Skill 的记录。"""

    name: str
    version: str
    author: str
    category: str
    uploaded_at: str
    uploaded_by: str
    file_count: int
    has_scripts: bool
    has_resources: bool
    checksum: str = Field(default="", description="ZIP 的 SHA256 校验和（截断前 16 位）")


class UploadResult(BaseModel):
    """upload() 方法的返回结构，也用于 REST API 响应。"""

    success: bool
    skill_name: str
    version: str
    message: str
    file_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class SkillListResult(BaseModel):
    """list_installed() 的返回：Skill 列表 + 总数。"""

    skills: list[SkillManifestEntry]
    total: int


# ─── 安全扫描器 ────────────────────────────────

class SecurityScanner:
    """
    对上传的 ZIP 和解压后的目录做静态安全扫描。

    扫描不会执行代码，只检查文件名、大小、压缩比和脚本中的危险模式。
    """

    @staticmethod
    def scan_zip(zip_bytes: bytes) -> list[str]:
        """
        扫描 ZIP 二进制内容。

        参数:
                zip_bytes: 完整 ZIP 文件字节

        返回:
                警告信息列表；空列表表示未发现明显风险
        """
        warnings: list[str] = []

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for info in zf.infolist():
                # 1. 路径遍历：如 ../../etc/passwd
                for pattern in PATH_TRAVERSAL_PATTERNS:
                    if pattern in info.filename:
                        warnings.append(
                            f"Path traversal detected: '{info.filename}' contains '{pattern}'"
                        )

                # 2. 绝对路径：以 / 或 \ 开头
                if info.filename.startswith("/") or info.filename.startswith("\\"):
                    warnings.append(f"Absolute path detected: '{info.filename}'")

                # 3. 危险扩展名
                suffix = Path(info.filename).suffix.lower()
                if suffix in DANGEROUS_EXTENSIONS:
                    warnings.append(
                        f"Dangerous file extension: '{info.filename}' ({suffix})"
                    )

                # 4. 单文件超过 50MB
                if info.file_size > 50 * 1024 * 1024:
                    warnings.append(
                        f"Oversized file: '{info.filename}' ({info.file_size / 1024 / 1024:.1f} MB)"
                    )

                # 5. ZIP 炸弹：解压后体积远大于压缩体积（压缩比 > 100x）
                if info.compress_size > 0 and info.file_size / info.compress_size > 100:
                    warnings.append(
                        f"Possible zip bomb: '{info.filename}' "
                        f"(ratio: {info.file_size / info.compress_size:.0f}x)"
                    )

        return warnings

    @staticmethod
    def scan_skill_content(skill_dir: Path) -> list[str]:
        """
        扫描解压后的 Skill 目录（重点检查 scripts/ 下的 Python 文件）。

        参数:
                skill_dir: Skill 根目录（含 SKILL.md 的文件夹）

        返回:
                警告列表
        """
        warnings: list[str] = []

        # 在 scripts 目录中查找危险 API 调用模式
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
                        pass  # 读失败则跳过该文件

        # 整个 Skill 目录总体积超过 100MB 时警告
        total_size = sum(f.stat().st_size for f in skill_dir.rglob("*") if f.is_file())
        if total_size > 100 * 1024 * 1024:
            warnings.append(
                f"Total skill size exceeds 100MB ({total_size / 1024 / 1024:.1f} MB)"
            )

        return warnings


# ─── Frontmatter 解析器 ────────────────────────

def parse_skill_md(skill_md_path: Path) -> SkillMeta:
    """
    解析 SKILL.md 文件顶部的 YAML frontmatter。

    SKILL.md 标准格式:
            ---
            name: my-skill
            description: ...
            ---
            # Markdown 正文

    为减少依赖，此处用手写解析器而非 PyYAML。

    参数:
            skill_md_path: SKILL.md 的路径

    返回:
            SkillMeta 实例

    异常:
            ValueError: frontmatter 格式错误或缺少必需字段
    """
    content = skill_md_path.read_text(encoding="utf-8")

    if not content.startswith("---"):
        raise ValueError(f"SKILL.md must start with YAML frontmatter (---). Got: {skill_md_path}")

    # 找第二个 --- 作为 frontmatter 结束位置
    end = content.find("---", 3)
    if end == -1:
        raise ValueError(f"SKILL.md frontmatter not closed (missing closing ---). Got: {skill_md_path}")

    frontmatter_str = content[3:end].strip()

    # 逐行解析 key: value（简易实现，不支持复杂嵌套 YAML）
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
                # 支持 tags: [a, b] 或 tags: single
                if value.startswith("[") and value.endswith("]"):
                    meta[key] = [t.strip().strip("'\"") for t in value[1:-1].split(",")]
                else:
                    meta[key] = [value]

    missing = REQUIRED_FIELDS - set(meta.keys())
    if missing:
        raise ValueError(f"SKILL.md missing required fields: {missing}")

    return SkillMeta(**meta)


# ─── Manifest 管理 ─────────────────────────────

def _load_manifest() -> dict[str, SkillManifestEntry]:
    """从磁盘读取 _manifest.json，不存在则返回空字典。"""
    if not MANIFEST_PATH.exists():
        return {}
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {k: SkillManifestEntry(**v) for k, v in data.items()}


def _save_manifest(entries: dict[str, SkillManifestEntry]) -> None:
    """将 manifest 字典写回 _manifest.json。"""
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {k: v.model_dump() for k, v in entries.items()}
    MANIFEST_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ─── 核心：SkillPackageManager ─────────────────

class SkillPackageManager:
    """
    Skill 包管理器 — 处理 ZIP 上传、解压、校验、安装、卸载。

    与 pydantic-ai-skills 的 SkillsToolset 共享同一个 skills/ 目录，
    因此通过本类安装的 Skill 会立即对 Agent 可见（若启用了 auto_reload）。
    """

    def __init__(self, skills_dir: Path | None = None):
        """
        初始化管理器。

        参数:
                skills_dir: Skill 根目录，默认 app/skills/
        """
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

        处理流程:
        1. ZIP 安全扫描
        2. 解压到临时目录
        3. 查找并解析 SKILL.md
        4. 内容安全扫描
        5. 复制到 skills_dir/<name>，更新 manifest

        ZIP 包结构示例:
                my-skill.zip
                └── my-skill/
                        ├── SKILL.md      (必需)
                        ├── scripts/      (可选)
                        └── resources/    (可选)

        参数:
                zip_bytes: ZIP 文件二进制内容
                uploaded_by: 上传者标识，写入 manifest
                allow_warnings: False 时，有任何警告即拒绝安装

        返回:
                UploadResult（success=False 时 message 说明原因）
        """
        all_warnings: list[str] = []

        # 1. 安全扫描 ZIP
        zip_warnings = self.scanner.scan_zip(zip_bytes)
        all_warnings.extend(zip_warnings)

        # 严重问题（路径遍历、危险扩展名）直接拒绝，不继续解压
        critical = [w for w in zip_warnings if "traversal" in w.lower() or "dangerous" in w.lower()]
        if critical:
            return UploadResult(
                success=False,
                skill_name="",
                version="",
                message=f"Upload rejected — critical security issues: {critical[0]}",
                warnings=all_warnings,
            )

        # 2. 解压到系统临时目录（with 块结束自动删除）
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

            # 3. 在解压树中递归查找 SKILL.md
            skill_md_files = list(tmp_dir.rglob("SKILL.md"))
            if not skill_md_files:
                return UploadResult(
                    success=False, skill_name="", version="",
                    message="No SKILL.md found in ZIP. A valid skill must contain SKILL.md.",
                    warnings=all_warnings,
                )

            skill_md = skill_md_files[0]
            skill_root = skill_md.parent  # SKILL.md 所在目录即 Skill 根目录

            # 4. 解析 frontmatter
            try:
                meta = parse_skill_md(skill_md)
            except ValueError as e:
                return UploadResult(
                    success=False, skill_name="", version="",
                    message=f"Invalid SKILL.md: {e}", warnings=all_warnings,
                )

            # 5. 解压后内容扫描
            content_warnings = self.scanner.scan_skill_content(skill_root)
            all_warnings.extend(content_warnings)

            # 6. 若不允许警告且存在警告，则拒绝
            if not allow_warnings and all_warnings:
                return UploadResult(
                    success=False, skill_name=meta.name, version=meta.version,
                    message=f"Upload rejected — {len(all_warnings)} warning(s) found and allow_warnings=False",
                    warnings=all_warnings,
                )

            # 7. 安装：复制到目标目录，同名则先备份
            target_dir = self.skills_dir / meta.name

            if target_dir.exists():
                backup_dir = self.skills_dir / f"_backup_{meta.name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                shutil.move(str(target_dir), str(backup_dir))

            shutil.copytree(str(skill_root), str(target_dir))

            # 8. 计算 ZIP 的 SHA256 摘要（取前 16 位便于阅读）
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
        """返回 manifest 中所有已安装 Skill 的列表。"""
        manifest = _load_manifest()
        return SkillListResult(
            skills=list(manifest.values()),
            total=len(manifest),
        )

    def uninstall(self, skill_name: str) -> bool:
        """
        卸载指定 Skill：删除目录并从 manifest 移除记录。

        参数:
                skill_name: Skill 的 name 字段

        返回:
                True 表示卸载成功；False 表示目录不存在

        异常:
                ValueError: 检测到路径遍历攻击（skill_name 试图跳出 skills_dir）
        """
        skill_dir = self.skills_dir / skill_name

        if not skill_dir.exists():
            return False

        # 解析真实路径后必须仍在 skills_dir 之下
        resolved = skill_dir.resolve()
        if not str(resolved).startswith(str(self.skills_dir.resolve())):
            raise ValueError(f"Path traversal attempt detected: {skill_name}")

        shutil.rmtree(str(skill_dir))

        manifest = _load_manifest()
        manifest.pop(skill_name, None)
        _save_manifest(manifest)

        return True

    def get_skill_dir(self, skill_name: str) -> Path | None:
        """
        获取已安装 Skill 的目录路径。

        仅当目录存在且包含 SKILL.md 时返回 Path，否则 None。
        """
        skill_dir = self.skills_dir / skill_name
        if skill_dir.exists() and (skill_dir / "SKILL.md").exists():
            return skill_dir
        return None

    def get_skills_directory(self) -> Path:
        """返回 skills 根目录，供 SkillsToolset 或运维脚本使用。"""
        return self.skills_dir
