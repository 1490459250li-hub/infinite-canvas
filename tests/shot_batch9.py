# -*- coding: utf-8 -*-
"""第九批实拍：空白启动 / 进度环 99% / 退出前保存确认。

跑法：python tests/shot_batch9.py http://127.0.0.1:8321
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8321"
# 第二个参数给截图文件名加前缀，方便同一批同时留「源码版」和「打包版」两套实拍
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "b9-"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "截图")
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge")
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    pg = ctx.new_page()
    pg.goto(BASE + "/canvas.html?plain=1")
    pg.wait_for_timeout(1200)
    pg.screenshot(path=os.path.join(OUT, PREFIX + "空白启动.png"))
    print("shot: " + PREFIX + "空白启动.png")

    pg.evaluate("() => window.SNC_TEST_API.progressRing(99)")
    pg.evaluate("""() => {
      const h = document.getElementById('sncProbeRing');
      h.style.left = '560px'; h.style.top = '300px';
      h.style.zIndex = '99999'; h.style.background = '#15171a';
      h.style.boxShadow = 'inset 0 0 0 1px rgba(255,255,255,.08)';
    }""")
    pg.wait_for_timeout(300)
    pg.screenshot(path=os.path.join(OUT, PREFIX + "进度环-99.png"))
    print("shot: " + PREFIX + "进度环-99.png")

    pg.evaluate("() => document.getElementById('sncProbeRing').remove()")
    pg.evaluate("() => window.SNC_TEST_API.dirty()")
    pg.evaluate("() => window.__sncRequestQuit()")
    pg.wait_for_timeout(250)
    pg.screenshot(path=os.path.join(OUT, PREFIX + "退出前保存确认.png"))
    print("shot: " + PREFIX + "退出前保存确认.png")

    b.close()
