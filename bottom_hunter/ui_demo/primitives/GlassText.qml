// GlassText — abstract text with the accepted tone hierarchy (PHASE 3-B).
//
// Encodes the shared text color + size conventions. The daylight environment
// uses brighter neutral grays so secondary information remains legible without
// turning the transparent glass into an opaque dark panel.
import QtQuick

Text {
    id: root

    // tone: primary | secondary | muted
    property string tone: "secondary"
    property int sizeHint: 14

    readonly property var _tones: ({
        "primary": "#F7FAFC",
        "secondary": "#D2DAE3",
        "muted": "#AAB6C3",
    })

    property color toneColor: _tones[tone] !== undefined ? _tones[tone] : _tones.secondary

    color: root.toneColor
    font.pixelSize: root.sizeHint
    font.family: "Noto Sans CJK SC"
}
