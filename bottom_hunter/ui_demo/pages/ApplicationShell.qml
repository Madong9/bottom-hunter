// PHASE 5 product shell. Routing and presentation only; no backend access.
import QtQuick
import "../components"

Item {
    id: root
    objectName: "applicationShell"
    width: 1440
    height: 900

    readonly property var pageIds: [
        "overview", "watchlist", "research", "report",
        "import", "status", "chart"
    ]
    readonly property var pageTitles: [
        "总览", "自选", "研究", "报告", "导入", "状态", "K线"
    ]
    readonly property string currentPage: {
        const requested = (typeof navController !== "undefined" && navController !== null)
            ? navController.currentPage : "overview"
        return pageIds.indexOf(requested) >= 0 ? requested : "overview"
    }
    readonly property int currentIndex: pageIds.indexOf(currentPage)
    readonly property bool currentPageLoaded: {
        switch (currentPage) {
        case "overview": return overviewPageLoader.item !== null
        case "watchlist": return watchlistPageLoader.item !== null
        case "research": return researchPageLoader.item !== null
        case "report": return reportPageLoader.item !== null
        case "import": return importPageLoader.item !== null
        case "status": return statusPageLoader.item !== null
        case "chart": return chartPageLoader.item !== null
        default: return false
        }
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
                    && typeof navController !== "undefined" && navController !== null)
                navController.navigate(root.pageIds[index])
        }
    }

    Item {
        id: content
        x: navRail.x + navRail.width + 20
        y: 20
        width: parent.width - x - 20
        height: parent.height - 40

        Loader {
            id: overviewPageLoader
            objectName: "overviewPageLoader"
            anchors.fill: parent
            active: root.currentPage === "overview"
            source: active ? Qt.resolvedUrl("overview/Overview.qml") : ""
        }
        Loader {
            id: watchlistPageLoader
            objectName: "watchlistPageLoader"
            anchors.fill: parent
            active: root.currentPage === "watchlist"
            source: active ? Qt.resolvedUrl("watchlist/Watchlist.qml") : ""
        }
        Loader {
            id: researchPageLoader
            objectName: "researchPageLoader"
            anchors.fill: parent
            active: root.currentPage === "research"
            source: active ? Qt.resolvedUrl("research/Research.qml") : ""
        }
        Loader {
            id: reportPageLoader
            objectName: "reportPageLoader"
            anchors.fill: parent
            active: root.currentPage === "report"
            source: active ? Qt.resolvedUrl("report/Report.qml") : ""
        }
        Loader {
            id: importPageLoader
            objectName: "importPageLoader"
            anchors.fill: parent
            active: root.currentPage === "import"
            source: active ? Qt.resolvedUrl("import/Import.qml") : ""
        }
        Loader {
            id: statusPageLoader
            objectName: "statusPageLoader"
            anchors.fill: parent
            active: root.currentPage === "status"
            source: active ? Qt.resolvedUrl("status/Status.qml") : ""
        }
        Loader {
            id: chartPageLoader
            objectName: "chartPageLoader"
            anchors.fill: parent
            active: root.currentPage === "chart"
            source: active ? Qt.resolvedUrl("chart/Chart.qml") : ""
        }

        Column {
            visible: !root.currentPageLoaded
            anchors.centerIn: parent
            spacing: 8
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.pageTitles[root.currentIndex]
                color: "#f2f4f8"
                font.pixelSize: 23
                font.weight: Font.Bold
                font.family: "Noto Sans CJK SC"
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "页面正在加载，如持续显示请检查 ViewModel 注入。"
                color: "#8b93a2"
                font.pixelSize: 13
                font.family: "Noto Sans CJK SC"
            }
        }
    }
}
