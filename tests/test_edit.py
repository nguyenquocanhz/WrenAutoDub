# -*- coding: utf-8 -*-
"""Test cho wrenautodub/edit.py — mô hình dự án, lưu/mở, ước tính, undo/redo.

Không đụng tới Qt: mọi thứ ở đây đều là dữ liệu thuần và chuỗi filter.
"""

from __future__ import annotations

import json

import pytest

from _hotro import nhan_trung
from wrenautodub.clips import Clip
from wrenautodub.edit import (AUDIO_KBPS, BITRATE, BLUR, DELOGO, LOGO, QUALITY,
                              ExportSettings, History, Project, Region,
                              build_full_graph, build_video_chain, human_size,
                              needs_reencode)
from wrenautodub.timing import Speed


def du_an_day_du() -> Project:
    """Một dự án dùng đủ mọi tính năng — để soi vòng tròn lưu/mở."""
    return Project(
        video=r"D:\phim\a.mkv", srt=r"D:\phim\a.srt", dub=r"D:\phim\dub.wav",
        width=1920, height=1080, duration=120.0,
        regions=[Region(kind=BLUR, x=.1, y=.2, w=.3, h=.4, start=1, end=2),
                 Region(kind=DELOGO, x=.5, strength=20),
                 Region(kind=LOGO, path=r"D:\logo.png", opacity=0.5)],
        speeds=[Speed(10, 20, 2.0), Speed(30, 40, 0.5)],
        clips=[Clip(0, 50, 0), Clip(60, 120, 50)],
        dub_clips=[Clip(0, 30, 0)],
        ripple=True, fps=30.0, sync_offset=0.4,
        export=ExportSettings(height=720, quality="cao", encoder="nvenc",
                              container=".mp4", keep_orig_audio=False, hardsub=True))


# ============================================================ Region.px


def test_region_px_ép_số_chẵn():
    """Nhiều filter của ffmpeg từ chối toạ độ/kích thước lẻ."""
    x, y, w, h = Region(x=.1, y=.1, w=.2, h=.12).px(1920, 1080)
    for ten, v in zip("xywh", (x, y, w, h)):
        assert v % 2 == 0, f"{ten}={v} phải là số chẵn"


def test_region_px_đổi_tỉ_lệ_sang_pixel_đúng():
    assert Region(x=.5, y=.5, w=.25, h=.25).px(1920, 1080)[:2] == (960, 540), \
        "tỉ lệ 0.5 của khung 1920×1080 phải ra đúng giữa khung"


def test_region_px_không_tràn_khỏi_khung_hình():
    x, y, w, h = Region(x=.9, y=.9, w=.5, h=.5).px(1920, 1080)
    assert x + w <= 1920, "vùng không được lòi ra ngoài chiều rộng khung"
    assert y + h <= 1080, "vùng không được lòi ra ngoài chiều cao khung"


def test_region_px_kích_thước_tối_thiểu_2_pixel():
    _x, _y, w, h = Region(x=.0, y=.0, w=.0001, h=.0001).px(1920, 1080)
    assert w >= 2 and h >= 2, "vùng bé tí vẫn phải ít nhất 2×2 để filter không nổ"


def test_region_px_theo_độ_phân_giải_khác_nhau():
    """Toạ độ lưu theo tỉ lệ nên đổi độ phân giải xuất không được lệch vùng."""
    r = Region(x=.25, y=.25, w=.5, h=.5)
    x1, _y1, w1, _h1 = r.px(1920, 1080)
    x2, _y2, w2, _h2 = r.px(3840, 2160)
    assert (x2, w2) == (x1 * 2, w1 * 2), "gấp đôi khung thì toạ độ và bề rộng gấp đôi"


def test_region_label():
    assert Region(kind=BLUR).label == "Làm mờ", "không đặt khoảng thì nhãn chỉ có tên"
    assert Region(kind=DELOGO, start=1, end=2).label == "Xoá logo  1–2s", \
        "có khoảng thời gian thì nhãn phải hiện kèm"
    assert Region(kind=LOGO, path=r"D:\a\logo.png").label == "Chèn logo  logo.png", \
        "logo hiện tên file, không hiện cả đường dẫn"


# ================================================ to_dict / from_dict vòng tròn


def test_to_dict_from_dict_vòng_tròn_khép_kín():
    p = du_an_day_du()
    d = p.to_dict()
    assert Project.from_dict(d).to_dict() == d, \
        "dựng lại dự án từ dict rồi đổ ra dict phải giống hệt ban đầu"


def test_vòng_tròn_qua_JSON():
    d = du_an_day_du().to_dict()
    assert Project.from_dict(json.loads(json.dumps(d, ensure_ascii=False))).to_dict() == d, \
        "đi một vòng qua JSON (như khi lưu file) cũng không được rơi rớt gì"


def test_from_dict_dựng_lại_đúng_kiểu_dữ_liệu():
    p = Project.from_dict(du_an_day_du().to_dict())
    assert isinstance(p.regions[0], Region), "vùng phải là Region chứ không phải dict"
    assert isinstance(p.speeds[0], Speed), "đoạn tốc độ phải là Speed"
    assert isinstance(p.clips[0], Clip), "clip phải là Clip"
    assert isinstance(p.dub_clips[0], Clip), "clip thuyết minh phải là Clip"
    assert isinstance(p.export, ExportSettings), "thiết lập xuất phải là ExportSettings"


def test_from_dict_giữ_đúng_giá_trị():
    p = Project.from_dict(du_an_day_du().to_dict())
    assert p.duration == 120.0 and p.fps == 30.0 and p.sync_offset == 0.4, \
        "các số vô hướng phải giữ nguyên"
    assert p.export.hardsub is True and p.export.keep_orig_audio is False, \
        "cờ bật/tắt phải giữ nguyên, không được đảo"
    assert p.regions[2].path == r"D:\logo.png", \
        "đường dẫn Windows có dấu \\ phải giữ nguyên qua JSON"


def test_to_dict_ra_kiểu_thuần_json():
    d = du_an_day_du().to_dict()
    json.dumps(d)          # nổ ở đây nghĩa là còn sót dataclass
    assert isinstance(d["regions"][0], dict), "vùng phải đổ thành dict để ghi JSON"
    assert isinstance(d["export"], dict), "thiết lập xuất phải đổ thành dict"


def test_from_dict_dict_rỗng_ra_dự_án_mặc_định():
    assert Project.from_dict({}).to_dict() == Project().to_dict(), \
        "dict rỗng phải ra dự án mặc định chứ không nổ"


def test_from_dict_thiếu_khoá_thì_lấy_mặc_định():
    """File dự án của bản cũ thiếu khoá mới — vẫn phải mở được."""
    p = Project.from_dict({"video": "x.mkv", "duration": 10.0})
    assert p.video == "x.mkv" and p.duration == 10.0, "khoá có thì lấy"
    assert p.ripple is True and p.fps == 25.0, "khoá thiếu thì lấy giá trị mặc định"


def test_from_dict_bỏ_qua_khoá_lạ():
    assert Project.from_dict({"khoa_khong_ton_tai": 1}).to_dict() == Project().to_dict(), \
        "khoá lạ trong file dự án không được làm hỏng việc mở"


def test_from_dict_danh_sách_rỗng():
    p = Project.from_dict({"regions": [], "speeds": [], "clips": [], "dub_clips": []})
    assert p.regions == [] and p.speeds == [] and p.clips == [] and p.dub_clips == [], \
        "danh sách rỗng phải giữ nguyên là rỗng"


@pytest.mark.bug
def test_from_dict_không_được_ghi_đè_phương_thức():
    """`hasattr(p, k)` đúng cả với tên phương thức, nên setattr đè mất hàm.

    File dự án hỏng/bịa có khoá "items" là từ đó `proj.items()` nổ TypeError ở
    tận lúc xuất bản, rất khó lần ra nguyên nhân.
    """
    p = Project.from_dict({"items": 123})
    assert callable(p.items), "phương thức items() không được bị dữ liệu đè lên"


# =============================================================== save / load


def test_save_load_vòng_tròn(tmp_path):
    p = du_an_day_du()
    f = tmp_path / "duan.json"
    p.save(f)
    assert Project.load(f).to_dict() == p.to_dict(), \
        "lưu ra file rồi mở lại phải được đúng dự án cũ"


def test_save_ghi_tiếng_việt_không_thoát_unicode(tmp_path):
    f = tmp_path / "vn.json"
    Project(video="phim tiếng Việt.mkv").save(f)
    assert "tiếng Việt" in f.read_text(encoding="utf-8"), \
        "file dự án phải đọc được bằng mắt, không được thoát thành \\uXXXX"


def test_load_file_không_tồn_tại(tmp_path):
    assert Project.load(tmp_path / "khong_co.json") is None, \
        "mở file không tồn tại trả None chứ không nổ"


def test_load_file_hỏng(tmp_path):
    f = tmp_path / "hong.json"
    f.write_text("{ đây không phải json", encoding="utf-8")
    assert Project.load(f) is None, "file JSON hỏng trả None chứ không nổ"


# ========================================================== final_duration


@pytest.mark.parametrize("kw,mong_doi,vi_sao", [
    ({}, 100.0, "chưa cắt chưa đổi tốc độ thì giữ nguyên thời lượng"),
    ({"speeds": [Speed(0, 100, 2.0)]}, 50.0, "cả phim 2× thì còn một nửa"),
    ({"speeds": [Speed(0, 100, 0.5)]}, 200.0, "cả phim 0.5× thì dài gấp đôi"),
    ({"speeds": [Speed(0, 50, 2.0)]}, 75.0, "nửa đầu 2× thì rút được 25 giây"),
    ({"speeds": [Speed(0, 50, 2.0), Speed(50, 100, 4.0)]}, 37.5,
     "hai đoạn tốc độ khác nhau cộng dồn"),
    ({"clips": [Clip(0, 50, 0)]}, 50.0, "cắt còn 50 giây"),
    ({"clips": [Clip(0, 25, 0), Clip(50, 75, 25)]}, 50.0, "giữ hai đoạn 25 giây"),
    ({"clips": [Clip(0, 50, 0)], "speeds": [Speed(0, 100, 2.0)]}, 25.0,
     "cắt còn 50 giây rồi chạy 2× thì còn 25"),
    ({"clips": [Clip(0, 25, 0), Clip(50, 75, 25)], "speeds": [Speed(0, 100, 2.0)]}, 25.0,
     "hai đoạn 25 giây chạy 2× thì còn 25"),
    ({"clips": [Clip(0, 25, 0), Clip(50, 75, 40)], "ripple": False}, 65.0,
     "chế độ rời rạc phải tính cả 15 giây màn đen"),
    ({"clips": [Clip(0, 50, 0, enabled=False)]}, 100.0,
     "tắt hết clip thì rơi về mặc định phủ cả phim"),
], ids=["tron", "2x", "0.5x", "nua-dau-2x", "hai-doan-toc-do", "cat-50",
        "hai-doan", "cat+2x", "hai-doan+2x", "roi-rac", "tat-het-clip"])
def test_final_duration_các_tổ_hợp_clip_và_tốc_độ(kw, mong_doi, vi_sao):
    p = Project(duration=100.0, **kw)
    assert p.final_duration() == pytest.approx(mong_doi), vi_sao


def test_final_duration_phim_dài_0_giây():
    assert Project(duration=0.0).final_duration() >= 0.0, \
        "phim dài 0 giây không được cho ra số âm"


def test_segments_và_live_clips_luôn_dùng_được():
    p = Project(duration=100.0)
    assert p.segments(), "bảng thời gian không bao giờ được rỗng"
    assert p.live_clips(), "danh sách clip sống không bao giờ được rỗng"


def test_dub_items_dùng_chung_với_hình_khi_chưa_tách():
    p = Project(duration=100.0, clips=[Clip(0, 50, 0)])
    assert p.audio_detached() is False, "chưa cắt riêng thì track tiếng không tách"
    assert p.dub_items() == p.items(), \
        "chưa tách thì track thuyết minh phải cắt y hệt hình"


def test_dub_items_riêng_khi_đã_tách():
    p = Project(duration=100.0, clips=[Clip(0, 50, 0)], dub_clips=[Clip(0, 30, 0)])
    assert p.audio_detached() is True, "có dub_clips nghĩa là đã tách"
    assert p.dub_items() != p.items(), "đã tách thì hai bên có nhát cắt riêng"
    assert p.dub_items() == [("src", 0, 30, 1.0)], "track tiếng phải theo dub_clips"


# ================================================== est_bytes / target_kbps


def test_out_height_ưu_tiên_thiết_lập_xuất():
    assert Project(height=1080, export=ExportSettings(height=720)).out_height() == 720, \
        "đặt chiều cao xuất thì lấy số đó"
    assert Project(height=1080).out_height() == 1080, "không đặt thì giữ nguyên phim gốc"
    assert Project().out_height() == 1080, "không biết gì thì mặc định 1080"


@pytest.mark.parametrize("cao,kbps", [(480, 1200), (720, 2500), (1080, 4500),
                                      (1440, 8000), (2160, 14000)],
                         ids=["480", "720", "1080", "1440", "2160"])
def test_target_kbps_theo_chiều_cao(cao, kbps):
    p = Project(height=cao, export=ExportSettings(quality="vừa"))
    assert p.target_kbps() == kbps, f"{cao}p ở mức 'vừa' phải là {kbps} kbps"


def test_target_kbps_chọn_mức_gần_nhất():
    assert Project(height=1000).target_kbps() == BITRATE[1080], \
        "1000p không có trong bảng thì lấy mức gần nhất (1080)"
    assert Project(height=99999).target_kbps() == BITRATE[2160], \
        "chiều cao lạ quá thì kẹp về mức cao nhất"


@pytest.mark.parametrize("muc", list(QUALITY), ids=list(QUALITY))
def test_target_kbps_theo_mức_chất_lượng(muc):
    p = Project(height=1080, export=ExportSettings(quality=muc))
    assert p.target_kbps() == int(BITRATE[1080] * QUALITY[muc]), \
        f"mức '{muc}' phải nhân đúng hệ số {QUALITY[muc]}"


def test_target_kbps_mức_lạ_thì_về_hệ_số_1():
    p = Project(height=1080, export=ExportSettings(quality="không có mức này"))
    assert p.target_kbps() == BITRATE[1080], "mức lạ thì coi như hệ số 1.0, không nổ"


def test_est_bytes_công_thức_bitrate():
    p = Project(duration=100.0, height=1080)
    mong_doi = int((4500 + AUDIO_KBPS * 2) * 1000 / 8 * 100)
    assert p.est_bytes() == mong_doi, \
        "ước tính = (bitrate hình + tiếng) × thời lượng, giữ đúng 2 track tiếng"


def test_est_bytes_bỏ_tiếng_gốc_thì_nhẹ_hơn():
    a = Project(duration=100.0, height=1080).est_bytes()
    b = Project(duration=100.0, height=1080,
                export=ExportSettings(keep_orig_audio=False)).est_bytes()
    assert b < a, "bỏ tiếng gốc thì file phải nhỏ hơn"
    assert a - b == int(AUDIO_KBPS * 1000 / 8 * 100), "chênh đúng một track tiếng"


def test_est_bytes_tỉ_lệ_với_thời_lượng():
    a = Project(duration=100.0, height=1080).est_bytes()
    b = Project(duration=200.0, height=1080).est_bytes()
    assert b == pytest.approx(a * 2, rel=1e-6), "phim dài gấp đôi thì nặng gấp đôi"


def test_est_bytes_giảm_khi_cắt_clip():
    day = Project(duration=100.0, height=1080)
    cat = Project(duration=100.0, height=1080, clips=[Clip(0, 50, 0)])
    assert cat.est_bytes() < day.est_bytes(), \
        "cắt còn nửa phim thì ước tính phải giảm theo"


def test_est_bytes_phim_rỗng_vẫn_dương():
    assert Project(duration=0.0, height=1080).est_bytes() > 0, \
        "thời lượng 0 vẫn kẹp về 1 giây để con số không thành 0"


@pytest.mark.parametrize("n,chu", [(0, "0 MB"), (5 * 2**20, "5 MB"),
                                   (2**30, "1.00 GB"), (3 * 2**30, "3.00 GB")],
                         ids=["0", "5MB", "1GB", "3GB"])
def test_human_size(n, chu):
    assert human_size(n) == chu, f"{n} byte phải hiện là {chu}"


# ============================================================ needs_reencode


@pytest.mark.parametrize("kw,vi_sao", [
    ({"regions": [Region()]}, "có vùng hiệu ứng thì buộc phải encode lại"),
    ({"speeds": [Speed(0, 5, 2.0)], "duration": 10.0}, "đổi tốc độ thì phải encode lại"),
    ({"sync_offset": 0.5}, "dời tiếng thì phải encode lại"),
    ({"export": ExportSettings(hardsub=True)}, "nung phụ đề thì phải encode lại"),
    ({"export": ExportSettings(height=720)}, "đổi cỡ khung thì phải encode lại"),
], ids=["vung", "toc-do", "sync", "hardsub", "doi-co"])
def test_needs_reencode_bật_khi_có_thay_đổi(kw, vi_sao):
    assert needs_reencode(Project(height=1080, **kw)) is True, vi_sao


def test_needs_reencode_dự_án_trắng_thì_không_cần():
    assert needs_reencode(Project(height=1080)) is False, \
        "không đụng gì vào phim thì chép luồng là đủ"


def test_needs_reencode_bỏ_qua_vùng_đã_tắt():
    assert needs_reencode(Project(height=1080, regions=[Region(enabled=False)])) is False, \
        "vùng đã tắt không sinh filter nào nên không cần encode lại"


@pytest.mark.bug
def test_needs_reencode_bật_khi_có_nhát_cắt_clip():
    """Cắt clip đổi hẳn nội dung phim mà hàm này lại bảo không cần encode lại.

    Hiện chưa hàm nào gọi tới nên chưa hỏng thật, nhưng ai nối nó vào nhánh
    "chép luồng cho nhanh" là bản xuất ra mất sạch nhát cắt.
    """
    p = Project(height=1080, duration=100.0, clips=[Clip(0, 50, 0)])
    assert needs_reencode(p) is True, \
        "dự án đã cắt bỏ nửa phim thì không thể chép luồng nguyên xi được"


# ================================================================== History


def test_history_ban_đầu_chưa_có_gì_để_hoàn_tác():
    h = History(Project(duration=1.0))
    assert h.can_undo() is False and h.can_redo() is False, \
        "vừa mở dự án thì chưa có thao tác nào để hoàn tác"


def test_history_hoàn_tác_và_làm_lại():
    p = Project(duration=1.0)
    h = History(p)
    p.video = "a.mkv"
    h.push(p)
    assert h.can_undo() is True, "sau một thay đổi thì hoàn tác được"

    truoc = h.undo()
    assert truoc.video == "", "hoàn tác phải quay về trạng thái trước đó"
    assert h.can_redo() is True, "hoàn tác xong thì làm lại được"

    sau = h.redo()
    assert sau.video == "a.mkv", "làm lại phải quay về trạng thái sau"


def test_history_bỏ_qua_ảnh_chụp_trùng():
    p = Project(duration=1.0)
    h = History(p)
    h.push(p)
    assert h.can_undo() is False, \
        "chụp lại y hệt trạng thái cũ thì đừng làm bẩn ngăn xếp hoàn tác"


def test_history_thao_tác_mới_xoá_nhánh_làm_lại():
    p = Project(duration=1.0)
    h = History(p)
    p.video = "a.mkv"
    h.push(p)
    h.undo()
    assert h.can_redo() is True
    p2 = Project(duration=1.0, video="b.mkv")
    h.push(p2)
    assert h.can_redo() is False, \
        "làm việc khác sau khi hoàn tác thì nhánh làm lại cũ phải bị xoá"


def test_history_không_hoàn_tác_quá_đáy():
    h = History(Project(duration=1.0))
    assert h.undo() is None, "không còn gì để hoàn tác thì trả None"
    assert h.redo() is None, "không có gì để làm lại thì trả None"


def test_history_giới_hạn_số_ảnh_chụp():
    h = History(Project(duration=1.0), limit=3)
    for i in range(5):
        p = Project(duration=1.0, video=f"{i}.mkv")
        h.push(p)
    dem = 0
    while h.can_undo():
        h.undo()
        dem += 1
    assert dem == 2, "giới hạn 3 ảnh chụp thì chỉ lùi được 2 bước"


def test_history_ảnh_chụp_độc_lập_với_dự_án_đang_sửa():
    p = Project(duration=1.0, video="a.mkv", regions=[Region()])
    h = History(p)
    p.regions[0].x = 0.99          # sửa tại chỗ sau khi đã chụp
    p.video = "b.mkv"
    h.push(p)
    cu = h.undo()
    assert cu.regions[0].x != 0.99, \
        "ảnh chụp phải là bản sao sâu, sửa dự án không được đổi lịch sử"


# ======================================================= dựng chuỗi filter


def test_build_video_chain_dự_án_trắng_không_dựng_gì():
    chain, extra, cur = build_video_chain(Project(height=1080), 1920, 1080)
    assert chain == "" and extra == [] and cur == "0:v", \
        "không có hiệu ứng nào thì không dựng mắt xích nào"


def test_build_video_chain_nhãn_không_được_trùng():
    """Trùng nhãn thì ffmpeg từ chối chạy — bẫy đã ghi trong CLAUDE.md."""
    p = Project(width=1920, height=1080,
                regions=[Region(kind=DELOGO), Region(kind=BLUR),
                         Region(kind=BLUR, x=.5), Region(kind=LOGO, path="l.png")],
                export=ExportSettings(height=720))
    chain, _extra, _cur = build_video_chain(p, 1920, 1080, srt_escaped="C\\:/a.srt")
    assert nhan_trung(chain.split(";")) == [], \
        f"nhãn trùng trong chuỗi video: {nhan_trung(chain.split(';'))}"


def test_build_video_chain_logo_thành_input_phụ():
    p = Project(width=1920, height=1080,
                regions=[Region(kind=LOGO, path="a.png"), Region(kind=LOGO, path="b.png")])
    chain, extra, _cur = build_video_chain(p, 1920, 1080, logo_base=2)
    assert extra == ["a.png", "b.png"], "mỗi logo phải thành một input phụ, đúng thứ tự"
    assert "[2:v]" in chain and "[3:v]" in chain, \
        "chỉ số input của logo phải đếm tiếp từ logo_base"


def test_build_video_chain_logo_base_đổi_theo_ngữ_cảnh():
    """Xem trước một khung hình không nạp audio nên logo bắt đầu từ input 1."""
    p = Project(width=1920, height=1080, regions=[Region(kind=LOGO, path="a.png")])
    chain, _extra, _cur = build_video_chain(p, 1920, 1080, logo_base=1)
    assert "[1:v]" in chain, "logo_base=1 thì logo phải là input số 1"


def test_build_video_chain_vùng_có_khoảng_thời_gian_thì_dùng_enable():
    p = Project(width=1920, height=1080, regions=[Region(kind=BLUR, start=1.0, end=2.0)])
    chain, _e, _c = build_video_chain(p, 1920, 1080)
    assert "enable='between(t,1.000,2.000)'" in chain, \
        "vùng chỉ hiệu lực trong một khoảng phải kèm enable=between"


def test_build_video_chain_vùng_suốt_phim_thì_không_enable():
    p = Project(width=1920, height=1080, regions=[Region(kind=BLUR)])
    chain, _e, _c = build_video_chain(p, 1920, 1080)
    assert "enable=" not in chain, "vùng suốt phim thì đừng thêm enable cho rối"


def test_build_video_chain_bỏ_qua_vùng_đã_tắt():
    p = Project(width=1920, height=1080, regions=[Region(kind=BLUR, enabled=False)])
    chain, _e, _c = build_video_chain(p, 1920, 1080)
    assert chain == "", "vùng đã tắt không được dựng ra filter nào"


def test_build_video_chain_bỏ_qua_logo_thiếu_đường_dẫn():
    p = Project(width=1920, height=1080, regions=[Region(kind=LOGO, path="")])
    chain, extra, _c = build_video_chain(p, 1920, 1080)
    assert chain == "" and extra == [], "logo chưa chọn file thì bỏ qua, không nổ"


def test_build_full_graph_nhãn_không_trùng_khi_bật_hết_tính_năng():
    """Chuỗi hình (cv*), tiếng gốc (cao*) và thuyết minh (cad*) chạy cùng lúc."""
    p = du_an_day_du()
    graph, _extra, vlab, alab = build_full_graph(p, 1920, 1080, srt_escaped="C\\:/a.srt")
    assert nhan_trung(graph.split(";")) == [], \
        f"nhãn trùng trong chuỗi đầy đủ: {nhan_trung(graph.split(';'))}"
    assert vlab and alab, "phải trả về nhãn ra cho cả hình lẫn tiếng"


def test_build_full_graph_không_có_thuyết_minh_thì_không_dựng_chuỗi_tiếng():
    p = Project(width=1920, height=1080, duration=100.0)
    graph, _e, _v, alab = build_full_graph(p, 1920, 1080, has_dub=False)
    assert alab == "", "chưa có file thuyết minh thì không có nhãn tiếng"
    assert "sidechaincompress" not in graph, "không có giọng đọc thì đừng dựng ducking"


def test_build_full_graph_cắt_trước_khi_trộn_tiếng():
    """Cắt sau khi trộn thì track thuyết minh có nhát cắt riêng bị cắt hai lần."""
    p = Project(width=1920, height=1080, duration=100.0,
                clips=[Clip(0, 30, 0), Clip(50, 100, 30)],
                dub_clips=[Clip(0, 40, 0)])
    graph, _e, _v, _a = build_full_graph(p, 1920, 1080)
    vi_tri_cat = graph.index("cadout")            # nhánh thuyết minh đã cắt xong
    vi_tri_tron = graph.index("amix")
    assert vi_tri_cat < vi_tri_tron, \
        "nhánh thuyết minh phải cắt xong trước khi tới amix"


def test_build_full_graph_chế_độ_trộn_đơn_giản():
    p = Project(width=1920, height=1080, duration=100.0)
    graph, _e, _v, _a = build_full_graph(p, 1920, 1080, duck="khong")
    assert "sidechaincompress" not in graph, "chế độ không ducking thì chỉ hạ âm lượng"
    assert "amix" in graph, "vẫn phải trộn hai track lại"
