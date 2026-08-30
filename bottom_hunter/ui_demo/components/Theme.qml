pragma Singleton
import QtQuick

// RainGlass Design Tokens — single source of truth (MASTER_PROMPT §7).
// No magic colours/radii/spacing elsewhere in the demo.
QtObject {
    id: theme

    // ---- Colors -------------------------------------------------------
    readonly property color bg0: "#0A1016"     // 背景偏暗但非纯黑（§0.1 背景暗 ≠ 玻璃暗）
    readonly property color bg1: "#0E161E"
    readonly property color bg2: "#111B24"

    readonly property color textPrimary: "#EEF3F6"
    readonly property color textSecondary: "#9AA6B2"
    readonly property color textMuted: "#626D78"

    readonly property color accent: "#2BD576"
    readonly property color accentDim: "#1DB764"
    readonly property color positive: "#2BD576"
    readonly property color warning: "#E8B45A"
    readonly property color error: "#E06C6C"
    readonly property color info: "#5B9FD6"

    // 红涨绿跌：尊重本地金融配色习惯（demo 图表中使用）
    readonly property color marketUp: "#E05C5C"
    readonly property color marketDown: "#2BD58F"

    // ---- Glass（无色透明：近白 tint，低 opacity，边缘高光 §4.2）----------
    // Level A（nav/toolbar）最明显，Level B（卡片）中等，Level C（数据区）克制
    readonly property color glassTint: "#FFFFFF"          // 近白，非深色
    readonly property real glassAlphaA: 0.07
    readonly property real glassAlphaB: 0.05
    readonly property real glassAlphaC: 0.03
    readonly property color glassEdge: "#FFFFFF"
    readonly property real glassEdgeAlpha: 0.22
    readonly property real glassEdgeAlphaHover: 0.32
    readonly property real glassTopLight: 0.20

    // ---- Radius（分档，不要全 24px）------------------------------------
    readonly property int radiusSmall: 9
    readonly property int radiusRegular: 12
    readonly property int radiusCard: 16
    readonly property int radiusSurface: 20

    // ---- Spacing（4/8 grid）--------------------------------------------
    readonly property int sp4: 4
    readonly property int sp8: 8
    readonly property int sp12: 12
    readonly property int sp16: 16
    readonly property int sp20: 20
    readonly property int sp24: 24
    readonly property int sp32: 32

    // ---- Motion --------------------------------------------------------
    readonly property int animFast: 120
    readonly property int animNormal: 220
    readonly property real parallaxMax: 4.0   // px, MASTER_PROMPT §10

    // ---- Quality presets -----------------------------------------------
    // High: 完整雨滴场+高质量折射; Balanced: 默认; Low: 静态玻璃
    function presetDropletDensity(preset) {
        if (preset === "high") return 1.0
        if (preset === "balanced") return 0.55
        return 0.0
    }
    function presetBlurMax(preset) {
        if (preset === "high") return 28.0
        if (preset === "balanced") return 18.0
        return 0.0
    }
    function presetShaderQuality(preset) {
        if (preset === "high") return 1.0
        if (preset === "balanced") return 0.75
        return 0.0
    }
}
