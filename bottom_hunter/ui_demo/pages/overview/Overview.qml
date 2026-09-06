import QtQuick
import QtQuick.Controls.Basic
import "../../primitives"

GlassSurface {
    id: root
    objectName: "overviewPage"
    tintAlpha: 0.42
    surfaceRadius: GlassTokens.pageRadius
    edgeContrast: GlassTokens.structuralEdgeContrast
    depthStrength: GlassTokens.structuralDepthStrength

    readonly property var vm: (typeof overviewState !== "undefined") ? overviewState : null
    readonly property var tasks: (typeof taskVm !== "undefined") ? taskVm : null
    readonly property bool ready: vm !== null && (vm.lifecycle === "READY" || vm.lifecycle === "STALE")

    function oneYearAgo() {
        const value = new Date()
        value.setFullYear(value.getFullYear() - 1)
        return Qt.formatDate(value, "yyyy-MM-dd")
    }

    Component.onCompleted: {
        if (vm !== null && vm.lifecycle === "INIT"
                && typeof overviewRefreshController !== "undefined"
                && overviewRefreshController !== null)
            overviewRefreshController.requestRefresh()
    }

    Column {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 14

        GlassText { text: "总览"; tone: "primary"; sizeHint: 23 }
        GlassText {
            text: root.vm === null ? "页面数据未注入"
                  : root.vm.lifecycle === "LOADING" ? "正在读取最新报告…"
                  : root.vm.lifecycle === "ERROR" ? root.vm.lastError
                  : root.vm.lifecycle === "STALE" ? "展示上次成功数据 · " + root.vm.lastError
                  : "最近更新 · " + root.vm.lastSuccessfulUpdate
            tone: root.vm !== null && root.vm.lifecycle === "ERROR" ? "secondary" : "muted"
            sizeHint: 13
        }

        GlassCard {
            visible: !root.ready
            width: parent.width
            height: 84
            interactive: false
            GlassText {
                anchors.centerIn: parent
                text: root.vm === null ? "总览 ViewModel 未连接"
                      : root.vm.lifecycle === "ERROR" ? "暂时无法读取总览快照"
                      : "正在准备总览数据…"
                tone: "muted"
                sizeHint: 14
            }
        }

        Grid {
            visible: root.ready
            width: parent.width
            columns: 3
            spacing: 12

            Repeater {
                model: root.vm === null ? [] : [
                    { label: "超跌机会", value: root.vm.opportunityCount, detail: root.vm.opportunityHint, tint: "#FFD9E8" },
                    { label: "市场状态", value: root.vm.marketStatus, detail: root.vm.marketStatusDetail, tint: "#CFE8FF" },
                    { label: "扫描状态", value: root.vm.scanStatus, detail: root.vm.scanStatusDetail, tint: "#CFF5E6" },
                    { label: "数据健康", value: root.vm.dataHealthText, detail: root.vm.dataHealthLevel, tint: "#FFE6C7" },
                    { label: "滚动验证", value: root.vm.validation, detail: root.vm.validationHint, tint: "#D9E0FF" },
                    { label: "模拟净值", value: root.vm.portfolioValue, detail: root.vm.portfolioHint, tint: "#E7D7FF" }
                ]

                delegate: GlassCard {
                    objectName: "overviewMetricCard" + index
                    appearanceKey: "overview.metric." + index
                    appearanceLabel: modelData.label
                    width: (root.width - 64) / 3
                    height: 132
                    interactive: false
                    surfaceRadius: Math.min(GlassTokens.cardRadius,
                                            GlassTokens.capsuleRadius(height))
                    tintAlpha: 0.30
                    edgeContrast: 0.48
                    depthStrength: 1.18
                    shadowOpacity: 0.14
                    accentTint: modelData.tint
                    accentStrength: 0.20
                    Column {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 8
                        GlassText { text: modelData.label; tone: "muted"; sizeHint: 12 }
                        GlassText {
                            width: parent.width
                            text: modelData.value
                            elide: Text.ElideRight
                            tone: "primary"
                            sizeHint: 20
                        }
                        GlassText {
                            width: parent.width
                            text: modelData.detail
                            elide: Text.ElideRight
                            tone: "secondary"
                            sizeHint: 12
                        }
                    }
                }
            }
        }

        Row {
            width: parent.width
            height: 116
            spacing: 14

            GlassCard {
                width: (parent.width - parent.spacing) / 2
                height: parent.height
                interactive: false
                accentTint: "#D6F2EA"
                accentStrength: 0.16
                Column {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 9
                    GlassText { text: "每日扫描"; tone: "primary"; sizeHint: 16 }
                    Row {
                        width: parent.width
                        spacing: 8
                        TextField {
                            id: scanDate
                            width: parent.width - 120
                            height: 38
                            placeholderText: "留空=最新交易日，或 YYYY-MM-DD"
                            color: GlassTokens.textPrimary
                            placeholderTextColor: GlassTokens.textMuted
                            leftPadding: 13
                            background: GlassSurface { tintAlpha: 0.16; surfaceRadius: GlassTokens.capsuleRadius(height) }
                        }
                        GlassButton {
                            width: 108
                            height: 38
                            label: root.tasks !== null && root.tasks.kind === "scan" && root.tasks.busy
                                   ? "扫描中…" : "开始扫描"
                            active: root.tasks !== null && root.tasks.kind === "scan" && root.tasks.busy
                            enabled: root.tasks !== null && !root.tasks.busy
                            opacity: enabled ? 1.0 : 0.55
                            onClicked: root.tasks.startScan(scanDate.text, false, 4)
                        }
                    }
                }
            }

            GlassCard {
                width: parent.width - x
                height: parent.height
                interactive: false
                accentTint: "#E7DCFF"
                accentStrength: 0.16
                Column {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 9
                    GlassText { text: "历史回测"; tone: "primary"; sizeHint: 16 }
                    Row {
                        width: parent.width
                        spacing: 7
                        TextField {
                            id: backtestStart
                            width: 116
                            height: 38
                            text: root.oneYearAgo()
                            color: GlassTokens.textPrimary
                            horizontalAlignment: TextInput.AlignHCenter
                            background: GlassSurface { tintAlpha: 0.16; surfaceRadius: GlassTokens.capsuleRadius(height) }
                        }
                        GlassText { text: "至"; tone: "muted"; sizeHint: 12; anchors.verticalCenter: parent.verticalCenter }
                        TextField {
                            id: backtestEnd
                            width: 116
                            height: 38
                            text: Qt.formatDate(new Date(), "yyyy-MM-dd")
                            color: GlassTokens.textPrimary
                            horizontalAlignment: TextInput.AlignHCenter
                            background: GlassSurface { tintAlpha: 0.16; surfaceRadius: GlassTokens.capsuleRadius(height) }
                        }
                        GlassButton {
                            width: parent.width - x
                            height: 38
                            label: root.tasks !== null && root.tasks.kind === "backtest" && root.tasks.busy
                                   ? "回测中…" : "运行回测"
                            active: root.tasks !== null && root.tasks.kind === "backtest" && root.tasks.busy
                            enabled: root.tasks !== null && !root.tasks.busy
                            opacity: enabled ? 1.0 : 0.55
                            onClicked: root.tasks.startBacktest(backtestStart.text, backtestEnd.text, false, 4)
                        }
                    }
                }
            }
        }

        GlassCard {
            width: parent.width
            height: parent.height - y
            interactive: false
            accentTint: root.tasks !== null && root.tasks.state === "ERROR" ? "#FFD8CF" : "#DCEAF7"
            accentStrength: 0.12
            Column {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 8
                Row {
                    width: parent.width
                    spacing: 10
                    GlassText {
                        width: parent.width - 108
                        text: "任务状态 · " + (root.tasks !== null ? root.tasks.detail : "任务控制器未连接")
                        elide: Text.ElideRight
                        tone: "primary"
                        sizeHint: 14
                    }
                    GlassButton {
                        width: 96
                        height: 34
                        visible: root.tasks !== null && root.tasks.busy
                        label: "停止任务"
                        onClicked: root.tasks.stop()
                    }
                }
                Flickable {
                    width: parent.width
                    height: parent.height - y
                    contentWidth: width
                    contentHeight: Math.max(height, taskLog.implicitHeight)
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    GlassText {
                        id: taskLog
                        width: parent.width
                        text: root.tasks !== null && root.tasks.log
                              ? root.tasks.log : "扫描和回测输出会实时显示在这里。"
                        wrapMode: Text.Wrap
                        tone: "muted"
                        sizeHint: 11
                    }
                }
            }
        }
    }
}
