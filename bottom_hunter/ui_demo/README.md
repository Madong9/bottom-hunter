# RainGlassDemo — PHASE 1 GPU 视觉原型

Rain Glass Quant Terminal（雨夜玻璃量化终端）的独立视觉样板。
**不改动任何正式页面与业务逻辑**（MASTER_PROMPT §18）。

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
    RainGlassDemo.qml        # 可复用主 item（背景+雨滴+玻璃布局）
    DemoWindow.qml           # ApplicationWindow 包装（launcher 入口）
    components/
        Theme.qml            # Design tokens 单例（颜色/半径/间距/质量档）
        GlassCard.qml        # Level B 玻璃卡片
        GlassNavRail.qml     # Level A 浮动玻璃导航
        MetricCard.qml       # 金融数据卡片
        StatusBadge.qml      # 状态徽章
    effects/RainGlassMaterial.qsb   # 预编译 shader（Vulkan/GLSL/HLSL/MSL）
    shaders/RainGlassMaterial.frag  # 源码
    demo_launcher.py         # 启动器 + Bridge（诊断/质量）
```

## 雨滴 shader（§9）

程序化、时间稳定的水滴场：
- 网格 hash 决定每 cell 是否有水滴——**不逐帧重生成**（无闪烁）
- 三层尺寸分布：小滴（26px 格）密、中滴（110px 格）少、大滴（260px 格）稀有
- 重力拉伸椭圆、边缘 specular 高光、局部折射（UV 扭曲 + 轻微放大）
- 少数中/大滴极慢滑落（2~6 px/s），绝大多数静止
- density/quality 两个 uniform 由质量档控制

## 质量档（§13）

| 档 | 雨滴密度 | 折射 | 预期 |
|---|---|---|---|
| High | 100% | 全强度 | 60 FPS 目标（独显） |
| Balanced（默认） | 55% | 75% | 核显推荐 |
| Low | 0（关闭） | 关 | 静态玻璃，CI/无 GPU |

窗口失焦/最小化时动画暂停（QML `Window.active` 绑定）。

## GPU 路线（§4）

Qt Quick Scene Graph + RHI（自动选择 Vulkan/OpenGL/D3D/Metal）。
Shader 用 `qsb` 预编译（PySide6 自带编译器）：

```bash
.venv/lib/python3.11/site-packages/PySide6/qsb \
  --glsl "100 es,120" --hlsl 50 --msl 12 \
  -o effects/RainGlassMaterial.qsb shaders/RainGlassMaterial.frag
```

验证（QSG_INFO=1 打印实际后端，不伪造 adapter 名）：

```bash
QSG_INFO=1 .venv/bin/python -m bottom_hunter.ui_demo.demo_launcher --diagnostics
```

## 测试

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen \
  python -m pytest bottom_hunter/tests/test_ui_demo.py -q
```

不做像素级截图断言（§17）；只测 QML 加载、组件解析、质量档数学、Bridge API。
