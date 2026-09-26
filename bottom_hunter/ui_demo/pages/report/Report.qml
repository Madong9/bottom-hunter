import QtQuick
import QtQuick.Controls.Basic
import "../../primitives"

GlassSurface {
    id: root
    objectName: "reportPage"
    tintAlpha: 0.42
    surfaceRadius: GlassTokens.pageRadius
    edgeContrast: GlassTokens.structuralEdgeContrast
    depthStrength: GlassTokens.structuralDepthStrength

    readonly property var vm: (typeof reportVm !== "undefined") ? reportVm : null
    readonly property var selectedSignal: vm !== null && vm.hasSelectedSignal
                                          ? vm.selectedSignal : ({})
    property bool showFullReport: false

    function signalColor(value) {
        const level = String(value || "").toUpperCase()
        if (level.indexOf("FAILED") >= 0 || level.indexOf("SELL") >= 0) return "#923D52"
        if (level.indexOf("BUY") >= 0 || level.indexOf("REVERSAL") >= 0) return "#08704D"
        if (level.indexOf("WATCH") >= 0) return "#80520A"
        return GlassTokens.textSecondary
    }

    Component.onCompleted: {
        if (vm !== null && vm.lifecycle === "INIT") vm.refresh()
    }

    Column {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 14

        GlassText { text: "报告"; tone: "primary"; sizeHint: 23 }
        Row {
            width: parent.width
            spacing: 8
            GlassText {
                width: parent.width - 250
                text: root.vm !== null && root.vm.reportDate !== "--"
                      ? "日报 " + root.vm.reportDate + "  ·  " + root.vm.marketText
                      : "最新生成报告"
                elide: Text.ElideRight
                tone: "muted"
                sizeHint: 13
            }
            GlassButton {
                width: 72
                height: 34
                label: root.showFullReport ? "摘要" : "全文"
                active: root.showFullReport
                onClicked: root.showFullReport = !root.showFullReport
            }
            GlassButton {
                width: 72
                height: 34
                label: "刷新"
                onClicked: if (root.vm !== null) root.vm.refresh()
            }
        }

        GlassCard {
            visible: root.vm === null || ["INIT", "LOADING", "EMPTY", "ERROR"].indexOf(root.vm.lifecycle) >= 0
            width: parent.width
            height: 82
            interactive: false
            GlassText {
                anchors.centerIn: parent
                text: root.vm === null ? "报告 ViewModel 未连接"
                      : root.vm.lifecycle === "ERROR" ? root.vm.error
                      : root.vm.lifecycle === "EMPTY" ? "尚无可展示的日报快照"
                      : "正在读取最新报告…"
                tone: root.vm !== null && root.vm.lifecycle === "ERROR" ? "secondary" : "muted"
                sizeHint: 14
            }
        }

        Row {
            visible: root.vm !== null && root.vm.lifecycle === "READY"
            width: parent.width
            spacing: 12
            Repeater {
                model: [
                    { label: "交易信号", value: root.vm !== null ? root.vm.signalCount : 0, tint: "#D7E4FF" },
                    { label: "有效机会", value: root.vm !== null ? root.vm.opportunityCount : 0, tint: "#D2F5E5" },
                    { label: "板块数量", value: root.vm !== null ? root.vm.sectorCount : 0, tint: "#E8DBFF" },
                    { label: "数据异常", value: root.vm !== null ? root.vm.errorCount : 0, tint: "#FFDCCF" }
                ]
                delegate: GlassCard {
                    width: (root.width - 76) / 4
                    height: 112
                    interactive: false
                    accentTint: modelData.tint
                    accentStrength: 0.22
                    Column {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 8
                        GlassText { text: modelData.label; tone: "muted"; sizeHint: 12 }
                        GlassText { text: String(modelData.value); tone: "primary"; sizeHint: 24 }
                    }
                }
            }
        }

        Row {
            visible: root.vm !== null && root.vm.lifecycle === "READY" && !root.showFullReport
            width: parent.width
            height: parent.height - y
            spacing: 14

            GlassCard {
                width: (parent.width - parent.spacing) * 0.60
                height: parent.height
                interactive: false
                accentTint: "#D9E6FF"
                accentStrength: 0.13
                Column {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 9
                    GlassText {
                        text: "交易信号详情 · " + (root.vm !== null ? root.vm.signalCount : 0)
                        tone: "primary"
                        sizeHint: 16
                    }
                    ListView {
                        id: signalList
                        width: parent.width
                        height: parent.height - y
                        clip: true
                        spacing: 7
                        model: root.vm !== null ? root.vm.signals : []
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        delegate: GlassSurface {
                            width: signalList.width
                            height: 58
                            tintAlpha: root.vm !== null && root.vm.hasSelectedSignal
                                       && root.selectedSignal.symbol === modelData.symbol ? 0.18 : 0.06
                            surfaceRadius: GlassTokens.capsuleRadius(height)
                            accentTint: modelData.level === "IGNORE" ? "#E6EBF1" : "#D5F1E5"
                            accentStrength: root.vm !== null && root.vm.hasSelectedSignal
                                            && root.selectedSignal.symbol === modelData.symbol ? 0.27 : 0.12
                            reactive: true
                            liftOnHover: true
                            pointerCursor: true
                            Row {
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 8
                                Column {
                                    width: parent.width * 0.42
                                    spacing: 3
                                    GlassText { text: modelData.name + "  ·  " + modelData.symbol; tone: "primary"; sizeHint: 13 }
                                    GlassText { width: parent.width; text: modelData.sector; elide: Text.ElideRight; tone: "muted"; sizeHint: 11 }
                                }
                                GlassText { width: 58; text: modelData.score_text; tone: "primary"; sizeHint: 15 }
                                GlassText { width: 92; text: modelData.level; color: root.signalColor(modelData.level); sizeHint: 12 }
                                GlassText { width: parent.width - x; text: modelData.stage; elide: Text.ElideRight; tone: "muted"; sizeHint: 12 }
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: if (root.vm !== null) root.vm.selectSignal(index)
                                onDoubleClicked: {
                                    if (root.vm !== null) {
                                        root.vm.selectSignal(index)
                                        root.vm.openSelectedChart()
                                    }
                                }
                            }
                        }
                    }
                }
            }

            GlassCard {
                width: parent.width - x
                height: parent.height
                interactive: false
                accentTint: "#E7DCFF"
                accentStrength: 0.13
                Column {
                    visible: root.vm === null || !root.vm.hasSelectedSignal
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 9
                    GlassText {
                        text: "板块排名 · " + (root.vm !== null ? root.vm.sectorCount : 0)
                        tone: "primary"
                        sizeHint: 16
                    }
                    ListView {
                        id: sectorList
                        width: parent.width
                        height: Math.min(parent.height * 0.58, contentHeight)
                        clip: true
                        spacing: 6
                        model: root.vm !== null ? root.vm.sectors : []
                        delegate: GlassSurface {
                            width: sectorList.width
                            height: 48
                            tintAlpha: 0.05
                            surfaceRadius: GlassTokens.capsuleRadius(height)
                            liftOnHover: true
                            Row {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 8
                                GlassText { width: parent.width - 190; text: modelData.name; elide: Text.ElideRight; tone: "primary"; sizeHint: 12 }
                                GlassText { width: 42; text: String(modelData.score); tone: "secondary"; sizeHint: 13 }
                                GlassText { width: 116; text: "上涨 " + modelData.breadth + " / 覆盖 " + modelData.coverage; tone: "muted"; sizeHint: 10 }
                            }
                        }
                    }
                    GlassText {
                        text: "最近告警 " + (root.vm !== null ? root.vm.alerts.length : 0)
                              + " 条 · 数据异常 " + (root.vm !== null ? root.vm.dataErrors.length : 0) + " 项"
                        tone: "secondary"
                        sizeHint: 12
                    }
                    GlassText {
                        visible: root.vm !== null && root.vm.alerts.length > 0
                        width: parent.width
                        text: root.vm !== null && root.vm.alerts.length > 0 ? root.vm.alerts[0] : ""
                        wrapMode: Text.Wrap
                        maximumLineCount: 3
                        elide: Text.ElideRight
                        tone: "muted"
                        sizeHint: 11
                    }
                }

                Column {
                    visible: root.vm !== null && root.vm.hasSelectedSignal
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 10

                    Row {
                        width: parent.width
                        height: 38
                        spacing: 8
                        GlassText {
                            width: parent.width - 84
                            text: root.vm !== null && root.vm.hasSelectedSignal
                                  ? root.selectedSignal.name + "  ·  " + root.selectedSignal.symbol
                                  : "交易信号详情"
                            elide: Text.ElideRight
                            tone: "primary"
                            sizeHint: 17
                        }
                        GlassButton {
                            width: 76
                            height: 34
                            label: "返回排名"
                            onClicked: if (root.vm !== null) root.vm.clearSelectedSignal()
                        }
                    }

                    Flickable {
                        id: signalDetail
                        width: parent.width
                        height: parent.height - y
                        contentWidth: width
                        contentHeight: detailColumn.implicitHeight
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        Column {
                            id: detailColumn
                            width: signalDetail.width - 8
                            spacing: 10

                            GlassSurface {
                                width: parent.width
                                height: 58
                                surfaceRadius: GlassTokens.capsuleRadius(height)
                                tintAlpha: 0.14
                                accentTint: "#D5F1E5"
                                accentStrength: 0.22
                                liftOnHover: true
                                Row {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 14
                                    GlassText { text: root.selectedSignal.score_text || "--"; tone: "primary"; sizeHint: 19 }
                                    GlassText { text: root.selectedSignal.level || "--"; color: root.signalColor(root.selectedSignal.level); sizeHint: 12 }
                                    GlassText { text: root.selectedSignal.stage || "--"; tone: "muted"; sizeHint: 12 }
                                    GlassText {
                                        width: parent.width - x
                                        text: (root.selectedSignal.market || "--") + "  ·  " + (root.selectedSignal.sector || "--")
                                        elide: Text.ElideRight
                                        horizontalAlignment: Text.AlignRight
                                        tone: "muted"
                                        sizeHint: 11
                                    }
                                }
                            }

                            GlassText { text: "打分构成"; tone: "primary"; sizeHint: 14 }
                            Flow {
                                width: parent.width
                                height: childrenRect.height
                                spacing: 7
                                Repeater {
                                    model: root.vm !== null && root.vm.hasSelectedSignal
                                           ? root.selectedSignal.score_parts : []
                                    delegate: GlassSurface {
                                        width: (detailColumn.width - 14) / 3
                                        height: 40
                                        surfaceRadius: GlassTokens.capsuleRadius(height)
                                        tintAlpha: 0.08
                                        accentTint: modelData.value === "N/A" ? "#E7EBF0" : "#E3D8FF"
                                        accentStrength: 0.14
                                        liftOnHover: true
                                        Row {
                                            anchors.centerIn: parent
                                            spacing: 7
                                            GlassText { text: modelData.label; tone: "muted"; sizeHint: 11 }
                                            GlassText { text: modelData.value; tone: "primary"; sizeHint: 13 }
                                        }
                                    }
                                }
                            }

                            GlassText { text: "关键指标"; tone: "primary"; sizeHint: 14 }
                            Flow {
                                width: parent.width
                                height: childrenRect.height
                                spacing: 7
                                Repeater {
                                    model: root.vm !== null && root.vm.hasSelectedSignal
                                           ? root.selectedSignal.metric_items : []
                                    delegate: GlassSurface {
                                        width: (detailColumn.width - 7) / 2
                                        height: 38
                                        surfaceRadius: GlassTokens.capsuleRadius(height)
                                        tintAlpha: 0.055
                                        liftOnHover: true
                                        Row {
                                            anchors.fill: parent
                                            anchors.leftMargin: 12
                                            anchors.rightMargin: 12
                                            spacing: 8
                                            GlassText { anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.55; text: modelData.label; tone: "muted"; sizeHint: 11 }
                                            GlassText { anchors.verticalCenter: parent.verticalCenter; width: parent.width - x; text: modelData.value; tone: "primary"; sizeHint: 12 }
                                        }
                                    }
                                }
                            }

                            GlassText { text: "打分依据"; tone: "primary"; sizeHint: 14 }
                            Repeater {
                                model: root.vm !== null && root.vm.hasSelectedSignal
                                       ? root.selectedSignal.reasons : []
                                delegate: GlassText {
                                    width: detailColumn.width
                                    text: "• " + modelData
                                    wrapMode: Text.Wrap
                                    tone: "secondary"
                                    sizeHint: 11
                                }
                            }

                            GlassText {
                                visible: root.vm !== null && root.vm.hasSelectedSignal
                                         && root.selectedSignal.risks.length > 0
                                text: "风险提示"
                                tone: "primary"
                                sizeHint: 14
                            }
                            Repeater {
                                model: root.vm !== null && root.vm.hasSelectedSignal
                                       ? root.selectedSignal.risks : []
                                delegate: GlassText {
                                    width: detailColumn.width
                                    text: "• " + modelData
                                    wrapMode: Text.Wrap
                                    tone: "secondary"
                                    sizeHint: 11
                                }
                            }

                            GlassButton {
                                width: 128
                                height: 40
                                label: "查看 K 线"
                                active: true
                                onClicked: if (root.vm !== null) root.vm.openSelectedChart()
                            }
                            Item { width: 1; height: 8 }
                        }
                    }
                }
            }
        }

        GlassCard {
            visible: root.vm !== null && root.vm.lifecycle === "READY" && root.showFullReport
            width: parent.width
            height: parent.height - y
            interactive: false
            accentTint: "#E3ECF7"
            accentStrength: 0.10
            Flickable {
                anchors.fill: parent
                anchors.margins: 18
                contentWidth: width
                contentHeight: reportText.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                GlassText {
                    id: reportText
                    width: parent.width
                    text: root.vm !== null && root.vm.markdown
                          ? root.vm.markdown : "暂无 Markdown 日报全文"
                    textFormat: Text.MarkdownText
                    wrapMode: Text.Wrap
                    tone: "primary"
                    sizeHint: 13
                    onLinkActivated: (link) => Qt.openUrlExternally(link)
                }
            }
        }
    }
}
