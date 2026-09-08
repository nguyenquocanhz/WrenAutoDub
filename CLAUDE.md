# WrenAutoDub — quy ước dự án

App desktop Windows: nhận dạng tiếng Nhật → dịch tiếng Việt → thuyết minh bằng
VieNeu-TTS → dựng phim → xuất bản. Chạy hoàn toàn local. Không có server, không
có app di động, không có API mạng nào ngoài Google Translate và edge-tts.

Chạy: `python wren.py <lệnh> "phim.mkv"` — xem `wren.py --help`.

## Kiến trúc: logic tách khỏi giao diện

Tầng logic **không được import Qt Widgets**. Đây là lý do chuyển giao diện sang
QML chỉ tốn vài file thay vì viết lại cả app.

| Tầng | File |
|---|---|
| Pipeline | `asr.py` `translate.py` `tts.py` `mux.py` `handoff.py` |
| Mô hình dựng | `edit.py` `clips.py` `timing.py` `export.py` |
| Hạ tầng | `hwaccel.py` `models.py` `cudafix.py` `srtutil.py` `media_strip.py` |
| Giao diện Widgets | `gui.py` `editor.py` `editor_main.py` `timeline.py` `icons.py` |
| Giao diện QML | `qml_app.py` `qml_models.py` `preview_qml.py` `timeline_qml.py` `qml/*.qml` |

Hai giao diện chạy song song, dùng chung tầng logic. Sửa logic phải đảm bảo cả
hai còn chạy.

## Quy tắc bắt buộc

**Mọi thay đổi tới chuỗi filter ffmpeg phải chạy thật rồi đối chiếu thời lượng
với `ffprobe`.** Không được kết luận "chắc đúng". Quy tắc này đã bắt được ba bug
thật trong dự án.

**Nhãn filter không được trùng.** Chuỗi video dùng dãy `[v0] [v1]...`, chuỗi
tiếng phải dùng tiền tố khác (`[vc1]`, `[cao*]`, `[cad*]`). Trùng nhãn thì ffmpeg
từ chối chạy, và chỉ lộ ra khi có từ hai hiệu ứng trở lên.

**Cắt phải áp trước khi trộn tiếng.** Cắt sau khi trộn thì track thuyết minh có
nhát cắt riêng sẽ bị áp cắt hai lần.

**Phụ đề phải ánh xạ qua `remap_cues_clips`,** không phải `remap_cues`. Bản sau
chỉ biết đổi tốc độ, không biết nhát cắt — dùng nhầm thì câu nằm trong đoạn đã
cắt vẫn còn và mốc sai hết.

**Kiểm bằng nội dung, không chỉ bằng thời lượng.** Có lần cả ba lần chạy đều báo
"lệch 0.000s" trong khi phụ đề sai hoàn toàn. Trích khung hình ra xem.

## Bẫy đã gặp

- **Đường dẫn Windows trong filter `subtitles`** phải escape hai lớp: `\` → `/`,
  rồi `:` → `\:`. Dùng `mux.escape_sub_path`.
- **Đọc output tiến trình con**: Windows kết dòng bằng CRLF. Phải `rstrip("\r")`
  trước khi tách theo `\r` (dùng để bắt dòng tiến độ ghi đè), không thì mọi dòng
  thành chuỗi rỗng.
- **`QPainter` giữ brush giữa các lần vẽ.** Đặt `NoBrush` trước khi vẽ khung
  viền, không thì nó tô đè kín lớp bên dưới.
- **`str.replace` không giới hạn số lần** khi patch code: chuỗi neo có thể xuất
  hiện ở nhiều hàm. Luôn truyền `count=1` hoặc thay theo số dòng.
- **Heredoc bash lớn (>150 dòng) hay đứt giữa chừng.** Dùng công cụ ghi file cho
  nội dung dài.
- **`atempo` chỉ nhận 0.5–100.** Chậm hơn phải nối chuỗi — dùng
  `timing.atempo_chain`.
- **DLL CUDA**: Windows không tự tìm `cublas64_12.dll` trong package pip
  `nvidia-*`. Phải gọi `cudafix.enable_cuda_dlls()` TRƯỚC khi import ctranslate2.

## Phần cứng đã đo

GTX 1650 Ti 4GB, `int8_float16`, `beam_size=5`:

| Model | Đỉnh VRAM | Tốc độ |
|---|---|---|
| medium | 1215 MiB | 5.8x realtime |
| large-v3 | 2281 MiB | 3.7x realtime |

`h264_nvenc` và `hevc_nvenc` chạy được. `av1_nvenc` KHÔNG (TU117 không có).
ffmpeg trên máy này **không build OpenCL và Vulkan** — dùng CUDA/NVENC.

## Văn phong code

Tiếng Việt cho comment, docstring và mọi chuỗi hiện ra cho người dùng. Comment
giải thích **tại sao**, không phải cái gì. Ưu tiên câu ngắn, không hoa mỹ.

Không thêm dependency mới nếu chưa hỏi. Không sửa file ngoài phạm vi được giao —
nhiều agent chạy song song, đè file của nhau là hỏng việc.
