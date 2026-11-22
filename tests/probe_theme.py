# -*- coding: utf-8 -*-
"""三套主题色板探针：读 CSS 变量的实际生效值，并出三张截图。

用法：python tests/probe_theme.py [SNC_BASE]
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SNC_BASE", "http://127.0.0.1:8321"))
URL = BASE + "/canvas.html"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "截图")
VARS = ["--paper", "--panel", "--card", "--raise", "--ink", "--ink2",
        "--muted", "--line", "--accent", "--ok-fg", "--err-fg"]
THEMES = ["warm", "dark", "light"]


def read_vars(pg):
    return pg.evaluate("""(names) => {
        const cs = getComputedStyle(document.getElementById('snc'));
        const o = {};
        names.forEach(n => o[n] = cs.getPropertyValue(n).trim());
        o['data-theme'] = document.getElementById('snc').getAttribute('data-theme') || '(none)';
        o['frame-theme'] = (document.getElementById('sncWinFrame') || {}).getAttribute
            ? (document.getElementById('sncWinFrame').getAttribute('data-theme') || '(none)') : 'n/a';
        return o;
    }""", VARS)


def main():
    rows = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge")
        for t in THEMES:
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_init_script(
                "try{localStorage.setItem('snc.eula.v1','1');"
                "localStorage.setItem('snc.theme.v2','%s')}catch(e){}" % t)
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(URL)
            pg.wait_for_selector('.snc-node[data-id^="g-"]')
            pg.wait_for_timeout(1400)
            rows[t] = read_vars(pg)
            pg.screenshot(path=os.path.join(OUT, "theme-%s.png" % t))
            if errs:
                print("JS 错误 @%s: %s" % (t, errs))
            ctx.close()
        b.close()

    keys = list(VARS)
    width = max(len(k) for k in keys) + 1
    print("".join(k.ljust(width) for k in [""] + THEMES))
    for k in keys:
        print("".join(str(k).ljust(width) if i == 0 else rows[t].get(k, "").ljust(width)
                      for i, t in enumerate([""] + THEMES)))
    print()
    for t in THEMES:
        print("%-6s data-theme=%s  frame=%s" % (t, rows[t]["data-theme"], rows[t]["frame-theme"]))

    # 关键断言：三套必须互不相同，且都用上了各自的强调色
    paper = [rows[t]["--paper"] for t in THEMES]
    accent = [rows[t]["--accent"] for t in THEMES]
    print()
    print("三套纸底互异:", len(set(paper)) == 3, paper)
    print("冷灰/米白共用蓝紫、暖灰是橙:",
          accent[1] == accent[2] and accent[0] != accent[1], accent)


if __name__ == "__main__":
    main()
