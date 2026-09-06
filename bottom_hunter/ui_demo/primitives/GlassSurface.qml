// GlassSurface — daylight liquid-glass slab.
//
// The desktop remains visible through the native transparent window, while
// this surface supplies the visible glass medium: an ice-white gradient,
// bright lens edge, restrained internal sheen and a cooler lower rim.
import QtQuick
import QtQuick.Effects

Rectangle {
    id: root

    property real tintAlpha: 0.30
    property color tint: "#EEF7FD"
    property color accentTint: "transparent"
    property real accentStrength: 0.0
    // Every surface participates in the optional visual editor. Explicit
    // keys/objectNames remain stable; anonymous repeater items get a runtime
    // key and can still be edited for the lifetime of that page instance.
    property string appearanceKey: ""
    property string appearanceLabel: ""
    property bool appearanceSelectable: true
    readonly property string resolvedAppearanceKey: appearanceKey !== ""
        ? appearanceKey : (objectName !== "" ? objectName : runtimeAppearanceKey)
    readonly property color effectiveAccentTint: GlassAppearance.tintFor(
        resolvedAppearanceKey, root.accentTint)
    readonly property real effectiveAccentStrength: GlassAppearance.strengthFor(
        resolvedAppearanceKey, root.accentStrength)
    property string runtimeAppearanceKey: ""
    property real surfaceRadius: 28
    property bool reactive: false
    readonly property bool materialHovered: liquidHover.hovered
    readonly property real materialOffsetX: liquidHover.hovered && width > 0
        ? Math.max(-1, Math.min(1, liquidHover.point.position.x / width * 2 - 1)) : -0.28
    readonly property real materialOffsetY: liquidHover.hovered && height > 0
        ? Math.max(-1, Math.min(1, liquidHover.point.position.y / height * 2 - 1)) : -0.42

    radius: surfaceRadius
    clip: true
    color: Qt.rgba(tint.r, tint.g, tint.b, tintAlpha)
    border.width: 1
    border.color: Qt.rgba(1, 1, 1, 0.66)

    Component.onCompleted: runtimeAppearanceKey = GlassAppearance.keyFor(root)

    // A local colour wash gives selected functional surfaces their own visual
    // identity while leaving most of the material optically neutral.  Content
    // supplied by derived components is rendered above this layer.
    Rectangle {
        visible: root.effectiveAccentStrength > 0.001
        anchors { top: parent.top; right: parent.right; bottom: parent.bottom }
        width: Math.max(root.surfaceRadius * 2, parent.width * 0.62)
        color: "transparent"
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: Qt.rgba(root.effectiveAccentTint.r, root.effectiveAccentTint.g, root.effectiveAccentTint.b, 0.0) }
            GradientStop { position: 0.62; color: Qt.rgba(root.effectiveAccentTint.r, root.effectiveAccentTint.g, root.effectiveAccentTint.b, root.effectiveAccentStrength * 0.42) }
            GradientStop { position: 1.0; color: Qt.rgba(root.effectiveAccentTint.r, root.effectiveAccentTint.g, root.effectiveAccentTint.b, root.effectiveAccentStrength) }
        }
    }

    // Secondary internal contour makes the rounded edge read as a thick lens
    // instead of a one-pixel outline painted on transparent plastic.
    Rectangle {
        anchors.fill: parent
        anchors.margins: 2
        radius: Math.max(0, root.surfaceRadius - 2)
        color: "transparent"
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, 0.24)
    }

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
        height: Math.min(92, Math.max(24, parent.height * 0.22))
        color: "transparent"
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.30) }
            GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.0) }
        }
    }

    // LiquidGlassVue keeps content sharp and applies chromatic separation only
    // at the refracting boundary. These two sub-pixel colour rims follow that
    // rule: the centre remains neutral while the lens edge gains optical depth.
    Rectangle {
        anchors { top: parent.top; left: parent.left; bottom: parent.bottom }
        anchors.margins: 2
        width: 1
        color: Qt.rgba(0.30, 0.82, 1.0, root.reactive && root.materialHovered ? 0.34 : 0.17)
    }
    Rectangle {
        anchors { top: parent.top; right: parent.right; bottom: parent.bottom }
        anchors.margins: 3
        width: 1
        color: Qt.rgba(0.82, 0.46, 1.0, root.reactive && root.materialHovered ? 0.24 : 0.11)
    }

    // Edit-mode selection ring is presentation-only and sits above the glass
    // optics. It is invisible during normal operation.
    Rectangle {
        anchors.fill: parent
        anchors.margins: 2
        radius: Math.max(0, root.surfaceRadius - 2)
        color: "transparent"
        visible: GlassAppearance.editMode && root.appearanceSelectable
        border.width: GlassAppearance.selectedKey === root.resolvedAppearanceKey ? 3 : 1
        border.color: GlassAppearance.selectedKey === root.resolvedAppearanceKey
                      ? Qt.rgba(0.32, 0.42, 0.92, 0.88)
                      : Qt.rgba(0.32, 0.42, 0.92, root.materialHovered ? 0.46 : 0.18)
        z: 90
    }

    TapHandler {
        enabled: GlassAppearance.editMode && root.appearanceSelectable
        acceptedButtons: Qt.LeftButton
        gesturePolicy: TapHandler.ReleaseWithinBounds
        onTapped: GlassAppearance.selectSurface(
            root.resolvedAppearanceKey,
            root.appearanceLabel !== "" ? root.appearanceLabel : root.objectName,
            root.accentTint,
            root.accentStrength)
    }

    // A narrow moving specular ribbon provides the pointer-linked reflection
    // used by liquid-glass controls, without tinting or blurring their content.
    Rectangle {
        visible: root.reactive
        width: Math.max(18, Math.min(54, root.width * 0.08))
        height: root.height * 1.5
        x: (root.materialOffsetX * 0.5 + 0.5) * Math.max(0, root.width - width)
        y: -root.height * 0.25
        rotation: -12 + root.materialOffsetY * 5
        opacity: root.materialHovered ? 0.34 : 0.0
        color: Qt.rgba(1, 1, 1, 0.22)
        layer.enabled: true
        layer.effect: MultiEffect {
            blurEnabled: true
            blur: 0.72
            blurMax: 28
        }
        Behavior on x { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 170; easing.type: Easing.OutCubic } }
    }

    // Short lower caustic band. Keeping gradients local avoids visible alpha
    // quantisation bands across a large transparent native window.
    Rectangle {
        anchors { bottom: parent.bottom; left: parent.left; right: parent.right }
        height: Math.min(72, Math.max(20, parent.height * 0.18))
        color: "transparent"
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0.0; color: Qt.rgba(0.72, 0.88, 1.0, 0.0) }
            GradientStop { position: 1.0; color: Qt.rgba(0.72, 0.88, 1.0, 0.16) }
        }
    }

    // Concentrated specular streak: short and directional, not a flat border.
    Rectangle {
        x: root.surfaceRadius
        y: 1
        width: Math.max(0, root.width * 0.62 - root.surfaceRadius)
        height: 2
        radius: 1
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.92) }
            GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.02) }
        }
    }

    // Left lens edge and cool lower/right thickness.
    Rectangle {
        anchors { top: parent.top; left: parent.left; bottom: parent.bottom }
        anchors.margins: 1
        width: 2
        color: Qt.rgba(1, 1, 1, 0.44)
    }
    Rectangle {
        anchors { bottom: parent.bottom; left: parent.left; right: parent.right }
        anchors.margins: 1
        height: 3
        color: Qt.rgba(0.18, 0.34, 0.46, 0.17)
    }
    Rectangle {
        anchors { top: parent.top; right: parent.right; bottom: parent.bottom }
        anchors.margins: 1
        width: 3
        color: Qt.rgba(0.18, 0.34, 0.46, 0.13)
    }

    HoverHandler {
        id: liquidHover
        enabled: root.reactive
        cursorShape: root.reactive ? Qt.PointingHandCursor : Qt.ArrowCursor
    }
}
