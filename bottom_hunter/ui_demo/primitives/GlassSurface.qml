// GlassSurface — daylight liquid-glass slab.
//
// The desktop remains visible through the native transparent window, while
// this surface supplies the visible glass medium: an ice-white gradient,
// bright lens edge, restrained internal sheen and a cooler lower rim.
import QtQuick

Rectangle {
    id: root

    property real tintAlpha: 0.16
    property color tint: "#F4FAFF"
    property real surfaceRadius: 20

    radius: surfaceRadius
    clip: true
    border.width: 1
    border.color: Qt.rgba(1, 1, 1, 0.52)
    gradient: Gradient {
        orientation: Gradient.Vertical
        GradientStop {
            position: 0.0
            color: Qt.rgba(1.0, 1.0, 1.0, Math.min(0.42, root.tintAlpha + 0.08))
        }
        GradientStop {
            position: 0.46
            color: Qt.rgba(root.tint.r, root.tint.g, root.tint.b, root.tintAlpha)
        }
        GradientStop {
            position: 1.0
            color: Qt.rgba(0.78, 0.88, 0.96, root.tintAlpha * 0.78)
        }
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
}
