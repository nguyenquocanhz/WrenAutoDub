# -*- coding: utf-8 -*-
"""Chan cua cho hook review commit.

Chay sau MOI lenh Bash nen phai re va tat dinh: doc JSON tren stdin, quyet
dinh bang cach tach token, khong goi git, khong goi mang. Moi duong di deu
phai thoat 0 - ma thoat 2 la ma CHAN, se lam hong dung cai no sinh ra de sua.
"""
import json
import shlex
import sys

# Token bat dau mot lenh moi trong shell. Chi tinh `git` la lenh khi no dung
# ngay dau chuoi hoac ngay sau mot trong nhung dau nay - khong thi
# `echo nho chay git commit sau` cung bi coi la commit.
NGAT = {";", "&&", "||", "|", "&", "(", ")", "{", "}", "\n"}


def la_git_commit(cmd: str) -> bool:
    """Dung `git commit`, khong tinh `git log` hay chu 'commit' trong cau van."""
    try:
        toks = shlex.split(cmd, posix=True)
    except ValueError:
        # Nhay khong can doi. Thu lai kieu khong posix; van hong thi thoi,
        # bao khong phai commit con hon bat nham.
        try:
            toks = shlex.split(cmd, posix=False)
        except ValueError:
            return False

    dau_lenh = True
    for i, t in enumerate(toks):
        if t in NGAT:
            dau_lenh = True
            continue
        if not dau_lenh:
            continue
        dau_lenh = False
        if t != "git":
            continue
        j = i + 1
        while j < len(toks) and toks[j].startswith("-"):
            j += 2 if toks[j] in ("-c", "-C") else 1
        if j < len(toks) and toks[j] == "commit":
            # --dry-run khong tao commit nao, khong co gi de review
            if "--dry-run" in toks[j:]:
                return False
            return True
    return False


def main() -> int:
    try:
        d = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(d, dict):
        return 0                     # JSON hop le nhung khong phai object
    ti = d.get("tool_input")
    if not isinstance(ti, dict):
        return 0
    cmd = ti.get("command")
    if not isinstance(cmd, str) or not cmd:
        return 0
    if not la_git_commit(cmd):
        return 0

    # KHONG doc noi dung tool_response de doan commit thanh cong hay khong.
    # Ban truoc quet chuoi "nothing to commit" nen `git commit && git status`
    # bi nuot: git status in dung chuoi do sau MOT COMMIT THANH CONG. Va
    # `git commit -q` thi khong in gi ca. De agent tu chay `git log` ma xet.
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "Vua chay mot lenh git commit trong WrenAutoDub. Hay giao cho "
                "MOT agent review doc lap (Agent tool): doc `git show --stat "
                "HEAD` va `git diff HEAD~1 HEAD`, doi chieu CLAUDE.md (quy tac "
                "bat buoc + danh sach bay da gap), CHI bao loi that kem "
                "file:dong, kich ban tai hien va hau qua, va phai CHAY THU "
                "truoc khi khang dinh dieu gi ve hanh vi code. Neu HEAD khong "
                "doi (commit that bai) hoac diff sach thi noi mot cau roi dung. "
                "Bao cao bang tieng Viet. Neu da review commit nay roi thi bo qua."
            ),
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
