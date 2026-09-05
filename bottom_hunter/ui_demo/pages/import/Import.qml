import QtQuick
import QtQuick.Dialogs
import "../../primitives"

GlassSurface {
    id: root
    objectName: "importPage"
    tintAlpha: 0.42
    surfaceRadius: 24

    readonly property var vm: (typeof importVm !== "undefined") ? importVm : null
    property string selectedSource: "tonghuashun"

    function resultValue(key, fallbackValue) {
        if (root.vm === null || !root.vm.result || root.vm.result[key] === undefined)
            return fallbackValue
        return root.vm.result[key]
    }

    FileDialog {
        id: fileDialog
        title: "选择自选文件"
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
            text: "自选导入"
            tone: "primary"
            sizeHint: 23
        }

        GlassText {
            text: "先预览并校验文件，确认后才会安全导入。"
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
                            reactive: true
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
                        reactive: true
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
            visible: root.vm !== null && ["IMPORTING", "SUCCESS", "PARTIAL_REVIEW", "ERROR"].indexOf(root.vm.lifecycle) >= 0
            width: parent.width
            height: 96
            interactive: false

            Column {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 7

                GlassText {
                    text: root.vm.lifecycle === "IMPORTING" ? "正在导入"
                          : root.vm.lifecycle === "SUCCESS" ? "导入完成"
                          : root.vm.lifecycle === "PARTIAL_REVIEW" ? "部分结果需要确认"
                          : "导入失败"
                    tone: "primary"
                    sizeHint: 16
                }
                GlassText {
                    width: parent.width
                    wrapMode: Text.Wrap
                    text: root.vm.lifecycle === "IMPORTING"
                          ? root.vm.progressMessage + " · " + root.vm.progress + "%"
                          : root.vm.lifecycle === "SUCCESS"
                            ? "新增 " + root.resultValue("importedCount", 0)
                              + " · 合并后 " + root.resultValue("mergedCount", 0)
                              + " · 生成板块 " + root.resultValue("generatedSectorCount", 0)
                          : root.vm.lifecycle === "PARTIAL_REVIEW"
                            ? "待分类 " + root.resultValue("unresolvedIndustryCount", 0)
                              + " · 无效 " + root.resultValue("invalidCount", 0)
                              + "；确认期间不占用导入锁。"
                          : root.vm.error
                    tone: "secondary"
                    sizeHint: 13
                }
            }
        }

        Row {
            visible: root.vm !== null && ["READY", "IMPORTING", "PARTIAL_REVIEW", "ERROR"].indexOf(root.vm.lifecycle) >= 0
            height: 40
            spacing: 10

            GlassSurface {
                objectName: "confirmImportButton"
                visible: root.vm !== null && root.vm.lifecycle === "READY"
                width: 132
                height: 38
                reactive: root.vm !== null && root.vm.validCount > 0
                tintAlpha: root.vm !== null && root.vm.validCount > 0 ? 0.10 : 0.025
                surfaceRadius: 10
                GlassText {
                    anchors.centerIn: parent
                    text: "确认导入"
                    tone: root.vm !== null && root.vm.validCount > 0 ? "primary" : "muted"
                    sizeHint: 13
                }
                MouseArea {
                    objectName: "confirmImportMouseArea"
                    anchors.fill: parent
                    enabled: root.vm !== null && root.vm.validCount > 0
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: root.vm.confirmImport()
                }
            }

            GlassSurface {
                objectName: "acceptPartialButton"
                visible: root.vm !== null && root.vm.lifecycle === "PARTIAL_REVIEW"
                width: 132
                height: 38
                reactive: true
                tintAlpha: 0.10
                surfaceRadius: 10
                GlassText { anchors.centerIn: parent; text: "接受并导入"; tone: "primary"; sizeHint: 13 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.vm.acceptPartial() }
            }

            GlassSurface {
                objectName: "cancelImportButton"
                visible: root.vm !== null && ["IMPORTING", "PARTIAL_REVIEW"].indexOf(root.vm.lifecycle) >= 0
                width: 108
                height: 38
                reactive: true
                tintAlpha: 0.035
                surfaceRadius: 10
                GlassText { anchors.centerIn: parent; text: "取消"; tone: "secondary"; sizeHint: 13 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.vm.cancelImport() }
            }

            GlassSurface {
                objectName: "retryImportButton"
                visible: root.vm !== null && root.vm.lifecycle === "ERROR"
                width: 108
                height: 38
                reactive: true
                tintAlpha: 0.08
                surfaceRadius: 10
                GlassText { anchors.centerIn: parent; text: "重试"; tone: "primary"; sizeHint: 13 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.vm.retryImport() }
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
