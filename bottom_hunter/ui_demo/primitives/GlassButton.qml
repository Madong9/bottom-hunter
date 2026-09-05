// GlassButton — abstract glass button (PHASE 3-B).
//
// Encodes the accepted nav-surface hover/active visual in a reusable,
// text-carrying button. Emerald active tint kept restrained (0.09 base) and
// a thin emerald optical edge — matching the frozen GlassNavRail active pill
// rather than redesigning it.
import QtQuick
import QtQuick.Controls.Basic

Rectangle {
    id: root

    property string label: ""
    property string glyph: ""
    property bool active: false
    property color activeTint: Qt.rgba(0.169, 0.835, 0.463, 0.09)

    radius: 14
    color: active ? activeTint
                  : hover.hovered ? Qt.rgba(1, 1, 1, 0.22)
                                  : Qt.rgba(1, 1, 1, 0.07)
    border.width: 1
    border.color: active ? Qt.rgba(0.169, 0.835, 0.463, 0.32)
                         : Qt.rgba(1, 1, 1, hover.hovered ? 0.46 : 0.22)
    scale: tap.pressed ? 0.965 : hover.hovered ? 1.025 : 1.0

    Rectangle {
        anchors { top: parent.top; left: parent.left; right: parent.right }
        anchors.margins: 1
        height: Math.max(1, parent.height * 0.42)
        radius: root.radius - 1
        color: Qt.rgba(1, 1, 1, hover.hovered ? 0.16 : 0.08)
    }

    Text {
        anchors.centerIn: parent
        text: root.glyph !== "" ? root.glyph : root.label
        color: root.active ? "#128653" : (hover.hovered ? "#152330" : "#465D70")
        font.pixelSize: root.glyph !== "" ? 19 : 13
        font.family: "Noto Sans CJK SC"
        font.weight: Font.DemiBold
    }

    HoverHandler { id: hover }
    TapHandler { id: tap; onTapped: root.clicked() }

    Behavior on scale {
        NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
    }

    signal clicked()
}
