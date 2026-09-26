// GlassButton — abstract glass button (PHASE 3-B).
//
// Encodes the accepted nav-surface hover/active visual in a reusable,
// text-carrying button. Emerald active tint kept restrained (0.09 base) and
// a thin emerald optical edge — matching the frozen GlassNavRail active pill
// rather than redesigning it.
import QtQuick

GlassSurface {
    id: root

    property string label: ""
    property string glyph: ""
    property bool active: false
    property color activeTint: Qt.rgba(0.169, 0.835, 0.463, 0.09)

    surfaceRadius: GlassTokens.capsuleRadius(height)
    tint: active ? "#CFF4E0" : "#EEF7FD"
    tintAlpha: active ? 0.38 : hover.hovered ? 0.32 : 0.22
    accentTint: active ? "#67D9A4" : "#D8E9F8"
    accentStrength: active ? 0.26 : hover.hovered ? 0.14 : 0.05
    edgeContrast: active ? 0.42 : hover.hovered ? 0.36 : 0.25
    depthStrength: hover.hovered ? 1.16 : 1.0
    reactive: enabled
    pointerCursor: enabled
    scale: tap.pressed ? 0.965 : hover.hovered ? 1.025 : 1.0
    transformOrigin: Item.Center

    GlassText {
        anchors.centerIn: parent
        text: root.glyph !== "" ? root.glyph : root.label
        color: root.active ? "#128653" : (hover.hovered ? "#152330" : "#465D70")
        sizeHint: root.glyph !== "" ? 19 : 13
        font.weight: Font.DemiBold
    }

    HoverHandler { id: hover; enabled: root.enabled }
    TapHandler { id: tap; onTapped: root.clicked() }

    Behavior on scale {
        NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
    }

    signal clicked()
}
