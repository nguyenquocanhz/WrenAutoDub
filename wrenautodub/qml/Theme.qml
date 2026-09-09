import QtQuick

// Thang màu dùng chung cho mọi màn hình QML. Đối ứng với wrenautodub/theme.py
// bên Python — sửa một bên thì sửa cả bên kia.
//
// Hai tầng như cách CapCut tổ chức 365 biến CSS của họ: tầng gốc chỉ là giá
// trị, tầng vai trò trỏ vào tầng gốc. Đổi diện mạo thì sửa tầng vai trò.
QtObject {
    // ---- tầng 1: nền, bảy bậc, đều ngả xanh nhẹ
    readonly property color nen0: "#0e0f12"     // sâu nhất — khung video
    readonly property color nen1: "#141518"
    readonly property color nen2: "#191b1f"     // ô nhập, danh sách
    readonly property color nen3: "#1e2024"     // thẻ, panel
    readonly property color nen4: "#26282e"     // nền cửa sổ
    readonly property color nen5: "#303338"     // nút, đường kẻ
    readonly property color nen6: "#3a3c42"     // viền rõ, hover

    readonly property color chu0: "#fcfaee"
    readonly property color chu1: "#e2e4e8"
    readonly property color chu2: "#969aa0"
    readonly property color chu3: "#6e7278"

    // ---- màu nhấn: hổ phách, theo đề xuất của bản thiết kế.
    // Xanh #4884d6 cũ là xanh Windows mặc định, trùng tông với mọi trình dựng
    // khác nên ảnh chụp lẫn vào nhau.
    readonly property color nhan:  "#e0a24b"
    readonly property color nhanH: "#edb061"
    readonly property color nhanN: "#c88c3a"
    readonly property color nhanNen: "#2b2418"

    readonly property color ok:    "#46b9a3"
    readonly property color okNen: "#16302c"
    readonly property color loi:   "#e07a63"
    readonly property color loiNen: "#251a17"

    // ---- thang số, giống bên Python
    readonly property int rNho: 2
    readonly property int rVua: 4
    readonly property int rLon: 8
    readonly property int rThe: 10

    readonly property int fNho: 11
    readonly property int fThuong: 12
    readonly property int fVua: 14
    readonly property int fTo: 17
    readonly property int fTieuDe: 26
}
