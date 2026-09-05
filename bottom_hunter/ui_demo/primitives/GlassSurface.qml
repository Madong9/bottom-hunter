// GlassSurface — daylight liquid-glass slab.
//
// The desktop remains visible through the native transparent window, while
// this surface supplies the visible glass medium: an ice-white gradient,
// bright lens edge, restrained internal sheen and a cooler lower rim.
import QtQuick
import QtQuick.Effects

Rectangle {
    id: root

    property real tintAlpha: 0.16
    property color tint: "#F4FAFF"
    property real surfaceRadius: 20
    property bool reactive: false
    readonly property bool materialHovered: liquidHover.hovered

    radius: surfaceRadius
    clip: true
    color: Qt.rgba(tint.r, tint.g, tint.b, tintAlpha)
    border.width: 1
    border.color: Qt.rgba(1, 1, 1, 0.52)

    // Pointer-driven reflection. This mirrors Liquid Glass's interactive
    // material response without moving static/non-interactive containers.
    Item {
        id: reflectionHost
        width: Math.min(240, Math.max(120, root.width * 0.34))
        height: width
        x: liquidHover.hovered
           ? liquidHover.point.position.x - width / 2
           : root.width * 0.28 - width / 2
        y: liquidHover.hovered
           ? liquidHover.point.position.y - height / 2
           : -height * 0.62
        opacity: root.reactive ? (liquidHover.hovered ? 0.82 : 0.20) : 0.0

        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: Qt.rgba(1, 1, 1, 0.18)
            layer.enabled: true
            layer.effect: MultiEffect {
                blurEnabled: true
                blur: 0.82
                blurMax: 48
            }
        }

        Behavior on x { NumberAnimation { duration: 130; easing.type: Easing.OutCubic } }
        Behavior on y { NumberAnimation { duration: 130; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    }

    // Soft liquid sheen immediately below the upper lens edge.
    Rectangle {
        anchors { top: parent.top; left: parent.left; right: parent.right }
        height: Math.min(72, Math.max(18, parent.height * 0.20))
        color: "transparent"
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.18) }
            GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.0) }
        }
    }

    // Short lower caustic band. Keeping gradients local avoids visible alpha
    // quantisation bands across a large transparent native window.
    Rectangle {
        anchors { bottom: parent.bottom; left: parent.left; right: parent.right }
        height: Math.min(54, Math.max(14, parent.height * 0.14))
        color: "transparent"
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0.0; color: Qt.rgba(0.72, 0.88, 1.0, 0.0) }
            GradientStop { position: 1.0; color: Qt.rgba(0.72, 0.88, 1.0, 0.09) }
        }
    }

    // Concentrated specular streak: short and directional, not a flat border.
    Rectangle {
        x: root.surfaceRadius
        y: 1
        width: Math.max(0, root.width * 0.48 - root.surfaceRadius)
        height: 2
        radius: 1
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.76) }
            GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.02) }
        }
    }

    // Left lens edge and cool lower/right thickness.
    Rectangle {
        anchors { top: parent.top; left: parent.left; bottom: parent.bottom }
        anchors.margins: 1
        width: 1
        color: Qt.rgba(1, 1, 1, 0.34)
    }
    Rectangle {
        anchors { bottom: parent.bottom; left: parent.left; right: parent.right }
        anchors.margins: 1
        height: 2
        color: Qt.rgba(0.18, 0.34, 0.46, 0.12)
    }
    Rectangle {
        anchors { top: parent.top; right: parent.right; bottom: parent.bottom }
        anchors.margins: 1
        width: 2
        color: Qt.rgba(0.18, 0.34, 0.46, 0.09)
    }

    HoverHandler {
        id: liquidHover
        enabled: root.reactive
        cursorShape: root.reactive ? Qt.PointingHandCursor : Qt.ArrowCursor
    }
}
