pragma Singleton
import QtQuick

// Session-scoped appearance controls shared by every liquid-glass surface.
// Keeping this presentation-only avoids coupling QML to settings/storage.
QtObject {
    // 1.25 gives the rose/sky/mint/gold/violet washes a little more depth
    // while preserving translucency. The navigation slider exposes 0.25–3.00.
    property real accentIntensity: 1.25

    // Per-surface editor state. Overrides stay in memory intentionally: the
    // visual layer never writes configuration or reaches the backend.
    property bool editMode: false
    property string selectedKey: ""
    property string selectedLabel: "尚未选择玻璃块"
    property color editorColor: "#CFE8FF"
    property real editorStrength: 0.22
    property color selectedBaseColor: "#CFE8FF"
    property real selectedBaseStrength: 0.22
    property var overrides: ({})
    property int revision: 0
    property int nextRuntimeId: 0

    signal selectionChanged()

    function allocateKey() {
        nextRuntimeId += 1
        return "runtime-glass-" + nextRuntimeId
    }

    function childIndex(parentItem, childItem) {
        if (parentItem === null || parentItem.children === undefined) return -1
        for (let index = 0; index < parentItem.children.length; ++index) {
            if (parentItem.children[index] === childItem) return index
        }
        return -1
    }

    function keyFor(item) {
        const parts = []
        let current = item
        while (current !== null && current !== undefined) {
            if (current.objectName !== undefined && current.objectName !== "") {
                parts.unshift(current.objectName)
            } else if (current.parent !== null && current.parent !== undefined) {
                parts.unshift("item-" + childIndex(current.parent, current))
            }
            current = current.parent
        }
        const path = parts.join("/")
        return path !== "" ? path : allocateKey()
    }

    function hasOverride(key) {
        const unused = revision
        return key !== "" && overrides[key] !== undefined
    }

    function tintFor(key, fallback) {
        const unused = revision
        return hasOverride(key) ? overrides[key].tint : fallback
    }

    function strengthFor(key, fallback) {
        const unused = revision
        return hasOverride(key)
            ? overrides[key].strength
            : Math.min(0.90, fallback * accentIntensity)
    }

    function selectSurface(key, label, fallbackTint, fallbackStrength) {
        selectedKey = key
        selectedLabel = label !== "" ? label : "玻璃块 " + key.replace("runtime-glass-", "#")
        selectedBaseColor = fallbackTint.a > 0.01 ? fallbackTint : "#CFE8FF"
        selectedBaseStrength = Math.max(0.12, Math.min(0.90,
            fallbackStrength * accentIntensity))
        if (hasOverride(key)) {
            editorColor = overrides[key].tint
            editorStrength = overrides[key].strength
        } else {
            editorColor = selectedBaseColor
            editorStrength = selectedBaseStrength
        }
        selectionChanged()
    }

    function applySelected(colorValue, strengthValue) {
        if (selectedKey === "") return
        const copy = Object.assign({}, overrides)
        copy[selectedKey] = {
            tint: colorValue,
            strength: Math.max(0.0, Math.min(0.90, strengthValue))
        }
        overrides = copy
        editorColor = colorValue
        editorStrength = copy[selectedKey].strength
        revision += 1
        selectionChanged()
    }

    function setSelectedColor(colorValue) {
        applySelected(colorValue, editorStrength)
    }

    function setSelectedStrength(strengthValue) {
        applySelected(editorColor, strengthValue)
    }

    function resetSelected() {
        if (selectedKey === "" || !hasOverride(selectedKey)) return
        const copy = Object.assign({}, overrides)
        delete copy[selectedKey]
        overrides = copy
        revision += 1
        editorColor = selectedBaseColor
        editorStrength = selectedBaseStrength
        selectionChanged()
    }
}
