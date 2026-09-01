// RainGlassSurface — the LAST physical glass surface over the composited UI
// (overview shell v2 architecture).
//
// Accepted pipeline (frozen MaterialLab rain material):
//   sceneContent (environment + glass panels + chrome/content)
//   ↓ captured ONCE by srcCapture (ShaderEffectSource, hideSource = true)
//   ↓ [optional ClearGlass pane when includeGlassPane = true]
//   ↓ rainEffect = StaticRainUI (frozen droplet optics + importance mask)
//   ↓ viewer
//
// The rain layer is physically last: droplets refract card borders, nav
// edges, toolbar edges and non-critical UI content. Critical content is
// protected by the importance mask (maskSource → u_mask, low-resolution
// texture). sceneContent is NOT duplicate-drawn underneath (hideSource =
// true). No recursive capture: sceneContent never contains this surface.
import QtQuick
import QtQuick.Effects

Item {
    id: root

    // composited scene (environment + glass panels + chrome) to cover
    property Item sourceItem: null
    // optional importance mask item (R channel = density factor, 0..1);
    // internal all-normal fallback is used when null
    property Item maskSource: null
    // true = additionally apply the accepted ClearGlass pane over the source
    // (env-only reuse); the shell keeps it false (panels carry the glass)
    property bool includeGlassPane: false
    // false = no rain (captured scene drawn directly, pixel-identical)
    property bool rainEnabled: true

    // frozen accepted glass constants (MaterialLab engineering acceptance)
    property real u_blur: 0.75
    property real u_tint: 0.018
    property real u_sat: 1.06
    // frozen accepted droplet field (do NOT raise; quota ~556 total)
    property real u_density: 1.0
    property real u_quality: 1.0
    // 1 = full-field diameter/count proof rings (lab diagnostic)
    property real u_debug: 0.0

    // read-only introspection for the launcher (texture size proofs)
    readonly property vector2d captureTextureSize: Qt.vector2d(
        srcCapture.textureSize.width, srcCapture.textureSize.height)
    // computed from maskScale (avoids forward-reference binding issues)
    readonly property vector2d rainMaskTextureSize: Qt.vector2d(
        Math.max(4, Math.round(width * maskScale)),
        Math.max(4, Math.round(height * maskScale)))

    // true low-resolution importance mask: 1/4 linear dimensions (STEP 4)
    readonly property real maskScale: 0.25

    // internal fallback mask: all-normal density (used when maskSource null);
    // parked off-window (visible so the capture is never empty)
    Item {
        id: fallbackMask
        x: -100; y: -100
        width: 8; height: 8
        Rectangle { anchors.fill: parent; color: "#FFFFFF" }
    }

    // COMPOSITED SCENE CAPTURE — the only renderer of sceneContent
    ShaderEffectSource {
        id: srcCapture
        anchors.fill: parent
        sourceItem: root.sourceItem
        hideSource: true               // sceneContent NOT duplicate-drawn
        // rain on  → texture only (rainEffect draws the composited scene)
        // rain off → draw the captured scene directly (pixel-identical)
        visible: !root.rainEnabled
        textureSize: Qt.size(root.width, root.height)
        smooth: true
    }

    // optional ClearGlass pane (reused accepted material, env-only mode)
    ShaderEffect {
        id: glassEffect
        anchors.fill: parent
        visible: root.includeGlassPane

        property variant source: srcCapture
        property vector2d resolution: Qt.vector2d(width, height)
        property real u_blur: root.u_blur
        property real u_refract: 0.35
        property real u_tint: root.u_tint
        property real u_sat: root.u_sat

        fragmentShader: "../material_lab/effects/ClearGlass.qsb"
    }

    ShaderEffectSource {
        id: glassCapture
        anchors.fill: parent
        sourceItem: glassEffect
        hideSource: false
        visible: false
        textureSize: Qt.size(root.width, root.height)
        smooth: true
    }

    // importance mask capture (TRUE low-resolution: 1/4 linear dims,
    // e.g. 1440x900 -> 360x225; smooth sampling, dilation stays accurate)
    ShaderEffectSource {
        id: maskCapture
        anchors.fill: parent
        sourceItem: root.maskSource !== null ? root.maskSource : fallbackMask
        visible: false
        smooth: true
        textureSize: Qt.size(Math.max(4, Math.round(root.width * root.maskScale)),
                             Math.max(4, Math.round(root.height * root.maskScale)))
    }

    // RAIN — physically last; refracts the whole composited UI
    ShaderEffect {
        id: rainEffect
        anchors.fill: parent
        visible: root.rainEnabled

        property variant source: root.includeGlassPane ? glassCapture : srcCapture
        property variant u_mask: maskCapture
        property vector2d resolution: Qt.vector2d(width, height)
        property real u_quality: root.u_quality
        property real u_density: root.u_density
        property real u_debug: root.u_debug
        property real u_time: 0.0

        fragmentShader: "effects/StaticRainUI.qsb"
    }
}
