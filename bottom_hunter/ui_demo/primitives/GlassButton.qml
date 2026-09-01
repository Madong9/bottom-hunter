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
                  : hover.hovered ? Qt.rgba(1, 1, 1, 0.05) : "transparent"
    border.width: active ? 1 : 0
    border.color: Qt.rgba(0.169, 0.835, 0.463, 0.28)

    Text {
        anchors.centerIn: parent
        text: root.glyph !== "" ? root.glyph : root.label
        color: root.active ? "#2BD576" : (hover.hovered ? "#C8CDD6" : "#6F7683")
        font.pixelSize: root.glyph !== "" ? 19 : 13
    }

    HoverHandler { id: hover }
    TapHandler { onTapped: root.clicked() }

    signal clicked()
}
