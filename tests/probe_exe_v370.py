# -*- coding: utf-8 -*-
"""打包件验收：/api/health 版本号、/.env 404、内嵌 canvas.html 与源文件一致、
exe 同目录的 update.json 能被读出来（v3.7.4 起产物是 onedir，路径多一层）。
WANT 直接读 proto/update.json 的 latest，升版时不用改测试。

用法：python tests/probe_exe_v370.py
"""
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# v3.7.4 起是 onedir：exe 在 dist\无限画布\ 里，静态资源在 _internal\。
# 发版后目录常被改名成 无限画布-vX.Y.Z-win64\无限画布\，而且 dist\无限画布\
# 可能留着早期版本的旧 exe —— 所以不看目录名，一律取 mtime 最新的那个，
# 否则验收会打到旧包上，报「版本不对 / 页面 md5 不一致」的假红。
SRC = os.path.join(ROOT, "proto", "canvas.html")
import glob  # noqa: E402
_cands = glob.glob(os.path.join(ROOT, "proto", "dist", "*", "无限画布", "无限画布.exe"))
EXE = max(_cands, key=os.path.getmtime) if _cands else \
    os.path.join(ROOT, "proto", "dist", "无限画布", "无限画布.exe")
MANIFEST = os.path.join(os.path.dirname(EXE), "update.json")
# 期望版本直接跟发版清单走，升版时不用再回来改这条常量
with open(os.path.join(ROOT, "proto", "update.json"), encoding="utf-8") as _f:
    WANT = json.loads(_f.read())["latest"]

# 本机请求必须绕开系统代理，否则会走 6688 之类的中转
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def get(base, path, timeout=4):
    try:
        with OPENER.open(base + path, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # noqa: BLE001
        return -1, repr(e).encode()


def main():
    if not os.path.exists(EXE):
        print("FAIL: exe 不存在 %s" % EXE)
        return 1
    size = os.path.getsize(EXE)
    print("exe: %s  %.1f MB (%d B)" % (EXE, size / 1048576.0, size))

    port = free_port()
    base = "http://127.0.0.1:%d" % port
    # 用 app 模式（无边框 Edge）会真开窗；这里只用它把服务拉起来，验完就杀
    proc = subprocess.Popen([EXE, "--port", str(port), "--window", "native"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    up = False
    for _ in range(120):
        code, _b = get(base, "/api/health", timeout=1)
        if code == 200:
            up = True
            break
        time.sleep(0.25)
    if not up:
        proc.kill()
        print("FAIL: 服务 30s 内没起来")
        return 1

    fails = []

    # 1) /api/health
    code, body = get(base, "/api/health")
    try:
        h = json.loads(body.decode("utf-8"))
    except Exception:  # noqa: BLE001
        h = {}
    ver = h.get("version") or h.get("appVersion") or ""
    print("health: status=%d ok=%s version=%s" % (code, h.get("ok"), ver or "(无字段)"))
    if code != 200:
        fails.append("health 状态码 %d" % code)
    if ver and ver != WANT:
        fails.append("health 版本 %r != %s" % (ver, WANT))

    # 2) /.env 必须拿不到
    for p in ("/.env", "/proto/.env", "/.git/config"):
        c, _ = get(base, p)
        print("%-14s -> %d" % (p, c))
        if c not in (403, 404):
            fails.append("%s 返回 %d（应为 404/403）" % (p, c))

    # 3) 内嵌 canvas.html 与源文件逐字节一致
    code, body = get(base, "/canvas.html", timeout=20)
    m_served = hashlib.md5(body).hexdigest()
    with open(SRC, "rb") as f:
        raw = f.read()
    m_src = hashlib.md5(raw).hexdigest()
    print("canvas.html: status=%d served=%d B md5=%s" % (code, len(body), m_served))
    print("              source=%d B md5=%s" % (len(raw), m_src))
    if code != 200:
        fails.append("canvas.html 状态码 %d" % code)
    if m_served != m_src:
        fails.append("内嵌页面 md5 不一致")

    # 4) 版本号在页面里也露出来了
    html = body.decode("utf-8", "ignore")
    hit = "3.7" in html
    print("页面含 3.7 字样: %s" % hit)
    if not hit:
        fails.append("页面里找不到 3.7")

    # 5) 更新清单：exe 同目录的 update.json 必须读得到，且和本版一致
    #    这条以前没验过 —— 清单放错位置时前端只会说"未配置版本清单"，
    #    看起来像"没有新版本"，实际是文件没跟着发出去。
    code, body = get(base, "/api/update/check")
    try:
        u = json.loads(body.decode("utf-8"))
    except Exception:  # noqa: BLE001
        u = {}
    print("update: status=%d current=%s latest=%s hasUpdate=%s"
          % (code, u.get("current"), u.get("latest"), u.get("hasUpdate")))
    if code != 200:
        fails.append("/api/update/check 状态码 %d" % code)
    if not os.path.exists(MANIFEST):
        fails.append("exe 同目录没有 update.json")
    if u.get("latest") != WANT:
        fails.append("清单 latest=%r != %s" % (u.get("latest"), WANT))
    if u.get("hasUpdate"):
        fails.append("清单 latest 与本版相同却报 hasUpdate=True")
    if not str(u.get("notes") or "").strip():
        fails.append("清单 notes 是空的")

    # 6) 「打包不要保留 key」验的是分发物，不是用户本机填的 Key。
    #    exe 同目录的 .env 是首次启动后用户按提示自行粘贴的，属于本机数据，允许存在；
    #    真正要卡死的是 zip 里不能出现 .env。早先直接判运行目录，用户一填 Key 就误红。
    stray = os.path.join(os.path.dirname(EXE), ".env")
    print(".env 在本机运行目录: %s（用户自行填写，允许）" % os.path.exists(stray))
    zip_path = os.path.join(ROOT, "proto", "dist", "无限画布-v%s-win64.zip" % WANT)
    if os.path.exists(zip_path):
        with zipfile.ZipFile(zip_path) as zf:
            env_in_zip = [n for n in zf.namelist()
                          if n.replace("\\", "/") == ".env"
                          or n.replace("\\", "/").endswith("/.env")]
        print("分发 zip 内 .env: %s" % (env_in_zip or "无"))
        if env_in_zip:
            fails.append("分发 zip 里含 .env")
    else:
        print("分发 zip 未找到，跳过（非发版目录）")

    proc.terminate()
    try:
        proc.wait(timeout=8)
    except Exception:  # noqa: BLE001
        proc.kill()

    print("-" * 46)
    if fails:
        for f in fails:
            print("FAIL:", f)
        return 1
    print("PASS: 打包件验收全过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
