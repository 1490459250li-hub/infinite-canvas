# -*- coding: utf-8 -*-
"""v3.8.14 自检：真跑一次 exe，抓启动画面收尾与主窗口。"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes as wt

from PIL import ImageGrab

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "proto", "dist", "无限画布", "无限画布.exe")
OUT = os.path.join(ROOT, "mock", "shots15")
os.makedirs(OUT, exist_ok=True)

u = ctypes.WinDLL("user32", use_last_error=True)
EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)


def windows():
    out = []

    def cb(hwnd, _):
        if u.IsWindowVisible(hwnd):
            t = ctypes.create_unicode_buffer(256)
            c = ctypes.create_unicode_buffer(256)
            u.GetWindowTextW(hwnd, t, 256)
            u.GetClassNameW(hwnd, c, 256)
            out.append((hwnd, c.value, t.value))
        return True

    u.EnumWindows(EnumProc(cb), 0)
    return out


def rect(hwnd):
    r = wt.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def grab(hwnd, name):
    l, t, r, b = rect(hwnd)
    im = ImageGrab.grab(bbox=(l, t, r, b), all_screens=True)
    im.save(os.path.join(OUT, name))
    print(name, im.size)


def main():
    t0 = time.time()
    proc = subprocess.Popen([EXE], cwd=os.path.dirname(EXE))
    try:
        splash = None
        while time.time() - t0 < 15:
            for hw, cls, title in windows():
                if cls == "SncSplashWnd":
                    splash = (hw, title)
                    break
            if splash:
                break
            time.sleep(0.05)
        print("splash:", splash, "at %.2fs" % (time.time() - t0))
        if splash:
            time.sleep(1.6)                 # 让进度条走满
            grab(splash[0], "exe-splash-full.png")
            print("bar shot at %.2fs" % (time.time() - t0))
            while time.time() - t0 < 30:
                if not any(c == "SncSplashWnd" for _, c, _ in windows()):
                    print("splash closed at %.2fs" % (time.time() - t0))
                    break
                time.sleep(0.2)
        # 主窗口：pywebview 的窗口类名不固定，按标题精确匹配
        main_hw = None
        while time.time() - t0 < 40:
            for hw, cls, title in windows():
                if title.strip() == "无限画布" and cls != "SncSplashWnd":
                    l, t, r, b = rect(hw)
                    if r - l > 600 and b - t > 400:
                        main_hw = hw
                        break
            if main_hw:
                break
            time.sleep(0.2)
        print("main:", main_hw, "at %.2fs" % (time.time() - t0))
        if main_hw:
            time.sleep(2.0)
            grab(main_hw, "exe-main.png")
            l, t, r, b = rect(main_hw)
            im = ImageGrab.grab(bbox=(l, t, l + 420, t + 120), all_screens=True)
            im.resize((im.width * 2, im.height * 2)).save(os.path.join(OUT, "exe-main-brand.png"))
            print("brand crop saved")
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
