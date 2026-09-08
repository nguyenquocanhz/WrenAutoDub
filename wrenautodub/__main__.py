# -*- coding: utf-8 -*-
"""WrenAutoDub — CLI."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from . import __version__

BANNER = r"""
 __      __             _         _        ___         _
 \ \    / / _ _  ___ _ _| |___    /_\  _  _| |_ ___  __| |_ _ ___
  \ \/\/ / | '_|/ -_) ' \  _/ _\ / _ \| || |  _/ _ \/ _` | || | _ \
   \_/\_/  |_|  \___|_||_\__\__//_/ \_\\_,_|\__\___/\__,_|\_,_|___/
                    ASR tiếng Nhật -> thuyết minh tiếng Việt
"""


def paths(video: Path, workdir: str | None):
    work = Path(workdir) if workdir else video.parent / f"{video.stem}_work"
    work.mkdir(parents=True, exist_ok=True)
    return {
        "work": work,
        "audio": work / "audio16k.wav",
        "ja": work / "ja.srt",
        "vi": work / "vi.srt",
        "cache": work / "vi.cache.json",
        "dub": work / "dub.wav",
        "out": video.parent / f"{video.stem}.vi{video.suffix}",
    }


def _pipeline_opts() -> argparse.ArgumentParser:
    """Tuỳ chọn dùng chung cho mọi lệnh có xử lý video."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("video", help="file video/audio nguồn")
    p.add_argument("-o", "--output", help="file video kết quả")
    p.add_argument("-w", "--workdir", help="thư mục làm việc (mặc định <tên>_work)")
    p.add_argument("-f", "--force", action="store_true",
                   help="làm lại kể cả khi đã có kết quả cũ")

    g = p.add_argument_group("Nhận dạng")
    g.add_argument("--model", default="large-v3",
                   help="tiny/base/small/medium/large-v3/large-v3-turbo — tự tải nếu chưa có")
    g.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    g.add_argument("--compute-type", default="auto",
                   help="auto/int8_float16/int8/float16 (auto sẽ tự dò và fallback)")
    g.add_argument("--beam-size", type=int, default=5)
    g.add_argument("--lang", default="ja", help="ngôn ngữ nguồn")
    g.add_argument("--no-prompt", action="store_true", help="tắt initial_prompt tiếng Nhật")
    g.add_argument("--max-cue-dur", type=float, default=8.0,
                   help="độ dài tối đa 1 câu phụ đề (giây)")
    g.add_argument("--max-cue-chars", type=int, default=60,
                   help="số ký tự tối đa 1 câu phụ đề")

    g = p.add_argument_group("Dịch")
    g.add_argument("--target", default="vi", help="ngôn ngữ đích")
    g.add_argument("--delay", type=float, default=0.25, help="nghỉ giữa các request Google")

    g = p.add_argument_group("Thuyết minh")
    g.add_argument("--tts", default="vieneu", choices=["vieneu", "edge"],
                   help="vieneu chạy offline trên CPU; edge cần mạng")
    g.add_argument("--voice", default=None,
                   help="vieneu: tên giọng (xem: wren.py voices) | edge: nam/nu")
    g.add_argument("--rate", default="+8%", help="tốc độ đọc của edge, vd +0%%, +15%%")
    g.add_argument("--precision", default="int8", choices=["int8", "fp32"],
                   help="độ chính xác ONNX của vieneu")
    g.add_argument("--batch-size", type=int, default=16, help="số câu mỗi lô của vieneu")
    g.add_argument("--max-tempo", type=float, default=1.7,
                   help="hệ số tăng tốc tối đa khi câu quá dài")
    g.add_argument("--max-overflow", type=float, default=1.5,
                   help="giây được phép tràn quá câu phụ đề")
    g.add_argument("--concurrency", type=int, default=5, help="số request edge-tts song song")

    g = p.add_argument_group("Ghép")
    g.add_argument("--duck", default="sidechain", choices=["sidechain", "flat"],
                   help="sidechain = tự hạ tiếng gốc khi có lời thuyết minh")
    g.add_argument("--orig-vol", type=float, default=0.35, help="âm lượng tiếng gốc")
    g.add_argument("--dub-vol", type=float, default=1.6, help="âm lượng giọng thuyết minh")
    g.add_argument("--no-orig-track", action="store_true",
                   help="không giữ track tiếng gốc riêng")
    g.add_argument("--no-softsub", action="store_true",
                   help="không nhúng phụ đề Việt vào video")
    g.add_argument("--hardsub", action="store_true",
                   help="nung phụ đề thẳng lên hình (buộc mã hoá lại video)")
    g.add_argument("--hwaccel", default="auto",
                   help="auto/cuda/d3d11va/dxva2/qsv/none — giải mã video bằng GPU")
    g.add_argument("--venc", default="copy",
                   help="copy (không mã hoá lại) / auto (chọn GPU tốt nhất) "
                        "/ h264_nvenc / hevc_nvenc / libx264")
    return p


def build_parser() -> argparse.ArgumentParser:
    common = _pipeline_opts()
    p = argparse.ArgumentParser(
        prog="wren.py",
        description="WrenAutoDub — nhận dạng tiếng Nhật, dịch, thuyết minh tiếng Việt, ghép video.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("-V", "--version", action="version", version=f"WrenAutoDub {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="LỆNH")

    fmt = argparse.ArgumentDefaultsHelpFormatter
    sub.add_parser("run", parents=[common], formatter_class=fmt,
                   help="chạy cả 4 bước (thường dùng nhất)")
    sub.add_parser("asr", parents=[common], formatter_class=fmt,
                   help="chỉ nhận dạng tiếng Nhật -> ja.srt")
    sub.add_parser("translate", parents=[common], formatter_class=fmt,
                   help="chỉ dịch ja.srt -> vi.srt")
    sub.add_parser("tts", parents=[common], formatter_class=fmt,
                   help="chỉ đọc vi.srt -> dub.wav")
    sub.add_parser("mux", parents=[common], formatter_class=fmt,
                   help="chỉ trộn và ghép vào video")

    m = sub.add_parser("models", help="xem / tải / xoá model")
    m.add_argument("--get", metavar="TÊN",
                   help="tải model (tên Whisper, 'vieneu', hoặc 'all-asr')")
    m.add_argument("--rm", metavar="TÊN", help="xoá model khỏi cache")
    m.add_argument("--json", action="store_true", help="in JSON cho GUI đọc")

    v = sub.add_parser("voices", help="liệt kê giọng đọc")
    v.add_argument("--tts", default="vieneu", choices=["vieneu", "edge"])
    v.add_argument("--json", action="store_true", help="in JSON cho GUI đọc")

    sub.add_parser("gui", help="mở giao diện đồ hoạ (PyQt6)")

    h = sub.add_parser("handoff",
                       help="gom vi.srt + dub.wav thành thư mục kéo vào CapCut")
    h.add_argument("video", help="file phim gốc")
    h.add_argument("-w", "--workdir", help="thư mục làm việc (mặc định <tên>_work)")
    h.add_argument("-o", "--out", help="thư mục bàn giao (mặc định <tên>_capcut)")
    h.add_argument("--copy-video", action="store_true",
                   help="chép cả phim gốc vào (mặc định chỉ ghi đường dẫn)")

    e = sub.add_parser("edit", help="mở cửa sổ sửa video (hiệu ứng, phụ đề, xuất bản)")
    e.add_argument("video", help="file video cần sửa")
    e.add_argument("-w", "--workdir", help="thư mục làm việc (mặc định <tên>_work)")
    e.add_argument("--qml", action="store_true",
                   help="dùng giao diện QML (bản đang dựng) thay cho Widgets")

    d = sub.add_parser("doctor", help="kiểm tra môi trường trước khi chạy phim dài")
    d.add_argument("--quick", action="store_true", help="bỏ qua kiểm tra mạng và chạy thử CUDA")
    return p


def _run_pipeline(args) -> int:
    video = Path(args.video).expanduser().resolve()
    if not video.exists():
        print(f"Không tìm thấy file: {video}")
        return 1

    P = paths(video, args.workdir)
    out = Path(args.output).expanduser() if args.output else P["out"]
    cmd, t0 = args.cmd, time.time()

    from . import asr as S1, mux as S4, translate as S2, tts as S3

    if cmd in ("run", "asr"):
        print("\n=== 1/4 NHẬN DẠNG TIẾNG NHẬT ===")
        S1.extract_audio(video, P["audio"], force=args.force)
        S1.transcribe(
            P["audio"], P["ja"],
            model_size=args.model, language=args.lang,
            device=args.device, compute_type=args.compute_type,
            beam_size=args.beam_size,
            initial_prompt=None if args.no_prompt else S1.DEFAULT_PROMPT,
            max_cue_dur=args.max_cue_dur, max_cue_chars=args.max_cue_chars,
            force=args.force,
        )

    if cmd in ("run", "translate"):
        print("\n=== 2/4 DỊCH SANG TIẾNG VIỆT ===")
        S2.translate_srt(P["ja"], P["vi"], source=args.lang, target=args.target,
                         cache_path=P["cache"], delay=args.delay, force=args.force)

    if cmd in ("run", "tts"):
        print("\n=== 3/4 TỔNG HỢP GIỌNG THUYẾT MINH ===")
        S3.build_dub(
            P["vi"], P["dub"], P["work"],
            engine=args.tts, voice=args.voice, rate=args.rate,
            precision=args.precision, batch_size=args.batch_size,
            total_dur=S1.ffprobe_duration(video),
            max_overflow=args.max_overflow, max_tempo=args.max_tempo,
            concurrency=args.concurrency, force=args.force,
        )

    if cmd in ("run", "mux"):
        print("\n=== 4/4 GHÉP AUDIO VÀO VIDEO ===")
        S4.mux(
            video, P["dub"], out,
            srt=None if args.no_softsub and not args.hardsub else P["vi"],
            duck=args.duck, orig_vol=args.orig_vol, dub_vol=args.dub_vol,
            keep_orig_audio=not args.no_orig_track,
            hardsub=args.hardsub, hwaccel_name=args.hwaccel, vcodec=args.venc,
            force=args.force, src_lang=args.lang,
        )

    print(f"\nHoàn tất sau {(time.time() - t0) / 60:.1f} phút.")
    if cmd in ("run", "mux"):
        print(f"Kết quả: {out}")
    if cmd == "run":
        print("\nMuốn tự dựng tiếp bằng CapCut hay trình dựng khác:")
        print(f'  python wren.py handoff "{video.name}"')
        print("  -> gom vi.srt + dub.wav thành thư mục kéo thả được")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.cmd == "models":
        from . import models
        if args.get:
            models.get(args.get)
            print()
        if args.rm:
            models.remove(args.rm)
            print()
        if args.json:
            import json
            rows = [{"group": g, "name": n, "cached": c, "size_mb": r, "est_mb": e,
                     "desc": d} for g, n, c, r, e, d in models.status()]
            print(json.dumps({"cache": str(models.hub_cache()),
                              "free_mb": models.free_mb(),
                              "models": rows}, ensure_ascii=False))
        elif not args.get and not args.rm:
            models.print_status()
        return 0

    if args.cmd == "voices":
        if args.json:
            import json
            if args.tts == "edge":
                import asyncio

                import edge_tts
                vs = asyncio.run(edge_tts.list_voices())
                out = [{"name": v["ShortName"],
                        "label": f"{v['ShortName']} — {v['Gender']}"}
                       for v in vs if v["Locale"].startswith("vi")]
            else:
                from .tts import list_vieneu_voices
                out = [{"name": n, "label": l} for l, n in list_vieneu_voices()]
            print(json.dumps(out, ensure_ascii=False))
            return 0

        if args.tts == "edge":
            import asyncio

            import edge_tts
            vs = asyncio.run(edge_tts.list_voices())
            print("Giọng edge-tts tiếng Việt (dùng với --tts edge):\n")
            for v in vs:
                if v["Locale"].startswith("vi"):
                    alias = {"vi-VN-NamMinhNeural": "nam",
                             "vi-VN-HoaiMyNeural": "nu"}.get(v["ShortName"], "")
                    print(f"  {v['ShortName']:<24} {v['Gender']:<8} {alias}")
        else:
            from .tts import list_vieneu_voices
            print("Giọng VieNeu-TTS (dùng với --voice \"Tên\"):\n")
            for label, name in list_vieneu_voices():
                print(f"  {name:<14} {label}")
        return 0

    if args.cmd == "handoff":
        from . import handoff
        return handoff.run(args.video, args.workdir, args.out, args.copy_video)

    if args.cmd == "edit":
        if getattr(args, "qml", False):
            from .qml_app import launch
            return launch(args.video, args.workdir)
        import sys as _sys

        from PyQt6.QtWidgets import QApplication, QStyleFactory

        from .editor_main import EditorWindow
        from .gui import dark_palette
        app = QApplication(_sys.argv)
        app.setStyle(QStyleFactory.create("Fusion"))
        app.setPalette(dark_palette())
        w = EditorWindow(args.video, args.workdir)
        w.show()
        return app.exec()

    if args.cmd == "gui":
        from .gui import launch
        return launch()

    if args.cmd == "doctor":
        from . import doctor
        print(BANNER)
        return doctor.run(quick=args.quick)

    return _run_pipeline(args)


if __name__ == "__main__":
    raise SystemExit(main())
