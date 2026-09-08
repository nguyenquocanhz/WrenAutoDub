# Đóng gói WrenAutoDub thành .exe

Người dùng hiện phải cài Python, khoảng 10 package và ffmpeg trước khi chạy
được dòng lệnh đầu tiên. Rào cản đó giết lượt tải. Tài liệu này ghi lại kết
quả nghiên cứu đóng gói bằng PyInstaller: **cái gì chạy được thật, cái gì
không, và giá phải trả.**

Mọi con số dưới đây là **đo thật trên máy phát triển**, không phải ước lượng.
Chỗ nào chưa kiểm thì có ghi rõ.

---

## Kết luận ngắn

**Đóng gói được, và bản đóng gói chạy thật.** Nhưng không xoá được hoàn toàn
rào cản, vì ba lý do không thể vòng qua:

| Vướng | Xử lý được? |
|---|---|
| File `.qml`, plugin Qt, module QtQuick | **Được.** Đã chạy thật. |
| DLL CUDA (`cublas64_12.dll`) | **Được, nhưng tốn 1,9 GB.** Cần runtime hook riêng. |
| `vieneu` (engine TTS mặc định) | **Không.** Kéo theo torch ~2,5 GB. Phải bỏ. |
| `ffmpeg` / `ffprobe` | **Không.** Người dùng vẫn phải tự cài. |

Rào cản giảm từ *"cài Python + 10 package + ffmpeg"* xuống *"giải nén + cài
ffmpeg"*. Đó là tiến bộ thật, nhưng ffmpeg vẫn còn đó — và không có cách nào
bỏ nó đi mà vẫn giữ được giấy phép cùng dung lượng hợp lý.

---

## Đã kiểm chứng được những gì

Chạy trên: Windows 10 Pro 19045, Python 3.14.6, PyInstaller 6.22.0,
PyQt6 6.11.0, GTX 1650 Ti 4 GB.

| Việc | Kết quả |
|---|---|
| Build hoàn tất | Có, mã thoát 0 |
| `WrenAutoDub.exe doctor --quick` | Có, mã thoát 0, bảng hiện đủ |
| `WrenAutoDub.exe doctor` (đầy đủ) | Có — Google Translate và edge-tts đều phản hồi |
| **Cửa sổ Widgets `gui` mở thật** | Có — tiêu đề `WrenAutoDub` |
| **Cửa sổ sửa video Widgets `edit`** | Có — tiêu đề `WrenAutoDub — Sửa video` |
| **Cửa sổ QML `edit --qml`** | Có — QML V4 dựng xong delegate, cửa sổ hiện |
| `editor.qml` vào đúng `_internal/wrenautodub/qml/` | Có |
| Plugin `platforms/qwindows.dll` | Có |
| Module `QtQuick`, `QtQuick/Controls`, `QtQuick/Layouts` kèm `qmldir` | Có |
| ffmpeg/ffprobe vẫn tìm thấy qua PATH hệ thống | Có |
| CUDA chạy trong bundle | Có — nhưng chỉ khi bật `WREN_PACK_CUDA=1` |
| `vieneu` trong bundle | Không — bị loại có chủ đích |
| Đủ 25 module của app trong bundle | Có — kiểm bằng `Analysis-00.toc` |

Ba giao diện được mở bằng cách chạy exe thật với một file `.mp4` 3 giây dựng
bằng `ffmpeg -f lavfi -i testsrc`, đợi 9–12 giây rồi đọc tiêu đề cửa sổ của
tiến trình. Cả ba đều còn sống và có cửa sổ thật, không phải chỉ "không nổ".

Kích thước đo được:

| Bản | Dung lượng | Số file |
|---|---|---|
| Không CUDA | **443 MB** | 3 185 |
| Có CUDA (`WREN_PACK_CUDA=1`) | **2 423 MB** | 3 201 |

Chênh lệch đúng bằng 16 file DLL CUDA, 1 980 MB: cuDNN 1 066 MB (10 file),
cuBLAS 736 MB (3 file), NVRTC 178 MB (3 file).

---

## Cách build

```bat
pip install pyinstaller
cd D:\đường\dẫn\tới\repo
pyinstaller packaging\wrenautodub.spec --noconfirm
```

Chạy **từ thư mục gốc repo**, không phải từ trong `packaging/`. Kết quả nằm ở
`dist\WrenAutoDub\`.

Muốn kèm CUDA (bundle phồng lên ~2,4 GB):

```bat
set WREN_PACK_CUDA=1
pyinstaller packaging\wrenautodub.spec --noconfirm
```

Đừng để `build/` và `dist/` lọt vào repo — `.gitignore` là danh sách trắng nên
hiện đã chặn sẵn, nhưng vẫn nên build ra thư mục ngoài:

```bat
pyinstaller packaging\wrenautodub.spec --noconfirm ^
    --workpath %TEMP%\wren-build --distpath %TEMP%\wren-dist
```

---

## Sáu chỗ vướng thật

### 1. File `.qml` không phải là `import` — PyInstaller không thấy

Đây là chỗ dễ mất thời gian nhất, vì **nó hỏng mà không báo lỗi.**

`qml_app.py` tính đường dẫn bằng `Path(__file__).parent / "qml"`. PyInstaller
chỉ lần theo `import` của Python; `editor.qml` không phải import nên mặc định
không được gom. Kết quả: build thành công, exe chạy, cửa sổ QML **im lặng
không hiện gì** vì `engine.rootObjects()` rỗng.

Xử lý — một dòng trong `datas`:

```python
datas = [(str(REPO / "wrenautodub" / "qml"), "wrenautodub/qml")]
```

May là code không phải sửa gì. Trong bundle onedir, `__file__` của
`qml_app.py` trỏ vào `_internal/wrenautodub/`, nên đặt file `.qml` đúng vị trí
tương đối là `Path(__file__).parent / "qml"` tự khớp.

**Đã kiểm:** `_internal\wrenautodub\qml\editor.qml` có mặt trong bundle.

### 2. Plugin Qt6 và module QtQuick — hoá ra PyInstaller lo được

Chỗ này nhẹ hơn dự đoán. PyInstaller 6.22 có sẵn `hook-PyQt6.QtQml.py`, và
hook đó gọi `pyqt6_library_info.collect_qtqml_files()` để gom cả cây QML.

Kiểm tra trong bundle, có đủ:

- `PyQt6/Qt6/plugins/platforms/` — `qwindows.dll`, `qminimal.dll`,
  `qoffscreen.dll`
- các nhóm plugin `styles`, `imageformats`, `iconengines`, `multimedia`,
  `networkinformation`, `tls`, `generic`
- `PyQt6/Qt6/qml/QtQuick/`, `QtQuick/Controls/`, `QtQuick/Layouts/`,
  `QtQml/` — đều kèm `qmldir`

Đúng bốn dòng `import` mà `editor.qml` cần.

Hai điều cần biết:

- **`qmltooling` không được gom.** Nó chỉ phục vụ trình gỡ lỗi QML, không cần
  lúc chạy. Chỉ thiếu nếu bạn muốn attach QML debugger vào bản đóng gói.
- **PyQt6 vẫn là phần nặng nhất: 163 MB.** Đã loại thẳng những module chắc
  chắn không dùng (`QtWebEngine*`, `Qt3D*`, `QtCharts`, `QtSql`,
  `QtBluetooth`...) trong `EXCLUDES` của file spec. Đừng loại `QtQml`,
  `QtQuick`, `QtMultimedia`, `QtWidgets`, `QtGui`, `QtCore` — app dùng cả.
- **Đừng bật UPX.** Nó hay làm hỏng DLL Qt. Spec đã đặt `upx=False`.

### 3. DLL CUDA — chỗ đau nhất

`CLAUDE.md` đã ghi sẵn: Windows không tự tìm `cublas64_12.dll` trong package
pip `nvidia-*`, phải gọi `cudafix.enable_cuda_dlls()` trước khi import
ctranslate2. **Trong bundle, `cudafix.py` một mình không đủ.**

Lý do: `cudafix` dò bằng `import nvidia` rồi đọc `nvidia.__path__`. Trong
bundle, package `nvidia` bị nén vào kho nội bộ nên `__path__` không còn là
thư mục thật; nhánh dự phòng quét `sys.path` cũng không tới được.

Triệu chứng **đã dựng lại được thật** trên bản build không kèm CUDA:

```
!  DLL CUDA          không tìm thấy package nvidia-*
!  CTranslate2 CUDA  1 thiết bị | float16, float32, int8, int8_float16   <- đánh lừa
!  Chạy thử CUDA     Library cublas64_12.dll is not found — sẽ tự lùi về CPU
```

Để ý dòng giữa: `CTranslate2 CUDA` vẫn báo **OK, 1 thiết bị**. Nó chỉ hỏi
driver nên vẫn thấy card; đến lúc nạp model thật mới nổ. Nghĩa là **`doctor`
báo xanh vẫn có thể đang chạy CPU** — kiểu hỏng âm thầm, người dùng chỉ thấy
"bản exe chậm hơn bản Python" mà không hiểu vì sao.

**Cơ chế xử lý đã được kiểm chứng riêng.** Chạy lại đúng bản exe đó nhưng
thêm thủ công các thư mục `nvidia/*/bin` vào `PATH`:

```
OK  Chạy thử CUDA     tiny/int8_float16 nhận dạng được
```

Nên hướng đi là đúng. `packaging/rthook_cuda.py` làm việc đó tự động: chạy
trước mọi code của app, thêm `_MEIPASS/nvidia/*/bin` vào **cả**
`os.add_dll_directory()` **và** `PATH`. Cần cả hai — `add_dll_directory` phủ
DLL do Python nạp trực tiếp, còn `cublas64_12.dll` là do `ctranslate2.dll`
nạp tiếp, trường hợp này chỉ `PATH` mới tới.

Kết quả sau khi bật `WREN_PACK_CUDA=1`:

```
OK  DLL CUDA          3 thư mục
OK  CTranslate2 CUDA  1 thiết bị | float16, float32, int8, int8_float16, int8_float32
```

**Giá phải trả: 1 980 MB.** Bundle từ 443 MB thành 2 423 MB. Tải về 2,4 GB
để dùng một app thuyết minh phim là quá đáng, và người không có card NVIDIA
tải về hoàn toàn vô ích.

### 4. `vieneu` kéo theo torch — phải bỏ

`tts.py` có `from vieneu import Vieneu` nằm trong hàm. PyInstaller phân tích
tĩnh nên vẫn thấy dòng đó và sẽ kéo cả `vieneu` → `torch` → `transformers`
vào bundle, thành vài GB nữa.

Spec loại thẳng `vieneu`, `torch`, `torchaudio`, `torchvision`,
`transformers`.

**Hệ quả phải nói thẳng với người dùng:** engine TTS mặc định là `vieneu`,
nên bản `.exe` **bắt buộc chạy với `--tts edge`**. Mà `edge-tts` gọi ra server
Microsoft, nghĩa là bản đóng gói **không còn "chạy hoàn toàn local"** như mô
tả trong `README.md`. Ai cần vieneu thì vẫn phải cài Python theo cách thường.

Đây là mâu thuẫn thật giữa "dễ cài" và "chạy local", chưa có cách dung hoà.

**Đã kiểm:** `doctor` trong bundle báo `! vieneu chưa cài
(ModuleNotFoundError)`, đúng như thiết kế.

### 5. `ffmpeg` không gói bằng pip được

`ffmpeg.exe` + `ffprobe.exe` bản full (có `rubberband`) khoảng 150 MB. pip
không cài được, và app gọi chúng bằng `subprocess` chứ không qua thư viện.

Ba lựa chọn, chưa chọn cái nào:

1. **Để người dùng tự cài** (hiện tại). Đơn giản, nhưng vẫn là rào cản — và
   là rào cản khó nhất với người không rành máy tính, vì còn phải sửa PATH.
2. **Kèm ffmpeg vào thư mục `dist`** rồi cho app tự dò cạnh `sys.executable`
   trước khi tra PATH. Gọn nhất cho người dùng. Nhưng phải sửa code ngoài
   phạm vi thư mục này (chỗ gọi `shutil.which`), nên chưa làm.
3. **Trình cài đặt tự tải ffmpeg** lần chạy đầu. Tránh phình file tải về,
   nhưng thêm một chỗ hỏng mới và cần mạng.

Nếu chọn cách 2, chú ý **giấy phép**: dự án là AGPL-3.0. Bản ffmpeg build kèm
`--enable-gpl` là GPL, phân phối chung được, nhưng phải kèm ghi chú giấy phép
và nguồn. Bản có `--enable-nonfree` thì **không được phân phối** — nên nếu
làm, phải chốt chính xác đang kèm bản build nào.

### 6. Module import trễ bị rụng im lặng

Gặp thật trong lúc dựng tài liệu này, nên ghi lại.

Gần như toàn bộ module của app được import **bên trong hàm**, không phải ở
đầu file — ví dụ `from . import asr as S1` nằm trong hàm chạy pipeline.
PyInstaller xếp chúng vào loại `delayed`. Một lần build, `wrenautodub.asr`
không được gom (file bị sửa đúng lúc phân tích), và:

- build vẫn **thành công**, mã thoát 0
- exe vẫn **chạy**, `doctor` vẫn ra bảng
- chỉ có một dòng đổi: `Chạy thử CUDA: No module named 'wrenautodub.asr' —
  sẽ tự lùi về CPU`

Vì `doctor.py` bọc `from .asr import load_model` trong `try/except Exception`,
module thiếu hẳn trông y hệt CUDA hỏng. Không đọc `warn-WrenAutoDub.txt` thì
gần như không lần ra.

Xử lý: spec khai báo thẳng **toàn bộ** module của app vào `hiddenimports`,
không dựa vào phân tích tĩnh.

**Cách tự kiểm sau mỗi lần build:**

```bat
findstr /C:"invalid module" build\WrenAutoDub\warn-WrenAutoDub.txt
findstr /C:"wrenautodub." build\WrenAutoDub\Analysis-00.toc
```

Dòng `invalid module named wrenautodub.*` nghĩa là PyInstaller **không parse
được** file đó — khác hẳn với module bị `excludes` loại. Thấy dòng này thì
đừng phát hành bản build đó.

---

## Rác lọt vào bundle

Lần build đầu ra 564 MB / 5 793 file. Soi ra một loạt thứ không dòng code nào
của WrenAutoDub chạm tới, lọt vào theo dependency phụ:

| Package | Dung lượng |
|---|---|
| `pyarrow` | 78,9 MB |
| `botocore` | 17,6 MB |
| `PIL` | 12,7 MB |
| `lxml` | 6,7 MB |

Loại hết trong `EXCLUDES`, bundle từ 564 MB / 5 793 file xuống **443 MB /
3 185 file** — bớt được 121 MB và hơn 2 600 file.

**Lưu ý khi sửa danh sách này:** máy phát triển có sẵn nhiều package của dự án
khác trong cùng `site-packages`, nên rác lọt vào phụ thuộc vào từng máy. Build
trong môi trường ảo sạch chỉ cài `requirements.txt` sẽ ra bundle nhỏ hơn và
ổn định hơn. **Chưa thử cách đó** — nên làm trước khi phát hành thật.

---

## Khuyến nghị phát hành

Không nên phát hành một bản 2,4 GB.

**Nên làm:** phát hành bản **không kèm CUDA** (443 MB). Nó chạy đúng, chỉ là
ASR chạy CPU. Ai có card NVIDIA thì hướng dẫn cài Python theo cách thường —
họ vốn là nhóm rành máy hơn.

**Phải ghi rõ trong phần mô tả bản phát hành**, không giấu ở cuối:

- Vẫn cần cài **ffmpeg** riêng (bản full, có `rubberband`).
- Chạy CPU. Có card NVIDIA muốn nhanh thì cài theo cách thường.
- Chỉ hỗ trợ `--tts edge`, **cần mạng**. Muốn `vieneu` chạy local thì cài theo
  cách thường.

Ba dòng đó thẳng thắn hơn là để người dùng tự phát hiện sau khi tải 443 MB.

Về AGPL-3.0: bản `.exe` là phân phối phần mềm, nên phải kèm `LICENSE` và cách
lấy mã nguồn tương ứng. Đừng quên khi dựng file phát hành.

---

## Chưa kiểm — đừng tưởng là đã xong

Ghi rõ ra để không ai nhầm:

- **Chưa bấm thử nút nào.** Ba cửa sổ đã mở được thật, nhưng chỉ mới xác nhận
  chúng *hiện ra và còn sống*. Chưa ai bấm nút, kéo timeline, hay xuất bản từ
  bản đóng gói. Phần vẽ bằng `QPainter` (timeline, dải phim) và
  `QMediaPlayer` đặc biệt cần mắt người xem — plugin `multimedia` có mặt
  không bảo đảm video phát được.
- **Chưa chạy trọn pipeline từ bundle.** `doctor` xanh không có nghĩa là
  `run` trên một phim thật sẽ ra đúng. Theo quy tắc trong `CLAUDE.md`, phải
  chạy thật rồi đối chiếu `ffprobe` **và trích khung hình ra xem**.
- **Chưa thử trên máy sạch.** Mọi lần chạy đều trên máy phát triển, nơi đã có
  sẵn ffmpeg, driver NVIDIA và cache model ở `D:\hf\hub`. Máy sạch có thể lộ
  ra DLL thiếu hoàn toàn khác (đặc biệt là Visual C++ Redistributable).
- **Chưa thử build trong môi trường ảo sạch**, xem mục "Rác lọt vào bundle".
- **Chưa thử `--onefile`.** Spec dùng onedir có chủ đích: onefile giải nén
  hàng trăm MB ra thư mục tạm mỗi lần chạy, khởi động chậm, và làm chỗ dò DLL
  CUDA phức tạp thêm. Nếu vẫn muốn onefile thì phải kiểm lại toàn bộ mục 3.
- **Chưa ký số.** Exe không ký sẽ bị SmartScreen chặn, và người dùng phổ
  thông sẽ bỏ cuộc ngay ở đó. Đây có thể là rào cản lớn hơn cả việc cài
  ffmpeg. Cần chứng chỉ ký code trả phí.
