# Pydantic AI Agent Starter

> 基于 [Pydantic AI](https://pydantic.dev/pydantic-ai) 的生产级 AI Agent 服务脚手架，开箱即用的多模型路由、结构化输出、Skill 动态加载与图编排。

---

## 特性一览

| 特性 | 说明 |
|------|------|
| **多模型路由** | 6 个模型预注册（DeepSeek / LongCat / Agnes AI / 商汤），一行别名切换 |
| **结构化输出** | Agent 绑定 Pydantic `output_type`，LLM 返回自动验证 + 失败重试 |
| **依赖注入** | `AgentDeps` dataclass 通过 `RunContext` 注入到工具函数，干净解耦 |
| **Skill 动态加载** | ZIP 上传 → 安全扫描 → 自动安装 → Agent 按需加载执行，无需重启 |
| **图编排** | `pydantic-graph` 定义多 Agent 协作工作流，支持条件路由 |
| **可观测性** | Logfire 全链路追踪（FastAPI + httpx + Agent 调用），开箱即用 |
| **成本追踪** | 每次调用按 Token 计费，全局汇总报告 |
| **安全工具** | Shell 白名单 + 黑名单双检，SQL 只允许 SELECT + 强制 LIMIT |
| **Docker 部署** | 多阶段构建 + docker-compose，含可选 Ollama 本地模型 |
| **Gradio 控制台** | `/ui` 提供 Chat / Agent / Workflow / Model / Skills 可视化管理 |

---

## 技术栈

| 层 | 技术 | 版本 |
|----|------|------|
| Agent 框架 | [Pydantic AI](https://github.com/pydantic/pydantic-ai) | >= 1.0 |
| 图编排 | [pydantic-graph](https://ai.pydantic.org.cn/graph/) | >= 1.0 |
| Skill 加载 | [pydantic-ai-skills](https://github.com/DougTrajano/pydantic-ai-skills) | >= 0.1 |
| 数据验证 | [Pydantic](https://github.com/pydantic/pydantic) V2 | >= 2.10 |
| Web 框架 | [FastAPI](https://github.com/tiangolo/fastapi) | >= 0.115 |
| 数据库 | SQLAlchemy 2.0 + aiosqlite | 异步 ORM |
| 可观测性 | [Logfire](https://logfire.pydantic.dev/) | >= 3.0 |
| Python | CPython | >= 3.11 |

---

## 项目结构

```
pydantic-ai-agent/
├── pyproject.toml                    # 项目配置 + 依赖声明
├── .env.example                      # 环境变量模板
├── .gitignore
│
├── app/
│   ├── main.py                       # FastAPI 应用入口 + 生命周期 + Gradio 挂载
│   │
│   ├── core/                         # 🏗 基础设施层
│   │   ├── config.py                 #   配置中心（pydantic-settings，自动 .env 加载）
│   │   ├── llm.py                    #   LLM 管理器（8 模型预注册 + 成本追踪 + 动态切换）
│   │   ├── deps.py                   #   依赖注入容器 + DB 会话管理
│   │   ├── uploads.py                #   上传文件存储（file_id 元数据与读取）
│   │   └── observability.py          #   Logfire 全链路追踪配置
│   │
│   ├── agents/                       # 🤖 Agent 层
│   │   ├── code_reviewer.py          #   代码审查 Agent（结构化输出 CodeReviewOutput）
│   │   ├── data_analyst.py           #   数据分析 Agent（SQL 工具链 + 图表生成）
│   │   ├── qa_assistant.py           #   知识问答 Agent（KB / Web / Skills / 天气）
│   │   ├── registry.py               #   Agent 注册表（AgentName + list_agents）
│   │   ├── runner.py                 #   统一 Agent 执行入口 run_agent()
│   │   └── input_files.py            #   附件预处理（file_id 注入 prompt）
│   │
│   ├── tools/                        # 🔧 工具层
│   │   ├── file_tools.py             #   文件读写 / Shell 执行 / Web 请求
│   │   ├── db_tools.py               #   SQL 查询 / 表结构探索（只读安全）
│   │   └── kb_tools.py               #   知识库搜索 / 网络搜索
│   │
│   ├── graphs/                       # 🔀 图编排层
│   │   ├── agent_router.py           #   agent-router 工作流图（意图路由 → Agent）
│   │   ├── registry.py               #   Workflow 注册表（WorkflowName + list_workflows）
│   │   └── runner.py                 #   统一 Workflow 执行入口 run_workflow()
│   │
│   ├── skills/                       # 📦 Skill 动态加载层
│   │   ├── manager.py                #   SkillPackageManager（ZIP 上传/安全扫描/安装/卸载）
│   │   ├── integration.py            #   pydantic-ai-skills 集成（SkillsCapability/Toolset）
│   │   ├── routes.py                 #   Skill 管理 API（上传/列表/卸载）
│   │   ├── code-review/              #   示例 Skill（脚本 + 资源）
│   │   ├── weather/                  #   天气 Skill（scripts/forecast.py）
│   │   ├── image-forgery-detector/   #   图像伪造检测 Skill
│   │   └── _manifest.json            #   已安装 Skill 清单（上传时写入）
│   │
│   ├── api/                          # 🌐 API 层
│   │   └── routes.py                 #   REST API（Agent / Workflow 统一端点）
│   │
│   ├── ui/                           # 🖥 Web 控制台
│   │   └── gradio_app.py             #   Gradio 管理界面（Chat / Agent / Workflow / Skills）
│   │
│   └── models/                       # 📋 数据模型层
│       ├── schemas.py                #   Pydantic Schema（Agent/Workflow 契约 + 结构化输出）
│       └── schema.py                 #   SQLAlchemy ORM 模型
│
├── tests/                            # 🧪 测试
│   ├── conftest.py                   #   pytest 全局 fixtures
│   ├── test_code_reviewer.py         #   代码审查 Agent 测试
│   ├── test_runner.py                #   run_agent 统一执行层测试
│   ├── test_workflow.py              #   图工作流路由测试
│   ├── test_workflow_runner.py       #   run_workflow 执行层测试
│   ├── test_input_files.py           #   附件预处理测试
│   ├── test_weather_forecast.py      #   天气 Skill 脚本测试
│   ├── test_llm_manager.py           #   LLM 管理器测试
│   ├── test_skill_manager.py         #   Skill 管理器测试
│   ├── test_uploads.py               #   上传存储测试
│   └── test_gradio_uploads.py        #   Gradio 上传集成测试
│
├── docker/                           # 🐳 部署
│   ├── Dockerfile                    #   多阶段构建（builder → production）
│   └── docker-compose.yml            #   编排（含可选 Ollama）
│
├── mcp_servers/                      # 🔌 MCP 服务器
│   └── fetch_server.py               #   Fetch MCP Server（SSE 模式）
│
└── scripts/
    └── start.py                      # 快速启动脚本
```

---

## 四层架构

```
┌──────────────────────────────────────────────────────┐
│              API 层 (FastAPI) + Gradio UI (/ui)        │
│  /api/v1/agents/*  /api/v1/skills/*  /health          │
│  统一请求校验 · success/error 信封 · 成本追踪            │
├──────────────────────────────────────────────────────┤
│           执行层 (runner.py)                           │
│  run_agent() · run_workflow() · input_files 预处理     │
├──────────────────────────────────────────────────────┤
│                  Agent 层 (Pydantic AI)                │
│  CodeReviewer · DataAnalyst · QaAssistant             │
│  结构化输出 · 依赖注入 · Skill 能力注入                 │
├──────────────────────────────────────────────────────┤
│            工具 + 图编排 层                             │
│  FileTools · DBTools · KBTools                        │
│  SkillsToolset (渐进式加载) · pydantic-graph (工作流)   │
├──────────────────────────────────────────────────────┤
│                基础设施层                               │
│  LlmManager (8模型路由) · Config (pydantic-settings)   │
│  Logfire (全链路追踪) · SQLAlchemy (持久化)             │
│  UploadStore (附件) · SecurityScanner · SkillManager   │
└──────────────────────────────────────────────────────┘
```

---

## 快速开始

### 1. 环境准备

```bash
# Python >= 3.11
python --version

# 克隆项目
cd pydantic-ai-agent
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入各 Provider 的 API Key 与 Base URL（见 `.env.example`）：

```bash
DEEPSEEK_API_KEY=sk-your-key-here

LONGCAT_API_KEY=ak-xxx
LONGCAT_BASE_URL=https://api.longcat.chat/openai

AGNESAI_API_KEY=sk-xxx
AGNESAI_BASE_URL=https://apihub.agnes-ai.com/v1

SENSENOVA_API_KEY=sk-xxx
SENSENOVA_BASE_URL=https://token.sensenova.cn/v1
```

### 3. 安装依赖

```bash
# 推荐：使用 uv（更快、更强依赖解析）
pip install uv
uv pip install -e ".[dev]"

# 或传统方式
pip install -e ".[dev]"
pip install -e .
```

### 4. 启动服务

```bash
# 方式一：快速启动脚本
python scripts/start.py

# 方式二：直接 uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 方式三：Python 直接运行
python -m app.main
```

启动成功后访问：
- **Gradio 控制台**：http://localhost:8000/ui/（根路径 `/` 自动重定向至此）
- **API 文档（Swagger）**：http://localhost:8000/docs
- **健康检查**：http://localhost:8000/health

---

## Gradio Web 控制台

服务启动后访问 http://localhost:8000/ui/，提供五个 Tab：

| Tab | 功能 |
|-----|------|
| **Chat** | 与 Agent 多轮对话，支持附件上传、模型切换、会话导出 |
| **Agent** | 查看已注册 Agent 列表，单次测试调用 |
| **Workflow** | 查看已注册 Workflow 列表，测试意图路由工作流 |
| **Model** | 模型注册表、API Key 状态、累计调用成本 |
| **Skills** | 上传/卸载 Skill ZIP，查看已安装列表 |

> Gradio 与 REST API **共用同一进程**，直接调用 `run_agent()` / `run_workflow()` / `list_agents()` 等 Python 函数，**不经过** HTTP `/api/v1/...` 接口。

## API 接口文档

所有 Agent / Workflow 接口统一挂载在 `/api/v1` 前缀下（见 `app/main.py`）。

### Agent / Workflow 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/agents/` | 列出所有可用 Agent 与 Workflow |
| `POST` | `/api/v1/agents/{name}/agent` | 运行指定 Agent（统一端点） |
| `POST` | `/api/v1/agents/{workflow_name}/workflow` | 运行指定 Workflow |
| `GET` | `/api/v1/agents/costs` | 成本追踪报告 |

**Agent 名称**（`{name}`）：`code-reviewer` | `data-analyst` | `qa-assistant`

**Workflow 名称**（`{workflow_name}`）：`agent-router`

### 请求 / 响应契约

**`AgentRunRequest`**（`POST .../agent` 请求体）：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user_input` | `str` | — | 传给 Agent 的用户输入 |
| `tenant_id` | `str` | `tenant01` | 租户 ID |
| `user_id` | `str` | `user01` | 用户 ID |
| `session_id` | `str` | `session01` | 会话 ID |
| `model_alias` | `str \| null` | `null` | 可选模型别名 |
| `file_ids` | `list[str]` | `[]` | 已上传文件 ID 列表 |

**`AgentRunResult`**（响应信封）：`status` 为 `success` 或 `error`；成功时 `output` 为各 Agent 的结构化输出，失败时 `error` 含错误信息；另含 `usage`、`cost_usd`、`elapsed_seconds`。

**`WorkflowRunRequest`**：`user_input`、`tenant_id`、`user_id`、`session_id`、`file_ids`（字段含义同上）。

**`WorkflowRunResult`**：`state` 含 `qa_result` / `review_result` / `analysis_result` 等分支结果摘要。

### Skill 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/skills/upload` | 上传 Skill ZIP 包 |
| `GET` | `/api/v1/skills/list` | 列出已安装 Skill |
| `DELETE` | `/api/v1/skills/uninstall` | 卸载 Skill |
| `GET` | `/api/v1/skills/directory` | 获取 skills 目录路径 |

### 调用示例

```bash
# 列出可用 Agent 与 Workflow
curl http://localhost:8000/api/v1/agents/

# 代码审查（统一 Agent 端点）
curl -X POST http://localhost:8000/api/v1/agents/code-reviewer/agent \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "请审查以下 Python 代码：\ndef add(a, b): return a+b\n\ndef div(a, b): return a/b",
    "session_id": "session01"
  }'

# 数据分析
curl -X POST http://localhost:8000/api/v1/agents/data-analyst/agent \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "统计每个部门的平均薪资",
    "session_id": "session01"
  }'

# 知识问答
curl -X POST http://localhost:8000/api/v1/agents/qa-assistant/agent \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "什么是 RAG 技术？它和微调有什么区别？",
    "session_id": "session01"
  }'

# 意图路由工作流（自动选择 Agent）
curl -X POST http://localhost:8000/api/v1/agents/agent-router/workflow \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "帮我审查这段 Python 代码有没有 bug",
    "session_id": "session01"
  }'

# 成本报告
curl http://localhost:8000/api/v1/agents/costs
```

### 指定模型

在请求体的 `model_alias` 字段中指定模型别名（非法别名返回 `status: "error"`，不抛 HTTP 异常）：

```bash
# 使用 deepseek-reasoner
curl -X POST http://localhost:8000/api/v1/agents/qa-assistant/agent \
  -H "Content-Type: application/json" \
  -d '{
    "user_input": "什么是微服务？",
    "model_alias": "deepseek-reasoner"
  }'
```

可选模型别名：`deepseek-chat` | `deepseek-reasoner` | `longcat-2.0-preview` | `agnes-2.0-flash` | `sensenova-6.7-flash-lite` | `sensenova-u1-fast`

---

## LLM 管理器

`app/core/llm.py` 提供统一的模型路由和成本追踪。

### 预注册模型

| 别名 | Provider | 模型 | 输入价格 ($/1M tokens) | 输出价格 | 能力 |
|------|----------|------|----------------------|---------|------|
| `deepseek-chat` | DeepSeek | deepseek-chat | $0.27 | $1.10 | 文本 |
| `deepseek-reasoner` | DeepSeek | deepseek-reasoner | $0.55 | $2.19 | 推理 |
| `longcat-2.0-preview` | LongCat (OpenAI 兼容) | LongCat-2.0-Preview | — | — | 文本 |
| `agnes-2.0-flash` | Agnes AI (OpenAI 兼容) | agnes-2.0-flash | — | — | 文本 |
| `sensenova-6.7-flash-lite` | 商汤 (OpenAI 兼容) | sensenova-6.7-flash-lite | — | — | 文本 + 图片理解 |
| `sensenova-u1-fast` | 商汤 (OpenAI 兼容) | sensenova-u1-fast | — | — | 文生图 |

### 使用方式

```python
from app.core.llm import get_llm_manager, ModelAlias

llm = get_llm_manager()

# 解析模型字符串
model_str = llm.resolve_model_string("deepseek-chat")
# → "deepseek:deepseek-chat"

# 追踪成本
cost = llm.track_cost("deepseek-chat", input_tokens=1000, output_tokens=500)

# 获取成本报告
report = llm.get_cost_report()
# → {"deepseek-chat": 0.000825, "deepseek-reasoner": 0.0012, ...}
```

### 添加自定义模型

在 `app/core/llm.py` 的 `MODEL_REGISTRY` 字典中添加：

```python
ModelAlias = Literal[
    # ... 现有别名
    "my-custom-model",   # 新增
]

MODEL_REGISTRY: dict[ModelAlias, ModelConfig] = {
    # ... 现有配置
    "my-custom-model": ModelConfig(
        alias="my-custom-model",
        provider="deepseek",                    # pydantic-ai 支持的 provider
        model_id="my-finetuned-v2",
        base_url="https://api.my-company.com/v1",  # 自定义端点
        api_key_env="MY_COMPANY_API_KEY",
        cost_per_1m_input=0.5,
        cost_per_1m_output=1.5,
    ),
}
```

---

## Skill 动态加载系统

### 架构

Skill 系统分为两层协作：

| 层 | 实现 | 职责 |
|----|------|------|
| **ZIP 上传管理层** | `SkillPackageManager` | 上传 → 安全扫描 → 解压 → 校验 SKILL.md → 安装到 skills/ 目录 |
| **Skill 动态加载层** | `pydantic-ai-skills` | 扫描 skills/ 目录 → 渐进式注入 → Agent 按需加载 → 执行脚本 |

### 渐进式加载流程

```
1. Agent 启动 → SkillsToolset 扫描 skills/ 目录
2. 只将 name + description 注入系统提示（≈1KB/Skill，最小 Token 开销）
3. Agent 判断当前任务需要某 Skill → 调用 load_skill(name) 加载完整指令
4. Agent 按指令执行 → 可调用 run_skill_script() 运行脚本
5. Agent 可调用 read_skill_resource() 查阅参考文档
```

### ZIP 包规范

```
my-skill.zip
└── my-skill/                 # 目录名须与 skill name 一致
    ├── SKILL.md              # 必需 — YAML frontmatter + Markdown 指令
    ├── scripts/              # 可选 — Python/Shell 可执行脚本
    │   └── analyze.py
    └── resources/            # 可选 — 参考文档/数据文件
        └── reference.md
```

### SKILL.md 格式

```markdown
---
name: my-skill                # 必需，小写+连字符，1-64 字符
description: >                # 必需，最长 1024 字符，决定 Agent 何时触发
  当用户需要做 XX 时使用此技能。
  此描述是 Agent 判断是否加载该技能的唯一依据。
version: 1.0.0                # 可选
author: your-name             # 可选
category: development         # 可选
tags: [code, review]          # 可选
---

# My Skill Title

## When to Use
- 场景 A
- 场景 B

## Instructions
1. 步骤一
2. 步骤二

## Scripts
执行分析脚本：
`python3 {baseDir}/scripts/analyze.py "{input}"`

## Output Format
返回 JSON 格式结果。
```

**关键**：`description` 是 Agent 判断是否加载该 Skill 的唯一依据，务必写得具体明确。

### 上传与卸载

```bash
# 上传 Skill
curl -X POST http://localhost:8000/api/v1/skills/upload \
  -F "file=@my-skill.zip" \
  -Q "uploaded_by=alice"

# 列出已安装
curl http://localhost:8000/api/v1/skills/list

# 卸载
curl -X DELETE http://localhost:8000/api/v1/skills/uninstall \
  -H "Content-Type: application/json" \
  -d '{"skill_name": "my-skill"}'
```

上传后 **无需重启服务**，`SkillsToolset` 每次运行都会重新扫描 skills/ 目录。

> **注意**：`_manifest.json` 中的 `has_scripts` / `has_resources` 在上传安装时写入。若之后手动向 Skill 目录添加 `scripts/`，列表可能仍显示 `-`，需重新上传或更新 manifest。

### 安全防护

| 防护层 | 检测内容 |
|--------|---------|
| ZIP 内容扫描 | 路径遍历（`../`）、绝对路径、危险扩展名（`.exe/.bat/.dll`等） |
| ZIP 炸弹检测 | 压缩比 > 100x 自动告警 |
| 脚本内容扫描 | `eval()`、`exec()`、`os.system()`、`rm -rf` 等危险模式 |
| 大小限制 | 单文件 50MB、总包 100MB 上限 |
| 路径验证 | 卸载时二次校验 `resolve()` 路径，防路径穿越 |

### Agent 集成 Skill 的三种方式

```python
# 方式一：SkillsCapability（推荐，最简洁）
from app.skills import create_skills_capability

agent = Agent(
    model='deepseek:deepseek-chat',
    instructions='You are a helpful assistant.',
    capabilities=[create_skills_capability('./skills')],
)

# 方式二：SkillsToolset（更底层控制）
from app.skills import create_skills_toolset

agent = Agent(
    model='deepseek:deepseek-chat',
    toolsets=[create_skills_toolset('./skills')],
)

# 方式三：便捷函数（一步到位）
from app.skills import create_skill_aware_agent

agent = create_skill_aware_agent(
    model='deepseek:deepseek-chat',
    instructions='You are a coding assistant.',
    skills_dir='./skills',
)

result = await agent.run('帮我审查这段代码')
```

---

## 图编排工作流

`app/graphs/agent_router.py` 使用 `pydantic-graph` 定义 **agent-router** 工作流，节点内部统一调用 `run_agent()`：

```
用户输入
   │
   ▼
┌─────────────┐
│  RouterNode  │  classify_route() 关键词意图识别
└──────┬──────┘
       │
       ├── 数据/统计/SQL/分析 ──→ AnalyzeNode (data-analyst) ──→ End
       │
       ├── 审查/review/bug ──→ ReviewNode (code-reviewer) ──→ End
       │
       └── 问答/天气/Skill/图像检测等 ──→ QaNode (qa-assistant) ──→ End
```

注册与执行：

| 模块 | 职责 |
|------|------|
| `app/graphs/registry.py` | `WorkflowName` 枚举 + `list_workflows()` |
| `app/graphs/runner.py` | `run_workflow()` 统一执行 + `WorkflowRunResult` 封装 |
| `app/api/routes.py` | `POST /api/v1/agents/agent-router/workflow` |

当前路由逻辑基于关键词匹配（适合快速验证），生产环境可替换为 LLM 意图分类。

## 三个预构建 Agent

所有 Agent 通过统一入口 `run_agent(AgentName, AgentRunRequest)` 执行（`app/agents/runner.py`），API 层与 Gradio 均调用此函数。

### CodeReviewer — 代码审查

| 配置 | 值 |
|------|---|
| 名称 | `code-reviewer` |
| 输入 | `user_input`（自然语言 + 可选代码/附件，由 `input_files.py` 预处理） |
| 输出 | `CodeReviewOutput`（summary, issues[], quality_score, approved） |
| 工具 | `read_file`, `run_shell`, 上传文件读取 |
| 模型 | 默认 `deepseek-chat` |

```python
from app.agents import run_agent
from app.agents.registry import AgentName
from app.models.schemas import AgentRunRequest

result = await run_agent(
    AgentName.code_reviewer,
    AgentRunRequest(user_input="Review: def div(a, b): return a/b"),
)
if result.is_success:
    print(result.output["quality_score"])
```

### DataAnalyst — 数据分析

| 配置 | 值 |
|------|---|
| 名称 | `data-analyst` |
| 输入 | `user_input`（自然语言分析需求 + 可选附件） |
| 输出 | `DataAnalysisOutput`（analysis, charts[], sql_query, recommendations） |
| 工具 | `execute_query`, `list_tables`, `describe_table` |
| 模型 | 默认 `deepseek-chat` |

### QaAssistant — 知识问答

| 配置 | 值 |
|------|---|
| 名称 | `qa-assistant` |
| 输入 | `user_input`（自然语言问题） |
| 输出 | `QaOutput`（answer, confidence, sources[], follow_ups[]） |
| 工具 | `search_knowledge_base`, `web_search`, `get_weather_forecast`, Skills 工具集 |
| 模型 | 默认 `deepseek-chat` |

> `schemas.py` 中仍保留 `CodeReviewInput`、`DataAnalysisInput`、`QaInput` 等类型，供 Agent 的 `output_type` 与文档参考；**API 统一使用 `AgentRunRequest.user_input`** 传递输入。

## 依赖注入

所有 Agent 共享 `AgentDeps` 依赖容器，通过 `RunContext` 在工具函数中访问：

```python
from app.core.deps import AgentDeps
from pydantic_ai import RunContext

@agent.tool
async def my_tool(ctx: RunContext[AgentDeps], query: str) -> str:
    # 访问租户信息
    tenant_id = ctx.deps.tenant_id
    # 访问数据库
    db = ctx.deps.db_session
    # 访问请求 ID
    request_id = ctx.deps.request_id
    ...
```

运行时注入（通过 `run_agent` 自动构造 `AgentDeps`）：

```python
from app.agents import run_agent
from app.agents.registry import AgentName
from app.models.schemas import AgentRunRequest

result = await run_agent(
    AgentName.qa_assistant,
    AgentRunRequest(
        user_input="帮我分析数据",
        tenant_id="tenant01",
        user_id="user01",
        session_id="session01",
    ),
)
```

---

## 可观测性

项目集成 Logfire，自动追踪以下组件：

- **FastAPI** — 请求/响应耗时、状态码
- **httpx** — 外部 HTTP 调用链路
- **Pydantic AI** — Agent 每步推理、工具调用、Token 消耗

配置方式：

```bash
# .env 中添加 Logfire Token
LOGFIRE_TOKEN=your-logfire-token
```

不配置 Logfire Token 时，追踪数据输出到标准日志，不影响运行。

---

## 测试

```bash
# 运行全部测试
pytest

# 带覆盖率
pytest --cov=app --cov-report=html

# 只运行特定模块
pytest tests/test_runner.py
pytest tests/test_workflow_runner.py
pytest tests/test_code_reviewer.py
pytest tests/test_skill_manager.py
pytest tests/test_weather_forecast.py
```

测试使用 Model `test`（Pydantic AI 内置的 mock 模型），无需真实 API Key。

---

## Docker 部署

### 构建与启动

```bash
cd docker

# 标准启动
docker-compose up -d

# 含 Ollama 本地模型
docker-compose --profile local-llm up -d
```

### 环境变量

在 `.env` 文件中配置（Docker Compose 自动读取）：

```bash
APP_ENV=production
DEFAULT_MODEL=deepseek:deepseek-chat
DEEPSEEK_API_KEY=sk-your-key
DATABASE_URL=sqlite+aiosqlite:///./data/agent.db
```

### 多阶段构建说明

```
Stage 1 (builder):  pip install → pip freeze → requirements-lock.txt
Stage 2 (production): 只安装 lock 文件中的依赖 → 复制代码 → 非 root 运行
```

确保生产环境的依赖版本与开发环境完全一致。

---

## 扩展指南

### 添加新 Agent

1. 在 `app/models/schemas.py` 中定义输入/输出 Schema：

```python
class MyAgentInput(BaseModel):
    query: str = Field(description="用户查询")

class MyAgentOutput(BaseModel):
    result: str = Field(description="处理结果")
    confidence: float = Field(ge=0, le=1)
```

2. 在 `app/agents/` 中创建 Agent 文件：

```python
# app/agents/my_agent.py
from pydantic_ai import Agent, RunContext
from app.core.deps import AgentDeps
from app.models.schemas import MyAgentOutput

my_agent = Agent(
    model="deepseek:deepseek-chat",
    deps_type=AgentDeps,
    output_type=MyAgentOutput,
    instructions="You are a specialized assistant for ...",
)

@my_agent.tool
async def my_tool(ctx: RunContext[AgentDeps], param: str) -> str:
    return f"processed: {param}"
```

3. 在 `app/agents/registry.py` 中注册：

```python
from app.agents.my_agent import my_agent

class AgentName(str, Enum):
    # ... 现有
    my_agent = "my-agent"

AGENTS[AgentName.my_agent] = my_agent
```

4. 无需新增 API 端点 — `POST /api/v1/agents/my-agent/agent` 自动可用

5. 在 `tests/` 中添加测试

### 添加新 Workflow

1. 在 `app/graphs/` 中定义图（参考 `agent_router.py`）
2. 在 `app/graphs/registry.py` 的 `WorkflowName` 和 `WORKFLOWS` 中注册
3. `POST /api/v1/agents/{workflow_name}/workflow` 自动可用

### 添加新 Skill

1. 创建 Skill 目录：

```bash
mkdir -p app/skills/my-skill/{scripts,resources}
```

2. 编写 `SKILL.md`（参见 [SKILL.md 格式](#skillmd-格式)）

3. 可选：添加 `scripts/` 和 `resources/`

4. 或打包为 ZIP 上传：

```bash
cd app/skills
zip -r my-skill.zip my-skill/
curl -X POST http://localhost:8000/api/v1/skills/upload \
  -F "file=@my-skill.zip"
```

### 添加新 LLM 模型

在 `app/core/llm.py` 的 `ModelAlias` 和 `MODEL_REGISTRY` 中添加条目即可。参见 [LLM 管理器](#llm-管理器) 章节。

---

## 配置参考

所有配置通过 `.env` 文件或环境变量管理，由 `pydantic-settings` 自动加载：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `APP_ENV` | `development` | 运行环境：development / staging / production |
| `APP_SECRET_KEY` | `change-me-in-production` | 应用密钥（生产环境务必修改） |
| `DEFAULT_MODEL` | `deepseek:deepseek-chat` | 默认 LLM 模型 |
| `DEEPSEEK_API_KEY` | — | DeepSeek API Key |
| `LONGCAT_API_KEY` | — | LongCat API Key |
| `LONGCAT_BASE_URL` | `https://api.longcat.chat/openai` | LongCat OpenAI 兼容 Base URL |
| `AGNESAI_API_KEY` | — | Agnes AI API Key |
| `AGNESAI_BASE_URL` | `https://apihub.agnes-ai.com/v1` | Agnes AI Base URL |
| `SENSENOVA_API_KEY` | — | 商汤 SenseNova API Key |
| `SENSENOVA_BASE_URL` | `https://token.sensenova.cn/v1` | 商汤 SenseNova Base URL |
| `LOGFIRE_TOKEN` | — | Logfire 可观测性 Token |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/agent.db` | 数据库连接字符串 |
| `MCP_FETCH_URL` | — | MCP Fetch 服务器 SSE 地址 |

---

## 与其他框架的对比

| 维度 | 本项目 (Pydantic AI) | LangGraph | Pi Agent |
|------|---------------------|-----------|----------|
| 依赖复杂度 | **低**（2-3 个核心包） | 高（7+ 个微包，版本互斥频发） | 低（TypeScript 单体） |
| 类型安全 | **强**（Pydantic V2 全链路） | 中（TypedDict，无验证） | 中 |
| 结构化输出 | **原生**（output_type 自动验证+重试） | 需自建 | 需自建 |
| 图编排 | 中（pydantic-graph 类型化状态机） | **强**（DAG + 条件分支） | 无 |
| Skill 动态加载 | **有**（pydantic-ai-skills + ZIP 管理） | 无 | 有（原生 SKILL.md） |
| 可观测性 | **Logfire 原生** | LangSmith | 事件流 |
| 多模型路由 | **6 模型预注册**（DeepSeek / LongCat / Agnes AI / 商汤） | 需自建 | 20+ 原生支持 |
| 学习曲线 | **低** | 高 | 低 |
| 语言 | Python | Python | TypeScript |

---

## 常见问题

### Q: 访问 `/agents/` 返回 404？

Agent API 统一挂载在 `/api/v1` 前缀下，请使用：

```
http://localhost:8000/api/v1/agents/
```

### Q: 启动时报 `ModuleNotFoundError: No module named 'pydantic_ai'`

确保安装了项目依赖：

```bash
pip install -e ".[dev]"
```

### Q: 如何不花钱测试？

测试使用 Pydantic AI 内置的 `test` 模型，无需任何 API Key：

```python
agent = Agent('test', output_type=MyOutput)
result = agent.run_sync('test input')  # 不调用真实 LLM
```

### Q: 上传 Skill 后 Agent 没识别到？

`SkillsToolset` 每次运行重新扫描 skills/ 目录。如果 Agent 已在运行中，下一次调用时新 Skill 自动生效。

### Q: 如何在生产环境中保证 Skill 安全？

1. 设置 `allow_warnings=False` 拒绝所有带安全警告的包
2. 在 API Gateway 层添加上传者身份认证
3. 定期审查 `_manifest.json` 中的已安装 Skill

### Q: 多租户如何实现？

在 `AgentDeps` 中传入 `tenant_id`，工具函数中根据 `ctx.deps.tenant_id` 做数据隔离。数据库层可通过行级安全策略（RLS）实现。

---

## 关键文件导航

| 文件 | 说明 |
|------|------|
| `app/main.py` | 程序入口，挂载 `/api/v1` 路由与 `/ui` Gradio |
| `app/core/config.py` | 配置读取 |
| `app/agents/registry.py` | Agent 注册表 |
| `app/agents/runner.py` | 统一 Agent 执行 `run_agent()` |
| `app/api/routes.py` | REST API 端点 |
| `app/graphs/agent_router.py` | agent-router 工作流图 |
| `app/graphs/runner.py` | 统一 Workflow 执行 `run_workflow()` |
| `app/ui/gradio_app.py` | Gradio Web 控制台 |

---

## License

MIT
