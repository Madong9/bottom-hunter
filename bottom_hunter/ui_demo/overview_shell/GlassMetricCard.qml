// GlassMetricCard — 总览卡片 clear crystal slab (overview shell v2 POC).
// Clear neutral tint (NOT dark fill): glass presence comes from a thick-glass
// optical edge (brighter top-left, subtle darker bottom-right), soft depth
// shadow, 1px inner top light and the accent bar. Text stays nearly fully
// opaque — only the background material is transparent (no parent opacity).
import QtQuick
import QtQuick.Effects

Rectangle {
    id: root

    property string label: ""
    property string value: ""
    property string hint: ""
    property color accent: "#2BD576"

    // real content geometry (card-local coords) — consumed by
    // ProtectionRegistry via mapToItem; masks follow these automatically
    readonly property rect labelRect: Qt.rect(labelText.x, labelText.y, labelText.width, labelText.height)
    readonly property rect valueRect: Qt.rect(valueText.x, valueText.y, valueText.width, valueText.height)
    readonly property rect hintRect: Qt.rect(hintText.x, hintText.y, hintText.width, hintText.height)

    radius: 16
    color: Qt.rgba(1, 1, 1, 0.035)   // clear neutral tint (target 0.025-0.050)

    // soft depth shadow (glass plate floating above the city environment)
    layer.enabled: true
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: "#000000"
        shadowBlur: 0.35
        shadowVerticalOffset: 8
        shadowOpacity: 0.30
        autoPaddingEnabled: true
    }

    // ---- thick-glass optical edges (2-4 mm slab impression, no neon) ----
    // top edge: brighter, fading to the right
    Rectangle {
        anchors { top: parent.top; left: parent.left; right: parent.right }
        height: 1
        radius: 1
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.30) }
            GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.12) }
        }
    }
    // left edge: bright, fading down
    Rectangle {
        anchors { top: parent.top; left: parent.left; bottom: parent.bottom }
        width: 1
        radius: 1
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.22) }
            GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.08) }
        }
    }
    // bottom edge: very subtle darker / refraction edge
    Rectangle {
        anchors { bottom: parent.bottom; left: parent.left; right: parent.right }
        height: 1
        color: Qt.rgba(0, 0, 0, 0.14)
    }
    // right edge: very subtle darker
    Rectangle {
        anchors { top: parent.top; right: parent.right; bottom: parent.bottom }
        width: 1
        color: Qt.rgba(0, 0, 0, 0.10)
    }
    // soft corner highlight (top-left)
    Rectangle {
        x: 1; y: 1
        width: 14; height: 14
        radius: 7
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.30) }
            GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0) }
        }
    }
    // 1px inner top light (inset)
    Rectangle {
        anchors { top: parent.top; left: parent.left; right: parent.right }
        anchors.margins: 1
        height: 1
        color: Qt.rgba(1, 1, 1, 0.12)
    }

    // ---- content (nearly fully opaque; only the material is transparent) ----
    Row {
        anchors.fill: parent
        anchors.margins: 14
        spacing: 12

        // 渐变强调条（accent → 透明）
        Rectangle {
            width: 4
            height: parent.height
            radius: 2
            gradient: Gradient {
                GradientStop { position: 0.0; color: root.accent }
                GradientStop { position: 1.0; color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.06) }
            }
        }

        Column {
            spacing: 3
            anchors.verticalCenter: parent.verticalCenter

            Text {
                id: labelText
                text: root.label
                color: "#828A98"
                font.pixelSize: 12
                font.family: "Noto Sans CJK SC"
            }
            Text {
                id: valueText
                text: root.value
                color: "#EEF3F6"
                font.pixelSize: 24
                font.weight: Font.DemiBold
            }
            Text {
                id: hintText
                text: root.hint
                color: "#626D78"
                font.pixelSize: 11
                font.family: "Noto Sans CJK SC"
            }
        }
    }
}
