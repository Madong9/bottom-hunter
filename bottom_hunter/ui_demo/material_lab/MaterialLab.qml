// CrystalGlassMaterialLab — three-layer material study (no app GUI, no PHASE 2).
//
//   layer 1: recognizable environment background (procedural night city)
//   layer 2: CLEAR colorless optical glass (subtle blur + weak refraction)
//   layer 3: static realistic small rain droplets (screen-space lenses)
//
// `mode` selects the visible stack for the lab screenshots:
//   "background"        → layer 1 only
//   "glass"             → layers 1+2
//   "rain"              → layers 1+2+3
//   "debug"             → layers 1+2+3 with u_debug=1 (droplet diameter proof)
//   "calibration"       → layers 1+2+3 + refraction calibration patch (no rings)
//   "final_rain"        → same as "rain" (final polish output)
//   "final_debug"       → same as "debug" (final polish output)
//   "final_calibration" → same as "calibration" (final polish output)
//
// Capture chain (no per-frame texture creation):
//   environment ─┐
//   envCapture (ShaderEffectSource, hidden) → glassEffect (opaque)
//   glassEffect ─┐
//   glassCapture (ShaderEffectSource, hidden) → rainEffect (opaque, top)
// The StaticRain source therefore samples the Environment + Clear Glass
// composite scene, as required.

import QtQuick
import QtQuick.Effects

Item {
    id: root
    implicitWidth: 1440
    implicitHeight: 900

    property string mode: "background"
    readonly property bool glassOn: mode !== "background"
    readonly property bool rainOn: mode !== "background" && mode !== "glass"
    readonly property bool calibOn:
        mode === "debug" || mode === "calibration"
        || mode === "final_debug" || mode === "final_calibration"

    // read-only introspection for the launcher (DPR / texture size proof)
    readonly property vector2d captureTextureSize: Qt.vector2d(
        envCapture.textureSize.width, envCapture.textureSize.height)
    readonly property real captureDpr: 1.0

    // ---- layer 1: environment background (procedural, deterministic) --------
    // A recognizable night city seen through a window: sky + stars + small
    // moon, two skyline rows with sparse lit windows, street with lamps.
    // No giant bokeh blobs — every light source is small and specific.
    Item {
        id: environment
        anchors.fill: parent

        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0.00; color: "#04070E" }
                GradientStop { position: 0.45; color: "#081120" }
                GradientStop { position: 0.78; color: "#102032" }
                GradientStop { position: 1.00; color: "#1B2C40" }
            }
        }

        Canvas {
            id: sceneCanvas
            anchors.fill: parent
            property int seed: 20260830
            onPaint: {
                const ctx = getContext("2d")
                ctx.reset()
                const w = width, h = height
                // deterministic PRNG (mulberry32) — stable across runs
                let s = seed >>> 0
                function rnd() {
                    s = (s + 0x6D2B79F5) >>> 0
                    let t = s
                    t = Math.imul(t ^ (t >>> 15), t | 1)
                    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
                    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
                }
                // stars (upper 55%, mostly 1px)
                for (let i = 0; i < 150; ++i) {
                    const x = rnd() * w
                    const y = rnd() * h * 0.55
                    const a = 0.20 + rnd() * 0.60
                    const sz = rnd() < 0.85 ? 0.8 : 1.2
                    ctx.fillStyle = "rgba(210,225,255," + a.toFixed(3) + ")"
                    ctx.fillRect(x, y, sz, sz)
                }
                // moon: small disc + modest halo (recognizable, not a blob)
                const mx = w * 0.82, my = h * 0.16
                const halo = ctx.createRadialGradient(mx, my, 4, mx, my, 80)
                halo.addColorStop(0, "rgba(220,230,245,0.30)")
                halo.addColorStop(0.35, "rgba(200,215,240,0.10)")
                halo.addColorStop(1, "rgba(200,215,240,0)")
                ctx.fillStyle = halo
                ctx.beginPath(); ctx.arc(mx, my, 80, 0, Math.PI * 2); ctx.fill()
                ctx.fillStyle = "rgba(232,238,248,0.95)"
                ctx.beginPath(); ctx.arc(mx, my, 16, 0, Math.PI * 2); ctx.fill()
                ctx.fillStyle = "rgba(175,190,212,0.35)"
                ctx.beginPath(); ctx.arc(mx - 5, my + 4, 4, 0, Math.PI * 2); ctx.fill()
                ctx.beginPath(); ctx.arc(mx + 6, my - 5, 2.6, 0, Math.PI * 2); ctx.fill()
                // horizon haze (city light pollution)
                const haze = ctx.createLinearGradient(0, h * 0.55, 0, h * 0.92)
                haze.addColorStop(0, "rgba(58,84,118,0)")
                haze.addColorStop(0.7, "rgba(64,92,128,0.20)")
                haze.addColorStop(1, "rgba(70,100,140,0.30)")
                ctx.fillStyle = haze
                ctx.fillRect(0, h * 0.5, w, h * 0.42)
                // building row: baseY = street line, bh = height, sparse windows
                function row(baseY, minH, maxH, color, winP, winW, winH, gapX, gapY, warm) {
                    let x = -20
                    while (x < w + 20) {
                        const bw = 34 + rnd() * 90
                        const bh = minH + rnd() * (maxH - minH)
                        ctx.fillStyle = color
                        ctx.fillRect(x, baseY - bh, bw, bh + 30)
                        if (winP > 0) {
                            const cols = Math.floor((bw - 8) / gapX)
                            const rowsN = Math.floor((bh - 10) / gapY)
                            for (let c = 0; c < cols; ++c) {
                                for (let rn = 0; rn < rowsN; ++rn) {
                                    if (rnd() > winP) continue
                                    const wx = x + 6 + c * gapX
                                    const wy = baseY - bh + 8 + rn * gapY
                                    const a = 0.35 + rnd() * 0.55
                                    ctx.fillStyle = (warm && rnd() < 0.6)
                                        ? "rgba(255,205,130," + a.toFixed(3) + ")"
                                        : "rgba(170,210,255," + (a * 0.85).toFixed(3) + ")"
                                    ctx.fillRect(wx, wy, winW, winH)
                                }
                            }
                        }
                        x += bw + 4 + rnd() * 26
                    }
                }
                row(h * 0.86, 90, 210, "#0B1220", 0.10, 2, 3, 9, 11, false)
                row(h * 0.97, 150, 330, "#070C15", 0.16, 3, 4, 12, 14, true)
                // street strip
                const street = ctx.createLinearGradient(0, h * 0.97, 0, h)
                street.addColorStop(0, "#05070C")
                street.addColorStop(1, "#020305")
                ctx.fillStyle = street
                ctx.fillRect(0, h * 0.97, w, h * 0.03)
                // a few street lamps (small glows)
                for (let i = 0; i < 5; ++i) {
                    const lx = w * (0.08 + i * 0.21) + rnd() * 40
                    const ly = h * 0.965
                    const g = ctx.createRadialGradient(lx, ly, 0.5, lx, ly, 24)
                    g.addColorStop(0, "rgba(255,214,150,0.85)")
                    g.addColorStop(0.25, "rgba(255,190,120,0.22)")
                    g.addColorStop(1, "rgba(255,190,120,0)")
                    ctx.fillStyle = g
                    ctx.beginPath(); ctx.arc(lx, ly, 24, 0, Math.PI * 2); ctx.fill()
                    ctx.fillStyle = "rgba(255,230,190,0.9)"
                    ctx.fillRect(lx - 1, ly - 1, 2, 2)
                }
            }
            Component.onCompleted: requestPaint()
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
        }

        // ---- refraction calibration patch (LAB ONLY) ----------------------------
        // High-frequency optical test region behind the glass, in a corner
        // with real droplet coverage: thin building edge + warm light point +
        // cool light point + thin vertical lines + small label + dot matrix.
        // Droplets over it must visibly bend / displace / magnify everything —
        // proof that refraction is real. Material verification only; never
        // part of the formal UI.
        Item {
            id: calibPatch
            visible: root.calibOn
            x: 1172
            y: 630
            width: 220
            height: 140

            // thin white vertical lines
            Row {
                spacing: 30
                Repeater {
                    model: 6
                    Rectangle { width: 1; height: 54; color: "#EAF2FC"; opacity: 0.9 }
                }
            }
            // small monospace label
            Text {
                y: 62
                text: "REFR-CAL px"
                color: "#F4F8FE"
                opacity: 0.95
                font.pixelSize: 12
                font.family: "monospace"
            }
            // dot matrix
            Grid {
                y: 88
                columns: 14
                spacing: 8
                Repeater {
                    model: 42
                    Rectangle { width: 2; height: 2; color: "#DCE8F6"; opacity: 0.85 }
                }
            }
            // thin building edge: dark slab + 1px bright edge line
            Rectangle { x: 160; y: 0; width: 3; height: 54; color: "#04070C"; opacity: 0.9 }
            Rectangle { x: 163; y: 0; width: 1; height: 54; color: "#C8DCF2"; opacity: 0.8 }
            // warm light point (halo + core)
            Rectangle { x: 170; y: 6; width: 18; height: 18; radius: 9; color: "#30FFC97A" }
            Rectangle { x: 175; y: 11; width: 8; height: 8; radius: 4; color: "#FFC97A" }
            // cool light point (halo + core)
            Rectangle { x: 170; y: 32; width: 16; height: 16; radius: 8; color: "#2E9FC8FF" }
            Rectangle { x: 174; y: 36; width: 8; height: 8; radius: 4; color: "#9FC8FF" }
        }
    }

    // ---- layer 2: clear colorless optical glass ------------------------------
    // Captures the environment and re-draws it with subtle blur, very weak
    // refraction, near-white film and edge highlight. Opaque output covers
    // the (still visible) environment item.
    ShaderEffectSource {
        id: envCapture
        anchors.fill: parent
        sourceItem: environment
        hideSource: false
        visible: false
        textureSize: Qt.size(root.width, root.height)
    }

    ShaderEffect {
        id: glassEffect
        anchors.fill: parent
        visible: root.glassOn

        property variant source: envCapture
        property vector2d resolution: Qt.vector2d(width, height)
        property real u_blur: 0.75
        property real u_refract: 0.35
        property real u_tint: 0.018
        property real u_sat: 1.06

        fragmentShader: "effects/ClearGlass.qsb"
    }

    // ---- layer 3: static rain droplets ----------------------------------------
    // Source MUST sample the Environment + Clear Glass composite: glassEffect
    // is exactly that (opaque full-frame render of the processed environment).
    ShaderEffectSource {
        id: glassCapture
        anchors.fill: parent
        sourceItem: glassEffect
        hideSource: false
        visible: false
        textureSize: Qt.size(root.width, root.height)
    }

    ShaderEffect {
        id: rainEffect
        anchors.fill: parent
        visible: root.rainOn

        property variant source: glassCapture
        property vector2d resolution: Qt.vector2d(width, height)
        property real u_quality: 1.0
        property real u_density: 1.0
        property real u_debug:
            (mode === "debug" || mode === "final_debug") ? 1.0 : 0.0
        property real u_time: 0.0

        fragmentShader: "effects/StaticRain.qsb"
    }
}
