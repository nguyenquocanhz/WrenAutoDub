# -*- coding: utf-8 -*-
"""Test cho wrenautodub/timing.py — bảng thời gian và đổi tốc độ.

Đây là tầng mà mọi thứ khác dựa vào: phụ đề, giọng thuyết minh và hình đều
ánh xạ qua cùng bảng này, sai một chỗ là lệch hết.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from _hotro import ROOT, he_so_atempo, lien_tuc, bo_ba, tich
from wrenautodub.srtutil import Cue
from wrenautodub.timing import (ATEMPO_MAX, ATEMPO_MIN, CURVE_PRESETS, Speed,
                                atempo_chain, build_speed_audio,
                                build_speed_video, expand_preset, has_speed,
                                map_time, normalize, out_duration, remap_cues,
                                sync_filter, timeline)

# ===================================================================== atempo


@pytest.mark.parametrize("he_so", [0.5, 0.75, 1.0, 2.0, 3.5, 50.0, 100.0],
                         ids=["0.5", "0.75", "1.0", "2.0", "3.5", "50", "100"])
def test_atempo_hệ_số_trong_tầm_thì_chỉ_một_mắt_xích(he_so):
    chain = atempo_chain(he_so)
    assert chain.count("atempo") == 1, \
        f"hệ số {he_so} nằm gọn trong 0.5–100 nên không được nối chuỗi: {chain!r}"
    assert he_so_atempo(chain) == pytest.approx([he_so]), \
        f"hệ số ghi ra phải đúng bằng {he_so}"


@pytest.mark.parametrize("he_so", [0.49, 0.4, 0.25, 0.2, 0.1, 0.01, 0.001],
                         ids=["0.49", "0.4", "0.25", "0.2", "0.1", "0.01", "0.001"])
def test_atempo_hệ_số_nhỏ_hơn_0_5_phải_nối_chuỗi(he_so):
    """atempo của ffmpeg chỉ kham 0.5–100, chậm hơn buộc phải nối nhiều lần."""
    chain = atempo_chain(he_so)
    hs = he_so_atempo(chain)
    assert len(hs) >= 2, \
        f"hệ số {he_so} < 0.5 bắt buộc phải nối từ 2 mắt xích trở lên, nhận: {chain!r}"
    assert tich(hs) == pytest.approx(he_so, rel=1e-6), \
        f"tích các mắt xích phải bằng đúng hệ số gốc {he_so}, nhận {tich(hs)}"
    for h in hs:
        assert ATEMPO_MIN - 1e-9 <= h <= ATEMPO_MAX + 1e-9, \
            f"mắt xích {h} vượt ngoài tầm ffmpeg cho phép ({ATEMPO_MIN}–{ATEMPO_MAX})"


@pytest.mark.parametrize("he_so", [101.0, 150.0, 1000.0, 10000.0],
                         ids=["101", "150", "1000", "10000"])
def test_atempo_hệ_số_lớn_hơn_100_phải_nối_chuỗi(he_so):
    hs = he_so_atempo(atempo_chain(he_so))
    assert len(hs) >= 2, f"hệ số {he_so} > 100 phải nối chuỗi"
    assert tich(hs) == pytest.approx(he_so, rel=1e-6), \
        f"tích các mắt xích phải bằng đúng hệ số gốc {he_so}"
    for h in hs:
        assert h <= ATEMPO_MAX + 1e-9, f"mắt xích {h} vượt trần {ATEMPO_MAX}"


def test_atempo_biên_0_5_không_bị_nối_thừa():
    assert atempo_chain(0.5) == "atempo=0.5", \
        "đúng 0.5 vẫn hợp lệ với ffmpeg nên không được nối thêm mắt xích"


def test_atempo_ngay_dưới_biên_thì_nối_hai_mắt_xích():
    hs = he_so_atempo(atempo_chain(0.499999))
    assert len(hs) == 2, "0.499999 chỉ cần đúng hai mắt xích"
    assert tich(hs) == pytest.approx(0.499999, rel=1e-6)


@pytest.mark.parametrize("he_so,mong_doi", [(1.0, "atempo=1"), (2.0, "atempo=2"),
                                            (100.0, "atempo=100"), (0.5, "atempo=0.5")],
                         ids=["1", "2", "100", "0.5"])
def test_atempo_không_để_số_0_thừa_ở_đuôi(he_so, mong_doi):
    """'atempo=1.000000' vừa dài vừa khó đọc khi soi lệnh ffmpeg."""
    assert atempo_chain(he_so) == mong_doi, \
        f"hệ số {he_so} phải ghi gọn thành {mong_doi!r}"


def test_atempo_không_làm_mất_số_0_trong_phần_nguyên():
    """rstrip('0') dễ ăn nhầm số 0 của 100 — kiểm để chắc không bị."""
    assert he_so_atempo(atempo_chain(100.0)) == [100.0], \
        "atempo=100 không được biến thành atempo=1"


@pytest.mark.bug
@pytest.mark.cham
def test_atempo_hệ_số_0_phải_dừng_chứ_không_treo():
    """Hệ số 0 làm `f /= 0.5` giữ nguyên 0 mãi mãi → vòng lặp không bao giờ thoát.

    Hệ số âm cũng treo y hệt (càng chia càng âm sâu). Chạy trong tiến trình con
    để bộ test không bị treo theo và không bị ăn hết RAM vì list phình vô hạn.
    """
    ma = ("import sys; sys.path.insert(0, r'%s');"
          "from wrenautodub.timing import atempo_chain; print(atempo_chain(0.0))"
          % ROOT)
    try:
        r = subprocess.run([sys.executable, "-c", ma], capture_output=True,
                           text=True, timeout=2.0)
    except subprocess.TimeoutExpired:
        pytest.fail("atempo_chain(0.0) treo vô hạn — phải trả về chuỗi hoặc báo lỗi")
    # Ném ValueError là cách xử đúng: hệ số 0 vô nghĩa, nuốt im lặng chỉ giấu
    # lỗi của chỗ gọi. Chỉ cấm treo, không cấm báo lỗi.
    assert r.returncode == 0 or "ValueError" in (r.stderr or ""),         f"atempo_chain(0.0) nổ kiểu khác: {r.stderr}"


# ================================================================== normalize


def test_normalize_danh_sách_rỗng():
    assert normalize([], 100.0) == [], "không có đoạn nào thì trả về danh sách rỗng"


def test_normalize_một_phần_tử_giữ_nguyên():
    ra = normalize([Speed(1.0, 2.0, 2.0)], 100.0)
    assert len(ra) == 1, "một đoạn hợp lệ phải được giữ"
    assert (ra[0].start, ra[0].end, ra[0].factor) == (1.0, 2.0, 2.0), \
        "đoạn nằm gọn trong phim thì không được sửa mốc"


def test_normalize_cắt_phần_chồng_lấn_một_phần():
    """Đoạn sau nhường đoạn trước, không thì một giây bị đổi tốc độ hai lần."""
    ra = normalize([Speed(0, 5, 2.0), Speed(3, 8, 3.0)], 100.0)
    assert [(s.start, s.end, s.factor) for s in ra] == [(0.0, 5, 2.0), (5, 8, 3.0)], \
        "đoạn sau phải bị đẩy đầu về 5 để không chồng lên đoạn trước"
    assert lien_tuc([(s.start, s.end) for s in ra]), "sau khi cắt phải nối đuôi nhau"


def test_normalize_chồng_lấn_hoàn_toàn_thì_bỏ_đoạn_trong():
    ra = normalize([Speed(0, 10, 2.0), Speed(2, 3, 3.0)], 100.0)
    assert len(ra) == 1, "đoạn nằm lọt thỏm bên trong đoạn khác phải bị bỏ hẳn"
    assert (ra[0].start, ra[0].end) == (0.0, 10)


def test_normalize_ba_đoạn_chồng_lấn_dây_chuyền():
    ra = normalize([Speed(0, 6, 2.0), Speed(2, 8, 3.0), Speed(4, 10, 4.0)], 100.0)
    assert [(s.start, s.end) for s in ra] == [(0.0, 6), (6, 8), (8, 10)], \
        "chồng lấn dây chuyền phải cắt lần lượt, không được bỏ sót đoạn"


def test_normalize_kẹp_vào_khoảng_phim():
    ra = normalize([Speed(-5, 3, 2.0), Speed(50, 500, 3.0)], 100.0)
    assert (ra[0].start, ra[0].end) == (0.0, 3), "đầu âm phải kẹp về 0"
    assert (ra[1].start, ra[1].end) == (50, 100.0), "đuôi vượt phim phải kẹp về duration"


def test_normalize_đoạn_nằm_hẳn_ngoài_phim_bị_bỏ():
    assert normalize([Speed(200, 300, 2.0)], 100.0) == [], \
        "đoạn nằm sau khi phim đã hết thì không còn gì để đổi tốc độ"


@pytest.mark.parametrize("he_so", [0.0, -1.0, -0.5], ids=["0", "-1", "-0.5"])
def test_normalize_loại_hệ_số_không_dương(he_so):
    """Hệ số <= 0 vô nghĩa, và để lọt xuống atempo_chain là treo app (BUG-1)."""
    assert normalize([Speed(0, 5, he_so)], 100.0) == [], \
        f"hệ số {he_so} phải bị loại ngay từ normalize"


def test_normalize_loại_đoạn_ngắn_hơn_0_05s():
    assert normalize([Speed(1.0, 1.04, 2.0)], 100.0) == [], \
        "đoạn 0.04s ngắn hơn ngưỡng 0.05s, giữ lại chỉ tổ đẻ ra mắt xích rác"


def test_normalize_khoảng_dài_bằng_0_bị_bỏ():
    assert normalize([Speed(5.0, 5.0, 2.0)], 100.0) == [], \
        "khoảng dài 0 giây không phải là đoạn"


def test_normalize_duration_bằng_0_thì_không_còn_đoạn_nào():
    assert normalize([Speed(0, 50, 2.0)], 0.0) == [], \
        "phim dài 0 giây thì mọi đoạn đều bị kẹp về rỗng"


def test_normalize_tự_sắp_xếp_theo_thời_gian():
    ra = normalize([Speed(6, 8, 3.0), Speed(1, 2, 2.0)], 100.0)
    assert [s.start for s in ra] == [1, 6], "kết quả phải được sắp theo mốc bắt đầu"


def test_normalize_không_sửa_danh_sách_gốc():
    goc = [Speed(0, 5, 2.0), Speed(3, 8, 3.0)]
    chup = [(s.start, s.end, s.factor) for s in goc]
    normalize(goc, 100.0)
    assert [(s.start, s.end, s.factor) for s in goc] == chup, \
        "normalize phải trả về danh sách mới, không được sửa đầu vào"


# =================================================================== timeline


def test_timeline_không_có_đoạn_nào_thì_phủ_kín_bằng_hệ_số_1():
    assert timeline([], 100.0) == [(0.0, 100.0, 1.0)], \
        "phim không đổi tốc độ vẫn phải có đúng một đoạn phủ kín"


def test_timeline_duration_bằng_0_vẫn_trả_về_đoạn_hợp_lệ():
    segs = timeline([], 0.0)
    assert len(segs) == 1 and segs[0][2] == 1.0, \
        "duration 0 vẫn phải trả về một đoạn, không được trả danh sách rỗng"
    assert segs[0][1] > segs[0][0], "đoạn trả về phải có độ dài dương"


def test_timeline_chèn_đoạn_hệ_số_1_vào_chỗ_trống():
    segs = timeline([Speed(3, 5, 2.0)], 10.0)
    assert segs == [(0.0, 3, 1.0), (3, 5, 2.0), (5, 10.0, 1.0)], \
        "khoảng không đặt tốc độ phải được lấp bằng hệ số 1.0"


def test_timeline_đoạn_phủ_hết_phim_thì_chỉ_một_đoạn():
    assert timeline([Speed(0, 10, 2.0)], 10.0) == [(0.0, 10, 2.0)], \
        "đặt tốc độ cho cả phim thì không cần thêm đoạn đệm nào"


def test_timeline_các_đoạn_nối_đuôi_nhau_và_phủ_kín():
    segs = timeline([Speed(2, 4, 2.0), Speed(6, 7, 0.5)], 10.0)
    assert lien_tuc(segs), f"các đoạn phải nối đuôi nhau, không hở không chồng: {segs}"
    assert segs[0][0] == 0.0, "đoạn đầu phải bắt đầu từ giây 0"
    assert segs[-1][1] == pytest.approx(10.0), "đoạn cuối phải kết thúc đúng cuối phim"
    assert sum(b - a for a, b, _f in segs) == pytest.approx(10.0), \
        "tổng độ dài các đoạn (thời gian gốc) phải bằng đúng thời lượng phim"


def test_timeline_nhiều_đoạn_liền_kề_không_sinh_đoạn_rỗng():
    segs = timeline([Speed(0, 5, 2.0), Speed(5, 10, 3.0)], 10.0)
    assert segs == [(0.0, 5, 2.0), (5, 10, 3.0)], \
        "hai đoạn sát nhau không được sinh thêm đoạn đệm dài 0 giây"


@pytest.mark.bug
def test_timeline_phủ_kín_cả_khi_khe_hở_nhỏ_hơn_0_01s():
    """Docstring của timeline hứa 'phủ kín [0, duration]' — ở đây thì không.

    Ngưỡng 0.01 làm 5 mili giây đầu phim biến mất khỏi bảng thời gian, kéo theo
    build_speed_video cắt thiếu đúng chừng ấy.
    """
    segs = timeline([Speed(0.005, 10, 2.0)], 10.0)
    assert segs[0][0] == 0.0, f"phải phủ từ giây 0, nhận đoạn đầu bắt đầu ở {segs[0][0]}"


# ============================================================ map_time / dur


def test_map_time_không_đổi_tốc_độ_thì_giữ_nguyên():
    segs = timeline([], 10.0)
    for t in (0.0, 3.3, 10.0):
        assert map_time(t, segs) == pytest.approx(t), \
            f"hệ số 1.0 thì giây {t} phải ánh xạ về chính nó"


def test_map_time_trước_và_sau_đoạn_đổi_tốc_độ():
    segs = timeline([Speed(2, 4, 2.0)], 10.0)      # 2 giây chạy nhanh gấp đôi
    assert map_time(2.0, segs) == pytest.approx(2.0), "trước đoạn nhanh thì chưa dồn"
    assert map_time(3.0, segs) == pytest.approx(2.5), "giữa đoạn nhanh thì đi được nửa"
    assert map_time(4.0, segs) == pytest.approx(3.0), "hết đoạn nhanh thì rút được 1 giây"
    assert map_time(10.0, segs) == pytest.approx(9.0), "phần đuôi giữ nguyên tốc độ"


def test_map_time_thời_điểm_âm_và_vượt_phim():
    segs = timeline([Speed(2, 4, 2.0)], 10.0)
    assert map_time(-5.0, segs) == 0.0, "thời điểm âm phải kẹp về 0"
    assert map_time(999.0, segs) == pytest.approx(out_duration(segs)), \
        "quá cuối phim thì kẹp về đúng thời lượng bản đã đổi tốc độ"


def test_map_time_đơn_điệu_không_giảm():
    segs = timeline([Speed(1, 3, 4.0), Speed(5, 6, 0.5)], 10.0)
    truoc = -1.0
    for i in range(0, 101):
        t = i / 10.0
        gio = map_time(t, segs)
        assert gio >= truoc - 1e-9, f"map_time phải không giảm, tụt ở giây {t}"
        truoc = gio


def test_map_time_danh_sách_đoạn_rỗng():
    assert map_time(5.0, []) == 0.0, "không có đoạn nào thì mọi thời điểm đều là 0"


def test_out_duration_theo_hệ_số():
    assert out_duration(timeline([], 10.0)) == pytest.approx(10.0)
    assert out_duration(timeline([Speed(0, 10, 2.0)], 10.0)) == pytest.approx(5.0), \
        "chạy nhanh gấp đôi thì phim còn nửa thời lượng"
    assert out_duration(timeline([Speed(0, 10, 0.5)], 10.0)) == pytest.approx(20.0), \
        "chạy chậm một nửa thì phim dài gấp đôi"


def test_out_duration_danh_sách_rỗng_bằng_0():
    assert out_duration([]) == 0, "không có đoạn nào thì thời lượng ra bằng 0"


def test_has_speed():
    assert not has_speed(timeline([], 10.0)), "toàn hệ số 1.0 nghĩa là không đổi tốc độ"
    assert has_speed(timeline([Speed(0, 5, 2.0)], 10.0)), "có đoạn 2× thì phải báo có"
    assert not has_speed([(0.0, 5.0, 1.0005)]), \
        "lệch dưới 1e-3 coi như không đổi, tránh dựng filter thừa"


# ================================================================ remap_cues


def test_remap_cues_co_giãn_theo_bảng_thời_gian():
    segs = timeline([Speed(2, 4, 2.0)], 10.0)
    ra = remap_cues([Cue(0, 1, "A"), Cue(2, 4, "B"), Cue(5, 6, "C")], segs)
    assert bo_ba(ra) == [(0.0, 1.0, "A"), (2.0, 3.0, "B"), (4.0, 5.0, "C")], \
        "câu nằm trong đoạn 2× phải ngắn lại một nửa, câu sau phải dồn lên"


def test_remap_cues_giữ_nguyên_số_câu_và_nội_dung():
    segs = timeline([Speed(0, 10, 3.0)], 10.0)
    goc = [Cue(0, 1, "một"), Cue(2, 3, "hai"), Cue(4, 5, "ba")]
    ra = remap_cues(goc, segs)
    assert len(ra) == 3, "remap_cues không biết nhát cắt nên không được bỏ câu nào"
    assert [c.text for c in ra] == ["một", "hai", "ba"], "nội dung phải giữ nguyên"


def test_remap_cues_kéo_dài_câu_quá_ngắn_lên_0_08s():
    segs = timeline([Speed(0, 10, 10.0)], 10.0)
    ra = remap_cues([Cue(0, 0.1, "chớp")], segs)
    assert ra[0].end - ra[0].start == pytest.approx(0.08), \
        "câu bị nén ngắn hơn 0.08s phải được kéo lên 0.08s cho kịp đọc"


def test_remap_cues_áp_offset_trước_khi_ánh_xạ():
    segs = timeline([], 10.0)
    ra = remap_cues([Cue(1, 2, "A")], segs, offset=1.5)
    assert bo_ba(ra) == [(2.5, 3.5, "A")], "offset dương đẩy câu ra sau đúng chừng ấy"


def test_remap_cues_danh_sách_rỗng():
    assert remap_cues([], timeline([], 10.0)) == [], "không có câu nào thì trả về rỗng"


# ============================================================= expand_preset


def test_expand_preset_đều_chỉ_một_đoạn():
    ra = expand_preset(0.0, 10.0, "Đều")
    assert len(ra) == 1 and ra[0].factor == 1.0, "preset 'Đều' không cần chia nhỏ"


def test_expand_preset_chia_đều_và_phủ_kín_khoảng_chọn():
    ra = expand_preset(0.0, 4.0, "Nhanh dần")
    assert len(ra) == len(CURVE_PRESETS["Nhanh dần"]), "phải đủ số đoạn của preset"
    assert ra[0].start == 0.0 and ra[-1].end == pytest.approx(4.0), \
        "chuỗi đoạn phải phủ đúng khoảng đã chọn"
    assert lien_tuc([(s.start, s.end) for s in ra]), "các đoạn nhỏ phải nối đuôi nhau"
    assert [s.factor for s in ra] == CURVE_PRESETS["Nhanh dần"], \
        "hệ số từng đoạn phải đúng thứ tự trong preset"


def test_expand_preset_tên_lạ_thì_về_hệ_số_1():
    ra = expand_preset(0.0, 4.0, "Không có preset này")
    assert len(ra) == 1 and ra[0].factor == 1.0, \
        "preset không biết thì giữ nguyên tốc độ, không được nổ"


def test_speed_label_hiển_thị_gọn():
    assert Speed(1.0, 2.5, 2.0).label == "2×  1.0–2.5s", \
        "nhãn hiện cho người dùng phải gọn và có ký hiệu ×"


# ============================================================== sync_filter


def test_sync_filter_lệch_không_đáng_kể_thì_không_dựng_filter():
    assert sync_filter(0.0) == "", "lệch 0 giây thì đừng thêm mắt xích vô ích"
    assert sync_filter(0.004) == "", "lệch dưới 5ms coi như khớp"


def test_sync_filter_đọc_muộn_hơn_thì_adelay():
    assert sync_filter(0.5) == "adelay=500:all=1", \
        "offset dương nghĩa là chèn im lặng ở đầu track thuyết minh"


def test_sync_filter_đọc_sớm_hơn_thì_cắt_đầu():
    assert sync_filter(-0.5).startswith("atrim=start=0.500"), \
        "offset âm nghĩa là cắt bớt đầu track thuyết minh"


# ================================================ dựng chuỗi filter tốc độ


def test_build_speed_không_đổi_tốc_độ_thì_không_dựng_gì():
    segs = timeline([], 10.0)
    assert build_speed_video(segs, "0:v") == ([], "0:v"), \
        "không đổi tốc độ thì trả thẳng luồng vào, khỏi trim/setpts vô ích"
    assert build_speed_audio(segs, "0:a") == ([], "0:a")


def test_build_speed_video_nhãn_không_được_trùng():
    """Trùng nhãn thì ffmpeg từ chối chạy — bẫy đã ghi trong CLAUDE.md."""
    from _hotro import nhan_trung
    segs = timeline([Speed(2, 4, 2.0), Speed(6, 8, 0.4)], 10.0)
    parts, ra = build_speed_video(segs, "0:v")
    assert nhan_trung(parts) == [], f"chuỗi video có nhãn trùng: {nhan_trung(parts)}"
    assert ra == "svout", "nhãn ra phải đúng quy ước để mắt xích sau nối vào"


def test_build_speed_audio_dùng_tiền_tố_khác_chuỗi_video():
    from _hotro import nhan_ra, nhan_trung
    segs = timeline([Speed(2, 4, 2.0)], 10.0)
    vparts, _v = build_speed_video(segs, "0:v")
    aparts, _a = build_speed_audio(segs, "0:a")
    assert nhan_trung(aparts) == [], "chuỗi tiếng có nhãn trùng"
    assert set(nhan_ra(vparts)) & set(nhan_ra(aparts)) == set(), \
        "chuỗi tiếng và chuỗi hình không được dùng chung nhãn nào"


def test_build_speed_audio_nối_chuỗi_atempo_cho_hệ_số_nhỏ():
    segs = timeline([Speed(0, 10, 0.25)], 10.0)
    parts, _ = build_speed_audio(segs, "0:a")
    day = [p for p in parts if "atempo" in p]
    assert day and day[0].count("atempo") >= 2, \
        "hệ số 0.25 phải sinh chuỗi atempo nhiều mắt xích trong filter tiếng"
