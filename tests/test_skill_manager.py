"""Skill 包管理器（SkillPackageManager）单元测试。

测试目的：
- **SkillMeta**：技能元数据名称、描述等字段的校验规则
- **SecurityScanner**：ZIP 包路径遍历、危险扩展名等安全扫描
- **parse_skill_md**：从 SKILL.md 解析 YAML frontmatter
- **SkillPackageManager**：上传、列表、卸载等完整生命周期

Fixtures 说明：
- ``manager``：使用 pytest 临时目录，避免污染真实 ``app/skills/`` 目录
- ``valid_skill_zip``：结构合法的标准 Skill ZIP 二进制内容
- ``dangerous_skill_zip``：含路径遍历与 .exe 等恶意特征的 ZIP
- ``no_skill_md_zip``：缺少 SKILL.md 的无效包
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from app.skills.manager import (
    SkillPackageManager,
    SkillMeta,
    SecurityScanner,
    parse_skill_md,
    _load_manifest,
    _save_manifest,
    SKILL_DIR,
)


# ─── Fixtures ──────────────────────────────────

@pytest.fixture
def manager(tmp_path):
    """创建使用临时目录的 SkillPackageManager。

    ``tmp_path`` 是 pytest 内置 fixture，每次测试自动分配独立临时文件夹。
    """
    return SkillPackageManager(skills_dir=tmp_path / "skills")


@pytest.fixture
def valid_skill_zip():
    """创建一个结构合法、可通过安全扫描的 Skill ZIP 包（bytes）。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # SKILL.md — Skill 的元数据与说明文档（含 YAML frontmatter）
        skill_md = """---
name: test-skill
description: A test skill for unit testing
version: 1.0.0
author: tester
category: test
tags: [test, demo]
---

# Test Skill

## When to Use
- When you need to test something

## Instructions
1. Do step 1
2. Do step 2
"""
        zf.writestr("test-skill/SKILL.md", skill_md)

        # 一个 Python 脚本 — 模拟 Skill 附带的可执行脚本
        script = '''#!/usr/bin/env python3
import sys
print(f"Hello from test-skill: {sys.argv[1:]}")
'''
        zf.writestr("test-skill/scripts/hello.py", script)

        # 一个资源文件 — 模拟 Skill 附带的静态资源
        zf.writestr("test-skill/resources/data.json", '{"key": "value"}')

    buf.seek(0)  # 将读写指针移回开头，便于 getvalue() 读取完整内容
    return buf.getvalue()


@pytest.fixture
def dangerous_skill_zip():
    """创建一个包含路径遍历与危险扩展名的恶意 ZIP 包。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("evil-skill/SKILL.md", """---
name: evil-skill
description: A malicious skill
---

# Evil Skill
""")
        # 路径遍历攻击：试图解压到 ZIP 根目录之外
        zf.writestr("../../../etc/passwd", "root:x:0:0::/root:/bin/bash")
        # 危险扩展名：.exe 等可执行文件应被安全扫描拒绝
        zf.writestr("evil-skill/scripts/malware.exe", "binary content")

    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def no_skill_md_zip():
    """创建一个没有 SKILL.md 的 ZIP 包（应上传失败）。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("some-dir/readme.txt", "This is not a skill")

    buf.seek(0)
    return buf.getvalue()


# ─── SkillMeta 验证 ───────────────────────────

class TestSkillMeta:
    """SkillMeta 数据模型字段校验测试。"""

    def test_valid_name(self):
        """小写连字符形式的名称应合法。"""
        meta = SkillMeta(name="my-skill", description="test")
        assert meta.name == "my-skill"

    def test_invalid_name_uppercase(self):
        """含大写字母的名称应抛出 ValueError。"""
        with pytest.raises(ValueError, match="invalid"):
            SkillMeta(name="MySkill", description="test")

    def test_invalid_name_spaces(self):
        """含空格的名称应抛出 ValueError。"""
        with pytest.raises(ValueError, match="invalid"):
            SkillMeta(name="my skill", description="test")

    def test_reserved_name(self):
        """保留名称（如 system）应被拒绝。"""
        with pytest.raises(ValueError, match="reserved"):
            SkillMeta(name="system", description="test")

    def test_description_too_long(self):
        """描述超过长度上限时应抛出 ValueError。"""
        with pytest.raises(ValueError):
            SkillMeta(name="test", description="x" * 1025)


# ─── SecurityScanner ──────────────────────────

class TestSecurityScanner:
    """ZIP 安全扫描器测试。"""

    def test_scan_clean_zip(self, valid_skill_zip):
        """合法 ZIP 扫描结果应无警告。"""
        warnings = SecurityScanner.scan_zip(valid_skill_zip)
        assert len(warnings) == 0

    def test_scan_dangerous_zip(self, dangerous_skill_zip):
        """恶意 ZIP 应产生路径遍历与危险文件相关警告。"""
        warnings = SecurityScanner.scan_zip(dangerous_skill_zip)
        assert any("traversal" in w.lower() for w in warnings)
        assert any("dangerous" in w.lower() for w in warnings)


# ─── parse_skill_md ───────────────────────────

class TestParseSkillMd:
    """SKILL.md 解析函数测试。"""

    def test_parse_valid(self, tmp_path):
        """完整 frontmatter 应正确解析 name、version 等字段。"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("""---
name: my-test
description: Test skill
version: 2.0.0
author: me
category: dev
---

# My Test
""")
        meta = parse_skill_md(skill_md)
        assert meta.name == "my-test"
        assert meta.version == "2.0.0"

    def test_parse_missing_required(self, tmp_path):
        """缺少必填字段（如 description）时应抛出 ValueError。"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("""---
name: my-test
---

# My Test
""")
        with pytest.raises(ValueError, match="missing required"):
            parse_skill_md(skill_md)

    def test_parse_no_frontmatter(self, tmp_path):
        """没有 YAML frontmatter 时应抛出 ValueError。"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("# Just a heading")
        with pytest.raises(ValueError, match="frontmatter"):
            parse_skill_md(skill_md)


# ─── SkillPackageManager 集成测试 ─────────────

class TestSkillPackageManager:
    """Skill 上传、列表、卸载等集成流程测试。"""

    @pytest.mark.asyncio
    async def test_upload_valid_skill(self, manager, valid_skill_zip):
        """合法 Skill 应上传成功，文件落盘且 manifest 更新。"""
        result = await manager.upload(valid_skill_zip, uploaded_by="tester")
        assert result.success is True
        assert result.skill_name == "test-skill"
        assert result.version == "1.0.0"
        assert "installed successfully" in result.message

        # 验证文件已解压安装到 skills 目录
        skill_dir = manager.skills_dir / "test-skill"
        assert skill_dir.exists()
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "scripts" / "hello.py").exists()
        assert (skill_dir / "resources" / "data.json").exists()

        # 验证全局 manifest 记录了该 Skill 的版本信息
        manifest = _load_manifest()
        assert "test-skill" in manifest
        assert manifest["test-skill"].version == "1.0.0"

    @pytest.mark.asyncio
    async def test_upload_no_skill_md(self, manager, no_skill_md_zip):
        """缺少 SKILL.md 的包应上传失败并返回明确错误信息。"""
        result = await manager.upload(no_skill_md_zip, uploaded_by="tester")
        assert result.success is False
        assert "No SKILL.md" in result.message

    @pytest.mark.asyncio
    async def test_upload_dangerous_rejected(self, manager, dangerous_skill_zip):
        """未通过安全扫描的包应被拒绝。"""
        result = await manager.upload(dangerous_skill_zip, uploaded_by="tester")
        assert result.success is False
        assert "security" in result.message.lower() or "rejected" in result.message.lower()

    @pytest.mark.asyncio
    async def test_upload_replace_existing(self, manager, valid_skill_zip):
        """同名 Skill 再次上传应成功覆盖（升级/替换）。"""
        # 先安装一次
        result1 = await manager.upload(valid_skill_zip, uploaded_by="tester")
        assert result1.success is True

        # 再安装同名 Skill（应该覆盖旧版本）
        result2 = await manager.upload(valid_skill_zip, uploaded_by="tester2")
        assert result2.success is True

    @pytest.mark.asyncio
    async def test_list_installed(self, manager, valid_skill_zip):
        """安装后 list_installed 应返回总数 1 且名称正确。"""
        await manager.upload(valid_skill_zip, uploaded_by="tester")
        result = manager.list_installed()
        assert result.total == 1
        assert result.skills[0].name == "test-skill"

    @pytest.mark.asyncio
    async def test_uninstall(self, manager, valid_skill_zip):
        """卸载已安装的 Skill 应删除目录并返回 True。"""
        await manager.upload(valid_skill_zip, uploaded_by="tester")
        success = manager.uninstall("test-skill")
        assert success is True
        assert not (manager.skills_dir / "test-skill").exists()

    @pytest.mark.asyncio
    async def test_uninstall_nonexistent(self, manager):
        """卸载不存在的 Skill 应返回 False，不抛异常。"""
        success = manager.uninstall("nonexistent")
        assert success is False

    def test_get_skill_dir(self, manager, valid_skill_zip):
        """get_skill_dir 对已安装 Skill 返回路径，对不存在名称返回 None。"""
        import asyncio
        # 同步测试里调用 async upload，用 asyncio.run 执行
        asyncio.run(manager.upload(valid_skill_zip, uploaded_by="tester"))

        skill_dir = manager.get_skill_dir("test-skill")
        assert skill_dir is not None
        assert (skill_dir / "SKILL.md").exists()

        assert manager.get_skill_dir("nonexistent") is None
