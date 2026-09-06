pragma Singleton
import QtQuick

// Session-scoped appearance controls shared by every liquid-glass surface.
// Keeping this presentation-only avoids coupling QML to settings/storage.
QtObject {
    // 1.25 gives the rose/sky/mint/gold/violet washes a little more depth
    // while preserving translucency. The navigation slider exposes 0.60–1.80.
    property real accentIntensity: 1.25
}
