# -*- coding: utf-8 -*-
"""v2.9 冒烟：先确认页面没抛错、新控件都在，再细看行为。"""
import json, os, sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get("SNC_BASE", "http://127.0.0.1:8321/canvas.html")
SHOTS = r"E:\canvas-probe2\shots-v29"
os.makedirs(SHOTS, exist_ok=True)
errs = []

with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    ctx = br.new_context(viewport={"width": 1560, "height": 940})
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
    pg.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" else None)
    pg.goto(BASE)
    pg.wait_for_timeout(1500)
    print("nodes:", pg.locator(".snc-node").count())
    print("imgs:", pg.locator(".snc-node .snc-photo").count())
    print("errs:", errs[:5])

    # 顶部按钮
    for sel in ["#sncLayersBtn", "#sncMiniBtn", "#sncTidyBtn", "#sncGAttBtn", "#sncGFile"]:
        print(sel, pg.locator(sel).count())
    # 旧蒙版是否彻底没了
    print("masklayer:", pg.locator(".snc-masklayer").count(),
          "maskhint:", pg.locator("#sncMaskHint").count(),
          "act=mask btn:", pg.locator('#sncImgBar button[data-act="mask"]').count())
    # 图层
    pg.click("#sncLayersBtn")
    pg.wait_for_timeout(300)
    rows = pg.locator("#sncLayersBody .snc-layer-row").count()
    eyes = pg.locator("#sncLayersBody .snc-layer-eye").count()
    print("layer rows:", rows, "eyes:", eyes)
    print("tools:", pg.locator("#sncLayersGroup").count(), pg.locator("#sncLayersUngroup").count())
    pg.screenshot(path=os.path.join(SHOTS, "layers-ps.png"))

    # 工作台：先选一张有图的卡，浮动条才有 inpaint
    pg.click("#sncFit")
    pg.wait_for_timeout(300)
    pg.locator(".snc-node .snc-photo").first.click()
    pg.wait_for_timeout(300)
    pg.click('#sncImgBar button[data-act="inpaint"]')
    pg.wait_for_timeout(600)
    print("help btn:", pg.locator("#sncInpHelp").count())
    print("tools:", pg.locator("#sncInpTools button").all_inner_texts())
    print("modes:", pg.locator('#sncInp [data-group="mode"] button').all_inner_texts())
    print("res:", pg.locator('#sncInp [data-group="res"] button').all_inner_texts())
    print("tools chip:", pg.locator('#sncInp [data-group="tool"] button').all_inner_texts())
    print("refadd:", pg.locator("#sncInpRefAdd").count())
    pg.screenshot(path=os.path.join(SHOTS, "inpaint-v29.png"))

    # 描述重绘显隐
    pg.click('#sncInp [data-group="mode"] button[data-v="desc"]')
    pg.wait_for_timeout(200)
    print("desc -> tool sec hidden:",
          pg.evaluate("() => document.getElementById('sncInpSecTool').hidden"),
          "edit sec hidden:", pg.evaluate("() => document.getElementById('sncInpSecEdit').hidden"))
    pg.screenshot(path=os.path.join(SHOTS, "desc-mode.png"))
    pg.click('#sncInp [data-group="mode"] button[data-v="select"]')
    pg.wait_for_timeout(200)
    print("select -> tool sec hidden:",
          pg.evaluate("() => document.getElementById('sncInpSecTool').hidden"))
    print("errs2:", errs[:8])
    ctx.close()
    br.close()
