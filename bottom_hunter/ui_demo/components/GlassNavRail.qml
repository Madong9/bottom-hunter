// GlassNavRail — Level A glass (most visible glass, MASTER_PROMPT §8/§12)。
// 约 72px 浮动玻璃栏：图标为主，active 用克制 emerald 指示。
import QtQuick
import QtQuick.Controls.Basic

Rectangle {
    id: root

    property int currentIndex: 0
    signal navigate(int index)

    // Level A: clear glass (v2: neutral white tint 0.045, NOT dark plastic)
    color: Qt.rgba(1, 1, 1, 0.045)
    radius: 20
    border.width: 1
    border.color: Qt.rgba(1, 1, 1, 0.12)

    // 顶部内高光（Level A 明显）
    Rectangle {
        anchors { top: parent.top; left: parent.left; right: parent.right }
        anchors.margins: 1
        height: 1
        color: Qt.rgba(1, 1, 1, 0.16)
    }

    // thick-glass slab edges: subtle darker bottom / right refraction edge
    Rectangle {
        anchors { bottom: parent.bottom; left: parent.left; right: parent.right }
        anchors.margins: 1
        height: 1
        color: Qt.rgba(0, 0, 0, 0.10)
    }
    Rectangle {
        anchors { top: parent.top; right: parent.right; bottom: parent.bottom }
        anchors.margins: 1
        width: 1
        color: Qt.rgba(0, 0, 0, 0.08)
    }

    Column {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 6

        // 品牌
        Rectangle {
            width: 40; height: 40
            radius: 20
            anchors.horizontalCenter: parent.horizontalCenter
            color: Qt.rgba(0.169, 0.835, 0.463, 0.16)
            border.width: 1
            border.color: Qt.rgba(0.169, 0.835, 0.463, 0.4)

            Text {
                anchors.centerIn: parent
                text: "B"
                color: "#2BD576"
                font.pixelSize: 19
                font.weight: Font.Bold
            }
        }

        Item { width: 1; height: 10 }

        Repeater {
            model: [
                { icon: "⌂", tip: "总览" },
                { icon: "◆", tip: "自选" },
                { icon: "◎", tip: "研究" },
                { icon: "▤", tip: "报告" },
                { icon: "✚", tip: "导入" },
                { icon: "◐", tip: "状态" },
                { icon: "↗", tip: "K线" }
            ]

            delegate: Item {
                width: 52
                height: 46
                anchors.horizontalCenter: parent.horizontalCenter

                // active 克制 emerald 药丸（very subtle tint + thin edge）
                Rectangle {
                    anchors.fill: parent
                    radius: 14
                    color: index === root.currentIndex
                           ? Qt.rgba(0.169, 0.835, 0.463, 0.09)
                           : hover.hovered ? Qt.rgba(1, 1, 1, 0.05) : "transparent"
                    border.width: index === root.currentIndex ? 1 : 0
                    border.color: Qt.rgba(0.169, 0.835, 0.463, 0.28)
                }

                Text {
                    anchors.centerIn: parent
                    text: modelData.icon
                    color: index === root.currentIndex
                           ? "#2BD576"
                           : hover.hovered ? "#C8CDD6" : "#6F7683"
                    font.pixelSize: 19
                }

                HoverHandler { id: hover }

                TapHandler {
                    onTapped: root.navigate(index)
                }

                ToolTip.visible: hover.hovered
                ToolTip.text: modelData.tip
                ToolTip.delay: 500
            }
        }
    }
}
