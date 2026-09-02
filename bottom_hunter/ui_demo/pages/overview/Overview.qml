import QtQuick
import "../../primitives"

GlassSurface {
    id: root
    objectName: "overviewPage"
    tintAlpha: 0.02
    surfaceRadius: 16

    readonly property var vm: (typeof overviewState !== "undefined") ? overviewState : null
    readonly property bool ready: vm !== null && (vm.lifecycle === "READY" || vm.lifecycle === "STALE")

    Component.onCompleted: {
        if (vm !== null && vm.lifecycle === "INIT"
                && typeof overviewRefreshController !== "undefined"
                && overviewRefreshController !== null)
            overviewRefreshController.requestRefresh()
    }

    Column {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 14

        GlassText { text: "总览"; tone: "primary"; sizeHint: 23 }
        GlassText {
            text: root.vm === null ? "页面数据未注入"
                  : root.vm.lifecycle === "LOADING" ? "正在读取最新报告…"
                  : root.vm.lifecycle === "ERROR" ? root.vm.lastError
                  : root.vm.lifecycle === "STALE" ? "展示上次成功数据 · " + root.vm.lastError
                  : "最近更新 · " + root.vm.lastSuccessfulUpdate
            tone: root.vm !== null && root.vm.lifecycle === "ERROR" ? "secondary" : "muted"
            sizeHint: 13
        }

        GlassCard {
            visible: !root.ready
            width: parent.width
            height: 84
            interactive: false
            GlassText {
                anchors.centerIn: parent
                text: root.vm === null ? "总览 ViewModel 未连接"
                      : root.vm.lifecycle === "ERROR" ? "暂时无法读取总览快照"
                      : "正在准备总览数据…"
                tone: "muted"
                sizeHint: 14
            }
        }

        Grid {
            visible: root.ready
            width: parent.width
            columns: 3
            spacing: 12

            Repeater {
                model: root.vm === null ? [] : [
                    { label: "超跌机会", value: root.vm.opportunityCount, detail: root.vm.opportunityHint },
                    { label: "市场状态", value: root.vm.marketStatus, detail: root.vm.marketStatusDetail },
                    { label: "扫描状态", value: root.vm.scanStatus, detail: root.vm.scanStatusDetail },
                    { label: "数据健康", value: root.vm.dataHealthText, detail: root.vm.dataHealthLevel },
                    { label: "滚动验证", value: root.vm.validation, detail: root.vm.validationHint },
                    { label: "模拟净值", value: root.vm.portfolioValue, detail: root.vm.portfolioHint }
                ]

                delegate: GlassCard {
                    width: (root.width - 64) / 3
                    height: 132
                    interactive: false
                    Column {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 8
                        GlassText { text: modelData.label; tone: "muted"; sizeHint: 12 }
                        GlassText {
                            width: parent.width
                            text: modelData.value
                            elide: Text.ElideRight
                            tone: "primary"
                            sizeHint: 20
                        }
                        GlassText {
                            width: parent.width
                            text: modelData.detail
                            elide: Text.ElideRight
                            tone: "secondary"
                            sizeHint: 12
                        }
                    }
                }
            }
        }
    }
}
