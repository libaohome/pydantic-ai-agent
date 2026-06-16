"""测试包初始化模块。

本文件使 ``tests/`` 目录被 Python 识别为一个「包」（package）。
有了它，pytest 才能正确发现并导入同目录下的测试模块（如 ``test_llm_manager.py``）。

对于 Python 小白：
- 包 = 包含 ``__init__.py`` 的文件夹，可被 ``import`` 引用
- 本文件可以为空，也可以放测试共用的工具函数；当前仅保留说明性 docstring
"""
