import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import "../../primitives"

GlassSurface {
    id: root
    objectName: "importPage"
    tintAlpha: 0.42
    surfaceRadius: GlassTokens.pageRadius
    edgeContrast: GlassTokens.structuralEdgeContrast
    depthStrength: GlassTokens.structuralDepthStrength

    readonly property var vm: (typeof importVm !== "undefined") ? importVm : null
    property string selectedSource: "tonghuashun"
    property string mode: "file"
    property string pendingClear: ""

    component EntryField: TextField {
        implicitHeight: 38
        leftPadding: 13
        rightPadding: 13
        color: GlassTokens.textPrimary
        placeholderTextColor: GlassTokens.textMuted
        font.family: "Noto Sans CJK SC"
        font.pixelSize: 13
        selectByMouse: true
        background: GlassSurface {
            surfaceRadius: GlassTokens.capsuleRadius(height)
            tintAlpha: parent.activeFocus ? 0.34 : 0.20
            accentTint: "#D5E8FF"
            accentStrength: parent.activeFocus ? 0.18 : 0.06
        }
    }

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
            text: "支持事务文件导入、手动添加和来源维护。"
            tone: "muted"
            sizeHint: 13
        }

        Row {
            height: 38
            spacing: 9
            Repeater {
                model: [
                    { id: "file", label: "文件导入" },
                    { id: "manual", label: "手动添加" },
                    { id: "manage", label: "来源管理" }
                ]
                delegate: GlassSurface {
                    width: 112; height: 36; reactive: true
                    surfaceRadius: GlassTokens.capsuleRadius(height)
                    tintAlpha: root.mode === modelData.id ? 0.15 : 0.05
                    accentTint: root.mode === modelData.id ? "#CDEFE1" : "transparent"
                    accentStrength: root.mode === modelData.id ? 0.20 : 0.0
                    GlassText { anchors.centerIn: parent; text: modelData.label; tone: "primary"; sizeHint: 13 }
                    MouseArea {
                        anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                        onClicked: { root.mode = modelData.id; root.pendingClear = "" }
                    }
                }
            }
        }

        GlassCard {
            visible: root.mode === "file"
            width: parent.width
            height: 116
            interactive: false
            accentTint: "#D6E8FF"
            accentStrength: 0.15

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
                            surfaceRadius: GlassTokens.capsuleRadius(height)
                            accentTint: root.selectedSource === modelData.id ? "#CDEFE1" : "transparent"
                            accentStrength: root.selectedSource === modelData.id ? 0.18 : 0.0

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
                        surfaceRadius: GlassTokens.capsuleRadius(height)
                        accentTint: "#CFE4FF"
                        accentStrength: 0.18

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
            visible: root.mode === "manual"
            width: parent.width
            height: 150
            interactive: false
            accentTint: "#D8F2E8"
            accentStrength: 0.14

            Column {
                anchors.fill: parent; anchors.margins: 16; spacing: 10
                GlassText { text: "手动添加自选"; tone: "primary"; sizeHint: 16 }
                Row {
                    spacing: 9
                    EntryField { id: manualSymbol; width: 190; placeholderText: "代码，如 600519.SS / BTC-USDT" }
                    EntryField { id: manualName; width: 155; placeholderText: "名称（可只填名称）" }
                    EntryField {
                        id: manualMarket; width: 120
                        placeholderText: root.selectedSource === "tonghuashun" ? "CN / HK / US" : "CRYPTO"
                    }
                    EntryField { id: manualIndustry; width: 160; placeholderText: "行业（可选）" }
                    GlassSurface {
                        width: 112; height: 38; reactive: root.vm !== null && root.vm.maintenanceState !== "RUNNING"
                        surfaceRadius: GlassTokens.capsuleRadius(height)
                        tintAlpha: 0.13; accentTint: "#CDEFE1"; accentStrength: 0.22
                        GlassText { anchors.centerIn: parent; text: "添加"; tone: "primary"; sizeHint: 13 }
                        MouseArea {
                            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                            enabled: root.vm !== null && root.vm.maintenanceState !== "RUNNING"
                            onClicked: root.vm.addManual(
                                root.selectedSource, manualSymbol.text, manualName.text,
                                manualMarket.text || (root.selectedSource === "tonghuashun" ? "CN" : "CRYPTO"),
                                manualIndustry.text
                            )
                        }
                    }
                }
                Row {
                    spacing: 8
                    GlassText { text: "归属："; tone: "muted"; sizeHint: 12; anchors.verticalCenter: parent.verticalCenter }
                    Repeater {
                        model: [
                            { id: "tonghuashun", label: "同花顺" },
                            { id: "binance", label: "币安" },
                            { id: "okx", label: "欧易" }
                        ]
                        delegate: GlassSurface {
                            width: 82; height: 30; reactive: true
                            surfaceRadius: GlassTokens.capsuleRadius(height)
                            tintAlpha: root.selectedSource === modelData.id ? 0.14 : 0.04
                            accentTint: root.selectedSource === modelData.id ? "#D6E8FF" : "transparent"
                            accentStrength: root.selectedSource === modelData.id ? 0.18 : 0
                            GlassText { anchors.centerIn: parent; text: modelData.label; tone: "primary"; sizeHint: 12 }
                            MouseArea { anchors.fill: parent; onClicked: root.selectedSource = modelData.id }
                        }
                    }
                }
            }
        }

        GlassCard {
            visible: root.mode === "manage"
            width: parent.width
            height: 192
            interactive: false
            accentTint: "#E7DEFF"
            accentStrength: 0.13

            Column {
                anchors.fill: parent; anchors.margins: 16; spacing: 10
                Row {
                    width: parent.width; height: 34; spacing: 12
                    GlassText { text: "来源状态"; tone: "primary"; sizeHint: 16 }
                    GlassSurface {
                        width: 142; height: 32; reactive: root.vm !== null && root.vm.maintenanceState !== "RUNNING"
                        surfaceRadius: GlassTokens.capsuleRadius(height)
                        tintAlpha: 0.09; accentTint: "#D5E8FF"; accentStrength: 0.15
                        GlassText { anchors.centerIn: parent; text: "刷新关联文件"; tone: "primary"; sizeHint: 12 }
                        MouseArea {
                            anchors.fill: parent; enabled: root.vm !== null && root.vm.maintenanceState !== "RUNNING"
                            cursorShape: Qt.PointingHandCursor; onClicked: root.vm.refreshLinked()
                        }
                    }
                }
                Repeater {
                    model: root.vm !== null ? root.vm.sourceStatuses : []
                    delegate: Row {
                        width: parent.width; height: 34; spacing: 12
                        GlassText { width: 100; text: modelData.label; tone: "primary"; sizeHint: 13 }
                        GlassText {
                            width: 190; text: modelData.count + " 个·手动 " + modelData.manualCount + " 个"
                            tone: "secondary"; sizeHint: 12
                        }
                        GlassText {
                            width: 270; text: modelData.importFile || "未关联文件"
                            elide: Text.ElideMiddle; tone: "muted"; sizeHint: 11
                        }
                        GlassSurface {
                            width: root.pendingClear === modelData.source ? 132 : 96; height: 30; reactive: true
                            surfaceRadius: GlassTokens.capsuleRadius(height)
                            tintAlpha: root.pendingClear === modelData.source ? 0.16 : 0.05
                            accentTint: "#FFD9D1"; accentStrength: root.pendingClear === modelData.source ? 0.24 : 0.10
                            GlassText {
                                anchors.centerIn: parent
                                text: root.pendingClear === modelData.source ? "再次确认清空" : "清空来源"
                                tone: "primary"; sizeHint: 12
                            }
                            MouseArea {
                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                enabled: root.vm !== null && root.vm.maintenanceState !== "RUNNING"
                                onClicked: {
                                    if (root.pendingClear === modelData.source) {
                                        root.vm.clearSource(modelData.source); root.pendingClear = ""
                                    } else root.pendingClear = modelData.source
                                }
                            }
                        }
                    }
                }
            }
        }

        GlassSurface {
            visible: root.mode !== "file" && root.vm !== null && root.vm.maintenanceMessage !== ""
            width: parent.width; height: 42
            surfaceRadius: GlassTokens.capsuleRadius(height)
            tintAlpha: 0.09
            accentTint: root.vm !== null && root.vm.maintenanceState === "ERROR" ? "#FFD9D1" : "#D5EFE4"
            accentStrength: 0.15
            GlassText {
                anchors.fill: parent; anchors.margins: 12
                verticalAlignment: Text.AlignVCenter
                text: root.vm !== null && root.vm.maintenanceState === "RUNNING" ? "正在后台处理…" : root.vm.maintenanceMessage
                tone: "secondary"; sizeHint: 12; elide: Text.ElideRight
            }
        }

        GlassCard {
            visible: root.mode === "file" && root.vm !== null && ["IMPORTING", "SUCCESS", "PARTIAL_REVIEW", "ERROR"].indexOf(root.vm.lifecycle) >= 0
            width: parent.width
            height: 96
            interactive: false
            accentTint: root.vm !== null && root.vm.lifecycle === "SUCCESS" ? "#CDEFE0"
                        : root.vm !== null && root.vm.lifecycle === "ERROR" ? "#FFD8CF"
                        : "#D9E4FF"
            accentStrength: 0.18

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
            visible: root.mode === "file" && root.vm !== null && ["READY", "IMPORTING", "PARTIAL_REVIEW", "ERROR"].indexOf(root.vm.lifecycle) >= 0
            height: 40
            spacing: 10

            GlassSurface {
                objectName: "confirmImportButton"
                visible: root.vm !== null && root.vm.lifecycle === "READY"
                width: 132
                height: 38
                reactive: root.vm !== null && root.vm.validCount > 0
                tintAlpha: root.vm !== null && root.vm.validCount > 0 ? 0.10 : 0.025
                surfaceRadius: GlassTokens.capsuleRadius(height)
                accentTint: "#CDEFE0"
                accentStrength: root.vm !== null && root.vm.validCount > 0 ? 0.20 : 0.0
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
                surfaceRadius: GlassTokens.capsuleRadius(height)
                accentTint: "#CDEFE0"
                accentStrength: 0.20
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
                surfaceRadius: GlassTokens.capsuleRadius(height)
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
                surfaceRadius: GlassTokens.capsuleRadius(height)
                accentTint: "#FFE1D6"
                accentStrength: 0.18
                GlassText { anchors.centerIn: parent; text: "重试"; tone: "primary"; sizeHint: 13 }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.vm.retryImport() }
            }
        }

        Row {
            id: previewStats
            visible: root.mode === "file" && root.vm !== null && root.vm.lifecycle === "READY"
            width: parent.width
            spacing: 12

            Repeater {
                model: [
                    { label: "文件", value: root.vm !== null ? root.vm.filename : "--", tint: "#D6E8FF" },
                    { label: "格式", value: root.vm !== null ? root.vm.fileFormat : "--", tint: "#E6DCFF" },
                    { label: "检测", value: root.vm !== null ? String(root.vm.detectedCount) : "0", tint: "#D6F1E7" },
                    { label: "有效 / 无效", value: root.vm !== null
                          ? root.vm.validCount + " / " + root.vm.invalidCount : "0 / 0", tint: "#FFE2D5" }
                ]

                delegate: GlassCard {
                    width: (previewStats.width - 3 * previewStats.spacing) / 4
                    height: 76
                    interactive: false
                    accentTint: modelData.tint
                    accentStrength: 0.18

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
            visible: root.mode === "file" && root.vm !== null && root.vm.lifecycle === "READY"
            width: parent.width
            height: parent.height - y
            spacing: 14

            GlassCard {
                width: (parent.width - parent.spacing) * 0.68
                height: parent.height
                interactive: false
                accentTint: "#D8E9FF"
                accentStrength: 0.10

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
                            surfaceRadius: GlassTokens.compactContainerRadius

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
                accentTint: "#FFE5D4"
                accentStrength: 0.12

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
