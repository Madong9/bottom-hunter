# Reference Assets — 使用说明

## A. 最重要的目标图

文件：`references/00_TARGET_CONCEPT_RainGlassQuantTerminal.png`

用途：
- 总体方向
- 页面层级
- 深色玻璃金融终端气质
- 雨滴与内容之间的平衡
- 左侧导航 + 主工作区的构图

不要逐像素复刻，也不要把图片直接当背景。

## B. 雨滴光学参考（网页）

### Ref 1 — Pexels: Rain drops on glass at night
https://www.pexels.com/photo/rain-drops-on-glass-at-night-4279011/

观察重点：
- 小滴/中滴尺寸分布
- 水滴边缘高光
- 暖色散景经过水滴后的光学变化
- 水滴不是规则圆形

### Ref 2 — Pexels: Close-up of Water Drops on a Window Pane
https://www.pexels.com/photo/close-up-of-water-drops-on-a-window-pane-25325334/

观察重点：
- 不同焦距层次
- 水滴局部折射
- 高亮 bokeh 背景被水滴扭曲

### Ref 3 — Unsplash: dark glass droplets
https://unsplash.com/photos/water-drops-on-a-glass-surface-with-a-dark-background-mMFl_D59hoo

观察重点：
- 黑色背景上的水滴轮廓
- 克制的高光
- 适合金融终端的低饱和质感

这些图片仅供视觉参考，不建议作为程序运行时资源。

## C. Dashboard 参考（网页）

### Ref 4 — Behance Glassmorphism Dashboard
https://www.behance.net/gallery/190227507/Glassmorphism-Dashboard-UI-DESIGN

只学习：
- 透明层级
- 卡片前后关系
- 材质层次

不要学习其暖色配色，也不要复制具体布局。

### Ref 5 — Behance Finance Dashboard Dark Version
https://www.behance.net/gallery/187634517/Finance-Dashboard-%28Dark-Version-%29

只学习：
- 信息密度
- dark dashboard 的可读性
- 图表与卡片的层级

## D. Qt 官方技术参考

Qt ShaderEffect:
https://doc.qt.io/qt-6/qml-qtquick-shadereffect.html

Qt MultiEffect:
https://doc.qt.io/qt-6/qml-qtquick-effects-multieffect.html

Qt Quick Scene Graph / RHI:
https://doc.qt.io/qt-6/qtquick-visualcanvas-scenegraph-renderer.html

QSB:
https://doc.qt.io/qt-6/qtshadertools-qsb.html

## E. 重要规则

1. 目标图和摄影图都是 reference，不是最终 runtime texture。
2. 雨滴优先 shader procedural / stable generated field。
3. 不允许直接把摄影图铺在整个窗口上。
4. 如果需要极低强度 grain/noise，可以生成小尺寸 tileable noise runtime asset，但不能依赖大图。
5. UI 的可读性优先级高于雨滴特效。
