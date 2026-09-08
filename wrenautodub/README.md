# WrenAutoDub

Nhận dạng tiếng Nhật → dịch tiếng Việt → thuyết minh → ghép lại vào video.
Tối ưu cho GPU 4GB (GTX 1650 Ti). Model tự tải, không phải chuẩn bị gì trước.

Ra `phim.vi.mp4`: track thuyết minh tiếng Việt + track tiếng gốc + phụ đề Việt nhúng sẵn.

## Giao diện

Bấm đúp `WrenAutoDub.bat`, hoặc:

```bash
python wren.py gui
```

Kéo thả file phim vào cửa sổ là chạy được. Cửa sổ có sẵn: chọn model và giọng
đọc, hai thanh chỉnh âm lượng, thanh tiến độ theo từng bước, log chạy trực tiếp,
nút Dừng, nút mở thư mục kết quả và nút mở `vi.srt` để sửa phụ đề.

Nút **Model…** mở bảng quản lý model — xem cái nào đã tải và chiếm bao nhiêu,
tải thêm hoặc xoá bớt. Nút **Doctor** chạy kiểm tra môi trường.

Mọi lựa chọn được nhớ lại cho lần mở sau. GUI chạy pipeline bằng tiến trình
riêng, nên cửa sổ không bị treo và nút Dừng dừng được thật.

## Dòng lệnh

```bash
python wren.py run "phim.mp4"
```

## Lệnh

| Lệnh | Việc |
|---|---|
| `run` | chạy cả 4 bước |
| `asr` | chỉ nhận dạng tiếng Nhật → `ja.srt` |
| `translate` | chỉ dịch → `vi.srt` |
| `tts` | chỉ đọc `vi.srt` → `dub.wav` |
| `mux` | chỉ trộn và ghép vào video |
| `models` | xem / tải / xoá model |
| `voices` | liệt kê giọng đọc |
| `gui` | mở giao diện đồ hoạ |
| `doctor` | kiểm tra môi trường |

Chạy `doctor` trước khi động vào phim dài — mọi thứ hay hỏng (DLL CUDA, ffmpeg
thiếu filter, mất mạng ở bước dịch) sẽ lộ ra trong 30 giây thay vì nổ giữa chừng:

```bash
python wren.py doctor
```

## Model tự tải

Không cần tải tay. Lần đầu chạy, model thiếu sẽ được tải về cache HuggingFace
(theo `HF_HOME` nếu bạn đã đặt). Trước khi tải có kiểm tra dung lượng đĩa, và
rớt mạng thì thử lại 3 lần — phần đã tải được giữ nguyên.

```bash
python wren.py models                    # xem cái nào đã có, chiếm bao nhiêu
python wren.py models --get large-v3     # tải trước cho yên tâm
python wren.py models --get vieneu       # model giọng đọc
python wren.py models --rm medium        # xoá cho nhẹ đĩa
```

## Giọng đọc

Hai engine, đổi bằng `--tts`:

**`vieneu`** (mặc định) — VieNeu-TTS v3 Turbo, chạy ONNX trên CPU nên **không tranh
VRAM với Whisper** và **không cần mạng**. 23 giọng preset, có giọng kể chuyện hợp
thuyết minh phim. Đo thật: ~0.91 giây/câu (2x realtime).

```bash
python wren.py voices                          # xem 23 giọng
python wren.py run "phim.mp4" --voice "Ngọc Linh"
```

**`edge`** — Microsoft edge-tts, cần mạng, nhẹ hơn, 2 giọng Việt (`nam` / `nu`).

```bash
python wren.py run "phim.mp4" --tts edge --voice nu --rate +12%
```

## Model nhận dạng

`--model`: `tiny` `base` `small` `medium` `large-v3` (mặc định) `large-v3-turbo`.

Đo thật trên GTX 1650 Ti 4GB, `int8_float16`, `beam_size=5`:

| Model | Đỉnh VRAM | Tốc độ |
|---|---|---|
| `medium` | 1215 MiB / 4096 | 5.8x realtime |
| `large-v3` | 2281 MiB / 4096 | 3.7x realtime |

`large-v3` vừa thoải mái nên để mặc định. Lưu ý tốc độ đo trên clip ngắn tiếng
sạch — audio phim nhiều tạp âm kích hoạt temperature fallback nhiều hơn nên sẽ
chậm hơn đáng kể.

## Có thể dừng giữa chừng

Mọi bước ghi kết quả ra `phim_work/` và **bỏ qua nếu đã có**. Ctrl+C rồi chạy lại
sẽ đi tiếp chứ không làm lại từ đầu. Bước TTS cache theo từng câu trong
`phim_work/pieces/`, nên phim 2 tiếng đứt giữa chừng vẫn chạy tiếp được.

Dùng `-f` để ép làm lại. Bản dịch còn cache riêng trong `vi.cache.json` — xoá
`vi.srt` rồi dịch lại không tốn request Google nào.

Cách dùng hay gặp nhất là sửa tay `vi.srt` rồi chạy lại từ bước đọc:

```bash
python wren.py tts "phim.mp4" -f
python wren.py mux "phim.mp4" -f
```

## Chỉnh âm lượng

```bash
# Tiếng gốc to hơn / giọng đọc nhỏ lại
python wren.py run "phim.mp4" --orig-vol 0.5 --dub-vol 1.4

# Hạ tiếng gốc cố định thay vì tự động né giọng đọc
python wren.py run "phim.mp4" --duck flat

# Câu ngắn hơn, thuyết minh bám hình sát hơn
python wren.py run "phim.mp4" --max-cue-dur 6 --max-cue-chars 45
```

## Vài chỗ đã xử lý sẵn

- **DLL CUDA** — `cudafix.py` tự nạp `cublas64_12.dll` / `cudnn64_9.dll` từ package
  pip `nvidia-*`. Thiếu bước này, model load xong vẫn chết giữa chừng vì Windows
  không tự tìm ra chúng.
- **Fallback thiết bị** — thử `cuda/int8_float16` → `cuda/int8` → `cuda/float16` →
  `cpu/int8`, kèm smoke-test 1 giây để lỗi lộ ra ngay lúc load thay vì sau 20 phút.
- **Cắt câu** — Whisper + VAD hay trả về khối 15–30 giây; bước ASR cắt lại theo mốc
  thời gian từng từ, ưu tiên dấu câu tiếng Nhật (`。！？`). Không có bước này thì
  cả đoạn dài thành một câu và thuyết minh không thể khớp hình.
- **Không lải nhải** — bật temperature fallback + `compression_ratio_threshold`,
  tắt `condition_on_previous_text`. Quan trọng với audio nhiều tạp âm.
- **Ép timing** — câu tiếng Việt thường dài hơn tiếng Nhật; `rubberband` tăng tốc
  (tối đa `--max-tempo`, mặc định 1.7x) mà không đổi cao độ giọng.
- **Cắt lặng đầu** — edge-tts chèn sẵn ~0.2s im lặng. Cắt đi thì giọng bám mốc phụ
  đề trong khoảng 0.03s, và đỡ phải tăng tốc câu.
- **Endpoint edge-tts chập chờn** — rớt ngẫu nhiên vài % không theo quy luật nội
  dung. Có 2 lượt vét lại tuần tự.
- **Dịch lệch dòng** — Google đôi khi gộp/nuốt dòng khi dịch cả lô; phát hiện lệch
  thì tự lùi về dịch từng câu cho lô đó.

## Yêu cầu

`faster-whisper` `ctranslate2` `deep-translator` `soundfile` `numpy`
`huggingface-hub` `nvidia-cublas-cu12` `nvidia-cudnn-cu12`, thêm `vieneu` hoặc
`edge-tts` tuỳ engine, `PyQt6` nếu dùng giao diện, và `ffmpeg`/`ffprobe`
trong PATH (bản ffmpeg phải có
`rubberband` — bản gyan.dev essentials có sẵn).

Bước dịch luôn cần mạng. Bước đọc chỉ cần mạng nếu dùng `--tts edge`.

Chạy `python wren.py doctor` để tự kiểm tra hết.
