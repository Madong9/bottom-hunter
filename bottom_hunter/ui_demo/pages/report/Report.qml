import QtQuick
import "../../primitives"

GlassSurface {
    id: root
    objectName: "reportPage"
    tintAlpha: 0.34
    surfaceRadius: 24

    readonly property var vm: (typeof reportVm !== "undefined") ? reportVm : null

    Component.onCompleted: {
        if (vm !== null && vm.lifecycle === "INIT") vm.refresh()
    }

    Column {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 14

        GlassText { text: "报告"; tone: "primary"; sizeHint: 23 }
        GlassText {
            text: root.vm !== null && root.vm.reportDate !== "--" ? "日报 " + root.vm.reportDate : "最新生成报告"
            tone: "muted"
            sizeHint: 13
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
                    { label: "交易信号", value: root.vm !== null ? root.vm.signalCount : 0 },
                    { label: "有效机会", value: root.vm !== null ? root.vm.opportunityCount : 0 },
                    { label: "板块数量", value: root.vm !== null ? root.vm.sectorCount : 0 },
                    { label: "数据异常", value: root.vm !== null ? root.vm.errorCount : 0 }
                ]
                delegate: GlassCard {
                    width: (root.width - 76) / 4
                    height: 112
                    interactive: false
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
    }
}
