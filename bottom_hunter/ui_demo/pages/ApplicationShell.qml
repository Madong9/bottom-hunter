// ApplicationShell — PHASE 3-A multi-page shell + native routing.
//
// Reuses the FROZEN GlassNavRail for navigation visual and drives routing
// from the NavigationController (context property `navController`). Every
// page is an empty placeholder at this stage — no business data yet.
//
// No new shaders, no layout redesign: nav rail + a single placeholder pane.
import QtQuick
import QtQuick.Controls.Basic
import "../components"

Item {
    id: root
    width: 1440
    height: 900

    // page ids in the same order as GlassNavRail's built-in model
    readonly property var pageIds: [
        "overview", "watchlist", "research", "report",
        "import", "status", "chart"
    ]
    readonly property var pageTitles: [
        "总览", "自选", "研究", "报告", "导入", "状态", "K线"
    ]

    // index of the current page in pageIds
    readonly property int currentIndex: {
        const id = (typeof navController !== "undefined" && navController !== null)
            ? navController.currentPage : "overview"
        const i = pageIds.indexOf(id)
        return i >= 0 ? i : 0
    }

    GlassNavRail {
        id: navRail
        x: 20
        y: 20
        width: 72
        height: parent.height - 40
        currentIndex: root.currentIndex
        onNavigate: (index) => {
            if (index >= 0 && index < root.pageIds.length
                && typeof navController !== "undefined" && navController !== null) {
                navController.navigate(root.pageIds[index])
            }
        }
    }

    // ---- content pane (placeholder; replaced per-page in later phases) ----
    Item {
        id: content
        x: navRail.x + navRail.width + 20
        y: 20
        width: parent.width - x - 20
        height: parent.height - 40

        Column {
            anchors.left: parent.left
            anchors.top: parent.top
            spacing: 8

            Text {
                text: root.pageTitles[root.currentIndex]
                color: "#f2f4f8"
                font.pixelSize: 23
                font.weight: Font.Bold
                font.family: "Noto Sans CJK SC"
            }
            Text {
                text: root.pageTitles[root.currentIndex] + " module ready"
                color: "#8b93a2"
                font.pixelSize: 14
                font.family: "Noto Sans CJK SC"
            }
            Text {
                text: "PHASE 3-A placeholder — no business data wired yet"
                color: "#5b6270"
                font.pixelSize: 12
                font.family: "Noto Sans CJK SC"
            }
        }
    }
}
