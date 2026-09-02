import QtQuick
import QtQuick.Controls.Basic
import "../../primitives"
import "../../components"

GlassCard {
    id: root

    readonly property bool hasData: watchlistVm !== undefined && watchlistVm !== null
                                    && watchlistVm.items.length > 0

    Column {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 12

        Row {
            width: parent.width
            spacing: 12

            GlassText {
                text: watchlistVm ? watchlistVm.title : "自选"
                tone: "primary"
                sizeHint: 23
            }

            GlassText {
                text: (watchlistVm && watchlistVm.count > 0) ? watchlistVm.count + " 个标的" : ""
                tone: "muted"
                sizeHint: 13
                anchors.verticalCenter: parent.verticalCenter
            }

            StatusBadge {
                anchors.verticalCenter: parent.verticalCenter
                text: {
                    if (!watchlistVm) return "加载中"
                    switch (watchlistVm.lifecycle) {
                    case "LOADING": return "加载中"
                    case "READY": return "已就绪"
                    case "EMPTY": return "空自选"
                    case "ERROR": return "错误"
                    default: return "未加载"
                    }
                }
                tone: {
                    if (!watchlistVm) return "idle"
                    switch (watchlistVm.lifecycle) {
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
            visible: watchlistVm && watchlistVm.generatedAt !== ""
            text: "快照更新 · " + (watchlistVm ? watchlistVm.generatedAt : "")
            tone: "muted"
            sizeHint: 12
        }

        GlassText {
            visible: watchlistVm && watchlistVm.lifecycle === "ERROR"
            text: watchlistVm ? watchlistVm.error : ""
            tone: "secondary"
            sizeHint: 14
        }

        GlassText {
            visible: watchlistVm && (watchlistVm.lifecycle === "EMPTY"
                                    || watchlistVm.lifecycle === "INIT"
                                    || (watchlistVm.lifecycle === "ERROR"))
            text: {
                if (!watchlistVm) return "自选为空"
                if (watchlistVm.lifecycle === "EMPTY") return "自选为空"
                if (watchlistVm.lifecycle === "INIT") return "正在加载自选数据…"
                return ""
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
            model: watchlistVm ? watchlistVm.items : []

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
