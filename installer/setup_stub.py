# -*- coding: utf-8 -*-
"""无限画布 · 自解压安装器（stub）

本文件不会单独分发：make_setup.py 会把它打成一个小 exe，然后在文件尾部附加
一个 zip（程序本体），最后写 24 字节尾标记指向那段 zip。

运行方式：
    无限画布-Setup-3.8.1.exe            图形界面安装（升级时默认沿用原目录）
    无限画布-Setup-3.8.1.exe /S         静默安装（一键更新用这个）
    无限画布-Setup-3.8.1.exe /S /D=路径 静默装到指定目录

设计上的三条硬约束：
  1. **不碰用户数据**。画布 / 技能 / MCP 在 %LOCALAPPDATA%\\SenseNovaCanvas，
     密钥也在那里（v3.8.1 起）。安装器只往程序目录写文件。
  2. **覆盖安装就是升级**。payload 里没有 .env，解压时也跳过 .env，所以
     无论装第几次，程序目录里的配置都不会被冲掉。
  3. **不留半截**。先把 zip 解到临时目录，确认主程序在，再逐个覆盖过去；
     中途失败不会把原来那份程序毁掉。
"""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile

TAIL_MAGIC = b"SNCSETUP"
# magic + 版本号（ASCII，补 \0）+ zip 起始偏移 + zip 字节数
TAIL = struct.Struct("<8s16sQQ")
APP_NAME = "无限画布"
APP_EXE = "无限画布.exe"


# ---------------------------------------------------------------- payload
def _self_path() -> str:
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return os.path.abspath(__file__)


def payload_span() -> tuple:
    """返回 (exe 路径, zip 起始偏移, zip 长度, 版本号)。"""
    exe = _self_path()
    with open(exe, "rb") as fh:
        fh.seek(-TAIL.size, os.SEEK_END)
        magic, ver, off, size = TAIL.unpack(fh.read(TAIL.size))
    if magic != TAIL_MAGIC:
        raise RuntimeError("这个文件不是无限画布安装包（缺少载荷标记）")
    if off <= 0 or size <= 0 or off + size > os.path.getsize(exe):
        raise RuntimeError("安装包已损坏（载荷越界）")
    return exe, off, size, ver.rstrip(b"\0").decode("ascii", "replace")


def extract_payload(dest_zip: str) -> None:
    """把尾部 zip 抽成一个独立文件 —— 直接让 zipfile 读 exe 会在 EOCD 偏移上踩坑。"""
    exe, off, size, _ver = payload_span()
    with open(exe, "rb") as src, open(dest_zip, "wb") as dst:
        src.seek(off)
        left = size
        while left > 0:
            block = src.read(min(1 << 20, left))
            if not block:
                break
            dst.write(block)
            left -= len(block)
    if left != 0:
        raise RuntimeError("读取安装包载荷不完整")


# ---------------------------------------------------------------- 环境
def local_appdata() -> str:
    return os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")


def data_home() -> str:
    return os.path.join(local_appdata(), "SenseNovaCanvas")


def default_dir() -> str:
    """默认装到 %LOCALAPPDATA%\\Programs\\无限画布（不需要管理员权限）。"""
    return os.path.join(local_appdata(), "Programs", APP_NAME)


def detect_install_dir() -> str:
    """升级时尽量装回原来那个目录，别把用户装出两份。"""
    cands = [
        default_dir(),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), APP_NAME),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), APP_NAME),
    ]
    try:
        import winreg
        for root, sub in ((winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\SenseNovaCanvas"),
                          (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\SenseNovaCanvas")):
            try:
                with winreg.OpenKey(root, sub) as key:
                    loc = winreg.QueryValueEx(key, "InstallLocation")[0]
                    if loc:
                        cands.insert(0, loc)
            except OSError:
                pass
    except Exception:
        pass
    for path in cands:
        if path and os.path.isfile(os.path.join(path, APP_EXE)):
            return path
    return default_dir()


def running_pids() -> list:
    """找正在跑的 无限画布.exe（安装前必须先关掉，否则 exe 是只读的）。"""
    pids = []
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq " + APP_EXE, "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=15,
            creationflags=0x08000000,           # CREATE_NO_WINDOW
        ).stdout or ""
        for line in out.splitlines():
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) >= 2 and parts[0].strip('"') == APP_EXE:
                try:
                    pids.append(int(parts[1]))
                except ValueError:
                    pass
    except Exception:
        pass
    return pids


def close_app(timeout: float = 8.0) -> bool:
    """先礼后兵：先发关闭，等一会儿；还在就强杀。返回是否真的关掉了。"""
    if not running_pids():
        return True
    subprocess.run(["taskkill", "/IM", APP_EXE, "/T"], capture_output=True,
                   creationflags=0x08000000)
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not running_pids():
            return True
        time.sleep(0.3)
    subprocess.run(["taskkill", "/F", "/IM", APP_EXE, "/T"], capture_output=True,
                   creationflags=0x08000000)
    time.sleep(0.6)
    return not running_pids()


# ---------------------------------------------------------------- 安装
SKIP_NAMES = {".env", ".env.bak"}


def install(payload_zip: str, target: str, log=None) -> None:
    """解压覆盖。payload 里本来就没有 .env，这里再挡一次是防止有人手工塞进去。"""
    say = log or (lambda _m: None)
    tmp = tempfile.mkdtemp(prefix="snc-setup-")
    try:
        say("正在解压程序文件…")
        with zipfile.ZipFile(payload_zip) as zf:
            zf.extractall(tmp)
        # payload 里包了一层版本目录，找到真正含主程序的那一层
        root = tmp
        if not os.path.isfile(os.path.join(root, APP_EXE)):
            hits = []
            for base, _dirs, files in os.walk(tmp):
                if APP_EXE in files:
                    hits.append(base)
            if not hits:
                raise RuntimeError("安装包里找不到 %s" % APP_EXE)
            hits.sort(key=len)
            root = hits[0]
        # 先确认拷得动，再动手
        os.makedirs(target, exist_ok=True)
        probe = os.path.join(target, ".snc_write_test")
        try:
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write("ok")
            os.remove(probe)
        except OSError as exc:
            raise RuntimeError("目标目录不可写：%s\n\n换一个目录，或用管理员身份运行。" % exc)

        say("正在写入 %s …" % target)
        for base, _dirs, files in os.walk(root):
            rel = os.path.relpath(base, root)
            out_dir = target if rel == "." else os.path.join(target, rel)
            os.makedirs(out_dir, exist_ok=True)
            for fn in files:
                if fn in SKIP_NAMES or fn.endswith(".log"):
                    continue
                shutil.copy2(os.path.join(base, fn), os.path.join(out_dir, fn))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def migrate_env(target: str) -> bool:
    """程序目录里如果有老配置，搬一份到 %LOCALAPPDATA%（新版从这里读）。"""
    src = os.path.join(target, ".env")
    dst = os.path.join(data_home(), ".env")
    if not os.path.isfile(src) or os.path.isfile(dst):
        return False
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        return True
    except OSError:
        return False


def make_shortcut(link: str, exe: str, workdir: str) -> bool:
    """用 WScript.Shell 建 .lnk（不需要 pywin32）。"""
    ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                      "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
        "$s.TargetPath='%s';$s.WorkingDirectory='%s';"
        "$s.IconLocation='%s,0';$s.Description='%s';$s.Save()"
    ) % (link.replace("'", "''"), exe.replace("'", "''"),
         workdir.replace("'", "''"), exe.replace("'", "''"), APP_NAME)
    try:
        subprocess.run([ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-Command", script],
                       capture_output=True, timeout=25, creationflags=0x08000000)
        return os.path.isfile(link)
    except Exception:
        return False


def write_uninstall(target: str, version: str) -> None:
    """写注册表卸载项 + 一个卸载脚本（只删程序，不动画布）。"""
    cmd = os.path.join(target, "卸载无限画布.cmd")
    body = "\r\n".join([
        "@echo off",
        "chcp 65001 >nul",
        "echo 正在卸载无限画布…",
        'taskkill /F /IM "%s" /T >nul 2>nul' % APP_EXE,
        'del /f /q "%s" >nul 2>nul' % os.path.join(
            os.environ.get("USERPROFILE", ""), "Desktop", APP_NAME + ".lnk"),
        'del /f /q "%s" >nul 2>nul' % os.path.join(
            os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs", APP_NAME + ".lnk"),
        'reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\SenseNovaCanvas" /f >nul 2>nul',
        'cd /d "%%TEMP%%"',
        'rd /s /q "%s" >nul 2>nul' % target,
        "echo.",
        "echo 已卸载。画布存档、技能、密钥仍在 %%LOCALAPPDATA%%\\SenseNovaCanvas，未删除。",
        "echo 需要彻底清空就手动删掉那个文件夹。",
        "pause",
        "",
    ])
    try:
        with open(cmd, "w", encoding="utf-8-sig", newline="") as fh:
            fh.write(body)
    except OSError:
        pass
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\SenseNovaCanvas"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, version)
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, target)
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ,
                              os.path.join(target, APP_EXE))
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, '"%s"' % cmd)
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
    except Exception:
        pass


def do_install(target: str, version: str, log=None, shortcuts: bool = True) -> str:
    """完整安装流程。返回最终目录。

    自动化测试用 SNC_SETUP_NOSHORTCUT / SNC_SETUP_NOREG 关掉副作用，
    免得测一次就往真实桌面和注册表里塞东西。
    """
    say = log or (lambda _m: None)
    shortcuts = shortcuts and not os.environ.get("SNC_SETUP_NOSHORTCUT")
    say("正在关闭已运行的无限画布…")
    if not close_app():
        raise RuntimeError("无限画布还在运行，关不掉。\n请手动退出（含右下角托盘图标）后再试。")
    tmp_zip = os.path.join(tempfile.gettempdir(), "snc-payload-%d.zip" % os.getpid())
    try:
        extract_payload(tmp_zip)
        install(tmp_zip, target, say)
    finally:
        try:
            os.remove(tmp_zip)
        except OSError:
            pass
    if migrate_env(target):
        say("已把程序目录里的密钥搬到用户目录。")
    if shortcuts:
        say("正在创建快捷方式…")
        exe = os.path.join(target, APP_EXE)
        desk = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
        start = os.path.join(os.environ.get("APPDATA", ""),
                             r"Microsoft\Windows\Start Menu\Programs")
        for folder in (desk, start):
            if folder and os.path.isdir(folder):
                make_shortcut(os.path.join(folder, APP_NAME + ".lnk"), exe, target)
    if not os.environ.get("SNC_SETUP_NOREG"):
        write_uninstall(target, version)
    say("安装完成。")
    return target


# ---------------------------------------------------------------- 界面
# 这里刻意不用 tkinter：打包机的 Python 不一定带 tk（这台就没有，
# pyinstaller 日志里是 missing module named tkinter），一 import 就崩，
# 崩了还会被 except 悄悄退化成"直接装到默认目录"——用户什么都没看见，
# 桌面上突然多了个快捷方式，比没有界面更糟。
# 系统原生的 MessageBox 一定在，两三个对话框就能把话说清楚。
MB_YESNO = 0x00000004
MB_OK = 0x00000000
MB_ICONQUESTION = 0x00000020
MB_ICONINFORMATION = 0x00000040
MB_ICONERROR = 0x00000010
MB_SETFOREGROUND = 0x00010000
IDYES = 6


def msgbox(text: str, title: str, flags: int = MB_OK | MB_ICONINFORMATION) -> int:
    if os.name != "nt":
        print(text)
        return IDYES
    try:
        import ctypes
        return int(ctypes.windll.user32.MessageBoxW(0, text, title, flags | MB_SETFOREGROUND))
    except Exception:
        print(text)
        return IDYES


def run_dialog(version: str) -> int:
    """双击进入：确认 → 安装 → 问要不要启动。"""
    target = detect_install_dir()
    upgrading = os.path.isfile(os.path.join(target, APP_EXE))
    busy = bool(running_pids())

    head = ("要把无限画布 %s 装到：\n\n%s\n\n" % (version, target))
    if upgrading:
        head = ("检测到已安装的版本，将就地升级到 %s：\n\n%s\n\n" % (version, target))
    tail = ("画布、技能、MCP 连接都在 %LOCALAPPDATA%\\SenseNovaCanvas，\n"
            "密钥也在那里 —— 这次安装不会动它们。\n\n")
    if busy:
        tail += "注意：程序正在运行，会先请它关闭（请确认已保存）。\n\n"
    if msgbox(head + tail + "继续安装吗？", APP_NAME + " 安装",
              MB_YESNO | MB_ICONQUESTION) != IDYES:
        return 0

    msgs = []
    try:
        do_install(target, version, log=msgs.append)
    except Exception as exc:
        msgbox("安装失败：\n\n%s\n\n如果提示文件被占用，请先从右下角托盘退出无限画布再试。" % exc,
               APP_NAME + " 安装失败", MB_OK | MB_ICONERROR)
        return 1

    if msgbox("安装完成（%s）。\n\n现在启动吗？" % target, APP_NAME,
              MB_YESNO | MB_ICONINFORMATION) == IDYES:
        try:
            subprocess.Popen([os.path.join(target, APP_EXE)], cwd=target)
        except Exception:
            pass
    return 0


def app_version() -> str:
    try:
        return payload_span()[3] or ""
    except Exception:
        return ""


def run_silent(argv) -> int:
    version = app_version()
    dest = detect_install_dir()
    for item in argv:
        if item.upper().startswith("/D="):
            dest = item[3:].strip('"')
    try:
        # 静默这条路是给「一键更新」用的：用户只是在程序里点了下升级，
        # 桌面不该突然多出个图标，所以不建快捷方式（GUI 安装仍会建）。
        target = do_install(dest, version or "?", log=lambda m: print(m, flush=True),
                            shortcuts=False)
        print("OK %s" % target, flush=True)
        return 0
    except Exception as exc:
        print("FAIL %s" % exc, flush=True)
        return 1


def main(argv=None):
    # 静默模式由一键更新调用，输出会被父进程收走：不指定编码就是 GBK，
    # 中文全是乱码，出问题时根本看不出卡在哪一步。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    argv = list(sys.argv[1:] if argv is None else argv)
    flags = [a.upper() for a in argv]
    silent = any(a in ("/S", "--SILENT", "-S", "/SILENT") for a in flags)
    if silent:
        return run_silent(argv)
    try:
        return run_dialog(app_version() or "最新版")
    except Exception as exc:
        msgbox("安装程序出错：\n\n%s" % exc, APP_NAME, MB_OK | MB_ICONERROR)
        return 1


if __name__ == "__main__":
    sys.exit(main())
