# Travel-planning-agent

AI 驱动的旅游计划 Agent：用户用自然语言描述目的地、天数、预算和偏好，Agent 生成结构化的逐日行程计划，并支持对话式迭代修改。

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | React + Vite + TypeScript + Tailwind CSS |
| 后端 | Python + FastAPI（SSE 流式对话） |
| Agent | 阿里百炼 DashScope（OpenAI 兼容接口，qwen-plus）+ 工具调用循环 |
| 数据库 | PostgreSQL 16（Docker Compose） |
| ORM | SQLAlchemy 2.x (async) |
| 实时数据 | P1 使用 Mock；P2 计划接入高德 + 和风天气 |

## 项目结构

```
backend/            # FastAPI 后端
├── app/
│   ├── agent/      # runner.py（agent 循环）+ tools.py（工具注册表）
│   ├── api/        # sessions.py + chat.py（SSE）
│   ├── db/         # SQLAlchemy models
│   ├── tools/      # mock_tools.py（POI/天气/交通 Mock）
│   ├── config.py   # 环境配置
│   ├── schemas.py  # Pydantic 行程 schema
│   └── main.py
├── docker-compose.yml   # postgres:16（宿主机端口 5433）
frontend/           # React SPA
├── src/
│   ├── components/ # ChatPanel + Timeline + SessionSidebar
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
.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

## API

- `POST /api/sessions` — 创建会话
- `GET /api/sessions` — 会话列表
- `GET /api/sessions/{id}` — 会话详情（含消息与最新行程）
- `POST /api/chat` — 发送消息（SSE 流式返回 agent 事件）

## 开发阶段

- **P1（已完成）**：最小闭环 — 对话式需求收集 → Mock 数据工具 → 结构化行程生成 → 时间线渲染 → 迭代修改
- **P2（进行中）**：评估 LangGraph 接入 + 高德/和风真实 API
- **P3**：JWT 账号 + 历史计划保存/导出
- **P4**：合理性校验增强、多方案对比
