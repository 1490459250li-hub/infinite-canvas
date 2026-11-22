# -*- coding: utf-8 -*-
"""把 demo-v37/demo.html 打成一个可直接双击打开的单文件（图片全部内联）。"""
import base64, json, os, re

D = r"E:\无限画布\demo-v37"
IMG = os.path.join(D, "img")
s = open(os.path.join(D, "demo.html"), encoding="utf-8").read()

# 1) 控件字典
s = s.replace("__CONTROLS__", open(os.path.join(D, "controls.json"), encoding="utf-8").read())

# 2) 网格用的 21 张：old-* / new-*
mp = {}
for f in sorted(os.listdir(IMG)):
    if f.startswith(("old-", "new-")):
        mp[os.path.splitext(f)[0]] = "data:image/jpeg;base64," + \
            base64.b64encode(open(os.path.join(IMG, f), "rb").read()).decode()
s = s.replace("__IMG__", json.dumps(mp, ensure_ascii=False))

# 3) 静态 <img src="img/xxx.jpg">
def inline(m):
    path = os.path.join(D, m.group(1))
    mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
    return 'src="data:%s;base64,%s"' % (mime, base64.b64encode(open(path, "rb").read()).decode())
s, n = re.subn(r'src="(img/[A-Za-z0-9_\-]+\.(?:jpg|png))"', inline, s)

out = os.path.join(D, "对比-技能窗口与预览图.html")
open(out, "w", encoding="utf-8").write(s)
print("静态图 %d 张 · 网格图 %d 张 · %.2f MB" % (n, len(mp), len(s.encode()) / 1048576))
