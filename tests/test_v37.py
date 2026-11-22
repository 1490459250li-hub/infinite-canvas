# -*- coding: utf-8 -*-
"""v3.5.2 回归：缩放上限 500%、成品图不再叠提示词。

A 段：源码断言（缩放常量、钳制点、gen-tag 移除、导出标签）。
B 段：浏览器实测（按钮 / 滚轮到 500%、下限 28%、成品卡无叠加、提示词仍可查）。
"""
import json
import os
import socket
import subprocess
import sys
import time

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


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "proto", "canvas.src.html")
SERVER = os.path.join(ROOT, "proto", "server.py")
DIST_HTML = os.path.join(ROOT, "proto", "canvas.html")

sys.path.insert(0, os.path.join(ROOT, "proto"))
import server  # noqa: E402

src = open(SRC, encoding="utf-8").read()
py = open(SERVER, encoding="utf-8").read()

print("\n== A  源码 ==")
check("版本号 >= 3.5.2", server._ver_key(server.APP_VERSION) >= server._ver_key("3.5.2"),
      server.APP_VERSION)

# ---- 缩放上限 ----
check("声明缩放上下限常量", "var ZOOM_MAX = 5.0, ZOOM_MIN = 0.28;" in src)
check("滚轮用常量钳制",
      "Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, state.view.k * factor))" in src)
check("按钮用常量钳制",
      "Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, state.view.k * f))" in src)
check("没有残留 2.4 上限", "Math.min(2.4" not in src)
check("上限是 5.0", "ZOOM_MAX = 5.0" in src)
check("下限仍是 0.28", "ZOOM_MIN = 0.28" in src)

# ---- 成品图不再叠提示词 ----
check("done 分支不再渲染 gen-tag", 'class="snc-gen-tag"' not in src)
check("done 分支只剩图片容器",
      'body.innerHTML = \'<div class="snc-gen">\' + media + \'</div>\';' in src)
check("gen-tag 样式已删", "#snc .snc-gen-tag{" not in src)
check("排队/生成中仍显示提示词（占位态保留）",
      src.count('class="snc-gen-q"') >= 2 and 'querySelector(".snc-gen-q").textContent = n.prompt' in src)
# 提示词信息本身没丢
check("图片卡的检查器本就是隐藏的（提示词不由它承载）",
      'if(n.type === "gen"){ insp.hidden = true;' in src)
check("记录面板仍展示提示词", "snc-hist-p" in src and "v.prompt" in src)
# 整板导出不再把 prompt 画进图
check("导出标签不再回落到 prompt",
      'String(n.label || n.prompt || "")' not in src)
check("导出标签只认 label", 'n.type === "gen" && n.label' in src)

# ---- 混淆产物要跟源码一致 ----
dist = open(DIST_HTML, encoding="utf-8").read()
# v3.7.4：预览图改成 /art/ 外链后，混淆产物从 2.0MB 掉到 0.43MB。
# 原来用「体积 >1MB」当「已重建」的代理指标，外链化后它会一直失败；
# 现在直接查真正关心的事：产物新鲜（含 /art/ 路径）且不再内联 base64。
check("canvas.html 已重建且预览图已外链化",
      len(dist) < 700000 and "data:image/jpeg;base64,/9j" not in dist
      and "/art/skill-" in dist, len(dist))
check("canvas.html 里没有 gen-tag 选择器",
      'class="snc-gen-tag"' not in dist and "'snc-gen-tag'" not in dist)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


print("\n== B  浏览器 ==")
from playwright.sync_api import sync_playwright  # noqa: E402
import requests  # noqa: E402

PORT = free_port()
BASE = "http://127.0.0.1:%d" % PORT
proc = subprocess.Popen([sys.executable, os.path.join(HERE, "serve.py")],
                        env=dict(os.environ, SNC_PORT=str(PORT)),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(80):
    try:
        requests.get(BASE + "/api/update/check", timeout=1)
        break
    except Exception:
        time.sleep(0.2)

PNG = ("iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAAWklEQVR4nO3QMQEAAAjDMMC/56"
       "EBT1JQ1M3tOQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
       "AAAA4G8GmAABkVXyWQAAAABJRU5ErkJggg==")
errs = []
PROMPT = "参考意向图优化我们效果图的整体效果"

try:
    with sync_playwright() as p:
        br = p.chromium.launch(channel="msedge")
        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.route("**/api/generate", lambda r: (page.wait_for_timeout(1200),
            r.fulfill(status=200, content_type="application/json",
                body=json.dumps({"ok": True, "b64": PNG, "size": "1024x1024", "width": 1024,
                                 "height": 1024, "format": "png", "model": "sensenova-u1.5-fast",
                                 "provider": "sensenova", "latencyMs": 1200}))))
        page.goto(BASE + "/canvas.html")
        page.wait_for_selector(".snc-node")
        page.wait_for_timeout(800)

        # ---- B1 按钮放到底 = 500% ----
        page.click("#sncFit")
        page.wait_for_timeout(200)
        for _ in range(40):
            page.click("#sncZoomIn")
        page.wait_for_timeout(300)
        hi = page.inner_text(".snc-zoomer span")
        check("点「+」能到 500%", hi.strip() == "500%", hi)
        scale = page.evaluate("""() => {
            const w = document.querySelector('#snc .snc-world') ||
                      document.querySelector('.snc-world');
            const m = w ? /scale\\(([\\d.]+)\\)/.exec(w.style.transform) : null;
            return m ? parseFloat(m[1]) : 0;
        }""")
        check("画布实际缩放 = 5", abs(scale - 5) < 0.01, scale)

        # ---- B2 滚轮也封顶 500% ----
        page.evaluate("""() => {
            const st = document.querySelector('#snc .snc-stage') ||
                       document.querySelector('.snc-stage');
            for(let i = 0; i < 40; i++) st.dispatchEvent(new WheelEvent('wheel',
              {bubbles:true, cancelable:true, deltaY:-120, clientX:700, clientY:400}));
        }""")
        page.wait_for_timeout(300)
        wheel_hi = page.inner_text(".snc-zoomer span")
        check("滚轮也能到 500%（超不过）", wheel_hi.strip() == "500%", wheel_hi)

        # ---- B3 下限仍是 28% ----
        for _ in range(60):
            page.click("#sncZoomOut")
        page.wait_for_timeout(300)
        lo = page.inner_text(".snc-zoomer span")
        check("点「-」能到 28%", lo.strip() == "28%", lo)

        # ---- B4 成品卡上没有提示词叠加 ----
        page.click("#sncFit")
        page.wait_for_timeout(200)
        # 只生成 1 张：出两张时它们会成组选中，浮动工具条要多选才隐藏，
        # 单张才好验「记录」入口。
        page.fill("#sncInput", PROMPT)
        page.click("#sncSend")
        page.wait_for_timeout(3800)
        card = page.evaluate("""() => {
            const cards = [...document.querySelectorAll('.snc-node')];
            const done = cards.filter(c => c.querySelector('.snc-photo'));
            if(!done.length) return {none: true, cards: cards.length};
            const c = done[done.length - 1];
            const body = c.querySelector('.snc-node-body');
            return {
              tag: !!c.querySelector('.snc-gen-tag'),
              hasPrompt: (body ? body.innerText : '').indexOf('参考意向图') >= 0,
              bodyText: (body ? body.innerText : '').trim(),
              badge: !!c.querySelector('.snc-sizebadge')
            };
        }""")
        check("生成出了成品卡", not card.get("none"), card)
        check("成品卡没有 gen-tag 节点", card.get("tag") is False, card.get("tag"))
        check("成品卡正文不含提示词", card.get("hasPrompt") is False, card.get("bodyText"))
        check("尺寸徽标仍在（没误删）", card.get("badge") is True, card.get("badge"))

        # ---- B5 提示词信息仍可查（选中后右栏） ----
        page.evaluate("() => window.getSelection && window.getSelection().removeAllRanges()")
        page.click("#sncFit")
        page.wait_for_timeout(400)
        bar = page.evaluate("() => document.getElementById('sncImgBar').hidden")
        check("生成后图片工具条出现", bar is False, bar)
        if bar is not False:
            page.mouse.click(420, 300)
            page.wait_for_timeout(300)
            page.locator(".snc-node:has(.snc-photo)").last.click()
            page.wait_for_timeout(500)
        page.click('#sncImgBar [data-act="history"]')
        page.wait_for_timeout(700)
        hist = page.evaluate("""() => {
            const b = document.getElementById('sncHistBd');
            const h = document.getElementById('sncHist');
            return {hidden: h ? h.hidden : null, text: b ? b.innerText.slice(0, 200) : null};
        }""")
        check("「记录」面板能打开", hist.get("hidden") is False, hist.get("hidden"))
        check("记录里仍能看到提示词", bool(hist.get("text")) and PROMPT in hist["text"],
              (hist.get("text") or "")[:60])

        check("页面无 JS 异常", not errs, errs[:2])
        br.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

print("\nv3.5.2 结果：%d 项通过，%d 项失败" % (PASS, FAIL))
if FAILS:
    for name, extra in FAILS:
        print("  -", name, extra)
sys.stdout.flush()
sys.exit(1 if FAIL else 0)
