import QtQuick
import QtQuick.Dialogs
import "../../primitives"

GlassSurface {
    id: root
    objectName: "importPage"
    tintAlpha: 0.02
    surfaceRadius: 16

    readonly property var vm: (typeof importVm !== "undefined") ? importVm : null
    property string selectedSource: "tonghuashun"

    FileDialog {
        id: fileDialog
        title: "选择自选文件用于预览"
        nameFilters: [
            "自选文件 (*.xlsx *.xls *.xlsm *.csv *.json *.txt *.sel *.ini)",
            "所有文件 (*)"
        ]
        onAccepted: {
            if (root.vm !== null)
                root.vm.requestPreview(selectedFile.toString(), root.selectedSource)
        }
    }

    Column {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 14

        GlassText {
            text: "导入预览"
            tone: "primary"
            sizeHint: 23
        }

        GlassText {
            text: "只读取并预览文件；本页不会导入、保存或修改任何数据。"
            tone: "muted"
            sizeHint: 13
        }

        GlassCard {
            width: parent.width
            height: 116
            interactive: false

            Column {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 10

                GlassText {
                    text: "选择文件来源"
                    tone: "primary"
                    sizeHint: 16
                }

                Row {
                    spacing: 10

                    Repeater {
                        model: [
                            { id: "tonghuashun", label: "同花顺" },
                            { id: "binance", label: "币安" },
                            { id: "okx", label: "欧易" }
                        ]

                        delegate: GlassSurface {
                            width: 108
                            height: 36
                            tintAlpha: root.selectedSource === modelData.id ? 0.10 : 0.035
                            surfaceRadius: 10

                            GlassText {
                                anchors.centerIn: parent
                                text: modelData.label
                                tone: root.selectedSource === modelData.id ? "primary" : "secondary"
                                sizeHint: 13
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.selectedSource = modelData.id
                            }
                        }
                    }

                    GlassSurface {
                        width: 138
                        height: 36
                        tintAlpha: 0.08
                        surfaceRadius: 10

                        GlassText {
                            anchors.centerIn: parent
                            text: root.vm !== null && root.vm.lifecycle === "SELECTING"
                                  ? "等待选择…" : "选择文件"
                            tone: "primary"
                            sizeHint: 13
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (root.vm !== null) root.vm.beginSelection()
                                fileDialog.open()
                            }
                        }
                    }
                }
            }
        }

        GlassCard {
            visible: root.vm !== null && root.vm.lifecycle === "ERROR"
            width: parent.width
            height: 64
            interactive: false

            GlassText {
                anchors.centerIn: parent
                text: root.vm !== null ? root.vm.error : ""
                tone: "secondary"
                sizeHint: 14
            }
        }

        Row {
            visible: root.vm !== null && root.vm.lifecycle === "READY"
            width: parent.width
            spacing: 12

            Repeater {
                model: [
                    { label: "文件", value: root.vm !== null ? root.vm.filename : "--" },
                    { label: "格式", value: root.vm !== null ? root.vm.fileFormat : "--" },
                    { label: "检测", value: root.vm !== null ? String(root.vm.detectedCount) : "0" },
                    { label: "有效 / 无效", value: root.vm !== null
                          ? root.vm.validCount + " / " + root.vm.invalidCount : "0 / 0" }
                ]

                delegate: GlassCard {
                    width: (parent.width - 3 * parent.spacing) / 4
                    height: 76
                    interactive: false

                    Column {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 5
                        GlassText { text: modelData.label; tone: "muted"; sizeHint: 11 }
                        GlassText {
                            width: parent.width
                            text: modelData.value
                            elide: Text.ElideMiddle
                            tone: "primary"
                            sizeHint: 15
                        }
                    }
                }
            }
        }

        Row {
            visible: root.vm !== null && root.vm.lifecycle === "READY"
            width: parent.width
            height: parent.height - y
            spacing: 14

            GlassCard {
                width: (parent.width - parent.spacing) * 0.68
                height: parent.height
                interactive: false

                Column {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 10

                    GlassText { text: "预览项"; tone: "primary"; sizeHint: 17 }

                    ListView {
                        id: previewList
                        width: parent.width
                        height: parent.height - y
                        spacing: 7
                        clip: true
                        model: root.vm !== null ? root.vm.previewItems : []

                        delegate: GlassSurface {
                            width: previewList.width
                            height: 54
                            tintAlpha: 0.025
                            surfaceRadius: 10

                            Row {
                                anchors.fill: parent
                                anchors.margins: 11
                                spacing: 8
                                GlassText { width: 145; text: modelData.symbol; tone: "primary"; sizeHint: 13 }
                                GlassText { width: 150; text: modelData.name; tone: "secondary"; sizeHint: 13 }
                                GlassText { width: 70; text: modelData.market; tone: "muted"; sizeHint: 12 }
                                GlassText {
                                    width: parent.width - 389
                                    text: modelData.industry
                                    elide: Text.ElideRight
                                    tone: "muted"
                                    sizeHint: 12
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
                        text: "警告 · " + (root.vm !== null ? root.vm.warnings.length : 0)
                        tone: "primary"
                        sizeHint: 17
                    }

                    GlassText {
                        visible: root.vm !== null && root.vm.warnings.length === 0
                        text: "未发现解析警告"
                        tone: "muted"
                        sizeHint: 13
                    }

                    Repeater {
                        model: root.vm !== null ? root.vm.warnings : []
                        GlassText {
                            width: parent.width
                            wrapMode: Text.Wrap
                            text: "• " + modelData
                            tone: "secondary"
                            sizeHint: 12
                        }
                    }
                }
            }
        }
    }
}
