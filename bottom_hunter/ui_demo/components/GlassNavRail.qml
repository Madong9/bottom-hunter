// GlassNavRail — raised daylight liquid-glass navigation lens.
import QtQuick
import QtQuick.Controls.Basic
import "../primitives"

GlassSurface {
    id: root

    property int currentIndex: 0
    signal navigate(int index)

    appearanceKey: "shell.navigation"
    appearanceLabel: "左侧导航"
    surfaceRadius: GlassTokens.containerRadius
    tint: "#EAF7FF"
    tintAlpha: 0.46
    edgeContrast: GlassTokens.structuralEdgeContrast
    depthStrength: GlassTokens.structuralDepthStrength
    clip: true

    Column {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 6

        // 品牌
        Rectangle {
            width: 40; height: 40
            radius: GlassTokens.circleRadius(width)
            anchors.horizontalCenter: parent.horizontalCenter
            color: Qt.rgba(0.169, 0.835, 0.463, 0.16)
            border.width: 1
            border.color: Qt.rgba(0.169, 0.835, 0.463, 0.4)

            GlassText {
                anchors.centerIn: parent
                text: "B"
                color: "#2BD576"
                sizeHint: 19
                font.weight: Font.Bold
            }
        }

        Item { width: 1; height: 10 }

        Repeater {
            model: [
                { icon: "overview", tip: "总览" },
                { icon: "watchlist", tip: "自选" },
                { icon: "research", tip: "研究" },
                { icon: "report", tip: "报告" },
                { icon: "import", tip: "导入" },
                { icon: "status", tip: "状态" },
                { icon: "chart", tip: "K线" }
            ]

            delegate: Item {
                width: 52
                height: 46
                anchors.horizontalCenter: parent.horizontalCenter
                scale: tap.pressed ? 0.94 : hover.hovered ? 1.04 : 1.0

                // active 克制 emerald 药丸（very subtle tint + thin edge）
                Rectangle {
                    anchors.fill: parent
                    radius: GlassTokens.capsuleRadius(height)
                    color: index === root.currentIndex
                           ? Qt.rgba(0.169, 0.835, 0.463, 0.09)
                           : hover.hovered ? Qt.rgba(1, 1, 1, 0.24) : "transparent"
                    border.width: index === root.currentIndex ? 1 : 0
                    border.color: Qt.rgba(0.169, 0.835, 0.463, 0.28)
                }

                NavSymbol {
                    anchors.centerIn: parent
                    width: 21
                    height: 21
                    symbol: modelData.icon
                    strokeWidth: index === root.currentIndex ? 2.25 : 1.85
                    strokeColor: index === root.currentIndex
                                 ? "#128653"
                                 : hover.hovered ? "#152330" : "#465D70"
                }

                HoverHandler { id: hover }

                TapHandler {
                    id: tap
                    onTapped: root.navigate(index)
                }

                Behavior on scale {
                    NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
                }

                ToolTip {
                    id: navTip
                    // Keep the tooltip inside the transparent QML scene. A
                    // native popup creates a rectangular platform window
                    // behind the rounded glass surface on Linux/X11.
                    popupType: Popup.Item
                    visible: hover.hovered
                    delay: 500
                    x: parent.width + 10
                    y: (parent.height - implicitHeight) / 2
                    padding: 10

                    contentItem: GlassText {
                        text: modelData.tip
                        tone: "primary"
                        sizeHint: 13
                    }
                    background: GlassSurface {
                        appearanceSelectable: false
                        implicitWidth: 58
                        implicitHeight: 38
                        tint: "#EAF6FF"
                        tintAlpha: 0.70
                        accentTint: "#A9D8FF"
                        accentStrength: 0.18
                        surfaceRadius: GlassTokens.capsuleRadius(height)
                    }
                }
            }
        }
    }

    Item {
        id: appearanceButton
        objectName: "appearanceControlButton"
        width: 52
        height: 46
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 12
        scale: appearanceTap.pressed ? 0.94 : appearanceHover.hovered ? 1.04 : 1.0

        Rectangle {
            anchors.fill: parent
            radius: GlassTokens.capsuleRadius(height)
            color: appearancePopup.opened
                   ? Qt.rgba(0.36, 0.48, 0.94, 0.13)
                   : appearanceHover.hovered ? Qt.rgba(1, 1, 1, 0.24) : "transparent"
            border.width: appearancePopup.opened ? 1 : 0
            border.color: Qt.rgba(0.36, 0.48, 0.94, 0.30)
        }

        NavSymbol {
            anchors.centerIn: parent
            width: 21
            height: 21
            symbol: "palette"
            strokeWidth: appearancePopup.opened ? 2.2 : 1.85
            strokeColor: appearancePopup.opened ? "#5368C8" : "#465D70"
        }

        HoverHandler { id: appearanceHover }
        TapHandler {
            id: appearanceTap
            onTapped: appearancePopup.opened ? appearancePopup.close() : appearancePopup.open()
        }

        Behavior on scale {
            NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
        }

        ToolTip {
            visible: appearanceHover.hovered && !appearancePopup.opened
            popupType: Popup.Item
            delay: 500
            x: parent.width + 10
            y: (parent.height - implicitHeight) / 2
            padding: 10
            contentItem: GlassText { text: "玻璃色彩"; tone: "primary"; sizeHint: 13 }
            background: GlassSurface {
                appearanceSelectable: false
                implicitWidth: 82
                implicitHeight: 38
                tint: "#F2F5FF"
                tintAlpha: 0.74
                accentTint: "#DCD9FF"
                accentStrength: 0.22
                surfaceRadius: GlassTokens.capsuleRadius(height)
            }
        }

        Popup {
            id: appearancePopup
            objectName: "appearanceControlPopup"
            popupType: Popup.Item
            x: parent.width + 12
            y: parent.height - height
            width: 306
            height: 390
            padding: 0
            modal: false
            focus: true
            closePolicy: Popup.CloseOnEscape
            onClosed: GlassAppearance.editMode = false
            background: Item { }

            contentItem: GlassSurface {
                appearanceSelectable: false
                surfaceRadius: GlassTokens.containerRadius
                tint: "#F4F8FF"
                tintAlpha: 0.86
                accentTint: "#E0D9FF"
                accentStrength: 0.26

                Column {
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 9

                    Row {
                        width: parent.width
                        height: 24
                        GlassText { text: "整体色彩浓度"; tone: "primary"; sizeHint: 14 }
                        Item { width: parent.width - 140; height: 1 }
                        GlassText {
                            text: Math.round(toneSlider.value * 100) + "%"
                            tone: "secondary"
                            sizeHint: 13
                        }
                    }

                    Slider {
                        id: toneSlider
                        width: parent.width
                        height: 32
                        from: 0.25
                        to: 3.00
                        stepSize: 0.05
                        value: GlassAppearance.accentIntensity
                        onMoved: GlassAppearance.accentIntensity = value

                        background: Rectangle {
                            x: toneSlider.leftPadding
                            y: toneSlider.topPadding + toneSlider.availableHeight / 2 - height / 2
                            width: toneSlider.availableWidth
                            height: 7
                            radius: GlassTokens.capsuleRadius(height)
                            color: Qt.rgba(0.35, 0.46, 0.58, 0.16)
                            gradient: Gradient {
                                orientation: Gradient.Horizontal
                                GradientStop { position: 0.00; color: "#F2DCE6" }
                                GradientStop { position: 0.25; color: "#BFDFFF" }
                                GradientStop { position: 0.50; color: "#BDEBD9" }
                                GradientStop { position: 0.75; color: "#F3D5A4" }
                                GradientStop { position: 1.00; color: "#C9C5FF" }
                            }
                        }
                        handle: Rectangle {
                            x: toneSlider.leftPadding + toneSlider.visualPosition
                               * (toneSlider.availableWidth - width)
                            y: toneSlider.topPadding + toneSlider.availableHeight / 2 - height / 2
                            width: 22
                            height: 22
                            radius: GlassTokens.circleRadius(width)
                            color: "#F8FCFF"
                            border.width: 2
                            border.color: "#7184D5"
                        }
                    }

                    Row {
                        width: parent.width
                        height: 16
                        GlassText { text: "25%"; tone: "muted"; sizeHint: 11 }
                        Item { width: parent.width - 66; height: 1 }
                        GlassText { text: "300%"; tone: "muted"; sizeHint: 11 }
                    }

                    Rectangle {
                        width: parent.width
                        height: 1
                        color: Qt.rgba(0.30, 0.42, 0.54, 0.16)
                    }

                    GlassSurface {
                        objectName: "perGlassEditButton"
                        width: parent.width
                        height: 38
                        appearanceSelectable: false
                        reactive: true
                        surfaceRadius: GlassTokens.capsuleRadius(height)
                        tintAlpha: GlassAppearance.editMode ? 0.34 : 0.16
                        accentTint: "#D8D4FF"
                        accentStrength: GlassAppearance.editMode ? 0.34 : 0.12
                        Row {
                            anchors.centerIn: parent
                            spacing: 8
                            GlassText {
                                text: GlassAppearance.editMode ? "✓" : "+"
                                tone: "primary"
                                sizeHint: 15
                            }
                            GlassText {
                                text: GlassAppearance.editMode ? "正在逐块调色" : "选择玻璃块"
                                tone: "primary"
                                sizeHint: 13
                            }
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: GlassAppearance.editMode = !GlassAppearance.editMode
                        }
                    }

                    GlassText {
                        width: parent.width
                        height: 22
                        text: GlassAppearance.editMode
                              ? (GlassAppearance.selectedKey === ""
                                 ? "请点击界面中的任意玻璃块"
                                 : "已选择 · " + GlassAppearance.selectedLabel)
                              : "开启后点击卡片、工具条或页面玻璃"
                        elide: Text.ElideRight
                        tone: GlassAppearance.selectedKey === "" ? "muted" : "secondary"
                        sizeHint: 12
                    }

                    Row {
                        width: parent.width
                        height: 34
                        spacing: 10
                        Repeater {
                            model: [
                                { name: "淡玫瑰", color: "#F3A9C2" },
                                { name: "天蓝", color: "#83C5F3" },
                                { name: "薄荷", color: "#83D9B8" },
                                { name: "暖金", color: "#E9B86B" },
                                { name: "蓝紫", color: "#9994EE" },
                                { name: "冰白", color: "#EAF4FA" }
                            ]
                            delegate: Rectangle {
                                width: 34
                                height: 34
                                radius: GlassTokens.circleRadius(width)
                                color: modelData.color
                                opacity: GlassAppearance.selectedKey === "" ? 0.42 : 0.92
                                border.width: GlassAppearance.editorColor.toString().toUpperCase()
                                              === modelData.color.toUpperCase() ? 3 : 1
                                border.color: border.width === 3 ? "#5266C7" : Qt.rgba(1, 1, 1, 0.90)
                                MouseArea {
                                    anchors.fill: parent
                                    enabled: GlassAppearance.selectedKey !== ""
                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onClicked: GlassAppearance.setSelectedColor(modelData.color)
                                }
                                HoverHandler { id: colorHover }
                                ToolTip {
                                    visible: colorHover.hovered
                                    popupType: Popup.Item
                                    delay: 350
                                    x: (parent.width - width) / 2
                                    y: -height - 6
                                    padding: 7
                                    contentItem: GlassText {
                                        text: modelData.name
                                        tone: "primary"
                                        sizeHint: 11
                                    }
                                    background: GlassSurface {
                                        appearanceSelectable: false
                                        implicitWidth: 58
                                        implicitHeight: 30
                                        surfaceRadius: GlassTokens.capsuleRadius(height)
                                        tintAlpha: 0.78
                                        accentTint: modelData.color
                                        accentStrength: 0.28
                                    }
                                }
                            }
                        }
                    }

                    Row {
                        width: parent.width
                        height: 22
                        GlassText { text: "当前玻璃深浅"; tone: "primary"; sizeHint: 13 }
                        Item { width: parent.width - 140; height: 1 }
                        GlassText {
                            text: Math.round(blockStrengthSlider.value * 100) + "%"
                            tone: "secondary"
                            sizeHint: 13
                        }
                    }

                    Slider {
                        id: blockStrengthSlider
                        objectName: "perGlassDepthSlider"
                        width: parent.width
                        height: 32
                        from: 0.0
                        to: 0.90
                        stepSize: 0.01
                        enabled: GlassAppearance.selectedKey !== ""
                        opacity: enabled ? 1.0 : 0.42
                        value: GlassAppearance.editorStrength
                        onMoved: GlassAppearance.setSelectedStrength(value)

                        Connections {
                            target: GlassAppearance
                            function onSelectionChanged() {
                                blockStrengthSlider.value = GlassAppearance.editorStrength
                            }
                        }

                        background: Rectangle {
                            x: blockStrengthSlider.leftPadding
                            y: blockStrengthSlider.topPadding
                               + blockStrengthSlider.availableHeight / 2 - height / 2
                            width: blockStrengthSlider.availableWidth
                            height: 7
                            radius: GlassTokens.capsuleRadius(height)
                            color: Qt.rgba(0.35, 0.46, 0.58, 0.15)
                            Rectangle {
                                width: blockStrengthSlider.visualPosition * parent.width
                                height: parent.height
                                radius: GlassTokens.capsuleRadius(height)
                                color: GlassAppearance.editorColor
                                opacity: 0.88
                            }
                        }
                        handle: Rectangle {
                            x: blockStrengthSlider.leftPadding + blockStrengthSlider.visualPosition
                               * (blockStrengthSlider.availableWidth - width)
                            y: blockStrengthSlider.topPadding
                               + blockStrengthSlider.availableHeight / 2 - height / 2
                            width: 22
                            height: 22
                            radius: GlassTokens.circleRadius(width)
                            color: "#F8FCFF"
                            border.width: 2
                            border.color: GlassAppearance.editorColor
                        }
                    }

                    Row {
                        width: parent.width
                        height: 36
                        spacing: 10
                        GlassSurface {
                            width: (parent.width - 10) / 2
                            height: 36
                            appearanceSelectable: false
                            surfaceRadius: GlassTokens.capsuleRadius(height)
                            reactive: GlassAppearance.selectedKey !== ""
                            tintAlpha: 0.20
                            GlassText { anchors.centerIn: parent; text: "恢复该块"; tone: "secondary"; sizeHint: 12 }
                            MouseArea {
                                anchors.fill: parent
                                enabled: GlassAppearance.selectedKey !== ""
                                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: GlassAppearance.resetSelected()
                            }
                        }
                        GlassSurface {
                            width: (parent.width - 10) / 2
                            height: 36
                            appearanceSelectable: false
                            surfaceRadius: GlassTokens.capsuleRadius(height)
                            reactive: true
                            tintAlpha: 0.26
                            accentTint: "#D4E5FF"
                            accentStrength: 0.22
                            GlassText { anchors.centerIn: parent; text: "完成"; tone: "primary"; sizeHint: 12 }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: appearancePopup.close()
                            }
                        }
                    }
                }
            }
        }
    }
}
