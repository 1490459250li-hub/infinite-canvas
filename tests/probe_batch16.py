# -*- coding: utf-8 -*-
"""v3.8.1 回归：单实例端口 / 配置位置 / 安装包 / 安装包式更新。

这一版改的都是"换个跑法会不会把数据弄丢"的地方，所以测试重点不是 UI，
而是四件事：
  A  同端口第二次启动必须复用已有窗口，绝不换端口（端口 = 存档的 origin）
  B  .env 落到 %LOCALAPPDATA%，老位置自动迁移（覆盖安装才不会丢密钥）
  C  更新既能吃 .exe 安装包，也能吃 .zip 绿色包，且 sha256 不匹配会删包
  D  安装包产物本身结构对：尾部有拿得到载荷的标记，载荷里有 exe、没有 .env

跑法：python tests/probe_batch16.py
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROTO = os.path.join(ROOT, "proto")
DIST = os.path.join(PROTO, "dist")

TMP = tempfile.mkdtemp(prefix="snc-p16-")
# 必须在 import server 之前改：UPDATE_DIR / LOG_PATH 都是模块级常量
os.environ["LOCALAPPDATA"] = TMP
os.environ["SNC_NO_MSG"] = "1"
sys.path.insert(0, PROTO)
import server  # noqa: E402

PASS = 0
FAIL = []


def check(name, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
        print("  PASS %s" % name)
    else:
        FAIL.append(name + ((" -> " + str(extra)) if extra else ""))
        print("  FAIL %s%s" % (name, (("  [" + str(extra) + "]") if extra else "")))


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


print("== A  单实例 / 端口稳定 ==")
srv = read(os.path.join(PROTO, "server.py"))
check("health 带 app 标识", '"app": "sensenova-canvas"' in srv)
check("空端口探测返回空串", server._probe_instance(59999, timeout=0.4) == "")
check("启动时先探测再用端口", "instance already running on port" in srv)
check("复用分支在 free_port 之前",
      srv.index("instance already running on port") < srv.index("port = free_port(args.port)"))
check("不拿 webbrowser 打开已有窗口（profile 不同，会看到空白）",
      "webbrowser.open(url)" not in srv[srv.index("if running:"):srv.index("port = free_port(args.port)")])
check("_focus_existing_window 不抛异常", server._focus_existing_window() in (True, False))
check("弹窗可被 SNC_NO_MSG 关掉", 'os.environ.get("SNC_NO_MSG")' in srv)

print("\n== B  配置位置 ==")
home_env = os.path.join(TMP, "SenseNovaCanvas", ".env")
legacy_env = os.path.join(server.app_dir(), ".env")
check("env_path 落在 LOCALAPPDATA", server.env_path() == home_env, server.env_path())
check("老位置的 .env 已迁移过来", os.path.isfile(home_env))
if os.path.isfile(legacy_env):
    check("迁移内容与原件一致",
          open(legacy_env, "rb").read() == open(home_env, "rb").read())
else:
    check("迁移内容与原件一致（本例无旧文件，跳过）", True)
before = os.path.getmtime(home_env)
server._ENV_PATH = None
server.env_path()
check("二次调用不重复复制", os.path.getmtime(home_env) == before)
check("README 不再教人把 .env 放程序目录（说明已更新）",
      "%LOCALAPPDATA%" in read(os.path.join(ROOT, "proto", "canvas.src.html")))

print("\n== C  更新：安装包与绿色包 ==")
script = server._setup_script(4242, r"C:\tmp\v9-setup.exe", r"C:\app\无限画布.exe")
check("替换脚本用 -Wait 等安装真正结束（GUI 程序不能用 & 调用）",
      "Start-Process -FilePath $setup" in script and "-Wait" in script)
check("替换脚本显式指定安装目录（否则绿色版会装出第二份）",
      '"/D=" + $dst' in script)
check("替换脚本等旧进程退出", "while ((Get-Process -Id $pid0" in script)
check("替换脚本装完把程序拉起来", "Start-Process -FilePath $exe" in script)
check("替换脚本清理安装包", "Remove-Item -LiteralPath $setup -Force" in script)

pkg_dir = os.path.join(PROTO, ".p16tmp")          # 放程序目录下：local: 只认相对路径
os.makedirs(pkg_dir, exist_ok=True)
src_pkg = os.path.join(pkg_dir, "fake-setup.exe")
with open(src_pkg, "wb") as fh:
    fh.write(b"MZ" + b"\0" * 4096)
sha = hashlib.sha256(open(src_pkg, "rb").read()).hexdigest()

dst = os.path.join(TMP, "downloaded.bin")
size, err = server._fetch_to(("file", src_pkg), dst)
check("本地包能取到", err == "" and size == 4098, "%s / %s" % (size, err))
check("sha256 对得上", server._verify_sha(dst, sha) == "")
check("sha256 对不上会删包", server._verify_sha(dst, "0" * 64) != "" and not os.path.isfile(dst))

# _clean_update_dir：只留指定那个
os.makedirs(server.UPDATE_DIR, exist_ok=True)
keep = os.path.join(server.UPDATE_DIR, "v9.9.9-setup.exe")
for name in ("v1.0.0.zip", "v1.0.0-setup.exe", "v9.9.9-setup.exe"):
    with open(os.path.join(server.UPDATE_DIR, name), "wb") as fh:
        fh.write(b"x")
server._clean_update_dir(keep)
left = sorted(fn for fn in os.listdir(server.UPDATE_DIR) if fn.endswith((".zip", ".exe")))
check("只清旧的升级包", left == ["v9.9.9-setup.exe"], left)

# 真跑一遍 update_download：临时把清单换成"发现 9.9.9 安装包"
manifest_path = os.path.join(PROTO, "update.json")
backup = open(manifest_path, "rb").read()
rel = os.path.relpath(src_pkg, server.app_dir()).replace(os.sep, "/")
try:
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"latest": "9.9.9", "url": "local:" + rel, "notes": "test",
                   "sha256": sha}, fh, ensure_ascii=False)
    got = server.update_download()
    check("发现 .exe 时走 setup 路线", got.get("kind") == "setup", got)
    check("升级包落盘且大小正确",
          got.get("ok") and os.path.isfile(got.get("setup") or "")
          and os.path.getsize(got["setup"]) == 4098, got)
    check("未把 .exe 当 zip 解压", not os.path.isfile(os.path.join(server.UPDATE_DIR,
                                                              "v9.9.9.zip")))
finally:
    with open(manifest_path, "wb") as fh:
        fh.write(backup)
    import shutil
    shutil.rmtree(pkg_dir, ignore_errors=True)
check("测试结束后清单已还原", open(manifest_path, "rb").read() == backup)

print("\n== D  安装包产物 ==")
inst_dir = os.path.join(DIST, "installer")
cands = [os.path.join(inst_dir, fn) for fn in os.listdir(inst_dir)] \
    if os.path.isdir(inst_dir) else []
setups = [p for p in cands if p.endswith(".exe")]
check("安装包已生成", bool(setups), inst_dir)
if setups:
    setup_exe = max(setups, key=os.path.getmtime)
    tail = struct.Struct("<8s16sQQ")
    with open(setup_exe, "rb") as fh:
        fh.seek(-tail.size, os.SEEK_END)
        magic, ver, off, size = tail.unpack(fh.read(tail.size))
    check("尾部载荷标记正确", magic == b"SNCSETUP", magic)
    check("安装包版本与 APP_VERSION 一致",
          ver.rstrip(b"\0").decode("ascii") == server.APP_VERSION,
          ver.rstrip(b"\0").decode("ascii"))
    check("载荷偏移落在文件内", 0 < off < os.path.getsize(setup_exe) - size + 1)
    tmp_zip = os.path.join(TMP, "payload.zip")
    with open(setup_exe, "rb") as src, open(tmp_zip, "wb") as dstf:
        src.seek(off)
        left_bytes = size
        while left_bytes > 0:
            block = src.read(min(1 << 20, left_bytes))
            if not block:
                break
            dstf.write(block)
            left_bytes -= len(block)
    with zipfile.ZipFile(tmp_zip) as zf:
        names = zf.namelist()
    check("载荷里有主程序", any(n.endswith("无限画布.exe") for n in names))
    check("载荷里没有 .env", not any(n.endswith("/.env") or n == ".env" for n in names))
    check("载荷里有内嵌页面",
          any(n.endswith("_internal/canvas.html") for n in names))
    check("载荷条目数与发布目录相当", len(names) >= 70, len(names))

stub_src = read(os.path.join(ROOT, "installer", "setup_stub.py"))
check("安装器支持 /S 静默", '"/S"' in stub_src or "'/S'" in stub_src)
check("安装器覆盖时跳过 .env", 'SKIP_NAMES = {".env"' in stub_src)
check("安装器会关掉正在跑的实例", "taskkill" in stub_src)
check("安装器写卸载项但不碰存档",
      "SenseNovaCanvas，未删除" in stub_src or "未删除" in stub_src)
maker = read(os.path.join(ROOT, "installer", "make_setup.py"))
check("打包工具排除 .env", 'SKIP_NAMES = {".env"' in maker)

print("\n" + "-" * 46)
print("PASS %d  FAIL %d" % (PASS, len(FAIL)))
for item in FAIL:
    print("  - %s" % item)
sys.exit(1 if FAIL else 0)
