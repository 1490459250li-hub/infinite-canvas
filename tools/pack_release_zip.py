# -*- coding: utf-8 -*-
"""把发布目录打成 zip：保留 无限画布-v<版本>-win64/无限画布/ 结构，排除 releases。"""
import os
import sys
import zipfile

DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "proto", "dist")


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "3.8.14"
    top = "无限画布-v%s-win64" % version
    src = os.path.join(DIST, top)
    out = os.path.join(DIST, top + ".zip")
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d != "releases"]
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, src)
                z.write(full, os.path.join(top, rel))
                n += 1
    print("zip:", out)
    print("files:", n, "size: %.1f MB" % (os.path.getsize(out) / 1048576.0))
    chk = zipfile.ZipFile(out)
    bad = chk.testzip()
    print("integrity:", "OK" if bad is None else bad)
    print("has releases:", any("releases" in x for x in chk.namelist()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
