# -*- coding: utf-8 -*-
"""Chan cua cho hook review commit.

Chay sau MOI lenh Bash nen phai re va tat dinh: doc JSON tren stdin, quyet
dinh bang cach tach token, khong goi git, khong goi mang, khong bao gio chan.
Thoat 0 im lang neu lenh vua chay khong phai `git commit`.
"""
import json
import shlex
import sys


def la_git_commit(cmd: str) -> bool:
    """Dung `git commit`, khong tinh `git log` hay chu 'commit' trong -m."""
    try:
        toks = shlex.split(cmd, posix=True)
    except ValueError:
        toks = cmd.split()
    i = 0
    while i < len(toks):
        if toks[i] == "git":
            j = i + 1
            # bo qua co toan cuc: -c key=val, -C duong/dan, --no-pager...
            while j < len(toks) and toks[j].startswith("-"):
                j += 2 if toks[j] in ("-c", "-C") else 1
            if j < len(toks) and toks[j] == "commit":
                return True
        i += 1
    return False


def main() -> int:
    try:
        d = json.load(sys.stdin)
    except Exception:
        return 0                     # khong doc duoc thi im lang, dung chan
    cmd = (d.get("tool_input") or {}).get("command") or ""
    if not la_git_commit(cmd):
        return 0

    # Commit that bai thi khong co gi de review
    resp = d.get("tool_response") or {}
    text = json.dumps(resp, ensure_ascii=False).lower()
    if "nothing to commit" in text or "no changes added" in text:
        return 0

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "Vua tao mot commit trong WrenAutoDub. Hay giao cho MOT agent "
                "review doc lap (Agent tool) voi noi dung: doc `git show --stat "
                "HEAD` va `git diff HEAD~1 HEAD`, doi chieu CLAUDE.md "
                "(quy tac bat buoc + danh sach bay da gap), CHI bao loi that kem "
                "file:dong, kich ban tai hien va hau qua. Neu diff sach thi noi "
                "'Khong thay loi nao' roi dung. Bao cao bang tieng Viet. "
                "Neu vua review commit nay roi thi bo qua."
            ),
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
