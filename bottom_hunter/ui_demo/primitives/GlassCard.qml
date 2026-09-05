// GlassCard — raised liquid-glass content lens.
import QtQuick
import QtQuick.Effects

GlassSurface {
    id: root

    property bool interactive: true
    property real shadowOpacity: 0.18

    layer.enabled: true
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: "#000000"
        shadowBlur: 0.42
        shadowVerticalOffset: 8
        shadowOpacity: root.shadowOpacity
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
        }
    ]
}
