// GlassText — abstract text with the accepted tone hierarchy (PHASE 3-B).
//
// Encodes the frozen text color + size conventions (title 23 #f2f4f8,
// heading 18 #eef1f5, body 14 #9aa3b2, muted 12 #626d78) into one type.
import QtQuick

Text {
    id: root

    // tone: primary | secondary | muted
    property string tone: "secondary"
    property int sizeHint: 14

    readonly property var _tones: ({
        "primary": "#f2f4f8",
        "secondary": "#9aa3b2",
        "muted": "#626d78",
    })

    property color toneColor: _tones[tone] !== undefined ? _tones[tone] : _tones.secondary

    color: root.toneColor
    font.pixelSize: root.sizeHint
    font.family: "Noto Sans CJK SC"
}
