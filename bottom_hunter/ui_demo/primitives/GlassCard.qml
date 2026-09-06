// GlassCard — raised liquid-glass content lens.
import QtQuick
import QtQuick.Effects

GlassSurface {
    id: root

    property bool interactive: true
    property real shadowOpacity: 0.08
    surfaceRadius: Math.min(GlassTokens.cardRadius,
                            GlassTokens.capsuleRadius(height))
    edgeContrast: 0.48
    tintAlpha: 0.26
    reactive: interactive

    // Rectangle.clip is axis-aligned even when Rectangle.radius is set. A
    // real alpha mask is therefore required to keep the sheen, colour wash
    // and caustic layers out of the four transparent corners.
    readonly property Item roundedMask: ShaderEffectSource {
        sourceItem: Rectangle {
            width: root.width
            height: root.height
            radius: root.surfaceRadius
            antialiasing: true
            color: "white"
        }
    }

    layer.enabled: true
    layer.effect: MultiEffect {
        maskEnabled: true
        maskSource: root.roundedMask
        shadowEnabled: true
        shadowColor: "#000000"
        shadowBlur: 0.72
        shadowVerticalOffset: 6
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
