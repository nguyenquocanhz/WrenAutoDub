import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Vỏ ứng dụng: ba màn hình nối tiếp thay vì một cửa sổ dựng duy nhất.
//
//     Mở  ->  Đang chạy  ->  Dựng
//
// Phản ánh đúng bản chất sản phẩm: một dây chuyền thuyết minh có kèm chỗ sửa,
// không phải một trình dựng đa dụng. Bản QML cũ mở thẳng vào timeline rỗng.
ApplicationWindow {
    id: win
    width: 1320; height: 860
    visible: true
    title: "WrenAutoDub"
    color: t.nen1

    Theme { id: t }

    property int man: manDau            // 0 mở, 1 đang chạy, 2 dựng

    StackLayout {
        anchors.fill: parent
        currentIndex: win.man

        Start {
            onBatDau: function (duongDan, lang) {
                win.man = 1
                pipe.start(duongDan, lang)
            }
        }

        Running {
            onXong: function (ketQua) {
                // Nạp dự án vào trình dựng rồi mới chuyển màn, không thì
                // timeline hiện ra rỗng một nhịp.
                app.moDuAn(pipe.video)
                win.man = 2
            }
            onDung: win.man = (pipe && pipe.result !== "") ? 2 : 0
        }

        Loader {
            // Chỉ dựng trình dựng khi thật sự cần: nó nạp video, sóng âm và
            // ảnh dải phim, tốn vài giây và vài trăm MB.
            active: win.man === 2
            sourceComponent: EditorView {}
        }
    }
}
