# -*- coding: utf-8 -*-
"""校验安装包载荷：解出尾标记指向的 zip，逐个资源与源码比哈希。"""
import hashlib
import io
import os
import struct
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROTO = os.path.join(os.path.dirname(HERE), "proto")


def h(b):
    return hashlib.sha256(b).hexdigest()[:12]


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "3.8.14"
    exe = os.path.join(PROTO, "dist", "installer", "无限画布-Setup-%s.exe" % version)
    raw = open(exe, "rb").read()
    magic, ipver, zoff, zlen = struct.unpack("8s16sQQ", raw[-40:])
    print("package", os.path.basename(exe), len(raw), "B")
    print("trailer", magic, ipver.decode("utf-8", "ignore").strip("\0"), zoff, zlen)
    z = zipfile.ZipFile(io.BytesIO(raw[zoff:zoff + zlen]))
    names = z.namelist()
    top = "无限画布-v%s-win64/无限画布/" % version
    print("files", len(names), "prefix ok:", all(n.startswith(top) for n in names))
    pairs = [("_internal/canvas.html", "canvas.html"),
             ("_internal/splash.dat", "splash.dat"),
             ("_internal/app.ico", "app.ico"),
             ("_internal/mark.png", "mark.png"),
             ("update.json", "update.json")]
    ok = True
    for inner, src in pairs:
        a = z.read(top + inner)
        b = open(os.path.join(PROTO, src), "rb").read()
        same = a == b
        ok = ok and same
        print("%-22s %9d %s %s" % (inner, len(a), h(a), "SAME" if same else "DIFF"))
    print("RESULT", "OK" if ok else "MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
