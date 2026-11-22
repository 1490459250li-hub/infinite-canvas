#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把新版本「摆」到某个已安装的程序目录旁，让旧版打开就能自己升级。

用法
----
    # 推荐：摆安装包（程序内点「下载并升级」会静默跑它）
    python tools/stage_update.py --app "proto/dist/无限画布-v3.7.6-win64/无限画布" \
        --pkg "proto/dist/installer/无限画布-Setup-3.8.1.exe" --notes "本次更新：…"

    # 绿色包也可以
    python tools/stage_update.py --app "<程序目录>" \
        --pkg "proto/dist/无限画布-v3.8.1-win64.zip"

它做三件事：
  1. 把包装进 <app>/releases/，各类包各留最近 3 个；
  2. 按包的实际内容写 <app>/update.json（latest / url / sha256 / size / notes）；
  3. 打印一句话，确认「旧版打开就能看到更新」。

之所以用 local: 前缀而不是 http：本项目没有固定分发服务器，
升级包直接放在程序目录的 releases 子目录里最省事（放共享盘、U 盘也一样能用）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def version_from_name(name: str) -> str:
    m = re.search(r"(\d+\.\d+\.\d+)", name)
    return m.group(1) if m else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True, help="目标程序目录（里面有 无限画布.exe）")
    ap.add_argument("--pkg", default="", help="新版安装包 .exe 或绿色包 .zip")
    ap.add_argument("--zip", dest="zip_legacy", default="", help="（旧参数）等同于 --pkg")
    ap.add_argument("--notes", default="", help="更新说明，写进清单")
    ap.add_argument("--version", default="", help="版本号，默认从文件名里取")
    ap.add_argument("--keep", type=int, default=3, help="releases 里每种包保留几个")
    ap.add_argument("--dry", action="store_true", help="只打印，不落盘")
    args = ap.parse_args()

    pkg = args.pkg or args.zip_legacy
    app = os.path.abspath(args.app)
    path = os.path.abspath(pkg) if pkg else ""
    if not os.path.isdir(app):
        print("程序目录不存在：%s" % app)
        return 2
    if not path or not os.path.isfile(path):
        print("升级包不存在：%s" % (path or "(未指定 --pkg)"))
        return 2
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".exe", ".zip"):
        print("只认 .exe 安装包或 .zip 绿色包，收到：%s" % ext)
        return 2
    ver = (args.version or version_from_name(os.path.basename(path))).strip()
    if not ver:
        print("认不出版本号，请用 --version 指定")
        return 2

    rel_dir = os.path.join(app, "releases")
    target = os.path.join(rel_dir, os.path.basename(path))
    rel_url = "local:releases/" + os.path.basename(path)
    sha = sha256_of(path)
    size = os.path.getsize(path)
    manifest = {
        "latest": ver,
        "notes": args.notes.strip() or ("v%s 更新" % ver),
        "url": rel_url,
        "sha256": sha,
        "size": size,
        "kind": "setup" if ext == ".exe" else "zip",
    }
    print("目标目录 : %s" % app)
    print("升级包   : %s (%d bytes, %s)" % (os.path.basename(path), size, ext))
    print("版本     : %s" % ver)
    print("sha256   : %s" % sha)
    print("清单 url : %s" % rel_url)
    if args.dry:
        print("\n[dry] 未写入任何文件")
        return 0

    os.makedirs(rel_dir, exist_ok=True)
    if os.path.abspath(target) != path:
        shutil.copy2(path, target)
    # 每种包各留最近几个，免得 releases 越堆越大
    for suffix in (".exe", ".zip"):
        olds = sorted(
            (os.path.join(rel_dir, fn) for fn in os.listdir(rel_dir)
             if fn.lower().endswith(suffix)),
            key=os.path.getmtime, reverse=True,
        )
        for stale in olds[max(1, args.keep):]:
            try:
                os.remove(stale)
            except OSError:
                pass
    with open(os.path.join(app, "update.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("\n已写入：%s" % os.path.join(app, "update.json"))
    print("已放入：%s" % target)
    print("旧版打开 → 设置 → 关于 → 检查更新，即可看到 v%s" % ver)
    return 0


if __name__ == "__main__":
    sys.exit(main())
