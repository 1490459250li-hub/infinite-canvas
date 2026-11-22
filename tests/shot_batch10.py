# -*- coding: utf-8 -*-
"""第十批实拍：圆角进度环 / logo 分级菜单 / 重新生成回填编辑框。

跑法：python tests/shot_batch10.py http://127.0.0.1:8321 [前缀]
"""
import os
import sys
from PIL import Image
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8321"
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "b10-"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "截图")
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge")
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    pg = ctx.new_page()
    pg.goto(BASE + "/canvas.html")
    pg.wait_for_selector(".snc-node:has(.snc-photo)")
    pg.wait_for_timeout(900)

    # 1) logo 分级菜单
    pg.locator("#sncDocBrandBtn").click()
    pg.wait_for_timeout(250)
    menu = os.path.join(OUT, PREFIX + "logo-分级菜单.png")
    pg.screenshot(path=menu)
    print("shot:", os.path.basename(menu))
    pg.keyboard.press("Escape")

    # 2) 进度环 99%（独立的探针环，挪到画面中央）
    pg.evaluate("() => window.SNC_TEST_API.progressRing(99)")
    pg.evaluate("""() => {
      const h = document.getElementById('sncProbeRing');
      h.style.left = '560px'; h.style.top = '300px';
      h.style.width = '240px'; h.style.height = '160px';
      h.style.zIndex = '99999'; h.style.background = '#15171a';
      h.style.boxShadow = 'inset 0 0 0 1px rgba(255,255,255,.08)';
    }""")
    pg.wait_for_timeout(300)
    ring = os.path.join(OUT, PREFIX + "进度环-99.png")
    pg.screenshot(path=ring)
    print("shot:", os.path.basename(ring))

    # 3) 四角放大拼图：把 240×160 环的四个角各裁 60×60 放大 4 倍
    im = Image.open(ring).convert("RGB")
    X, Y, W, H, S, K = 560, 300, 240, 160, 60, 4
    tiles = [("左上", (X, Y, X + S, Y + S)),
             ("右上", (X + W - S, Y, X + W, Y + S)),
             ("左下", (X, Y + H - S, X + S, Y + H)),
             ("右下", (X + W - S, Y + H - S, X + W, Y + H))]
    sheet = Image.new("RGB", (S * K * 2 + 12, S * K * 2 + 12), (24, 25, 28))
    for i, (_name, box) in enumerate(tiles):
        t = im.crop(box).resize((S * K, S * K), Image.NEAREST)
        sheet.paste(t, ((i % 2) * (S * K + 12), (i // 2) * (S * K + 12)))
    corners = os.path.join(OUT, PREFIX + "进度环-四角放大.png")
    sheet.save(corners)
    print("shot:", os.path.basename(corners))
    pg.evaluate("() => { const h=document.getElementById('sncProbeRing'); if(h) h.remove(); }")

    # 4) 重新生成回填编辑框
    pg.locator(".snc-node:has(.snc-photo)").first.click()
    pg.wait_for_timeout(300)
    pg.locator('#sncImgBar button[data-act="regen"]').click()
    pg.wait_for_timeout(350)
    regen = os.path.join(OUT, PREFIX + "重新生成-回填编辑框.png")
    pg.screenshot(path=regen)
    print("shot:", os.path.basename(regen))

    b.close()
