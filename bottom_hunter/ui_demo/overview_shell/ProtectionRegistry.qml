// ProtectionRegistry — dynamic UI-protection zone registry (production
// hardening, STEP 2). Protection zones are derived from REAL Item geometry
// via mapToItem() — no hardcoded magic coordinates. Both the rain importance
// mask and the readability mask consume this registry; shaders never know
// about widgets. Card moves / window resizes / late font layout all trigger
// a rebuild, so masks automatically follow the UI.
//
// Sources are RAW content rects + importance level; each mask applies its
// own dilation:
//   rain importance mask:  critical +28px, normal +20px (full exclusion)
//   readability mask:      critical +32px, normal +24px (feathered 22px)
import QtQuick

Item {
    id: registry

    // GlassMetricCard instances (value/label/hint = critical/normal/normal);
    // registered by the delegates themselves via registerCard()
    property var cards: []
    // header items (title, subtitle, status badge, date, tag) — normal level
    property var normalItems: []
    // coordinate space for zone geometry (sceneContent)
    property Item sceneRoot: null

    function registerCard(card) {
        const next = cards.slice()
        next.push(card)
        cards = next
        Qt.callLater(rebuild)
    }

    // [{x, y, w, h, level}] — raw content rects, registry coordinates
    property var sources: []
    // subset with level "critical" (metric values / prices)
    property var metricValueRects: []
    // NOTE: no explicit signal — the `sources` property already provides the
    // automatic sourcesChanged signal consumed by the masks via Connections.

    function rebuild() {
        if (sceneRoot === null) return
        const src = []
        const vals = []

        const pushRect = (item, rx, ry, rw, rh, level) => {
            if (item === null || rw <= 0 || rh <= 0) return
            const p = item.mapToItem(sceneRoot, rx, ry)
            src.push({ x: p.x, y: p.y, w: rw, h: rh, level: level })
            if (level === "critical") vals.push({ x: p.x, y: p.y, w: rw, h: rh })
        }

        // metric cards: value text = critical; label/hint = normal important
        for (let i = 0; i < cards.length; ++i) {
            const card = cards[i]
            if (card === null || card === undefined) continue
            const vr = card.valueRect
            const vp = card.mapToItem(sceneRoot, vr.x, vr.y)
            if (vr.width > 0) {
                src.push({ x: vp.x, y: vp.y, w: vr.width, h: vr.height, level: "critical" })
                vals.push({ x: vp.x, y: vp.y, w: vr.width, h: vr.height })
            }
            const lr = card.labelRect
            const lp = card.mapToItem(sceneRoot, lr.x, lr.y)
            if (lr.width > 0) src.push({ x: lp.x, y: lp.y, w: lr.width, h: lr.height, level: "normal" })
            const hr = card.hintRect
            const hp = card.mapToItem(sceneRoot, hr.x, hr.y)
            if (hr.width > 0) src.push({ x: hp.x, y: hp.y, w: hr.width, h: hr.height, level: "normal" })
        }

        // header content (headings / status / date / buttons text) — normal
        for (let j = 0; j < normalItems.length; ++j) {
            const it = normalItems[j]
            if (it === null || it === undefined) continue
            pushRect(it, 0, 0, it.width, it.height, "normal")
        }

        sources = src
        metricValueRects = vals
        sourcesChanged()
    }

    // true union bounds of all sources (for viewport containment checks)
    function bounds() {
        if (sources.length === 0) return Qt.rect(0, 0, 0, 0)
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
        for (let i = 0; i < sources.length; ++i) {
            const s = sources[i]
            x0 = Math.min(x0, s.x); y0 = Math.min(y0, s.y)
            x1 = Math.max(x1, s.x + s.w); y1 = Math.max(y1, s.y + s.h)
        }
        return Qt.rect(x0, y0, x1 - x0, y1 - y0)
    }

    Component.onCompleted: Qt.callLater(rebuild)
}
