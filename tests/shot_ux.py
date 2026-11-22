# -*- coding: utf-8 -*-
"""v3.7.4 第四批视觉探针：比例图形选择器 + 空态引导，三套主题各出一张。

  ux-params-<theme>.png  底部参数行特写（比例方块 + 胶囊）
  ux-empty-<theme>.png   空态引导全景
  ux-params-narrow.png   窄窗（1200 宽）下参数行是否仍挤得下

用法：python tests/shot_ux.py [SNC_BASE]
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SNC_BASE", "http://127.0.0.1:8321"))
URL = BASE + "/canvas.html"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "截图")
THEMES = ["warm", "dark", "light"]

READ_JS = """() => {
  const snc = document.getElementById('snc');
  const cs = getComputedStyle(snc);
  const pick = document.getElementById('sncGRatioPick');
  const btns = pick ? [...pick.querySelectorAll('button[data-r]')] : [];
  const on = btns.filter(b => b.getAttribute('aria-checked') === 'true')[0];
  const onI = on ? on.querySelector('i') : null;
  const rows = document.querySelector('.snc-p-params');
  return {
    theme: snc.getAttribute('data-theme') || '(none)',
    '--accent': cs.getPropertyValue('--accent').trim(),
    '--raise': cs.getPropertyValue('--raise').trim(),
    n: btns.length,
    checked: on ? on.dataset.r : '(none)',
    on_bg: on ? getComputedStyle(on).backgroundColor : '(none)',
    on_fg: on ? getComputedStyle(on).color : '(none)',
    shape: onI ? [Math.round(onI.getBoundingClientRect().width),
                  Math.round(onI.getBoundingClientRect().height)] : null,
    row_w: rows ? Math.round(rows.getBoundingClientRect().width) : 0,
    row_h: rows ? Math.round(rows.getBoundingClientRect().height) : 0,
    row_wrap: rows ? getComputedStyle(rows).flexWrap : '',
  };
}"""


def main():
    rows = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge")
        for t in THEMES:
            ctx = b.new_context(viewport={"width": 1400, "height": 880})
            ctx.add_init_script(
                "try{localStorage.setItem('snc.eula.v1','1');"
                "localStorage.setItem('snc.theme.v2','%s')}catch(e){}" % t)
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(URL)
            pg.wait_for_selector(".snc-node")
            pg.wait_for_timeout(800)

            # 参数行特写：先点到 16:9，让选中态有东西可看
            pg.click('#sncGRatioPick button[data-r="16:9"]')
            pg.wait_for_timeout(250)
            pg.locator(".snc-prompt").screenshot(path=os.path.join(OUT, "ux-params-%s.png" % t))
            rows[t] = pg.evaluate(READ_JS)

            # 空态全景
            pg.evaluate("() => { const N = window.SNC_TEST_API.nodes(); N.length = 0; window.SNC_TEST_API.render(); }")
            pg.wait_for_timeout(400)
            pg.screenshot(path=os.path.join(OUT, "ux-empty-%s.png" % t))

            if errs:
                print("JS 错误 @%s: %s" % (t, errs))
            ctx.close()

        # 窄窗：1200 宽，看参数行会不会换行/溢出
        ctx = b.new_context(viewport={"width": 1200, "height": 820})
        ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1');"
                            "localStorage.setItem('snc.theme.v2','dark')}catch(e){}")
        pg = ctx.new_page()
        pg.goto(URL)
        pg.wait_for_selector(".snc-node")
        pg.wait_for_timeout(700)
        pg.click('#sncGRatioPick button[data-r="9:16"]')
        pg.wait_for_timeout(250)
        pg.locator(".snc-prompt").screenshot(path=os.path.join(OUT, "ux-params-narrow.png"))
        narrow = pg.evaluate("""() => {
          const rows = document.querySelector('.snc-p-params');
          const prompt = document.querySelector('.snc-prompt');
          const pr = prompt.getBoundingClientRect();
          const kids = [...rows.children].map(k => {
            const r = k.getBoundingClientRect();
            return {cls: k.className || k.tagName, l: Math.round(r.left), t: Math.round(r.top),
                    w: Math.round(r.width), h: Math.round(r.height)};
          });
          return {
            prompt_w: Math.round(pr.width),
            rows_w: Math.round(rows.getBoundingClientRect().width),
            rows_h: Math.round(rows.getBoundingClientRect().height),
            scroll_w: rows.scrollWidth, client_w: rows.clientWidth,
            tops: [...new Set(kids.map(k => k.t))],
            kids: kids
          };
        }""")
        ctx.close()
        b.close()

    keys = ["theme", "--accent", "--raise", "n", "checked", "on_bg", "on_fg", "shape", "row_w", "row_h", "row_wrap"]
    w = max(len(k) for k in keys) + 1
    print("".join(k.ljust(w) for k in [""] + THEMES))
    for k in keys:
        line = ""
        for t in THEMES:
            v = rows.get(t, {}).get(k, "")
            line += str(v).ljust(w)
        print(k.ljust(w) + line)

    print()
    print("窄窗（1200px）参数行：容器宽 %s / 内容宽 %s / 高 %s"
          % (narrow["rows_w"], narrow["scroll_w"], narrow["rows_h"]))
    print("  是否溢出（scrollWidth > clientWidth）:", narrow["scroll_w"] > narrow["client_w"] + 1)
    print("  各行 y 坐标（>1 个值说明换了行）:", narrow["tops"])


if __name__ == "__main__":
    main()
