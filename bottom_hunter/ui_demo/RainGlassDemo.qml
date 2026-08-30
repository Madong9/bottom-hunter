// RainGlassDemo — PHASE 1 independent GPU visual prototype.
// Rain Glass Quant Terminal look (MASTER_PROMPT §0/§18):
// dark bg + rain-droplet ShaderEffect glass + floating nav + metric cards
// + chart placeholder + parallax + High/Balanced/Low + diagnostics.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Effects
import "components"

Rectangle {
    id: root

    // quality: "high" | "balanced" | "low"（由 demo_launcher 经 Bridge 设置）
    property string quality: "balanced"
    property bool gpuActive: true          // 由 launcher 注入（RHI backend 检测）
    property string rhiBackend: "unknown"  // launcher 注入实际后端名

    // ---- parallax state (§10: max 4px, smooth interpolation) ----------
    property real mouseX: 0.5
    property real mouseY: 0.5
    readonly property real parallaxX: (mouseX - 0.5) * 2 * 4.0
    readonly property real parallaxY: (mouseY - 0.5) * 2 * 3.0

    readonly property bool effectsOn: quality !== "low"
    readonly property real dropletDensity: quality === "high" ? 1.0 : (quality === "balanced" ? 0.55 : 0.0)
    readonly property real shaderQuality: quality === "high" ? 1.0 : (quality === "balanced" ? 0.75 : 0.0)

    width: 1440
    height: 900
    color: "#05070A"

    // 深色渐变背景（charcoal → deep navy-black）
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#05070A" }
            GradientStop { position: 0.55; color: "#090D12" }
            GradientStop { position: 1.0; color: "#0D131A" }
        }

        // 超低速柔和 fog（低频渐变移动，§11 允许）
        Rectangle {
            anchors.fill: parent
            opacity: 0.05
            gradient: Gradient {
                orientation: Gradient.Vertical
                GradientStop { position: 0.0; color: "#1B2A3A" }
                GradientStop { position: 0.5; color: "transparent" }
                GradientStop { position: 1.0; color: "#14202C" }
            }
            SequentialAnimation on opacity {
                loops: Animation.Infinite
                NumberAnimation { from: 0.03; to: 0.07; duration: 9000; easing.type: Easing.InOutSine }
                NumberAnimation { from: 0.07; to: 0.03; duration: 9000; easing.type: Easing.InOutSine }
            }
        }
    }

    // ---- 雨滴玻璃层（ShaderEffect + 预编译 .qsb）-------------------------
    // 捕获背景（含雾层），叠加程序化水滴场：折射 + 边缘高光 + 视差。
    ShaderEffectSource {
        id: backgroundSource
        anchors.fill: parent
        sourceItem: bgGradientItem
        hideSource: false
        visible: false
        textureSize: Qt.size(
            Math.max(2, Math.floor(root.width * (root.quality === "high" ? 1.0 : 0.7))),
            Math.max(2, Math.floor(root.height * (root.quality === "high" ? 1.0 : 0.7)))
        )
    }

    Rectangle {
        id: bgGradientItem
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#05070A" }
            GradientStop { position: 0.55; color: "#090D12" }
            GradientStop { position: 1.0; color: "#0D131A" }
        }
    }

    ShaderEffect {
        id: rainEffect
        anchors.fill: parent
        visible: root.effectsOn && root.gpuActive

        property variant source: backgroundSource
        property vector2d resolution: Qt.vector2d(width, height)
        property real u_time: 0.0
        property vector2d u_parallax: Qt.vector2d(root.parallaxX, root.parallaxY)
        property real u_quality: root.shaderQuality
        property real u_density: root.dropletDensity

        fragmentShader: "effects/RainGlassMaterial.qsb"

        // 时间步进：慢速（水滴极慢移动）。失焦时由 Bridge 减速。
        NumberAnimation on u_time {
            from: 0
            to: 3600
            duration: 3600000
            loops: Animation.Infinite
            running: root.effectsOn && root.gpuActive && root.Window.active !== false
        }

        Behavior on u_parallax {
            Vector3dAnimation { duration: 900; easing.type: Easing.OutCubic }
        }
    }

    // ---- 主布局（parallax 前景）------------------------------------------
    Item {
        id: foreground
        anchors.fill: parent
        // 前景反向极小位移制造深度（§10）
        transform: Translate {
            x: -root.parallaxX * 0.25
            y: -root.parallaxY * 0.25
        }

        RowLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 16

            // 左侧浮动玻璃导航（Level A）
            GlassNavRail {
                id: navRail
                Layout.preferredWidth: 72
                Layout.fillHeight: true
                currentIndex: 0
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 16

                // 顶部 toolbar（Level A 玻璃）
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 52
                    radius: 14
                    color: Qt.rgba(0.051, 0.078, 0.102, 0.085)
                    border.width: 1
                    border.color: Qt.rgba(1, 1, 1, 0.10)

                    Rectangle {
                        anchors { top: parent.top; left: parent.left; right: parent.right }
                        anchors.margins: 1
                        height: 1
                        color: Qt.rgba(1, 1, 1, 0.15)
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 16
                        anchors.rightMargin: 12
                        spacing: 12

                        Text {
                            text: "Rain Glass Quant Terminal"
                            color: "#EEF3F6"
                            font.pixelSize: 15
                            font.weight: Font.DemiBold
                        }

                        Item { Layout.fillWidth: true }

                        Text {
                            text: "2026-08-30 · CN/US/CRYPTO"
                            color: "#9AA6B2"
                            font.pixelSize: 11
                        }

                        ComboBox {
                            id: qualityCombo
                            model: ["high", "balanced", "low"]
                            currentIndex: 1
                            font.pixelSize: 11
                            implicitHeight: 28
                            implicitWidth: 108
                            background: Rectangle {
                                radius: 9
                                color: Qt.rgba(1, 1, 1, 0.05)
                                border.width: 1
                                border.color: Qt.rgba(1, 1, 1, 0.12)
                            }
                            onActivated: root.quality = currentText
                        }
                    }
                }

                // 指标卡片区（4 张，Level B 玻璃）
                GridLayout {
                    Layout.fillWidth: true
                    columns: 4
                    columnSpacing: 12
                    rowSpacing: 12

                    MetricCard { Layout.fillWidth: true; label: "今日机会"; value: "2"; hint: "BUY CANDIDATE"; tone: "positive"; accent: "#2BD576" }
                    MetricCard { Layout.fillWidth: true; label: "数据健康"; value: "98%"; hint: "CN 完整 · US 延迟"; tone: "info"; accent: "#5B9FD6" }
                    MetricCard { Layout.fillWidth: true; label: "市场状态"; value: "Neutral"; hint: "Risk-Off 观察中"; tone: "warning"; accent: "#E8B45A" }
                    MetricCard { Layout.fillWidth: true; label: "信号验证"; value: "—"; hint: "样本积累中"; tone: "neutral"; accent: "#8A93A6" }
                }

                // 图表占位（Level C：克制玻璃，可读性优先）
                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: 16
                    color: Qt.rgba(0.051, 0.078, 0.102, 0.035)
                    border.width: 1
                    border.color: Qt.rgba(1, 1, 1, 0.08)

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 8

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10

                            Text {
                                text: "600332.SS 白云山 · 5 日"
                                color: "#EEF3F6"
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                            }
                            Text {
                                text: "20.46  -0.02%"
                                color: "#E06C6C"
                                font.pixelSize: 12
                            }
                            Item { Layout.fillWidth: true }
                            StatusBadge { text: "BREADTH_CONFIRM"; tone: "idle" }
                        }

                        // 图表占位：假 K 线烛台（数据可视化占位，PHASE 3+ 嵌真实图表）
                        Item {
                            Layout.fillWidth: true
                            Layout.fillHeight: true

                            Canvas {
                                id: chartPlaceholder
                                anchors.fill: parent
                                onPaint: {
                                    const ctx = getContext("2d")
                                    ctx.reset()
                                    // 假 K 线：几何生成，涨红跌绿（本地配色）
                                    const w = width, h = height
                                    const n = 42
                                    const cw = w / n
                                    let price = 100
                                    let seed = 7
                                    const rand = () => {
                                        seed = (seed * 16807) % 2147483647
                                        return seed / 2147483647
                                    }
                                    for (let i = 0; i < n; ++i) {
                                        const open = price
                                        const change = (rand() - 0.48) * 3.2
                                        const close = open + change
                                        const high = Math.max(open, close) + rand() * 1.2
                                        const low = Math.min(open, close) - rand() * 1.2
                                        price = close
                                        const x = i * cw + cw * 0.5
                                        const scale = h / 18
                                        const yOpen = h - (open - 88) * scale
                                        const yClose = h - (close - 88) * scale
                                        const yHigh = h - (high - 88) * scale
                                        const yLow = h - (low - 88) * scale
                                        const up = close >= open
                                        ctx.strokeStyle = up ? "#E05C5C" : "#2BD58F"
                                        ctx.fillStyle = up ? "#E05C5C" : "#2BD58F"
                                        // 影线
                                        ctx.beginPath()
                                        ctx.moveTo(x, yHigh)
                                        ctx.lineTo(x, yLow)
                                        ctx.stroke()
                                        // 实体
                                        const top = Math.min(yOpen, yClose)
                                        const bodyH = Math.max(1.5, Math.abs(yClose - yOpen))
                                        ctx.fillRect(x - cw * 0.28, top, cw * 0.56, bodyH)
                                    }
                                }
                                Component.onCompleted: requestPaint()
                                onWidthChanged: requestPaint()
                                onHeightChanged: requestPaint()
                            }
                        }

                        Text {
                            text: "图表占位 · PHASE 3 将嵌入真实 matplotlib FigureCanvas"
                            color: "#4C5560"
                            font.pixelSize: 10
                        }
                    }
                }
            }
        }
    }

    // ---- diagnostics overlay（仅 dev 模式，MASTER_PROMPT §14）-----------
    Rectangle {
        id: diagnostics
        visible: bridge !== null && (bridge.diagnosticsVisible || !root.gpuActive)
        anchors { top: parent.top; right: parent.right }
        anchors.margins: 12
        width: diagColumn.implicitWidth + 24
        height: diagColumn.implicitHeight + 20
        radius: 10
        color: Qt.rgba(0.02, 0.03, 0.045, 0.88)
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, 0.12)

        Column {
            id: diagColumn
            anchors.centerIn: parent
            spacing: 3

            Text { color: "#6CB2FF"; font.pixelSize: 10; text: "RainGlass diagnostics" }
            Text { color: "#9AA6B2"; font.pixelSize: 10; text: bridge !== null ? ("Qt " + bridge.qtVersion) : "Qt ?" }
            Text { color: "#9AA6B2"; font.pixelSize: 10; text: "RHI backend: " + root.rhiBackend }
            Text { color: "#9AA6B2"; font.pixelSize: 10; text: "quality: " + root.quality }
            Text { color: root.gpuActive ? "#2BD576" : "#E06C6C"; font.pixelSize: 10
                   text: "gpu: " + (root.gpuActive ? "active" : "software fallback") }
            Text { color: "#9AA6B2"; font.pixelSize: 10; text: "fps: " + (bridge ? bridge.fps.toFixed(1) : "?") }
            Text { color: "#9AA6B2"; font.pixelSize: 10
                   text: "frame: " + (bridge ? bridge.frameMs.toFixed(1) + " ms" : "?") }
            Text { color: "#9AA6B2"; font.pixelSize: 10
                   text: "shader: " + (rainEffect.status === 0 ? "uncompiled" : rainEffect.status === 1 ? "compiled" : "error") }
        }
    }

    // ---- 鼠标视差采集（平滑插值，最大 4px）--------------------------------
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
        onPositionChanged: (mouse) => {
            root.mouseX = mouse.x / root.width
            root.mouseY = mouse.y / root.height
        }
    }

    // Bridge 由 demo_launcher 注入：提供 diagnostics 状态与 FPS 采样
    property QtObject bridge: null

    // 外层 Window 的引用（DemoWindow 注入），grabSnapshot 用它抓全窗
    property var hostWindow: null

    // 暴露实际窗口给 Python 侧（QML attached Window.window 解析）
    function grabSnapshot(path) {
        // QQuickItem.grabToImage：异步抓本 item + children
        root.grabToImage(function(result) {
            result.saveToFile(path)
        }, Qt.size(root.width, root.height))
    }
}
