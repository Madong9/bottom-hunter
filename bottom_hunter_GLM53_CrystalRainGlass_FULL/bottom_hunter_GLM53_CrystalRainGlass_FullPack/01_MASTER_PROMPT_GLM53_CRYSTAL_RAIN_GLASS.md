# GLM-5.3 完整实施提示词
## Bottom Hunter — Crystal Clear Rain Glass UI / 无色透明晶体玻璃 + 真实雨滴 + GPU 加速

项目：
`https://github.com/Madong9/bottom-hunter`

你现在是本项目的：
- Senior Desktop UI Engineer
- Qt Quick / QML Graphics Engineer
- GPU Shader Engineer
- UI/UX Designer
- Regression-safe Refactoring Engineer

你的任务不是“简单换皮”，也不是制作启动动画。
你的任务是在 **不破坏任何业务逻辑和既有功能** 的前提下，把 Bottom Hunter 的桌面界面逐步重构为：

> **Crystal Clear Rain Glass Quant Terminal**
> **无色透明晶体玻璃量化终端**

---

# 0. 最高优先级：重新理解我的视觉目标

这是最高优先级，后面任何技术决策都不能与本节冲突。

## 0.1 我说的“玻璃”是无色透明玻璃

我要的是：

- crystal clear glass
- transparent optical glass
- clear liquid glass
- high transparency
- realistic refraction
- subtle backdrop blur
- subtle Fresnel reflection
- clean optical material
- transparent rain-covered glass
- premium professional financial terminal

**不要**：

- dark glass
- smoked glass
- black acrylic
- opaque charcoal card
- navy glass
- cyberpunk neon glass
- cyan tinted glass
- dark frosted plastic

背景可以偏暗、偏冷、偏夜景，以帮助金融数据阅读；
但是：

> **背景暗 ≠ 玻璃暗**

玻璃自身必须尽可能无色透明。

玻璃应该像真实的透明窗户/光学玻璃：
后方环境仍然明显可见，只产生轻微模糊、折射、亮边、反射和层次变化。

---

# 0.2 我说的“雨滴”是粘在玻璃表面的真实小水滴

雨滴必须属于：

> **screen-space / glass-surface**

正确空间关系：

Viewer
↓
small transparent water droplets attached to glass surface
↓
clear glass pane
↓
Bottom Hunter UI content
↓
background / environment

不是：

Viewer
↓
floating 3D spheres / orbs / bubbles
↓
Bottom Hunter

严禁把雨滴理解成：

- 3D sphere
- icosphere
- floating orb
- bubble
- cyan ball
- glass marble
- metaball
- jelly blob
- 3D splash object

### 特别注意当前错误实现

请先检查当前仓库是否仍然包含：

- `bottom_hunter/src/droplet_scene.py`
- `bottom_hunter/src/droplet_splash.py`
- `gui_qt.py` 中对 `DropletSplash` 的启动接入
- MatCap cyan glass sphere assets
- commit `4dc556c8041d0682b8588ba25ef45edbf97c22cd` 引入的 3D 大水球方案

这个方向是错误的。

附件：
`references/N1_WRONG_BIG_CYAN_ORBS.png`

它是 **NEGATIVE REFERENCE**。

禁止再次生成类似截图中的：
- 几个直径数百像素的青色球体
- 盖住 UI 的巨大 bubble
- 具有强烈自身颜色的 cyan water object

不要通过“把球缩小一点”来修复。
应放弃这条几何球路线。

如果当前分支仍然保留该错误实现：
1. 先审计后续提交依赖；
2. 安全移除错误 splash / sphere 接入；
3. 如适合，可用 `git revert`，但不得盲目 `reset --hard`；
4. 不得破坏后续独立 `ui_demo` 与业务代码；
5. 完成后跑全量测试。

---

# 1. 项目现状与红线

当前项目核心是：

- Python
- PySide6
- Qt Widgets
- QSS
- matplotlib
- QWebSocket
- scanner/backtest/research/storage/state machine 等业务模块

重点文件至少包括：

- `bottom_hunter/src/gui_qt.py`
- `bottom_hunter/src/gui_core.py`
- `bottom_hunter/src/chart_widget.py`
- `bottom_hunter/src/research_widget.py`
- `bottom_hunter/src/scanner.py`
- `bottom_hunter/src/backtest.py`
- `bottom_hunter/src/state_machine.py`
- `bottom_hunter/src/scoring.py`
- `bottom_hunter/src/sector_scoring.py`
- `bottom_hunter/src/storage.py`
- `bottom_hunter/src/research.py`
- `bottom_hunter/src/data_provider.py`
- `bottom_hunter/src/account_connectors.py`
- `bottom_hunter/src/longbridge_adapter.py`
- tests
- `bottom_hunter/pyproject.toml`

现有正式 GUI 有多个页面与成熟业务交互。

## 绝对红线

本次主要是 UI / presentation refactor。

禁止为了新 UI 重写或复制：

- scanner
- backtest
- state_machine
- scoring
- sector_scoring
- storage
- research
- data_provider
- account_connectors
- longbridge_adapter
- report
- alerts

禁止把 Python 业务逻辑复制进 QML。

保留现有子进程 / command 架构，或通过非常薄的 QObject/ViewModel Bridge 与 QML 连接。

---

# 2. 先审计，再编码

不要一上来改正式界面。

首先输出：

## 2.1 Repository UI Audit
说明：
- QWidget / QSS 当前架构
- UI 与业务耦合点
- signal / slot 关系
- 子进程关系
- chart/research 的关键交互
- 哪些代码是 presentation
- 哪些代码不能动
- 当前 `ui_demo` 状态
- 当前错误 droplet splash 是否仍接入生产界面

## 2.2 Migration Architecture
给出：

Python business layer
↓
thin QObject / ViewModel bridge
↓
Qt Quick / QML
↓
Scene Graph
↓
ShaderEffect / MultiEffect
↓
Qt RHI
↓
OpenGL / Vulkan / D3D
↓
GPU

## 2.3 File-level Plan
逐文件说明：
- 保留
- 新增
- 迁移
- 删除
- 风险
- 测试方法

然后才开始 Phase 1。

---

# 3. GPU 技术路线

目标技术栈：

- PySide6
- Qt Quick
- QML
- Qt Quick Scene Graph
- ShaderEffect
- MultiEffect
- `.qsb`
- Qt RHI
- OpenGL / Vulkan / Direct3D，按平台选择

## 禁止

不要为 UI 引入：
- CUDA
- PyTorch
- TensorFlow
- CuPy

这是 GPU Graphics，不是 AI Compute。

---

# 4. 玻璃材质规范：CLEAR TRANSPARENT GLASS

所有玻璃组件必须满足：

## 4.1 基础特征

- 基本无色
- 高透明度
- 后方内容可见
- 轻微 backdrop blur
- 极轻微 background refraction
- 细白色/环境色边缘高光
- very subtle inner highlight
- very subtle shadow
- very subtle noise
- subtle saturation compensation
- 清晰层级

## 4.2 视觉参数建议

不是硬编码要求，但可作为初始区间：

- glass tint/fill opacity: `0.025 ~ 0.10`
- border highlight opacity: `0.15 ~ 0.35`
- blur equivalent: `18 ~ 32 px`
- saturation: `1.05 ~ 1.15`
- shadow opacity: low
- refraction strength: subtle
- tint: neutral / near-white

注意：

“fill opacity 0.05”
不是把整个 QML Item opacity 设置为 0.05。

文字、图表、数字、控件必须保持完全清晰。

## 4.3 正确理解

我要的是：

> “UI 像刻在真正透明的玻璃上。”

不是：

> “UI 放在半透明黑塑料板上。”

---

# 5. 雨滴系统规范

## 5.1 尺寸分布

在约 1440×900 窗口中：

### micro droplets
- 1.5px ~ 4px
- 占 70% 以上
- 大多静止

### small droplets
- 4px ~ 9px
- 约 15~20%

### medium droplets
- 9px ~ 18px
- 数量较少

### large droplets
- 18px ~ 30px
- 极少
- 可以缓慢滑落

### absolute max
- 约 35px
- 极端稀少

禁止重新出现：
- 50px+
- 100px+
- 200px+
- 300px+

的大水球。

## 5.2 数量

High quality：
视觉上可产生约 80~180 个 micro/small droplets。

不要求创建 180 个 QObject。

优先：
- procedural shader
- SDF field
- hash/noise based distribution

## 5.3 形状

小滴：
- 近似圆
- 略微不规则

中滴：
- 重力方向略拉长

滑落滴：
- tear shape
- elongated shape
- thin trail

禁止：
- 完美球体 mesh
- bubble
- balloon
- soap bubble

---

# 6. 水滴的“3D 感”来自光学，不来自几何球

水滴的体积感通过：

- SDF / mask
- surface normal illusion
- Fresnel
- specular highlight
- refraction
- local UV displacement
- lens distortion
- subtle caustic-like highlight
- trail attenuation

实现。

优先 screen-space shader。

不要使用真实 sphere mesh。

---

# 7. 最重要：真实折射

水滴基本透明。

水滴内部应该看到：

> 后方 UI 被局部放大 / 扭曲 / 偏移

而不是被 cyan 色块遮住。

建议逻辑：

droplet mask
→ derive local normal
→ offset source UV
→ sample underlying scene/background
→ add weak highlight at edge
→ blend near-transparent result

### 效果要求

例如：
如果雨滴覆盖在某个非关键区域文字后方，
应该能隐约看到文字被 lens distortion 扭曲，
而不是文字被蓝绿色球挡住。

水滴主体颜色：
- neutral
- transparent
- slight environment reflection only

禁止：
- strong cyan
- turquoise solid fill
- saturated blue-green body

---

# 8. 雨滴不能影响金融数据阅读

建立 importance / exclusion zone 概念。

雨滴密度降低区域：

- K线主体
- 股票代码
- 价格
- 表格数字
- 主要按钮文字
- 输入框
- 警告
- 核心状态

雨滴密度可以增加区域：

- window edge
- nav background
- toolbar 空白区域
- card margin
- ambient background
- non-critical negative space

K 线必须保持高度清晰。

---

# 9. 3D UI 的真正含义

我要的“3D UI”不是塞入 3D 模型。

空间感来自：

- clear glass layering
- parallax
- shadow depth
- blur depth
- refraction
- highlight motion
- light response
- subtle perspective
- z-order separation

Mouse parallax：
- 最大约 2~5px
- 极轻
- 不影响操作

Hover：
- scale 约 1.005~1.01
- 微弱抬升
- 边缘高光增强

禁止：
- exaggerated bounce
- large zoom
- game HUD animation

---

# 10. 整体视觉语言

关键词：

- crystal clear
- clean
- transparent
- premium
- restrained
- professional
- financial
- optical
- realistic
- cinematic but subtle
- elegant
- minimal
- high information density
- non-cyberpunk

禁止：

- cyberpunk
- RGB
- purple neon
- blue neon
- gaming HUD
- sci-fi cockpit
- huge glow
- opaque cards everywhere
- black glass
- smoked glass

强调色：
- emerald green：正向/active
- restrained red：风险/错误
- white / cool gray：文字
- 不使用大面积高饱和色

---

# 11. 页面与组件方向

正式页面功能全部保留。

玻璃层级建议：

## Layer A：App environmental background
- 提供足够明暗变化，让透明玻璃可被看见
- 不能喧宾夺主

## Layer B：主透明玻璃壳
- 高透明
- 轻微 blur
- 边缘高光

## Layer C：导航 / toolbar
- 可以比内容卡片更强的玻璃感

## Layer D：内容卡片
- 更轻的透明玻璃
- 更少 blur
- 高可读性

## Layer E：表格 / K线
- 接近实体阅读层
- 不要为了透明而牺牲清晰度

## Layer F：最前方 water surface
- 小雨滴
- refraction
- highlight
- sparse motion

---

# 12. K线：早期绝对不要重写

现有 `chart_widget.py` 已经包含成熟功能：
- matplotlib / FigureCanvasQTAgg
- WebSocket
- 实时 K线
- 缩放
- 平移
- 十字光标
- 技术指标
- 画线
- 定时刷新
- 各类状态

早期迁移中：

**不要重写 K线核心。**

先把：
- app shell
- nav
- toolbar
- dashboard
- glass surface
- rain layer

做好。

K线可以先作为现有 QWidget / rendering surface 被包裹或保留。

只有整体稳定后，单独评估 GPU chart migration。

---

# 13. Phase 顺序

必须严格按顺序。

## PHASE 0 — Clean wrong implementation
- 审计错误 sphere splash
- 安全移除/撤销生产接入
- 跑测试

## PHASE 1 — Independent CrystalRainGlassDemo
只改：
- `bottom_hunter/ui_demo/`
或新的等价独立 demo 路径。

实现：
- clear background
- crystal glass
- small procedural rain
- refraction
- subtle parallax
- High / Balanced / Low
- FPS / frame time / RHI diagnostics

**不得接入正式 GUI。**

完成后必须：
- 给实际运行截图
- 给 backend
- 给 FPS
- 给 High/Balanced/Low 性能数据
- 停止并等待验收

## PHASE 2 — Design System
抽离：
- Theme
- Glass tokens
- radius
- spacing
- typography
- status colors
- quality presets

## PHASE 3 — App Shell
迁移：
- background
- nav
- toolbar
- global glass shell

## PHASE 4 — Dashboard
迁移总览。

## PHASE 5 — Other pages
逐页：
- 自选
- 报告
- 系统状态
- 研究
- 导入

## PHASE 6 — Chart Surroundings
只迁 K线外围 UI。

## PHASE 7 — Rain / Optical Refinement
优化：
- refraction
- droplet normal
- trails
- quality scaling

## PHASE 8 — Performance
- adaptive quality
- focus throttling
- minimize stop
- texture resolution optimization

## PHASE 9 — Tests / Regression
全量测试与回归。

---

# 14. Quality Presets

## High
- full procedural droplets
- refraction
- specular
- subtle trails
- higher shader resolution
- target 60 FPS

## Balanced
- fewer animated droplets
- lower internal effect resolution
- reduced refraction cost

## Low
- mostly static droplets
- no expensive dynamic refraction
- preserve clear-glass appearance

窗口失焦：
- 降低动画刷新频率

窗口最小化：
- 停止动画 / 重绘

静止状态：
- 不允许无意义满速 repaint

---

# 15. Linux / Windows 兼容

必须优先保证 Linux 桌面。

支持：
- X11
- Wayland
- software/offscreen fallback for CI

如果系统级 backdrop blur 在某平台不可用：

不要因此退化成黑色玻璃。

使用：
- internal scene sampling
- ShaderEffectSource
- QML scene background
- shader-based fallback

做跨平台透明玻璃。

---

# 16. Shader 约束

使用 Qt 6 正确 shader 路线：

- `.frag` / `.vert`
- qsb
- QML ShaderEffect
- Qt RHI compatible uniforms/layout
- reusable textures
- no per-frame texture creation

推荐探索：
- SDF droplet field
- hash/noise seeded distribution
- local UV displacement
- normal reconstruction
- Fresnel
- highlight
- trail field
- exclusion/importance mask

禁止：
- Qt5 obsolete inline shader assumptions
- huge per-droplet QObject count
- per-frame texture allocation
- per-frame new shader object

---

# 17. GPU Diagnostics

开发模式可显示：

- Qt version
- graphics API / RHI backend
- FPS
- frame time
- quality preset
- renderer / adapter（若 Qt 可可靠获取）
- effect resolution scale

正常用户模式隐藏。

---

# 18. 测试要求

原有 tests 不能删除来“让 CI 变绿”。

至少保留/增加：

- app construct smoke test
- QML load smoke test
- component existence
- shader `.qsb` existence
- quality preset behavior
- signal/slot wiring
- page switch
- scan command
- backtest command
- process stop behavior
- business regression tests

CI 无 GPU：
- software/offscreen fallback
- 不做像素级 GPU 视觉断言
- 不能因没有 GPU 而失败

---

# 19. 每阶段输出格式

每个 Phase 完成后报告：

1. 修改文件
2. 新增文件
3. 删除文件
4. 为什么
5. 是否触及业务逻辑
6. 运行命令
7. 测试命令
8. 测试结果
9. GPU backend
10. FPS / frame time
11. 截图路径
12. 已知风险
13. 下一步计划

不要只说“完成了”。

---

# 20. 视觉验收标准

必须全部满足。

## Glass
- [ ] 玻璃本身无色透明
- [ ] 后方环境明显可见
- [ ] 不是黑灰实体卡片
- [ ] 有轻微 blur
- [ ] 有真实折射
- [ ] 有细腻边缘高光
- [ ] 层级清晰

## Rain
- [ ] 雨滴像真实窗户小水滴
- [ ] 水滴基本透明
- [ ] 绝大多数 < 10px
- [ ] 极少数 18~30px
- [ ] 无巨大 sphere/orb
- [ ] 有局部折射
- [ ] 有轻微高光
- [ ] 少量滑落/水痕即可
- [ ] 不挡关键金融数据

## UI
- [ ] 专业金融终端
- [ ] 高可读性
- [ ] 非赛博朋克
- [ ] 非游戏 HUD
- [ ] K线清楚
- [ ] 表格清楚
- [ ] 操作逻辑不变

## Engineering
- [ ] GPU shader 实际工作
- [ ] 不使用 CUDA
- [ ] High/Balanced/Low 可切换
- [ ] Linux 可运行
- [ ] CI 无 GPU 可通过
- [ ] 原业务功能不变
- [ ] tests 通过

---

# 21. 附件优先级

请按以下优先级阅读附件：

### A0 — 最高优先视觉目标
`references/A0_PRIMARY_VISUAL_TARGET_CRYSTAL_CLEAR_UI.png`

只参考：
- 透明玻璃程度
- 玻璃层级
- 雨滴尺度
- 雨滴贴附感
- 数据可读性
- 整体克制感

### A1 / A2 — 设计规范辅助
- `references/A1_CRYSTAL_RAIN_GLASS_SPEC_OVERVIEW.png`
- `references/A2_CRYSTAL_RAIN_GLASS_DESIGN_BRIEF.png`

用于理解：
- 材质语言
- 分区
- rain/glass 关系
- GPU / Phase 约束

### N1 — 负面参考
`references/N1_WRONG_BIG_CYAN_ORBS.png`

这是错误实现。

任何新版本只要再次出现：
- 直径几十/上百像素的 cyan orb
- floating bubble
- sphere mesh
- 盖住内容的巨大水球

即视为验收失败。

---

# 22. 本轮只执行到 PHASE 1

现在开始：

STEP 1：
读取所有附件和本提示词。

STEP 2：
审计当前仓库状态。

STEP 3：
确认并清理错误 3D sphere splash（若仍存在）。

STEP 4：
跑全量测试。

STEP 5：
只在独立 `ui_demo` 中实现 Crystal Clear Rain Glass Demo。

STEP 6：
验证 GPU backend / FPS。

STEP 7：
提供实际运行截图。

STEP 8：
停止。

**未经我确认，不得进入正式 GUI migration。**

开始执行。
