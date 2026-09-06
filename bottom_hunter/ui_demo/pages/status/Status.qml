import QtQuick
import "../../primitives"

GlassSurface {
    id: root
    objectName: "statusPage"
    tintAlpha: 0.42
    surfaceRadius: GlassTokens.pageRadius
    edgeContrast: GlassTokens.structuralEdgeContrast
    depthStrength: GlassTokens.structuralDepthStrength

    readonly property var vm: (typeof statusVm !== "undefined") ? statusVm : null

    Component.onCompleted: {
        if (vm !== null && vm.lifecycle === "INIT") vm.refresh()
    }

    Column {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 14

        Row {
            width: parent.width
            spacing: 10
            GlassText { width: parent.width - 90; text: "系统状态"; tone: "primary"; sizeHint: 23 }
            GlassButton {
                width: 76
                height: 34
                label: "重新检查"
                onClicked: if (root.vm !== null) root.vm.refresh()
            }
        }
        GlassText {
            text: root.vm !== null && root.vm.generatedAt !== "" ? "检查时间 · " + root.vm.generatedAt : "只读健康检查"
            tone: "muted"
            sizeHint: 12
        }

        GlassCard {
            visible: root.vm === null || ["INIT", "LOADING", "EMPTY", "ERROR"].indexOf(root.vm.lifecycle) >= 0
            width: parent.width
            height: 76
            interactive: false
            GlassText {
                anchors.centerIn: parent
                text: root.vm === null ? "状态 ViewModel 未连接"
                      : root.vm.lifecycle === "ERROR" ? root.vm.error
                      : root.vm.lifecycle === "EMPTY" ? "尚无系统状态快照"
                      : "正在读取系统状态…"
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
                    { label: "数据状态", value: root.vm !== null ? root.vm.dataStatus : "--", tint: "#D7E9FF" },
                    { label: "最近扫描", value: root.vm !== null ? root.vm.lastScanTime : "--", tint: "#E5DCFF" },
                    { label: "系统健康", value: root.vm !== null ? root.vm.systemHealth : "--", tint: "#D3F4E4" }
                ]
                delegate: GlassCard {
                    width: (root.width - 64) / 3
                    height: 100
                    interactive: false
                    accentTint: modelData.tint
                    accentStrength: 0.20
                    Column {
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 7
                        GlassText { text: modelData.label; tone: "muted"; sizeHint: 12 }
                        GlassText {
                            width: parent.width
                            text: modelData.value
                            elide: Text.ElideRight
                            tone: "primary"
                            sizeHint: 15
                        }
                    }
                }
            }
        }

        Row {
            visible: root.vm !== null && root.vm.lifecycle === "READY"
            width: parent.width
            height: parent.height - y
            spacing: 14

            GlassCard {
                width: (parent.width - parent.spacing) * 0.58
                height: parent.height
                interactive: false
                accentTint: "#D8F4EA"
                accentStrength: 0.12
                Column {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 9
                    GlassText {
                        text: "健康检查 · " + (root.vm !== null ? root.vm.okCount + "/" + root.vm.totalCount : "0/0")
                        tone: "primary"
                        sizeHint: 16
                    }
                    Repeater {
                        model: root.vm !== null ? root.vm.items : []
                        GlassSurface {
                            width: parent.width
                            height: 52
                            tintAlpha: 0.025
                            surfaceRadius: GlassTokens.compactContainerRadius
                            accentTint: modelData.ok ? "#CDEFE0" : "#FFD8CF"
                            accentStrength: 0.12
                            Row {
                                anchors.fill: parent
                                anchors.margins: 11
                                spacing: 10
                                GlassText { width: 90; text: modelData.ok ? "正常" : "异常"; tone: modelData.ok ? "primary" : "secondary"; sizeHint: 12 }
                                GlassText { width: 110; text: modelData.name; tone: "primary"; sizeHint: 13 }
                                GlassText { width: parent.width - 220; text: modelData.detail; elide: Text.ElideRight; tone: "muted"; sizeHint: 12 }
                            }
                        }
                    }
                }
            }

            GlassCard {
                width: parent.width - x
                height: parent.height
                interactive: false
                accentTint: "#FFE2D7"
                accentStrength: 0.12
                Column {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 9
                    GlassText { text: "数据源健康"; tone: "primary"; sizeHint: 16 }
                    ListView {
                        id: marketHealthList
                        width: parent.width
                        height: Math.min(230, contentHeight)
                        spacing: 6
                        clip: true
                        model: root.vm !== null ? root.vm.marketHealth : []
                        delegate: GlassSurface {
                            width: marketHealthList.width
                            height: 54
                            tintAlpha: 0.05
                            surfaceRadius: GlassTokens.compactContainerRadius
                            accentTint: modelData.errors > 0 ? "#FFD8CF" : "#D4F1E6"
                            accentStrength: 0.10
                            Row {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 8
                                GlassText { width: 58; text: modelData.market; tone: "primary"; sizeHint: 12 }
                                Column {
                                    width: parent.width - 66
                                    spacing: 3
                                    GlassText { text: modelData.session + "  ·  完整 " + modelData.complete + "/" + modelData.signals + "  ·  异常 " + modelData.errors; tone: "secondary"; sizeHint: 11 }
                                    GlassText { width: parent.width; text: modelData.providers; elide: Text.ElideRight; tone: "muted"; sizeHint: 10 }
                                }
                            }
                        }
                    }
                    GlassText {
                        text: "最近扫描批次 · " + (root.vm !== null ? root.vm.recentRuns.length : 0)
                        tone: "primary"
                        sizeHint: 14
                    }
                    GlassText {
                        visible: root.vm !== null && root.vm.recentRuns.length > 0
                        width: parent.width
                        text: root.vm !== null && root.vm.recentRuns.length > 0
                              ? "#" + root.vm.recentRuns[0].run_id + "  ·  "
                                + root.vm.recentRuns[0].report_date + "  ·  "
                                + root.vm.recentRuns[0].status : ""
                        tone: "muted"
                        sizeHint: 11
                    }
                    GlassText { text: "最近错误"; tone: "primary"; sizeHint: 14 }
                    GlassText {
                        visible: root.vm !== null && root.vm.recentErrors.length === 0
                        text: "未发现最近数据错误"
                        tone: "muted"
                        sizeHint: 13
                    }
                    Repeater {
                        model: root.vm !== null ? root.vm.recentErrors : []
                        GlassText {
                            width: parent.width
                            text: "• " + modelData
                            wrapMode: Text.Wrap
                            tone: "secondary"
                            sizeHint: 12
                        }
                    }
                }
            }
        }
    }
}
