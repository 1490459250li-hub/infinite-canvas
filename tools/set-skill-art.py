# -*- coding: utf-8 -*-
"""把某条技能的预览图写进 proto/art/（外链文件）。

v3.7.4 起预览图不再内联进 canvas.src.html —— 21 张 base64 曾占源码七成体积。
现在 SKILL_ART 里存的是 /art/skill-<id>.jpg 路径，图片本体在这个目录。

用法：
    python tools/set-skill-art.py bi-time                 # 从 截图/v37/preview/bi-time.jpg 读
    python tools/set-skill-art.py bi-time --src X.jpg     # 指定源文件
    python tools/set-skill-art.py --all                   # 把 preview 目录里已有的全部同步

预览图统一压到 512 宽、质量 4 的 jpg，跟已有 21 张同规格（40-60 KB）。
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "proto", "canvas.src.html")
ART = os.path.join(ROOT, "proto", "art")
PREVIEW = os.path.join(ROOT, "截图", "v37", "preview")
MAX_W = 512


def shrink(src, dst):
    """缩到 512 宽写进 dst，返回字节数。"""
    tmp = os.path.join(tempfile.gettempdir(), "snc-art-%d.jpg" % os.getpid())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src,
                    "-vf", "scale=%d:-1" % MAX_W, "-q:v", "4", tmp], check=True)
    with open(tmp, "rb") as f:
        b = f.read()
    os.remove(tmp)
    if len(b) < 8000:
        raise SystemExit("压完太小，可能不是有效图：%s" % src)
    with open(dst, "wb") as f:
        f.write(b)
    return len(b)


def ensure_entry(key):
    """SKILL_ART 里还没有这个键时补一行，指向 /art/skill-<key>.jpg。"""
    s = open(HTML, encoding="utf-8").read()
    pat = re.compile(r'(\n    "%s": ")([^"]*)(")' % re.escape(key))
    m = pat.search(s)
    if m:
        if m.group(2).startswith("/art/"):
            return "reuse"
        # 老格式（内联 base64）：只改值，不碰别的
        s2 = s[:m.start(2)] + "/art/skill-%s.jpg" % key + s[m.end(2):]
        open(HTML, "w", encoding="utf-8").write(s2)
        return "migrated"
    anchor = "\n  var SKILL_ART = {"
    i = s.find(anchor)
    if i < 0:
        raise SystemExit("找不到 SKILL_ART 定义")
    j = s.find("\n", i + len(anchor)) + 1
    line = '    "%s": "/art/skill-%s.jpg",\n' % (key, key)
    s2 = s[:j] + line + s[j:]
    open(HTML, "w", encoding="utf-8").write(s2)
    return "added"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--all" in sys.argv:
        args = [k[:-4] for k in os.listdir(PREVIEW) if k.endswith(".jpg")]
    if not args:
        raise SystemExit("给我一个技能 id，或 --all")
    src_override = None
    if "--src" in sys.argv:
        src_override = sys.argv[sys.argv.index("--src") + 1]
    os.makedirs(ART, exist_ok=True)
    for key in args:
        src = src_override or os.path.join(PREVIEW, key + ".jpg")
        if not os.path.exists(src):
            print("SKIP %-12s 没有 %s" % (key, src))
            continue
        dst = os.path.join(ART, "skill-%s.jpg" % key)
        n = shrink(src, dst)
        state = ensure_entry(key)
        print("OK   %-12s %3d KB -> art/skill-%s.jpg  [%s]"
              % (key, n // 1024, key, state))


if __name__ == "__main__":
    main()
