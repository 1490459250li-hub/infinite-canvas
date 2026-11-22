# -*- coding: utf-8 -*-
"""设置页主题选择器截图（三套主题各一张）。"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SNC_BASE", "http://127.0.0.1:8321")
URL = BASE + "/canvas.html"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "截图")

with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge")
    for t in ["warm", "dark", "light"]:
        ctx = b.new_context(viewport={"width": 1280, "height": 820})
        ctx.add_init_script(
            "try{localStorage.setItem('snc.eula.v1','1');"
            "localStorage.setItem('snc.theme.v2','%s')}catch(e){}" % t)
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(URL)
        pg.wait_for_selector('.snc-node[data-id^="g-"]')
        pg.wait_for_timeout(1000)
        pg.click('[data-set="1"]')
        pg.wait_for_timeout(700)
        pg.screenshot(path=os.path.join(OUT, "theme-set-%s.png" % t))
        now = pg.inner_text("#sncThemeNow") if pg.locator("#sncThemeNow").count() else "?"
        print("%-6s %s%s" % (t, now, ("  JS错误:" + str(errs)) if errs else ""))
        ctx.close()
    b.close()
