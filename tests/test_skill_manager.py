"""Skill 包管理器测试"""

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
    """创建使用临时目录的 SkillPackageManager"""
    return SkillPackageManager(skills_dir=tmp_path / "skills")


@pytest.fixture
def valid_skill_zip():
    """创建一个合法的 Skill ZIP 包"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # SKILL.md
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

        # 一个 Python 脚本
        script = '''#!/usr/bin/env python3
import sys
print(f"Hello from test-skill: {sys.argv[1:]}")
'''
        zf.writestr("test-skill/scripts/hello.py", script)

        # 一个资源文件
        zf.writestr("test-skill/resources/data.json", '{"key": "value"}')

    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def dangerous_skill_zip():
    """创建一个包含危险文件的 ZIP 包"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("evil-skill/SKILL.md", """---
name: evil-skill
description: A malicious skill
---

# Evil Skill
""")
        # 路径遍历攻击
        zf.writestr("../../../etc/passwd", "root:x:0:0::/root:/bin/bash")
        # 危险扩展名
        zf.writestr("evil-skill/scripts/malware.exe", "binary content")

    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def no_skill_md_zip():
    """创建一个没有 SKILL.md 的 ZIP 包"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("some-dir/readme.txt", "This is not a skill")

    buf.seek(0)
    return buf.getvalue()


# ─── SkillMeta 验证 ───────────────────────────

class TestSkillMeta:
    def test_valid_name(self):
        meta = SkillMeta(name="my-skill", description="test")
        assert meta.name == "my-skill"

    def test_invalid_name_uppercase(self):
        with pytest.raises(ValueError, match="invalid"):
            SkillMeta(name="MySkill", description="test")

    def test_invalid_name_spaces(self):
        with pytest.raises(ValueError, match="invalid"):
            SkillMeta(name="my skill", description="test")

    def test_reserved_name(self):
        with pytest.raises(ValueError, match="reserved"):
            SkillMeta(name="system", description="test")

    def test_description_too_long(self):
        with pytest.raises(ValueError):
            SkillMeta(name="test", description="x" * 1025)


# ─── SecurityScanner ──────────────────────────

class TestSecurityScanner:
    def test_scan_clean_zip(self, valid_skill_zip):
        warnings = SecurityScanner.scan_zip(valid_skill_zip)
        assert len(warnings) == 0

    def test_scan_dangerous_zip(self, dangerous_skill_zip):
        warnings = SecurityScanner.scan_zip(dangerous_skill_zip)
        assert any("traversal" in w.lower() for w in warnings)
        assert any("dangerous" in w.lower() for w in warnings)


# ─── parse_skill_md ───────────────────────────

class TestParseSkillMd:
    def test_parse_valid(self, tmp_path):
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
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("""---
name: my-test
---

# My Test
""")
        with pytest.raises(ValueError, match="missing required"):
            parse_skill_md(skill_md)

    def test_parse_no_frontmatter(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("# Just a heading")
        with pytest.raises(ValueError, match="frontmatter"):
            parse_skill_md(skill_md)


# ─── SkillPackageManager 集成测试 ─────────────

class TestSkillPackageManager:
    @pytest.mark.asyncio
    async def test_upload_valid_skill(self, manager, valid_skill_zip):
        result = await manager.upload(valid_skill_zip, uploaded_by="tester")
        assert result.success is True
        assert result.skill_name == "test-skill"
        assert result.version == "1.0.0"
        assert "installed successfully" in result.message

        # 验证文件已安装
        skill_dir = manager.skills_dir / "test-skill"
        assert skill_dir.exists()
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "scripts" / "hello.py").exists()
        assert (skill_dir / "resources" / "data.json").exists()

        # 验证 manifest 已更新
        manifest = _load_manifest()
        assert "test-skill" in manifest
        assert manifest["test-skill"].version == "1.0.0"

    @pytest.mark.asyncio
    async def test_upload_no_skill_md(self, manager, no_skill_md_zip):
        result = await manager.upload(no_skill_md_zip, uploaded_by="tester")
        assert result.success is False
        assert "No SKILL.md" in result.message

    @pytest.mark.asyncio
    async def test_upload_dangerous_rejected(self, manager, dangerous_skill_zip):
        result = await manager.upload(dangerous_skill_zip, uploaded_by="tester")
        assert result.success is False
        assert "security" in result.message.lower() or "rejected" in result.message.lower()

    @pytest.mark.asyncio
    async def test_upload_replace_existing(self, manager, valid_skill_zip):
        # 先安装一次
        result1 = await manager.upload(valid_skill_zip, uploaded_by="tester")
        assert result1.success is True

        # 再安装同名 Skill（应该覆盖旧版本）
        result2 = await manager.upload(valid_skill_zip, uploaded_by="tester2")
        assert result2.success is True

    @pytest.mark.asyncio
    async def test_list_installed(self, manager, valid_skill_zip):
        await manager.upload(valid_skill_zip, uploaded_by="tester")
        result = manager.list_installed()
        assert result.total == 1
        assert result.skills[0].name == "test-skill"

    @pytest.mark.asyncio
    async def test_uninstall(self, manager, valid_skill_zip):
        await manager.upload(valid_skill_zip, uploaded_by="tester")
        success = manager.uninstall("test-skill")
        assert success is True
        assert not (manager.skills_dir / "test-skill").exists()

    @pytest.mark.asyncio
    async def test_uninstall_nonexistent(self, manager):
        success = manager.uninstall("nonexistent")
        assert success is False

    def test_get_skill_dir(self, manager, valid_skill_zip):
        import asyncio
        asyncio.run(manager.upload(valid_skill_zip, uploaded_by="tester"))

        skill_dir = manager.get_skill_dir("test-skill")
        assert skill_dir is not None
        assert (skill_dir / "SKILL.md").exists()

        assert manager.get_skill_dir("nonexistent") is None
