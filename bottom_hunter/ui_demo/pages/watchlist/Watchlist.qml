import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../../primitives"
import "../../components" as Components

GlassSurface {
    id: root
    objectName: "watchlistPage"
    tintAlpha: 0.42
    surfaceRadius: GlassTokens.pageRadius
    edgeContrast: GlassTokens.structuralEdgeContrast
    depthStrength: GlassTokens.structuralDepthStrength

    readonly property var vm: (typeof watchlistVm !== "undefined") ? watchlistVm : null
    readonly property bool hasData: vm !== null && vm.items.length > 0
    readonly property int tableHeaderHeight: 40
    readonly property int tableRowHeight: 52

    Component.onCompleted: {
        if (vm !== null && vm.lifecycle === "INIT") vm.refresh()
    }

    Column {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 12

        Row {
            width: parent.width
            spacing: 12

            GlassText {
                text: root.vm !== null ? root.vm.title : "自选"
                tone: "primary"
                sizeHint: 23
            }

            GlassText {
                text: root.vm !== null ? root.vm.count + " / " + root.vm.totalCount + " 个标的" : ""
                tone: "muted"
                sizeHint: 13
                anchors.verticalCenter: parent.verticalCenter
            }

            Components.StatusBadge {
                anchors.verticalCenter: parent.verticalCenter
                text: {
                    if (root.vm === null) return "未连接"
                    switch (root.vm.lifecycle) {
                    case "LOADING": return "加载中"
                    case "READY": return "已就绪"
                    case "EMPTY": return "空自选"
                    case "ERROR": return "错误"
                    default: return "未加载"
                    }
                }
                tone: {
                    if (root.vm === null) return "warning"
                    switch (root.vm.lifecycle) {
                    case "READY": return "idle"
                    case "LOADING": return "running"
                    case "ERROR": return "danger"
                    case "EMPTY": return "warning"
                    default: return "idle"
                    }
                }
            }
        }

        GlassText {
            visible: root.vm !== null && root.vm.generatedAt !== ""
            text: "快照更新 · " + (root.vm !== null ? root.vm.generatedAt : "")
            tone: "muted"
            sizeHint: 12
        }

        RowLayout {
            width: parent.width
            spacing: 8

            TextField {
                id: watchlistSearch
                objectName: "watchlistSearch"
                Layout.preferredWidth: 250
                height: 38
                placeholderText: "搜索代码、名称或行业"
                color: GlassTokens.textPrimary
                placeholderTextColor: GlassTokens.textMuted
                selectByMouse: true
                leftPadding: 14
                rightPadding: 14
                onTextChanged: if (root.vm !== null) root.vm.setQuery(text)
                background: GlassSurface {
                    tintAlpha: 0.18
                    surfaceRadius: GlassTokens.capsuleRadius(height)
                }
            }

            Repeater {
                model: [
                    { id: "all", label: "全部", count: root.vm !== null ? root.vm.totalCount : 0 },
                    { id: "crypto", label: "加密", count: root.vm !== null ? root.vm.cryptoCount : 0 },
                    { id: "global_equity", label: "美港股", count: root.vm !== null ? root.vm.globalEquityCount : 0 },
                    { id: "cn_equity", label: "A股", count: root.vm !== null ? root.vm.cnEquityCount : 0 }
                ]
                GlassButton {
                    Layout.preferredWidth: modelData.id === "global_equity" ? 94 : 76
                    height: 38
                    label: modelData.label + " " + modelData.count
                    active: root.vm !== null && root.vm.category === modelData.id
                    onClicked: if (root.vm !== null) root.vm.setCategory(modelData.id)
                }
            }

            Item { Layout.fillWidth: true }

            GlassButton {
                Layout.preferredWidth: 76
                height: 38
                label: "刷新"
                onClicked: if (root.vm !== null) root.vm.refresh()
            }
            GlassButton {
                Layout.preferredWidth: 92
                height: 38
                label: "导入自选"
                onClicked: if (root.vm !== null) root.vm.openImport()
            }
        }

        GlassText {
            visible: root.vm !== null && root.vm.lifecycle === "ERROR"
            text: root.vm !== null ? root.vm.error : ""
            tone: "secondary"
            sizeHint: 14
        }

        GlassText {
            visible: root.vm !== null && root.vm.lifecycle === "READY" && root.vm.count === 0
            text: "没有符合当前筛选条件的标的"
            tone: "muted"
            sizeHint: 13
        }

        GlassText {
            visible: root.vm === null || root.vm.lifecycle === "EMPTY"
                     || root.vm.lifecycle === "INIT" || root.vm.lifecycle === "LOADING"
            text: {
                if (root.vm === null) return "自选 ViewModel 未连接"
                if (root.vm.lifecycle === "EMPTY") return "自选为空"
                return "正在加载自选数据…"
            }
            tone: "muted"
            sizeHint: 14
        }

        GlassSurface {
            width: parent.width
            height: root.tableHeaderHeight
            tintAlpha: 0.025
            surfaceRadius: GlassTokens.compactContainerRadius
            accentTint: "#D8E8FA"
            accentStrength: 0.10

            Row {
                id: tableHeader
                anchors.left: parent.left
                anchors.leftMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - 32
                spacing: 0

                property real col0W: 170
                property real col1W: 110
                property real col2W: 120
                property real col3W: 120
                property real col4W: (tableHeader.width - tableHeader.col0W - tableHeader.col1W
                                     - tableHeader.col2W - tableHeader.col3W)

                GlassText { width: tableHeader.col0W; text: "代码 / 资产"; tone: "muted"; sizeHint: 12 }
                GlassText { width: tableHeader.col1W; text: "名称"; tone: "muted"; sizeHint: 12 }
                GlassText { width: tableHeader.col2W; text: "最新价"; tone: "muted"; sizeHint: 12 }
                GlassText { width: tableHeader.col3W; text: "涨跌幅"; tone: "muted"; sizeHint: 12 }
                GlassText { width: tableHeader.col4W; text: "信号状态"; tone: "muted"; sizeHint: 12 }
            }
        }

        ListView {
            id: list
            objectName: "watchlistList"
            width: parent.width
            height: parent.height - list.y
            clip: true
            spacing: 8
            interactive: true
            boundsBehavior: Flickable.StopAtBounds
            cacheBuffer: root.tableRowHeight * 4
            model: root.vm !== null ? root.vm.items : []

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }

            delegate: GlassSurface {
                width: list.width
                height: root.tableRowHeight
                tintAlpha: 0.035
                surfaceRadius: GlassTokens.compactContainerRadius
                accentTint: modelData.change_percent.startsWith("+") ? "#FFE0E0" : "#D4F1E6"
                accentStrength: 0.08

                property string up: modelData.change_percent.startsWith("+") ? "#E05C5C" : "#2BD58F"
                property string down: "#2BD58F"

                Row {
                    id: row
                    anchors.left: parent.left
                    anchors.leftMargin: 16
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - 32
                    spacing: 0

                    property real col0W: 170
                    property real col1W: 110
                    property real col2W: 120
                    property real col3W: 120
                    property real col4W: (row.width - row.col0W - row.col1W
                                         - row.col2W - row.col3W)

                    GlassText { width: row.col0W; text: modelData.symbol; tone: "primary"; sizeHint: 14 }
                    GlassText { width: row.col1W; text: modelData.name; tone: "secondary"; sizeHint: 14 }
                    GlassText { width: row.col2W; text: modelData.price; tone: "secondary"; sizeHint: 14 }
                    GlassText { width: row.col3W; text: modelData.change_percent; tone: "secondary"; sizeHint: 14 }
                    GlassText { width: row.col4W; text: modelData.signal; tone: "muted"; sizeHint: 13 }
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    acceptedButtons: Qt.LeftButton
                    onDoubleClicked: if (root.vm !== null) root.vm.openChart(index)
                }
            }
        }
    }
}
