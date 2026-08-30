// StatusBadge — 状态徽章：半透明底 + 提亮文字（dark-glass skill 硬规则 5）。
import QtQuick

Rectangle {
    id: root

    property string text: ""
    property string tone: "idle"   // idle|running|warning|danger

    function toneColors(name) {
        if (name === "running") return { bg: 0.10, fill: "#4DA3FF", text: "#6CB2FF" }
        if (name === "warning") return { bg: 0.10, fill: "#FFB020", text: "#FFC14D" }
        if (name === "danger") return { bg: 0.10, fill: "#FF5C5C", text: "#FF7B7B" }
        return { bg: 0.09, fill: "#2BD576", text: "#43D98B" }
    }

    readonly property var _colors: toneColors(tone)

    radius: 12
    implicitHeight: 24
    implicitWidth: badgeText.implicitWidth + 20
    color: Qt.rgba(_colors.fill.r, _colors.fill.g, _colors.fill.b, _colors.bg)
    border.width: 1
    border.color: Qt.rgba(_colors.fill.r, _colors.fill.g, _colors.fill.b, 0.28)

    Text {
        id: badgeText
        anchors.centerIn: parent
        text: root.text
        color: root._colors.text
        font.pixelSize: 11
        font.weight: Font.DemiBold
    }
}
