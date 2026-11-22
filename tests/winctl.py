"""临时工具：强制激活窗口、按客户区坐标点击、读窗口状态。

为什么需要 AttachThreadInput：SetForegroundWindow 对非前台进程有系统级限制，
单独调用经常被忽略，截屏/点击就会落到别的窗口上。
"""
import ctypes
import time
from ctypes import wintypes

u = ctypes.windll.user32
k = ctypes.windll.kernel32
u.SetProcessDPIAware()

SW_MINIMIZE = 6
SW_RESTORE = 9


def activate(hwnd: int) -> bool:
    """把窗口顶到前台。先最小化再还原，绕开系统的前台锁。"""
    u.ShowWindow(hwnd, SW_MINIMIZE)
    time.sleep(0.12)
    u.ShowWindow(hwnd, SW_RESTORE)
    time.sleep(0.12)
    fg = u.GetForegroundWindow()
    tid_fg = u.GetWindowThreadProcessId(fg, None)
    tid_me = k.GetCurrentThreadId()
    attached = False
    try:
        if tid_fg and tid_fg != tid_me:
            attached = bool(u.AttachThreadInput(tid_me, tid_fg, True))
        u.SetForegroundWindow(hwnd)
        u.BringWindowToTop(hwnd)
    finally:
        if attached:
            u.AttachThreadInput(tid_me, tid_fg, False)
    time.sleep(0.35)
    return u.GetForegroundWindow() == hwnd


def rect(hwnd: int):
    r = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom, r.right - r.left, r.bottom - r.top


def client_size(hwnd: int):
    c = wintypes.RECT()
    u.GetClientRect(hwnd, ctypes.byref(c))
    return c.right - c.left, c.bottom - c.top


def click_client(hwnd: int, x: int, y: int):
    """按客户区坐标点击（不受窗口位置影响）。"""
    pt = wintypes.POINT(x, y)
    u.ClientToScreen(hwnd, ctypes.byref(pt))
    u.SetCursorPos(pt.x, pt.y)
    time.sleep(0.18)
    u.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.06)
    u.mouse_event(0x0004, 0, 0, 0, 0)
    return pt.x, pt.y


def state(hwnd: int) -> dict:
    return {"zoomed": bool(u.IsZoomed(hwnd)), "iconic": bool(u.IsIconic(hwnd)),
            "rect": rect(hwnd), "client": client_size(hwnd),
            "foreground": u.GetForegroundWindow() == hwnd}
