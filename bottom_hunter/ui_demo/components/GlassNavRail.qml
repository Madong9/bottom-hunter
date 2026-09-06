// GlassNavRail — raised daylight liquid-glass navigation lens.
import QtQuick
import QtQuick.Controls.Basic
import "../primitives"

Rectangle {
    id: root

    property int currentIndex: 0
    signal navigate(int index)

    color: Qt.rgba(0.92, 0.97, 1.0, 0.46)
    radius: 32
    clip: true
    border.width: 1
    border.color: Qt.rgba(1, 1, 1, 0.70)

    Rectangle {
        anchors.fill: parent
        anchors.margins: 1
        radius: parent.radius - 1
        color: "transparent"
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, 0.28)
    }

    // 顶部内高光（Level A 明显）
    Rectangle {
        anchors { top: parent.top; left: parent.left; right: parent.right }
        anchors.margins: 1
        height: 2
        color: Qt.rgba(1, 1, 1, 0.82)
    }

    // thick-glass slab edges: subtle darker bottom / right refraction edge
    Rectangle {
        anchors { bottom: parent.bottom; left: parent.left; right: parent.right }
        anchors.margins: 1
        height: 3
        color: Qt.rgba(0.18, 0.34, 0.46, 0.17)
    }
    Rectangle {
        anchors { top: parent.top; right: parent.right; bottom: parent.bottom }
        anchors.margins: 1
        width: 3
        color: Qt.rgba(0.18, 0.34, 0.46, 0.13)
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
                { icon: "overview", tip: "总览" },
                { icon: "watchlist", tip: "自选" },
                { icon: "research", tip: "研究" },
                { icon: "report", tip: "报告" },
                { icon: "import", tip: "导入" },
                { icon: "status", tip: "状态" },
                { icon: "chart", tip: "K线" }
            ]

            delegate: Item {
                width: 52
                height: 46
                anchors.horizontalCenter: parent.horizontalCenter
                scale: tap.pressed ? 0.94 : hover.hovered ? 1.04 : 1.0

                // active 克制 emerald 药丸（very subtle tint + thin edge）
                Rectangle {
                    anchors.fill: parent
                    radius: 18
                    color: index === root.currentIndex
                           ? Qt.rgba(0.169, 0.835, 0.463, 0.09)
                           : hover.hovered ? Qt.rgba(1, 1, 1, 0.24) : "transparent"
                    border.width: index === root.currentIndex ? 1 : 0
                    border.color: Qt.rgba(0.169, 0.835, 0.463, 0.28)
                }

                NavSymbol {
                    anchors.centerIn: parent
                    width: 21
                    height: 21
                    symbol: modelData.icon
                    strokeWidth: index === root.currentIndex ? 2.25 : 1.85
                    strokeColor: index === root.currentIndex
                                 ? "#128653"
                                 : hover.hovered ? "#152330" : "#465D70"
                }

                HoverHandler { id: hover }

                TapHandler {
                    id: tap
                    onTapped: root.navigate(index)
                }

                Behavior on scale {
                    NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
                }

                ToolTip {
                    id: navTip
                    // Keep the tooltip inside the transparent QML scene. A
                    // native popup creates a rectangular platform window
                    // behind the rounded glass surface on Linux/X11.
                    popupType: Popup.Item
                    visible: hover.hovered
                    delay: 500
                    x: parent.width + 10
                    y: (parent.height - implicitHeight) / 2
                    padding: 10

                    contentItem: GlassText {
                        text: modelData.tip
                        tone: "primary"
                        sizeHint: 13
                    }
                    background: GlassSurface {
                        implicitWidth: 58
                        implicitHeight: 38
                        tint: "#EAF6FF"
                        tintAlpha: 0.70
                        accentTint: "#A9D8FF"
                        accentStrength: 0.18
                        surfaceRadius: 19
                    }
                }
            }
        }
    }
}
