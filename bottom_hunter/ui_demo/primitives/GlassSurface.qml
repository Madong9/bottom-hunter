// GlassSurface — abstract neutral glass slab (PHASE 3-B).
//
// Encodes the ALREADY-ACCEPTED glass visual DNA (no redesign): near-white
// neutral tint, thin bright edge, 1px top light, subtle darker bottom/right
// refraction edge. Used by higher-level primitives (GlassCard/GlassButton).
// Does NOT modify the frozen GlassNavRail / GlassMetricCard — it extracts
// their shared visual values into one place.
import QtQuick

Rectangle {
    id: root

    // neutral tint alpha: Level A=0.045, B=0.035, C=0.02 (accepted ranges)
    property real tintAlpha: 0.035
    property color tint: "#FFFFFF"
    property real surfaceRadius: 16

    radius: surfaceRadius
    color: Qt.rgba(tint.r, tint.g, tint.b, tintAlpha)
    border.width: 0

    // 1px top inner light
    Rectangle {
        anchors { top: parent.top; left: parent.left; right: parent.right }
        anchors.margins: 1
        height: 1
        radius: 1
        color: Qt.rgba(1, 1, 1, 0.14)
    }
    // thin bright edge (top-left bias)
    Rectangle {
        anchors { top: parent.top; left: parent.left; right: parent.right }
        height: 1
        radius: 1
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.28) }
            GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.10) }
        }
    }
    Rectangle {
        anchors { top: parent.top; left: parent.left; bottom: parent.bottom }
        width: 1
        color: Qt.rgba(1, 1, 1, 0.18)
    }
    // subtle darker bottom/right refraction edge (thick-glass slab feel)
    Rectangle {
        anchors { bottom: parent.bottom; left: parent.left; right: parent.right }
        height: 1
        color: Qt.rgba(0, 0, 0, 0.10)
    }
    Rectangle {
        anchors { top: parent.top; right: parent.right; bottom: parent.bottom }
        width: 1
        color: Qt.rgba(0, 0, 0, 0.08)
    }
}
