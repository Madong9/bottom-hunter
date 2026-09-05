// GlassText — abstract text with the accepted tone hierarchy (PHASE 3-B).
//
// Encodes the daylight liquid-glass text hierarchy. The glass medium is pale,
// so ink-like blue grays provide the Apple-style light appearance and remain
// readable over varied desktop content.
import QtQuick

Text {
    id: root

    // tone: primary | secondary | muted
    property string tone: "secondary"
    property int sizeHint: 14

    readonly property var _tones: ({
        "primary": "#152330",
        "secondary": "#34495C",
        "muted": "#61778B",
    })

    property color toneColor: _tones[tone] !== undefined ? _tones[tone] : _tones.secondary

    color: root.toneColor
    font.pixelSize: root.sizeHint
    font.family: "Noto Sans CJK SC"
}
