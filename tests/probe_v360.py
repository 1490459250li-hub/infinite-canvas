# -*- coding: utf-8 -*-
"""v3.6 渲染工作台手检：不烧额度（/api/generate 打桩），只验交互与拼出来的提示词。"""
import json
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHOT = r"E:\无限画布\截图\v360"
os.makedirs(SHOT, exist_ok=True)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


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
bodies = []
errs = []

try:
    with sync_playwright() as p:
        br = p.chromium.launch(channel="msedge")
        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("console", lambda m: errs.append("CONSOLE:" + m.text) if m.type == "error" else None)
        page.route("**/api/generate", lambda r: (bodies.append(r.request.post_data),
            r.fulfill(status=200, content_type="application/json",
                body=json.dumps({"ok": True, "b64": PNG, "size": "1024x1024", "width": 1024,
                                 "height": 1024, "format": "png", "model": "sensenova-u1.5-fast",
                                 "provider": "sensenova", "latencyMs": 900}))))
        page.goto(BASE + "/canvas.html")
        page.wait_for_selector(".snc-node")
        page.wait_for_timeout(900)

        # 选中第一张图（图片 1），打开技能抽屉
        page.evaluate("""() => {
            const d = [...document.querySelectorAll('.snc-node')]
              .find(x => (x.querySelector('.snc-node-label')||{}).textContent === '图片 1');
            const r = d.getBoundingClientRect();
            d.dispatchEvent(new MouseEvent('pointerdown', {bubbles:true, clientX:r.x+40, clientY:r.y+40}));
            d.dispatchEvent(new MouseEvent('pointerup', {bubbles:true, clientX:r.x+40, clientY:r.y+40}));
            d.dispatchEvent(new MouseEvent('click', {bubbles:true, clientX:r.x+40, clientY:r.y+40}));
        }""")
        page.wait_for_timeout(400)
        page.click('#sncImgBar button[data-act="skill"]')
        page.wait_for_timeout(400)
        tabs = page.evaluate("() => [...document.querySelectorAll('#sncSkpTabs button')].map(b=>b.textContent.trim())")
        print("tabs:", tabs)
        # v3.7 起渲染 4 条并回「通用技能」并排在最前，单独的「渲染」页签已经取消
        page.click('#sncSkpTabs button[data-g="general"]')
        page.wait_for_timeout(350)
        tiles = page.evaluate("() => [...document.querySelectorAll('#sncSkpBody .snc-skp-tile em')].map(e=>e.textContent)")
        print("general tiles (前 4 条应是渲染类):", tiles[:4])
        page.screenshot(path=os.path.join(SHOT, "01-渲染页签.png"))

        # 点建筑渲染
        page.click('#sncSkpBody .snc-skp-tile')
        page.wait_for_timeout(500)
        win = page.evaluate("""() => {
            const w = document.getElementById('sncSkWin');
            const r = w.getBoundingClientRect();
            return {open: !w.hidden, x: r.x, y: r.y, w: r.width, h: r.height,
                    inbox: r.x >= 0 && r.y >= 0 && r.right <= innerWidth && r.bottom <= innerHeight,
                    chips: [...w.querySelectorAll('.snc-skwin-chip')].map(b=>b.textContent.trim()),
                    ref: !!w.querySelector('.snc-skwin-ref img'),
                    pop: !document.getElementById('sncSkillPop').hidden,
                    name: document.getElementById('sncSkWinName').textContent};
        }""")
        print("window:", win)
        page.screenshot(path=os.path.join(SHOT, "02-建筑渲染窗口.png"))

        # 建筑类型 → 办公建筑 → 高层办公
        page.click('#sncSkWinChips button[data-chip="building"]')
        page.wait_for_timeout(300)
        page.screenshot(path=os.path.join(SHOT, "03-建筑类型一级.png"))
        page.click('#sncSkWinMenu button[data-m="office"]')
        page.wait_for_timeout(250)
        page.screenshot(path=os.path.join(SHOT, "04-建筑类型二级.png"))
        page.click('#sncSkWinMenu button[data-m="high_rise_office"]')
        page.wait_for_timeout(250)

        page.click('#sncSkWinChips button[data-chip="time"]')
        page.wait_for_timeout(250)
        page.click('#sncSkWinMenu button[data-m="evening"]')
        page.wait_for_timeout(200)
        page.click('#sncSkWinChips button[data-chip="weather"]')
        page.wait_for_timeout(250)
        page.click('#sncSkWinMenu button[data-m="clear"]')
        page.wait_for_timeout(200)
        chips2 = page.evaluate("() => [...document.querySelectorAll('#sncSkWinChips .snc-skwin-chip')].map(b=>b.textContent.trim()+(b.classList.contains('is-on')?'*':''))")
        print("chips after pick:", chips2)
        page.fill("#sncSkWinText", "加强入口雨棚的暖光")
        page.screenshot(path=os.path.join(SHOT, "05-选完参数.png"))

        page.click("#sncSkWinGo")
        page.wait_for_timeout(2500)
        print("bodies:", len(bodies))
        if bodies:
            try:
                js = json.loads(bodies[0])
                print("prompt:\n", js.get("prompt", "")[:900])
            except Exception as e:
                print("parse fail", e, bodies[0][:300])
        st = page.evaluate("""() => ({win: !document.getElementById('sncSkWin').hidden,
                                     compose: !document.getElementById('sncCompose').hidden,
                                     cards: document.querySelectorAll('.snc-node').length})""")
        print("after generate:", st)
        page.screenshot(path=os.path.join(SHOT, "06-生成后.png"))

        # 手绘渲染：12 画风（刷新一次，避开刚生成的卡还在跑）
        page.reload()
        page.wait_for_selector(".snc-node")
        page.wait_for_timeout(1200)
        page.evaluate("""() => {
            const d = [...document.querySelectorAll('.snc-node')]
              .find(x => (x.querySelector('.snc-node-label')||{}).textContent === '图片 1');
            const r = d.getBoundingClientRect();
            d.dispatchEvent(new MouseEvent('pointerdown', {bubbles:true, clientX:r.x+40, clientY:r.y+40}));
            d.dispatchEvent(new MouseEvent('pointerup', {bubbles:true, clientX:r.x+40, clientY:r.y+40}));
            d.dispatchEvent(new MouseEvent('click', {bubbles:true, clientX:r.x+40, clientY:r.y+40}));
        }""")
        page.wait_for_timeout(400)
        page.click('#sncImgBar button[data-act="skill"]')
        page.wait_for_timeout(300)
        page.click('#sncSkpTabs button[data-g="general"]')
        page.wait_for_timeout(300)
        page.evaluate("""() => [...document.querySelectorAll('#sncSkpBody .snc-skp-tile')]
            .find(t => t.querySelector('em').textContent.indexOf('手绘') >= 0).click()""")
        page.wait_for_timeout(400)
        page.click('#sncSkWinChips button[data-chip="style"]')
        page.wait_for_timeout(300)
        styles = page.evaluate("() => [...document.querySelectorAll('#sncSkWinMenu button[data-m]')].map(b=>b.textContent.trim())")
        print("styles:", len(styles), styles)
        page.screenshot(path=os.path.join(SHOT, "07-手绘画风.png"))
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        print("esc closes:", page.evaluate("() => document.getElementById('sncSkWin').hidden"))
        print("errors:", errs[:5])
        br.close()
finally:
    proc.terminate()
