# RapidOCR-vi — bộ huấn luyện model đọc chữ tiếng Việt

## Vì sao cần

`wrenautodub/ocr.py` đọc phụ đề nung sẵn trên hình. Model đi kèm RapidOCR đọc
tiếng Trung rất tốt, nhưng **không đọc được tiếng Việt có dấu**:

| | Chữ thật trên màn hình | Model Latin đọc ra |
|---|---|---|
| | `Hôm nay vốn dĩ tôi định bắt quả tang,` | `Hom nay von di toi dinh bat qua tang.` |
| | `cách an toàn nhất của hắn,` | `cach an toan nhat cia han,` |
| | `Cô đuổi theo hướng Tây năm dặm,` | `Co duoi theo hurong Tay nam dam,` |

Nguyên nhân đo được: bảng ký tự của `latin_PP-OCRv3_rec` có **185 ký tự**,
trong đó chỉ **17/67** nguyên âm có dấu của tiếng Việt. Thiếu hẳn `ă ơ ư` và
toàn bộ dấu hỏi ngã nặng. Không phải chỉnh tham số được — model chưa từng có
lớp đầu ra cho những ký tự đó.

Làm được thì phim hardsub song ngữ sẽ lấy thẳng **bản dịch của người**, bỏ luôn
cả Whisper lẫn Google Translate.

## Ba file

| File | Việc |
|---|---|
| `bang_ky_tu.py` | sinh `chars_vi.txt` — 236 ký tự, 134 chữ có dấu |
| `sinh_du_lieu.py` | sinh ảnh chữ giống hệt phụ đề phim, kèm nhãn |
| `RapidOCR_vi_T4.ipynb` | notebook Colab T4: tinh chỉnh + xuất ONNX |

## Chạy

```bash
python bang_ky_tu.py

python sinh_du_lieu.py \
    --video "D:/phim/phim_co_hardsub.mp4" \
    --srt   "D:/phim/phim_work/vi.srt" \
    --so 200000 --ra data_vi

tar -czf data_vi.tar.gz data_vi chars_vi.txt
```

Đẩy `data_vi.tar.gz` lên Google Drive, mở notebook trên Colab T4, chạy từ trên
xuống. Cuối notebook tải về `rapidocr_vi.tar.gz`.

## Vì sao dữ liệu làm như vậy

Model này chỉ đọc **phụ đề phim**, nên dữ liệu phải giống hệt phụ đề phim.
Huấn luyện bằng chữ đen trên nền trắng rồi đem đọc phụ đề là lệch miền.

- **Chữ trắng viền đen, nằm giữa** — đúng kiểu phụ đề
- **Nền là khung hình phim thật**, lấy từ **nửa trên** khung. Lấy cả khung là
  phụ đề nung của chính bộ phim lọt vào nền, model học nhầm rằng nền hay có
  chữ mờ. Đã dính lỗi này và đã sửa.
- **73 font** có đủ 134 chữ có dấu. Font thiếu glyph vẽ ra ô vuông rỗng nên
  phải lọc bằng `fontTools`, không lấy bừa.
- **Trộn hai nguồn chữ**: 35% câu thoại thật từ `vi.srt` cho đúng văn phong,
  65% âm tiết ghép ngẫu nhiên theo cấu trúc âm tiết tiếng Việt. Chỉ dùng câu
  thật thì chữ hiếm như `ỡ ẵ ự` xuất hiện vài lần, model không học nổi.

## Vì sao tinh chỉnh chứ không train từ đầu

Checkpoint `latin_PP-OCRv3_rec` đã biết hình dáng chữ Latin. Ta chỉ dạy thêm
phần dấu. Tầng cuối đổi từ 185 lên 236 lớp nên được khởi tạo lại, phần trích
đặc trưng kế thừa nguyên. Nhanh hơn train từ đầu nhiều lần.

## Đã kiểm và CHƯA kiểm

**Đã chạy thật ở máy:**
- `bang_ky_tu.py` → 236 ký tự, đủ cả 134 chữ có dấu, có cả chữ hoa
- `sinh_du_lieu.py` → sinh 600 ảnh, đã xem tận mắt: chữ có dấu rõ, viền đen
  đúng kiểu, nền sạch không lẫn phụ đề gốc
- Lọc font → 73/301 font có đủ glyph
- Notebook parse được, YAML nhúng trong đó cũng hợp lệ

**CHƯA chạy, vì máy này không có T4:**
- Bản thân việc huấn luyện
- Cấu hình PaddleOCR có chạy trơn không
- Bước xuất ONNX
- Chất lượng model sau khi train

Nói thẳng: notebook là code chưa từng chạy. Lần chạy đầu nhiều khả năng vấp
vài lỗi phiên bản — PaddleOCR đổi API khá thường xuyên. Cứ chạy tới đâu vướng
thì báo, sửa nhanh.

## Ước lượng thời gian

Trên T4, batch 128, 200k ảnh: khoảng **25–40 phút một epoch**. Tinh chỉnh
thường cần 20–40 epoch, tức **10–25 tiếng**. Colab free ngắt sau ~4 tiếng nên
phải chạy tiếp nhiều lần — notebook đã đặt `save_epoch_step: 5` cho việc đó.
