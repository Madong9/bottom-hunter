import QtQuick
import QtQuick.Controls.Basic
import "../../primitives"
import "../../components"

GlassCard {
    id: root
    objectName: "watchlistPage"

    readonly property var vm: (typeof watchlistVm !== "undefined") ? watchlistVm : null
    readonly property bool hasData: vm !== null && vm.items.length > 0

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
                text: (root.vm !== null && root.vm.count > 0) ? root.vm.count + " 个标的" : ""
                tone: "muted"
                sizeHint: 13
                anchors.verticalCenter: parent.verticalCenter
            }

            StatusBadge {
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

        GlassText {
            visible: root.vm !== null && root.vm.lifecycle === "ERROR"
            text: root.vm !== null ? root.vm.error : ""
            tone: "secondary"
            sizeHint: 14
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

        GlassCard {
            width: parent.width
            height: tableHeader.implicitHeight + 20

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

                GlassText { width: col0W; text: "代码 / 资产"; tone: "muted"; sizeHint: 12 }
                GlassText { width: col1W; text: "名称"; tone: "muted"; sizeHint: 12 }
                GlassText { width: col2W; text: "最新价"; tone: "muted"; sizeHint: 12 }
                GlassText { width: col3W; text: "涨跌幅"; tone: "muted"; sizeHint: 12 }
                GlassText { width: col4W; text: "信号状态"; tone: "muted"; sizeHint: 12 }
            }
        }

        ListView {
            id: list
            width: parent.width
            height: parent.height - list.y
            clip: true
            spacing: 8
            interactive: false
            model: root.vm !== null ? root.vm.items : []

            delegate: GlassCard {
                width: list.width
                height: row.implicitHeight + 16

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

                    GlassText { width: col0W; text: modelData.symbol; tone: "primary"; sizeHint: 14 }
                    GlassText { width: col1W; text: modelData.name; tone: "secondary"; sizeHint: 14 }
                    GlassText { width: col2W; text: modelData.price; tone: "secondary"; sizeHint: 14 }
                    GlassText { width: col3W; text: modelData.change_percent; tone: "secondary"; sizeHint: 14 }
                    GlassText { width: col4W; text: modelData.signal; tone: "muted"; sizeHint: 13 }
                }
            }
        }
    }
}
