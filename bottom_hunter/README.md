# 每日板块超跌反弹狩猎系统

这是一个以用户手动维护的自选为唯一观察池的日线扫描与研究系统，支持同花顺、币安和欧易三个自选来源，并可接入长桥 OpenAPI 作为 A股、港股和美股的认证行情主源。合并后分为加密货币、美港股和 A 股；链上股票归入美港股，加密货币不细分行业，股票则按行业动态生成检测板块。系统寻找“深度超跌 → 恐慌释放 → 拒绝创新低 → 相对强度转强 → 板块宽度确认”，不会自动下单。

> 输出仅供观察和量化研究，不构成投资建议。基本面没有可靠的时点数据时严格记为 `N/A`，不会自动补 2 分，也不会编造新闻。

## 目录结构

```text
板块检测/
├── scanner.py                    # 简便的日报入口
├── backtest.py                   # 简便的回测入口
└── bottom_hunter/
    ├── config/
    │   ├── watchlist.yaml        # 由三个自选来源的本地快照自动生成
    │   ├── industry_overrides.yaml # 人工行业修正
    │   ├── research.yaml         # 研究数据源、宏观指标和行业映射
    │   └── thresholds.yaml       # 默认阈值和板块覆盖阈值
    ├── data/
    │   ├── fundamentals.csv      # 人工/可靠来源的时点基本面评分
    │   ├── research_import_template.csv # 新闻/观点手工导入模板
    │   └── raw/                  # 日K缓存或离线 CSV
    ├── src/
    │   ├── account_watchlist.py  # 导入、标准化、去重和行业分组
    │   ├── account_connectors.py # 长桥认证行情连接
    │   ├── longbridge_adapter.py # 长桥官方 SDK 只读适配与代码转换
    │   ├── data_provider.py      # 长桥、公开股票源与币安/欧易日 K
    │   ├── indicators.py         # RSI、ATR、均线、回撤、K线形态
    │   ├── scoring.py            # 个股 10 分模型
    │   ├── breadth.py            # 板块宽度
    │   ├── state_machine.py      # 三阶段与失败状态机
    │   ├── sector_scoring.py     # 板块 100 分和领先排序
    │   ├── scanner.py            # 扫描编排与 CLI
    │   ├── alerts.py             # A–E 高级提醒
    │   ├── storage.py            # SQLite 状态和提醒去重
    │   ├── research.py           # 财报、公告、新闻、观点和宏观数据源
    │   ├── research_storage.py   # 研究数据时点缓存与去重
    │   ├── report.py             # Markdown、JSON 和图表
    │   └── backtest.py           # 无未来函数回测
    ├── tests/
    ├── reports/
    ├── state/watchlists/          # 三个来源的最后良好快照
    ├── state/signals.db
    └── pyproject.toml
```

## 安装

建议使用 Python 3.11 或 3.12；长桥官方 SDK 在 Python 3.13 上需要本地 Rust 编译环境，且其安装会失败。若你需要长桥行情，请在兼容版本 Python 中安装，其他功能可在 Python 3.13 上正常使用。

最简单的安装方式是在项目根目录执行：

```bash
python setup_longbridge.py
```

该脚本会自动查找 Python 3.11/3.12，创建隔离的 `.venv`，并安装 GUI、测试依赖和长桥 SDK。安装完成后，即使终端当前仍是 Python 3.13，`python gui.py` 也会自动切换到项目 `.venv`。

如需手动安装，要明确使用 Python 3.11/3.12：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e "./bottom_hunter[dev]"
```

如需启用长桥行情，再在该环境里执行：

```bash
python -m pip install -e "./bottom_hunter[dev,longbridge]"
```

系统依赖 `pandas`、`numpy`、`openpyxl`、`xlrd`、`PyYAML`、`matplotlib`、`exchange-calendars` 和 `PySide6`。`longbridge` 是官方行情 SDK 可选依赖；不安装时其他行情源仍可正常运行。开发依赖额外包含 `pytest`。

## 每日扫描

扫描每个市场最新一个已经完成的交易日：

```bash
python scanner.py
```

历史日期扫描：

```bash
python scanner.py --date 2026-08-13
```

常用选项：

```bash
python scanner.py \
  --config-dir bottom_hunter/config \
  --data-dir bottom_hunter/data/raw \
  --output-dir bottom_hunter/reports \
  --state-db bottom_hunter/state/signals.db
```

完全离线、只读取本地 CSV：

```bash
python scanner.py --offline --date 2026-08-13
```

报告输出为：

```text
bottom_hunter/reports/daily_report_YYYYMMDD.md
bottom_hunter/reports/daily_report_YYYYMMDD.json
bottom_hunter/reports/charts/YYYYMMDD/*.png
```

报告日期是运行/请求日期；报告内部单独记录 CN、HK、US 各自的实际完整行情日，周末和节假日不会被当作交易日。若交易所日历暂时不可用，程序只以实际取得的市场基准 K 线确认行情日，且时间窗口不加分。

## 桌面操作台

在项目根目录启动：

```bash
python gui.py
```

安装项目后也可以使用：

```bash
bottom-hunter-gui
```

操作台使用类似微信的三栏桌面布局：左侧深色功能导航、中间上下文列表、右侧工作区。界面使用 Qt 矢量绘制和高清中文字体，支持系统缩放，包含七个页面：

- **总览**：聚焦今日机会、数据健康、滚动验证和模拟组合四项核心信息；双击信号可查看中文分项、触发依据、关键价位与失效条件。
- **我的自选**：查看加密货币、美港股、A 股、跨来源重合和链上股票标识，按类别/行业过滤，也可人工修正股票行业。
- **研究中心**：按自选股查看财务指标、财报/公告、新闻、媒体与雪球等社区观点，并用归一化趋势图比较不同量纲的财务/宏观变化。
- **报告中心**：按时间浏览 Markdown 日报和回测报告，也可以交给系统默认应用打开。
- **自选导入**：同花顺、币安和欧易统一通过文件或手动添加维护，不需要平台 API Key；长桥认证行情作为独立的可选数据源保留。
- **系统状态**：检查组件、配置、SQLite、日报和各市场实际数据源，显示行情日、完整信号数、异常数及中文批次状态。
- **K线与画线**：查看自选标的的分钟、小时、日、周、月 K 线，支持自动刷新、十字光标、常用技术指标、成交量、缩放、平移、趋势线和水平线。

界面始终复用 `scanner.py` 和 `backtest.py` 子进程，不会在窗口线程里复制或简化评分逻辑。关闭正在运行的窗口或点击“停止任务”时，程序先发送安全中断，超时后再终止进程组。

服务器或CI环境可以只做无界面检查：

```bash
python gui.py --check
```

Linux 桌面需要 X11/Wayland 图形会话。极简系统如果缺少 Qt xcb 运行库，Debian/Ubuntu 可安装 `libxcb-cursor0`，Conda 环境可安装 `xcb-util-cursor`。命令行扫描和回测不依赖图形桌面。

### QML 产品外壳

PHASE 5 的 QtQuick/QML 产品外壳可独立启动：

```bash
bottom-hunter-qml
# 或
python -m bottom_hunter.ui_demo.pages.application_shell_launcher
```

该入口通过 `build_production_flow()` 统一注入总览、自选、研究、报告、导入、状态和 K 线七个路由的 ViewModel。导入页已接入异步事务链；K 线页通过只读 Adapter 复用现有行情服务，支持后台加载、定时刷新、周期切换、MA/BOLL/MACD/RSI/KDJ、Ctrl+滚轮缩放和会话内画线。原 `bottom-hunter-gui` 与 `python gui.py` 保持不变。完整边界说明见 [docs/architecture/final_architecture.md](docs/architecture/final_architecture.md)。

## 研究中心

在左侧点“研究”，再选择自选股或“宏观经济”。首次选择会自动后台加载，之后先显示 SQLite 缓存；点“刷新研究数据”可强制增量更新。所有表格的行都可双击打开原始来源。

- A 股财务指标和公告使用东方财富公开数据索引，同时提供巨潮资讯官方披露入口；重要数值应以公告原文为准。
- 美股使用 SEC EDGAR submissions 和 company facts/XBRL。
- 港股提供港交所官方检索入口；免费公共源无法稳定结构化财务表时，界面会保留为空而不编造。
- 新闻通过 Google News RSS 检索并去重；雪球通过 `site:xueqiu.com` 的公开搜索结果展示，不登录、不保存 Cookie、不复制整篇内容。
- 宏观数据默认使用 FRED CSV，指标和行业映射可在 [config/research.yaml](config/research.yaml) 修改。每个序列有独立最大数据年龄；过期值标黄、退出宏观评分但仍保留供核查。刷新后的最近 24 期用于趋势图。

如果某媒体/社区来源无法自动读取，点“导入观点”导入 CSV/JSON。CSV 格式参考 [data/research_import_template.csv](data/research_import_template.csv)，支持 `filing` / `news` / `media_opinion` / `community_opinion` / `official_analysis` 类型。本地库只保存标题、短摘要、来源和链接。

研究数据保存在 [state/signals.db](state/signals.db) 的 `financial_facts`、`research_items`、`macro_observations` 和 `research_refreshes` 表中。已缓存财报只有在 `available_at <= 扫描日` 时才能进入基本面分项；手工 [data/fundamentals.csv](data/fundamentals.csv) 仍有更高优先级。新闻、媒体观点和社区情绪永远不直接加减基本面分。

## 接入长桥行情

长桥用于补齐 A股、港股和美股的认证多周期行情，不读取长桥自选，也不用于下单：

1. 先按长桥 [OpenAPI 快速开始](https://open.longbridge.com/docs/getting-started) 在开发者平台创建应用并取得 App Key、App Secret 和 Access Token。
2. 确保当前环境已安装官方 SDK：`python -m pip install -e "./bottom_hunter[longbridge]"`。
3. 打开桌面端“导入”页，在“可选行情数据源”的长桥卡片中填入三项凭据，保持默认的中国区 OpenAPI 地址，点击“验证并启用行情”。
4. 验证成功后，卡片会显示连接状态，并在 SDK 可提供时显示行情等级和套餐。之后图表与日线扫描自动优先使用长桥，无需另改配置。

当前桌面端面向本地单用户，使用官方 SDK 仍支持的 API Key 认证。长桥对新的外部应用推荐 OAuth2；如果将本系统分发给多用户，应改为 OAuth2 + PKCE。凭据只保存在操作系统密钥环；密钥环不可用时仅保留在本次运行内存。程序只导入和创建 `QuoteContext`，不导入、不创建 `TradeContext`。

命令行扫描会自动从系统密钥环读取凭据。无图形服务器也可由密钥管理器注入 `LONGBRIDGE_APP_KEY`、`LONGBRIDGE_APP_SECRET` 和 `LONGBRIDGE_ACCESS_TOKEN`，不要把它们写入项目文件、启动脚本或日志。

可用市场、行情时效和历史 K 线唯一标的数量取决于账号的行情套餐及配额。程序将长桥并发限制为 5，每个扫描批次在连续失败后会熔断，并自动转用本地缓存和公开备用源。

## 维护我的自选

币安、欧易和同花顺的公开个人 API 不提供 App 收藏/自选列表读取。因此三个来源统一采用本地维护，系统不需要平台 API Key、登录密码或 Cookie，也不会模拟登录：

1. 在“导入”页为三个来源填写可选的“列表名称”，仅用于本地显示。
2. 同花顺可导入 `.xlsx`、`.xls`、`.csv` 等表格，也可按股票代码或名称手动添加；币安和欧易支持 Excel、CSV、JSON、TXT，或批量粘贴现货交易对。表格只有 `DOGE`、`SOL` 等币种简称时默认补为 USDT 交易对；`USDT` 本身因不存在 `USDT/USDT` K 线会跳过并提示。
3. 添加后系统按底层资产跨来源去重，且只从这些本地快照生成 [config/watchlist.yaml](config/watchlist.yaml)。原来的固定板块和公司不再参与扫描。
4. 将更新后的文件覆盖到原路径后，点击“刷新已导入文件”；开始扫描/回测前也会自动重新读取。

币安公共 K 线使用官方只读数据域名 `data-api.binance.vision`，不可用时自动降级到欧易或本地缓存。它只提供行情，不读取账号或平台收藏。

同花顺表格支持表头不在第一行，并自动识别以下常用列名：

| 用途 | 可用列名 | 是否必填 |
| --- | --- | --- |
| 股票代码 | `股票代码`、`证券代码`、`代码`、`symbol`、`ticker` | 与股票名称至少填一个 |
| 股票名称 | `股票名称`、`股票简称`、`证券名称`、`名称`、`名称（按截图）`、`name` | 与股票代码至少填一个 |
| 市场 | `市场`、`市场/类别`、`交易所`、`market` | 可选，建议名称重名时填写 A股/港股/美股 |
| 证券类型 | `证券类型`、`资产类型`、`type` | 可选，用于区分股票和 ETF |
| 行业 | `所属行业`、`行业`、`领域`、`industry` | 可选，留空会尝试自动补全 |

只有股票名称而没有代码时，系统只接受唯一的精确名称匹配；找不到或存在同名结果时不会猜测，会提示你补充股票代码和市场。股票和 ETF 会导入；概念/行业指数、期货主连和尚未支持的市场会安全跳过，导入完成后显示数量和原因。重新上传表格时，手动添加的股票会保留。

命令行也可以完成同样操作：

```bash
python sync_watchlists.py import --source tonghuashun --file /path/to/我的自选.xlsx --account 我的同花顺
python sync_watchlists.py import --source binance --file /path/to/binance.csv --account 我的币安
python sync_watchlists.py import --source okx --file /path/to/okx.json --account 我的欧易
python sync_watchlists.py sync
python sync_watchlists.py status
```

股票行业会先使用导入文件中的值，再通过公开行情资料补全股票名称和行业，结果会缓存以避免重复查询。仍为“待分类”时，在“我的自选”页选中股票后手工修正。修正保存在 [config/industry_overrides.yaml](config/industry_overrides.yaml)。全局评分阈值仍由 [config/thresholds.yaml](config/thresholds.yaml) 控制。

## K 线与画线分析

在“我的自选”页选中一个标的，点击“查看K线 / 画线”或直接双击该行，即可进入行情页。支持 `1分钟`、`5分钟`、`15分钟`、`30分钟`、`60分钟`、`4小时`、`日K`、`周K` 和 `月K`。币安自选优先使用无需账号的官方 WebSocket，当前未收盘 K 线约每 2 秒更新；欧易实时流可用时最快每秒更新，连续连接失败会自动改为 5 秒 REST 刷新。长桥股票 K 线每 5 秒刷新，其他公共股票行情每 15 秒刷新并明确标注可能延迟。关闭“自动刷新”后会同时停止实时流。

- 点击“趋势线”后，在 K 线图上依次点两个位置。
- 点击“水平线”后，在目标价位点一次。
- “主图指标”可选择 `MA(5/10/20/60)`、`EMA(12/26)`、`BOLL(20,2)` 或关闭；“副图指标”可选择 `MACD(12,26,9)`、`RSI(14)`、`KDJ(9,3,3)`、`ATR(14)` 或关闭。指标只使用当前及过去 K 线计算，切换时直接重绘，不会重新请求行情。
- 鼠标移到某根 K 线上时，底部信息栏会同时显示该根 K 线所选指标的数值。
- 鼠标位于图表内时，按住 `Ctrl` 滚动鼠标滚轮，可以以鼠标位置为中心调整画面内的 K 线数量；纵轴会随可见区间自动缩放。
- 下方 Matplotlib 工具栏支持缩放、平移、复位和导出图片。
- 画线按“标的 + 周期”自动保存在 [state/chart_drawings.json](state/chart_drawings.json)，刷新行情或重启程序后仍会恢复。

加密货币优先读取自选来源对应的币安/欧易公开 K 线。长桥已启用时，A股、港股和美股所有分钟、小时、日、周、月周期优先读取长桥官方前复权 K 线，SDK 可提供时界面会同时显示行情等级。未配置长桥或账号没有相应市场权限时，分钟图回退到腾讯/Nasdaq；日/周/月 K 回退到腾讯、最近扫描缓存、东方财富、Yahoo 和 Stooq，并标明实际数据源及最新日期。公共行情可能延迟，其中港股和美股的部分分钟周期由逐分钟报价聚合，高低价或成交量精度有限。

## 评分、状态和失败重置

个股名义满分 10 分：超跌 2、恐慌抛售 2、拒绝创新低 2、支撑位 1、板块宽度 1、基本面 2。首次一年事件回测显示月末/季度窗口没有稳定增益，因此时间窗口仍记录在报告中，但不再计分。支撑位取目标日之前历史摆动低点（可选叠加恐慌低点锚），当日回踩支撑区间并收于其上记 1 分。压力位为同期历史摆动高点的配套判断（不计分）。基本面为 `N/A` 时显示为 `x/8`；没有“拒绝创新低”触发时，无论总分多高都只显示观察。

当前一年回测没有任何分数阈值同时通过样本量、胜率、净收益、超额收益和分段稳定性验证，因此 `thresholds.yaml` 默认关闭行动级标签，候选最高为“早期反转观察”。只有新的滚动验证明确通过后，才应人工开启 `validation.action_signals_enabled`。

本次完整口径和校准结果见 [docs/validation_20260828.md](docs/validation_20260828.md)。

状态机包括：

```text
NORMAL → SELL_OFF → CAPITULATION → REVERSAL_DAY
       → NO_NEW_LOW → BREADTH_CONFIRM → TREND_CONFIRM
       → FAILED（重置）
```

- `ENTRY_STAGE_1`：深度超跌和强恐慌反转共振，仓位框架仅提示试探 25%。
- `ENTRY_STAGE_2`：恐慌后 1–3 个交易日拒绝创新低/突破恐慌日高点，提示增加 35%。
- `ENTRY_STAGE_3`：拒绝创新低、板块 60% 以上上涨、ETF 确认且 Risk-On，提示剩余 40%。
- 跌破恐慌低点超过配置阈值、连续创新低、放量再杀、宽度持续恶化或可靠基本面评分为 0 时转为 `FAILED`。

仓位百分比只是研究框架，不是下单指令。

## 基本面数据

[data/fundamentals.csv](data/fundamentals.csv) 是保守的时点接口：

```csv
date,symbol,score,reason,source
2026-08-10,SYMBOL,1,业绩指引存在不确定性,公告链接或内部数据编号
```

- `date` 必须是信息当时已经公开的日期；回测只能读取 `date <= 信号日` 的最后一条记录。
- `score` 只能是 0、1、2。
- `reason` 和 `source` 必须可人工核查。
- 没有手工记录时，系统才会尝试使用研究中心已缓存且当时已公开的财报指标。可用证据少于 3 项时仍为 `N/A`，不会默认给 2 分。

## 行情数据源与质量控制

`MarketDataProvider` 暴露以下可替换接口：

```python
get_daily_bars()
get_index_data()
get_sector_data()
get_fundamental_data()
```

默认优先复用已覆盖目标日期的完整本地缓存。加密货币优先使用它所在自选来源的币安/欧易官方公开日 K；币安公开行情因地区限制或网络故障不可用时，会在欧易尝试同交易对。A/H/美股在长桥账号已启用时优先使用长桥官方前复权日 K，随后按适用市场使用 Cboe 官方 VIX、腾讯行情、东方财富、Yahoo Chart 和 Stooq。连续网络失败达到配置次数后，该提供器会在本批次熔断。所有结果记录 `provider`、`data_timestamp`、`data_quality` 和警告，远程结果写入 `data/raw`。

风险偏好池中的中证 2000 默认使用中证2000ETF（563300）作为价格代理，并在名称中明确标识，不会伪装成指数原始行情。VIX 直接读取 Cboe 官方历史 CSV。

离线 CSV 文件名使用标准化后的证券/交易对代码，例如 `600000.SS.csv`、`BTC-USDT.csv`；指数 `^VIX` 对应 `INDEX_VIX.csv`。字段为：

```csv
date,open,high,low,close,volume
2026-08-12,100,105,98,104,1234567
```

也支持 `adj_close`。存在复权收盘价时 OHLC 会使用同一复权比例处理。重复日期保留最后一行；非法价格、空 OHLC 被移除。证券当日无 K 线、成交量为零、历史不足或数据陈旧时不生成该证券信号；板块最新数据覆盖低于配置比例时，整个板块停止产生交易信号；市场基准缺失时停止该市场。

## 提醒、推送与 SQLite

`state/signals.db` 保存扫描批次、个股信号、板块分数、提醒和研究缓存。提醒只包括文档中的 A–E：评分首次跃升、进入新 Stage、板块分数激增、指数创新低而核心股拒绝创新低、旧反转结构失败。相同日期、提醒类型、实体和消息指纹不会重复写入或重复显示。

信号发出后，每次扫描会自动回填历史信号的**真实后续收益**（3/5/10/20 日），形成滚动胜率（`signal_outcomes` 表）；日报和 GUI 总览显示近 30/90 天 5 日持有胜率，用于检验参数调整是否真的有效。

可选推送：复制 `config/notify.example.yaml` 为 `notify.yaml`，填入凭据并设 `enabled: true`。真实 `notify.yaml` 已被仓库忽略，建议权限设为 `600`，不得提交 Token、Secret 或 UID。到达微信的三条路：**Server酱**、**企业微信自建应用**、**WxPusher**；另有企业微信群机器人 webhook。扫描只推送数据库确认的新提醒，同一天重复运行不会重发；消息按手机阅读重排为中文状态、触发依据、支撑/压力、失效位、数据源与风险说明。

⚠️ **客户群/外部群限制**：微信与腾讯的政策均不允许全自动推送进客户群（防骚扰合规设计）——「客户群群发」API 只能创建任务，且必须由员工在手机上手动确认才发出。需要发给客户时：扫描会生成精简摘要文本 `reports/digest_YYYYMMDD.txt`，可直接复制转发；或使用企业微信「群发助手」生成任务后手动确认。

## 模拟组合

按三阶段入场框架记录目标仓位：阶段一 25%、阶段二累计 60%、阶段三累计 100%（实际增量为 25%、35%、40%）。净值包含未投入现金；多个候选总目标权重超过 100% 时按比例归一化，不使用隐含杠杆。每次扫描用最新收盘估值，日报同时显示净值与投入比例。仅供研究对照，不涉及真实下单。

## 回测

```bash
python backtest.py --start 2024-01-01 --end 2026-08-13
```

离线回测：

```bash
python backtest.py \
  --start 2024-01-01 \
  --end 2026-08-13 \
  --offline \
  --data-dir bottom_hunter/data/raw
```

输出：

```text
backtest_YYYYMMDD_YYYYMMDD.md
backtest_YYYYMMDD_YYYYMMDD.json
backtest_YYYYMMDD_YYYYMMDD_events.csv
```

系统分别统计 Score ≥ 5/6/7/8/9/10 后 3、5、10、20、60 个交易日的结果。连续达标按一次信号事件去重，信号次日开盘成交，扣除配置的双边成本；同时输出各市场基准收益、超额收益、分市场结果、止损/止盈/到期退出结果和滚动时间分段。校准器只有在事件样本≥20、胜率≥50%、净收益和超额收益均为正且至少半数时间分段同时为正时，才给出可行动阈值。

回测同时内置**压力位过滤实验**：对比"临近压力位（≤3%）"与"非临近"两组信号的 5 日胜率/收益，用于决定是否要在实盘信号中降级被压制的候选；逐事件 CSV 含 `near_resistance`、`breakout` 列。

防未来函数措施：所有指标在信号日逐行计算；新低和均量基准先排除当日；每个回测日期传给评分函数的行情在该日截断；支撑/压力位只用目标日之前的摆动点；基本面执行 `as_of` 过滤，并与实时扫描共用“手工记录优先、研究缓存兜底”链路；未来收益仅在评分冻结后计算。

## 突破候选（第二类信号）

除超跌反弹外，系统同时识别**放量突破压力位**的趋势候选：收盘越过近期摆动高点（2% 带内）、量比 ≥1.5、站上 MA20，且距突破点过远（>2%）视为追高风险不计。达标信号在日报标注"⚡突破候选"并持久化到 `signals.breakout` 列，与超跌反弹互补。

## 自动运行

提供 systemd 单元（见 `deploy/`）：

```bash
cp bottom_hunter/deploy/bottom-hunter-scan.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now bottom-hunter-scan.timer
```

定时器会在 A/H 股收盘后、美股收盘后以及加密货币周末分别运行。扫描器内置**数据看门狗**：若某市场基准数据缺失或过期，自动重试一次，仍失败才标记“部分完成”并继续其他市场。

Linux `cron` 示例（每天上海时间 07:15，通常可覆盖刚结束的美股以及此前结束的 A/H 股完整日K）：

```cron
CRON_TZ=Asia/Shanghai
15 7 * * * cd /home/robot/idea_work/板块检测 && /absolute/path/to/.venv/bin/python scanner.py >> bottom_hunter/reports/scanner.log 2>&1
```

服务器必须设置正确时区并保证网络、磁盘和 Python 虚拟环境稳定。上线时应配合进程退出码、日志轮转和外部监控；报告存在数据质量警告时不应将其转发成交易提醒。

扫描期间按一次 `Ctrl-C` 会取消尚未开始的取数任务，当前 SQLite 批次记为 `aborted`，命令以退出码 130 结束。网络请求使用短超时，少量已经开始的请求最多需要等待其超时回收；下次启动会自动修复上次遗留的 `running` 批次。

## 测试

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest bottom_hunter/tests -q
ruff check bottom_hunter/src bottom_hunter/tests
```

禁用插件自动发现可避免系统全局安装的第三方 pytest 插件污染本项目；干净虚拟环境中也可直接运行 `pytest`。

## 示例日报

仓库提供一份明确标注为合成数据的 [示例日报](reports/example_daily_report.md)。真实日报不会为了凑数而推荐标的：若没有 7 分以上且数据完整的候选，会直接输出“今日没有高质量反弹底部机会”、当日最高分和“建议继续等待”。

## 已知限制

- 长桥实际可用市场、延迟级别、推送能力和历史 K 线标的配额取决于账号资产与行情套餐；不足时系统会降级到公开行情，不会绕过平台限额。
- 免费公共行情可能限流、延迟、调整历史数据或缺少 A/H 股部分指数；生产使用应替换为授权数据并校验复权规则。
- 腾讯、东方财富、Yahoo Chart 和 Stooq 都不是本项目可审计的授权交易所数据。系统会故障回退，但多个公共源一致也不等于数据绝对正确；VIX 的 Cboe 来源除外。
- 中证 2000 使用跟踪 ETF 作为风险偏好代理，可能存在跟踪误差；若代理或 VIX 缺失，Risk-On 判定会保守退为 `Neutral`。
- 免费财报、新闻和宏观公共源可能限流、改版或暂时不可用；系统会保留最后良好缓存并显示数据源错误，但不会用新闻补齐缺失财报。
- FRED 免密钥 CSV 只能记录本机本次获取时间；严格宏观回测需通过 FRED/ALFRED API 另行导入历史 vintage，不能直接使用最新修订值。
- 新上市股票历史少于 65 根日K、停牌股票和板块覆盖不足时不会出信号。
- 回测已加入可配置的手续费/滑点、事件去重、市场基准与规则退出，但日K无法精确还原盘中成交顺序，也未模拟涨跌停、汇率、税、分红现金流和成交容量。
- 板块 100 分是排序指标，不等同于个股 10 分，也不直接构成买入理由。
