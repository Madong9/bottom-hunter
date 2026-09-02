import QtQuick
import "../../primitives"

GlassSurface {
    id: root
    objectName: "researchPage"
    tintAlpha: 0.02
    surfaceRadius: 16

    readonly property var vm: (typeof researchVm !== "undefined") ? researchVm : null
    readonly property bool hasData: vm !== null && (vm.assetCount > 0 || vm.macroCount > 0)

    Component.onCompleted: {
        if (vm !== null && vm.lifecycle === "INIT")
            vm.refresh()
    }

    Column {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 14

        Row {
            width: parent.width
            spacing: 14

            GlassText {
                text: root.vm !== null ? root.vm.title : "研究"
                tone: "primary"
                sizeHint: 23
            }

            GlassText {
                anchors.verticalCenter: parent.verticalCenter
                text: root.vm !== null && root.vm.reportDate !== "--"
                      ? "报告 " + root.vm.reportDate : ""
                tone: "muted"
                sizeHint: 12
            }

            GlassText {
                anchors.verticalCenter: parent.verticalCenter
                text: {
                    if (root.vm === null) return "加载中"
                    switch (root.vm.lifecycle) {
                    case "LOADING": return "加载中"
                    case "READY": return "已就绪"
                    case "EMPTY": return "暂无数据"
                    case "ERROR": return "读取失败"
                    default: return "未加载"
                    }
                }
                tone: root.vm !== null && root.vm.lifecycle === "ERROR" ? "secondary" : "muted"
                sizeHint: 12
            }
        }

        GlassText {
            visible: root.vm !== null && root.vm.generatedAt !== ""
            text: "快照更新 · " + (root.vm !== null ? root.vm.generatedAt : "")
            tone: "muted"
            sizeHint: 12
        }

        GlassCard {
            visible: root.vm === null || root.vm.lifecycle === "INIT"
                     || root.vm.lifecycle === "LOADING"
                     || root.vm.lifecycle === "EMPTY"
                     || root.vm.lifecycle === "ERROR"
            width: parent.width
            height: 72
            interactive: false

            GlassText {
                anchors.centerIn: parent
                text: {
                    if (root.vm === null || root.vm.lifecycle === "INIT"
                            || root.vm.lifecycle === "LOADING")
                        return "正在读取最新研究快照…"
                    if (root.vm.lifecycle === "ERROR") return root.vm.error
                    return "最新报告中暂无研究数据"
                }
                tone: root.vm !== null && root.vm.lifecycle === "ERROR" ? "secondary" : "muted"
                sizeHint: 14
            }
        }

        Row {
            visible: root.hasData
            width: parent.width
            height: parent.height - y
            spacing: 14

            GlassCard {
                width: (parent.width - parent.spacing) * 0.42
                height: parent.height
                interactive: false

                Column {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 10

                    GlassText {
                        text: "公司研究 · " + (root.vm !== null ? root.vm.assetCount : 0)
                        tone: "primary"
                        sizeHint: 18
                    }

                    ListView {
                        id: assetList
                        width: parent.width
                        height: parent.height - y
                        spacing: 8
                        clip: true
                        model: root.vm !== null ? root.vm.assets : []

                        delegate: GlassSurface {
                            width: assetList.width
                            height: 86
                            tintAlpha: 0.025
                            surfaceRadius: 12

                            Column {
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 5

                                GlassText {
                                    text: modelData.symbol + "  ·  财务期 "
                                          + modelData.latest_financial_period
                                    tone: "primary"
                                    sizeHint: 14
                                }
                                GlassText {
                                    width: parent.width
                                    elide: Text.ElideRight
                                    text: modelData.items.length > 0
                                          ? modelData.items[0].title : "暂无最新研究条目"
                                    tone: "secondary"
                                    sizeHint: 13
                                }
                                GlassText {
                                    text: modelData.items.length > 0
                                          ? modelData.items[0].source : ""
                                    tone: "muted"
                                    sizeHint: 11
                                }
                            }
                        }
                    }
                }
            }

            GlassCard {
                width: parent.width - x
                height: parent.height
                interactive: false

                Column {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 10

                    GlassText {
                        text: "宏观观测 · " + (root.vm !== null ? root.vm.macroCount : 0)
                        tone: "primary"
                        sizeHint: 18
                    }

                    ListView {
                        id: macroList
                        width: parent.width
                        height: parent.height - y
                        spacing: 8
                        clip: true
                        model: root.vm !== null ? root.vm.macro : []

                        delegate: GlassSurface {
                            width: macroList.width
                            height: 66
                            tintAlpha: 0.025
                            surfaceRadius: 12

                            Row {
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 12

                                Column {
                                    width: parent.width * 0.48
                                    spacing: 4
                                    GlassText {
                                        text: modelData.name
                                        tone: "primary"
                                        sizeHint: 14
                                    }
                                    GlassText {
                                        text: modelData.dimension + " · " + modelData.source
                                        tone: "muted"
                                        sizeHint: 11
                                    }
                                }
                                Column {
                                    width: parent.width * 0.28
                                    spacing: 4
                                    GlassText {
                                        text: (modelData.value === null || modelData.value === undefined)
                                              ? "--" : String(modelData.value)
                                                + (modelData.unit ? " " + modelData.unit : "")
                                        tone: "secondary"
                                        sizeHint: 14
                                    }
                                    GlassText {
                                        text: modelData.observation_date
                                        tone: "muted"
                                        sizeHint: 11
                                    }
                                }
                                GlassText {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.signal > 0 ? "正向"
                                          : (modelData.signal < 0 ? "承压" : "中性")
                                    tone: "muted"
                                    sizeHint: 12
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
