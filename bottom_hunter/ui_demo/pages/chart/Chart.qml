import QtQuick
import QtQuick.Controls.Basic
import "../../primitives"

GlassSurface {
    id: root
    objectName: "chartPage"
    tintAlpha: 0.42
    surfaceRadius: 24

    readonly property var vm: (typeof chartVm !== "undefined") ? chartVm : null
    property string overlayIndicator: "MA"
    property string panelIndicator: "MACD"
    property int visibleCount: 80
    property string drawingMode: ""
    property var annotations: []
    property var draftPoint: null

    Component.onCompleted: {
        if (vm !== null) vm.activate()
    }

    Connections {
        target: root.vm
        function onChanged() {
            root.visibleCount = Math.min(Math.max(30, root.visibleCount), Math.max(30, root.vm.barCount))
            chartCanvas.requestPaint()
        }
    }

    Timer {
        interval: root.vm !== null && root.vm.selectedMarket === "CRYPTO" ? 5000 : 15000
        repeat: true
        running: root.visible && root.vm !== null && root.vm.lifecycle === "READY"
        onTriggered: root.vm.refresh()
    }

    component ChoiceBox: ComboBox {
        id: combo
        implicitHeight: 38
        font.family: "Noto Sans CJK SC"
        font.pixelSize: 13
        leftPadding: 13
        rightPadding: 30

        contentItem: Text {
            text: combo.displayText
            color: "#152330"
            font: combo.font
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        indicator: Text {
            x: combo.width - width - 11
            anchors.verticalCenter: parent.verticalCenter
            text: "⌄"
            color: "#465D70"
            font.pixelSize: 15
            font.weight: Font.DemiBold
        }
        background: Rectangle {
            radius: 11
            color: Qt.rgba(0.94, 0.98, 1.0, combo.hovered ? 0.38 : 0.25)
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, combo.activeFocus ? 0.86 : 0.58)
        }
        popup: Popup {
            y: combo.height + 6
            width: combo.width
            implicitHeight: Math.min(contentItem.implicitHeight + 10, 330)
            padding: 5
            background: Rectangle {
                radius: 13
                color: "#EAF2F7"
                border.color: "#FFFFFF"
                border.width: 1
            }
            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: combo.popup.visible ? combo.delegateModel : null
                currentIndex: combo.highlightedIndex
                ScrollIndicator.vertical: ScrollIndicator { }
            }
        }
        delegate: ItemDelegate {
            width: combo.width - 10
            height: 38
            highlighted: combo.highlightedIndex === index
            contentItem: Text {
                text: combo.textRole ? model[combo.textRole] : modelData
                color: "#152330"
                font.family: "Noto Sans CJK SC"
                font.pixelSize: 13
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
            background: Rectangle {
                radius: 9
                color: parent.highlighted ? Qt.rgba(0.10, 0.58, 0.38, 0.14) : "transparent"
            }
        }
    }

    Column {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 10

        Row {
            width: parent.width
            height: 34
            spacing: 12

            GlassText { text: "K线分析"; tone: "primary"; sizeHint: 23 }
            GlassText {
                anchors.verticalCenter: parent.verticalCenter
                text: root.vm !== null && root.vm.barCount > 0 ? root.vm.barCount + " 根·" + root.vm.provider : ""
                tone: "muted"
                sizeHint: 12
            }
            Item { width: 1; height: 1 }
            GlassText {
                anchors.verticalCenter: parent.verticalCenter
                text: root.vm === null ? "未连接" : root.vm.lifecycle === "LOADING" ? "● 正在加载"
                      : root.vm.lifecycle === "READY" ? "● 自动更新"
                      : root.vm.lifecycle === "ERROR" ? "● 行情异常" : "● 等待数据"
                color: root.vm !== null && root.vm.lifecycle === "READY" ? "#128653" : "#61778B"
                font.pixelSize: 12
                font.family: "Noto Sans CJK SC"
                font.weight: Font.DemiBold
            }
        }

        GlassCard {
            width: parent.width
            height: 62
            interactive: false

            Row {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 9

                ChoiceBox {
                    width: Math.max(250, parent.width * 0.29)
                    model: root.vm !== null ? root.vm.assets : []
                    textRole: "label"
                    currentIndex: root.vm !== null ? root.vm.selectedIndex : -1
                    onActivated: function(index) {
                        root.annotations = []
                        root.draftPoint = null
                        if (root.vm !== null) root.vm.selectAsset(index)
                    }
                }

                Repeater {
                    model: [
                        { key: "1m", label: "1分" }, { key: "5m", label: "5分" },
                        { key: "15m", label: "15分" }, { key: "60m", label: "60分" },
                        { key: "4h", label: "4时" }, { key: "1d", label: "日" },
                        { key: "1w", label: "周" }, { key: "1M", label: "月" }
                    ]
                    delegate: GlassSurface {
                        width: 48
                        height: 38
                        reactive: true
                        tintAlpha: root.vm !== null && root.vm.timeframe === modelData.key ? 0.18 : 0.06
                        surfaceRadius: 11
                        GlassText {
                            anchors.centerIn: parent
                            text: modelData.label
                            tone: root.vm !== null && root.vm.timeframe === modelData.key ? "primary" : "secondary"
                            sizeHint: 12
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                root.annotations = []
                                root.draftPoint = null
                                if (root.vm !== null) root.vm.selectTimeframe(modelData.key)
                            }
                        }
                    }
                }

                GlassSurface {
                    width: 82
                    height: 38
                    reactive: true
                    tintAlpha: 0.10
                    surfaceRadius: 11
                    GlassText { anchors.centerIn: parent; text: "刷新"; tone: "primary"; sizeHint: 12 }
                    MouseArea {
                        anchors.fill: parent
                        enabled: root.vm !== null && root.vm.lifecycle !== "LOADING"
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.vm.refresh()
                    }
                }
            }
        }

        GlassCard {
            width: parent.width
            height: 54
            interactive: false

            Row {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 8

                GlassText { anchors.verticalCenter: parent.verticalCenter; text: "主图"; tone: "muted"; sizeHint: 12 }
                ChoiceBox {
                    width: 112
                    model: ["无", "MA", "BOLL"]
                    currentIndex: 1
                    onActivated: { root.overlayIndicator = currentText; chartCanvas.requestPaint() }
                }
                GlassText { anchors.verticalCenter: parent.verticalCenter; text: "副图"; tone: "muted"; sizeHint: 12 }
                ChoiceBox {
                    width: 118
                    model: ["无", "MACD", "RSI", "KDJ"]
                    currentIndex: 1
                    onActivated: { root.panelIndicator = currentText; chartCanvas.requestPaint() }
                }

                Item { width: 10; height: 1 }

                Repeater {
                    model: [
                        { mode: "trend", label: "趋势线" },
                        { mode: "horizontal", label: "水平线" }
                    ]
                    delegate: GlassSurface {
                        width: 82
                        height: 36
                        reactive: true
                        tintAlpha: root.drawingMode === modelData.mode ? 0.17 : 0.055
                        surfaceRadius: 10
                        GlassText { anchors.centerIn: parent; text: modelData.label; tone: "primary"; sizeHint: 12 }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.CrossCursor
                            onClicked: {
                                root.drawingMode = root.drawingMode === modelData.mode ? "" : modelData.mode
                                root.draftPoint = null
                            }
                        }
                    }
                }

                GlassSurface {
                    width: 62; height: 36; reactive: root.annotations.length > 0
                    tintAlpha: 0.05; surfaceRadius: 10
                    GlassText { anchors.centerIn: parent; text: "撤销"; tone: "secondary"; sizeHint: 12 }
                    MouseArea {
                        anchors.fill: parent; enabled: root.annotations.length > 0
                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: {
                            let values = root.annotations.slice(); values.pop(); root.annotations = values
                            chartCanvas.requestPaint()
                        }
                    }
                }
                GlassSurface {
                    width: 72; height: 36; reactive: root.annotations.length > 0
                    tintAlpha: 0.05; surfaceRadius: 10
                    GlassText { anchors.centerIn: parent; text: "清空"; tone: "secondary"; sizeHint: 12 }
                    MouseArea {
                        anchors.fill: parent; enabled: root.annotations.length > 0
                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: { root.annotations = []; root.draftPoint = null; chartCanvas.requestPaint() }
                    }
                }
                GlassText {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Ctrl + 滚轮调整画面 K 线数量"
                    tone: "muted"
                    sizeHint: 11
                }
            }
        }

        GlassCard {
            id: chartCard
            width: parent.width
            height: Math.max(430, root.height - 20 * 2 - 34 - 62 - 54 - 30 - 4 * parent.spacing)
            interactive: false

            Item {
                id: chartHost
                anchors.fill: parent
                anchors.margins: 10
                anchors.bottomMargin: 34

                Canvas {
                    id: chartCanvas
                    anchors.fill: parent
                    antialiasing: true
                    renderStrategy: Canvas.Cooperative

                    property real plotLeft: 58
                    property real plotRight: width - 18
                    property real plotTop: 18
                    property real mainBottom: root.panelIndicator === "无" ? height * 0.74 : height * 0.61
                    property real volumeTop: mainBottom + 10
                    property real volumeBottom: root.panelIndicator === "无" ? height - 28 : height * 0.73
                    property real panelTop: height * 0.77
                    property real panelBottom: height - 28
                    property real minPrice: 0
                    property real maxPrice: 1
                    property int firstBar: 0
                    property int shownBars: 0
                    property real crossX: -1
                    property real crossY: -1

                    function finite(value) { return value !== null && value !== undefined && isFinite(Number(value)) }
                    function barX(index) {
                        return plotLeft + (index - firstBar + 0.5) * (plotRight - plotLeft) / Math.max(1, shownBars)
                    }
                    function priceY(value) {
                        return mainBottom - (Number(value) - minPrice) / Math.max(0.0000001, maxPrice - minPrice) * (mainBottom - plotTop)
                    }
                    function dataPointAt(px, py) {
                        const index = firstBar + (px - plotLeft) / Math.max(1, plotRight - plotLeft) * shownBars - 0.5
                        const price = maxPrice - (py - plotTop) / Math.max(1, mainBottom - plotTop) * (maxPrice - minPrice)
                        return { x: index, price: price }
                    }
                    function lineSeries(ctx, values, key, color, low, high, top, bottom) {
                        ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = 1.35
                        let started = false
                        for (let i = 0; i < values.length; ++i) {
                            const value = values[i][key]
                            if (!finite(value)) { started = false; continue }
                            const x = barX(firstBar + i)
                            const y = bottom - (Number(value) - low) / Math.max(0.0000001, high - low) * (bottom - top)
                            if (!started) { ctx.moveTo(x, y); started = true } else ctx.lineTo(x, y)
                        }
                        ctx.stroke()
                    }

                    onPaint: {
                        const ctx = getContext("2d")
                        ctx.reset()
                        ctx.fillStyle = Qt.rgba(0.96, 0.985, 1.0, 0.16)
                        ctx.fillRect(0, 0, width, height)
                        const all = root.vm !== null ? root.vm.bars : []
                        shownBars = Math.min(all.length, Math.max(10, root.visibleCount))
                        firstBar = Math.max(0, all.length - shownBars)
                        const values = all.slice(firstBar)
                        if (!values.length) return

                        let low = Number(values[0].low), high = Number(values[0].high), maxVolume = 1
                        for (let i = 0; i < values.length; ++i) {
                            low = Math.min(low, Number(values[i].low)); high = Math.max(high, Number(values[i].high))
                            maxVolume = Math.max(maxVolume, Number(values[i].volume || 0))
                        }
                        const pad = Math.max((high - low) * 0.06, Math.abs(high) * 0.001)
                        minPrice = low - pad; maxPrice = high + pad

                        ctx.strokeStyle = Qt.rgba(0.25, 0.38, 0.48, 0.18); ctx.lineWidth = 1
                        ctx.fillStyle = "#61778B"; ctx.font = "11px 'Noto Sans CJK SC'"
                        for (let grid = 0; grid <= 4; ++grid) {
                            const y = plotTop + (mainBottom - plotTop) * grid / 4
                            ctx.beginPath(); ctx.moveTo(plotLeft, y); ctx.lineTo(plotRight, y); ctx.stroke()
                            const label = (maxPrice - (maxPrice - minPrice) * grid / 4).toFixed(2)
                            ctx.fillText(label, 4, y + 4)
                        }

                        const step = (plotRight - plotLeft) / Math.max(1, shownBars)
                        const candleWidth = Math.max(2, Math.min(11, step * 0.62))
                        for (let j = 0; j < values.length; ++j) {
                            const bar = values[j], x = barX(firstBar + j)
                            const openY = priceY(bar.open), closeY = priceY(bar.close)
                            const up = Number(bar.close) >= Number(bar.open)
                            const color = up ? "#E25555" : "#149A68"
                            ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1
                            ctx.beginPath(); ctx.moveTo(x, priceY(bar.high)); ctx.lineTo(x, priceY(bar.low)); ctx.stroke()
                            ctx.fillRect(x - candleWidth / 2, Math.min(openY, closeY), candleWidth, Math.max(1.5, Math.abs(closeY - openY)))
                            const volumeHeight = Number(bar.volume || 0) / maxVolume * (volumeBottom - volumeTop)
                            ctx.globalAlpha = 0.46
                            ctx.fillRect(x - candleWidth / 2, volumeBottom - volumeHeight, candleWidth, volumeHeight)
                            ctx.globalAlpha = 1
                        }

                        if (root.overlayIndicator === "MA") {
                            lineSeries(ctx, values, "ma5", "#E49A2F", minPrice, maxPrice, plotTop, mainBottom)
                            lineSeries(ctx, values, "ma10", "#2D84CC", minPrice, maxPrice, plotTop, mainBottom)
                            lineSeries(ctx, values, "ma20", "#8B62C9", minPrice, maxPrice, plotTop, mainBottom)
                            lineSeries(ctx, values, "ma60", "#B34D7B", minPrice, maxPrice, plotTop, mainBottom)
                        } else if (root.overlayIndicator === "BOLL") {
                            lineSeries(ctx, values, "bollUpper", "#8B62C9", minPrice, maxPrice, plotTop, mainBottom)
                            lineSeries(ctx, values, "bollMid", "#2D84CC", minPrice, maxPrice, plotTop, mainBottom)
                            lineSeries(ctx, values, "bollLower", "#8B62C9", minPrice, maxPrice, plotTop, mainBottom)
                        }

                        if (root.panelIndicator !== "无") {
                            let keys = root.panelIndicator === "MACD" ? ["macdDif", "macdDea", "macdHist"]
                                     : root.panelIndicator === "RSI" ? ["rsi14"] : ["kdjK", "kdjD", "kdjJ"]
                            let panelLow = root.panelIndicator === "RSI" || root.panelIndicator === "KDJ" ? 0 : 0
                            let panelHigh = root.panelIndicator === "RSI" || root.panelIndicator === "KDJ" ? 100 : 0
                            if (root.panelIndicator === "MACD") {
                                for (let m = 0; m < values.length; ++m)
                                    for (let n = 0; n < keys.length; ++n) if (finite(values[m][keys[n]])) {
                                        panelLow = Math.min(panelLow, Number(values[m][keys[n]])); panelHigh = Math.max(panelHigh, Number(values[m][keys[n]]))
                                    }
                            }
                            if (root.panelIndicator === "MACD") {
                                const zeroY = panelBottom - (0 - panelLow) / Math.max(0.000001, panelHigh - panelLow) * (panelBottom - panelTop)
                                for (let h = 0; h < values.length; ++h) if (finite(values[h].macdHist)) {
                                    const histY = panelBottom - (Number(values[h].macdHist) - panelLow) / Math.max(0.000001, panelHigh - panelLow) * (panelBottom - panelTop)
                                    ctx.fillStyle = Number(values[h].macdHist) >= 0 ? Qt.rgba(0.89, 0.33, 0.33, 0.55) : Qt.rgba(0.08, 0.60, 0.40, 0.55)
                                    ctx.fillRect(barX(firstBar + h) - Math.max(1, candleWidth * 0.35), Math.min(zeroY, histY), Math.max(2, candleWidth * 0.7), Math.max(1, Math.abs(histY - zeroY)))
                                }
                                lineSeries(ctx, values, "macdDif", "#D88324", panelLow, panelHigh, panelTop, panelBottom)
                                lineSeries(ctx, values, "macdDea", "#357BB7", panelLow, panelHigh, panelTop, panelBottom)
                            } else if (root.panelIndicator === "RSI") {
                                lineSeries(ctx, values, "rsi14", "#8B62C9", 0, 100, panelTop, panelBottom)
                            } else {
                                lineSeries(ctx, values, "kdjK", "#D88324", 0, 100, panelTop, panelBottom)
                                lineSeries(ctx, values, "kdjD", "#357BB7", 0, 100, panelTop, panelBottom)
                                lineSeries(ctx, values, "kdjJ", "#9A4C88", 0, 100, panelTop, panelBottom)
                            }
                        }

                        ctx.strokeStyle = "#195B88"; ctx.lineWidth = 1.5
                        for (let a = 0; a < root.annotations.length; ++a) {
                            const item = root.annotations[a]
                            if (item.type === "horizontal") {
                                const y = priceY(item.price)
                                ctx.beginPath(); ctx.moveTo(plotLeft, y); ctx.lineTo(plotRight, y); ctx.stroke()
                            } else {
                                ctx.beginPath(); ctx.moveTo(barX(item.x1), priceY(item.y1)); ctx.lineTo(barX(item.x2), priceY(item.y2)); ctx.stroke()
                            }
                        }
                        if (crossX >= plotLeft && crossX <= plotRight && crossY >= plotTop && crossY <= mainBottom) {
                            ctx.strokeStyle = Qt.rgba(0.15, 0.28, 0.38, 0.40); ctx.lineWidth = 1
                            ctx.beginPath(); ctx.moveTo(crossX, plotTop); ctx.lineTo(crossX, volumeBottom); ctx.stroke()
                            ctx.beginPath(); ctx.moveTo(plotLeft, crossY); ctx.lineTo(plotRight, crossY); ctx.stroke()
                        }
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: root.drawingMode === "" ? Qt.ArrowCursor : Qt.CrossCursor
                    onPositionChanged: function(mouse) {
                        chartCanvas.crossX = mouse.x; chartCanvas.crossY = mouse.y; chartCanvas.requestPaint()
                    }
                    onExited: { chartCanvas.crossX = -1; chartCanvas.crossY = -1; chartCanvas.requestPaint() }
                    onWheel: function(wheel) {
                        if (wheel.modifiers & Qt.ControlModifier) {
                            const direction = wheel.angleDelta.y > 0 ? -10 : 10
                            root.visibleCount = Math.max(20, Math.min(root.vm !== null ? Math.max(20, root.vm.barCount) : 500, root.visibleCount + direction))
                            chartCanvas.requestPaint(); wheel.accepted = true
                        }
                    }
                    onClicked: function(mouse) {
                        if (root.drawingMode === "" || mouse.x < chartCanvas.plotLeft || mouse.x > chartCanvas.plotRight
                                || mouse.y < chartCanvas.plotTop || mouse.y > chartCanvas.mainBottom) return
                        const point = chartCanvas.dataPointAt(mouse.x, mouse.y)
                        let values = root.annotations.slice()
                        if (root.drawingMode === "horizontal") {
                            values.push({ type: "horizontal", price: point.price }); root.annotations = values
                        } else if (root.draftPoint === null) {
                            root.draftPoint = point
                        } else {
                            values.push({ type: "trend", x1: root.draftPoint.x, y1: root.draftPoint.price, x2: point.x, y2: point.price })
                            root.annotations = values; root.draftPoint = null
                        }
                        chartCanvas.requestPaint()
                    }
                }
            }

            Row {
                anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                anchors.leftMargin: 16; anchors.rightMargin: 16; anchors.bottomMargin: 10
                height: 20
                spacing: 12
                GlassText {
                    width: parent.width * 0.65
                    text: root.vm === null ? "K线 ViewModel 未连接"
                          : root.vm.lifecycle === "ERROR" ? "行情加载失败：" + root.vm.error
                          : root.vm.lifecycle === "EMPTY" ? "自选为空，请先在导入页添加标的"
                          : root.vm.lifecycle === "LOADING" ? "正在后台加载行情…"
                          : root.vm.note || "行情仅供研究，可能存在延迟"
                    elide: Text.ElideRight
                    tone: root.vm !== null && root.vm.lifecycle === "ERROR" ? "secondary" : "muted"
                    sizeHint: 11
                }
                GlassText {
                    width: parent.width - x
                    horizontalAlignment: Text.AlignRight
                    text: root.vm !== null && root.vm.updatedAt !== "" ? "更新 · " + root.vm.updatedAt : ""
                    elide: Text.ElideLeft
                    tone: "muted"
                    sizeHint: 11
                }
            }

            Rectangle {
                visible: root.vm !== null && root.vm.lifecycle === "LOADING"
                anchors.centerIn: parent
                width: 176; height: 48; radius: 16
                color: Qt.rgba(0.92, 0.97, 1.0, 0.82)
                border.color: Qt.rgba(1, 1, 1, 0.92)
                GlassText { anchors.centerIn: parent; text: "正在读取 K 线…"; tone: "primary"; sizeHint: 13 }
            }
        }
    }
}
