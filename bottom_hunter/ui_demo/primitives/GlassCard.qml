// GlassCard — raised liquid-glass content lens.
import QtQuick
import QtQuick.Effects

GlassSurface {
    id: root

    property bool interactive: true
    property real shadowOpacity: 0.24
    reactive: interactive

    layer.enabled: true
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: "#000000"
        shadowBlur: 0.52
        shadowVerticalOffset: 10
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

    // Directional elasticity is intentionally restrained: the optical slab
    // yields toward the pointer while text remains fully legible.
    transform: Scale {
        origin.x: root.width / 2
        origin.y: root.height / 2
        xScale: root.interactive && root.materialHovered
                ? 1.0 + Math.abs(root.materialOffsetX) * 0.006
                      - Math.abs(root.materialOffsetY) * 0.002 : 1.0
        yScale: root.interactive && root.materialHovered
                ? 1.0 + Math.abs(root.materialOffsetY) * 0.006
                      - Math.abs(root.materialOffsetX) * 0.002 : 1.0
        Behavior on xScale { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
        Behavior on yScale { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
    }
}
