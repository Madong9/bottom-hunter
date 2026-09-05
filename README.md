# Bottom Hunter

[![CI](https://github.com/Madong9/bottom-hunter/actions/workflows/ci.yml/badge.svg)](https://github.com/Madong9/bottom-hunter/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB?logo=python&logoColor=white)
![UI](https://img.shields.io/badge/UI-Qt%20Quick%20%2F%20QML-41CD52?logo=qt&logoColor=white)

面向个人自选池的跨市场超跌反弹扫描、研究与验证系统。项目支持 A 股、港股、美股和加密货币，统一管理同花顺、币安、欧易来源的自选资产，并通过日线数据识别“深度超跌、恐慌释放、拒绝创新低、相对强度转强和板块宽度确认”等结构。

桌面端采用 Qt Quick/QML，提供桌面透底的 Liquid Glass 界面、GPU 雨滴效果、只读研究中心、系统状态页，以及经过预览、校验、暂存、提交和回滚保护的自选导入流程。

> [!IMPORTANT]
> 本项目只用于观察、量化研究和策略验证，不构成投资建议，不连接实盘交易，也不会自动下单。数据不完整时系统会停止生成相关信号，而不是猜测或补造数据。

## 核心能力

- **自选驱动**：只扫描用户导入或手动维护的自选，不使用预置股票池。
- **跨市场分类**：加密货币、美港股和 A 股分开处理；股票按行业动态生成板块。
- **超跌反弹评分**：结合回撤、RSI、成交量、K 线拒绝形态、支撑位、板块宽度和时点基本面。
- **数据质量保护**：记录实际数据源、行情日期和覆盖率；停牌、缺失、过期或板块覆盖不足时不出信号。
- **滚动验证**：实时扫描与回测复用同一评分逻辑，并支持市场基准、费用、规则退出和时间分段。
- **研究中心**：展示财务指标、公告、新闻、媒体/社区观点和宏观数据；来源不足时保持 `N/A`。
- **安全导入**：文件先预览，再执行 `prepare -> stage -> verify -> commit`；失败时自动回滚。
- **桌面操作台**：总览、自选、研究、报告、导入、状态和 K 线七个入口。
- **通知去重**：支持 Server酱、企业微信、WxPusher 等可选通道，同一事件不会重复推送。

## 界面

当前 QML 产品外壳使用日间 Liquid Glass 视觉：

- 背景直接显示用户桌面，不内置黑夜或城市图片；
- 冰白半透明玻璃、内高光、厚边与柔和阴影；
- 可操作控件具有鼠标反射和按压反馈；
- 统一线宽的矢量导航图标和清晰中文字体；
- 静态 GPU 雨滴覆盖在最终合成层上。

Ubuntu GNOME/X11 可以显示透明窗口，但桌面级实时背景模糊取决于系统合成器。本项目在不读取、不保存桌面截图的前提下提供半透明材质、边缘折射感和交互高光。

## 架构

产品界面遵循单向依赖：

```text
Backend / snapshots
        |
        v
Adapter boundary
        |
        v
Frozen DTO
        |
        v
QObject ViewModel
        |
        v
Qt Quick / QML
```

QML 不直接访问业务模块、数据库或文件系统。`build_production_flow()` 是组合根，负责创建 Adapter、DTO Provider、ViewModel、导航和导入控制器。

导入是唯一的命令型页面：

```text
用户文件
  -> 只读预览与指纹
  -> ImportCommandDTO
  -> ImportController / worker thread
  -> RealMutationPort
  -> prepare -> stage -> verify -> commit / rollback
  -> ImportResultDTO
  -> ViewModel -> QML
```

详细架构说明见 [最终产品架构](bottom_hunter/docs/architecture/final_architecture.md)。

## 环境要求

- Linux 桌面（X11 或 Wayland）
- Python 3.11 或 3.12
- 推荐使用项目虚拟环境 `.venv`

长桥官方 Python SDK 在 Python 3.13 上可能需要本地 Rust/Cargo 编译，因此需要长桥行情时建议使用 Python 3.11/3.12。

Ubuntu/Debian 如果 Qt 提示无法加载 `xcb` 插件：

```bash
sudo apt update
sudo apt install -y libxcb-cursor0
```

## 快速安装

在仓库根目录执行：

```bash
git clone https://github.com/Madong9/bottom-hunter.git
cd bottom-hunter
python setup_longbridge.py
```

安装脚本会寻找兼容的 Python、创建 `.venv`，并安装 GUI、测试依赖和可用的长桥 SDK。

手动安装：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e "./bottom_hunter[dev]"
```

需要长桥认证行情时：

```bash
python -m pip install -e "./bottom_hunter[dev,longbridge]"
```

## 启动桌面端

推荐的 QML Liquid Glass 界面：

```bash
.venv/bin/python -m bottom_hunter.ui_demo.pages.application_shell_launcher
```

安装后也可使用：

```bash
bottom-hunter-qml
```

保留的 QtWidgets 完整操作台：

```bash
python gui.py
# 或
bottom-hunter-gui
```

无图形环境检查：

```bash
python gui.py --check
```

## 导入自选

同花顺、币安和欧易的个人收藏统一通过本地文件或手动方式维护，不要求平台密码、Cookie 或交易 API Key。

支持 Excel、CSV、JSON、TXT 等格式。建议在 QML“自选导入”页面选择来源、预览解析结果并确认导入。

命令行示例：

```bash
python sync_watchlists.py import \
  --source tonghuashun \
  --file /path/to/watchlist.xlsx \
  --account 我的同花顺

python sync_watchlists.py import \
  --source binance \
  --file /path/to/binance.csv \
  --account 我的币安

python sync_watchlists.py sync
python sync_watchlists.py status
```

`--account` 只是本地显示名称，不是账号密码。

## 每日扫描

扫描各市场最新已完成交易日：

```bash
python scanner.py
```

指定历史日期：

```bash
python scanner.py --date 2026-08-13
```

完全离线、只读取本地 CSV：

```bash
python scanner.py --offline --date 2026-08-13
```

输出位置：

```text
bottom_hunter/reports/daily_report_YYYYMMDD.md
bottom_hunter/reports/daily_report_YYYYMMDD.json
bottom_hunter/reports/charts/YYYYMMDD/
```

## 回测

```bash
python backtest.py \
  --start 2024-01-01 \
  --end 2026-08-13 \
  --cost-bps 20 \
  --stop-loss 0.08 \
  --take-profit 0.12
```

回测包含连续信号事件去重、次日开盘成交、手续费/滑点、分市场基准、规则退出和滚动时间分段。只有样本量、胜率、净收益、超额收益与时间稳定性同时满足要求，校准器才会给出可行动阈值。

## 评分概览

个股名义满分为 10 分：

| 维度 | 分值 |
| --- | ---: |
| 深度超跌 | 2 |
| 恐慌抛售 | 2 |
| 拒绝创新低 | 2 |
| 历史支撑位 | 1 |
| 板块宽度确认 | 1 |
| 时点基本面 | 2 |

基本面缺少可靠证据时显示为 `N/A`，总分改按可用分母展示。没有“拒绝创新低”确认时，即使其他指标较高，也只作为观察候选。

完整策略校准记录见：

- [策略复核](bottom_hunter/docs/strategy_review_20260829.md)
- [滚动验证结果](bottom_hunter/docs/validation_20260828.md)

## 配置与数据

| 路径 | 用途 |
| --- | --- |
| `bottom_hunter/config/watchlist.yaml` | 当前统一自选池 |
| `bottom_hunter/config/thresholds.yaml` | 评分和数据质量阈值 |
| `bottom_hunter/config/research.yaml` | 研究与宏观数据源 |
| `bottom_hunter/config/industry_overrides.yaml` | 人工行业修正 |
| `bottom_hunter/config/notify.example.yaml` | 通知配置模板 |
| `bottom_hunter/data/raw/` | 本地日 K 与远程缓存 |
| `bottom_hunter/state/signals.db` | 扫描、信号、提醒和研究状态 |
| `bottom_hunter/reports/` | 日报、回测和图表 |

真实通知凭据应写入被 Git 忽略的 `bottom_hunter/config/notify.yaml`，不要把 Token、Secret、Webhook 或 UID 提交到仓库。

## 数据源与隐私

- 股票行情可选择长桥认证行情，并在失败时降级到适用的公开备用源和本地缓存。
- 加密货币使用币安/欧易公开只读行情，不读取交易账户和平台收藏。
- 长桥凭据优先保存在操作系统密钥环；项目不会创建交易上下文。
- 新闻、观点和财报只保存必要的标题、摘要、来源、时间和链接。
- Liquid Glass 窗口通过系统 Alpha 合成显示桌面，不截取或保存桌面内容。

免费公共数据可能出现限流、延迟、缺失或历史调整；多个公共源一致也不等于数据绝对正确。用于真实资金决策前，应替换为有授权、可审计的生产行情并人工核查公告原文。

## 测试

当前回归基线为 273 项测试：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
QT_QPA_PLATFORM=offscreen \
.venv/bin/python -m pytest bottom_hunter/tests -q

.venv/bin/ruff check bottom_hunter/src bottom_hunter/tests
```

测试覆盖 DTO、Adapter、ViewModel 生命周期、QML 加载、事务导入、并发锁、回滚、策略计算、回测和架构隔离。

## 项目结构

```text
bottom-hunter/
├── README.md
├── gui.py
├── scanner.py
├── backtest.py
├── sync_watchlists.py
└── bottom_hunter/
    ├── config/
    ├── data/
    ├── docs/
    ├── reports/
    ├── src/                  # 业务、数据、扫描、回测
    ├── state/
    ├── tests/
    └── ui_demo/              # Qt Quick / QML 产品界面
```

更完整的参数、数据格式、长桥接入、研究中心、K 线操作、通知和自动运行说明，请阅读 [完整使用手册](bottom_hunter/README.md)。

## 已知边界

- 不包含实盘交易、自动交易或券商下单功能。
- QML K 线页已接入只读行情 Adapter，支持后台加载、定时刷新、周期切换、常用指标、Ctrl+滚轮缩放与会话内趋势线/水平线；持久化画线仍由 QtWidgets 操作台提供。
- GNOME/X11 没有通用的第三方窗口桌面模糊 API，因此 Liquid Glass 使用透明合成、材质 Tint、边缘光学和交互反射近似实现。
- 免费财报、新闻、宏观和行情服务可能不可用，系统会显示错误或保留最后良好缓存。
- 日 K 回测无法精确重建盘中成交顺序、涨跌停、汇率、税费和成交容量。

## 文档

- [完整使用手册](bottom_hunter/README.md)
- [最终产品架构](bottom_hunter/docs/architecture/final_architecture.md)
- [策略复核](bottom_hunter/docs/strategy_review_20260829.md)
- [验证报告](bottom_hunter/docs/validation_20260828.md)
- [QML / GPU 界面说明](bottom_hunter/ui_demo/README.md)
