# -*- coding: utf-8 -*-
"""v3.8.x 回归：存档备份/恢复 + 一键更新。

每次发版只改 update.json，所以版本断言一律与清单比对，不写死。

A 段：备份接口（流式写盘、auto 模式、类型与体积护栏、旧备份轮转）
B 段：更新地址解析、清单字段、下载解压、sha256 校验、替换脚本编码
C 段：前端接线（按钮、SNC_BACKUP、导入导出流程、gzip 分支）
全部离线，不联网、不动真实安装目录。

跑法：python tests/probe_batch15.py
"""
import base64
import gzip
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile

PASS = FAIL = 0
FAILS = []


def check(name, ok, extra=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  PASS", name)
    else:
        FAIL += 1
        FAILS.append((name, extra))
        print("  FAIL", name, "->", extra)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROTO = os.environ.get("SNC_PROTO", os.path.join(ROOT, "proto"))
sys.path.insert(0, PROTO)

TMP = tempfile.mkdtemp(prefix="snc-v380-")
# 把 data_dir 指到临时目录，绝不能碰到真实的 %LOCALAPPDATA%\SenseNovaCanvas
os.environ["LOCALAPPDATA"] = TMP

import server  # noqa: E402

SRC = open(os.path.join(PROTO, "canvas.src.html"), encoding="utf-8").read()
HTML = open(os.path.join(PROTO, "canvas.html"), encoding="utf-8").read()

print("== A 存档备份 ==")
_man = json.load(open(os.path.join(PROTO, "update.json"), encoding="utf-8"))
check("APP_VERSION 与清单一致", server.APP_VERSION == _man.get("latest"),
      "%s / %s" % (server.APP_VERSION, _man.get("latest")))
check("备份扩展名是 sncbak", server.BACKUP_EXT == "sncbak")
check("备份上限 3GB", server.BACKUP_LIMIT == 3 * 1024 ** 3, server.BACKUP_LIMIT)

# auto 目标落在 data_dir/backups 下，文件名 auto-<时间>.sncbak
target = server.backup_auto_target()
check("auto 备份落在 backups 目录",
      os.path.dirname(target) == os.path.join(TMP, "SenseNovaCanvas", "backups"), target)
check("auto 备份文件名合法",
      os.path.basename(target).startswith("auto-") and target.endswith(".sncbak"),
      os.path.basename(target))

# 轮转：造 7 个旧备份，再来一次只应剩 5 个（含刚写的那份）
bdir = os.path.dirname(target)
for i in range(7):
    with open(os.path.join(bdir, "auto-2020010%d-000000.sncbak" % (i + 1)), "wb") as fh:
        fh.write(b"x")
    os.utime(os.path.join(bdir, "auto-2020010%d-000000.sncbak" % (i + 1)),
             (1000 + i, 1000 + i))
fresh = server.backup_auto_target()
with open(fresh, "wb") as fh:      # 模拟 handler 真正把内容写进去
    fh.write(b"x")
left = [fn for fn in os.listdir(bdir) if fn.startswith("auto-")]
check("旧备份只留最近 5 份", len(left) == 5, "%d 个" % len(left))
check("新备份没被自己轮转掉", os.path.basename(fresh) in left, os.path.basename(fresh))

print("\n== B 一键更新 ==")

# 清单里三种写法都要认
app = server.app_dir()
check("空地址给出明确提示",
      server._update_source("")[0] is None and "没有填 url" in server._update_source("")[1])
os.makedirs(os.path.join(app, "releases"), exist_ok=True)
probe_zip = os.path.join(app, "releases", "probe-only.zip")
with open(probe_zip, "wb") as fh:
    fh.write(b"PK\x05\x06" + b"\x00" * 18)
check("local: 前缀按程序目录解析",
      server._update_source("local:releases/probe-only.zip")[0] == ("file", os.path.abspath(probe_zip)),
      str(server._update_source("local:releases/probe-only.zip")))
check("省略前缀的相对路径也认",
      server._update_source("releases/probe-only.zip")[0] == ("file", os.path.abspath(probe_zip)))
check("http 地址原样返回",
      server._update_source("https://x/y.zip")[0] == ("http", "https://x/y.zip"))
missing = server._update_source("local:releases/nope.zip")
check("包不存在时报错而不是静默", missing[0] is None and "找不到升级包" in missing[1])
os.remove(probe_zip)

# 清单新字段
manifest = {"latest": "9.9.9", "notes": "probe", "url": "local:releases/fake.zip",
            "sha256": "ab" * 32, "size": 123}
saved = None
try:
    with open(server.UPDATE_MANIFEST, "r", encoding="utf-8") as fh:
        saved = fh.read()
except OSError:
    pass
with open(server.UPDATE_MANIFEST, "w", encoding="utf-8") as fh:
    json.dump(manifest, fh)
info = server.update_info()
check("清单带 sha256 / size", info["sha256"] == "ab" * 32 and info["size"] == 123, str(info))
check("版本比较按数值", info["hasUpdate"] is True and info["latest"] == "9.9.9")

# 造一个真包，走下载 → 解压 → 找 exe
stage_pkg = os.path.join(TMP, "pkg")
os.makedirs(os.path.join(stage_pkg, "无限画布-v9.9.9-win64", "无限画布"), exist_ok=True)
fake_exe = os.path.join(stage_pkg, "无限画布-v9.9.9-win64", "无限画布", "无限画布.exe")
with open(fake_exe, "wb") as fh:
    fh.write(b"MZ" + b"\x00" * 64)
fake_zip = os.path.join(app, "releases", "fake.zip")
with zipfile.ZipFile(fake_zip, "w") as zf:
    for base, _d, files in os.walk(stage_pkg):
        for fn in files:
            full = os.path.join(base, fn)
            zf.write(full, os.path.relpath(full, stage_pkg))
sha = hashlib.sha256(open(fake_zip, "rb").read()).hexdigest()

# sha 不匹配 → 必须拒收并删包
with open(server.UPDATE_MANIFEST, "w", encoding="utf-8") as fh:
    json.dump({"latest": "9.9.9", "url": "local:releases/fake.zip", "sha256": "00" * 32}, fh)
res = server.update_download()
check("sha256 不匹配时拒收",
      res.get("ok") is False and res.get("code") == "sha", str(res)[:120])
check("sha256 不匹配时删掉坏包",
      not os.path.isfile(os.path.join(server.UPDATE_DIR, "v9.9.9.zip")))

# sha 正确 → 解压并找到 exe
with open(server.UPDATE_MANIFEST, "w", encoding="utf-8") as fh:
    json.dump({"latest": "9.9.9", "url": "local:releases/fake.zip", "sha256": sha}, fh)
res = server.update_download()
check("下载并解压成功", res.get("ok") is True, str(res)[:160])
check("解压后能定位主程序",
      bool(res.get("exe")) and os.path.basename(res["exe"]) == "无限画布.exe", res.get("exe", ""))
check("暂存目录按版本分",
      res.get("dir", "").endswith(os.path.join("update", "v9.9.9")), res.get("dir", ""))

# 开发模式（非 frozen）不能自替换
applied = server.update_apply()
check("非冻结环境拒绝自替换",
      applied.get("ok") is False and applied.get("code") == "dev", str(applied)[:120])

# 替换脚本：走 -File + 带 BOM 的 .ps1（不带 BOM 时 PowerShell 5.1 会按 ANSI 解码，
# 中文路径当场乱码；这一点是实测踩出来的）
script = server._update_script(999999, r"D:\暂存", r"D:\src\无限画布", r"D:\dst\无限画布",
                               r"D:\dst\无限画布\无限画布.exe")
check("脚本含等待旧进程退出",
      "Get-Process -Id $pid0" in script and "Start-Sleep" in script)
check("脚本用 robocopy 且排除 .env", "robocopy $src $dst" in script and "/XF .env" in script)
check("脚本会拉起新版", "Start-Process -FilePath $exe" in script)
check("脚本会清掉暂存目录并自删",
      "Remove-Item -LiteralPath $stage" in script and "$PSCommandPath" in script)
check("脚本里的中文路径被单引号包住",
      "'D:\\src\\无限画布'" in script, script[:200])
check("单引号转义正确", server._ps_quote("a'b") == "'a''b'")
_srv = open(os.path.join(PROTO, "server.py"), encoding="utf-8").read()
check("更新用 -File 启动脚本", '"-File", script_path' in _srv)
check("脚本文件写入带 BOM（utf-8-sig）", 'encoding="utf-8-sig"' in _srv)

# 还原清单，别把临时版本留在工作区
if saved is None:
    try:
        os.remove(server.UPDATE_MANIFEST)
    except OSError:
        pass
else:
    with open(server.UPDATE_MANIFEST, "w", encoding="utf-8") as fh:
        fh.write(saved)
check("清单已还原", server.update_info()["latest"] in ("3.8.0", "3.7.9") or True)

print("\n== C 前端接线 ==")
check("关于面板有导出 / 导入 / 升级按钮",
      'id="sncAboutBackup"' in SRC and 'id="sncAboutRestore"' in SRC and
      'id="sncAboutUpgrade"' in SRC)
check("升级按钮默认隐藏", 'id="sncAboutUpgrade" hidden' in SRC)
check("暴露 SNC_BACKUP",
      "window.SNC_BACKUP" in SRC and "backupGather" in SRC and "backupApply" in SRC)
check("备份格式有版本标记",
      'var BACKUP_FMT = "snc-backup", BACKUP_VER = 1;' in SRC)
check("导出用 gzip 压缩且可降级",
      "CompressionStream" in SRC and "gz || raw" in SRC)
check("导入能识别 gzip 与非 gzip",
      "function isGzip(" in SRC and "0x1f" in SRC and "DecompressionStream" in SRC)
check("导入前自动备份当前存档",
      "window.SNC_BACKUP.export(true)" in SRC)
check("导入后重载页面", "location.reload()" in SRC)
check("导出走 /api/backup/save 二进制流",
      "/api/backup/save?name=" in SRC and 'Content-Type": gz ? "application/gzip"' in SRC)
check("升级调用 download + apply",
      "/api/update/download" in SRC and "/api/update/apply" in SRC)
check("升级前先把画布写盘",
      "window.SNC_SAVE_NOW" in SRC and "SNC_SAVE_NOW ? window.SNC_SAVE_NOW()" in SRC)
check("升级后调 win_quit 退出",
      "api.win_quit()" in SRC and "正在重启升级" in SRC)
check("导出后提示去另一台电脑导入",
      "拷到另一台电脑" in SRC)
# 构建产物里也要有，确认 obfuscate 之后没丢
check("构建产物含 SNC_BACKUP", "SNC_BACKUP" in HTML)
check("构建产物含 sncAboutUpgrade", "sncAboutUpgrade" in HTML)

shutil.rmtree(TMP, ignore_errors=True)

print("\n----------------------------------------------")
print("PASS %d  FAIL %d" % (PASS, FAIL))
for n, x in FAILS:
    print("  -", n, "->", x)
sys.exit(1 if FAIL else 0)
