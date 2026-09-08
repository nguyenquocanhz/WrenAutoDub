# -*- coding: utf-8 -*-
"""Test cho wrenautodub/srtutil.py — đọc/ghi SRT.

File SRT ngoài đời rất hay dị dạng: thiếu số thứ tự, dùng dấu chấm thay dấu
phẩy, có BOM, kết dòng CRLF. Đọc hỏng một câu là lệch cả bản dịch.
"""

from __future__ import annotations

import pytest

from _hotro import bo_ba
from wrenautodub.srtutil import Cue, fmt_ts, parse_ts, read_srt, write_srt


def ghi(tmp_path, ten: str, noi_dung: str, ma_hoa: str = "utf-8"):
    """Ghi nguyên văn, không để Python đụng vào ký tự xuống dòng."""
    p = tmp_path / ten
    p.write_text(noi_dung, encoding=ma_hoa, newline="")
    return p


# ================================================ parse_ts / fmt_ts vòng tròn


@pytest.mark.parametrize("chuoi,giay", [
    ("00:00:00,000", 0.0),
    ("00:00:01,000", 1.0),
    ("00:01:00,000", 60.0),
    ("01:00:00,000", 3600.0),
    ("01:02:03,456", 3723.456),
    ("99:59:59,999", 359999.999),
], ids=["0", "1s", "1phut", "1gio", "hon-hop", "rat-dai"])
def test_parse_ts_đọc_đúng_số_giây(chuoi, giay):
    assert parse_ts(chuoi) == pytest.approx(giay), f"{chuoi} phải ra {giay} giây"


@pytest.mark.parametrize("chuoi,giay", [
    ("00:00:01.500", 1.5),
    ("00:00:01,500", 1.5),
], ids=["dau-cham", "dau-phay"])
def test_parse_ts_chấp_nhận_cả_dấu_chấm_lẫn_dấu_phẩy(chuoi, giay):
    """Nhiều công cụ xuất SRT theo kiểu Mỹ (dấu chấm) — vẫn phải đọc được."""
    assert parse_ts(chuoi) == pytest.approx(giay), f"{chuoi} phải đọc được như {giay}s"


@pytest.mark.parametrize("chuoi,giay", [("00:00:01,5", 1.5), ("00:00:01,05", 0.05 + 1),
                                        ("00:00:01,123", 1.123)],
                         ids=["1-chu-so", "2-chu-so", "3-chu-so"])
def test_parse_ts_mili_giây_thiếu_chữ_số_được_bù_0_bên_phải(chuoi, giay):
    """',5' nghĩa là 500ms chứ không phải 5ms — bù 0 bên phải mới đúng."""
    assert parse_ts(chuoi) == pytest.approx(giay), f"{chuoi} phải ra {giay}s"


def test_parse_ts_giờ_một_chữ_số():
    assert parse_ts("1:02:03,004") == pytest.approx(3723.004), \
        "giờ ghi 1 chữ số vẫn phải đọc được"


@pytest.mark.parametrize("giay", [0.0, 0.001, 1.0, 59.999, 60.0, 3599.999, 3600.0,
                                  3723.456, 359999.999],
                         ids=["0", "1ms", "1s", "gan-1phut", "1phut", "gan-1gio",
                              "1gio", "hon-hop", "rat-dai"])
def test_parse_ts_và_fmt_ts_là_vòng_tròn_khép_kín(giay):
    assert parse_ts(fmt_ts(giay)) == pytest.approx(giay, abs=0.0005), \
        f"{giay}s ghi ra rồi đọc lại phải ra chính nó"


def test_fmt_ts_đúng_định_dạng_srt():
    assert fmt_ts(3723.456) == "01:02:03,456", \
        "SRT bắt buộc hh:mm:ss,mmm — hai chữ số giờ và dấu phẩy"


def test_fmt_ts_số_âm_bị_kẹp_về_0():
    assert fmt_ts(-5.0) == "00:00:00,000", \
        "mốc âm (do dời offset quá tay) phải kẹp về 0 chứ không ghi dấu trừ"


def test_fmt_ts_làm_tròn_mili_giây():
    assert fmt_ts(1.9996) == "00:00:02,000", "0.9996s phải làm tròn lên 1000ms"
    assert fmt_ts(0.0004) == "00:00:00,000", "dưới nửa mili giây thì về 0"


# ============================================================ read_srt


def test_read_srt_file_chuẩn(tmp_path):
    p = ghi(tmp_path, "a.srt",
            "1\n00:00:01,000 --> 00:00:02,000\nXin chào\n\n"
            "2\n00:00:03,000 --> 00:00:04,500\nTạm biệt\n")
    assert bo_ba(read_srt(p)) == [(1.0, 2.0, "Xin chào"), (3.0, 4.5, "Tạm biệt")], \
        "file chuẩn phải đọc ra đúng hai câu"


def test_read_srt_thiếu_số_thứ_tự(tmp_path):
    """Số thứ tự chỉ để cho người đọc, thiếu thì vẫn phải hiểu được."""
    p = ghi(tmp_path, "b.srt",
            "00:00:01,000 --> 00:00:02,000\nKhông có số\n\n"
            "00:00:03,000 --> 00:00:04,000\nCâu hai\n")
    assert bo_ba(read_srt(p)) == [(1.0, 2.0, "Không có số"), (3.0, 4.0, "Câu hai")], \
        "khối thiếu số thứ tự vẫn phải đọc đủ hai câu"


def test_read_srt_số_thứ_tự_lung_tung(tmp_path):
    p = ghi(tmp_path, "c.srt",
            "99\n00:00:01,000 --> 00:00:02,000\nMột\n\n"
            "5\n00:00:03,000 --> 00:00:04,000\nHai\n")
    assert [c.text for c in read_srt(p)] == ["Một", "Hai"], \
        "số thứ tự sai cũng không được làm mất câu"


def test_read_srt_dùng_dấu_chấm_thay_dấu_phẩy(tmp_path):
    p = ghi(tmp_path, "d.srt", "1\n00:00:01.000 --> 00:00:02.500\nDấu chấm\n")
    assert bo_ba(read_srt(p)) == [(1.0, 2.5, "Dấu chấm")], \
        "mốc dùng dấu chấm vẫn phải đọc đúng"


def test_read_srt_có_BOM(tmp_path):
    """Notepad và nhiều tool Windows ghi kèm BOM — không được lọt vào chữ."""
    p = ghi(tmp_path, "e.srt", "1\n00:00:01,000 --> 00:00:02,000\nCó BOM\n",
            ma_hoa="utf-8-sig")
    ra = read_srt(p)
    assert bo_ba(ra) == [(1.0, 2.0, "Có BOM")], "BOM không được làm hỏng câu đầu"
    assert not ra[0].text.startswith("﻿"), "BOM không được dính vào nội dung"


def test_read_srt_kết_dòng_CRLF(tmp_path):
    p = ghi(tmp_path, "f.srt", "1\r\n00:00:01,000 --> 00:00:02,000\r\nCRLF\r\n")
    assert bo_ba(read_srt(p)) == [(1.0, 2.0, "CRLF")], \
        "file kết dòng kiểu Windows phải đọc như thường, không dính \\r vào chữ"


def test_read_srt_gộp_câu_nhiều_dòng_thành_một(tmp_path):
    p = ghi(tmp_path, "g.srt", "1\n00:00:01,000 --> 00:00:02,000\nDòng một\nDòng hai\n")
    assert bo_ba(read_srt(p)) == [(1.0, 2.0, "Dòng một Dòng hai")], \
        "câu xuống dòng phải được nối bằng dấu cách để pipeline dịch cả câu"


def test_read_srt_thừa_khoảng_trắng_quanh_mũi_tên(tmp_path):
    p = ghi(tmp_path, "h.srt", "1\n00:00:01,000   -->   00:00:02,000\nThừa cách\n")
    assert bo_ba(read_srt(p)) == [(1.0, 2.0, "Thừa cách")], \
        "khoảng trắng thừa quanh --> không được làm hỏng việc đọc"


def test_read_srt_bỏ_khối_không_có_chữ(tmp_path):
    p = ghi(tmp_path, "i.srt",
            "1\n00:00:01,000 --> 00:00:02,000\n\n\n"
            "2\n00:00:03,000 --> 00:00:04,000\nCó chữ\n")
    assert bo_ba(read_srt(p)) == [(3.0, 4.0, "Có chữ")], \
        "khối chỉ có mốc mà không có chữ thì bỏ, giữ lại chỉ tổ tạo câu rỗng"


def test_read_srt_file_rỗng(tmp_path):
    assert read_srt(ghi(tmp_path, "j.srt", "")) == [], "file rỗng đọc ra danh sách rỗng"


def test_read_srt_file_chỉ_có_khoảng_trắng(tmp_path):
    assert read_srt(ghi(tmp_path, "k.srt", "\n\n   \n\n")) == [], \
        "file toàn dòng trắng cũng phải ra rỗng chứ không được nổ"


def test_read_srt_file_không_phải_srt(tmp_path):
    assert read_srt(ghi(tmp_path, "l.srt", "đây không phải srt\nchẳng có mốc nào\n")) == [], \
        "file không có dòng mốc nào thì bỏ qua hết, không nổ"


def test_read_srt_khối_thừa_dòng_rác_trước_mốc(tmp_path):
    p = ghi(tmp_path, "m.srt", "rác\n1\n00:00:01,000 --> 00:00:02,000\nNội dung\n")
    assert bo_ba(read_srt(p)) == [(1.0, 2.0, "Nội dung")], \
        "dòng rác trước mốc phải bị bỏ qua, chữ chỉ lấy từ sau dòng mốc"


def test_read_srt_một_câu_duy_nhất(tmp_path):
    p = ghi(tmp_path, "n.srt", "1\n00:00:00,000 --> 00:00:01,000\nMột câu\n")
    assert len(read_srt(p)) == 1, "file một câu phải đọc ra đúng một câu"


# ====================================================== write_srt vòng tròn


def test_write_rồi_read_là_vòng_tròn_khép_kín(tmp_path):
    goc = [Cue(0.0, 1.5, "Câu một"), Cue(2.25, 4.0, "Câu hai"),
           Cue(3723.456, 3724.0, "Câu ba")]
    p = tmp_path / "rt.srt"
    write_srt(p, goc)
    assert bo_ba(read_srt(p)) == bo_ba(goc), \
        "ghi ra rồi đọc lại phải được đúng danh sách ban đầu"


def test_write_srt_đánh_số_lại_từ_1(tmp_path):
    p = tmp_path / "so.srt"
    write_srt(p, [Cue(1, 2, "a"), Cue(3, 4, "b")])
    dong = p.read_text(encoding="utf-8").splitlines()
    assert dong[0] == "1" and dong[4] == "2", \
        "số thứ tự phải được đánh lại từ 1 và tăng dần"


def test_write_srt_danh_sách_rỗng_ra_file_rỗng(tmp_path):
    p = tmp_path / "rong.srt"
    write_srt(p, [])
    assert p.read_text(encoding="utf-8") == "", "không có câu nào thì file rỗng"
    assert read_srt(p) == [], "đọc lại file rỗng vẫn phải ra danh sách rỗng"


def test_write_srt_dùng_dấu_phẩy_cho_mili_giây(tmp_path):
    p = tmp_path / "phay.srt"
    write_srt(p, [Cue(1.5, 2.5, "a")])
    assert "00:00:01,500 --> 00:00:02,500" in p.read_text(encoding="utf-8"), \
        "SRT chuẩn dùng dấu phẩy, ghi dấu chấm là nhiều trình dựng không nhận"


def test_write_srt_ghi_UTF8_không_BOM(tmp_path):
    p = tmp_path / "utf8.srt"
    write_srt(p, [Cue(1, 2, "Tiếng Việt có dấu")])
    assert not p.read_bytes().startswith(b"\xef\xbb\xbf"), \
        "ghi kèm BOM dễ làm filter subtitles của ffmpeg hiển thị sai ký tự đầu"
    assert "Tiếng Việt có dấu" in p.read_text(encoding="utf-8"), \
        "chữ tiếng Việt phải giữ nguyên dấu"


def test_write_srt_câu_nhiều_dòng_khi_đọc_lại_bị_gộp_thành_một_dòng(tmp_path):
    """Vòng tròn không khép kín ở đây và đó là cố ý: pipeline dịch theo cả câu."""
    p = tmp_path / "multi.srt"
    write_srt(p, [Cue(1, 2, "dòng một\ndòng hai")])
    assert bo_ba(read_srt(p)) == [(1.0, 2.0, "dòng một dòng hai")], \
        "chữ xuống dòng khi đọc lại bị nối bằng dấu cách"


def test_write_srt_ghi_đè_file_cũ(tmp_path):
    p = tmp_path / "de.srt"
    write_srt(p, [Cue(1, 2, "cũ"), Cue(3, 4, "cũ 2")])
    write_srt(p, [Cue(5, 6, "mới")])
    assert bo_ba(read_srt(p)) == [(5.0, 6.0, "mới")], \
        "ghi lại phải thay hẳn nội dung cũ, không được nối thêm"


def test_write_srt_mốc_âm_được_kẹp_khi_ghi(tmp_path):
    p = tmp_path / "am.srt"
    write_srt(p, [Cue(-2.0, 1.0, "lệch offset")])
    assert bo_ba(read_srt(p)) == [(0.0, 1.0, "lệch offset")], \
        "mốc âm phải thành 0 khi ghi ra, không thì file SRT hỏng"


# ==================================================================== Cue


def test_cue_thời_lượng():
    assert Cue(1.0, 3.5, "x").dur == pytest.approx(2.5), "thời lượng là hiệu hai mốc"


def test_cue_mốc_ngược_thì_thời_lượng_bằng_0():
    assert Cue(5.0, 1.0, "x").dur == 0.0, "mốc ngược cho thời lượng 0, không được âm"
