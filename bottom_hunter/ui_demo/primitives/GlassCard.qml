// GlassCard — abstract glass card (PHASE 3-B).
//
// GlassSurface + soft depth shadow (accepted visual values only). A neutral
// container for page content in later phases; does not redesign the frozen
// GlassMetricCard.
import QtQuick
import QtQuick.Effects

GlassSurface {
    id: root

    property bool interactive: true
    property real shadowOpacity: 0.26

    layer.enabled: true
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: "#000000"
        shadowBlur: 0.30
        shadowVerticalOffset: 6
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
