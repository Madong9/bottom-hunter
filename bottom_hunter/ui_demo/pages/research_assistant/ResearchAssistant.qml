import QtQuick
import QtWebEngine
import "../../primitives"

GlassSurface {
    id: root
    objectName: "researchAssistantPage"
    tintAlpha: 0.42
    surfaceRadius: GlassTokens.pageRadius
    edgeContrast: GlassTokens.structuralEdgeContrast
    depthStrength: GlassTokens.structuralDepthStrength

    readonly property var vm: (typeof researchAssistantVm !== "undefined")
                              ? researchAssistantVm : null

    Component.onCompleted: {
        if (vm !== null && vm.autoStart && vm.canStart)
            vm.start()
    }

    Column {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 12

        Row {
            width: parent.width
            height: 48
            spacing: 10

            Column {
                width: parent.width - 374
                anchors.verticalCenter: parent.verticalCenter
                spacing: 3
                GlassText {
                    text: "AI 投研助手"
                    tone: "primary"
                    sizeHint: 21
                    font.weight: Font.Bold
                }
                GlassText {
                    text: "Query Router + Stock Resolver + 五 Agent · 已内嵌到 Bottom Hunter"
                    tone: "muted"
                    sizeHint: 11
                }
            }

            GlassSurface {
                width: 116
                height: 34
                anchors.verticalCenter: parent.verticalCenter
                appearanceSelectable: false
                surfaceRadius: GlassTokens.capsuleRadius(height)
                tintAlpha: 0.18
                accentTint: root.vm !== null && root.vm.ready ? "#BDEBD9"
                            : root.vm !== null && root.vm.state === "error" ? "#FFD8CF"
                            : "#D7E9FF"
                accentStrength: 0.20
                Row {
                    anchors.centerIn: parent
                    spacing: 7
                    Rectangle {
                        width: 7
                        height: 7
                        radius: GlassTokens.circleRadius(width)
                        color: root.vm !== null && root.vm.ready ? "#24A66D"
                               : root.vm !== null && root.vm.state === "error" ? "#D96555"
                               : "#7A8CA0"
                    }
                    GlassText {
                        text: root.vm !== null ? root.vm.statusText : "未连接"
                        tone: "secondary"
                        sizeHint: 11
                    }
                }
            }

            GlassButton {
                width: 106
                height: 36
                anchors.verticalCenter: parent.verticalCenter
                label: root.vm !== null && root.vm.canStop ? "停止服务" : "启动服务"
                enabled: root.vm !== null && (root.vm.canStart || root.vm.canStop)
                active: root.vm !== null && root.vm.canStop
                onClicked: {
                    if (root.vm === null) return
                    if (root.vm.canStop) root.vm.stop()
                    else root.vm.start()
                }
            }

            GlassButton {
                width: 106
                height: 36
                anchors.verticalCenter: parent.verticalCenter
                label: assistantWebView.viewingExternalPage || assistantWebView.canGoBack
                       ? "返回投研" : "刷新页面"
                enabled: root.vm !== null && root.vm.ready
                onClicked: {
                    if (assistantWebView.canGoBack) assistantWebView.goBack()
                    else if (assistantWebView.viewingExternalPage)
                        assistantWebView.url = root.vm.frontendUrl
                    else assistantWebView.reload()
                }
            }
        }

        GlassSurface {
            id: workspace
            objectName: "researchAssistantWorkspace"
            width: parent.width
            height: parent.height - y
            appearanceKey: "research_assistant.workspace"
            appearanceLabel: "投研助手工作台"
            surfaceRadius: GlassTokens.containerRadius
            tint: "#EAF6FC"
            tintAlpha: 0.48
            edgeContrast: 0.32
            depthStrength: 0.54
            clip: true

            WebEngineView {
                id: assistantWebView
                objectName: "researchAssistantWebView"
                readonly property bool viewingExternalPage: root.vm !== null
                                                            && url.toString().indexOf(root.vm.frontendUrl) !== 0
                anchors.fill: parent
                anchors.margins: 1
                visible: root.vm !== null && root.vm.ready
                url: visible ? root.vm.frontendUrl : "about:blank"
                // Keep the web canvas transparent so its glass layers share the
                // same light and depth as the native QML surface underneath.
                backgroundColor: "transparent"
                focus: visible
                zoomFactor: 1.10

                settings.javascriptEnabled: true
                settings.localStorageEnabled: true
                settings.errorPageEnabled: true

                onNewWindowRequested: function(request) {
                    request.openIn(assistantWebView)
                }
            }

            Column {
                visible: assistantWebView.visible === false
                width: Math.min(620, parent.width - 80)
                anchors.centerIn: parent
                spacing: 14

                Rectangle {
                    width: 58
                    height: 58
                    anchors.horizontalCenter: parent.horizontalCenter
                    radius: GlassTokens.circleRadius(width)
                    color: Qt.rgba(0.38, 0.34, 0.84, 0.12)
                    border.width: 1
                    border.color: Qt.rgba(0.38, 0.34, 0.84, 0.28)
                    GlassText {
                        anchors.centerIn: parent
                        text: "AI"
                        tone: "primary"
                        sizeHint: 17
                        font.weight: Font.Bold
                    }
                }

                GlassText {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: root.vm === null ? "投研助手运行时未连接"
                          : root.vm.state === "starting" ? "正在启动投研工作台…"
                          : root.vm.state === "stopping" ? "正在停止服务…"
                          : root.vm.state === "error" ? "投研助手启动失败"
                          : "投研助手尚未启动"
                    tone: root.vm !== null && root.vm.state === "error" ? "secondary" : "primary"
                    sizeHint: 20
                    font.weight: Font.DemiBold
                }

                GlassText {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: root.vm !== null ? root.vm.detail : "请检查 researchAssistantVm 注入。"
                    tone: "muted"
                    sizeHint: 12
                    wrapMode: Text.Wrap
                }

                GlassButton {
                    visible: root.vm !== null && root.vm.canStart
                    width: 132
                    height: 40
                    anchors.horizontalCenter: parent.horizontalCenter
                    label: root.vm !== null && root.vm.state === "error" ? "重试" : "启动投研助手"
                    active: true
                    onClicked: root.vm.start()
                }

                GlassText {
                    visible: root.vm !== null && root.vm.logTail !== ""
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: root.vm !== null ? root.vm.logTail : ""
                    tone: "muted"
                    sizeHint: 10
                    wrapMode: Text.Wrap
                    maximumLineCount: 4
                    elide: Text.ElideRight
                }
            }
        }
    }
}
