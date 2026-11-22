# -*- coding: utf-8 -*-
"""验证局部重绘的像素效果：在真实照片上框一块地面，只改这块，把结果存盘检查接缝。"""
import base64, os, sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8310/canvas.html"
OUT = r"C:\Users\Flish\WorkBuddy\2026-11-07-19-49-41\_inspect\p0"

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    ctx = b.new_context(viewport={"width": 1280, "height": 860})
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(800)

    gen = page.locator('.snc-node[data-id^="g-"]').first
    nid = gen.get_attribute("data-id")
    gen.click()
    page.wait_for_timeout(300)

    # v2.8：快速框选入口已撤，统一走局部重绘工作台
    page.click('#sncImgBar button[data-act="inpaint"]')
    page.wait_for_timeout(600)
    box = page.locator("#sncInpMask").bounding_box()
    # 框住下半部分地面
    x0 = box["x"] + box["width"] * 0.12
    x1 = box["x"] + box["width"] * 0.9
    y0 = box["y"] + box["height"] * 0.62
    y1 = box["y"] + box["height"] * 0.95
    page.mouse.move(x0, y0)
    page.mouse.down()
    page.mouse.move(x1, y1, steps=10)
    page.mouse.up()
    page.wait_for_timeout(300)
    rects = page.evaluate("() => window.SNC_V26_INPAINT.rects.length")
    print("maskrects:", rects)

    page.fill("#sncInpPrompt", "把这块地面换成深灰色火烧面花岗岩铺装，缝隙更宽，保持原有光照方向")
    page.click("#sncInpGo")
    # 局部重绘派生成新卡：等这张新卡把结果画出来
    page.wait_for_function(
        """() => document.querySelectorAll('.snc-node').length > 1""", timeout=30000)
    new_id = page.evaluate(
        "() => [...document.querySelectorAll('.snc-node')].pop().dataset.id")
    print("derived:", new_id)
    page.wait_for_function(
        """(id) => {
            const n = document.querySelector('.snc-node[data-id="' + id + '"]');
            if (!n) return false;
            return n.querySelector('.snc-vstrip:not([hidden])') !== null
                || n.querySelector('.snc-gen-fail') !== null;
        }""", arg=new_id, timeout=180000)
    fail = page.locator('.snc-node[data-id="%s"] .snc-fail-msg' % new_id).all_inner_texts()
    if fail:
        print("FAILED:", fail)
    page.wait_for_timeout(1200)

    data = page.evaluate("""(id) => {
        const img = document.querySelector('.snc-node[data-id="' + id + '"] .snc-photo');
        return img ? img.src : null;
    }""", new_id)
    os.makedirs(OUT, exist_ok=True)
    if data and data.startswith("data:image"):
        raw = base64.b64decode(data.split(",", 1)[1])
        path = os.path.join(OUT, "region-result.png")
        open(path, "wb").write(raw)
        print("saved", path, len(raw), "bytes")
    else:
        print("no data url:", str(data)[:60])

    page.screenshot(path=os.path.join(OUT, "region-board.png"))
    print("errors:", errs[:3])
    b.close()
