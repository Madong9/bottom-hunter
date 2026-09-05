// Consistent Apple-style outline symbols for the product navigation rail.
// Drawn as vectors instead of font glyphs so weight, baseline and scale remain
// identical on every Linux desktop.
import QtQuick

Canvas {
    id: root

    property string symbol: "overview"
    property color strokeColor: "#465D70"
    property real strokeWidth: 1.9

    implicitWidth: 22
    implicitHeight: 22
    antialiasing: true
    renderStrategy: Canvas.Cooperative

    onSymbolChanged: requestPaint()
    onStrokeColorChanged: requestPaint()
    onStrokeWidthChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    function line(ctx, points) {
        ctx.beginPath()
        ctx.moveTo(points[0][0], points[0][1])
        for (let i = 1; i < points.length; ++i)
            ctx.lineTo(points[i][0], points[i][1])
        ctx.stroke()
    }

    onPaint: {
        const ctx = getContext("2d")
        const sx = width / 24
        const sy = height / 24
        ctx.reset()
        ctx.scale(sx, sy)
        ctx.strokeStyle = strokeColor
        ctx.fillStyle = strokeColor
        ctx.lineWidth = strokeWidth
        ctx.lineCap = "round"
        ctx.lineJoin = "round"

        if (symbol === "overview") {
            line(ctx, [[4, 11], [12, 4], [20, 11]])
            line(ctx, [[6.5, 9.2], [6.5, 20], [17.5, 20], [17.5, 9.2]])
            line(ctx, [[10, 20], [10, 14], [14, 14], [14, 20]])
        } else if (symbol === "watchlist") {
            ctx.beginPath()
            for (let i = 0; i < 10; ++i) {
                const angle = -Math.PI / 2 + i * Math.PI / 5
                const radius = i % 2 === 0 ? 8.6 : 3.9
                const x = 12 + Math.cos(angle) * radius
                const y = 12 + Math.sin(angle) * radius
                if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
            }
            ctx.closePath(); ctx.stroke()
        } else if (symbol === "research") {
            ctx.beginPath(); ctx.arc(10.5, 10.5, 6.2, 0, Math.PI * 2); ctx.stroke()
            line(ctx, [[15.2, 15.2], [20.5, 20.5]])
        } else if (symbol === "report") {
            ctx.strokeRect(5, 3.5, 14, 17)
            line(ctx, [[8, 8], [16, 8]])
            line(ctx, [[8, 12], [16, 12]])
            line(ctx, [[8, 16], [14, 16]])
        } else if (symbol === "import") {
            line(ctx, [[12, 3.5], [12, 15]])
            line(ctx, [[7.8, 11], [12, 15.2], [16.2, 11]])
            line(ctx, [[5, 17], [5, 20], [19, 20], [19, 17]])
        } else if (symbol === "status") {
            ctx.beginPath(); ctx.arc(12, 12, 8.5, 0, Math.PI * 2); ctx.stroke()
            line(ctx, [[7, 12.5], [10, 12.5], [11.5, 8.5], [14, 16], [15.5, 12.5], [18, 12.5]])
        } else {
            line(ctx, [[4, 19.5], [4, 5]])
            line(ctx, [[4, 19.5], [20, 19.5]])
            line(ctx, [[6.5, 16], [10.2, 12], [13.2, 14], [19, 7]])
            line(ctx, [[15.5, 7], [19, 7], [19, 10.5]])
        }
    }
}
