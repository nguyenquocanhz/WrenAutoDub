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
- **File tải từ HLS hay thiếu segment.** Mốc thời gian của gói tin vẫn liền
  mạch nhưng bên trong hụt cả phút âm thanh. ffmpeg dồn hai mép lỗ lại, thoát
  mã 0, không cảnh báo gì — mọi mốc thoại sau lỗ bị đẩy sớm đúng bằng độ dài
  lỗ. **Mọi chỗ decode `[0:a]` phải có `aresample=async=1`** (`asr.py`,
  `mux.py`). Đã dính thật: phim 15:21 ra track thuyết minh 12:03.
- **`sidechaincompress` kết thúc theo nhánh NGẮN hơn.** Nhánh điều khiển phải
  `apad`, không thì thuyết minh ngắn hơn phim sẽ cắt cụt cả bản trộn.
- **Không có `dub.wav` thì tiếng gốc vẫn phải cắt theo hình.** Map thẳng
  `0:a:0` là hình cắt còn tiếng nguyên bản, lệch ngay từ nhát cắt đầu tiên.
- **Chỉ số input của ảnh logo phụ thuộc có `dub.wav` hay không** (2 nếu có, 1
  nếu không). Đóng cứng bằng 2 là ffmpeg báo `Invalid file index 2`.
- **Gán `self.x = ...` cho list dùng chung là cắt đứt tham chiếu.** `timeline`
  và `Project` chia nhau cùng một list; phải sửa tại chỗ `self.x[:] = ...`,
  không thì màn hình một đằng, lúc xuất một nẻo.
- **Undo phải trả về ĐỦ mọi trường.** Thiếu `clips`/`dub_clips`/`ripple` thì
  undo cho ra trạng thái lai, rồi `save_project` ghi nguyên cái lai đó xuống đĩa.
- **Mã ngôn ngữ của Whisper khác Google Translate**: `zh`→`zh-CN`, `he`→`iw`,
  `jv`→`jw`. Dùng `translate.map_lang`.
- **Heredoc bash nuot ky tu escape.** Da dinh 4 lan trong mot phien:
  backslash-n bien thanh xuong dong that, backslash-s va backslash-d
  trong regex mat backslash. Viet script va khong dung escape nao, hoac
  dung cong cu ghi file.
- **QMediaPlayer khong giai ma khung nao truoc khi that su phat.** Chi
  setSource roi doi thi khung xem truoc dung o "Dang lay khung hinh..."
  vinh vien, ke ca sau khi goi seek(0). Phai nha play/pause mot cai.
- **Keo dau doc luc dang phat phai GOP lenh tua.** Chuot sinh ~60 su kien moi
  giay, tua du 60 lan thi bo giai ma nghen: do duoc 2.3 FPS va co lan dung
  hinh 5.2 giay. Gop con toi da 1 lan / 90ms.
- **Dung phat trong luc keo lam TE HON** (6.7 -> 2.8 FPS): dung roi thi khung
  hinh chi con den tu lenh tua. Da thu va da bo.
- **File h264 thieu khung tham chieu lam moi lan tua deu dat.** Cung do phan
  giai, cung thao tac: phim lanh keo duoc 20.8 FPS (te nhat 202ms), phim tai
  hut segment chi 2.8-6.7 FPS va co cu dung 4.2 giay. Do la file, khong phai app.
- **PyQt6 giet process ngay khi exception lot ra khoi slot Qt**, khong in gi.
  Cua so chi bien mat. Dung `crashlog.install()` de con dau vet ma doc.
- **Thời lượng đúng KHÔNG chứng minh nội dung đúng.** Bản cắt từng ra đủ
  14.000s mà tiếng vẫn phát đoạn đã bị cắt khỏi hình. Kiểm bằng nội dung: màu
  khung hình, tần số sóng âm, `volumedetect` — đừng bao giờ chỉ so `ffprobe`.

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
