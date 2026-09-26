// PHASE 5 product shell. Routing and presentation only; no backend access.
// The Crystal Rain Glass pipeline is composited here as:
// transparent product UI -> alpha-preserving screen-space rain surface.
// There is intentionally no application background: the desktop is supplied
// by the operating-system compositor through the transparent QQuickView.
import QtQuick
import "../components"
import "../overview_shell"
import "../primitives"

Item {
    id: root
    objectName: "applicationShell"
    width: 1440
    height: 900

    property bool rainEnabled: true
    property string alertNotice: ""
    readonly property vector2d rainCaptureTextureSize: rainSurface.captureTextureSize
    readonly property vector2d rainMaskTextureSize: rainSurface.rainMaskTextureSize

    readonly property var pageIds: [
        "overview", "watchlist", "research", "strategy", "research_assistant", "report",
        "import", "status", "chart"
    ]
    readonly property var pageTitles: [
        "总览", "自选", "研究", "因子策略", "投研助手", "报告", "导入", "状态", "K线"
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
        case "strategy": return strategyPageLoader.item !== null
        case "research_assistant": return researchAssistantPageLoader.item !== null
        case "report": return reportPageLoader.item !== null
        case "import": return importPageLoader.item !== null
        case "status": return statusPageLoader.item !== null
        case "chart": return chartPageLoader.item !== null
        default: return false
        }
    }

    // The product UI has no full-window fill. It is captured once by
    // RainGlassSurface; the source remains interactive while its direct
    // rendering is hidden. Empty pixels therefore stay transparent to the
    // real desktop instead of revealing an application-owned image.
    Item {
        id: sceneContent
        anchors.fill: parent

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
                id: strategyPageLoader
                objectName: "strategyPageLoader"
                anchors.fill: parent
                active: root.currentPage === "strategy"
                source: active ? Qt.resolvedUrl("strategy/Strategy.qml") : ""
            }
            Loader {
                id: researchAssistantPageLoader
                objectName: "research_assistantPageLoader"
                anchors.fill: parent
                active: root.currentPage === "research_assistant"
                source: active ? Qt.resolvedUrl("research_assistant/ResearchAssistant.qml") : ""
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
                GlassText {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: root.pageTitles[root.currentIndex]
                    tone: "primary"
                    sizeHint: 23
                    font.weight: Font.Bold
                    font.family: "Noto Sans CJK SC"
                }
                GlassText {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "页面正在加载，如持续显示请检查 ViewModel 注入。"
                    tone: "muted"
                    sizeHint: 13
                    font.family: "Noto Sans CJK SC"
                }
            }
        }

        GlassSurface {
            id: alertToast
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.rightMargin: 28
            anchors.topMargin: 28
            width: Math.min(520, parent.width * 0.48)
            height: 62
            visible: root.alertNotice !== ""
            z: 20
            tintAlpha: 0.84
            surfaceRadius: GlassTokens.containerRadius
            accentTint: "#D9F3E4"
            accentStrength: 0.24
            GlassText {
                anchors.fill: parent
                anchors.margins: 14
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.WordWrap
                text: root.alertNotice
                tone: "primary"
                sizeHint: 13
            }
        }
        Connections {
            target: (typeof priceAlertVm !== "undefined") ? priceAlertVm : null
            function onAlertTriggered(message) {
                root.alertNotice = message
                toastTimer.restart()
            }
        }
        Timer {
            id: toastTimer
            interval: 9000
            onTriggered: root.alertNotice = ""
        }
    }

    // Coarse production-safe importance mask. Rain remains full strength on
    // the window edge/nav/negative space and is reduced over dense financial
    // content. The shader's droplet optics and distribution stay untouched.
    Item {
        id: importanceMask
        anchors.fill: parent
        visible: false

        Rectangle { anchors.fill: parent; color: "#FFFFFF" }
        Rectangle {
            x: content.x
            y: content.y
            width: content.width
            height: content.height
            color: "#A8A8A8"
        }
    }

    // Physically last: screen-space water lenses refract application pixels;
    // over empty space they render only translucent water highlights, leaving
    // the live desktop visible. Qt never captures or stores desktop pixels.
    RainGlassSurface {
        id: rainSurface
        objectName: "productRainGlassSurface"
        anchors.fill: parent
        sourceItem: sceneContent
        maskSource: importanceMask
        includeGlassPane: false
        rainEnabled: root.rainEnabled
    }
}
