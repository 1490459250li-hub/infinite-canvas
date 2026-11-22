# -*- coding: utf-8 -*-
"""启动 / 页面 / 画布 三段性能实测，用来给优化方案做基线。

用法：
    SNC_PORT=8321 python tests/serve.py          # 另开一个窗口常驻
    python tools/perf_audit.py                   # 跑一遍，打印 JSON
    python tools/perf_audit.py --exe             # 顺带测打包件冷启动

为什么拆三段分开测：
    打开软件慢，可能是「壳启动慢」也可能是「页面慢」。不分段就会拍脑袋优化
    canvas.html（实测页面只要 0.2s，根本不是瓶颈）。这个脚本先把三段拆开量准。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

BASE = os.environ.get("SNC_BASE", "http://127.0.0.1:8321")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "proto", "dist", "无限画布.exe")


def measure_exe(runs: int = 3) -> list:
    """打包件冷启动：用 --self-test（起窗 → 等页面 ping → 关窗），
    包含 onefile 解压 + Python 导入 + WebView2 初始化 + 页面加载，是最接近
    用户双击图标的那条路径。"""
    if not os.path.exists(EXE):
        return [{"error": "exe not found: %s" % EXE}]
    out = []
    for i in range(runs):
        t0 = time.time()
        r = subprocess.run([EXE, "--self-test"], capture_output=True, timeout=180)
        out.append({"run": i + 1, "seconds": round(time.time() - t0, 2),
                    "rc": r.returncode})
    return out


def measure_source(runs: int = 2) -> list:
    """同一流程走源码（python server.py --self-test），差值就是 onefile 解压开销。"""
    out = []
    for i in range(runs):
        t0 = time.time()
        r = subprocess.run([sys.executable, "server.py", "--self-test"],
                           cwd=os.path.join(ROOT, "proto"),
                           capture_output=True, timeout=180)
        out.append({"run": i + 1, "seconds": round(time.time() - t0, 2),
                    "rc": r.returncode})
    return out


def measure_page(runs: int = 3) -> dict:
    """页面侧：加载耗时、DOM 节点、JS 堆、长任务；以及拖动画布的真实帧率。"""
    from playwright.sync_api import sync_playwright

    url = BASE.rstrip("/") + "/canvas.html?shell=1"
    rows = []
    with sync_playwright() as pw:
        br = pw.chromium.launch(channel="msedge")
        for i in range(runs):
            ctx = br.new_context(viewport={"width": 1440, "height": 900})
            # 跳过 EULA，否则量到的是协议弹窗那一屏
            ctx.add_init_script(
                "try{localStorage.setItem('snc.eula.v1','1');"
                "localStorage.setItem('snc.theme.v1','dark');}catch(e){}")
            pg = ctx.new_page()
            t0 = time.time()
            pg.goto(url, wait_until="load")
            wall = round((time.time() - t0) * 1000)
            m = pg.evaluate("""() => {
                const n = performance.getEntriesByType('navigation')[0] || {};
                const lt = performance.getEntriesByType('longtask') || [];
                return {
                    dcl: Math.round(n.domContentLoadedEventEnd || 0),
                    load: Math.round(n.loadEventEnd || 0),
                    dom: document.getElementsByTagName('*').length,
                    nodes: document.querySelectorAll('.snc-node').length,
                    heapMB: performance.memory
                        ? +(performance.memory.usedJSHeapSize / 1048576).toFixed(1) : null,
                    longTasks: lt.length,
                    longestTask: lt.length
                        ? Math.round(Math.max(...lt.map(x => x.duration))) : 0
                };
            }""")
            rows.append({"run": i + 1, "wall_ms": wall, **m})
            ctx.close()

        # 真实鼠标拖动平移，用 rAF 计数算帧率（比读 FPS 面板靠谱）
        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script(
            "try{localStorage.setItem('snc.eula.v1','1');"
            "localStorage.setItem('snc.theme.v1','dark');}catch(e){}")
        pg = ctx.new_page()
        pg.goto(url, wait_until="load")
        pg.wait_for_timeout(1600)
        pg.evaluate("""() => { window.__f = 0; window.__t0 = performance.now();
            (function loop(){ window.__f++; requestAnimationFrame(loop); })(); }""")
        pg.mouse.move(1100, 600)
        pg.mouse.down()
        for i in range(40):
            pg.mouse.move(1100 - i * 8, 600 - i * 3)
            pg.wait_for_timeout(50)
        pg.mouse.up()
        fps = pg.evaluate("""() => {
            const dt = performance.now() - window.__t0;
            return {fps: +(window.__f / (dt / 1000)).toFixed(1), frames: window.__f};
        }""")
        ctx.close()
        br.close()
    return {"load": rows, "pan": fps}


def asset_breakdown() -> dict:
    """内联资源占比：canvas.src.html 里有多少是 base64 图。"""
    import re
    p = os.path.join(ROOT, "proto", "canvas.src.html")
    s = open(p, encoding="utf-8").read()
    total = len(s.encode("utf-8"))
    b64 = re.findall(r'data:image/(?:jpeg|png|webp);base64,([A-Za-z0-9+/=]{200,})', s)
    b64_bytes = sum(len(x) for x in b64)
    out_html = os.path.join(ROOT, "proto", "canvas.html")
    return {
        "src_bytes": total,
        "b64_blocks": len(b64),
        "b64_bytes": b64_bytes,
        "b64_ratio": round(b64_bytes * 100.0 / total, 1),
        "obfuscated_bytes": os.path.getsize(out_html) if os.path.exists(out_html) else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", action="store_true", help="顺带测打包件冷启动")
    ap.add_argument("--source", action="store_true", help="顺带测源码流程启动")
    a = ap.parse_args()

    out = {"assets": asset_breakdown()}
    out["page"] = measure_page()
    if a.source:
        out["source_start"] = measure_source()
    if a.exe:
        out["exe_start"] = measure_exe()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
