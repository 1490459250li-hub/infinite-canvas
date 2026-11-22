# -*- coding: utf-8 -*-
"""启动画面可行性实测：Python 侧用 GDI DIB Section 逐像素画粒子，能跑多少帧。

现有启动框是 FillRect + TextOut，画不了粒子光晕。
要上 S1 就必须改成「32 位 DIB + 手写像素 + BitBlt」。
这个脚本只测最热的那一段，不建窗口，纯粹回答：一帧要多久。
"""
import ctypes
import math
import time
from ctypes import wintypes as wt

W, H = 520, 300
N_RIM = 720
N_INNER = 1650
STRIDE = W * 4

g = ctypes.WinDLL("gdi32", use_last_error=True)
u = ctypes.WinDLL("user32", use_last_error=True)

g.CreateCompatibleDC.argtypes = [wt.HDC]
g.CreateCompatibleDC.restype = wt.HDC
g.CreateDIBSection.argtypes = [wt.HDC, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p),
                               wt.HANDLE, wt.DWORD]
g.CreateDIBSection.restype = wt.HANDLE
g.SelectObject.argtypes = [wt.HDC, wt.HANDLE]
g.SelectObject.restype = wt.HANDLE
g.BitBlt.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                     wt.HDC, ctypes.c_int, ctypes.c_int, wt.DWORD]
g.DeleteObject.argtypes = [wt.HANDLE]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


def make_points():
    """和预览页同一套几何：边缘采样 + 内部实心填充。"""
    cx, cy, a = W / 2, 106.0, 106.0
    pts = []

    def lem(u):
        s, c = math.sin(u), math.cos(u)
        d = 1 + s * s
        return a * c / d, a * s * c / d

    import random
    rnd = random.Random(20261121)
    for i in range(N_RIM):
        uu = i / N_RIM * math.tau
        x, y = lem(uu)
        off = (rnd.random() * 2 - 1) * 1.6
        pts.append((int(cx + x), int(cy + y + off), 0.52 + rnd.random() * 0.38))

    filled = 0
    tries = 0
    while filled < N_INNER and tries < 200000:
        tries += 1
        x = (rnd.random() * 2 - 1) * a
        y = (rnd.random() * 2 - 1) * a * 0.40
        l = x * x + y * y
        if l * l > a * a * (x * x - y * y):
            continue
        filled += 1
        pts.append((int(cx + x), int(cy + y), 0.18 + rnd.random() * 0.20))

    # 颜色表：蓝 → 青 → 绿 → 金 → 橙（预先算好，每帧只查表）
    ramp = [(58, 92, 255), (45, 170, 250), (45, 216, 208),
            (132, 226, 118), (250, 202, 78), (255, 128, 78), (255, 92, 122)]
    out = []
    for x, y, al in pts:
        v = max(0.0, min(0.999, (x - 0) / W))
        seg = v * (len(ramp) - 1)
        i0 = int(seg)
        k = seg - i0
        c0, c1 = ramp[i0], ramp[min(i0 + 1, len(ramp) - 1)]
        r = int(c0[0] + (c1[0] - c0[0]) * k)
        gg = int(c0[1] + (c1[1] - c0[1]) * k)
        b = int(c0[2] + (c1[2] - c0[2]) * k)
        # 预乘 alpha：DIB 是不透明底，直接给足亮度
        f = 0.45 + al * 0.55
        out.append((x, y, int(b * f), int(gg * f), int(r * f)))
    return out


def main():
    hdc_screen = u.GetDC(0)
    hdc = g.CreateCompatibleDC(hdc_screen)

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = W
    bmi.biHeight = -H            # 负值 = 自上而下，行序和 Canvas 一致
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0        # BI_RGB

    bits = ctypes.c_void_p()
    hbmp = g.CreateDIBSection(hdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    g.SelectObject(hdc, hbmp)
    print("DIB ok:", bool(hbmp), "buffer ptr:", bool(bits))

    pts = make_points()
    print("点数:", len(pts))

    # ctypes 数组的 memoryview 格式是 <B / <c，切片赋值一律 NotImplementedError。
    # 正解：先在 bytearray 上画（原生 'B' 视图，切片赋值很快），画完整块 memmove 进 DIB。
    ba = bytearray(STRIDE * H)
    mv = memoryview(ba)
    src_view = (ctypes.c_char * (STRIDE * H)).from_buffer(ba)

    # 预先把每个点要写的字节算好，循环里只做切片赋值
    ops = []
    for x, y, b, gg, r in pts:
        if not (0 <= x < W - 1 and 0 <= y < H - 1):
            continue
        i = y * STRIDE + x * 4
        px = bytes((b, gg, r, 255))
        # 2×2 的点，四个像素一次写
        ops.append((i, px + px))
        ops.append((i + STRIDE, px + px))

    black = bytes(STRIDE * H)
    N = 200
    t0 = time.perf_counter()
    for _ in range(N):
        mv[:] = black                        # 清屏（一次 memcpy）
        for i, px8 in ops:                   # 画点
            mv[i:i + 8] = px8
        ctypes.memmove(bits.value, src_view, STRIDE * H)   # bytearray → DIB，一次 624 KB
        g.BitBlt(hdc, 0, 0, W, H, hdc, 0, 0, 0)   # 自拷贝，代表上行到屏幕的那次 blit
    dt = time.perf_counter() - t0
    per = dt / N * 1000
    print("每帧 %.2f ms  →  理论上限 %.0f fps" % (per, 1000 / per))
    print("200 帧总耗时 %.3f s" % dt)

    g.DeleteObject(hbmp)
    g.DeleteDC(hdc)
    u.ReleaseDC(0, hdc_screen)


if __name__ == "__main__":
    main()
