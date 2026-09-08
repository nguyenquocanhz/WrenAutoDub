import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Wren 1.0

// Bố cục cửa sổ sửa video. Sửa file này là đổi được giao diện, không cần
// động tới Python. Dữ liệu lấy từ đối tượng `app` do qml_app.py đưa sang.

ApplicationWindow {
    id: win
    width: 1320; height: 820
    visible: true
    title: "WrenAutoDub — Sửa video"
    color: pal.bg

    QtObject {
        id: pal
        readonly property color bg:      "#202124"
        readonly property color panel:   "#191b1f"
        readonly property color line:    "#2c3036"
        readonly property color text:    "#e2e5ea"
        readonly property color dim:     "#8d939b"
        readonly property color accent:  "#4884d6"
        readonly property color green:   "#1f8b4c"
    }

    component Btn: Rectangle {
        id: btn
        property alias text: lbl.text
        property bool primary: false
        signal clicked()
        implicitWidth: lbl.implicitWidth + 26
        implicitHeight: 32
        radius: 6
        color: primary ? (ma.pressed ? "#187a41" : ma.containsMouse ? "#25a259" : pal.green)
                       : (ma.pressed ? "#33373d" : ma.containsMouse ? "#2b2e33" : "#242730")
        border.color: primary ? "#2aa35c" : pal.line
        Text {
            id: lbl; anchors.centerIn: parent
            color: pal.text; font.pixelSize: 13
            font.bold: btn.primary
        }
        MouseArea {
            id: ma; anchors.fill: parent; hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: btn.clicked()
        }
        Behavior on color { ColorAnimation { duration: 110 } }
    }

    // ------------------------------------------------------------ thanh trên
    header: Rectangle {
        height: 52; color: pal.panel
        Rectangle { anchors.bottom: parent.bottom; width: parent.width
                    height: 1; color: pal.line }
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 14
            anchors.rightMargin: 12; spacing: 12
            Text { text: app.fileName; color: pal.text
                   font.pixelSize: 14; font.bold: true }
            Text { text: app.meta; color: pal.dim; font.pixelSize: 12 }
            Item { Layout.fillWidth: true }
            Btn { text: "Lưu"; onClicked: app.save() }
            Btn { text: "Xuất video"; primary: true; onClicked: app.exportVideo() }
        }
    }

    // ------------------------------------------------------------ thân
    SplitView {
        anchors.fill: parent
        orientation: Qt.Vertical

        // --- nửa trên
        SplitView {
            SplitView.fillHeight: true
            SplitView.minimumHeight: 240
            orientation: Qt.Horizontal

            RowLayout {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 360
                spacing: 8

                // rail công cụ
                Rectangle {
                    Layout.preferredWidth: 84; Layout.fillHeight: true
                    Layout.margins: 8
                    color: pal.panel; radius: 8
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: 6; spacing: 4
                        Repeater {
                            model: ["Phụ đề", "Hiệu ứng", "Tốc độ", "Xuất bản"]
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 44
                                radius: 6
                                color: rail.containsMouse ? "#2b2e33"
                                     : index === win.panel ? "#333941" : "transparent"
                                Text {
                                    anchors.centerIn: parent; text: modelData
                                    color: index === win.panel ? pal.text : pal.dim
                                    font.pixelSize: 12
                                }
                                MouseArea {
                                    id: rail; anchors.fill: parent; hoverEnabled: true
                                    onClicked: win.panel = index
                                }
                                Behavior on color { ColorAnimation { duration: 110 } }
                            }
                        }
                        Item { Layout.fillHeight: true }
                    }
                }

                // khung xem
                ColumnLayout {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    Layout.margins: 8; spacing: 6
                    PreviewView {
                        id: pv
                        Layout.fillWidth: true; Layout.fillHeight: true
                        Component.onCompleted: app.attachPreview(pv)
                        onRegionCommitted: app.onRegionCommitted()
                    }

                    // công cụ vùng hiệu ứng
                    RowLayout {
                        Layout.fillWidth: true; spacing: 6
                        Repeater {
                            model: [["Làm mờ", "blur"], ["Xoá logo", "delogo"],
                                    ["Chèn logo", "logo"]]
                            Btn {
                                text: modelData[0]
                                primary: win.tool === modelData[1]
                                onClicked: {
                                    win.tool = (win.tool === modelData[1]) ? "" : modelData[1]
                                    app.setTool(win.tool)
                                }
                            }
                        }
                        Btn {
                            text: "Xoá vùng"
                            onClicked: { pv.deleteSelected(); pv.update() }
                        }
                        Item { Layout.fillWidth: true }
                        ComboBox {
                            Layout.preferredWidth: 152
                            model: ["Nghe cả hai", "Chỉ tiếng gốc", "Chỉ thuyết minh"]
                            onCurrentIndexChanged: app.setMix(currentIndex)
                        }
                    }

                    // transport
                    RowLayout {
                        Layout.fillWidth: true; spacing: 6
                        Item { Layout.fillWidth: true }
                        Btn { text: "◀◀"; onClicked: app.seekBy(-5) }
                        Btn {
                            text: app.playing ? "❚❚" : "▶"
                            primary: app.playing
                            onClicked: app.togglePlay()
                        }
                        Btn { text: "▶▶"; onClicked: app.seekBy(5) }
                        Text {
                            text: app.timecode
                            color: pal.text
                            font.family: "Consolas"; font.pixelSize: 13
                            Layout.leftMargin: 10
                            Layout.preferredWidth: 140
                        }
                        Item { Layout.fillWidth: true }
                    }
                }
            }

            // bảng phải
            Rectangle {
                SplitView.preferredWidth: 420
                SplitView.minimumWidth: 260
                color: pal.panel; radius: 8

                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 12; spacing: 8

                    Text {
                        text: ["Phụ đề", "Hiệu ứng", "Tốc độ", "Xuất bản"][win.panel]
                        color: pal.text; font.pixelSize: 15; font.bold: true
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: pal.line }

                    StackLayout {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        currentIndex: win.panel

                        // ---------------------------------------- phụ đề
                        ColumnLayout {
                            spacing: 8
                            Text {
                                text: app.cueCount + " câu · bấm một dòng để nhảy tới"
                                color: pal.dim; font.pixelSize: 11
                            }
                            Rectangle {
                                Layout.fillWidth: true; Layout.fillHeight: true
                                color: "#16181c"; radius: 6; border.color: pal.line
                                clip: true

                                ListView {
                                    id: cueView
                                    anchors.fill: parent; anchors.margins: 3
                                    model: app.cueList
                                    spacing: 2
                                    currentIndex: app.activeCue
                                    ScrollBar.vertical: ScrollBar {}
                                    onCurrentIndexChanged:
                                        if (currentIndex >= 0)
                                            positionViewAtIndex(currentIndex, ListView.Contain)

                                    delegate: Rectangle {
                                        width: cueView.width - 6
                                        height: col.implicitHeight + 10
                                        radius: 5
                                        color: index === app.activeCue ? "#24405e"
                                             : rowMa.containsMouse ? "#232730" : "transparent"
                                        Behavior on color { ColorAnimation { duration: 100 } }

                                        MouseArea {
                                            id: rowMa
                                            anchors.fill: parent; hoverEnabled: true
                                            onClicked: app.gotoCue(index)
                                        }

                                        ColumnLayout {
                                            id: col
                                            anchors.left: parent.left
                                            anchors.right: parent.right
                                            anchors.verticalCenter: parent.verticalCenter
                                            anchors.leftMargin: 8; anchors.rightMargin: 8
                                            spacing: 2

                                            RowLayout {
                                                spacing: 6
                                                Text {
                                                    text: num
                                                    color: pal.dim; font.pixelSize: 10
                                                    Layout.preferredWidth: 22
                                                }
                                                Text {
                                                    text: start + "  →  " + end
                                                    color: pal.dim
                                                    font.family: "Consolas"; font.pixelSize: 10
                                                }
                                            }
                                            TextEdit {
                                                Layout.fillWidth: true
                                                text: line
                                                color: pal.text; font.pixelSize: 12
                                                wrapMode: TextEdit.Wrap
                                                selectByMouse: true
                                                onEditingFinished: app.cueList.setLine(index, text)
                                                Keys.onReturnPressed: focus = false
                                            }
                                        }
                                    }
                                }
                            }
                            Btn {
                                Layout.fillWidth: true
                                text: "Lưu phụ đề"
                                onClicked: app.saveSubs()
                            }
                        }

                        // ---------------------------------------- hiệu ứng
                        ColumnLayout {
                            spacing: 8
                            Text { text: app.regionCount + " vùng đã đặt"; color: pal.dim }
                            Text {
                                Layout.fillWidth: true
                                text: "Bật một công cụ dưới khung xem rồi kéo một khung trên hình. Kéo bốn góc để chỉnh, Xoá vùng để bỏ."
                                color: pal.dim; font.pixelSize: 11; wrapMode: Text.Wrap
                            }
                            Item { Layout.fillHeight: true }
                        }

                        // ---------------------------------------- tốc độ
                        ColumnLayout {
                            spacing: 8
                            Text { text: app.clipCount + " clip"; color: pal.dim }
                            Text {
                                Layout.fillWidth: true
                                text: "Cắt bằng nút Cắt hình, chọn clip trên dòng thời gian rồi Xoá clip để bỏ đoạn."
                                color: pal.dim; font.pixelSize: 11; wrapMode: Text.Wrap
                            }
                            Item { Layout.fillHeight: true }
                        }

                        // ---------------------------------------- xuất bản
                        ColumnLayout {
                            spacing: 10
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 62
                                radius: 6; color: "#20242a"; border.color: pal.line
                                Text {
                                    anchors.centerIn: parent; text: app.estimate
                                    color: "#cdd3da"; font.pixelSize: 12
                                }
                            }
                            Btn {
                                Layout.fillWidth: true
                                text: "Xuất video"; primary: true
                                onClicked: app.exportVideo()
                            }
                            Item { Layout.fillHeight: true }
                        }
                    }
                }
            }
        }

        // --- nửa dưới: thanh công cụ + dòng thời gian
        ColumnLayout {
            SplitView.preferredHeight: 280
            SplitView.minimumHeight: 160
            spacing: 4

            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: 42
                Layout.leftMargin: 8; Layout.rightMargin: 8
                color: pal.panel; radius: 6
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 8
                    anchors.rightMargin: 8; spacing: 6
                    Btn { text: "Cắt hình";  onClicked: app.action("split") }
                    Btn { text: "Ghép";      onClicked: app.action("merge") }
                    Btn { text: "Xoá clip";  onClicked: app.action("delete") }
                    Item { Layout.fillWidth: true }
                    Text { text: app.status; color: pal.dim; font.pixelSize: 12 }
                    Item { Layout.fillWidth: true }
                    Btn { text: "−"; onClicked: tl.setZoom(tl.zoom() / 1.6) }
                    Btn { text: "+"; onClicked: tl.setZoom(tl.zoom() * 1.6) }
                    Btn { text: "vừa khít"; onClicked: tl.setZoom(1.0) }
                }
            }

            TimelineView {
                id: tl
                Layout.fillWidth: true; Layout.fillHeight: true
                Layout.leftMargin: 8; Layout.rightMargin: 8
                Layout.bottomMargin: 8
                Component.onCompleted: app.attachTimeline(tl)
                onSeeked: tl.update()
                onCommitted: tl.update()
            }
        }
    }

    property int panel: 0
    property string tool: ""
}
