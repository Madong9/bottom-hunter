# AI投研助手

> 本目录由原“投研助手”项目完整合并而来，现作为 Bottom Hunter
> 的独立投研模块。桌面端可从左侧“投研助手”页面托管其生命周期；
> 原有前后端独立开发方式仍然保留。

AI投研助手是一个面向普通投资者、可在本地个人使用的公司认知辅助工具。它先通过 Query Router 将请求分为公司分析、同行比较、财务分析、估值分析、风险分析或新闻解读，再由 Stock Entity Resolver 解析公司实体，最后由五个专项 Agent 协作生成结构化、可追溯、易理解的公司研究报告。

## 产品定位

本项目帮助普通投资者：

- 理解公司信息和基础财务指标
- 从大量财经信息中发现值得关注的关键变化
- 建立可持续跟踪公司的关注框架

产品边界：

- 不预测股价
- 不提供买卖建议
- 不替用户进行投资决策

## 用户痛点

1. 金融知识门槛高

   PE、ROE、营收增长率等专业指标不容易理解，普通投资者难以快速判断这些指标反映了什么。

2. 财经信息过载，无法判断重点

   公告、新闻和行业信息数量庞大，用户难以分辨信息是否相关、可信、及时，以及它可能影响公司的哪个方面。

3. 缺少时间持续研究

   用户没有足够时间完整阅读财报、公告和新闻，也难以建立一套持续观察公司的问题清单。

## 核心能力

- 七 Agent 协作：任务路由、证券实体解析、问题理解、数据检索、新闻过滤、分析、风险审核
- 动态报告模块：Query Router 确定公司分析、同行比较、财务分析、估值分析、风险分析或新闻解读后，再结合用户原始提示词生成本次模块清单，前端仅展示相关内容
- 金融信息检索：可使用 Yahoo Finance 公开行情、财务和新闻数据，也可切换为离线 Mock 数据
- 千问分析增强：通过阿里云百炼 OpenAI 兼容接口生成通俗解释，失败时自动退回规则分析
- 本地研究历史：通过 SQLite 保存报告，刷新或重启服务后仍可查询
- 新闻过滤：展示候选、去重、低相关、低可信、过期和最终保留统计
- 财务指标解释：为 PE、ROE、营收增长率、净利润增长率提供通俗解释
- Fact / Analysis / Scenario 分离：区分已确认事实、AI 推断和条件式未来情景
- Human-in-the-loop 风险确认：涉及直接投资行动的问题必须由用户确认后继续
- 风险审核：检查事实来源、确定性承诺、推断标记、投资建议边界和情景措辞
- 认知引导：生成公司画像、关键关注问题、Future Watch 和学习型后续问题
- 多股票比较：结构化比较财务指标、商业特征、积极因素和主要风险

## 技术架构

Frontend：

- React
- TypeScript
- Vite

Backend：

- FastAPI
- Python
- Pydantic
- yfinance / Yahoo Finance 公开数据
- 千问 OpenAI 兼容 API
- SQLite

系统工作流：

```text
用户问题
  ↓
任务路由 Agent（六类金融任务）
  ↓
证券实体解析 Agent（公司名、简称、代码、市场）
  ↓
问题理解 Agent
  ↓
数据检索 Agent
  ↓
新闻过滤 Agent
  ↓
分析 Agent
  ↓
风险审核 Agent
  ↓
结构化认知辅助报告
```

## 项目结构

```text
投研助手/
├── backend/
│   ├── app/
│   │   ├── agents/          # Query Router + Stock Resolver + 五个专项 Agent
│   │   ├── api/             # REST API 路由
│   │   ├── core/            # 配置与异常
│   │   ├── mock_data/       # Mock 股票和新闻数据
│   │   ├── llm/             # 千问解释层与安全约束
│   │   ├── orchestration/   # 七 Agent 工作流
│   │   ├── providers/       # 金融数据 Provider 抽象
│   │   ├── repositories/    # SQLite / 内存任务仓库
│   │   ├── schemas/         # Agent 输入输出 Schema
│   │   └── services/        # 投研任务服务
│   ├── tests/
│   ├── Dockerfile
│   └── README.md
├── frontend/
│   ├── src/
│   │   ├── api/             # Backend API 客户端
│   │   ├── components/      # 对话、Timeline 和报告组件
│   │   ├── types/           # TypeScript 数据类型
│   │   └── utils/           # 投资行动意图识别
│   ├── package.json
│   └── README.md
├── docs/
│   ├── product_design.md
│   ├── evaluation_plan.md
│   └── demo_guide.md
└── README.md
```

## 启动方式

环境要求：Python 3.10+、Node.js 18+。

### 在 Bottom Hunter 中使用（推荐）

在仓库根目录执行：

```bash
.venv/bin/python -m pip install -e './bottom_hunter[research-assistant]'
npm --prefix research_assistant/frontend ci
```

然后启动 `bottom-hunter-qml`，进入“投研助手”页面。上位机会自动启动本地服务，
并通过 Qt WebEngine 把完整 React 工作台嵌入当前 QML 页面，不打开系统浏览器。
如需脱离桌面端一次启动前后端：

```bash
.venv/bin/python research_assistant/run.py --open
```

`run.py --check` 可只检查依赖。统一启动器会复用已运行的投研服务，
并仅回收由它自己创建的子进程。

### 1. 启动 Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

编辑 `backend/.env`，填入自己的千问 API Key：

```dotenv
DATA_PROVIDER=yfinance
DATABASE_PATH=./data/research.db
QWEN_ENABLED=true
DASHSCOPE_API_KEY=sk-你的百炼APIKey
QWEN_MODEL=qwen-plus
```

`.env` 已被 Git 忽略。请不要把 Key 写进代码、截图或提交记录。配置完成后启动：

```bash
uvicorn app.main:app --reload
```

Backend 地址：

- API：<http://localhost:8000/api/v1>
- Swagger：<http://localhost:8000/docs>
- 运行状态：<http://localhost:8000/api/v1/health>

### 2. 启动 Frontend

打开另一个终端：

```bash
cd frontend
npm install
npm run dev
```

Frontend 地址：<http://localhost:5173>

### 3. 运行测试

```bash
cd backend
pytest
```

```bash
cd frontend
npm test
npm run build
```

## Demo示例

### 分析贵州茅台

输入：

```text
分析贵州茅台
```

展示公司画像、普通投资者需要关注的问题、财务指标解释、新闻过滤结果、Fact / Analysis / Scenario 分层、Future Watch 和风险审核清单。

### 比较贵州茅台和宁德时代

输入：

```text
比较贵州茅台和宁德时代
```

展示两家公司在营收增速、净利润增速、ROE、PE、商业特点、积极因素和主要风险方面的结构化比较，并提示跨行业指标不能直接等同。

### PE是什么意思

输入：

```text
茅台PE是什么意思？
```

系统在保留原始 PE 数据的同时，展示专业定义和面向金融小白的通俗解释。

## 重要说明

真实模式支持：

- A 股：输入六位代码（如 `600519` / `600519.SH`）或内置常用中文公司名
- 港股：输入 Yahoo 格式代码（如 `0700.HK`）
- 美股：输入代码（如 `AAPL`）或公司英文名

Yahoo Finance 数据可能延迟、缺失或存在口径差异，且 yfinance 获取的数据仅适合个人研究使用。关键事实必须回到交易所公告、公司财报等正式来源核验。所有输出均不构成投资建议、收益承诺或交易依据。

如需完全离线演示，把 `backend/.env` 中的 `DATA_PROVIDER` 改为 `mock`、`QWEN_ENABLED` 改为 `false` 即可。

更详细的产品、评估和演示说明见 [docs](docs/)。
