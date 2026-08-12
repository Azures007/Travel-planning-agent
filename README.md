# Travel-planning-agent

AI 驱动的旅游计划 Agent：用户用自然语言描述目的地、天数、预算和偏好，Agent 生成结构化的逐日行程计划，并通过对话式追问补齐缺失信息，支持迭代修改。

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | React + Vite + TypeScript + Tailwind CSS |
| 后端 | Python + FastAPI（SSE 流式对话） |
| Agent 编排 | **LangGraph 状态机**（collect → ask_user → generate → validate） |
| LLM | 阿里百炼 DashScope（OpenAI 兼容接口，qwen-plus） |
| 状态持久化 | LangGraph Checkpointer（AsyncPostgresSaver） |
| 数据库 | PostgreSQL 16（Docker Compose） |
| ORM | SQLAlchemy 2.x (async) |
| 实时数据 | 高德 + 和风天气适配器（Key 留空自动降级 Mock） |

## 项目结构

```
backend/            # FastAPI 后端
├── app/
│   ├── agent/      # LangGraph 图 + 节点 + 校验器 + checkpointer
│   │   ├── graph.py       # TravelState + build_graph + 条件路由
│   │   ├── nodes.py       # collect / ask_user / generate / validate
│   │   ├── runner.py      # 图编排 + SSE 事件 + 消息同步
│   │   ├── llm.py         # AsyncOpenAI 封装（流式 + 工具调用）
│   │   ├── validation.py  # 行程合理性校验器
│   │   ├── checkpointer.py # Postgres checkpointer 单例
│   │   ├── prompts.py     # 节点系统提示词
│   │   └── tools.py       # 工具定义
│   ├── api/        # sessions.py + chat.py（SSE）
│   ├── db/         # SQLAlchemy models
│   ├── tools/      # registry（选择+降级）+ gaode + qweather + mock
│   ├── config.py   # 环境配置
│   ├── schemas.py  # Pydantic 行程 schema
│   ├── main.py
│   └── run.py      # 启动入口（Windows 事件循环策略）
├── docker-compose.yml   # postgres:16（宿主机端口 5433）
frontend/           # React SPA
├── src/
│   ├── components/ # ChatPanel（含等待回答横幅）+ Timeline + SessionSidebar
│   └── lib/        # api.ts（SSE 客户端）+ types.ts
```

## 快速启动

### 1. 启动数据库

```bash
cd backend
docker compose up -d
```

### 2. 启动后端

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
# 配置 .env（参照 .env.example：DASHSCOPE_API_KEY 等）
.venv/Scripts/python run.py   # http://127.0.0.1:8000
```

> Windows 注意：必须用 `run.py` 启动（内部设置 Selector 事件循环，psycopg async 必需），不要直接 `uvicorn app.main:app`。

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

## Agent 工作流（LangGraph）

```
START → collect ──(数据工具自环)────────────────┐
            ├(需求不齐/模型追问)→ ask_user ───────┤(interrupt，前端展示等待)
            └(需求齐)→ generate → validate ─(ok)→ END
                               ├(fail, retries<2)→ generate  # 校验失败重新生成
                               └(fail, retries>=2)→ END       # 尽力而为带警告
```

- **collect**：LLM 调用数据工具（POI/天气/交通），抽取需求
- **ask_user**：`interrupt` 暂停等用户回答，状态经 Postgres checkpointer 持久化（刷新页面/断线可恢复）
- **generate**：强制调用 `output_itinerary` 输出结构化行程（Pydantic 校验）
- **validate**：业务校验（天数编号/活动数/花费非负/时间顺序/预算一致/地理相邻），失败自动重生成

## SSE 事件协议

| 事件 | 说明 |
|---|---|
| `agent_message` | LLM 文本增量（流式） |
| `tool_result` | 工具调用结果 |
| `itinerary` | 完整行程（结构化 JSON） |
| `question` | Agent 追问（interrupt，前端展示「等你回答」） |
| `validation_report` | 校验警告（协议先行，UI 未渲染） |
| `error` / `done` | 错误 / 完成 |

## 实时数据 API

- `AMAP_KEY`：高德开放平台（POI 搜索 + 路径规划）
- `QWEATHER_KEY`：和风天气（逐日预报）
- 任一 Key 留空或调用失败 → 自动降级 Mock（结果带 `_degraded` 标记）
- `FORCE_MOCK_TOOLS=true`：开发期整体关闭真实 API

## 开发阶段

- **P1（已完成）**：最小闭环 — 手写工具循环 → 结构化行程生成 → 时间线渲染 → 迭代修改
- **P2（已完成）**：LangGraph 状态机 + interrupt 追问 + 合理性校验器 + 真实 API 适配层
- **P3（计划）**：JWT 账号 + 历史计划保存/导出
- **P4（计划）**：合理性校验增强、多方案对比
