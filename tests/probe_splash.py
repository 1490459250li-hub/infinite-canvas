# -*- coding: utf-8 -*-
"""测两个时间点：启动画面出现、主窗口出现。

为什么不用截图：截图要等浏览器工具起动，本身几百 ms，测不准。
这里直接枚举顶层窗口的类名 —— tkinter 的 root 是 TkTopLevel，
WebView2 宿主是 WinForms/Chrome_WidgetWin，一眼能分开。

用法：
    python tests/probe_splash.py
    python tests/probe_splash.py --exe "E:\\...\\无限画布.exe"
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CMD = [sys.executable, os.path.join(ROOT, "proto", "server.py"), "--self-test"]

user32 = ctypes.windll.user32
EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)


def visible_windows():
    out = []

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            n = user32.GetWindowTextLengthW(hwnd)
            title = ""
            if n:
                b = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, b, n + 1)
                title = b.value
            out.append((cls.value, title))
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return out


SPLASH_CLASS = "SncSplashWnd"
MAIN_TITLE = "无限画布"


def is_splash(cls):
    return cls == SPLASH_CLASS


def is_main(cls, title):
    return title == MAIN_TITLE


def run(cmd, label):
    t0 = time.time()
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t_splash = t_main = None
    while time.time() - t0 < 40:
        if p.poll() is not None:
            break
        for cls, title in visible_windows():
            if t_splash is None and is_splash(cls):
                t_splash = time.time() - t0
            if t_main is None and is_main(cls, title):
                t_main = time.time() - t0
        if t_splash and t_main:
            break
        time.sleep(0.02)
    try:
        p.wait(timeout=40)
    except subprocess.TimeoutExpired:
        p.kill()
    total = time.time() - t0

    def f(x):
        return ("%.2f s" % x) if x is not None else "未出现"

    print("%-12s splash=%-8s 主窗口=%-8s 进程退出=%.2f s  rc=%s"
          % (label, f(t_splash), f(t_main), total, p.returncode))
    return t_splash, t_main, total


if __name__ == "__main__":
    cmd = DEFAULT_CMD
    if "--exe" in sys.argv:
        cmd = [sys.argv[sys.argv.index("--exe") + 1], "--self-test"]
    n = 2
    if "--runs" in sys.argv:
        n = int(sys.argv[sys.argv.index("--runs") + 1])
    main_times = []
    for i in range(n):
        _, t_main, _ = run(cmd, "run%d" % (i + 1))
        if t_main:
            main_times.append(t_main)
    if main_times:
        main_times.sort()
        mid = main_times[len(main_times) // 2]
        print("主窗口中位 %.2f s / 最快 %.2f s / 最慢 %.2f s（%d 次）"
              % (mid, main_times[0], main_times[-1], len(main_times)))
