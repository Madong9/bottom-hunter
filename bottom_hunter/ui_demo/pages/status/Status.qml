import QtQuick
import "../../primitives"

GlassSurface {
    id: root
    objectName: "statusPage"
    tintAlpha: 0.16
    surfaceRadius: 24

    readonly property var vm: (typeof statusVm !== "undefined") ? statusVm : null

    Component.onCompleted: {
        if (vm !== null && vm.lifecycle === "INIT") vm.refresh()
    }

    Column {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 14

        GlassText { text: "系统状态"; tone: "primary"; sizeHint: 23 }
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
                    { label: "数据状态", value: root.vm !== null ? root.vm.dataStatus : "--" },
                    { label: "最近扫描", value: root.vm !== null ? root.vm.lastScanTime : "--" },
                    { label: "系统健康", value: root.vm !== null ? root.vm.systemHealth : "--" }
                ]
                delegate: GlassCard {
                    width: (root.width - 64) / 3
                    height: 100
                    interactive: false
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
                            surfaceRadius: 9
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
                Column {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 9
                    GlassText { text: "最近错误"; tone: "primary"; sizeHint: 16 }
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
