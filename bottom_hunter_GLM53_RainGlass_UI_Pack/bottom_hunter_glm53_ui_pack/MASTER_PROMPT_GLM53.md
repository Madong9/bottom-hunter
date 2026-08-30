# GLM-5.3 Master Prompt — bottom-hunter「Rain Glass Quant Terminal」GPU UI 重构

你现在作为这个项目的 **Senior Desktop UI Engineer + Qt Quick/QML Engineer + GPU Graphics Engineer + UI/UX Designer + Python Refactoring Engineer** 工作。

项目仓库：
https://github.com/Madong9/bottom-hunter

## 0. 最终目标

在 **不改变现有业务逻辑、不破坏扫描/回测/研究/状态机/行情/数据库行为** 的前提下，把当前桌面 GUI 重构为一个高端、克制、真实、GPU 加速的：

> **Rain Glass Quant Terminal / 雨夜玻璃量化终端**

目标不是普通 QSS 换皮，不是网页式 glassmorphism，也不是满屏霓虹的赛博朋克 Dashboard。

我要的是：

- 深色金融工作站
- 真实透明/半透明玻璃层
- 高质量毛玻璃
- 玻璃边缘高光
- 局部折射与真实光学层次
- 粘附在玻璃表面的逼真雨滴
- 少量缓慢滑落、合并、留下水痕的水滴
- 微弱空间视差和 3D 深度
- GPU 渲染
- 数据可读性始终高于视觉特效
- Linux 桌面优先可用，同时兼容 Windows

视觉关键词：

`dark luxury`, `rainy glass`, `liquid glass`, `realistic optical material`, `cinematic`, `professional quantitative terminal`, `subtle 3D depth`, `restrained`, `high-end`, `graphite`, `charcoal`, `deep navy-black`, `emerald accent`。

---

# 1. 先完整阅读仓库，禁止盲改

在写代码之前，先完整检查至少这些文件/目录：

- `bottom_hunter/src/gui_qt.py`
- `bottom_hunter/src/gui_core.py`
- `bottom_hunter/src/chart_widget.py`
- `bottom_hunter/src/research_widget.py`
- `bottom_hunter/src/gui_launcher.py` 或实际 GUI launcher
- `bottom_hunter/tests/`
- `bottom_hunter/pyproject.toml`
- `.github/workflows/`
- README 中桌面端说明

首先输出简短但具体的 **UI architecture audit**：

1. 当前 Qt Widgets 架构是什么。
2. 哪些代码纯属 UI/presentation。
3. 哪些代码属于业务层，绝对不能迁进 QML。
4. 哪些 QWidget 可以保留并嵌入/过渡。
5. 哪些区域适合逐步迁移 QML。
6. 当前测试里哪些会受 UI 改造影响。
7. 你准备采用什么 GPU 渲染路线。
8. 文件级修改计划。

然后直接开始 PHASE 1，不需要等待我再次确认；但 **先做独立视觉原型，禁止一开始重写全部正式 GUI**。

---

# 2. 你需要理解当前项目的真实技术背景

当前项目是 Python 桌面应用，核心 GUI 使用 PySide6 / Qt Widgets。

已知重点：

- `gui_qt.py` 中存在较大的 QSS/APP_STYLE，当前透明效果主要依赖 `rgba`、渐变、边框等传统 QWidget 样式。
- 项目依赖 `PySide6>=6.8,<7`。
- K 线工作区当前使用 `matplotlib.backends.backend_qtagg.FigureCanvasQTAgg`。
- K 线已有实时 WebSocket、指标、十字光标、缩放、平移、趋势线/水平线等成熟交互。
- GUI 已经有多个正式页面，业务功能不是空壳。

因此：

**不要为了视觉重构把成熟的业务与交互一并推倒。**

尤其 PHASE 1–3 不允许重写完整 K 线模块。

---

# 3. 业务层红线

这次是 UI/渲染架构重构，不是策略系统重构。

除非为 UI 暴露只读状态而增加很薄的 adapter / QObject bridge，否则禁止重写或复制下列业务逻辑到 QML：

- scanner
- backtest
- state_machine
- scoring
- sector_scoring
- storage
- research
- research_storage
- data_provider
- account_watchlist
- account_connectors
- longbridge_adapter
- report
- alerts
- charting 中的数据/指标逻辑

必须继续复用现有扫描/回测子进程或现有调用机制。

**QML 只负责 View / Presentation / Interaction，不能成为新的业务层。**

如果需要桥接，创建明确的 Python ViewModel / QObject bridge，并让它调用现有 Python API。

---

# 4. GPU 技术路线

不要仅靠 `Qt Widgets + QSS` 模拟最终效果。

优先采用：

- PySide6
- Qt Quick / QML
- Qt Quick Scene Graph
- Qt Rendering Hardware Interface (RHI)
- `ShaderEffect`
- `ShaderEffectSource`
- `QtQuick.Effects.MultiEffect`
- Qt Shader Tools / `qsb`

Qt 6 shader 必须使用正确的 `.qsb` 工作流。

**禁止使用 Qt 5 时代的 inline GLSL string 当成最终方案。**

GPU 是 graphics rendering，不是 AI compute：

禁止为 UI 引入：

- CUDA dependency
- PyTorch
- TensorFlow
- CuPy

不要绑定 NVIDIA。

应允许 Qt RHI 根据平台使用：

- Vulkan
- OpenGL
- Direct3D 11/12
- Metal（如果未来运行于 macOS）

Linux 上优先保证 OpenGL/Vulkan 正常。

如果某个系统/CI 没有 GPU，必须提供软件/低质量 fallback，不能启动即崩溃。

---

# 5. 参考图片使用规则（极其重要）

我会附带视觉参考图片。

它们的作用只包括：

- 理解雨滴大小分布
- 理解水滴边缘高光
- 理解折射/散景
- 理解深色玻璃层级
- 理解整体气质
- 理解最终界面大致布局

**禁止：**

- 把参考雨滴照片直接盖到整个窗口
- 把参考图作为最终 UI 背景
- 直接截取参考 Dashboard 的组件
- 复制参考作品的品牌或具体设计

运行时视觉应尽可能程序化实现。

其中 `00_TARGET_CONCEPT_RainGlassQuantTerminal.png` 是最重要的“方向图”，但也只是设计方向，不要求逐像素复刻。

---

# 6. 视觉系统

## 6.1 总体气质

优先：

- 深色
- 精密
- 安静
- 高级
- 金融专业
- 真实材质
- 有空间感
- 长时间使用不疲劳

禁止：

- 廉价赛博朋克
- 大面积紫/蓝霓虹
- RGB 灯效
- 夸张 glow
- 游戏 HUD
- 动漫风
- 过度圆润的玩具感
- 大量渐变按钮
- 所有东西都半透明
- 看起来像网页模板

---

# 7. Design Tokens

请把样式抽象成统一 tokens，不要在所有 QML 文件散落 magic numbers。

建议初始值，可以根据实际效果微调：

## Colors

- Background 0: `#05070A`
- Background 1: `#090D12`
- Background 2: `#0D131A`
- Surface glass tint: cool charcoal / blue-black
- Primary text: `#EEF3F6`
- Secondary text: `#9AA6B2`
- Muted text: `#626D78`
- Emerald accent: `#2BD576` 或更克制的近似绿色
- Positive: emerald green
- Warning: low-saturation amber
- Error: low-saturation red
- Info: restrained cool blue

中国/亚洲金融软件已有涨跌配色习惯的地方，不要盲目把业务含义改掉；尊重项目现有颜色语义。

## Radius

- small controls: 8–10
- regular controls: 12
- card: 14–18
- major glass surface: 18–24

不要所有控件都 24px 大圆角。

## Spacing

采用统一 4/8px grid，常用：

- 4
- 8
- 12
- 16
- 20
- 24
- 32

金融终端信息密度可以偏高，不要做成巨大留白的营销网站。

---

# 8. 真实玻璃材质

玻璃绝对不能只等于：

`rgba + 1px white border`

玻璃材质应组合：

1. Background capture / transmission
2. Blur
3. Dark translucent tint
4. Edge highlight
5. Inner highlight
6. Soft external shadow
7. Very subtle noise/grain
8. Optional local refraction
9. Layer-specific opacity
10. Depth-aware hierarchy

玻璃层级建议：

### Level A — 导航/浮动工具条
玻璃感最明显。

### Level B — 信息卡片
中等玻璃。

### Level C — 表格/K线/密集数据内容
玻璃效果非常克制，以可读性为主。

不要让文字本身被 blur。

不要对整个 UI 做高强度 blur。

---

# 9. 雨滴 GPU Shader 设计

雨滴必须看起来像粘附在真实玻璃表面，而不是粒子系统。

目标元素：

- 多尺寸 droplets
- 大量极小静态 droplets
- 少量中等 droplets
- 极少数较大 droplets
- 非完美圆形
- 椭圆/重力拉伸
- surface tension appearance
- edge specular highlight
- normal-like lighting
- local refraction
- background UV distortion
- slight magnification
- occasional slow slide
- gravity
- trail / wet streak
- rare merge behavior
- stable random seed / temporal coherence

不要每帧随机重生成整个水滴场，否则会闪烁。

雨滴空间分布要服从 UI 可读性：

高密度允许出现在：

- 外围背景
- 导航玻璃外缘
- 空白区域

低密度/禁用区：

- K线蜡烛主体
- 股票代码
- 当前价格
- 表格数字
- 输入框文字
- 重要风险提示文字

雨滴移动：

- 绝大多数不动
- 少数非常慢
- 不允许“下雨粒子从顶部不断落下”的游戏效果

---

# 10. 3D 深度与交互

不需要为了“3D”引入大量真正的 3D 模型。

通过以下方式产生深度：

- foreground/background separation
- shadow hierarchy
- blur hierarchy
- highlight movement
- subtle scale
- slight parallax
- small perspective transforms

鼠标 parallax：

- 最大位移约 2–5 px
- 极其缓慢
- 必须平滑插值
- 禁止晃动

hover：

- scale 约 1.005–1.01
- 轻微上浮
- 玻璃边缘高光增强
- 不要 bounce

pressed：

- scale 轻微下降
- 高光减少

---

# 11. 背景

背景应接近：

- charcoal
- graphite
- deep navy-black

允许：

- 超慢速柔和 light fog
- extremely subtle bokeh
- low-frequency gradient movement
- subtle grain

禁止：

- 明显循环视频背景
- 大范围快速流体动画
- 抢注意力的城市视频
- 强紫色 aurora

视觉上应该像“雨夜高级金融工作站”，而不是动态壁纸软件。

---

# 12. 正式页面重构方向

保留所有现有页面与功能。

至少包括仓库中当前已有的：

- 总览
- 我的自选
- 研究中心
- 报告中心
- 自选导入
- 系统状态
- K线与画线

## 左侧导航

- 约 64–76px
- floating glass rail
- 图标为主
- active 状态使用非常克制的 emerald indicator
- 不要整块亮绿色

## 上下文侧栏

- 约 250–300px
- 列表密度适中
- selected item 使用浅玻璃抬升

## 顶部 toolbar

- 状态
- 日期/市场信息
- quality preset
- 可选 settings

保持低视觉噪音。

## 总览 Dashboard

应该融合：

- Bloomberg/Trading Terminal 的信息效率
- 高端空间化玻璃 UI 的层级感

但绝对不要复制 Bloomberg 的视觉。

核心卡片：

- 今日扫描机会
- 数据健康
- 市场状态
- 风险/实时提醒
- 板块排名
- 历史验证/模拟组合等现有项目已有数据

## K线

K线必须成为页面的视觉核心。

PHASE 1–3：

**保留现有 matplotlib / FigureCanvasQTAgg，不要重写。**

先把它放进干净、低干扰的深色容器里，周边 QML/QWidget shell 负责玻璃效果。

以后如果真的需要把图表也 GPU 化，必须单独立项，先确保当前所有：

- 指标
- 实时 WebSocket
- 十字光标
- 缩放
- 平移
- 画线
- 注释

行为有完整迁移方案和回归测试。

---

# 13. 性能策略：必须有自适应质量

实现：

## High

目标：现代独显/高性能核显

- 60 FPS target
- 完整雨滴场
- 高质量 refraction
- glass blur
- edge highlights
- subtle parallax
- better shader resolution

## Balanced

默认推荐档。

- 减少雨滴数量
- 降低 blurMax
- 降低 shader texture/internal resolution
- 降低折射复杂度
- 保留整体质感

## Low

- 关闭动态雨滴
- 关闭昂贵 refraction
- 降低/关闭实时 blur
- 保留静态玻璃 tint/border/shadow
- 界面依旧完整、美观、可读

窗口失焦：降低动画刷新。

窗口最小化：暂停所有非必要动画。

如果可能，在静态状态减少 continuous repaint。

不要为了 60 FPS 无意义地让所有组件每帧刷新。

---

# 14. GPU/渲染诊断

添加仅开发模式可见的 diagnostics overlay 或日志功能。

至少尝试显示：

- Qt version
- Scene Graph / RHI graphics API
- requested backend
- actual backend（能可靠取得时）
- FPS
- frame time
- active quality preset
- shader load status

如果平台允许可靠获取 renderer/adapter 名称则显示，否则不要伪造。

支持通过 Qt 自己的日志/QSG 信息验证 GPU 路径。

不要使用 CUDA 来判断 GPU。

---

# 15. Shader 性能约束

必须避免：

- 每帧创建 texture
- 每帧创建 QObject
- 巨大 4K/8K offscreen texture
- 无限 droplet 数量
- 多层全屏 blur 串联
- 不必要的多 pass
- 对整个 app 每层都做 ShaderEffectSource

优先：

- MultiEffect 合并常用效果
- 控制 ShaderEffectSource textureSize
- 只对必要区域 capture
- 低分辨率效果缓冲 + upscale/composite
- reusable resources
- stable uniforms
- 降低 overdraw

---

# 16. Linux / Windows 兼容

Linux 是一等公民。

必须考虑：

- X11
- Wayland
- Mesa/Intel/AMD
- NVIDIA proprietary driver
- OpenGL fallback
- Vulkan 可用时可选

不要把 Windows Acrylic/Mica 当唯一方案。

平台原生 blur 可以是 enhancement，但必须有跨平台 shader/static fallback。

Windows 下也不能写死特定 GPU vendor。

---

# 17. CI / Headless 测试

CI 没有真实 GPU 时不能失败。

要保留/补充：

- `python gui.py --check` 等已有无界面检查能力
- existing unit tests
- GUI smoke test
- window construction test
- page construction/switching
- signal-slot wiring
- scan/backtest command wiring
- close/stop task behavior
- QML load smoke test

如果 software backend 不支持 ShaderEffect：

允许自动进入 Low / visual effects disabled 模式。

不要在 CI 对 shader 像素结果做脆弱的 screenshot equality test。

---

# 18. PHASE 1：独立 GPU Visual Prototype（现在首先执行）

**不要先改正式七个页面。**

新增一个完全独立可运行的视觉样板，例如：

```text
bottom_hunter/ui_demo/
    RainGlassDemo.qml
    components/
    effects/
    shaders/
    demo_launcher.py
```

具体目录可根据项目包装结构调整，但要清晰隔离。

原型尺寸以约 1440×900 为主要设计参考，必须支持 resize。

原型使用假数据即可。

至少包含：

1. 深色背景
2. 左侧 glass nav rail
3. 中间 glass context panel
4. 顶部 toolbar
5. 4–6 个金融数据卡片
6. 大面积 chart placeholder
7. 雨滴 shader
8. 玻璃材质
9. 微弱 parallax
10. High/Balanced/Low 切换
11. diagnostics

先验证：

- 真不真实
- 漂不漂亮
- 有没有廉价感
- GPU 是否工作
- Linux 是否稳定
- 是否能接近 60FPS

**如果 visual prototype 不够惊艳，不要急着迁移正式页面，先把材质和 shader 做对。**

---

# 19. PHASE 2：Design System

在 prototype 通过之后，提取统一：

- `Theme.qml`
- `GlassSurface.qml`
- `GlassCard.qml`
- `GlassButton.qml`
- `GlassInput.qml`
- `GlassPanel.qml`
- `StatusBadge.qml`
- `MetricCard.qml`
- `SectionHeader.qml`
- `QualityManager`
- `EffectsManager`

名字可调整，但必须组件化。

不要把所有视觉逻辑堆进一个巨大 QML 文件。

---

# 20. PHASE 3：Shell Migration

迁移应用外壳：

- background
- nav
- toolbar
- page container
- context panel

此阶段仍尽量保持现有业务 QWidget 可嵌入或通过桥接复用。

确保回退路径存在。

---

# 21. PHASE 4–6：页面逐步迁移

建议顺序：

1. 总览
2. 我的自选
3. 系统状态
4. 报告中心
5. 导入
6. 研究中心
7. K线外围 shell

不要一次性重写全部。

每迁移一个页面都要跑原测试与 GUI smoke tests。

---

# 22. PHASE 7：Rain Shader Refinement

正式 UI 稳定后再做：

- better droplet normals
- merge approximation
- trails
- adaptive density masks
- depth-aware distortion
- low-frequency lighting movement

特效必须可关闭。

---

# 23. PHASE 8：性能与稳定性

测量：

- idle FPS / frame time
- mouse moving
- resize
- full rain
- chart live update
- window focus/unfocus
- minimize/restore

避免用户把窗口放着不动时 GPU 仍持续高负载。

---

# 24. PHASE 9：回归与清理

最终：

- 全测试
- ruff
- formatting
- headless check
- Linux launch
- Windows compatibility review
- resource cleanup
- shader compilation instructions
- README 使用说明

不要为了 UI 重构删除原有有价值的 tests。

---

# 25. 用户体验细节

必须做好：

- hover
- pressed
- focus
- disabled
- loading
- empty
- warning
- error
- success
- scrollbars
- tooltip
- modal/dialog
- dropdown
- table selected row
- keyboard focus

玻璃 UI 不能牺牲可访问性。

---

# 26. 文本与中文

这是中文金融桌面应用。

保证：

- 中文字体清晰
- 高 DPI 正常
- 125% / 150% / 200% scaling 正常
- 字号不要过小
- 数字最好使用稳定的 tabular / monospace-like 数字布局（字体支持时）

不要为了“高级感”把文字做成细到难读。

---

# 27. 安全修改原则

开始修改前：

- 查看 git status
- 不覆盖用户未提交修改
- 不删除不相关代码
- 不修改策略阈值
- 不修改行情认证行为
- 不改变数据库 schema，除非 UI 配置确实需要，并优先避免

建议在独立 feature branch 工作。

---

# 28. 完成每个阶段时的固定汇报格式

每阶段完成后告诉我：

### Files changed
列出新增/修改文件。

### What changed
具体说明效果。

### Business logic impact
明确说明是否改动业务层；原则上应为“无”。

### GPU path
说明当前渲染走什么路径以及如何验证。

### How to run
给出准确命令。

### How to test
给出准确测试命令。

### Performance
说明当前 High/Balanced/Low 差异和已知瓶颈。

### Known limitations
不要隐藏问题。

### Next phase
下一阶段计划。

---

# 29. 最终验收标准

只有同时满足以下条件才算完成：

1. 第一眼是高端金融工作站，而不是网页模板。
2. 玻璃具有真实光学层次。
3. 雨滴像粘在玻璃上，而不是粒子特效。
4. 雨滴会产生可控的局部折射/高光。
5. UI 有空间深度但不晃眼。
6. 重要金融数据始终清晰。
7. GPU 参与 Qt Quick/Scene Graph 视觉渲染。
8. 不需要 CUDA。
9. Linux 可正常运行。
10. Windows 设计上可兼容。
11. 无 GPU/CI 环境有 fallback。
12. High/Balanced/Low 可切换。
13. 最小化/失焦会降低开销。
14. 原有业务功能行为保持。
15. scanner/backtest/research/state_machine/storage 不被复制到 QML。
16. K线原有交互在迁移前不被破坏。
17. 所有相关 tests 通过。
18. 视觉效果参数可维护、组件化，而不是散落 magic numbers。

---

# 30. 现在开始执行

执行顺序：

1. Audit repository。
2. 输出架构审计和文件级计划。
3. 立即创建 PHASE 1 独立 `RainGlassDemo`。
4. 编译/准备 Qt 6 `.qsb` shaders。
5. 加 High/Balanced/Low。
6. 加 diagnostics。
7. 运行能运行的测试与 smoke check。
8. 汇报实际修改和启动命令。

不要只给我设计建议或伪代码。

**你需要实际落地到仓库代码。**

如果某个效果在当前 PySide6/Qt 版本做不到，明确说明技术限制并采用视觉上最接近且跨平台可维护的 fallback；不要伪造“已经实现真正系统级 backdrop blur”。
