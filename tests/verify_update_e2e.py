# -*- coding: utf-8 -*-
"""一键更新全链路实测（手动跑，不进 run_all —— 它真的要替换文件、会起进程）。

⚠️ 只能从「已经带了更新接口的版本」（v3.8.0 起）向后验：
   3.7.9 里没有 /api/update/download，新功能没法给已发出的旧二进制打补丁，
   那一步只能手动换一次文件夹。

做法：把 3.8.0 发布包复制到临时目录当「当前版本」，再把另一个真实发布包
（默认 3.7.9）改名成 v9.9.9 的升级包 —— 这样只验替换机制，不依赖真有 9.9.9。
然后启动 3.8.0 的 exe，调 /api/update/download 与 /api/update/apply，
验证「进程退出 → 程序目录被替换 → .env 仍在 → 新版被拉起」。

全程在临时目录里发生，本机真实安装目录与 %LOCALAPPDATA% 都不参与
（LOCALAPPDATA 在子进程里被改成临时目录）。

跑法：
    python tests/verify_update_e2e.py --old "proto/dist/无限画布-v3.8.0-win64" \
                                     --payload "proto/dist/无限画布-v3.7.9-win64"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

PASS = FAIL = 0


def check(name, ok, extra=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  PASS", name)
    else:
        FAIL += 1
        print("  FAIL", name, "->", extra)


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def get(url, timeout=3):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def post(url, timeout=180):
    req = urllib.request.Request(url, data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True, help="当前版本目录（必须自带更新接口，v3.8.0+）")
    ap.add_argument("--payload", required=True, help="用作「新版」内容的真实发布目录")
    ap.add_argument("--version", default="9.9.9", help="假装的新版本号")
    args = ap.parse_args()
    old_pkg = os.path.abspath(args.old)
    payload_pkg = os.path.abspath(args.payload)
    root = tempfile.mkdtemp(prefix="snc-upd-e2e-")
    app_root = os.path.join(root, "app")
    os.makedirs(app_root, exist_ok=True)
    # 复制「当前版本」（onedir 结构：无限画布.exe + _internal）
    src_dir = os.path.join(old_pkg, "无限画布")
    if not os.path.isdir(src_dir):
        print("旧版目录不对：%s" % src_dir)
        return 2
    shutil.copytree(src_dir, os.path.join(app_root, "无限画布"))
    exe = os.path.join(app_root, "无限画布", "无限画布.exe")
    exe_md5_old = md5(exe)
    # 造一个假 .env，验证升级后还在
    env_file = os.path.join(app_root, "无限画布", ".env")
    with open(env_file, "w", encoding="utf-8") as fh:
        fh.write("SNC_TEST_MARK=keep-me\n")

    print("临时目录 : %s" % root)
    print("当前版本 : %s (%s)" % (exe, exe_md5_old[:12]))

    print("\n[0] 把 payload 打成 v%s 的升级包" % args.version)
    new_zip = os.path.join(root, "无限画布-v%s-win64.zip" % args.version)
    payload_dir = os.path.join(payload_pkg, "无限画布")
    if not os.path.isdir(payload_dir):
        print("payload 目录不对：%s" % payload_dir)
        return 2
    with zipfile.ZipFile(new_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for base, _d, files in os.walk(payload_pkg):
            for fn in files:
                if fn == ".env":
                    continue
                full = os.path.join(base, fn)
                rel = os.path.relpath(full, payload_pkg)
                zf.write(full, os.path.join("无限画布-v%s-win64" % args.version, rel))
    check("升级包已生成", os.path.isfile(new_zip), new_zip)

    print("\n[1] 摆升级包 + 写清单")
    rc = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools", "stage_update.py"),
        "--app", os.path.join(app_root, "无限画布"), "--zip", new_zip,
        "--notes", "e2e probe"], capture_output=True, text=True)
    print("   ", rc.stdout.strip().splitlines()[-1] if rc.stdout.strip() else rc.stderr[:200])
    check("stage_update 返回 0", rc.returncode == 0, rc.stderr[-200:])
    manifest = json.load(open(os.path.join(app_root, "无限画布", "update.json"), encoding="utf-8"))
    check("清单 latest 指向新版", manifest.get("latest") not in ("", None), manifest)

    port = free_port()
    base = "http://127.0.0.1:%d" % port
    env = dict(os.environ)
    env["LOCALAPPDATA"] = os.path.join(root, "localapp")
    os.makedirs(env["LOCALAPPDATA"], exist_ok=True)
    print("\n[2] 启动旧版 exe（端口 %d，LOCALAPPDATA 已隔离）" % port)
    proc = subprocess.Popen([exe, "--port", str(port), "--window", "browser", "--no-open"],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    health = None
    for _ in range(120):
        try:
            health = get(base + "/api/health")
            break
        except Exception:
            if proc.poll() is not None:
                break
            time.sleep(0.5)
    check("旧版起来了", bool(health), str(health))
    old_ver = (health or {}).get("version", "")
    print("    旧版版本：", old_ver)

    print("\n[3] 下载升级包")
    dl = post(base + "/api/update/download")
    check("下载成功", dl.get("ok") is True, str(dl)[:200])
    check("下载到的是新版", str(dl.get("version")) == manifest.get("latest"), str(dl.get("version")))
    check("解压后找到 exe", os.path.isfile(dl.get("exe") or ""), dl.get("exe", ""))

    print("\n[4] 触发替换（真实退出 → robocopy → 重启）")
    ap_ = post(base + "/api/update/apply")
    check("替换进程已拉起", ap_.get("ok") is True, str(ap_)[:200])
    # 模拟前端 win_quit：让旧进程退出，替换脚本才会往下走
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    check("旧进程已退出", proc.poll() is not None)

    # 等替换完成
    exe_new_md5 = None
    try:
        with zipfile.ZipFile(new_zip) as zf:
            for n in zf.namelist():
                if n.endswith("无限画布.exe"):
                    import io
                    with zf.open(n) as fh:
                        h = hashlib.md5()
                        for b in iter(lambda: fh.read(1 << 20), b""):
                            h.update(b)
                        exe_new_md5 = h.hexdigest()
                    break
    except Exception as exc:
        print("    读新包算 md5 失败：", exc)

    swapped = False
    for _ in range(80):
        time.sleep(0.5)
        try:
            if exe_new_md5 and md5(exe) == exe_new_md5:
                swapped = True
                break
        except OSError:
            pass
    check("程序目录已被替换成新版", swapped,
          "期望 %s 实得 %s" % ((exe_new_md5 or "?")[:12],
                              (md5(exe)[:12] if os.path.isfile(exe) else "文件不见了")))
    check("旧 .env 还在且内容未变",
          os.path.isfile(env_file) and "keep-me" in open(env_file, encoding="utf-8").read())
    check("新版 update.json 已就位",
          json.load(open(os.path.join(app_root, "无限画布", "update.json"),
                         encoding="utf-8")).get("latest") == manifest.get("latest"))

    print("\n[5] 收尾：关掉自动拉起的新版进程")
    killed = 0
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                             text=True, errors="ignore").stdout
        for line in out.splitlines():
            if "无限画布.exe" in line:
                pid = line.split(",")[1].strip('"')
                subprocess.run(["taskkill", "/F", "/PID", pid],
                               capture_output=True)
                killed += 1
    except Exception as exc:
        print("    收尾清理失败（手动关一下）：", exc)
    print("    已结束 %d 个进程" % killed)

    log_path = os.path.join(env["LOCALAPPDATA"], "SenseNovaCanvas", "update.log")
    if os.path.isfile(log_path):
        print("\n[替换日志]")
        for line in open(log_path, encoding="utf-8", errors="replace").read().splitlines()[-12:]:
            print("   ", line)
        check("替换日志里有 swap 记录", "swap start" in open(log_path, encoding="utf-8",
                                                            errors="replace").read())

    # 临时目录留着便于排查，只提示位置
    print("\n临时目录保留在：%s" % root)
    print("----------------------------------------------")
    print("PASS %d  FAIL %d" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
