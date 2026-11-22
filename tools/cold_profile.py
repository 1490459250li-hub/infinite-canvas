# -*- coding: utf-8 -*-
"""冷启动拆解：把「程序就绪」和「WebView2 就绪」分开测。

为什么需要这个：
    probe_splash.py 只能测到「主窗口出现」，而那一步在 WebView2 手里，
    实测 2-5 秒且抖动极大 —— 抖动盖过了打包方式（onefile/onedir）的差异，
    拿它对比会得出「改打包没用」的错误结论。

这里用两个独立信号：
    t_api    = 进程启动到 /api/health 返回 200
               这一段是「onefile 解压 + import + 建服务」，换 onedir 省的就是它
    t_window = 进程启动到主窗口出现（标题 = 无限画布）
               这一段主要是 WebView2 初始化，和打包方式无关

用法：
    python tools/cold_profile.py --exe "E:\\...\\无限画布.exe" --runs 3
    python tools/cold_profile.py --src            # 直接跑源码做对照
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8911
MAIN_TITLE = "无限画布"

user32 = ctypes.windll.user32
EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)


def main_window_seen():
    found = []

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if not n:
            return True
        b = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, b, n + 1)
        if b.value == MAIN_TITLE:
            found.append(1)
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return bool(found)


def port_free():
    """端口没人监听才算干净 —— 上一轮的进程没退干净时，探针会连到旧服务，
    测出 0.09 秒这种假数据。"""
    import socket
    s = socket.socket()
    try:
        s.settimeout(0.2)
        s.connect(("127.0.0.1", PORT))
        return False
    except Exception:
        return True
    finally:
        s.close()


def reap(p):
    """杀整棵进程树：PyInstaller 的 bootloader 会 fork 出真正的 Python 子进程，
    只杀父进程的话子进程还占着端口。"""
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=15)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass
    deadline = time.time() + 12
    while time.time() < deadline and not port_free():
        time.sleep(0.15)


def health_ok():
    """单次探测，不阻塞等待 —— 探针自己管循环，时间点才准。"""
    url = "http://127.0.0.1:%d/api/health" % PORT
    try:
        with urllib.request.urlopen(url, timeout=0.15) as r:
            if r.status != 200:
                return False
            json.loads(r.read().decode("utf-8"))
            return True
    except Exception:
        return False


def one_run(cmd, label):
    # 开测前必须确认上一轮真的退干净了
    guard = time.time() + 12
    while time.time() < guard and not port_free():
        time.sleep(0.15)
    t0 = time.time()
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t_api = t_win = None
    deadline = t0 + 40
    while time.time() < deadline:
        if p.poll() is not None:
            break
        if t_api is None and health_ok():
            t_api = time.time() - t0
        if t_api is not None and t_win is None and main_window_seen():
            t_win = time.time() - t0
        if t_api is not None and t_win is not None:
            break
        time.sleep(0.01)
    reap(p)

    def f(x):
        return ("%.2f" % x) if x is not None else "—"

    print("%-10s t_api=%-6s t_window=%-6s" % (label, f(t_api), f(t_win)))
    return t_api, t_win


def main():
    if "--src" in sys.argv:
        cmd = [sys.executable, os.path.join(ROOT, "proto", "server.py"),
               "--port", str(PORT), "--window", "native"]
        label = "source"
    else:
        exe = sys.argv[sys.argv.index("--exe") + 1] if "--exe" in sys.argv else None
        if not exe:
            raise SystemExit("给一个 --exe 路径，或用 --src")
        cmd = [exe, "--port", str(PORT), "--window", "native"]
        label = os.path.basename(exe)

    runs = int(sys.argv[sys.argv.index("--runs") + 1]) if "--runs" in sys.argv else 3
    apis, wins = [], []
    for i in range(runs):
        a, w = one_run(cmd, "%s#%d" % (label[:8], i + 1))
        if a:
            apis.append(a)
        if w:
            wins.append(w)
        time.sleep(0.8)          # 让 WebView2 profile 锁释放

    def summary(name, xs):
        if not xs:
            print("%s: 无数据" % name)
            return
        xs = sorted(xs)
        print("%s 中位 %.2f s  最快 %.2f s  最慢 %.2f s"
              % (name, xs[len(xs) // 2], xs[0], xs[-1]))

    print()
    summary("程序就绪(t_api)", apis)
    summary("窗口可见(t_window)", wins)


if __name__ == "__main__":
    main()
