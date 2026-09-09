import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Màn hình đầu: chọn phim. Trước đây bản QML mở thẳng vào trình dựng với
// timeline rỗng — người dùng có một file phim trong tay mà không biết bỏ vào
// đâu.
Item {
    id: man
    property alias video: o.video

    signal batDau(string duongDan, string lang)

    Theme { id: t }
    Rectangle { anchors.fill: parent; color: t.nen1 }

    QtObject {
        id: o
        property string video: ""
        property string ten: ""
        property string thongTin: ""
    }

    DropArea {
        anchors.fill: parent
        onEntered: function (d) { khung.keo = true }
        onExited: khung.keo = false
        onDropped: function (d) {
            khung.keo = false
            if (d.hasUrls && d.urls.length > 0)
                man.nhan(d.urls[0].toString())
        }
    }

    function nhan(url) {
        var p = app.duongDanTuUrl(url)
        if (!p) return
        o.video = p
        o.ten = app.tenFile(p)
        o.thongTin = app.thongTinPhim(p)
    }

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(parent.width - 80, 620)
        spacing: 20

        Text {
            text: "WrenAutoDub"
            color: t.chu0
            font.pixelSize: t.fTieuDe
            font.weight: Font.DemiBold
            Layout.alignment: Qt.AlignHCenter
        }
        Text {
            text: "Thuyết minh tiếng Việt cho phim nước ngoài, chạy hoàn toàn trên máy bạn"
            color: t.chu2
            font.pixelSize: t.fVua
            Layout.alignment: Qt.AlignHCenter
        }

        // ---- vùng thả file
        Rectangle {
            id: khung
            property bool keo: false
            Layout.fillWidth: true
            Layout.preferredHeight: 176
            radius: t.rThe
            color: keo ? t.nhanNen : t.nen2
            border.width: 1
            border.color: keo ? t.nhan : t.nen6
            Behavior on color { ColorAnimation { duration: 110 } }

            ColumnLayout {
                anchors.centerIn: parent
                spacing: 10
                visible: o.video === ""

                Text {
                    text: "Kéo file phim vào đây"
                    color: t.chu1
                    font.pixelSize: t.fTo
                    font.weight: Font.DemiBold
                    Layout.alignment: Qt.AlignHCenter
                }
                Text {
                    text: "mkv · mp4 · avi · mov · ts"
                    color: t.chu3
                    font.pixelSize: t.fNho
                    Layout.alignment: Qt.AlignHCenter
                }
                Button {
                    text: "Chọn file…"
                    Layout.alignment: Qt.AlignHCenter
                    onClicked: man.nhan(app.chonPhim())
                }
            }

            ColumnLayout {
                anchors.centerIn: parent
                width: parent.width - 40
                spacing: 6
                visible: o.video !== ""

                Text {
                    text: o.ten
                    color: t.chu0
                    font.pixelSize: t.fVua
                    font.weight: Font.DemiBold
                    elide: Text.ElideMiddle
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                }
                Text {
                    text: o.thongTin
                    color: t.chu2
                    font.pixelSize: t.fThuong
                    Layout.alignment: Qt.AlignHCenter
                }
                Button {
                    text: "Đổi file khác"
                    flat: true
                    Layout.alignment: Qt.AlignHCenter
                    onClicked: { o.video = ""; o.ten = ""; o.thongTin = "" }
                }
            }
        }

        // ---- nút chạy
        Button {
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            enabled: o.video !== ""
            text: "Bắt đầu thuyết minh"
            font.pixelSize: t.fVua
            font.weight: Font.DemiBold
            background: Rectangle {
                radius: t.rLon
                color: !parent.enabled ? t.nen3
                       : parent.down ? t.nhanN
                       : parent.hovered ? t.nhanH : t.nhan
            }
            contentItem: Text {
                text: parent.text
                color: parent.enabled ? "#241a08" : t.chu3
                font: parent.font
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            onClicked: man.batDau(o.video, "")
        }

        // Tính năng có thật mà giao diện chưa bao giờ nói ra: mọi bước ghi kết
        // quả xuống phim_work/, chạy lại là đi tiếp chứ không làm lại từ đầu.
        Text {
            text: "Dừng giữa chừng thoải mái — chạy lại sẽ đi tiếp từ chỗ dở, không làm lại từ đầu."
            color: t.chu3
            font.pixelSize: t.fNho
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            Layout.fillWidth: true
        }
    }
}
