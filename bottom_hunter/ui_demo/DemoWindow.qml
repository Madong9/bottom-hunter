// DemoWindow — ApplicationWindow wrapper so QQmlApplicationEngine gets a
// proper window root; embeds the reusable RainGlassDemo item.
import QtQuick
import QtQuick.Controls.Basic
import "components"

ApplicationWindow {
    id: appWindow

    width: 1440
    height: 900
    visible: true
    color: "#05070A"

    RainGlassDemo {
        id: demo
        anchors.fill: parent
        hostWindow: appWindow
    }

    function grabSnapshot(path) {
        demo.grabSnapshot(path)
    }
}
