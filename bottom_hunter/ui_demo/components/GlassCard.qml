// GlassCard — Level B glass surface (medium glass, MASTER_PROMPT §8).
// Translucent fill + 1px light edge + brighter top light + soft shadow.
// Hover: edge brightens, scale 1.006, no bounce (§10).
import QtQuick
import QtQuick.Effects

Rectangle {
    id: root

    property bool interactive: true
    property real glassAlpha: 0.055   // Level B default
    property color tint: "#0D141A"

    radius: 16
    color: Qt.rgba(tint.r, tint.g, tint.b, glassAlpha)
    border.width: 1

    // Layered edge: uniform light border + stronger top highlight (liquid-glass)
    border.color: interactive && hover.hovered
                  ? Qt.rgba(1, 1, 1, 0.16)
                  : Qt.rgba(1, 1, 1, 0.10)

    // Top inner light: brighter 1px line along the top edge
    Rectangle {
        anchors { top: parent.top; left: parent.left; right: parent.right }
        anchors.margins: 1
        height: 1
        radius: 1
        color: Qt.rgba(1, 1, 1, 0.13)
        opacity: root.interactive && hover.hovered ? 0.9 : 0.6
    }

    // Soft external shadow + hover lift via MultiEffect (merged pass, §15)
    MultiEffect {
        anchors.fill: parent
        source: root
        visible: root.interactive
        shadowEnabled: true
        shadowColor: "#000000"
        shadowBlur: 0.35
        shadowVerticalOffset: 10
        shadowOpacity: 0.35
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
