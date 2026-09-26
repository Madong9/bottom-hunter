// GlassCard — raised liquid-glass content lens.
import QtQuick
import QtQuick.Effects

GlassSurface {
    id: root

    property bool interactive: true
    property real shadowOpacity: 0.14
    // Compact cards are true capsules; only large structural panes retain a
    // bounded corner radius so their content area remains practical.
    surfaceRadius: height <= 180 ? GlassTokens.capsuleRadius(height)
                                 : GlassTokens.cardRadius
    edgeContrast: 0.48
    depthStrength: 1.18
    tintAlpha: 0.30
    reactive: root.interactive || root.height <= 180
    // Compact information cards lift on hover even when they have no click
    // action.  Large workspaces (chart, long lists) stay geometrically stable
    // so mouse coordinates and scrolling are never disturbed.
    liftOnHover: root.interactive || root.height <= 180
    pointerCursor: interactive
    hoverScale: 1.016

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

    // Directional elasticity is intentionally restrained: the optical slab
    // yields toward the pointer while text remains fully legible.
    transform: Scale {
        origin.x: root.width / 2
        origin.y: root.height / 2
        xScale: root.materialHovered
                ? 1.0 + Math.abs(root.materialOffsetX) * 0.006
                      - Math.abs(root.materialOffsetY) * 0.002 : 1.0
        yScale: root.materialHovered
                ? 1.0 + Math.abs(root.materialOffsetY) * 0.006
                      - Math.abs(root.materialOffsetX) * 0.002 : 1.0
        Behavior on xScale { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
        Behavior on yScale { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
    }
}
