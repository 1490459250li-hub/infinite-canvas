"""临时工具：用 Win32 GDI 截取指定窗口的屏幕区域，存成 BMP。

为什么不用 PowerShell 的 System.Drawing：本机安全策略禁止运行时编译 .NET。
为什么不用 PrintWindow：WebView2 走 D3D 渲染，PrintWindow 常常截到全黑。
这里用 BitBlt 从屏幕抠窗口矩形，前提是窗口已在前台。
"""
import ctypes
import struct
import sys
from ctypes import wintypes

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

SW_RESTORE = 9
SW_SHOW = 5
SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def grab(hwnd: int, path: str, pad: int = 0, scale: int = 1,
         crop=None) -> str:
    """crop=(x, y, w, h) 相对窗口左上角；scale 为最近邻缩小倍数（1 = 原始像素）。"""
    user32.ShowWindow(hwnd, SW_RESTORE) if hwnd else None
    if hwnd:
        user32.SetForegroundWindow(hwnd)
    # 给窗口一点时间完成重绘与动画
    ctypes.windll.kernel32.Sleep(900)

    if hwnd:
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return "GetWindowRect failed"
        left, top = rect.left - pad, rect.top - pad
        w = rect.right - rect.left + pad * 2
        h = rect.bottom - rect.top + pad * 2
    else:
        # hwnd=0 表示整屏
        left, top = 0, 0
        w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

    hdc_screen = user32.GetDC(0)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    old = gdi32.SelectObject(hdc_mem, hbmp)
    gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, left, top, SRCCOPY)

    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = w
    info.bmiHeader.biHeight = -h          # 负数 = 自上而下，省一次翻转
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = 0

    buf = ctypes.create_string_buffer(w * h * 4)
    got = gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(info), DIB_RGB_COLORS)

    gdi32.SelectObject(hdc_mem, old)
    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(0, hdc_screen)

    if not got:
        return "GetDIBits failed"

    src = bytes(buf)
    src_w, src_h = w, h
    cx, cy, cw, ch = 0, 0, src_w, src_h
    if crop:
        cx, cy, cw, ch = crop
        cx = max(0, cx + pad)
        cy = max(0, cy + pad)
        cw = min(cw, src_w - cx)
        ch = min(ch, src_h - cy)

    step = max(1, int(scale))
    out_w, out_h = cw // step, ch // step
    rows = []
    for y in range(out_h):
        sy = cy + y * step
        base = sy * src_w * 4
        # 每 step 个像素取一个，整行切片再按步长取更省事
        line = bytearray()
        for x in range(out_w):
            off = base + (cx + x * step) * 4
            line += src[off:off + 4]
        rows.append(bytes(line))
    pixels = b"".join(rows)

    header = struct.pack("<2sIHHI", b"BM", 14 + 40 + len(pixels), 0, 0, 54)
    bih = struct.pack("<IiiHHIIiiII", 40, out_w, -out_h, 1, 32, 0, len(pixels), 0, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(header + bih + pixels)
    return "%dx%d (from %dx%d) at %d,%d -> %s" % (out_w, out_h, src_w, src_h, left, top, path)


if __name__ == "__main__":
    hwnd = int(sys.argv[1], 0)
    out = sys.argv[2]
    pad = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    scale = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    crop = None
    if len(sys.argv) > 5:
        crop = tuple(int(v) for v in sys.argv[5].split(","))
    print(grab(hwnd, out, pad, scale, crop))
