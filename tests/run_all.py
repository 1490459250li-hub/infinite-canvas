# -*- coding: utf-8 -*-
"""整体体检：批量跑全部回归脚本并汇总 PASS/FAIL。

跳过：消耗真实 Key 的 *_real / test_final_real / test_region_quality、
纯截图的 shot_*、探 exe 的 probe_splash / probe_exe_v370（发版时单独跑）、
工具模块 winctl / winshot / serve。
"""
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "http://127.0.0.1:8321"

GROUPS = [
    # 静态自检（不需要服务）
    ("static", ["tests/probe_batch12.py"]),
    ("static", ["tests/probe_batch13.py"]),
    ("static", ["tests/probe_batch14.py"]),
    ("static", ["tests/probe_batch15.py"]),
    ("static", ["tests/probe_batch16.py"]),
    # 浏览器回归（8321）
    ("browser", ["tests/probe_batch5.py", BASE]),
    ("browser", ["tests/probe_batch6.py", BASE]),
    ("browser", ["tests/probe_batch7.py", BASE]),
    ("browser", ["tests/probe_batch8.py", BASE]),
    ("browser", ["tests/probe_batch9.py", BASE]),
    ("browser", ["tests/probe_batch10.py", BASE]),
    ("browser", ["tests/probe_batch11.py", BASE]),
    ("browser", ["tests/probe_archive.py", BASE]),
    ("browser", ["tests/probe_art.py", BASE]),
    ("browser", ["tests/probe_panel.py"]),
    ("browser", ["tests/probe_theme.py", BASE]),
    ("browser", ["tests/probe_tidy.py"]),
    ("browser", ["tests/probe_ux.py", BASE]),
    ("browser", ["tests/probe_v37b.py"]),
    ("browser", ["tests/smoke_v29.py"]),
    ("browser", ["tests/test_stub.py"]),
    ("browser", ["tests/test_v15.py"]),
    ("browser", ["tests/test_v16.py"]),
    ("browser", ["tests/test_v17.py"]),
    ("browser", ["tests/test_v19.py"]),
    ("browser", ["tests/test_v20.py"]),
    ("browser", ["tests/test_v21_refs.py"]),
    ("browser", ["tests/test_v22_ui.py"]),
    ("browser", ["tests/test_v23_viewer.py"]),
    ("browser", ["tests/test_v24_arco.py"]),
    ("browser", ["tests/test_v26_inpaint.py"]),
    ("browser", ["tests/test_v26_platform.py"]),
    ("browser", ["tests/test_v27_fixes.py"]),
    ("browser", ["tests/test_v27_savefile.py"]),
    ("browser", ["tests/test_v29_fixes.py"]),
    ("browser", ["tests/test_v30_providers.py"]),
    ("browser", ["tests/test_v31_group_rename.py"]),
    ("browser", ["tests/test_v32_shell.py"]),
    ("browser", ["tests/test_v33.py"]),
    ("browser", ["tests/test_v35.py"]),
    ("browser", ["tests/test_v36.py"]),
    ("browser", ["tests/test_v37.py"]),
    ("browser", ["tests/test_v38.py"]),
    ("browser", ["tests/test_v39.py"]),
    ("browser", ["tests/test_v40.py"]),
    ("browser", ["tests/test_v41.py"]),
    ("browser", ["tests/test_v42.py"]),
    ("browser", ["tests/test_v380_backup.py"]),
    ("browser", ["tests/probe_v360.py"]),
]

SUMMARY_RE = re.compile(r"(\d+)\s*/\s*(\d+)")

results = []
t_all = time.time()
for kind, cmd in GROUPS:
    name = os.path.basename(cmd[0])
    t0 = time.time()
    try:
        env = dict(os.environ)
        # 两套 URL 约定并存：
        #   test_v* / smoke_v29 / probe_v37b → SNC_BASE 是「完整页面地址」；
        #   probe_batch* / probe_archive/art/theme/ux → argv[1] 是根路径，自己拼 /canvas.html。
        # 所以这里给完整地址，根路径约定的脚本统一走 GROUPS 里的 argv。
        env["SNC_BASE"] = BASE + "/canvas.html"
        p = subprocess.run(
            [sys.executable] + cmd,
            cwd=ROOT, env=env,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=420,
        )
        out = (p.stdout or "") + (p.stderr or "")
        dt = time.time() - t0
        m = SUMMARY_RE.findall(out)
        nums = None
        # 找形如 55/55 的通过率（取最后一次出现）
        for a, b in m:
            nums = (int(a), int(b))
        status = "PASS" if p.returncode == 0 else "FAIL"
        # 有的脚本返回 0 但断言有 FAIL 字样
        if p.returncode == 0 and re.search(r"^FAIL", out, re.M):
            status = "FAIL(报告有FAIL但退出0)"
        results.append((name, status, dt, nums, out))
    except subprocess.TimeoutExpired:
        results.append((name, "TIMEOUT(>420s)", time.time() - t0, None, ""))
    except Exception as e:
        results.append((name, "ERROR:%s" % e, time.time() - t0, None, ""))

print("=" * 72)
bad = 0
for name, status, dt, nums, out in results:
    flag = "" if status == "PASS" else "  <<<"
    print("%-26s %-14s %5.1fs  %s%s" % (
        name, status, dt,
        ("%d/%d" % nums) if nums else "-",
        flag))
    if status != "PASS":
        bad += 1
        # 打印失败详情（最多 25 行）
        lines = [l for l in out.splitlines() if l.strip()][-25:]
        for l in lines:
            print("      | " + l[:150])
print("=" * 72)
total = len(results)
print("总计 %d 个脚本，PASS %d，异常 %d，用时 %.1f 分钟" % (
    total, total - bad, bad, (time.time() - t_all) / 60))
