# -*- coding: utf-8 -*-
"""Test cho wrenautodub/handoff.py — gom file bàn giao cho CapCut.

Không gọi ffprobe thật: `_probe` được thay bằng bản giả để test chạy nhanh và
không phụ thuộc máy có cài ffmpeg hay không.
"""

from __future__ import annotations

import pytest

from wrenautodub import handoff
from wrenautodub.srtutil import Cue, write_srt

# Giữ bản thật trước khi fixture bên dưới thay bằng bản giả
PROBE_THAT = handoff._probe

PROBE_GIA = {
    "format": {"duration": "125.5", "size": str(21 * 2 ** 20)},
    "streams": [{"codec_type": "audio", "sample_rate": "48000", "channels": 2}],
}


@pytest.fixture(autouse=True)
def khong_gọi_ffprobe(monkeypatch):
    """Chặn mọi lần gọi ffprobe — test tầng logic không được phụ thuộc ffmpeg."""
    monkeypatch.setattr(handoff, "_probe", lambda path: dict(PROBE_GIA))


@pytest.fixture
def bo_file(tmp_path):
    """Dựng sẵn phim gốc và thư mục làm việc rỗng."""
    video = tmp_path / "phim.mkv"
    video.write_bytes(b"gia lap phim")
    work = tmp_path / "work"
    work.mkdir()
    return video, work, tmp_path / "ban_giao"


def them_srt(work, so_cau=2):
    write_srt(work / "vi.srt",
              [Cue(i * 10.0, i * 10.0 + 2.0, f"Câu {i}") for i in range(1, so_cau + 1)])


def them_dub(work):
    (work / "dub.wav").write_bytes(b"RIFF" + b"\0" * 1000)


def doc_readme(out):
    return (out / "DOC-TRUOC-KHI-DUNG.txt").read_text(encoding="utf-8")


# =========================================================== khi thiếu file


def test_thiếu_cả_hai_file_thì_báo_đủ_hai_cảnh_báo(bo_file):
    video, work, out_dir = bo_file
    out, warn = handoff.build(video, work, out_dir)
    assert len(warn) == 2, f"thiếu cả phụ đề lẫn giọng đọc phải báo 2 việc: {warn}"
    assert any("vi.srt" in w for w in warn), "phải nói rõ thiếu file phụ đề nào"
    assert any("dub.wav" in w for w in warn), "phải nói rõ thiếu file giọng đọc nào"


def test_cảnh_báo_kèm_lệnh_cần_chạy(bo_file):
    video, work, out_dir = bo_file
    _out, warn = handoff.build(video, work, out_dir)
    assert any("wren.py translate" in w for w in warn), \
        "thiếu phụ đề thì phải chỉ luôn lệnh dịch"
    assert any("wren.py tts" in w for w in warn), \
        "thiếu giọng đọc thì phải chỉ luôn lệnh đọc"


def test_thiếu_file_vẫn_tạo_thư_mục_và_README(bo_file):
    video, work, out_dir = bo_file
    out, _warn = handoff.build(video, work, out_dir)
    assert out.is_dir(), "thư mục bàn giao phải được tạo dù còn thiếu file"
    assert (out / "DOC-TRUOC-KHI-DUNG.txt").exists(), \
        "luôn phải có file hướng dẫn để người dùng biết còn thiếu gì"
    assert "(chưa có)" in doc_readme(out), "README phải ghi rõ file nào chưa có"


def test_chỉ_thiếu_giọng_đọc(bo_file):
    video, work, out_dir = bo_file
    them_srt(work)
    out, warn = handoff.build(video, work, out_dir)
    assert len(warn) == 1 and "dub.wav" in warn[0], "chỉ còn thiếu đúng giọng đọc"
    assert (out / "phim.vi.srt").exists(), "phụ đề đã có thì vẫn phải chép sang"


def test_chỉ_thiếu_phụ_đề(bo_file):
    video, work, out_dir = bo_file
    them_dub(work)
    out, warn = handoff.build(video, work, out_dir)
    assert len(warn) == 1 and "vi.srt" in warn[0], "chỉ còn thiếu đúng phụ đề"
    assert (out / "phim.thuyetminh.wav").exists(), "giọng đọc đã có thì vẫn phải chép sang"


def test_thiếu_phim_gốc_thì_báo(bo_file):
    _video, work, out_dir = bo_file
    them_srt(work)
    them_dub(work)
    _out, warn = handoff.build(work.parent / "khong_co_phim.mkv", work, out_dir)
    assert any("không thấy phim gốc" in w for w in warn), \
        "phim gốc biến mất thì phải cảnh báo, không thì người dùng dựng nhầm bản"


def test_không_gọi_ffprobe_khi_thiếu_file_giọng_đọc(bo_file, monkeypatch):
    video, work, out_dir = bo_file

    def no(_path):
        raise AssertionError("không được gọi ffprobe khi file giọng đọc chưa có")

    monkeypatch.setattr(handoff, "_probe", no)
    handoff.build(video, work, out_dir)      # nổ ở đây nghĩa là gọi ffprobe thừa


# ============================================================ khi đủ file


def test_đủ_file_thì_không_còn_cảnh_báo(bo_file):
    video, work, out_dir = bo_file
    them_srt(work)
    them_dub(work)
    out, warn = handoff.build(video, work, out_dir)
    assert warn == [], f"đủ file thì không được còn cảnh báo nào: {warn}"
    assert sorted(f.name for f in out.iterdir()) == \
        ["DOC-TRUOC-KHI-DUNG.txt", "phim.thuyetminh.wav", "phim.vi.srt"], \
        "thư mục bàn giao phải có đúng ba file: hướng dẫn, giọng đọc, phụ đề"


def test_tên_file_ra_theo_tên_phim(bo_file):
    video, work, out_dir = bo_file
    them_srt(work)
    them_dub(work)
    out, _warn = handoff.build(video, work, out_dir)
    assert (out / "phim.vi.srt").exists(), "phụ đề phải mang tên phim cho dễ nhận"
    assert (out / "phim.thuyetminh.wav").exists(), "giọng đọc cũng vậy"


def test_nội_dung_phụ_đề_được_chép_nguyên_vẹn(bo_file):
    video, work, out_dir = bo_file
    them_srt(work, so_cau=3)
    out, _warn = handoff.build(video, work, out_dir)
    from wrenautodub.srtutil import read_srt
    assert len(read_srt(out / "phim.vi.srt")) == 3, \
        "chép sang phải giữ đủ số câu, không được đụng vào nội dung"


def test_README_ghi_số_câu_và_mốc_cuối(bo_file):
    video, work, out_dir = bo_file
    them_srt(work, so_cau=3)
    them_dub(work)
    out, _warn = handoff.build(video, work, out_dir)
    txt = doc_readme(out)
    assert "3 câu" in txt, "README phải nói có bao nhiêu câu để người dùng đối chiếu"
    assert "0m32s" in txt, "phải ghi mốc kết thúc của câu cuối (32 giây)"


def test_README_ghi_thông_số_giọng_đọc(bo_file):
    video, work, out_dir = bo_file
    them_dub(work)
    out, _warn = handoff.build(video, work, out_dir)
    txt = doc_readme(out)
    assert "2m05s" in txt, "phải ghi thời lượng giọng đọc lấy từ ffprobe"
    assert "48000 Hz" in txt and "2 kênh" in txt, "phải ghi tần số và số kênh"
    assert "21 MB" in txt, "phải ghi dung lượng"


def test_README_ffprobe_hỏng_thì_vẫn_ghi_được(bo_file, monkeypatch):
    """Máy chưa cài ffmpeg thì `_probe` trả dict rỗng — không được nổ."""
    video, work, out_dir = bo_file
    them_srt(work)
    them_dub(work)
    monkeypatch.setattr(handoff, "_probe", lambda p: {})
    out, warn = handoff.build(video, work, out_dir)
    assert "? Hz" in doc_readme(out), "không đọc được thông số thì ghi dấu hỏi"
    assert warn == [], "ffprobe hỏng không phải là thiếu file, đừng cảnh báo nhầm"


def test_README_nhắc_đường_dẫn_phim_gốc_và_lệnh_chạy_lại(bo_file):
    video, work, out_dir = bo_file
    out, _warn = handoff.build(video, work, out_dir)
    txt = doc_readme(out)
    assert str(video) in txt, "README phải ghi đường dẫn phim gốc"
    assert 'python wren.py run "phim.mkv"' in txt, "phải chỉ lệnh chạy lại pipeline"


# ============================================================ chép phim gốc


def test_mặc_định_không_chép_phim_gốc(bo_file):
    video, work, out_dir = bo_file
    out, _warn = handoff.build(video, work, out_dir)
    assert not (out / "phim.mkv").exists(), \
        "phim hai tiếng mà chép lại thì rất phí, mặc định chỉ ghi đường dẫn"


def test_copy_video_thì_chép_kèm_phim(bo_file):
    video, work, out_dir = bo_file
    out, _warn = handoff.build(video, work, out_dir, copy_video=True)
    assert (out / "phim.mkv").exists(), "bật copy_video thì phải có phim trong thư mục"
    assert "đã được chép vào thư mục này" in doc_readme(out), \
        "README phải nói phim đã nằm sẵn trong thư mục"


def test_copy_video_khi_phim_không_tồn_tại_thì_chỉ_cảnh_báo(bo_file):
    _video, work, out_dir = bo_file
    _out, warn = handoff.build(work.parent / "khong_co.mkv", work, out_dir,
                               copy_video=True)
    assert any("không thấy phim gốc" in w for w in warn), \
        "không có phim để chép thì cảnh báo chứ không được nổ"


# ==================================================== thư mục mặc định


def test_thư_mục_ra_mặc_định_cạnh_phim(bo_file):
    video, work, _out_dir = bo_file
    out, _warn = handoff.build(video, work)
    assert out.name == "phim_capcut", "mặc định là <tên phim>_capcut"
    assert out.parent == video.parent, "và nằm ngay cạnh phim gốc"


def test_thư_mục_làm_việc_mặc_định(bo_file):
    video, _work, out_dir = bo_file
    _out, warn = handoff.build(video, None, out_dir)
    assert all("phim_work" in w for w in warn), \
        "không truyền workdir thì tìm ở <tên phim>_work"


def test_tạo_được_thư_mục_ra_nhiều_cấp(tmp_path):
    video = tmp_path / "phim.mkv"
    video.write_bytes(b"x")
    out, _warn = handoff.build(video, tmp_path / "work", tmp_path / "a" / "b" / "c")
    assert out.is_dir(), "thư mục ra nhiều cấp phải được tạo hết"


def test_chạy_lại_lần_hai_thì_ghi_đè_không_nổ(bo_file):
    video, work, out_dir = bo_file
    them_srt(work, so_cau=2)
    them_dub(work)
    handoff.build(video, work, out_dir)
    them_srt(work, so_cau=5)
    out, warn = handoff.build(video, work, out_dir)
    assert warn == [], "chạy lại trên thư mục cũ vẫn phải sạch cảnh báo"
    assert "5 câu" in doc_readme(out), "README phải được cập nhật theo bản mới"


# ================================================================= _probe


def test_probe_không_có_ffprobe_thì_trả_dict_rỗng(monkeypatch, tmp_path):
    """Máy chưa cài ffmpeg vẫn phải bàn giao được, chỉ là thiếu thông số."""
    def no(*_a, **_k):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(handoff.subprocess, "run", no)
    assert PROBE_THAT(tmp_path / "x.wav") == {}, "ffprobe vắng mặt thì trả dict rỗng"


def test_probe_ffprobe_trả_rác_thì_trả_dict_rỗng(monkeypatch, tmp_path):
    class KetQua:
        stdout = "không phải json"

    monkeypatch.setattr(handoff.subprocess, "run", lambda *a, **k: KetQua())
    assert PROBE_THAT(tmp_path / "x.wav") == {}, "output hỏng thì nuốt lỗi, trả rỗng"


def test_probe_đọc_được_json(monkeypatch, tmp_path):
    class KetQua:
        stdout = '{"format": {"duration": "12.5"}}'

    monkeypatch.setattr(handoff.subprocess, "run", lambda *a, **k: KetQua())
    assert PROBE_THAT(tmp_path / "x.wav") == {"format": {"duration": "12.5"}}, \
        "output hợp lệ thì phải trả về đúng dữ liệu ffprobe"


# ==================================================================== run


def test_run_còn_thiếu_file_thì_trả_mã_lỗi_1(bo_file, capsys):
    video, work, out_dir = bo_file
    ma = handoff.run(video, work, out_dir)
    assert ma == 1, "còn thiếu file thì trả mã khác 0 để script gọi biết mà dừng"
    assert "[!]" in capsys.readouterr().out, "phải in cảnh báo ra màn hình"


def test_run_đủ_file_thì_trả_mã_0(bo_file, capsys):
    video, work, out_dir = bo_file
    them_srt(work)
    them_dub(work)
    ma = handoff.run(video, work, out_dir)
    ra = capsys.readouterr().out
    assert ma == 0, "đủ file thì trả mã 0"
    assert "[!]" not in ra, "không còn gì thiếu thì đừng in cảnh báo"
    assert "phim.vi.srt" in ra and "phim.thuyetminh.wav" in ra, \
        "phải liệt kê các file đã tạo kèm dung lượng"
    assert "CapCut" in ra, "phải nhắc người dùng bước tiếp theo"


# =============================================================== _fmt_dur


@pytest.mark.parametrize("giay,chu", [
    (0, "0m00s"), (5, "0m05s"), (65, "1m05s"), (599, "9m59s"),
    (3600, "1h00m00s"), (3725, "1h02m05s"), (7325.9, "2h02m05s"),
], ids=["0", "5s", "65s", "599s", "1gio", "1gio2phut", "2gio"])
def test_fmt_dur(giay, chu):
    assert handoff._fmt_dur(giay) == chu, f"{giay} giây phải hiện là {chu}"
