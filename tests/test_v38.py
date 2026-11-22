# -*- coding: utf-8 -*-
"""v3.6 回归：渲染类技能（建筑 / 鸟瞰 / 景观 / 手绘）+ D5 式渲染工作台弹窗。

A 段：源码断言（技能定义、chips 绑定、两级分类、工作台 DOM/CSS、提交链路复用）。
B 段：浏览器实测（渲染页签、弹窗、两级下拉、三套参数生成、提示词内容、Esc 关闭）。
出图接口全部打桩，不消耗额度，也不调用 /api/config/clear。
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
dist = open(DIST_HTML, encoding="utf-8").read()

print("\n== A  源码 ==")
check("版本号 >= 3.6.0", server._ver_key(server.APP_VERSION) >= server._ver_key("3.6.0"),
      server.APP_VERSION)

# ---- 四条渲染技能 ----
for sid, name in [("r-bldg", "建筑渲染"), ("r-aerial", "鸟瞰渲染"),
                  ("r-land", "景观渲染"), ("r-hand", "手绘渲染")]:
    check("内置技能有「%s」" % name, ('id:"%s"' % sid) in src and ('name:"%s"' % name) in src)
check("四条渲染技能归到 render 分组", src.count('group:"render"') == 4,
      src.count('group:"render"'))
check("建筑渲染绑定 建筑类型/时间/天气",
      all(k in src for k in ['k:"building", t:"建筑类型"', 'k:"time", t:"时间"',
                             'k:"weather", t:"天气"']))
check("景观渲染绑定 景观类型/时间/天气",
      all(k in src for k in ['k:"landscape", t:"景观类型"', 'k:"time", t:"时间"',
                             'k:"weather", t:"天气"']))
check("手绘渲染绑定画风", '{k:"style", t:"画风", art:true}' in src)
check("渲染 4 条并回通用并排最前", "return {general: r.concat(g), pro: p, mine: userSkills.slice()};" in src)
check("抽屉回到三个页签（渲染页签已删）", 'data-g="render"' not in src)

# ---- D5 的四个大类清单 ----
for label in ["钢笔画", "水彩画", "小清新拼贴", "波普风艺术", "铅笔素描", "马克笔手绘",
              "建筑技术线稿", "白模表现", "后数字建筑插画", "复古建筑拼贴", "水墨淡彩",
              "孔版印刷"]:
    check("手绘 12 画风含「%s」" % label, '"l": "%s"' % label in src)
for label in ["四宫格", "九宫格", "十六宫格", "二十五宫格"]:
    check("场景分镜含「%s」" % label, '"l": "%s"' % label in src)
for label in ["办公建筑", "商业建筑", "住宅建筑", "酒店建筑", "教育建筑", "公共文化",
              "医疗康养", "乡村农业", "工业建筑", "交通建筑", "城市规划", "通用建筑"]:
    check("建筑类型 12 类含「%s」" % label, '"l": "%s"' % label in src)
for label in ["城市开放空间", "城郊公园", "商业办公", "住宅花园", "酒店度假景观",
              "公共文化景观", "乡村农业景观", "道路交通", "造园风格", "构筑与小品",
              "水景设计", "通用景观"]:
    check("景观类型 12 类含「%s」" % label, '"l": "%s"' % label in src)

# ---- 工作台弹窗 ----
check("工作台 DOM 存在", 'id="sncSkWin"' in src and 'id="sncSkWinChips"' in src and
      'id="sncSkWinText"' in src and 'id="sncSkWinGo"' in src)
check("工作台样式存在", "#snc .snc-skwin{" in src and "#snc .snc-skwin-menu{" in src)
check("所有技能都走同一个弹窗", "function useSkillOn(n, sk){" in src and
      "openSkillWin(n, sk, imgBar.querySelector" in src)
check("旧的纯文字选项菜单已删除",
      'id="sncSkillOptMenu"' not in src and "function showSkillOpts" not in src and
      "function applySkillToNode" not in src)
check("生成复用编辑提交链路", "function submitEdit(){" in src and
      "document.getElementById(\"sncComposeSend\").addEventListener(\"click\", submitEdit);" in src)
check("弹窗生成时编辑面板不亮出来", "openCompose(n, {silent: true})" in src and
      'var silent = !!(opt && opt.silent);' in src)
check("Esc 先关工作台", "if(skWinEl && !skWinEl.hidden){ closeSkillWin(); return; }" in src)
check("点窗外收起工作台", '!e.target.closest("#sncSkWin")' in src)
check("时间/天气有画面级短语", "var WIN_PHRASE = {" in src and "time: {" in src and "weather: {" in src)
check("四条渲染技能都有 head + body", src.count('head:"把这张图渲染') == 3)
check("canvas.html 已重建到 3.6", "snc-skwin" in dist and "r-bldg" in dist)


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
errs, bodies = [], []


def gen(route):
    try:
        bodies.append(json.loads(route.request.post_data or "{}"))
    except Exception:
        bodies.append({})
    route.fulfill(status=200, content_type="application/json",
                  body=json.dumps({"ok": True, "b64": PNG, "size": "1024x1024", "width": 1024,
                                   "height": 1024, "format": "png", "model": "stub-image",
                                   "provider": "sensenova", "latencyMs": 600,
                                   "usage": {"total_tokens": 100}}))


SELECT = """() => {
    const d = [...document.querySelectorAll('.snc-node')]
      .find(x => (x.querySelector('.snc-node-label')||{}).textContent === '图片 1');
    if(!d) return false;
    const r = d.getBoundingClientRect();
    const opt = {bubbles:true, clientX:r.x+40, clientY:r.y+40};
    d.dispatchEvent(new MouseEvent('pointerdown', opt));
    d.dispatchEvent(new MouseEvent('pointerup', opt));
    d.dispatchEvent(new MouseEvent('click', opt));
    return true;
}"""


def open_render_tab(page):
    page.click("#sncFit")          # 先把全部卡片收进视口，工具条才不会在屏幕外
    page.wait_for_timeout(420)
    page.evaluate(SELECT)
    page.wait_for_timeout(320)
    page.click('#sncImgBar button[data-act="skill"]')
    page.wait_for_timeout(320)


def pick(page, chip, *path):
    page.click('#sncSkWinChips button[data-chip="%s"]' % chip)
    page.wait_for_timeout(200)
    for v in path:
        page.click('#sncSkWinMenu button[data-m="%s"]' % v)
        page.wait_for_timeout(200)


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
        page.wait_for_timeout(1100)

        # ---- B1 渲染页签的四条技能 ----
        open_render_tab(page)
        tabs = page.evaluate("() => [...document.querySelectorAll('#sncSkpTabs button')].map(b=>b.textContent.trim())")
        check("技能抽屉三个页签", len(tabs) == 3, tabs)
        tiles = page.evaluate("() => [...document.querySelectorAll('#sncSkpBody .snc-skp-tile em')].map(e=>e.textContent)")
        check("通用技能页最前面是 4 条渲染技能",
              tiles[:4] == ["建筑渲染", "鸟瞰渲染", "景观渲染", "手绘渲染"], tiles[:6])

        # ---- B2 点技能弹工作台，不烧额度 ----
        page.click('#sncSkpBody .snc-skp-tile')
        page.wait_for_timeout(480)
        win = page.evaluate("""() => {
            const w = document.getElementById('sncSkWin');
            const r = w.getBoundingClientRect();
            return {open: !w.hidden, name: document.getElementById('sncSkWinName').textContent,
                    chips: [...w.querySelectorAll('.snc-skwin-chip')].map(b=>b.dataset.chip),
                    ref: !!w.querySelector('.snc-skwin-ref img'),
                    pop: !document.getElementById('sncSkillPop').hidden,
                    compose: !document.getElementById('sncCompose').hidden,
                    inbox: r.x >= 0 && r.y >= 0 && r.right <= innerWidth && r.bottom <= innerHeight,
                    w: Math.round(r.width), h: Math.round(r.height)};
        }""")
        check("点「建筑渲染」弹出工作台", bool(win) and win["open"] and win["name"] == "建筑渲染", win)
        check("工作台三个参数 chips", win["chips"] == ["building", "time", "weather"], win["chips"])
        check("工作台带当前图缩略图", bool(win) and win["ref"], win)
        check("技能抽屉自动收起", bool(win) and not win["pop"], win)
        check("工作台整块在窗口内", bool(win) and win["inbox"], win)
        check("只看参数不发请求", len(bodies) == 0, len(bodies))

        # ---- B3 建筑类型两级 ----
        page.click('#sncSkWinChips button[data-chip="building"]')
        page.wait_for_timeout(250)
        lvl1 = page.evaluate("() => [...document.querySelectorAll('#sncSkWinMenu button[data-m]')].map(b=>b.dataset.m)")
        check("建筑类型一级 12 类 + 不限", len(lvl1) == 13 and "office" in lvl1, lvl1)
        page.click('#sncSkWinMenu button[data-m="office"]')
        page.wait_for_timeout(220)
        lvl2 = page.evaluate("() => [...document.querySelectorAll('#sncSkWinMenu button[data-m]')].map(b=>b.dataset.m)")
        check("办公建筑下钻出子类", len(lvl2) >= 5 and "high_rise_office" in lvl2, lvl2)
        page.click('#sncSkWinMenu button[data-m="high_rise_office"]')
        page.wait_for_timeout(220)
        chip_txt = page.inner_text('#sncSkWinChips button[data-chip="building"]')
        check("选完大类+子类，chip 显示子类名", chip_txt.strip() == "高层办公", chip_txt)
        check("菜单选完自动收起",
              page.evaluate("() => document.getElementById('sncSkWinMenu').hidden"))

        # ---- B4 时间 / 天气 + 补充描述 ----
        pick(page, "time", "evening")
        pick(page, "weather", "clear")
        chips2 = page.evaluate("""() => [...document.querySelectorAll('#sncSkWinChips .snc-skwin-chip')]
            .map(b => b.textContent.trim())""")
        check("三个 chip 都带上选中值", chips2 == ["高层办公", "傍晚", "晴朗"], chips2)
        page.evaluate("""() => {
            const t = document.getElementById('sncSkWinText');
            t.value = t.value + "\\n补充要求：加强入口雨棚的暖光";
            t.dispatchEvent(new Event('input', {bubbles:true}));
        }""")

        # ---- B5 生成 = 一次请求，提示词带全参数 ----
        before = page.evaluate("() => document.querySelectorAll('.snc-node').length")
        page.click("#sncSkWinGo")
        page.wait_for_timeout(2600)
        after = page.evaluate("() => document.querySelectorAll('.snc-node').length")
        check("生成派生了一张新卡", after == before + 1, (before, after))
        check("生成后工作台关闭",
              page.evaluate("() => document.getElementById('sncSkWin').hidden"))
        check("生成后编辑面板没被亮出来",
              page.evaluate("() => document.getElementById('sncCompose').hidden"))
        check("只发了一次出图请求", len(bodies) == 1, len(bodies))
        pr = (bodies[-1].get("prompt") or "") if bodies else ""
        check("提示词带建筑类型（大类+子类）", "办公建筑 · 高层办公" in pr, pr[:160])
        check("提示词带时间短语", "傍晚，黄金时刻" in pr, pr[:200])
        check("提示词带天气短语", "晴朗，天空干净通透" in pr, pr[:220])
        check("提示词带补充描述", "补充要求：加强入口雨棚的暖光" in pr, pr[-80:])
        check("提示词没有重复首句", pr.count("照片级的建筑表现图") == 1, pr.count("照片级的建筑表现图"))
        check("主编辑图作为第 1 张参考图发出",
              "第 1 张：主编辑图" in pr, pr[-120:])

        # ---- B6 手绘渲染：12 画风 + 水彩生成 ----
        page.reload()
        page.wait_for_selector(".snc-node")
        page.wait_for_timeout(1200)
        open_render_tab(page)
        page.evaluate("""() => [...document.querySelectorAll('#sncSkpBody .snc-skp-tile')]
            .find(t => t.querySelector('em').textContent === '手绘渲染').click()""")
        page.wait_for_timeout(420)
        check("手绘渲染只有画风一个 chip",
              page.evaluate("() => [...document.querySelectorAll('#sncSkWinChips .snc-skwin-chip')].map(b=>b.dataset.chip)") == ["style"])
        page.click('#sncSkWinChips button[data-chip="style"]')
        page.wait_for_timeout(250)
        styles = page.evaluate("() => [...document.querySelectorAll('#sncSkWinMenu button[data-m]')].map(b=>b.textContent.trim())")
        check("画风下拉 12 项（不含不限）", len(styles) == 13, len(styles))
        check("画风首项是钢笔画", styles[1] == "钢笔画", styles[:3])
        page.click('#sncSkWinMenu button[data-m="watercolor"]')
        page.wait_for_timeout(220)
        page.click("#sncSkWinGo")
        page.wait_for_timeout(2400)
        pr2 = (bodies[-1].get("prompt") or "") if bodies else ""
        check("手绘生成带上画风执行细则", "水彩建筑表现" in pr2, pr2[:200])
        check("手绘生成标明目标画风", "目标画风：水彩" in pr2, pr2[:200])

        # ---- B7 景观渲染：12 类 + 生成 ----
        page.reload()
        page.wait_for_selector(".snc-node")
        page.wait_for_timeout(1200)
        open_render_tab(page)
        page.evaluate("""() => [...document.querySelectorAll('#sncSkpBody .snc-skp-tile')]
            .find(t => t.querySelector('em').textContent === '景观渲染').click()""")
        page.wait_for_timeout(420)
        page.click('#sncSkWinChips button[data-chip="landscape"]')
        page.wait_for_timeout(250)
        lands = page.evaluate("() => [...document.querySelectorAll('#sncSkWinMenu button[data-m]')]"
                             ".slice(1).map(b=>b.textContent.trim())")
        check("景观类型一级 12 类", len(lands) == 12, lands)
        check("景观首项是城市开放空间", lands[0].startswith("城市开放空间"), lands[:3])
        page.click('#sncSkWinMenu button[data-m="public_realm"]')
        page.wait_for_timeout(250)
        page.click('#sncSkWinMenu button[data-m="urban_park"]')
        page.wait_for_timeout(250)
        lchip = page.inner_text('#sncSkWinChips button[data-chip="landscape"]')
        check("景观 chip 显示子类名", lchip.strip() == "城市公园", lchip)
        page.click("#sncSkWinGo")
        page.wait_for_timeout(2400)
        pr3 = (bodies[-1].get("prompt") or "") if bodies else ""
        check("景观生成走景观口径", "照片级的景观表现图" in pr3, pr3[:120])
        check("景观生成带场景类型", "场景类型为「" in pr3, pr3[:160])

        # ---- B8 Esc / 点外面收起 ----
        page.reload()
        page.wait_for_selector(".snc-node")
        page.wait_for_timeout(1200)
        open_render_tab(page)
        page.click('#sncSkpBody .snc-skp-tile')
        page.wait_for_timeout(400)
        page.keyboard.press("Escape")
        page.wait_for_timeout(280)
        check("Esc 收起工作台",
              page.evaluate("() => document.getElementById('sncSkWin').hidden"))
        open_render_tab(page)
        page.click('#sncSkpBody .snc-skp-tile')
        page.wait_for_timeout(400)
        page.mouse.click(200, 700)
        page.wait_for_timeout(300)
        check("点窗外收起工作台",
              page.evaluate("() => document.getElementById('sncSkWin').hidden"))
        check("全程没有 JS 报错", not errs, errs[:3])
        br.close()
finally:
    proc.terminate()

print("\n== 合计 %d 项 · 失败 %d ==" % (PASS + FAIL, FAIL))
if FAILS:
    for n, e in FAILS:
        print("  -", n, "->", e)
    sys.exit(1)
