# -*- coding: utf-8 -*-
"""v3.7.1 回归（两条修复）：
  1) 结构化参数浮层可拖动 —— 拖过之后记住位置、双击标题复位、位置始终夹在可视区内。
  2) 删掉「应用到所有生成」—— 手写指令不再被 {最高准则, 要求} 包装；技能与参数浮层照旧生效。

A 段源码断言，B 段浏览器实测。出图接口全部打桩，不消耗额度。
"""
import json
import os
import socket
import struct
import subprocess
import sys
import time
import base64
import zlib

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
DIST_HTML = os.path.join(ROOT, "proto", "canvas.html")
SHOTS = os.path.join(ROOT, "截图", "v371")
os.makedirs(SHOTS, exist_ok=True)

sys.path.insert(0, os.path.join(ROOT, "proto"))
import server  # noqa: E402

src = open(SRC, encoding="utf-8").read()
dist = open(DIST_HTML, encoding="utf-8").read()

print("\n== A  源码 ==")
check("版本号 >= 3.7.1", server._ver_key(server.APP_VERSION) >= server._ver_key("3.7.1"),
      server.APP_VERSION)

# ---- 1. 可拖动 ----
check("标题栏是拖动条（cursor:move）", "cursor:move" in src and "user-select:none" in src)
check("标题栏滚动时钉在顶部（position:sticky）",
      ".snc-struct-h" in src and "position:sticky; top:0" in src)
check("拖动中状态样式 is-drag 已定义", ".snc-struct-panel.is-drag" in src)
check("拖动逻辑 bindStructDrag 存在", "function bindStructDrag" in src)
check("拖动监听挂在 window 上（甩出面板也不掉）",
      'window.addEventListener("pointermove", move, true)' in src)
check("位置记忆键 snc.struct.pos", 'var STRUCT_POS_KEY = "snc.struct.pos"' in src)
check("落位前夹回可视区 clampStructPos", "function clampStructPos" in src)
check("placeStructPanel 优先用用户位置",
      "if(applyStructPos()) return;" in src)
check("双击拖动条复位", "dblclick" in src and "localStorage.removeItem(key)" in src)
check("交互元素不触发拖动（按钮/输入框）",
      'var DRAG_SKIP = "input, select, textarea, button, a, [data-nodrag]"' in src
      and "e.target.closest(DRAG_SKIP)" in src)
check("按下不动 4px 不算拖（搜索框还能点）",
      "Math.abs(e.clientX - startX) + Math.abs(e.clientY - startY) < 4" in src)
check("技能抽屉也绑了拖动",
      'snDrag(skPop, [".snc-skp-top", ".snc-skp-tabs", ".snc-skp-foot"],' in src)
check("技能工作台也绑了拖动",
      'snDrag(skWinEl, [".snc-skwin-hd"],' in src)
check("抽屉/工作台各有独立的位置记忆键",
      'var SKPOP_POS_KEY = "snc.skpop.pos"' in src
      and 'var SKWIN_POS_KEY = "snc.skwin.pos"' in src)
check("抽屉落位优先用户位置", "applyPanelPos(skPop, SKPOP_POS_KEY)" in src)
check("工作台落位优先用户位置", "applyPanelPos(skWinEl, SKWIN_POS_KEY)" in src)

# ---- 2. 「应用到所有生成」删干净 ----
check("DOM 里的 #sncStructAll 已删", 'id="sncStructAll"' not in src)
check("「应用到所有生成」的可点文案已删",
      "> 应用到所有生成" not in src and "应用到所有生成</label>" not in src,
      [m.start() for m in __import__("re").finditer("应用到所有生成", src)])
check("structAllOn 已删", "structAllOn" not in src)
check("STRUCT_ALL_KEY 已删", "STRUCT_ALL_KEY" not in src)
check("buildPrompt 不再无条件包装",
      'if(!st && structAllOn()) st = {kind: "generic"};' not in src)
check("buildPrompt 仍保留 struct 才包装的主干",
      "var st = struct || null;" in src and "if(st){" in src)
check("参数按钮高亮只看已选参数",
      'classList.toggle("is-on", n > 0);' in src)
check("老版本 localStorage 标记会被清掉",
      'localStorage.removeItem("snc.struct.all")' in src)
check("canvas.html 已重建并带上新逻辑",
      "snc.struct.pos" in dist and "sncStructAll" not in dist)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def png_bytes(w, h):
    row = bytes([190, 120, 90]) * w
    raw = b"".join(b"\x00" + row for _ in range(h))

    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


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

PNG = base64.b64encode(png_bytes(800, 600)).decode("ascii")
errs, bodies = [], []


def gen(route):
    try:
        bodies.append(json.loads(route.request.post_data or "{}"))
    except Exception:
        bodies.append({})
    route.fulfill(status=200, content_type="application/json",
                  body=json.dumps({"ok": True, "b64": PNG, "size": "stub", "width": 800,
                                   "height": 600, "format": "png", "model": "stub-image",
                                   "provider": "sensenova", "latencyMs": 120,
                                   "usage": {}}))


def panel_state(page):
    return page.evaluate("""() => {
        const p = document.getElementById('sncStructPanel');
        const h = p.querySelector('.snc-struct-h');
        const r = p.getBoundingClientRect();
        const hr = h.getBoundingClientRect();
        const rr = document.getElementById('snc').getBoundingClientRect();
        return {
            open: !p.hidden,
            left: parseInt(p.style.left || '0', 10),
            top: parseInt(p.style.top || '0', 10),
            x: Math.round(r.left), y: Math.round(r.top),
            w: Math.round(r.width), h: Math.round(r.height),
            inView: r.left >= -1 && r.top >= -1 &&
                    r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1,
            headX: hr.x + hr.width * 0.32, headY: hr.y + hr.height / 2,
            cursor: getComputedStyle(h).cursor,
            dragging: p.classList.contains('is-drag'),
            rootW: Math.round(rr.width), rootH: Math.round(rr.height)
        };
    }""")


try:
    with sync_playwright() as p:
        br = p.chromium.launch(channel="msedge")
        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.route("**/api/generate", gen)
        page.goto(BASE + "/canvas.html")
        page.wait_for_selector(".snc-node")
        page.wait_for_timeout(800)

        def make_card(label):
            before = page.evaluate(
                "() => Array.from(document.querySelectorAll('.snc-node')).map(d=>d.dataset.id)")
            page.fill("#sncInput", label)
            page.click("#sncSend")
            page.wait_for_timeout(1100)
            return page.evaluate("""(old) => {
                const n = Array.from(document.querySelectorAll('.snc-node'))
                  .find(d => !old.includes(d.dataset.id));
                return n ? n.dataset.id : '';
            }""", before)

        def open_edit(cid):
            page.click('.snc-node[data-id="%s"]' % cid)
            page.wait_for_timeout(250)
            page.click('#sncImgBar button[data-act="edit"]')
            page.wait_for_timeout(280)

        cid = make_card("v371 面板可拖动原图")
        check("生成出可编辑卡片", bool(cid), cid)
        open_edit(cid)

        # ---------- C. 参数浮层可拖动 ----------
        page.click("#sncStructBtn")
        page.wait_for_timeout(320)
        base = panel_state(page)
        check("点「参数」打开浮层", base["open"])
        check("标题栏光标是 move", base["cursor"] == "move", base["cursor"])
        check("默认位置完整落在窗口内", base["inView"], base)

        # 拖 (140, 96)
        page.mouse.move(base["headX"], base["headY"])
        page.mouse.down()
        page.wait_for_timeout(80)
        mid = panel_state(page)
        check("按下不动不算拖（还没加 is-drag）", not mid["dragging"])
        page.mouse.move(base["headX"] + 10, base["headY"] + 6, steps=3)
        page.wait_for_timeout(90)
        check("移动超过 4px 才进入拖动态（is-drag）", panel_state(page)["dragging"])
        page.mouse.move(base["headX"] + 70, base["headY"] + 48, steps=6)
        page.wait_for_timeout(60)
        page.mouse.move(base["headX"] + 140, base["headY"] + 96, steps=6)
        page.wait_for_timeout(80)
        page.mouse.up()
        page.wait_for_timeout(220)
        moved = panel_state(page)
        check("拖动后松手退出拖动态", not moved["dragging"])
        check("位置确实跟着手走了（左 +140 容差 8）",
              abs((moved["left"] - base["left"]) - 140) <= 8,
              (base["left"], moved["left"]))
        check("位置确实跟着手走了（上 +96 容差 8）",
              abs((moved["top"] - base["top"]) - 96) <= 8,
              (base["top"], moved["top"]))
        check("拖动后仍在窗口内", moved["inView"], moved)
        page.screenshot(path=os.path.join(SHOTS, "01-拖到新位置.png"))

        # 关闭再开：位置要留在原地
        page.click("#sncStructX")
        page.wait_for_timeout(200)
        check("点 × 收起浮层",
              page.evaluate("() => document.getElementById('sncStructPanel').hidden"))
        page.click("#sncStructBtn")
        page.wait_for_timeout(320)
        again = panel_state(page)
        check("重新打开仍在拖过去的位置",
              abs(again["left"] - moved["left"]) <= 2 and abs(again["top"] - moved["top"]) <= 2,
              (moved["left"], moved["top"], again["left"], again["top"]))

        # 关掉页面重开：位置也要记住（localStorage）
        page.reload()
        page.wait_for_selector(".snc-node")
        page.wait_for_timeout(700)
        cid2 = make_card("v371 重开后原图")
        open_edit(cid2)
        page.click("#sncStructBtn")
        page.wait_for_timeout(320)
        reloaded = panel_state(page)
        check("刷新后位置仍然记得",
              abs(reloaded["left"] - moved["left"]) <= 2 and
              abs(reloaded["top"] - moved["top"]) <= 2,
              (moved["left"], reloaded["left"], moved["top"], reloaded["top"]))

        # 双击标题复位
        hx, hy = reloaded["headX"], reloaded["headY"]
        page.mouse.dblclick(hx, hy)
        page.wait_for_timeout(320)
        reset = panel_state(page)
        check("双击标题栏回到默认位置",
              abs(reset["left"] - base["left"]) <= 10 and abs(reset["top"] - base["top"]) <= 10,
              (base["left"], base["top"], reset["left"], reset["top"]))
        page.screenshot(path=os.path.join(SHOTS, "02-双击复位.png"))

        # 拖到右下角超出边界 → 夹回可视区
        hx, hy = reset["headX"], reset["headY"]
        page.mouse.move(hx, hy)
        page.mouse.down()
        page.mouse.move(reset["rootW"] - 20, reset["rootH"] - 20, steps=8)
        page.wait_for_timeout(80)
        page.mouse.up()
        page.wait_for_timeout(220)
        pushed = panel_state(page)
        check("拖出边界会被夹回可视区", pushed["inView"], pushed)
        check("夹回后左边不越界",
              pushed["left"] + pushed["w"] <= pushed["rootW"],
              (pushed["left"], pushed["w"], pushed["rootW"]))
        check("夹回后仍留一条标题栏可见（top ≤ 视口高-40）",
              pushed["top"] <= 900 - 40, pushed["top"])

        # 关闭按钮不能引发拖动（面板已在右下角，用它的标题栏坐标双击复位）
        page.mouse.dblclick(pushed["headX"], pushed["headY"])
        page.wait_for_timeout(260)
        st0 = panel_state(page)
        xb = page.evaluate("""() => {
            const r = document.getElementById('sncStructX').getBoundingClientRect();
            return {x: r.x + r.width / 2, y: r.y + r.height / 2};
        }""")
        page.mouse.move(xb["x"], xb["y"])
        page.mouse.down()
        page.mouse.move(xb["x"] + 40, xb["y"] + 40, steps=4)
        page.mouse.up()
        page.wait_for_timeout(200)
        st1 = panel_state(page)
        check("按住关闭按钮拖不会移动面板",
              abs(st1["left"] - st0["left"]) <= 1 and abs(st1["top"] - st0["top"]) <= 1,
              (st0["left"], st1["left"]))
        check("拖标题栏不会把浮层拖没（仍打开）", st1["open"])

        # ---------- D. 「应用到所有生成」已经没有了 ----------
        has_cb = page.evaluate("() => !!document.getElementById('sncStructAll')")
        check("浮层里没有 #sncStructAll", not has_cb)
        txt = page.evaluate(
            "() => document.getElementById('sncStructPanel').textContent")
        check("浮层文案里没有「应用到所有生成」", "应用到所有生成" not in txt)
        foot_labels = page.evaluate("""() => [...document.querySelectorAll(
            '#sncStructPanel .snc-struct-foot label')]
            .map(l => (l.textContent || '').trim().replace(/\\s+/g, ''))""")
        check("底部只剩格式/优化器/分类模板三个下拉", len(foot_labels) == 3, foot_labels)
        page.screenshot(path=os.path.join(SHOTS, "03-底部去掉开关.png"))

        # ---------- E. 手写提交不再被包装（旧标记也不管用） ----------
        page.evaluate("""() => {
            try{ localStorage.setItem('snc.struct.all','1');
                 localStorage.setItem('snc.struct.fmt','text'); }catch(e){}
        }""")
        page.reload()
        page.wait_for_selector(".snc-node")
        page.wait_for_timeout(700)
        cid3 = make_card("v371 手写原图")
        open_edit(cid3)
        page.fill("#sncComposeInput", "只把天空压暗一点，别动建筑")
        bodies.clear()
        page.click("#sncComposeSend")
        page.wait_for_timeout(1300)
        pr = (bodies[-1].get("prompt") or "") if bodies else ""
        check("手写提交仍逐字以原句开头", pr.startswith("只把天空压暗一点，别动建筑"), pr[:60])
        check("手写提交不带【最高准则】", "【最高准则】" not in pr, pr[:120])
        check("手写提交不带【要求", "【要求" not in pr, pr[:120])
        check("手写提交不带摄影参数尾段", "摄影参数" not in pr)
        check("旧 localStorage 标记已被清掉",
              page.evaluate("() => localStorage.getItem('snc.struct.all')") is None)

        # ---------- F. 参数浮层照旧生效（别把功能一起删了） ----------
        open_edit(cid3)
        page.click("#sncStructBtn")
        page.wait_for_timeout(300)
        page.select_option('#sncStructGrid select[data-sk="weather"]', "mist")
        page.wait_for_timeout(200)
        check("选参数后计数变 1", page.inner_text("#sncStructCount") == "已选 1 项",
              page.inner_text("#sncStructCount"))
        check("参数按钮亮起（is-on）",
              page.evaluate("""() => document.getElementById('sncStructBtn')
                                 .classList.contains('is-on')"""))
        page.fill("#sncComposeInput", "把庭院改成清晨薄雾氛围")
        bodies.clear()
        page.click("#sncComposeSend")
        page.wait_for_timeout(1300)
        pr2 = (bodies[-1].get("prompt") or "") if bodies else ""
        check("选了参数的手写提交带【最高准则】", "【最高准则】" in pr2, pr2[:120])
        check("参数提交里含薄雾", "薄雾" in pr2)
        check("参数提交仍以原句开头", pr2.startswith("把庭院改成清晨薄雾氛围"), pr2[:60])

        # ---------- G. 技能抽屉可拖动 ----------
        page.keyboard.press("Escape")
        page.wait_for_timeout(220)
        page.click('.snc-node[data-id="%s"]' % cid3)
        page.wait_for_timeout(260)
        page.click('#sncImgBar button[data-act="skill"]')
        page.wait_for_timeout(420)

        def pop_state():
            return page.evaluate("""() => {
                const p = document.getElementById('sncSkillPop');
                const t = p.querySelector('.snc-skp-tabs').getBoundingClientRect();
                const f = p.querySelector('.snc-skp-foot').getBoundingClientRect();
                const r = p.getBoundingClientRect();
                return {open: !p.hidden,
                        left: parseInt(p.style.left || '0', 10),
                        top: parseInt(p.style.top || '0', 10),
                        tabX: t.right - 24, tabY: t.y + t.height / 2,
                        footX: f.x + 10, footY: f.y + f.height / 2,
                        w: Math.round(r.width), h: Math.round(r.height),
                        inView: r.left >= -1 && r.top >= -1 &&
                                r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1,
                        cursor: getComputedStyle(p.querySelector('.snc-skp-tabs')).cursor};
            }""")

        p0 = pop_state()
        check("技能抽屉已打开", p0["open"])
        check("抽屉的 tab 行光标是 move", p0["cursor"] == "move", p0["cursor"])

        page.mouse.move(p0["tabX"], p0["tabY"])
        page.mouse.down()
        page.mouse.move(p0["tabX"] + 30, p0["tabY"] + 18, steps=5)
        page.mouse.move(p0["tabX"] + 60, p0["tabY"] + 40, steps=5)
        page.wait_for_timeout(80)
        page.mouse.up()
        page.wait_for_timeout(240)
        p1 = pop_state()
        check("拖抽屉 tab 行右侧空白能移动（左 +60 容差 8）",
              abs((p1["left"] - p0["left"]) - 60) <= 8, (p0["left"], p1["left"]))
        check("拖抽屉 tab 行右侧空白能移动（上 +40 容差 8）",
              abs((p1["top"] - p0["top"]) - 40) <= 8, (p0["top"], p1["top"]))
        check("拖完抽屉仍在窗口内", p1["inView"], p1)
        page.screenshot(path=os.path.join(SHOTS, "04-抽屉拖动.png"))

        # 拖动条之外（搜索框）仍然正常
        page.fill("#sncSkpSearch", "夜景")
        page.wait_for_timeout(300)
        kept = pop_state()
        check("抽屉里的搜索框照样能输入（拖动条没抢事件）",
              page.evaluate("() => document.getElementById('sncSkpSearch').value") == "夜景"
              and abs(kept["left"] - p1["left"]) <= 1, (p1["left"], kept["left"]))
        page.fill("#sncSkpSearch", "")
        page.wait_for_timeout(220)

        # 关掉再开：位置留着
        page.click("#sncSkpClose")
        page.wait_for_timeout(220)
        page.click('#sncImgBar button[data-act="skill"]')
        page.wait_for_timeout(400)
        p2 = pop_state()
        check("抽屉重开还在拖过去的位置",
              abs(p2["left"] - p1["left"]) <= 2 and abs(p2["top"] - p1["top"]) <= 2,
              (p1["left"], p2["left"]))

        # 拖底部提示条也能动
        page.mouse.move(p2["footX"], p2["footY"])
        page.mouse.down()
        page.mouse.move(p2["footX"] - 40, p2["footY"] - 20, steps=5)
        page.wait_for_timeout(70)
        page.mouse.up()
        page.wait_for_timeout(220)
        p3 = pop_state()
        check("拖抽屉底部提示条也能移动",
              abs((p3["left"] - p2["left"]) + 40) <= 8, (p2["left"], p3["left"]))

        # 双击 tab 行复位
        page.mouse.dblclick(p3["tabX"], p3["tabY"])
        page.wait_for_timeout(320)
        p4 = pop_state()
        check("双击抽屉 tab 行回到默认锚点",
              abs(p4["left"] - p0["left"]) <= 12 and abs(p4["top"] - p0["top"]) <= 12,
              (p0["left"], p0["top"], p4["left"], p4["top"]))

        # ---------- H. 技能工作台可拖动 ----------
        box = page.evaluate("""() => {
            const t = [...document.querySelectorAll('#sncSkpBody .snc-skp-tile')][0];
            const r = t.getBoundingClientRect();
            return {x: r.x + r.width / 2, y: r.y + r.height / 2};
        }""")
        page.mouse.click(box["x"], box["y"])
        page.wait_for_timeout(450)

        def win_state():
            return page.evaluate("""() => {
                const w = document.getElementById('sncSkWin');
                const hd = w.querySelector('.snc-skwin-hd').getBoundingClientRect();
                const r = w.getBoundingClientRect();
                return {open: !w.hidden,
                        left: parseInt(w.style.left || '0', 10),
                        top: parseInt(w.style.top || '0', 10),
                        hdX: hd.x + 16, hdY: hd.y + hd.height / 2,
                        w: Math.round(r.width), h: Math.round(r.height),
                        inView: r.left >= -1 && r.top >= -1 &&
                                r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1,
                        cursor: getComputedStyle(w.querySelector('.snc-skwin-hd')).cursor};
            }""")

        w0 = win_state()
        check("技能工作台已打开", w0["open"])
        check("工作台标题栏光标是 move", w0["cursor"] == "move", w0["cursor"])

        page.mouse.move(w0["hdX"], w0["hdY"])
        page.mouse.down()
        page.mouse.move(w0["hdX"] + 40, w0["hdY"] + 26, steps=5)
        page.mouse.move(w0["hdX"] + 80, w0["hdY"] + 52, steps=5)
        page.wait_for_timeout(70)
        page.mouse.up()
        page.wait_for_timeout(240)
        w1 = win_state()
        check("拖工作台标题栏能移动（左 +80 容差 8）",
              abs((w1["left"] - w0["left"]) - 80) <= 8, (w0["left"], w1["left"]))
        check("拖工作台标题栏能移动（上 +52 容差 8）",
              abs((w1["top"] - w0["top"]) - 52) <= 8, (w0["top"], w1["top"]))
        check("拖完工作台仍在窗口内", w1["inView"], w1)
        page.screenshot(path=os.path.join(SHOTS, "05-工作台拖动.png"))

        # 提示词输入框还能正常编辑
        page.click("#sncSkWinText")
        page.keyboard.press("End")
        page.keyboard.type("，夕阳")
        page.wait_for_timeout(200)
        txt_now = page.evaluate("() => document.getElementById('sncSkWinText').value")
        check("工作台提示词框照样能编辑（拖动条没抢事件）",
              "，夕阳" in txt_now, txt_now[-40:])

        # Esc 关掉再开：位置留着
        page.keyboard.press("Escape")
        page.wait_for_timeout(240)
        page.click('#sncImgBar button[data-act="skill"]')
        page.wait_for_timeout(380)
        page.mouse.click(box["x"], box["y"])
        page.wait_for_timeout(450)
        w2 = win_state()
        check("工作台重开还在拖过去的位置",
              abs(w2["left"] - w1["left"]) <= 2 and abs(w2["top"] - w1["top"]) <= 2,
              (w1["left"], w2["left"]))

        page.mouse.dblclick(w2["hdX"], w2["hdY"])
        page.wait_for_timeout(320)
        w3 = win_state()
        check("双击工作台标题栏回到默认锚点",
              abs(w3["left"] - w0["left"]) <= 12 and abs(w3["top"] - w0["top"]) <= 12,
              (w0["left"], w0["top"], w3["left"], w3["top"]))

        check("全程没有 JS 报错", not errs, errs[:3])
        br.close()
finally:
    proc.terminate()

print("\n== 合计 %d 项 · 失败 %d ==" % (PASS + FAIL, FAIL))
if FAILS:
    for n, e in FAILS:
        print("  -", n, "->", e)
    sys.exit(1)
