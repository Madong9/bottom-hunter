import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../../primitives"

GlassSurface {
    id: root
    objectName: "strategyPage"
    tintAlpha: 0.42
    surfaceRadius: GlassTokens.pageRadius
    edgeContrast: GlassTokens.structuralEdgeContrast
    depthStrength: GlassTokens.structuralDepthStrength

    readonly property var vm: (typeof strategyVm !== "undefined") ? strategyVm : null
    readonly property var alertVm: (typeof priceAlertVm !== "undefined") ? priceAlertVm : null
    property string activeTab: "research"

    function pct(value) {
        const number = Number(value)
        return isFinite(number) ? (number * 100).toFixed(2) + "%" : "--"
    }
    function number(value, digits) {
        const result = Number(value)
        return isFinite(result) ? result.toFixed(digits === undefined ? 3 : digits) : "--"
    }

    Column {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 14

        RowLayout {
            width: parent.width
            height: 42
            GlassText { text: "因子策略研究"; tone: "primary"; sizeHint: 23 }
            GlassText {
                Layout.leftMargin: 10
                text: root.vm !== null && root.vm.result.generated_at
                      ? "本地历史样本 · " + String(root.vm.result.generated_at).slice(0, 16).replace("T", " ")
                      : "因子挖掘 · 机器学习 · 强化学习"
                tone: "muted"
                sizeHint: 12
            }
            Item { Layout.fillWidth: true }
            GlassButton {
                width: 92; height: 36
                label: root.vm !== null && root.vm.running ? "评估中…" : "运行评估"
                enabled: root.vm !== null && !root.vm.running
                onClicked: if (root.vm !== null) root.vm.runResearch()
            }
        }

        Row {
            width: parent.width
            height: 38
            spacing: 8
            GlassButton { width: 108; height: 36; label: "因子与策略"; active: root.activeTab === "research"; onClicked: root.activeTab = "research" }
            GlassButton { width: 108; height: 36; label: "盘中预警"; active: root.activeTab === "alerts"; onClicked: root.activeTab = "alerts" }
            GlassText {
                anchors.verticalCenter: parent.verticalCenter
                text: root.activeTab === "alerts" && root.alertVm !== null
                      ? (root.alertVm.monitoring ? "● 自动监控中 · 约 30 秒检查一次" : "○ 监控已暂停") : "仅供策略研究，不会连接交易或下单"
                tone: root.activeTab === "alerts" && root.alertVm !== null && root.alertVm.monitoring ? "primary" : "muted"
                sizeHint: 12
            }
        }

        GlassText {
            visible: root.vm !== null && root.vm.error !== ""
            width: parent.width
            text: root.vm !== null ? root.vm.error : ""
            tone: "secondary"
            sizeHint: 13
        }

        ScrollView {
            visible: root.activeTab === "research"
            width: parent.width
            height: parent.height - y
            clip: true
            contentWidth: availableWidth
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            Column {
                width: parent.width
                spacing: 12

                GlassSurface {
                    width: parent.width
                    height: 58
                    tintAlpha: 0.18
                    surfaceRadius: GlassTokens.containerRadius
                    accentTint: "#DCE8FF"
                    accentStrength: 0.14
                    GlassText {
                        anchors.fill: parent
                        anchors.margins: 14
                        verticalAlignment: Text.AlignVCenter
                        wrapMode: Text.WordWrap
                        text: root.vm !== null && root.vm.result.asset_count
                              ? "已评估 " + root.vm.result.asset_count + " 个有历史缓存的自选标的，合计 " + root.vm.result.sample_count + " 个前向收益样本。训练/测试按时间顺序切分；数据不够时会显示样本不足。"
                              : "研究范围：自选股本地日K缓存。请先完成行情扫描，或准备至少 80 根历史日K，再运行评估。"
                        tone: "muted"
                        sizeHint: 13
                    }
                }

                RowLayout {
                    width: parent.width
                    height: 266
                    spacing: 12

                    GlassSurface {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        tintAlpha: 0.17
                        surfaceRadius: GlassTokens.containerRadius
                        accentTint: "#D8F2E7"
                        accentStrength: 0.17
                        Column {
                            anchors.fill: parent; anchors.margins: 14; spacing: 8
                            GlassText { text: "因子挖掘 · 5日 Rank IC"; tone: "primary"; sizeHint: 17 }
                            GlassText { text: "按交易日横截面计算因子与未来5日收益的 Spearman 相关"; tone: "muted"; sizeHint: 11 }
                            Row {
                                width: parent.width; height: 25; spacing: 8
                                GlassText { width: parent.width * 0.34; text: "因子"; tone: "muted"; sizeHint: 11 }
                                GlassText { width: parent.width * 0.19; text: "Mean IC"; tone: "muted"; sizeHint: 11 }
                                GlassText { width: parent.width * 0.16; text: "ICIR"; tone: "muted"; sizeHint: 11 }
                                GlassText { width: parent.width * 0.18; text: "方向"; tone: "muted"; sizeHint: 11 }
                                GlassText { text: "期数"; tone: "muted"; sizeHint: 11 }
                            }
                            Repeater {
                                model: root.vm !== null ? root.vm.result.factors || [] : []
                                delegate: Row {
                                    width: parent.width; height: 30; spacing: 8
                                    GlassText { width: parent.width * 0.34; text: modelData.label; tone: "primary"; sizeHint: 12 }
                                    GlassText { width: parent.width * 0.19; text: root.number(modelData.mean_ic); tone: "secondary"; sizeHint: 12 }
                                    GlassText { width: parent.width * 0.16; text: root.number(modelData.icir); tone: "secondary"; sizeHint: 12 }
                                    GlassText { width: parent.width * 0.18; text: modelData.direction; tone: "muted"; sizeHint: 12 }
                                    GlassText { text: String(modelData.periods); tone: "muted"; sizeHint: 12 }
                                }
                            }
                            GlassText {
                                visible: root.vm === null || !root.vm.result.factors || root.vm.result.factors.length === 0
                                text: "运行评估后显示因子排序"
                                tone: "muted"; sizeHint: 13
                            }
                        }
                    }

                    GlassSurface {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        tintAlpha: 0.17
                        surfaceRadius: GlassTokens.containerRadius
                        accentTint: "#E4DEFF"
                        accentStrength: 0.17
                        Column {
                            anchors.fill: parent; anchors.margins: 14; spacing: 9
                            GlassText { text: "机器学习 · Ridge 回归"; tone: "primary"; sizeHint: 17 }
                            GlassText { width: parent.width; wrapMode: Text.WordWrap; text: "输入：5/20日收益、波动、均线偏离、量比、RSI；预测未来5日收益。"; tone: "muted"; sizeHint: 12 }
                            GlassText { text: "状态 · " + (root.vm !== null && root.vm.result.machine_learning.status ? root.vm.result.machine_learning.status : "待运行"); tone: "primary"; sizeHint: 13 }
                            GlassText { text: "训练/测试样本 · " + (root.vm !== null && root.vm.result.machine_learning.train_samples !== undefined ? root.vm.result.machine_learning.train_samples + " / " + root.vm.result.machine_learning.test_samples : "--"); tone: "muted"; sizeHint: 12 }
                            GlassText { text: "测试方向准确率 · " + (root.vm !== null && root.vm.result.machine_learning.direction_accuracy !== undefined ? root.pct(root.vm.result.machine_learning.direction_accuracy) : "--"); tone: "muted"; sizeHint: 12 }
                            GlassText { width: parent.width; wrapMode: Text.WordWrap; text: "Top 20% 预测组平均未来5日收益 · " + (root.vm !== null && root.vm.result.machine_learning.top_quantile_mean_5d_return !== undefined ? root.pct(root.vm.result.machine_learning.top_quantile_mean_5d_return) : "--"); tone: "muted"; sizeHint: 12 }
                            GlassText { text: "模型 · Ridge（numpy 实现），按时间切分，正则化防止过拟合"; tone: "muted"; sizeHint: 11 }
                        }
                    }

                    GlassSurface {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        tintAlpha: 0.17
                        surfaceRadius: GlassTokens.containerRadius
                        accentTint: "#FFF0D8"
                        accentStrength: 0.18
                        Column {
                            anchors.fill: parent; anchors.margins: 14; spacing: 9
                            GlassText { text: "强化学习 · Q-learning"; tone: "primary"; sizeHint: 17 }
                            GlassText { width: parent.width; wrapMode: Text.WordWrap; text: "状态：价格相对20日均线 × 5日动量；动作：空仓/持有；奖励扣除换仓成本。"; tone: "muted"; sizeHint: 12 }
                            GlassText { text: "状态 · " + (root.vm !== null && root.vm.result.reinforcement_learning.status ? root.vm.result.reinforcement_learning.status : "待运行"); tone: "primary"; sizeHint: 13 }
                            GlassText { text: "训练/测试交易日 · " + (root.vm !== null && root.vm.result.reinforcement_learning.train_days !== undefined ? root.vm.result.reinforcement_learning.train_days + " / " + root.vm.result.reinforcement_learning.test_days : "--"); tone: "muted"; sizeHint: 12 }
                            GlassText { text: "测试策略 / 持有收益 · " + (root.vm !== null && root.vm.result.reinforcement_learning.strategy_return !== undefined ? root.pct(root.vm.result.reinforcement_learning.strategy_return) + " / " + root.pct(root.vm.result.reinforcement_learning.benchmark_return) : "--"); tone: "muted"; sizeHint: 12 }
                            GlassText { text: "测试最大回撤 · " + (root.vm !== null && root.vm.result.reinforcement_learning.max_drawdown !== undefined ? root.pct(root.vm.result.reinforcement_learning.max_drawdown) : "--"); tone: "muted"; sizeHint: 12 }
                            GlassText { text: "策略仅作研究模拟，不含实盘执行"; tone: "muted"; sizeHint: 11 }
                        }
                    }
                }

                Repeater {
                    model: root.vm !== null ? root.vm.result.caveats || [] : []
                    delegate: GlassText { width: parent.width; text: "• " + modelData; tone: "muted"; sizeHint: 11 }
                }
            }
        }

        GlassSurface {
            visible: root.activeTab === "alerts"
            width: parent.width
            height: parent.height - y
            tintAlpha: 0.17
            surfaceRadius: GlassTokens.containerRadius
            accentTint: "#DCEAFF"
            accentStrength: 0.16

            ColumnLayout {
                anchors.fill: parent; anchors.margins: 18; spacing: 12
                RowLayout {
                    Layout.fillWidth: true
                    GlassText { text: "自定义盘中预警"; tone: "primary"; sizeHint: 18 }
                    GlassText { Layout.leftMargin: 10; text: "价格阈值或当日涨跌幅，触发后提示；回落/反向穿越后可再次触发"; tone: "muted"; sizeHint: 12 }
                    Item { Layout.fillWidth: true }
                    GlassText { text: root.alertVm !== null ? "规则 " + root.alertVm.rules.length : "规则 0"; tone: "muted"; sizeHint: 12 }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    ComboBox {
                        id: assetPicker
                        Layout.preferredWidth: 280
                        model: root.alertVm !== null ? root.alertVm.assets : []
                        textRole: "label"
                        background: GlassSurface { tintAlpha: 0.2; surfaceRadius: GlassTokens.capsuleRadius(height) }
                    }
                    ComboBox {
                        id: conditionPicker
                        Layout.preferredWidth: 135
                        model: ["价格 ≥", "价格 ≤", "涨幅 ≥", "涨幅 ≤"]
                        background: GlassSurface { tintAlpha: 0.2; surfaceRadius: GlassTokens.capsuleRadius(height) }
                    }
                    TextField {
                        id: thresholdInput
                        Layout.preferredWidth: 130
                        placeholderText: conditionPicker.currentIndex >= 2 ? "阈值（%）" : "阈值价格"
                        validator: DoubleValidator { bottom: -100000000; top: 100000000; decimals: 6 }
                        selectByMouse: true
                        color: GlassTokens.textPrimary
                        background: GlassSurface { tintAlpha: 0.2; surfaceRadius: GlassTokens.capsuleRadius(height) }
                    }
                    GlassButton {
                        width: 106; height: 38; label: "添加预警"
                        enabled: root.alertVm !== null && assetPicker.count > 0 && thresholdInput.acceptableInput
                        onClicked: {
                            const conditions = ["price_above", "price_below", "change_above", "change_below"]
                            if (assetPicker.currentIndex >= 0) {
                                root.alertVm.addRule(root.alertVm.assets[assetPicker.currentIndex].canonical_id,
                                                    conditions[conditionPicker.currentIndex], Number(thresholdInput.text))
                            }
                            thresholdInput.clear()
                        }
                    }
                    Item { Layout.fillWidth: true }
                }

                GlassText {
                    visible: root.alertVm !== null && root.alertVm.error !== ""
                    text: root.alertVm !== null ? root.alertVm.error : ""
                    tone: "secondary"; sizeHint: 12
                }

                ListView {
                    id: ruleList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 8
                    model: root.alertVm !== null ? root.alertVm.rules : []
                    delegate: GlassSurface {
                        width: ruleList.width
                        height: 62
                        tintAlpha: 0.15
                        surfaceRadius: GlassTokens.capsuleRadius(height)
                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 10; spacing: 12
                            GlassText { Layout.preferredWidth: 210; text: modelData.name + " · " + modelData.symbol; tone: "primary"; sizeHint: 13 }
                            GlassText { Layout.preferredWidth: 130; text: modelData.condition_label + " " + modelData.threshold_label; tone: "secondary"; sizeHint: 13 }
                            GlassText { Layout.preferredWidth: 90; text: modelData.triggered ? "已触发" : modelData.enabled ? "监控中" : "已暂停"; tone: modelData.triggered ? "secondary" : "muted"; sizeHint: 12 }
                            Item { Layout.fillWidth: true }
                            GlassButton { width: 70; height: 32; label: modelData.enabled ? "暂停" : "启用"; onClicked: root.alertVm.setRuleEnabled(modelData.rule_id, !modelData.enabled) }
                            GlassButton { width: 70; height: 32; label: "删除"; onClicked: root.alertVm.removeRule(modelData.rule_id) }
                        }
                    }
                    GlassText {
                        anchors.centerIn: parent
                        visible: ruleList.count === 0
                        text: "还没有预警规则；添加规则后会在后台轮询行情。"
                        tone: "muted"; sizeHint: 14
                    }
                }
            }
        }
    }
}
