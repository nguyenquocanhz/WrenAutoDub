<!--
Cảm ơn bạn đã gửi PR. Xoá phần nào không liên quan, đừng để trống nguyên mẫu.
Thanks for the PR. Delete sections that do not apply — do not leave the
template untouched.
-->

## Thay đổi gì / What changed

<!--
Một hai câu. Nếu có issue liên quan thì ghi "Đóng #123" / "Closes #123".
One or two sentences. Link the issue with "Closes #123" if there is one.
-->

## Vì sao / Why

<!--
Vấn đề thật đang được giải quyết, không phải mô tả lại đoạn code.
The actual problem being solved, not a restatement of the diff.
-->

---

## Đã kiểm chứng thế nào / How this was verified

**Bắt buộc.** CI chỉ kiểm cú pháp và test logic thuần — nó không chạy được
ffmpeg, không có GPU, không có model. Mọi thứ dính tới video phải được kiểm
trên máy thật và ghi lại ở đây.

**Required.** CI only checks syntax and pure-logic tests — it cannot run
ffmpeg, has no GPU and no models. Anything touching video must be verified on
a real machine and written down here.

<!--
Dán lệnh đã chạy và kết quả thật. Ví dụ:

    python wren.py run "test.mkv" --tts edge
    ffprobe -v error -show_entries format=duration -of csv=p=0 test.vi.mp4
    -> 143.360000  (gốc 143.362000, lệch 0.002s)
-->

```
```

### Nếu có động vào chuỗi filter ffmpeg / If the ffmpeg filter chain changed

Quy tắc bắt buộc của dự án — xem `CLAUDE.md`. Quy tắc này đã bắt được ba bug
thật. Không được kết luận "chắc đúng".

Mandatory project rule — see `CLAUDE.md`. It has caught three real bugs.
"It should be fine" is not acceptable.

- [ ] Đã chạy thật, không chỉ đọc code. / Actually ran it, did not just read the code.
- [ ] Đã đối chiếu thời lượng đầu ra với `ffprobe`. / Compared output duration with `ffprobe`.
- [ ] **Đã trích khung hình ra xem, không chỉ tin vào thời lượng.** Đã có lần cả ba lần chạy đều báo lệch 0.000s trong khi phụ đề sai hoàn toàn. / **Extracted frames and looked at them, not just trusted the duration.** There was a case where all three runs reported 0.000s drift while the subtitles were entirely wrong.
- [ ] Nhãn filter không trùng: chuỗi video dùng `[v0] [v1]...`, chuỗi tiếng dùng tiền tố khác (`[vc1]`, `[cao*]`, `[cad*]`). Trùng nhãn chỉ lộ ra khi có từ hai hiệu ứng trở lên. / No duplicate filter labels: video uses `[v0] [v1]...`, audio uses a different prefix. Duplicates only surface with two or more effects.
- [ ] Đã thử với **từ hai hiệu ứng trở lên** cùng lúc. / Tested with **two or more effects** at once.
- [ ] Cắt được áp **trước** khi trộn tiếng. / Cuts applied **before** audio mixing.
- [ ] Phụ đề đi qua `remap_cues_clips`, không phải `remap_cues`. / Subtitles go through `remap_cues_clips`, not `remap_cues`.

### Đã thử trên / Tested on

<!-- Bỏ trống dòng nào không thử. Nói thẳng là chưa thử tốt hơn là để mập mờ. -->
<!-- Leave blank what you did not test. Saying "not tested" beats being vague. -->

- Card đồ hoạ / GPU:
- ffmpeg:
- Định dạng file đã thử / File formats tested:
- Windows + Python:

---

## Kiến trúc / Architecture

- [ ] Tầng logic (`asr` `translate` `tts` `mux` `handoff` `edit` `clips` `timing` `export` `hwaccel` `models` `cudafix` `srtutil`) **không import `PyQt6.QtWidgets`**. CI kiểm việc này. / The logic layer does **not** import `PyQt6.QtWidgets`. CI enforces this.
- [ ] **Cả hai giao diện còn chạy** — bản Widgets (`wren.py gui`, `wren.py edit`) và bản QML. Sửa logic là đụng cả hai. / **Both GUIs still run** — Widgets and QML. Logic changes affect both.
- [ ] Không thêm dependency mới. Nếu có thì đã mở issue hỏi trước, và đã cập nhật `requirements.txt`. / No new dependency. If there is one, it was raised in an issue first and `requirements.txt` was updated.
- [ ] Comment, docstring và chuỗi hiện ra cho người dùng viết bằng tiếng Việt. Comment giải thích **tại sao**, không phải cái gì. / Comments, docstrings and user-facing strings are in Vietnamese, explaining **why** rather than what.

## Giấy phép / Licensing

- [ ] Tôi đồng ý đóng góp phần code này theo **AGPL-3.0**, giống phần còn lại của dự án. / I agree to contribute this code under **AGPL-3.0**, same as the rest of the project.

## Còn thiếu gì / Known gaps

<!--
Chỗ nào chưa thử, trường hợp nào biết là chưa xử lý. Ghi thẳng ra — người
review đọc phần này kỹ nhất.

What is untested, which cases you know are unhandled. Be blunt — reviewers
read this section most carefully.
-->
