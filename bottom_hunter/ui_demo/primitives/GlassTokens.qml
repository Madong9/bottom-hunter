pragma Singleton
import QtQuick

// Shared Liquid Glass geometry and typography tokens. Components choose a
// semantic role instead of inventing local radii or low-contrast ink colors.
QtObject {
    readonly property real pageRadius: 32
    readonly property real cardRadius: 44
    readonly property real containerRadius: 28
    readonly property real compactContainerRadius: 22
    // Large structural panes should separate through material and radius, not
    // through bright, ruler-straight borders.
    readonly property real structuralEdgeContrast: 0.18
    readonly property real structuralDepthStrength: 0.32

    // Cool ink colours remain legible over both bright desktop windows and
    // darker refracted patches.  Muted text is intentionally blue-gray rather
    // than low-opacity gray, so hierarchy never depends on transparency.
    readonly property color textPrimary: "#071722"
    readonly property color textSecondary: "#173247"
    readonly property color textMuted: "#294A60"
    readonly property color textHighlight: Qt.rgba(1, 1, 1, 0.20)

    function capsuleRadius(height) {
        return Math.max(0, height / 2)
    }

    function circleRadius(size) {
        return Math.max(0, size / 2)
    }
}
