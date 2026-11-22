# -*- coding: utf-8 -*-
"""截启动画面，存 BMP（这台机器没有 Pillow，BMP 可以纯手写头）。

用法：python /tmp/shot_splash.py <输出.bmp> [停留秒数]
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
import time

sys.path.insert(0, r"E:\无限画布\proto")
import server  # noqa: E402

u = ctypes.WinDLL("user32", use_last_error=True)
g = ctypes.WinDLL("gdi32", use_last_error=True)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


u.GetDC.restype = wt.HDC
u.GetDC.argtypes = [wt.HWND]
u.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
u.GetSystemMetrics.argtypes = [ctypes.c_int]
g.CreateCompatibleDC.restype = wt.HDC
g.CreateCompatibleDC.argtypes = [wt.HDC]
g.CreateCompatibleBitmap.restype = wt.HANDLE
g.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
g.SelectObject.restype = wt.HANDLE
g.SelectObject.argtypes = [wt.HDC, wt.HANDLE]
g.BitBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                     wt.HDC, ctypes.c_int, ctypes.c_int, wt.DWORD]
g.GetDIBits.argtypes = [wt.HDC, wt.HANDLE, wt.UINT, wt.UINT, ctypes.c_void_p,
                        ctypes.POINTER(BITMAPINFO), wt.UINT]


def grab(path):
    w, h = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    hdc = u.GetDC(None)
    mem = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, w, h)
    g.SelectObject(mem, bmp)
    g.BitBlt(mem, 0, 0, w, h, hdc, 0, 0, 0x00CC0020)

    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h                 # 负数 = 从上往下
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0
    bi.bmiHeader.biSizeImage = w * h * 4
    buf = ctypes.create_string_buffer(w * h * 4)
    g.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)

    with open(path, "wb") as f:
        f.write(b"BM")
        f.write(struct.pack("<IHHI", 14 + 40 + len(buf.raw), 0, 0, 54))
        f.write(struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 32, 0, len(buf.raw), 2835, 2835, 0, 0))
        f.write(buf.raw)
    u.ReleaseDC(None, hdc)
    return w, h


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else r"E:\无限画布\截图\v374\splash.bmp"
    hold = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    server.splash_show()
    time.sleep(hold)
    w, h = grab(out)
    server.splash_close()
    time.sleep(0.4)
    print("saved %s  %dx%d" % (out, w, h))
