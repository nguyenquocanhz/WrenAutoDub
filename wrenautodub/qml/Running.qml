import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Màn hình theo dõi chuỗi 4 bước — phần lõi của sản phẩm mà bản QML cũ không
// hề có. Thẻ bước đã xong gập lại một dòng, thẻ đang chạy nở ra với số liệu
// thật, để mắt người dùng đi thẳng tới chỗ đang diễn ra.
Item {
    id: man
    signal xong(string ketQua)
    signal dung()

    Theme { id: t }
    Rectangle { anchors.fill: parent; color: t.nen1 }

    // Gói trạng thái pipeline thành thuộc tính của màn hình. Bên trong delegate
    // của Repeater thì `pipe` tra ra null, mà rải `pipe ? ... : ...` khắp nơi
    // thì rối — gom một chỗ vừa hết lỗi vừa dễ đọc.
    readonly property int      pBuoc: pipe ? pipe.stage : 0
    readonly property real     pTrong: pipe ? pipe.stageFrac : 0
    readonly property real     pTong: pipe ? pipe.overall : 0
    readonly property bool     pChay: pipe ? pipe.running : false
    readonly property string   pLoi: pipe ? pipe.error : ""
    readonly property string   pKetQua: pipe ? pipe.result : ""
    readonly property string   pChiTiet: pipe ? pipe.detail : ""
    readonly property int      pEpQua: pipe ? pipe.overFitted : 0
    readonly property var      pXong: pipe ? pipe.stageDone : ["", "", "", ""]
    readonly property var      pNhatKy: pipe ? pipe.logLines : []
    readonly property string   pMay: pipe ? pipe.engineInfo : ""
    readonly property string   pVram: pipe ? pipe.vram : ""
    readonly property string   pODia: pipe ? pipe.workSize : ""
    readonly property string   pTroi: pipe ? pipe.elapsed : ""
    readonly property int      pCau: pipe ? pipe.cueIndex : 0
    readonly property int      pCauTong: pipe ? pipe.cueTotal : 0
    readonly property string   pCauVi: pipe ? pipe.cueVi : ""
    readonly property string   pCauGoc: pipe ? pipe.cueGoc : ""
    readonly property string   pCauMoc: pipe ? pipe.cueTime : ""
    readonly property string   pTocDo: pipe ? pipe.speed : ""
    readonly property string   pConLai: pipe ? pipe.remain : ""
    readonly property bool     pNgheDuoc: pipe ? pipe.canPlay : false

    readonly property var tenBuoc: [
        "Lấy lời thoại gốc", "Dịch sang tiếng Việt",
        "Thuyết minh", "Ghép video"]
    readonly property var moTaBuoc: [
        "nhận dạng tiếng nói, hoặc đọc phụ đề nung sẵn trên hình",
        "Google Translate, có lượt vá cho câu dịch hỏng",
        "VieNeu-TTS đọc rồi ép khớp khung thời gian từng câu",
        "trộn hai track tiếng, ghép phụ đề vào phim"]

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 14

        // ---------------------------------------------------- đầu trang
        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            ColumnLayout {
                spacing: 2
                Layout.fillWidth: true
                Text {
                    text: man.pBuoc > 0
                          ? "Bước " + man.pBuoc + " / 4 — " + man.tenBuoc[man.pBuoc - 1]
                          : "Đang chuẩn bị…"
                    color: t.chu0
                    font.pixelSize: t.fTo
                    font.weight: Font.DemiBold
                }
                Text {
                    text: (man.pConLai !== "" ? "còn khoảng " + man.pConLai + "  ·  " : "")
                          + (man.pChiTiet !== "" ? man.pChiTiet
                             : (man.pChay ? "đang chạy…" : ""))
                    color: t.chu2
                    font.pixelSize: t.fThuong
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }
            Button {
                text: man.pChay ? "Dừng" : "Quay lại"
                onClicked: { if (man.pChay) pipe.stop(); man.dung() }
            }
        }

        // ---------------------------------------------------- tiến độ tổng
        // Chia đoạn đúng theo tỉ trọng thời gian thật của từng bước, nên không
        // bao giờ đứng im ở 50% suốt nửa thời gian.
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 6
            radius: 3
            color: t.nen3
            Rectangle {
                width: parent.width * Math.max(0, Math.min(1, man.pTong))
                height: parent.height
                radius: parent.radius
                color: t.nhan
                Behavior on width { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
            }
        }

        // ---------------------------------------------------- bốn thẻ bước
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 8

            Repeater {
                model: 4
                delegate: Rectangle {
                    required property int index
                    readonly property int so: index + 1
                    readonly property bool dangChay: man.pBuoc === so && man.pChay
                    readonly property bool daXong: man.pBuoc > so
                                                   || (!man.pChay && man.pBuoc === so
                                                       && man.pLoi === "")

                    Layout.fillWidth: true
                    Layout.preferredHeight: dangChay ? 96 : 44
                    radius: t.rThe
                    color: dangChay ? t.nen3 : t.nen2
                    border.width: 1
                    border.color: dangChay ? t.nhan : t.nen5
                    Behavior on Layout.preferredHeight {
                        NumberAnimation { duration: 160; easing.type: Easing.OutCubic }
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 12

                        // huy hiệu số bước
                        Rectangle {
                            Layout.alignment: Qt.AlignTop
                            width: 20; height: 20; radius: 10
                            color: daXong ? t.okNen : (dangChay ? t.nhanNen : t.nen4)
                            border.width: 1
                            border.color: daXong ? t.ok : (dangChay ? t.nhan : t.nen6)
                            Text {
                                anchors.centerIn: parent
                                text: daXong ? "✓" : so
                                color: daXong ? t.ok : (dangChay ? t.nhan : t.chu3)
                                font.pixelSize: t.fNho
                                font.weight: Font.DemiBold
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4

                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    text: man.tenBuoc[index]
                                    color: dangChay ? t.chu0 : (daXong ? t.chu1 : t.chu3)
                                    font.pixelSize: t.fVua
                                    font.weight: dangChay ? Font.DemiBold : Font.Normal
                                }
                                Item { Layout.fillWidth: true }
                                Text {
                                    text: man.pXong[index] || ""
                                    color: t.chu2
                                    font.pixelSize: t.fNho
                                }
                            }

                            Text {
                                visible: dangChay
                                text: man.moTaBuoc[index]
                                color: t.chu2
                                font.pixelSize: t.fNho
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }

                            // thanh tiến độ riêng của bước đang chạy
                            Rectangle {
                                visible: dangChay
                                Layout.fillWidth: true
                                Layout.preferredHeight: 4
                                radius: 2
                                color: t.nen1
                                Rectangle {
                                    width: parent.width * Math.max(0, Math.min(1, man.pTrong))
                                    height: parent.height
                                    radius: parent.radius
                                    color: t.nhan
                                    Behavior on width { NumberAnimation { duration: 240 } }
                                }
                            }
                        }
                    }
                }
            }
        }

        // ---------------------------------------------------- câu đang đọc
        // Chờ mấy phút mà màn hình không có gì chuyển động thì rất dài. Cho
        // thấy đúng câu đang được đọc, song ngữ, để biết nó đang tới đâu
        // trong phim và bản dịch có ra hồn không.
        Rectangle {
            visible: man.pCauVi !== "" && man.pChay
            Layout.fillWidth: true
            Layout.preferredHeight: 74
            radius: t.rThe
            color: t.nen2
            border.width: 1
            border.color: t.nen5

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 3

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Text {
                        text: "đang đọc"
                        color: t.nhan
                        font.pixelSize: t.fNho
                        font.weight: Font.DemiBold
                    }
                    Text {
                        text: "câu " + man.pCau + " / " + man.pCauTong
                              + (man.pCauMoc !== "" ? "  ·  " + man.pCauMoc : "")
                        color: t.chu3
                        font.pixelSize: t.fNho
                    }
                    Item { Layout.fillWidth: true }
                    // Mảnh audio đã nằm sẵn trong pieces/ — nghe thử ngay câu
                    // vừa đọc xong, không phải chờ hết cả phim rồi mới biết
                    // giọng có ra hồn không.
                    Button {
                        visible: man.pNgheDuoc
                        text: "▶ nghe thử"
                        font.pixelSize: t.fNho
                        implicitHeight: 24
                        onClicked: pipe.playCue()
                    }
                }
                Text {
                    text: man.pCauGoc
                    color: t.chu3
                    font.pixelSize: t.fNho
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Text {
                    text: man.pCauVi
                    color: t.chu0
                    font.pixelSize: t.fVua
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }
        }

        // ---------------------------------------------------- dải tài nguyên
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            visible: man.pChay || man.pTroi !== ""

            Repeater {
                model: [
                    ["đã chạy",   man.pTroi],
                    ["tốc độ",    man.pTocDo],
                    ["VRAM",      man.pVram],
                    ["thư mục",   man.pODia],
                    ["giọng đọc", man.pMay]
                ]
                delegate: Rectangle {
                    required property var modelData
                    visible: modelData[1] !== ""
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    radius: t.rLon
                    color: t.nen2
                    ColumnLayout {
                        anchors.centerIn: parent
                        spacing: 0
                        Text {
                            text: modelData[0]
                            color: t.chu3
                            font.pixelSize: t.fNho
                            Layout.alignment: Qt.AlignHCenter
                        }
                        Text {
                            text: modelData[1]
                            color: t.chu1
                            font.pixelSize: t.fThuong
                            Layout.alignment: Qt.AlignHCenter
                        }
                    }
                }
            }
        }

        // ---------------------------------------------------- cảnh báo ép quá tay
        // Đây là việc người dùng phải làm SAU khi chạy xong, mà giao diện cũ
        // không hề chỉ ra. Biến việc mơ hồ "nghe lại cả phim" thành một con số.
        Rectangle {
            visible: man.pEpQua > 0
            Layout.fillWidth: true
            Layout.preferredHeight: 38
            radius: t.rLon
            color: t.loiNen
            border.width: 1
            border.color: t.loi
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                Text {
                    text: man.pEpQua + " câu bị ép quá 1.4× — nghe có thể hụt hơi"
                    color: t.loi
                    font.pixelSize: t.fThuong
                    Layout.fillWidth: true
                }
                Text {
                    text: "sửa được ở bước dựng, không phải chạy lại cả phim"
                    color: t.chu2
                    font.pixelSize: t.fNho
                }
            }
        }

        // ---------------------------------------------------- nhật ký
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 90
            radius: t.rLon
            color: t.nen0
            border.width: 1
            border.color: t.nen5

            ListView {
                id: nhatKy
                anchors.fill: parent
                anchors.margins: 8
                clip: true
                model: man.pNhatKy
                delegate: Text {
                    required property string modelData
                    width: nhatKy.width
                    text: modelData
                    color: t.chu2
                    font.pixelSize: t.fNho
                    font.family: "Consolas, monospace"
                    wrapMode: Text.NoWrap
                    elide: Text.ElideRight
                }
                onCountChanged: positionViewAtEnd()
            }
        }

        // ---------------------------------------------------- xong / lỗi
        Rectangle {
            visible: !man.pChay && (man.pKetQua !== "" || man.pLoi !== "")
            Layout.fillWidth: true
            Layout.preferredHeight: 52
            radius: t.rLon
            color: man.pLoi !== "" ? t.loiNen : t.okNen
            border.width: 1
            border.color: man.pLoi !== "" ? t.loi : t.ok

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 10
                spacing: 10
                Text {
                    Layout.fillWidth: true
                    text: man.pLoi !== "" ? man.pLoi : "Xong: " + man.pKetQua
                    color: man.pLoi !== "" ? t.loi : t.chu0
                    font.pixelSize: t.fThuong
                    elide: Text.ElideMiddle
                }
                Button {
                    visible: man.pLoi === "" && man.pKetQua !== ""
                    text: "Mở trình dựng"
                    onClicked: man.xong(man.pKetQua)
                }
            }
        }
    }
}
