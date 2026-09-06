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
        "primary": GlassTokens.textPrimary,
        "secondary": GlassTokens.textSecondary,
        "muted": GlassTokens.textMuted,
    })

    property color toneColor: _tones[tone] !== undefined ? _tones[tone] : _tones.secondary

    color: root.toneColor
    opacity: 1.0
    font.pixelSize: root.sizeHint
    font.family: "Noto Sans CJK SC"
    font.weight: root.tone === "primary" || root.sizeHint >= 20
                 ? Font.DemiBold : Font.Medium
    font.letterSpacing: root.sizeHint >= 20 ? -0.25 : 0.0
    font.hintingPreference: Font.PreferFullHinting
    style: Text.Raised
    styleColor: GlassTokens.textHighlight
}
