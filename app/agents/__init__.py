"""Agent 包初始化 — 对外暴露 Agent 注册表的公共接口。

Python 包中的 ``__init__.py`` 文件有两个作用：
1. 把目录标记为可导入的 Python 包
2. 定义 ``from app.agents import xxx`` 时能直接拿到哪些符号

本包通过 ``__all__`` 明确声明公开 API，避免外部依赖内部实现细节。

使用示例::

    from app.agents import get_agent, AgentName

    agent = get_agent(AgentName.qa_assistant)
    result = await agent.run("什么是 Python？", deps=deps)
"""

from app.agents.registry import get_agent, list_agents, AgentName, AGENTS

# __all__ 列表中的名称是 ``from app.agents import *`` 时会被导入的符号
# 也是本包对外承诺的稳定公共接口
__all__ = ["get_agent", "list_agents", "AgentName", "AGENTS"]
