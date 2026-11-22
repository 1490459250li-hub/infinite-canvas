# -*- coding: utf-8 -*-
"""把发布目录做成一个「双击即装、覆盖即升级」的安装包。

产物：proto\\dist\\installer\\无限画布-Setup-<版本>.exe

它其实由两段拼起来：
    [安装器 stub.exe]  +  [程序本体 zip]  +  [40 字节尾标记]
尾标记记着 zip 的起始偏移和长度，stub 靠它把 zip 抽出来。PyInstaller 的
onefile 启动器是从文件尾反向找自己的 cookie，所以尾随数据不影响它运行
（已实测：尾部附加 5 MB 后 exe 照常启动）。

用法：
    python installer/make_setup.py                      # 自动找最新 dist 目录
    python installer/make_setup.py --src proto/dist/无限画布-v3.8.1-win64/无限画布
    python installer/make_setup.py --skip-stub          # 复用上次的 stub，只重打载荷
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TAIL_MAGIC = b"SNCSETUP"
TAIL = struct.Struct("<8s16sQQ")
SKIP_NAMES = {".env", ".env.bak", ".env.example"}


def app_version() -> str:
    path = os.path.join(ROOT, "proto", "server.py")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    hit = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', text, re.M)
    if not hit:
        raise SystemExit("在 proto/server.py 里没找到 APP_VERSION")
    return hit.group(1)


def newest_dist() -> str:
    """定位要打包的 onedir 产物。

    优先用 proto/dist/无限画布 —— 那才是 PyInstaller 刚写出来的目录。
    以前这里只按「目录名里的版本号最大」挑，而 dist/无限画布 不带版本号、
    算出来是 (0,0,0)，于是永远输给上一版拼好的 dist/无限画布-vX-win64/无限画布：
    3.8.5 就是这么把 3.8.4 的整棵树（含旧 canvas.html）打进安装包的。
    """
    base = os.path.join(ROOT, "proto", "dist")
    fresh = os.path.join(base, "无限画布")
    if os.path.isfile(os.path.join(fresh, "无限画布.exe")):
        return fresh
    best, best_key = "", None
    for name in os.listdir(base):
        path = os.path.join(base, name, "无限画布")
        if not os.path.isfile(os.path.join(path, "无限画布.exe")):
            continue
        nums = [int(x) for x in re.findall(r"\d+", name)[:3]] or [0]
        while len(nums) < 3:
            nums.append(0)
        if best_key is None or tuple(nums) > best_key:
            best, best_key = path, tuple(nums)
    if not best:
        raise SystemExit("proto/dist 下没找到已打包的发布目录")
    return best


def guard_freshness(src: str) -> None:
    """拦「拿旧目录出包」：src 里的 canvas.html 必须和 proto/canvas.html 一模一样。

    canvas.html 是 obfuscate.mjs 的产物，PyInstaller 会把它摊到 _internal 下。
    一旦 src 指向上一次拼好的发布目录，页面就是旧的，装完还看得见已经删掉的 UI。
    直接比对哈希，比事后翻截图可靠。
    """
    built = os.path.join(ROOT, "proto", "canvas.html")
    packed = os.path.join(src, "_internal", "canvas.html")
    if not (os.path.isfile(built) and os.path.isfile(packed)):
        return
    with open(built, "rb") as fh:
        a = hashlib.sha256(fh.read()).hexdigest()
    with open(packed, "rb") as fh:
        b = hashlib.sha256(fh.read()).hexdigest()
    if a != b:
        raise SystemExit(
            "源目录的 canvas.html 与 proto/canvas.html 不一致，说明它是个旧目录：\n"
            "  src : %s\n  proto: %s\n"
            "先重新跑 PyInstaller（python -m PyInstaller 无限画布.spec），或用 --src 指到 proto/dist/无限画布。"
            % (packed, built))


def build_stub(force: bool) -> str:
    """把 setup_stub.py 打成单文件 exe；源码没变就复用。"""
    out_dir = os.path.join(HERE, "build")
    stub = os.path.join(out_dir, "snc_setup.exe")
    src = os.path.join(HERE, "setup_stub.py")
    if not force and os.path.isfile(stub) and os.path.getmtime(stub) >= os.path.getmtime(src):
        print("复用安装器 stub：%s" % stub)
        return stub
    os.makedirs(out_dir, exist_ok=True)
    icon = os.path.join(ROOT, "proto", "app.ico")
    cmd = [sys.executable, "-m", "PyInstaller", "--onefile", "--noconsole",
           "--name", "snc_setup", "--distpath", out_dir,
           "--workpath", os.path.join(out_dir, "work"),
           "--specpath", out_dir, "--noconfirm", "--clean"]
    if os.path.isfile(icon):
        cmd += ["--icon", icon]
    cmd.append(src)
    print("正在打包安装器 stub …")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.isfile(stub):
        sys.stderr.write(res.stdout[-3000:] + "\n" + res.stderr[-3000:])
        raise SystemExit("安装器 stub 打包失败")
    return stub


def build_payload(src_dir: str, version: str, out_zip: str) -> int:
    """把程序目录压成 zip，外层保留 无限画布-v<版本>-win64/无限画布 结构。"""
    top = "无限画布-v%s-win64" % version
    count = 0
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for base, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", "releases")]
            for fn in files:
                if fn in SKIP_NAMES or fn.endswith(".log"):
                    continue
                full = os.path.join(base, fn)
                rel = os.path.relpath(full, src_dir).replace(os.sep, "/")
                zf.write(full, "%s/无限画布/%s" % (top, rel))
                count += 1
    return count


def assemble(stub: str, payload: str, version: str, out_exe: str) -> None:
    with open(stub, "rb") as fh:
        head = fh.read()
    size = os.path.getsize(payload)
    ver = version.encode("ascii", "replace")[:15]
    tmp = out_exe + ".part"
    with open(tmp, "wb") as out:
        out.write(head)
        with open(payload, "rb") as src:
            shutil.copyfileobj(src, out, 1 << 20)
        out.write(TAIL.pack(TAIL_MAGIC, ver, len(head), size))
    os.replace(tmp, out_exe)


def digest(path: str) -> tuple:
    md5 = hashlib.md5()
    sha = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            md5.update(block)
            sha.update(block)
    return md5.hexdigest(), sha.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="", help="含 无限画布.exe 的目录")
    ap.add_argument("--version", default="")
    ap.add_argument("--skip-stub", action="store_true", help="复用已有 stub")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    version = args.version or app_version()
    src = os.path.abspath(args.src) if args.src else newest_dist()
    if not os.path.isfile(os.path.join(src, "无限画布.exe")):
        raise SystemExit("源目录里没有 无限画布.exe：%s" % src)
    guard_freshness(src)
    print("源目录 : %s" % src)

    # PyInstaller 刚出的目录里没有 update.json（那是发布清单，不是打包产物）。
    # 装完的程序要能「检查更新」，就得把 proto/update.json 一起带进去。
    manifest = os.path.join(ROOT, "proto", "update.json")
    if os.path.isfile(manifest):
        shutil.copyfile(manifest, os.path.join(src, "update.json"))
        print("清单   : update.json -> %s" % version)

    stub = build_stub(force=not args.skip_stub)
    tmp_zip = os.path.join(HERE, "build", "payload.zip")
    os.makedirs(os.path.dirname(tmp_zip), exist_ok=True)
    n = build_payload(src, version, tmp_zip)
    print("载荷：%d 个文件，%.1f MB" % (n, os.path.getsize(tmp_zip) / 1048576))

    out_exe = args.out or os.path.join(ROOT, "proto", "dist", "installer",
                                       "无限画布-Setup-%s.exe" % version)
    os.makedirs(os.path.dirname(out_exe), exist_ok=True)
    assemble(stub, tmp_zip, version, out_exe)
    md5, sha = digest(out_exe)
    size = os.path.getsize(out_exe)

    print("")
    print("安装包 : %s" % out_exe)
    print("版本   : %s" % version)
    print("大小   : %d B (%.1f MB)" % (size, size / 1048576))
    print("md5    : %s" % md5)
    print("sha256 : %s" % sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
