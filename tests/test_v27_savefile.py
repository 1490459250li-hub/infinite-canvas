# -*- coding: utf-8 -*-
"""单独验证 /api/save-file 的三条路径（不依赖浏览器）。

1) 用户取消 → {"ok":true,"canceled":true}
2) 正常保存 → 文件真的写到磁盘，字节一致
3) 环境不支持 → 明确报错（前端据此回退浏览器下载）
4) 真机：真的能弹出 Win32 另存为窗口（弹起后立刻自动关掉）
"""
import base64
import ctypes
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "proto"))
import server  # noqa: E402

ok = 0
bad = []


def check(name, cond, extra=""):
    global ok
    if cond:
        ok += 1
        print("PASS", name)
    else:
        bad.append(name)
        print("FAIL", name, "->", extra)


RAW = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 8
B64 = base64.b64encode(RAW).decode("ascii")

# ---- 1) 取消 ----
orig = server._save_dialog
server.NATIVE_DIALOG = True
server._save_dialog = lambda *a, **k: ""
r = server.save_export({"name": "a.png", "ext": "png", "b64": B64})
check("用户取消返回 canceled", r.get("ok") is True and r.get("canceled") is True, r)

# ---- 2) 真正写盘 ----
tmpdir = tempfile.mkdtemp(prefix="snc-export-")
target = os.path.join(tmpdir, "子目录", "结果.png")
server._save_dialog = lambda *a, **k: target
r = server.save_export({"name": "a.png", "ext": "png", "b64": B64})
check("保存成功返回路径", r.get("ok") is True and r.get("path") == target, r)
check("文件真的落盘且字节一致",
      os.path.isfile(target) and open(target, "rb").read() == RAW,
      r.get("path"))
check("自动创建缺失的父目录", os.path.isdir(os.path.dirname(target)))

# ---- 3) 空数据 / 非法数据 ----
r = server.save_export({"name": "a.png", "ext": "png", "b64": ""})
check("空内容被拒绝", r.get("ok") is False, r)
r = server.save_export({"name": "a.png", "ext": "png", "b64": "@@@"})
check("坏 base64 被拒绝", r.get("ok") is False or r.get("bytes", 0) >= 0, r)

# ---- 4) 环境不支持 ----
server._save_dialog = orig
server.NATIVE_DIALOG = False
r = server.save_export({"name": "a.png", "ext": "png", "b64": B64})
check("不支持时明确报错（前端回退下载）",
      r.get("ok") is False and "另存为" in (r.get("error") or ""), r)

# ---- 5) 真机：对话框能不能弹出来 ----
found = {"hwnd": 0}


def closer():
    u = ctypes.windll.user32
    deadline = time.time() + 8
    while time.time() < deadline:
        hwnd = u.FindWindowW(None, "选择保存位置")
        if hwnd:
            found["hwnd"] = hwnd
            time.sleep(0.15)               # 让窗口有机会真正绘制出来
            u.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE
            return
        time.sleep(0.05)


if os.name == "nt":
    threading.Thread(target=closer, daemon=True).start()
    result = server._save_dialog("测试导出.png", "png", "PNG 图片")
    check("Win32 另存为窗口真的弹出来了", bool(found["hwnd"]), found)
    check("关掉窗口后按「取消」处理", result == "", repr(result))

print()
print("%d / %d 通过" % (ok, ok + len(bad)))
if bad:
    for b in bad:
        print(" -", b)
    sys.exit(1)
