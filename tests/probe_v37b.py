# -*- coding: utf-8 -*-
"""v3.7 技能工作台手检：点技能 → 一个窗，参数 0/1/2 个都是同一套骨架。"""
import json, os, sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get("SNC_BASE") or "http://127.0.0.1:8321/canvas.html"
SHOT = r"E:\无限画布\截图\v37b"
os.makedirs(SHOT, exist_ok=True)

SELECT = """() => {
  const d = [...document.querySelectorAll('.snc-node')]
    .find(x => (x.querySelector('.snc-node-label')||{}).textContent === '图片 1');
  const r = d.getBoundingClientRect();
  ['pointerdown','pointerup','click'].forEach(t =>
    d.dispatchEvent(new MouseEvent(t,{bubbles:true,clientX:r.x+40,clientY:r.y+40})));
}"""

def open_skill(page, name):
    page.click('#sncImgBar button[data-act="skill"]')
    page.wait_for_timeout(420)
    box = page.evaluate("""(name) => {
      const t = [...document.querySelectorAll('#sncSkpBody .snc-skp-tile')]
        .find(x => (x.querySelector('em')||{}).textContent.trim() === name);
      if(!t) return null;
      const r = t.getBoundingClientRect();
      return {x:r.x+r.width/2, y:r.y+r.height/2};
    }""", name)
    assert box, "找不到技能 " + name
    page.mouse.click(box["x"], box["y"])
    page.wait_for_timeout(420)

def win(page):
    return page.evaluate("""() => {
      const w = document.getElementById('sncSkWin');
      return {
        open: !w.hidden,
        name: document.getElementById('sncSkWinName').textContent,
        chips: [...document.querySelectorAll('#sncSkWinChips .snc-skwin-chip')].map(b=>b.textContent.trim()),
        text: document.getElementById('sncSkWinText').value,
        opts: [...document.querySelectorAll('.snc-skwin-opts select')].map(s=>s.value),
        hint: document.getElementById('sncSkWinHint').textContent,
        h: Math.round(w.getBoundingClientRect().height)
      };
    }""")

with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    ctx = br.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(1500)
    page.click("#sncFit")
    page.wait_for_timeout(500)
    page.evaluate(SELECT)
    page.wait_for_timeout(350)

    # 1) 抽屉只有三个页签
    page.click('#sncImgBar button[data-act="skill"]')
    page.wait_for_timeout(400)
    tabs = page.eval_on_selector_all("#sncSkpTabs button[data-g]", "e=>e.map(x=>x.textContent.trim())")
    print("页签:", tabs)
    first = page.eval_on_selector_all("#sncSkpBody .snc-skp-tile em", "e=>e.slice(0,4).map(x=>x.textContent)")
    print("通用首四:", first)
    page.screenshot(path=os.path.join(SHOT, "01-抽屉三页签.png"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(250)

    # 2) 无参数技能
    open_skill(page, "夜景转换")
    w = win(page)
    print("\n[夜景转换] chips=%s h=%s" % (w["chips"], w["h"]))
    print("  提示词:", w["text"][:90].replace("\n", " / "))
    page.query_selector("#sncSkWin").screenshot(path=os.path.join(SHOT, "02-零参数.png"))
    page.keyboard.press("Escape"); page.wait_for_timeout(250)

    # 3) 一个参数：时间迁移
    open_skill(page, "时间迁移")
    w = win(page)
    print("\n[时间迁移] chips=%s h=%s" % (w["chips"], w["h"]))
    page.click('#sncSkWinChips button[data-chip="time"]')
    page.wait_for_timeout(280)
    opts = page.eval_on_selector_all("#sncSkWinMenu button[data-m]", "e=>e.map(x=>x.textContent.trim())")
    print("  下拉:", opts)
    page.click('#sncSkWinMenu button[data-m="evening"]')
    page.wait_for_timeout(320)
    w = win(page)
    print("  选后 chip:", w["chips"], "| 提示词:", w["text"][:80].replace("\n", " / "))
    page.query_selector("#sncSkWin").screenshot(path=os.path.join(SHOT, "03-单参数.png"))
    page.keyboard.press("Escape"); page.wait_for_timeout(250)

    # 4) 三个参数 + 两级下钻：建筑渲染
    open_skill(page, "建筑渲染")
    w = win(page)
    print("\n[建筑渲染] 初始 chips=%s opts=%s h=%s" % (w["chips"], w["opts"], w["h"]))
    page.click('#sncSkWinChips button[data-chip="building"]')
    page.wait_for_timeout(260)
    page.click('#sncSkWinMenu button[data-m="office"]')
    page.wait_for_timeout(260)
    lvl2 = page.eval_on_selector_all("#sncSkWinMenu button[data-m]", "e=>e.map(x=>x.textContent.trim())")
    print("  二级:", lvl2)
    page.query_selector("#sncSkWin").screenshot(path=os.path.join(SHOT, "04-两级下钻.png"))
    page.click('#sncSkWinMenu button[data-m="high_rise_office"]')
    page.wait_for_timeout(280)
    page.click('#sncSkWinChips button[data-chip="time"]')
    page.wait_for_timeout(260)
    page.click('#sncSkWinMenu button[data-m="evening"]')
    page.wait_for_timeout(280)
    page.click('#sncSkWinChips button[data-chip="weather"]')
    page.wait_for_timeout(260)
    page.click('#sncSkWinMenu button[data-m="clear"]')
    page.wait_for_timeout(320)
    w = win(page)
    print("  选后 chips:", w["chips"])
    print("  提示词:")
    for line in w["text"].split("\n"):
        print("   ·", line[:110])
    page.query_selector("#sncSkWin").screenshot(path=os.path.join(SHOT, "05-三参数.png"))
    page.screenshot(path=os.path.join(SHOT, "06-整屏.png"))
    page.keyboard.press("Escape"); page.wait_for_timeout(250)

    # 5) 场景分镜：宫格下拉
    open_skill(page, "场景分镜")
    page.click('#sncSkWinChips button[data-chip="layout"]')
    page.wait_for_timeout(280)
    print("\n[场景分镜] 宫格:", page.eval_on_selector_all("#sncSkWinMenu button[data-m]", "e=>e.map(x=>x.textContent.trim())"))
    page.click('#sncSkWinMenu button[data-m="grid_9"]')
    page.wait_for_timeout(300)
    w = win(page)
    print("  提示词:", w["text"][:100].replace("\n", " / "))
    page.query_selector("#sncSkWin").screenshot(path=os.path.join(SHOT, "07-分镜宫格.png"))
    page.keyboard.press("Escape"); page.wait_for_timeout(250)

    # 6) 手绘渲染：12 画风 + 默认值 + ART_STYLE 整段
    open_skill(page, "手绘渲染")
    w = win(page)
    print("\n[手绘渲染] chips=%s" % w["chips"])
    print("  提示词首行:", w["text"].split("\n")[0][:120])
    page.click('#sncSkWinChips button[data-chip="style"]')
    page.wait_for_timeout(280)
    styles = page.eval_on_selector_all("#sncSkWinMenu button[data-m]", "e=>e.map(x=>x.textContent.trim())")
    print("  画风(%d):" % len(styles), styles)
    page.click('#sncSkWinMenu button[data-m="watercolor"]')
    page.wait_for_timeout(320)
    w = win(page)
    print("  选水彩后首行:", w["text"].split("\n")[0][:120])
    page.query_selector("#sncSkWin").screenshot(path=os.path.join(SHOT, "08-手绘画风.png"))

    # 7) 手改提示词 → hint 变，再改参数不覆盖
    page.evaluate("""() => {
      const t = document.getElementById('sncSkWinText');
      t.value = '这是我手改过的提示词';
      t.dispatchEvent(new Event('input', {bubbles:true}));
    }""")
    page.wait_for_timeout(200)
    h1 = win(page)["hint"]
    page.click('#sncSkWinChips button[data-chip="style"]')
    page.wait_for_timeout(250)
    page.click('#sncSkWinMenu button[data-m="ink_pen"]')
    page.wait_for_timeout(300)
    w = win(page)
    print("\n[手改] hint=%s | 文本=%s" % (h1, w["text"]))
    page.keyboard.press("Escape"); page.wait_for_timeout(250)

    print("\nJS 错误:", errs[:5] if errs else "无")
    br.close()
