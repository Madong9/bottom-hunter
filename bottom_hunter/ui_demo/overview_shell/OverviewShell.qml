// OverviewShell — Bottom Hunter 总览页外壳 Crystal Clear Glass POC (v2).
// (ui_demo POC only: shell + global RainGlassSurface; no business logic,
//  no other pages, formal QtWidgets GUI untouched.)
//
// FINAL COMPOSITING ORDER (review acceptance):
//   sceneContent
//     Environment          (accepted procedural night city, upper-area hf
//                           features for glass readability)
//     GlassPanels          (clear nav rail, toolbar strip, metric cards —
//                           clear neutral tints, thick-glass edges)
//     UIChrome             (title, subtitle, date, chip, card text — nearly
//                           fully opaque content)
//   ↓ COMPOSITED SCENE CAPTURE  (RainGlassSurface.srcCapture,
//                                hideSource = true — sceneContent is NOT
//                                duplicate-drawn underneath)
//   ↓ RainGlassSurface / StaticRainUI (frozen rain material + importance
//                                       mask) — physically LAST
//   ↓ Viewer
//
// Rain is allowed in front of the UI (refracts card borders, nav edges,
// toolbar edges, non-critical content). Critical content (titles, values,
// chip) is protected by the low-resolution importance mask.
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects
import "../components"

Item {
    id: root
    width: 1440
    height: 900

    // mode: "shell" (rain on) | "glass" (rain off) | "debug" (rain + rings)
    //     | "readability_debug" (rain + zone overlays, mask audit)
    property string mode: "shell"
    readonly property bool rainOn: mode !== "glass"
    readonly property bool debugOn: mode === "debug"
    readonly property bool readDebug: mode === "readability_debug"

    // read-only introspection for the launcher (texture size proof)
    readonly property vector2d captureTextureSize: surface.captureTextureSize

    // ================= COMPOSITED SCENE (captured as one texture) ==========
    Item {
        id: sceneContent
        anchors.fill: parent

        // ---- 1. environment (accepted MaterialLab night city) --------------
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
                    let s = seed >>> 0
                    function rnd() {
                        s = (s + 0x6D2B79F5) >>> 0
                        let t = s
                        t = Math.imul(t ^ (t >>> 15), t | 1)
                        t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
                        return ((t ^ (t >>> 14)) >>> 0) / 4294967296
                    }
                    for (let i = 0; i < 150; ++i) {
                        const x = rnd() * w
                        const y = rnd() * h * 0.55
                        const a = 0.20 + rnd() * 0.60
                        const sz = rnd() < 0.85 ? 0.8 : 1.2
                        ctx.fillStyle = "rgba(210,225,255," + a.toFixed(3) + ")"
                        ctx.fillRect(x, y, sz, sz)
                    }
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
                    const haze = ctx.createLinearGradient(0, h * 0.55, 0, h * 0.92)
                    haze.addColorStop(0, "rgba(58,84,118,0)")
                    haze.addColorStop(0.7, "rgba(64,92,128,0.20)")
                    haze.addColorStop(1, "rgba(70,100,140,0.30)")
                    ctx.fillStyle = haze
                    ctx.fillRect(0, h * 0.5, w, h * 0.42)
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
                    const street = ctx.createLinearGradient(0, h * 0.97, 0, h)
                    street.addColorStop(0, "#05070C")
                    street.addColorStop(1, "#020305")
                    ctx.fillStyle = street
                    ctx.fillRect(0, h * 0.97, w, h * 0.03)
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
                    // ---- v2: upper-area high-frequency features (behind the
                    //      card row) so the clear glass / refraction reads:
                    //      soft vertical edges, distant warm points, faint
                    //      cool reflections. Small & specific — no bokeh.
                    for (let i = 0; i < 7; ++i) {
                        const vx = w * (0.06 + i * 0.145) + rnd() * 24
                        const edge = ctx.createLinearGradient(vx - 10, 0, vx + 10, 0)
                        edge.addColorStop(0, "rgba(150,180,215,0)")
                        edge.addColorStop(0.5, "rgba(150,180,215,0.09)")
                        edge.addColorStop(1, "rgba(150,180,215,0)")
                        ctx.fillStyle = edge
                        ctx.fillRect(vx - 10, h * 0.04, 20, h * 0.24)
                    }
                    const warmZones = [[w * 0.28, h * 0.10], [w * 0.64, h * 0.13]]
                    for (let i = 0; i < warmZones.length; ++i) {
                        const wx = warmZones[i][0], wy = warmZones[i][1]
                        const g = ctx.createRadialGradient(wx, wy, 1, wx, wy, 30)
                        g.addColorStop(0, "rgba(255,205,140,0.32)")
                        g.addColorStop(1, "rgba(255,205,140,0)")
                        ctx.fillStyle = g
                        ctx.beginPath(); ctx.arc(wx, wy, 30, 0, Math.PI * 2); ctx.fill()
                        ctx.fillStyle = "rgba(255,225,180,0.70)"
                        ctx.fillRect(wx - 1, wy - 1, 2, 2)
                    }
                    const coolZones = [[w * 0.45, h * 0.075], [w * 0.80, h * 0.20]]
                    for (let i = 0; i < coolZones.length; ++i) {
                        const cx2 = coolZones[i][0], cy2 = coolZones[i][1]
                        const g2 = ctx.createRadialGradient(cx2, cy2, 1, cx2, cy2, 24)
                        g2.addColorStop(0, "rgba(140,180,235,0.24)")
                        g2.addColorStop(1, "rgba(140,180,235,0)")
                        ctx.fillStyle = g2
                        ctx.beginPath(); ctx.arc(cx2, cy2, 24, 0, Math.PI * 2); ctx.fill()
                    }
                }
                Component.onCompleted: requestPaint()
                onWidthChanged: requestPaint()
                onHeightChanged: requestPaint()
            }
        }

        // ---- 1b. environment readability attenuation (LAST env step) -------
        // Pipeline inside Environment (unchanged overall compositing order):
        //   base sky/city -> light streaks -> warm/cool highlights -> THIS
        // Attenuates bright/high-frequency environment features behind
        // critical content, driven by the feathered readabilityMask. Soft
        // (not binary), runs BEFORE glass panels and UI chrome — never
        // touches text. No dark boxes: highlights -90%, base only -10%.
        ShaderEffectSource {
            id: envCapture
            anchors.fill: parent
            sourceItem: environment
            hideSource: true
            visible: false
            textureSize: Qt.size(root.width, root.height)
        }

        ShaderEffect {
            id: envReadability
            anchors.fill: parent

            property variant source: envCapture
            property variant u_mask: readMaskCapture
            property vector2d resolution: Qt.vector2d(width, height)

            fragmentShader: "effects/EnvReadability.qsb"
        }

        // ---- 2. glass panels (clear slabs; NO dark fills) -------------------
        Item {
            id: glassPanels
            anchors.fill: parent

            // 导航 rail (clear, slim, accepted layout)
            GlassNavRail {
                id: navRail
                x: 20
                y: 20
                width: 72
                height: parent.height - 40
                currentIndex: 0
                onNavigate: (index) => navRail.currentIndex = index
            }

            // 顶部栏 glass strip (very weak neutral tint, thin optical edges)
            Rectangle {
                id: toolbarGlass
                x: navRail.x + navRail.width + 20
                y: 20
                width: root.width - x - 20
                height: 64
                radius: 14
                color: Qt.rgba(1, 1, 1, 0.018)   // toolbar glass 0.015-0.040
                border.width: 0

                Rectangle {
                    anchors { top: parent.top; left: parent.left; right: parent.right }
                    anchors.margins: 1
                    height: 1
                    radius: 1
                    color: Qt.rgba(1, 1, 1, 0.10)
                }
                Rectangle {
                    anchors { bottom: parent.bottom; left: parent.left; right: parent.right }
                    anchors.margins: 1
                    height: 1
                    color: Qt.rgba(0, 0, 0, 0.08)
                }
            }
        }

        // ---- 3. UI chrome (content stays nearly fully opaque) ---------------
        Item {
            id: chrome
            anchors.fill: parent

            // 顶部栏 content
            Item {
                id: topBar
                x: toolbarGlass.x
                y: toolbarGlass.y
                width: toolbarGlass.width
                height: toolbarGlass.height

                Column {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2

                    Text {
                        text: "工作台"
                        color: "#f2f4f8"
                        font.pixelSize: 23
                        font.weight: Font.Bold
                        font.family: "Noto Sans CJK SC"
                    }
                    Text {
                        text: "捕捉超跌后的结构性反转，不追逐单一指标"
                        color: "#8b93a2"
                        font.pixelSize: 12
                        font.family: "Noto Sans CJK SC"
                    }
                }

                Row {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 12

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Crystal Clear Glass POC"
                        color: "#5b6270"
                        font.pixelSize: 11
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "2026-08-31"
                        color: "#9aa3b2"
                        font.pixelSize: 12
                    }
                    StatusBadge {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "就绪"
                        tone: "idle"
                    }
                }
            }

            // 总览卡片 (4 clear glass plates, static POC data)
            Row {
                id: cardsRow
                x: topBar.x
                y: topBar.y + topBar.height + 20
                width: topBar.width
                spacing: 16

                Repeater {
                    model: [
                        { label: "今日机会", value: "--",      hint: "等待最新扫描",      accent: "#07C160" },
                        { label: "数据健康", value: "--",      hint: "行情完整度",        accent: "#F3BA2F" },
                        { label: "信号验证", value: "--",      hint: "近30天5日持有胜率", accent: "#2D8CF0" },
                        { label: "模拟组合", value: "1.0000",  hint: "三阶段框架净值",    accent: "#8854D0" }
                    ]
                    delegate: GlassMetricCard {
                        width: (cardsRow.width - 3 * cardsRow.spacing) / 4
                        height: 91
                        label: modelData.label
                        value: modelData.value
                        hint: modelData.hint
                        accent: modelData.accent
                    }
                }
            }
        }
    }

    // ================= IMPORTANCE / EXCLUSION MASK (low-res data texture) ===
    // White = normal rain density, dark = low density (protected). A small set
    // of rectangular zones over critical content (titles, values, chip) — NOT
    // per-widget QObjects. Feeds StaticRainUI.u_mask; reduces droplet PRESENCE
    // only, never removes the optical glass.
    Item {
        id: importanceMask
        anchors.fill: parent
        visible: false   // rendered via maskCapture only

        Rectangle {
            anchors.fill: parent
            color: "#FFFFFF"
        }

        // LOW density zones — PRE-DILATED beyond actual text bounds so no
        // droplet body (max influence ~14.4px) can touch protected content:
        // extremely important metric value fields dilated 28px (range
        // 24-32), normal critical text / date / status dilated 20px (range
        // 18-24). Full exclusion inside the zone (factor 0) — affects
        // droplet PRESENCE only; glass, refraction elsewhere and edge
        // highlights stay untouched. Card margins / panel edges stay white
        // (normal density).
        Repeater {
            model: [
                { x: 96,   y: 6,   w: 340, h: 86 },  // 工作台 title + subtitle (+20px)
                { x: 1100, y: 14,  w: 310, h: 74 },  // POC tag + date + 就绪 chip (+20px)
                { x: 114,  y: 107, w: 156, h: 84 },  // card 1 label/value/hint (+28px)
                { x: 445,  y: 107, w: 156, h: 84 },  // card 2 label/value/hint (+28px)
                { x: 776,  y: 107, w: 156, h: 84 },  // card 3 label/value/hint (+28px)
                { x: 1107, y: 107, w: 156, h: 84 }   // card 4 label/value/hint (+28px)
            ]
            delegate: Rectangle {
                x: modelData.x
                y: modelData.y
                width: modelData.w
                height: modelData.h
                radius: 8
                color: "#000000"   // full exclusion (presence only)
            }
        }
    }

    // ================= READABILITY MASK (soft, feathered; NOT the rain mask)
    // Purpose: attenuate high-brightness environment features behind critical
    // financial content — NOT a dark box, NOT visible. Geometry = the same
    // protected content as the rain mask, expanded further with FEATHERED
    // edges (shadowBlur 22px):
    //   critical numeric fields (metric values): +32px (range 28-36)
    //   normal important text (title, chip/date/status): +24px (range 20-28)
    //   edge feather: 22px (range 16-28)
    // Plus the deterministic vertical-streak strips where they cross metric
    // cards (streaks stay untouched in empty/background regions).
    // Attenuation in EnvReadability: highlights -90%, base city -10%, soft.
    Item {
        id: readabilityMask
        anchors.fill: parent
        visible: false   // rendered via readMaskCapture only

        Canvas {
            anchors.fill: parent
            onPaint: {
                const ctx = getContext("2d")
                ctx.reset()
                // feathered white zones on transparent canvas; R channel =
                // protection strength sampled by EnvReadability.u_mask
                const FEATHER = 22
                ctx.shadowColor = "rgba(255,255,255,1)"
                ctx.shadowBlur = FEATHER
                ctx.shadowOffsetX = 0
                ctx.shadowOffsetY = 0
                ctx.fillStyle = "rgba(255,255,255,1)"
                // critical numeric fields: metric value zone +32px
                const cards = [112, 443, 774, 1105]
                for (let i = 0; i < 4; ++i) {
                    ctx.fillRect(cards[i] - 2, 103, 164, 92)
                }
                // normal important text: title +24px, chip/date/status +24px
                ctx.fillRect(92, 2, 348, 94)
                ctx.fillRect(1096, 10, 318, 82)
                // vertical streak strips where they cross metric cards
                // (deterministic streak x from the seeded env Canvas)
                const streakX = [297.3, 525.9, 714.7, 938.2, 1142.5, 1346.0]
                for (let i = 0; i < streakX.length; ++i) {
                    ctx.fillRect(streakX[i] - 15, 104, 30, 91)
                }
            }
            Component.onCompleted: requestPaint()
        }
    }

    // readability mask capture (low cost; R = feathered protection strength)
    ShaderEffectSource {
        id: readMaskCapture
        anchors.fill: parent
        sourceItem: readabilityMask
        visible: false
        smooth: true
    }

    // ================= RAIN GLASS — physically LAST ==========================
    RainGlassSurface {
        id: surface
        anchors.fill: parent
        sourceItem: sceneContent
        maskSource: importanceMask
        includeGlassPane: false
        rainEnabled: root.rainOn
        u_debug: root.debugOn ? 1.0 : 0.0
    }

    // ================= MASK AUDIT OVERLAY (readability_debug only) ============
    // Lab diagnostic: rain protection zones (red) vs readability protection
    // zones (blue). Never part of the UI.
    Item {
        id: maskAudit
        anchors.fill: parent
        visible: root.readDebug

        Repeater {
            model: [
                { x: 96,   y: 6,   w: 340, h: 86 },  // rain: title +20px
                { x: 1100, y: 14,  w: 310, h: 74 },  // rain: chip +20px
                { x: 114,  y: 107, w: 156, h: 84 },  // rain: card 1 value +28px
                { x: 445,  y: 107, w: 156, h: 84 },  // rain: card 2
                { x: 776,  y: 107, w: 156, h: 84 },  // rain: card 3
                { x: 1107, y: 107, w: 156, h: 84 }   // rain: card 4
            ]
            delegate: Rectangle {
                x: modelData.x; y: modelData.y
                width: modelData.w; height: modelData.h
                radius: 8
                color: Qt.rgba(1, 0.36, 0.36, 0.18)
                border.width: 1
                border.color: Qt.rgba(1, 0.36, 0.36, 0.70)
            }
        }

        Repeater {
            model: [
                { x: 92,   y: 2,   w: 348, h: 94 },  // readability: title +24px
                { x: 1096, y: 10,  w: 318, h: 82 },  // readability: chip +24px
                { x: 110,  y: 103, w: 164, h: 92 },  // readability: card 1 value +32px
                { x: 441,  y: 103, w: 164, h: 92 },  // readability: card 2
                { x: 772,  y: 103, w: 164, h: 92 },  // readability: card 3
                { x: 1103, y: 103, w: 164, h: 92 }   // readability: card 4
            ]
            delegate: Rectangle {
                x: modelData.x; y: modelData.y
                width: modelData.w; height: modelData.h
                radius: 8
                color: Qt.rgba(0.30, 0.64, 1.0, 0.14)
                border.width: 1
                border.color: Qt.rgba(0.30, 0.64, 1.0, 0.65)
            }
        }
    }
}
