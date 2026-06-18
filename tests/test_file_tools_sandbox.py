"""file_tools 沙箱 runtime_config 测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.deps import AgentDeps
from app.tools.file_tools import read_file, run_shell, write_file


def _ctx(sandbox_root: str):
    deps = AgentDeps(runtime_config={"sandbox_root": sandbox_root})
    return SimpleNamespace(deps=deps)


@pytest.mark.asyncio
async def test_read_file_denies_outside_sandbox(tmp_path):
    inside = tmp_path / "inside.txt"
    inside.write_text("ok", encoding="utf-8")
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    ctx = _ctx(str(tmp_path))
    assert "ok" == await read_file(str(inside), ctx=ctx)
    assert "outside sandbox" in await read_file(str(outside), ctx=ctx)


@pytest.mark.asyncio
async def test_write_file_denies_outside_sandbox(tmp_path):
    ctx = _ctx(str(tmp_path))
    target = tmp_path.parent / "escape.txt"
    result = await write_file(str(target), "nope", ctx=ctx)
    assert "outside sandbox" in result
    assert not target.exists()


@pytest.mark.asyncio
async def test_run_shell_uses_sandbox_cwd(tmp_path):
    (tmp_path / "marker.txt").write_text("here", encoding="utf-8")
    ctx = _ctx(str(tmp_path))
    output = await run_shell("cat marker.txt", ctx=ctx)
    assert "here" in output
