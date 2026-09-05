import QtQuick
import "../../primitives"

GlassSurface {
    id: root
    objectName: "chartPage"
    tintAlpha: 0.34
    surfaceRadius: 24

    readonly property var vm: (typeof chartVm !== "undefined") ? chartVm : null

    Column {
        anchors.centerIn: parent
        width: Math.min(parent.width - 80, 620)
        spacing: 14

        GlassText { anchors.horizontalCenter: parent.horizontalCenter; text: "K线分析"; tone: "primary"; sizeHint: 23 }
        GlassCard {
            width: parent.width
            height: 130
            interactive: false
            Column {
                anchors.centerIn: parent
                width: parent.width - 40
                spacing: 10
                GlassText {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "尚未迁移到 QML"
                    tone: "primary"
                    sizeHint: 17
                }
                GlassText {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    text: root.vm !== null ? root.vm.message : "K线模块未连接，请使用现有安全页面。"
                    tone: "muted"
                    sizeHint: 13
                }
            }
        }
    }
}
