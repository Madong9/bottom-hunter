pragma Singleton
import QtQuick

// Shared Liquid Glass geometry and typography tokens. Components choose a
// semantic role instead of inventing local radii or low-contrast ink colors.
QtObject {
    readonly property real pageRadius: 32
    readonly property real containerRadius: 28
    readonly property real compactContainerRadius: 22

    readonly property color textPrimary: "#0E1B27"
    readonly property color textSecondary: "#263B4D"
    readonly property color textMuted: "#4C667A"
    readonly property color textHighlight: Qt.rgba(1, 1, 1, 0.48)

    function capsuleRadius(height) {
        return Math.max(0, height / 2)
    }

    function circleRadius(size) {
        return Math.max(0, size / 2)
    }
}
