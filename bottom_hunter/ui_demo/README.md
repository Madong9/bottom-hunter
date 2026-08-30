# CrystalClearRainGlassDemo — PHASE 1 GPU 视觉原型

**Crystal Clear Rain Glass Quant Terminal（无色透明晶体玻璃量化终端）** 的独立视觉样板。
**不改动任何正式页面与业务逻辑**（MASTER_PROMPT §18）。

方向：无色透明玻璃 + 粘附在玻璃表面的 transparent 小雨滴（screen-space shader），
**不是** 3D 球/orb/bubble、不是暗色烟熏玻璃、不是赛博朋克霓虹。

## 运行

```bash
# 默认 balanced 档
.venv/bin/python -m bottom_hunter.ui_demo.demo_launcher

# 指定质量档 + 诊断 overlay
.venv/bin/python -m bottom_hunter.ui_demo.demo_launcher --quality high --diagnostics

# CI / 无 GPU 环境强制软件渲染（自动降级，不崩溃）
.venv/bin/python -m bottom_hunter.ui_demo.demo_launcher --software
```

## 结构

```
ui_demo/
    RainGlassDemo.qml        # 可复用主 item（散景背景+雨滴玻璃+布局）
    DemoWindow.qml           # ApplicationWindow 包装（launcher 入口）
    components/
        Theme.qml            # Design tokens 单例（含无色 glassTint #FFFFFF）
        GlassCard.qml        # Level B 透明玻璃卡片（近白 tint 0.05）
        GlassNavRail.qml     # Level A 透明玻璃导航
        MetricCard.qml       # 金融数据卡片
        StatusBadge.qml      # 状态徽章
    effects/RainGlassMaterial.qsb   # 预编译 shader（Vulkan/GLSL/HLSL/MSL）
    shaders/RainGlassMaterial.frag  # 源码
    demo_launcher.py         # 启动器 + Bridge（诊断/质量）
```

## 玻璃材质（Crystal Clear §4）

- **无色透明**：tint 用 `#FFFFFF`（近白），不是深 navy/charcoal
- fill opacity 0.03~0.07（§4.2 区间），文字/图表/数字保持完全清晰
- 边缘高光 0.22→0.32（hover），顶部 1px 内高光 0.20
- 阴影极弱（opacity 0.22），无大面积黑块
- 背景偏暗但是非纯黑 + 程序化 bokeh 散景，让透明玻璃有可被折射的明暗层次

## 雨滴 shader（screen-space，§5/§7）

**透明水滴，不是球体**：
- 四层 hash 分布，时间稳定（不逐帧重生成，无闪烁）
- 尺寸分布：micro 1.5–4px（密集 70%+）→ small 4–9px → medium 9–18px → large 18–30px（稀有，可缓慢滑落），硬上限 ~32px
- 主体透明：只做 **局部折射**（背后 UI 被放大/扭曲，不被色块遮挡）+ 极弱 environment inner light + 细 specular 边
- 边缘高光 + 轻微重力拉伸椭圆，无 cyan 实体填色
- **importance/exclusion zone**（`u_exclude` uniform）：图表/表格区域密度自动降到 0.18，保证金融数据可读

## 质量档（§14）

| 档 | 雨滴 | 折射 | FPS 实测（RTX 4080） |
|---|---|---|---|
| High | 完整 | 全强度 | 59.9 |
| Balanced（默认） | 55% | 75% | 60.0 |
| Low | 0（关闭） | 关 | 60.0 |

窗口失焦/最小化时动画暂停（QML `Window.active` 绑定）。

## GPU 路线（§3）

Qt Quick Scene Graph + RHI（自动 Vulkan/OpenGL/D3D/Metal），shader 经 `qsb` 预编译：

```bash
.venv/lib/python3.11/site-packages/PySide6/qsb \
  --glsl "100 es,120" --hlsl 50 --msl 12 \
  -o effects/RainGlassMaterial.qsb shaders/RainGlassMaterial.frag
```

实测 backend：`QRhi with backend OpenGL` + `NVIDIA GeForce RTX 4080` + GL 4.6。

## 测试

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen \
  python -m pytest bottom_hunter/tests/test_ui_demo.py -q
```

不做像素级截图断言（§18）；只测 QML 加载、组件解析、质量档数学、Bridge API。
