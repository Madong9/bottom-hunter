// GlassCard — Level B glass surface (medium glass, MASTER_PROMPT §8).
// Translucent fill + 1px light edge + brighter top light + soft shadow.
// Hover: edge brightens, scale 1.006, no bounce (§10).
import QtQuick
import QtQuick.Effects

Rectangle {
    id: root

    property bool interactive: true
    property real glassAlpha: 0.05    // Level B default（§4.2: 0.025~0.10）
    property color tint: "#FFFFFF"    // 无色透明：近白 tint，不是 dark navy

    radius: 16
    color: Qt.rgba(tint.r, tint.g, tint.b, glassAlpha)
    border.width: 1

    // Layered edge: uniform light border + stronger top highlight (liquid-glass)
    border.color: interactive && hover.hovered
                  ? Qt.rgba(1, 1, 1, 0.32)
                  : Qt.rgba(1, 1, 1, 0.22)

    // Top inner light: brighter 1px line along the top edge
    Rectangle {
        anchors { top: parent.top; left: parent.left; right: parent.right }
        anchors.margins: 1
        height: 1
        radius: 1
        color: Qt.rgba(1, 1, 1, 0.22)
        opacity: root.interactive && hover.hovered ? 1.0 : 0.7
    }

    // Very subtle external shadow (§4.2: shadow opacity low)
    MultiEffect {
        anchors.fill: parent
        source: root
        visible: root.interactive
        shadowEnabled: true
        shadowColor: "#000000"
        shadowBlur: 0.30
        shadowVerticalOffset: 6
        shadowOpacity: 0.22
        autoPaddingEnabled: true
    }

    Behavior on scale {
        enabled: root.interactive
        NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
    }

    HoverHandler {
        id: hover
        cursorShape: root.interactive ? Qt.PointingHandCursor : Qt.ArrowCursor
    }

    states: [
        State {
            when: root.interactive && hover.hovered
            PropertyChanges { target: root; scale: 1.006 }
        },
        State {
            when: root.interactive && !hover.hovered
            PropertyChanges { target: root; scale: 1.0 }
        }
    ]
}
