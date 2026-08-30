// MetricCard — 金融数据卡片 (MASTER_PROMPT §12 dashboard)。
// 左侧渐变强调条 + 标签/大数值/提示三行；数值唯一大号粗体。
import QtQuick

Rectangle {
    id: root

    property string label: ""
    property string value: ""
    property string hint: ""
    property string tone: "neutral"   // neutral|positive|warning|danger
    property color accent: "#2BD576"

    function toneColor(name) {
        if (name === "positive") return "#2BD576"
        if (name === "warning") return "#E8B45A"
        if (name === "danger") return "#E06C6C"
        if (name === "info") return "#5B9FD6"
        return "#5B9FD6"
    }

    radius: 14
    color: Qt.rgba(1, 1, 1, 0.05)
    border.width: 1
    border.color: Qt.rgba(1, 1, 1, hover.hovered ? 0.16 : 0.10)

    Row {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 12

        // 渐变强调条（accent → 透明，dark-glass-ui skill 手法）
        Rectangle {
            width: 4
            height: parent.height
            radius: 2
            gradient: Gradient {
                GradientStop { position: 0.0; color: root.accent }
                GradientStop { position: 1.0; color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.06) }
            }
        }

        Column {
            spacing: 3
            anchors.verticalCenter: parent.verticalCenter

            Text {
                text: root.label
                color: "#828A98"
                font.pixelSize: 12
            }
            Text {
                text: root.value
                color: "#EEF3F6"
                font.pixelSize: 24
                font.weight: Font.DemiBold
            }
            Text {
                text: root.hint
                color: "#626D78"
                font.pixelSize: 11
            }
        }
    }

    // 顶部内高光
    Rectangle {
        anchors { top: parent.top; left: parent.left; right: parent.right }
        anchors.margins: 1
        height: 1
        color: Qt.rgba(1, 1, 1, 0.13)
    }

    HoverHandler { id: hover }

    Behavior on border.color { ColorAnimation { duration: 140 } }
}
