# AI 投研助手 Web

ChatGPT 风格的 React 单页投研界面，用于展示用户问题以及问题理解、金融数据获取、新闻过滤、分析和风险审核的完整过程。

产品定位：帮助普通投资者理解公司信息、发现关键变化并建立关注框架，不提供买卖建议。

## 启动

先启动后端：

```bash
cd ../backend
uvicorn app.main:app --reload
```

再启动前端：

```bash
cd frontend
npm install
npm run dev
```

访问 <http://localhost:5173>。开发服务器会把 `/api` 请求代理到 `http://localhost:8000`。

## 页面能力

- ChatGPT 风格的侧栏、消息流与底部输入框
- 预设投研问题和对话历史
- 五阶段 Agent 执行进度动画
- 投资行动问题的人机确认门，用户确认后才执行完整研究
- 报告顶部提供“这家公司当前需要了解什么”认知引导
- 公司画像和 PE、ROE、营收增长率等小白术语解释
- 股票行情、估值和财务指标卡片
- 新闻筛选漏斗、单条新闻五维评分和保留原因
- 已确认事实、AI 分析、未来情景和主要不确定性分层展示
- 积极因素、负面因素和待验证因素，不输出方向性评级
- 多股票结构化横向比较表
- Future Watch 关键变量清单和学习型推荐问题
- 每条保留新闻说明“为什么值得关注”
- 风险审核检查清单、证据来源及免责声明
- 桌面端和移动端响应式布局

## 配置独立 API 地址

默认使用 Vite 本地代理。若前端与后端分开部署，创建 `.env`：

```bash
cp .env.example .env
```

然后设置：

```text
VITE_API_BASE_URL=http://localhost:8000
```

## 构建

```bash
npm run build
```

运行前端测试：

```bash
npm test
```
