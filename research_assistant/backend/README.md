# AI 投研助手 Backend

这是一个基于 FastAPI 的本地多 Agent 投研助手。系统可使用 Yahoo Finance 公开数据覆盖 A 股、港股和美股，并通过千问生成通俗分析；离线测试继续使用确定性 Mock 数据。

> 本项目仅用于产品演示和技术交流，输出不构成投资建议。

## 功能

- Query Router、Stock Entity Resolver 与五个相互独立的专项 Agent 模块
- 通用证券实体解析：支持公司简称、全称、A/港/美股代码、本地主表、远程搜索、SQLite 缓存和同名歧义提示
- 每个 Agent 都有 Pydantic 输入、输出 Schema
- yfinance 真实数据 Provider 与可回退的 Mock Provider
- 千问解释层：大模型不允许改写事实、指标和来源，异常时自动降级
- SQLite 本地研究历史
- 统一工作流编排和逐 Agent 执行记录
- 按 Query Router 主任务与用户提示词动态生成 `visible_modules`，让六类任务生成和展示不同的报告模块
- 创建、查询和列出投研任务的 REST API
- 股票搜索和健康检查接口
- 自动生成引用、风险审核结果与免责声明
- 报告严格拆分为已确认事实、AI 分析、未来情景和主要不确定性
- 新闻过滤返回候选、去重、低相关、低可信、过期和最终保留统计
- 风险审核返回证据覆盖率和逐项检查结果，不使用投资判断置信度
- 输出面向普通投资者的公司画像、关注问题和 Future Watch
- 为 PE、ROE、营收增长率、净利润增长率提供通俗解释
- 保留新闻额外说明事件值得关注的经营原因
- 返回上下文相关的学习型后续问题
- OpenAPI 文档和 CORS 配置

## 目录说明

```text
backend/
├── app/
│   ├── agents/             # Query Router + Stock Resolver + 五个专项 Agent
│   ├── api/                # FastAPI 路由和依赖
│   ├── core/               # 配置与领域异常
│   ├── mock_data/          # Mock 股票和新闻 JSON
│   ├── llm/                # 千问客户端和解释层约束
│   ├── orchestration/      # Agent 工作流与执行审计
│   ├── providers/          # 可替换的数据 Provider 接口
│   ├── repositories/       # SQLite / 内存任务仓库
│   ├── schemas/            # Agent 与 API 的 Pydantic Schema
│   ├── services/           # 任务服务和内存存储
│   └── main.py             # FastAPI 应用入口
├── tests/                  # Agent 与 API 测试
├── .env.example
├── Dockerfile
└── pyproject.toml
```

## Agent 流程

```text
用户问题
  → QueryRouterAgent
  → StockEntityResolverAgent
  → QuestionUnderstandingAgent
  → DataRetrievalAgent
  → NewsFilterAgent
  → AnalysisAgent
  → RiskReviewAgent
  → 结构化投研结果
```

每个 Agent 继承 `BaseAgent[InputSchema, OutputSchema]`，只通过结构化对象交互。数据访问通过 `FinancialDataProvider` 抽象；真实与 Mock Provider 使用同一接口。千问只增强 Analysis Agent 的解释字段，Risk Review Agent 仍作为最后一道独立审核。

## 本地运行

需要 Python 3.10 或更高版本。

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY
uvicorn app.main:app --reload
```

启动后访问：

- Swagger UI：<http://localhost:8000/docs>
- OpenAPI JSON：<http://localhost:8000/openapi.json>
- 健康检查：<http://localhost:8000/api/v1/health>

## API

### 创建投研任务

```bash
curl -X POST http://localhost:8000/api/v1/research \
  -H 'Content-Type: application/json' \
  -d '{"query":"请分析贵州茅台的基本面、近期新闻和风险"}'
```

Demo 当前同步执行工作流，并以 `201 Created` 返回已完成的任务。无法识别股票时也会创建一个可审计的失败任务，响应中的 `status` 为 `failed`，`agent_runs` 会标记失败步骤。

### 查询任务

```bash
curl http://localhost:8000/api/v1/research/{task_id}
```

### 查询任务列表

```bash
curl 'http://localhost:8000/api/v1/research?limit=20'
```

### 搜索 Demo 股票

```bash
curl 'http://localhost:8000/api/v1/stocks/search?query=茅台'
```

## 支持的示例问题

- `分析贵州茅台的基本面和估值`
- `宁德时代近期有什么新闻和风险？`
- `比较贵州茅台和宁德时代`
- `Apple 的估值是否偏高？`

## 配置

复制环境变量模板后按需调整，并在启动前加载：

```bash
cp .env.example .env
set -a
source .env
set +a
```

| 变量 | 默认值 | 说明 |
|---|---|---|
| `APP_NAME` | `AI 投研助手 Demo` | OpenAPI 中的服务名称 |
| `APP_ENV` | `development` | 运行环境标识 |
| `API_V1_PREFIX` | `/api/v1` | API 前缀 |
| `CORS_ORIGINS` | `http://localhost:5173` | 逗号分隔的前端 Origin |
| `DATA_PROVIDER` | `yfinance` | `yfinance` 使用公开数据，`mock` 用于离线演示 |
| `DATABASE_PATH` | `./data/research.db` | SQLite 历史记录文件 |
| `QWEN_ENABLED` | `true` | 是否启用千问解释层 |
| `DASHSCOPE_API_KEY` | 空 | 阿里云百炼 API Key，只放在本地 `.env` |
| `QWEN_MODEL` | `qwen-plus` | 千问模型名 |
| `QWEN_BASE_URL` | 百炼兼容端点 | OpenAI 兼容 API 基础地址 |

## 测试

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest
```

测试覆盖完整 Agent 数据流、可解释新闻过滤统计、事实/分析/情景分类、风险审核边界、任务创建与查询、失败任务审计、股票搜索和 404 处理。

## 使用边界

- yfinance/Yahoo Finance 公开数据可能延迟、缺失或存在口径差异，仅用于本地个人研究。
- 中文公司名仅内置常用映射；任意 A/H/US 股票都可直接输入标准代码查询。
- 当前任务同步执行，一次真实分析需要等待外部数据源和千问响应。
- 关键事实请以交易所、监管机构和公司正式公告为准。
- 系统不预测股价、不提供买卖建议，也不会替用户作出投资决策。
