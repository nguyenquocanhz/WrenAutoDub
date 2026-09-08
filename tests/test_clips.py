# -*- coding: utf-8 -*-
"""Test cho wrenautodub/clips.py — cắt, ghép, sắp xếp clip và ánh xạ phụ đề.

Phần quan trọng nhất là `remap_cues_clips`: theo CLAUDE.md, dùng nhầm
`remap_cues` (bản chỉ biết tốc độ) thì câu nằm trong đoạn đã cắt vẫn còn và
mốc sai hết.
"""

from __future__ import annotations

import pytest

from _hotro import bo_ba, bo_bon, lien_tuc, nhan_ra, nhan_trung
from wrenautodub.clips import (MIN_CLIP, Clip, _edge_after, _edge_before,
                               build_items_audio, build_items_video, can_merge,
                               compose, default_clips, dest_to_src, ensure,
                               items_duration, layout, merge_all, merge_at,
                               out_duration, remap_cues_clips, ripple_close,
                               split_at)
from wrenautodub.srtutil import Cue
from wrenautodub.timing import Speed, timeline

KHONG_TOC_DO = timeline([], 30.0)      # bảng thời gian phim 30s, không đổi tốc độ


# ======================================================== Clip / ensure


def test_clip_thời_lượng_và_nhãn():
    c = Clip(2.0, 5.5, 0.0)
    assert c.dur == pytest.approx(3.5), "thời lượng là hiệu hai mốc nguồn"
    assert c.label == "2.0–5.5s  (3.5s)", "nhãn hiện cho người dùng phải gọn"


def test_clip_mốc_ngược_thì_thời_lượng_bằng_0_chứ_không_âm():
    assert Clip(5.0, 2.0, 0.0).dur == 0.0, \
        "clip có mốc cuối nhỏ hơn mốc đầu phải cho thời lượng 0, không được âm"


def test_default_clips_luôn_có_ít_nhất_một_clip_hợp_lệ():
    assert bo_bon(default_clips(100.0)) == [(0.0, 100.0, 0.0, True)], \
        "phim chưa cắt gì thì có đúng một clip phủ cả phim"
    assert default_clips(0.0)[0].dur >= MIN_CLIP, \
        "phim dài 0 giây vẫn phải sinh clip dài tối thiểu MIN_CLIP để không nổ"


@pytest.mark.parametrize("dau_vao", [None, [], [Clip(0, 5, 0, enabled=False)],
                                     [Clip(0, 0.05, 0)]],
                         ids=["None", "rong", "clip-tat", "clip-qua-ngan"])
def test_ensure_không_còn_clip_sống_thì_quay_về_phủ_cả_phim(dau_vao):
    assert bo_bon(ensure(dau_vao, 100.0)) == [(0.0, 100.0, 0.0, True)], \
        "không còn clip nào dùng được thì phải rơi về mặc định, không trả rỗng"


def test_ensure_giữ_clip_đang_bật():
    ra = ensure([Clip(0, 5, 0), Clip(10, 20, 5, enabled=False)], 100.0)
    assert bo_bon(ra) == [(0.0, 5.0, 0.0, True)], "clip bị tắt phải bị loại khỏi bản dựng"


# ========================================================== ripple_close


def test_ripple_close_danh_sách_rỗng():
    assert ripple_close([]) == [], "không có clip nào thì trả về rỗng"


def test_ripple_close_xoá_hết_khoảng_hở():
    ra = ripple_close([Clip(0, 5, 0.0), Clip(20, 25, 50.0)])
    assert [c.at for c in ra] == [0.0, 5.0], \
        "clip sau phải hít sát clip trước, khoảng hở 45 giây bị dồn hết"
    assert [(c.src_start, c.src_end) for c in ra] == [(0, 5), (20, 25)], \
        "dồn vị trí không được đổi mốc nguồn"


def test_ripple_close_sắp_theo_vị_trí_hiện_có():
    ra = ripple_close([Clip(20, 25, 10.0), Clip(0, 5, 0.0)])
    assert [(c.src_start, c.src_end) for c in ra] == [(0, 5), (20, 25)], \
        "phải xếp theo vị trí trên dòng thời gian đích, không theo thứ tự nhập"


def test_ripple_close_giữ_cờ_bật_tắt():
    ra = ripple_close([Clip(0, 5, 0.0, enabled=False)])
    assert ra[0].enabled is False, "dồn clip không được bật lại clip đã tắt"


# ================================================================ layout


def test_layout_chế_độ_hít_lại_phủ_liên_tục_không_khoảng_trống():
    cs = [Clip(0, 5, 0.0), Clip(20, 25, 10.0)]
    lay = layout(cs, ripple=True)
    assert lay == [(0.0, 5.0, 0), (5.0, 10.0, 1)], \
        "chế độ hít lại thì clip sau nối ngay sau clip trước"
    assert all(i >= 0 for _a, _b, i in lay), "chế độ hít lại không được có khoảng trống"


def test_layout_chế_độ_rời_rạc_chèn_khoảng_trống():
    cs = [Clip(0, 5, 0.0), Clip(20, 25, 10.0)]
    lay = layout(cs, ripple=False)
    assert lay == [(0.0, 5.0, 0), (5.0, 10, -1), (10, 15, 1)], \
        "chế độ rời rạc phải chèn khoảng trống (-1) để clip giữ đúng chỗ"
    assert lien_tuc([(a, b) for a, b, _i in lay]), "các mảnh vẫn phải nối đuôi nhau"


def test_layout_rời_rạc_có_khoảng_trống_ở_đầu():
    lay = layout([Clip(0, 5, 3.0)], ripple=False)
    assert lay == [(0.0, 3.0, -1), (3.0, 8.0, 0)], \
        "clip đặt ở giây 3 thì 3 giây đầu phải là khoảng trống"


def test_layout_danh_sách_rỗng():
    assert layout([], True) == [] and layout([], False) == [], \
        "không có clip nào thì bố cục rỗng ở cả hai chế độ"


def test_layout_không_bao_giờ_cho_hai_mảnh_chồng_nhau():
    cs = [Clip(0, 10, 0.0), Clip(50, 60, 2.0)]     # at=2 chồng lên clip trước
    lay = layout(cs, ripple=False)
    assert lien_tuc([(a, b) for a, b, _i in lay]), \
        "clip đặt chồng nhau phải bị đẩy nối tiếp, không được chồng lấn"


def test_out_duration_hai_chế_độ():
    cs = [Clip(0, 5, 0.0), Clip(20, 25, 10.0)]
    assert out_duration(cs, True) == pytest.approx(10.0), \
        "hít lại: thời lượng bằng tổng độ dài clip"
    assert out_duration(cs, False) == pytest.approx(15.0), \
        "rời rạc: thời lượng tính cả khoảng trống 5 giây ở giữa"


def test_out_duration_danh_sách_rỗng():
    assert out_duration([], True) == 0.0, "không có clip nào thì thời lượng 0"


# =========================================================== dest_to_src


def test_dest_to_src_hít_lại():
    cs = [Clip(0, 5, 0.0), Clip(20, 25, 10.0)]
    assert dest_to_src(0.0, cs, True) == pytest.approx(0.0)
    assert dest_to_src(4.9, cs, True) == pytest.approx(4.9), "còn trong clip đầu"
    assert dest_to_src(5.0, cs, True) == pytest.approx(20.0), \
        "vừa qua mối nối là nhảy sang mốc nguồn của clip sau"
    assert dest_to_src(7.0, cs, True) == pytest.approx(22.0)


def test_dest_to_src_rơi_vào_khoảng_trống_thì_không_có_nguồn():
    cs = [Clip(0, 5, 0.0), Clip(20, 25, 10.0)]
    assert dest_to_src(7.0, cs, False) is None, \
        "giây 7 rơi vào khoảng trống (màn đen) nên không ứng với giây nào của phim gốc"


def test_dest_to_src_ngoài_phim_thì_trả_None():
    cs = [Clip(0, 5, 0.0)]
    assert dest_to_src(100.0, cs, True) is None, "quá cuối bản dựng thì không có nguồn"


# ============================================================== split_at


def test_split_at_cắt_giữa_clip_thành_hai():
    ra = split_at([Clip(0, 10, 0.0)], 4.0, ripple=True)
    assert bo_bon(ra) == [(0.0, 4.0, 0.0, True), (4.0, 10.0, 4.0, True)], \
        "cắt ở giây 4 phải sinh đúng hai clip nối nhau, không hở mốc nguồn"


def test_split_at_không_làm_đổi_tổng_thời_lượng():
    goc = [Clip(0, 10, 0.0)]
    ra = split_at(goc, 4.0, True)
    assert out_duration(ra, True) == pytest.approx(out_duration(goc, True)), \
        "cắt chỉ tách clip, không được làm phim dài ra hay ngắn đi"


@pytest.mark.parametrize("t", [0.0, 0.05, 9.95, 10.0, -5.0, 50.0],
                         ids=["0", "sat-dau", "sat-cuoi", "dung-cuoi", "am", "ngoai"])
def test_split_at_quá_sát_mép_hoặc_ngoài_tầm_thì_không_cắt(t):
    """Cắt sát mép sẽ đẻ ra clip ngắn hơn MIN_CLIP, vô dụng mà còn phiền."""
    ra = split_at([Clip(0, 10, 0.0)], t, True)
    assert len(ra) == 1, f"cắt ở giây {t} không được sinh thêm clip"
    assert bo_bon(ra) == [(0.0, 10.0, 0.0, True)], "clip phải giữ nguyên"


def test_split_at_danh_sách_rỗng():
    assert split_at([], 5.0, True) == [], "không có clip nào thì không có gì để cắt"


def test_split_at_chỉ_cắt_clip_chứa_điểm_cắt():
    cs = [Clip(0, 5, 0.0), Clip(20, 30, 5.0)]
    ra = split_at(cs, 8.0, ripple=True)      # giây 8 rơi vào clip thứ hai
    assert len(ra) == 3, "chỉ clip chứa điểm cắt bị tách, clip kia giữ nguyên"
    assert bo_bon(ra)[0] == (0.0, 5.0, 0.0, True), "clip đầu không bị đụng tới"
    assert bo_bon(ra)[1][:2] == (20.0, 23.0), \
        "điểm cắt ở giây 8 của bản dựng ứng với giây 23 của phim gốc"


def test_split_at_chế_độ_rời_rạc_giữ_nguyên_vị_trí():
    ra = split_at([Clip(0, 10, 0.0)], 4.0, ripple=False)
    assert bo_bon(ra) == [(0.0, 4.0, 0.0, True), (4.0, 10.0, 4.0, True)], \
        "chế độ rời rạc cũng phải cắt đúng chỗ và đặt nửa sau ngay sau nửa đầu"


def test_split_at_rời_rạc_không_cắt_khi_điểm_cắt_rơi_vào_khoảng_trống():
    cs = [Clip(0, 5, 0.0), Clip(20, 25, 10.0)]
    ra = split_at(cs, 7.0, ripple=False)     # giây 7 là màn đen
    assert len(ra) == 2, "điểm cắt rơi vào khoảng trống thì không có clip nào bị tách"


def test_split_at_cắt_hai_lần_thành_ba_clip():
    ra = split_at(split_at([Clip(0, 30, 0.0)], 10.0, True), 20.0, True)
    assert len(ra) == 3, "cắt hai lần phải ra ba clip"
    assert [(c.src_start, c.src_end) for c in ra] == [(0, 10.0), (10.0, 20.0), (20.0, 30)], \
        "ba clip phải phủ liền mạch phim gốc, không sót giây nào"


# =============================================== can_merge / merge_at / all


def test_can_merge_hai_clip_vốn_liền_nhau():
    cs = [Clip(0, 5, 0.0), Clip(5, 10, 5.0)]
    assert can_merge(cs, 0, True) is True, "hai clip liền nhau trong phim gốc thì ghép được"


def test_can_merge_hai_clip_không_liền_nhau():
    cs = [Clip(0, 5, 0.0), Clip(7, 10, 5.0)]
    assert can_merge(cs, 0, True) is False, \
        "giữa hai clip đã mất 2 giây phim gốc nên ghép lại là sai nội dung"


@pytest.mark.parametrize("i", [-1, 1, 5, 99], ids=["-1", "cuoi", "5", "99"])
def test_can_merge_chỉ_số_ngoài_tầm(i):
    cs = [Clip(0, 5, 0.0), Clip(5, 10, 5.0)]
    assert can_merge(cs, i, True) is False, f"chỉ số {i} không có clip kế để ghép"


def test_can_merge_danh_sách_rỗng():
    assert can_merge([], 0, True) is False, "danh sách rỗng thì không ghép được gì"


def test_merge_at_gộp_hai_clip_liền_nhau():
    ra = merge_at([Clip(0, 5, 0.0), Clip(5, 10, 5.0)], 0, True)
    assert bo_bon(ra) == [(0.0, 10.0, 0.0, True)], \
        "ghép hai clip liền nhau phải ra đúng một clip phủ cả hai"


def test_merge_at_không_ghép_được_thì_giữ_nguyên():
    cs = [Clip(0, 5, 0.0), Clip(7, 10, 5.0)]
    ra = merge_at(cs, 0, True)
    assert len(ra) == 2, "không liền nhau thì phải giữ nguyên hai clip"
    assert out_duration(ra, True) == pytest.approx(out_duration(cs, True)), \
        "thao tác bất thành không được làm đổi thời lượng"


def test_merge_all_gộp_hết_chuỗi_liền_nhau():
    cs = [Clip(0, 2, 0.0), Clip(2, 4, 2.0), Clip(4, 6, 4.0)]
    assert bo_bon(merge_all(cs, True)) == [(0.0, 6.0, 0.0, True)], \
        "ba clip liền nhau phải gộp về đúng một"


def test_merge_all_chỉ_gộp_cặp_thật_sự_liền_nhau():
    cs = [Clip(0, 2, 0.0), Clip(2, 4, 2.0), Clip(8, 9, 4.0)]
    ra = merge_all(cs, True)
    assert [(c.src_start, c.src_end) for c in ra] == [(0, 4.0), (8, 9)], \
        "clip thứ ba cách quãng nên phải đứng riêng"


@pytest.mark.parametrize("cs", [[], [Clip(0, 2, 0.0)]], ids=["rong", "mot-phan-tu"])
def test_merge_all_danh_sách_rỗng_hoặc_một_phần_tử(cs):
    ra = merge_all(cs, True)
    assert len(ra) == len(cs), "không có cặp nào để gộp thì giữ nguyên"


def test_merge_all_không_làm_đổi_tổng_thời_lượng():
    cs = [Clip(0, 2, 0.0), Clip(2, 4, 2.0), Clip(8, 9, 4.0)]
    assert out_duration(merge_all(cs, True), True) == pytest.approx(out_duration(cs, True)), \
        "gộp clip chỉ bớt số mảnh, không được đổi thời lượng"


def test_cắt_rồi_gộp_lại_trả_về_đúng_clip_ban_đầu():
    goc = [Clip(0.0, 30.0, 0.0)]
    ra = merge_all(split_at(split_at(goc, 10.0, True), 20.0, True), True)
    assert bo_bon(ra) == bo_bon(goc), \
        "cắt bao nhiêu lần rồi gộp hết cũng phải quay về clip ban đầu"


# =============================================================== compose


def test_compose_một_clip_không_đổi_tốc_độ():
    items = compose([Clip(0, 30, 0.0)], KHONG_TOC_DO, True)
    assert items == [("src", 0, 30, 1.0)], \
        "phim chưa cắt chưa đổi tốc độ thì chỉ có đúng một việc phải làm"


def test_compose_cắt_clip_theo_mốc_đổi_tốc_độ():
    """Cắt clip theo mốc tốc độ để hai tính năng chồng lên nhau vẫn đúng."""
    segs = timeline([Speed(2, 4, 2.0)], 30.0)
    items = compose([Clip(0, 10, 0.0)], segs, True)
    assert items == [("src", 0, 2, 1.0), ("src", 2, 4, 2.0), ("src", 4, 10, 1.0)], \
        "một clip phải bị chẻ thành ba mảnh vì đoạn giữa chạy 2×"


def test_compose_bỏ_hẳn_phần_phim_bị_cắt():
    items = compose([Clip(0, 10, 0.0), Clip(20, 30, 10.0)], KHONG_TOC_DO, True)
    assert items == [("src", 0, 10, 1.0), ("src", 20, 30, 1.0)], \
        "đoạn 10–20s đã bị cắt thì không được xuất hiện trong danh sách việc"


def test_compose_không_có_bảng_tốc_độ_thì_lấy_nguyên_clip():
    items = compose([Clip(0, 10, 0.0)], [], True)
    assert items == [("src", 0, 10, 1.0)], \
        "không truyền bảng tốc độ thì vẫn phải giữ nguyên clip, không được bỏ trống"


def test_compose_danh_sách_clip_rỗng():
    assert compose([], KHONG_TOC_DO, True) == [], "không có clip nào thì không có việc gì"


def test_compose_chế_độ_rời_rạc_sinh_khoảng_trống():
    items = compose([Clip(0, 10, 0.0), Clip(20, 30, 15.0)], KHONG_TOC_DO, False)
    assert items == [("src", 0, 10, 1.0), ("gap", 5.0), ("src", 20, 30, 1.0)], \
        "khoảng hở 5 giây giữa hai clip phải thành một mảnh 'gap' (màn đen + im lặng)"


def test_compose_thời_lượng_khớp_với_bố_cục():
    cs = [Clip(0, 10, 0.0), Clip(20, 30, 15.0)]
    for ripple in (True, False):
        assert items_duration(compose(cs, KHONG_TOC_DO, ripple)) == \
            pytest.approx(out_duration(cs, ripple)), \
            f"tổng thời lượng các mảnh phải bằng thời lượng bố cục (ripple={ripple})"


def test_compose_hệ_số_tốc_độ_rút_ngắn_thời_lượng():
    segs = timeline([Speed(0, 30, 2.0)], 30.0)
    items = compose([Clip(0, 30, 0.0)], segs, True)
    assert items_duration(items) == pytest.approx(15.0), \
        "cả phim chạy 2× thì bản dựng còn đúng một nửa"


def test_items_duration_rỗng_và_có_khoảng_trống():
    assert items_duration([]) == 0.0, "không có mảnh nào thì thời lượng 0"
    assert items_duration([("gap", 3.0), ("src", 0, 10, 2.0)]) == pytest.approx(8.0), \
        "khoảng trống tính nguyên, mảnh 2× tính một nửa"


@pytest.mark.bug
def test_compose_giữ_clip_nằm_ngoài_khoảng_bảng_tốc_độ():
    """Clip không giao với bảng tốc độ bị bỏ im lặng, kéo theo thời lượng = 0.

    Hệ quả: build_items_video nhận danh sách rỗng nên không dựng filter nào, và
    bản xuất ra lại là NGUYÊN phim gốc — sai hoàn toàn mà không có lỗi nào.
    """
    items = compose([Clip(40, 50, 0.0)], KHONG_TOC_DO, True)   # bảng chỉ phủ 0–30s
    assert items, "clip 40–50s không được biến mất khỏi danh sách việc"


# ================================================== remap_cues_clips (cốt lõi)


GIU = [Clip(0, 10, 0.0), Clip(20, 30, 10.0)]     # phim 30s, cắt bỏ đoạn 10–20s


def test_remap_câu_trong_đoạn_giữ_lại_thì_giữ_nguyên_mốc():
    ra = remap_cues_clips([Cue(1, 3, "A")], GIU, KHONG_TOC_DO, True)
    assert bo_ba(ra) == [(1.0, 3.0, "A")], \
        "câu nằm trong đoạn đầu (không bị cắt gì phía trước) thì mốc không đổi"


def test_remap_câu_sau_nhát_cắt_phải_dồn_lên():
    ra = remap_cues_clips([Cue(21, 25, "E")], GIU, KHONG_TOC_DO, True)
    assert bo_ba(ra) == [(11.0, 15.0, "E")], \
        "đã cắt bỏ 10 giây phía trước nên câu ở giây 21 phải dồn về giây 11"


def test_remap_câu_nằm_gọn_trong_đoạn_bị_cắt_thì_bỏ_hẳn():
    """Đây chính là cái mà remap_cues (bản chỉ biết tốc độ) làm sai."""
    ra = remap_cues_clips([Cue(12, 15, "B")], GIU, KHONG_TOC_DO, True)
    assert ra == [], "câu 12–15s nằm trọn trong đoạn đã cắt nên phải biến mất"


def test_remap_câu_bắc_qua_mối_nối_giữ_sang_cắt_phải_bị_cắt_cụt():
    ra = remap_cues_clips([Cue(8, 13, "C")], GIU, KHONG_TOC_DO, True)
    assert bo_ba(ra) == [(8.0, 10.0, "C")], \
        "câu 8–13s phải bị cắt cụt ở mối nối (giây 10), không được bỏ cả câu"


def test_remap_câu_bắc_qua_mối_nối_cắt_sang_giữ_phải_bị_cắt_cụt():
    ra = remap_cues_clips([Cue(18, 22, "D")], GIU, KHONG_TOC_DO, True)
    assert bo_ba(ra) == [(10.0, 12.0, "D")], \
        "câu 18–22s phải bắt đầu ngay tại mối nối chứ không bị bỏ"


def test_remap_câu_vượt_quá_cuối_phim_bị_cắt_cụt_ở_cuối():
    ra = remap_cues_clips([Cue(29, 35, "G")], GIU, KHONG_TOC_DO, True)
    assert bo_ba(ra) == [(19.0, 20.0, "G")], \
        "câu tràn qua cuối phim phải dừng đúng ở cuối bản dựng"


def test_remap_câu_bắt_đầu_đúng_lúc_phim_hết_thì_bỏ():
    ra = remap_cues_clips([Cue(30, 32, "H")], GIU, KHONG_TOC_DO, True)
    assert ra == [], "câu bắt đầu ở giây 30 (phim đã hết) thì không còn chỗ để hiện"


def test_remap_câu_trùm_qua_cả_đoạn_bị_cắt():
    ra = remap_cues_clips([Cue(5, 25, "F")], GIU, KHONG_TOC_DO, True)
    assert bo_ba(ra) == [(5.0, 15.0, "F")], \
        "hai đầu câu đều rơi vào phần giữ lại nên câu được co lại ôm qua mối nối"


def test_remap_danh_sách_rỗng():
    assert remap_cues_clips([], GIU, KHONG_TOC_DO, True) == [], \
        "không có câu nào thì trả về rỗng"


def test_remap_câu_dài_bằng_0_bị_bỏ():
    assert remap_cues_clips([Cue(5, 5, "x")], GIU, KHONG_TOC_DO, True) == [], \
        "câu dài 0 giây không hiện được nên bỏ"


def test_remap_câu_ngắn_hơn_0_05s_bị_bỏ():
    assert remap_cues_clips([Cue(5, 5.04, "x")], GIU, KHONG_TOC_DO, True) == [], \
        "câu ngắn hơn 0.05s sau khi ánh xạ thì bỏ cho đỡ nhấp nháy"


def test_remap_kết_hợp_cắt_clip_và_đổi_tốc_độ():
    segs = timeline([Speed(0, 10, 2.0)], 30.0)     # 10s đầu chạy 2×
    ra = remap_cues_clips([Cue(2, 4, "x")], GIU, segs, True)
    assert bo_ba(ra) == [(1.0, 2.0, "x")], \
        "câu trong đoạn 2× phải vừa dồn vừa ngắn lại đúng một nửa"
    ra2 = remap_cues_clips([Cue(22, 24, "y")], GIU, segs, True)
    assert bo_ba(ra2) == [(7.0, 9.0, "y")], \
        "câu sau đó phải dồn thêm 5 giây do đoạn đầu đã bị rút ngắn"


def test_remap_áp_offset_giọng_đọc():
    ra = remap_cues_clips([Cue(1, 3, "x")], GIU, KHONG_TOC_DO, True, offset=2.0)
    assert bo_ba(ra) == [(3.0, 5.0, "x")], "offset dương đẩy câu ra sau"
    ra2 = remap_cues_clips([Cue(1, 3, "x")], GIU, KHONG_TOC_DO, True, offset=-2.0)
    assert bo_ba(ra2) == [(0.0, 1.0, "x")], \
        "offset âm đẩy câu về trước, phần lòi ra trước giây 0 bị cắt cụt"


def test_remap_chế_độ_rời_rạc_tính_cả_khoảng_trống():
    rr = [Clip(0, 10, 0.0), Clip(20, 30, 15.0)]    # có 5 giây màn đen ở giữa
    ra = remap_cues_clips([Cue(21, 23, "x")], rr, KHONG_TOC_DO, False)
    assert bo_ba(ra) == [(16.0, 18.0, "x")], \
        "câu sau khoảng trống phải cộng thêm đúng 5 giây màn đen"


def test_remap_giữ_nguyên_nội_dung_câu():
    ra = remap_cues_clips([Cue(1, 3, "Xin chào các bạn")], GIU, KHONG_TOC_DO, True)
    assert ra[0].text == "Xin chào các bạn", "ánh xạ mốc không được đụng vào chữ"


@pytest.mark.bug
def test_remap_câu_trùm_gọn_clip_được_giữ_vẫn_phải_còn():
    """Hai đầu câu đều rơi vào phần đã cắt nhưng khúc giữa thì vẫn được giữ.

    Code kết luận 's is None and e is None' là 'cả câu nằm trong đoạn đã cắt'
    rồi bỏ luôn — trái với chính chú thích trong hàm ('không thì mất phụ đề cho
    đoạn còn giữ').
    """
    giu = [Clip(10, 12, 0.0)]                      # chỉ giữ đúng 2 giây 10–12s
    ra = remap_cues_clips([Cue(5, 20, "câu dài")], giu, KHONG_TOC_DO, True)
    assert ra, "đoạn 10–12s vẫn nằm trong bản dựng nên câu phải được giữ (cắt cụt hai đầu)"


def test_tìm_mối_nối_của_thời_điểm_ngoài_bản_dựng():
    """Nhánh phòng thân: thời điểm không nằm trong mảnh nào thì trả None."""
    items = [("src", 0, 10, 1.0)]
    assert _edge_after(99.0, items) is None, "quá cuối bản dựng thì không có mối nối sau"
    assert _edge_before(99.0, items) is None, "quá cuối bản dựng thì không có mối nối trước"
    assert _edge_after(0.0, []) is None, "không có mảnh nào thì không có mối nối"
    assert _edge_before(0.0, []) is None, "không có mảnh nào thì không có mối nối"


def test_tìm_mối_nối_trong_bản_dựng():
    items = [("src", 0, 10, 1.0), ("gap", 5.0), ("src", 20, 30, 1.0)]
    assert _edge_after(3.0, items) == pytest.approx(10.0), \
        "giây 3 nằm trong mảnh đầu nên mối nối sau là giây 10"
    assert _edge_before(17.0, items) == pytest.approx(15.0), \
        "giây 17 nằm trong mảnh cuối (bắt đầu ở giây 15 sau khoảng trống)"


# ================================================= dựng chuỗi filter cho clip


def test_build_items_không_có_mảnh_nào_thì_không_dựng_filter():
    assert build_items_video([], "0:v", 1920, 1080) == ([], "0:v"), \
        "không có mảnh nào thì trả thẳng luồng vào"
    assert build_items_audio([], "0:a") == ([], "0:a")


def test_build_items_video_nhãn_không_trùng():
    items = compose([Clip(0, 10, 0.0), Clip(20, 30, 15.0)],
                    timeline([Speed(2, 4, 2.0)], 30.0), False)
    parts, ra = build_items_video(items, "0:v", 1920, 1080)
    assert nhan_trung(parts) == [], f"nhãn trùng thì ffmpeg từ chối chạy: {nhan_trung(parts)}"
    assert ra == "cvout", "nhãn ra phải theo quy ước để mắt xích sau nối vào"


def test_build_items_video_khoảng_trống_dựng_màn_đen():
    items = compose([Clip(0, 10, 0.0), Clip(20, 30, 15.0)], KHONG_TOC_DO, False)
    parts, _ = build_items_video(items, "0:v", 1280, 720, fps=30.0)
    den = [p for p in parts if "color=c=black" in p]
    assert len(den) == 1, "đúng một khoảng trống thì dựng đúng một mảnh màn đen"
    assert "s=1280x720" in den[0] and "r=30" in den[0], \
        "màn đen phải đúng khung hình và fps, không thì concat từ chối ghép"


def test_build_items_audio_khoảng_trống_dựng_im_lặng():
    items = compose([Clip(0, 10, 0.0), Clip(20, 30, 15.0)], KHONG_TOC_DO, False)
    parts, _ = build_items_audio(items, "0:a")
    assert any("anullsrc" in p for p in parts), \
        "khoảng trống bên tiếng phải là im lặng chứ không được bỏ trống"


def test_build_items_tiếng_và_hình_không_dùng_chung_nhãn():
    items = compose([Clip(0, 10, 0.0)], timeline([Speed(2, 4, 2.0)], 30.0), True)
    vparts, _v = build_items_video(items, "0:v", 1920, 1080)
    aparts, _a = build_items_audio(items, "0:a")
    assert nhan_trung(aparts) == [], "chuỗi tiếng có nhãn trùng"
    assert set(nhan_ra(vparts)) & set(nhan_ra(aparts)) == set(), \
        "chuỗi hình dùng tiền tố cv*, chuỗi tiếng ca* — không được đụng nhau"


def test_build_items_audio_hệ_số_chậm_thì_nối_chuỗi_atempo():
    items = compose([Clip(0, 10, 0.0)], timeline([Speed(0, 30, 0.25)], 30.0), True)
    parts, _ = build_items_audio(items, "0:a")
    day = [p for p in parts if "atempo" in p]
    assert day and day[0].count("atempo") >= 2, \
        "hệ số 0.25 dưới ngưỡng ffmpeg nên phải nối nhiều atempo"
