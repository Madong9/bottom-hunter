// GlassCard — raised liquid-glass content lens.
import QtQuick
import QtQuick.Effects

GlassSurface {
    id: root

    property bool interactive: true
    property real shadowOpacity: 0.18
    reactive: interactive

    layer.enabled: true
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: "#000000"
        shadowBlur: 0.42
        shadowVerticalOffset: 8
        shadowOpacity: root.materialHovered
                       ? Math.min(0.30, root.shadowOpacity + 0.07)
                       : root.shadowOpacity
        autoPaddingEnabled: true
    }

    Behavior on scale {
        enabled: root.interactive
        NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
    }

    states: [
        State {
            when: root.interactive && root.materialHovered
            PropertyChanges { target: root; scale: 1.012 }
        }
    ]
}
