# -*- coding: utf-8 -*-
"""v3.7.4 第四批视觉探针：快捷键表 / 队列面板 / 缩放条，三套主题各出一张。

  b5-keys-<theme>.png    快捷键表
  b5-queue-<theme>.png   队列面板（角标 + 展开后的列表）
  b5-zoomer-<theme>.png  缩放条（多了 ? 入口）

用法：python tests/shot_batch5.py [SNC_BASE]
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SNC_BASE", "http://127.0.0.1:8321"))
URL = BASE + "/canvas.html"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "截图")
THEMES = ["warm", "dark", "light"]

KEYS_JS = """() => {
  const snc = document.getElementById('snc');
  const cs = getComputedStyle(snc);
  const box = document.querySelector('#sncKeys .snc-keys');
  const r = box.getBoundingClientRect();
  const hd = box.querySelector('h2');
  const dd = box.querySelector('.snc-keys-g dd');
  const kb = box.querySelector('kbd');
  return {
    theme: snc.getAttribute('data-theme') || '(none)',
    card: cs.getPropertyValue('--card').trim(),
    box: [Math.round(r.width), Math.round(r.height)],
    scroll: [box.scrollWidth, box.scrollHeight],
    title_px: hd ? getComputedStyle(hd).fontSize : '',
    dd_px: dd ? getComputedStyle(dd).fontSize : '',
    kbd_fg: kb ? getComputedStyle(kb).color : '',
    kbd_bd: kb ? getComputedStyle(kb).borderTopColor : '',
  };
}"""

QUEUE_JS = """() => {
  const pop = document.getElementById('sncQueuePop');
  const row = pop ? pop.querySelector('.snc-qrow') : null;
  const name = row ? row.querySelector('.snc-qmeta b') : null;
  const sub = row ? row.querySelector('.snc-qmeta span') : null;
  const x = row ? row.querySelector('.snc-qx') : null;
  const th = row ? row.querySelector('.snc-qthumb') : null;
  return {
    rows: pop ? pop.querySelectorAll('.snc-qrow').length : 0,
    w: pop ? Math.round(pop.getBoundingClientRect().width) : 0,
    h: pop ? Math.round(pop.getBoundingClientRect().height) : 0,
    name_w: name ? Math.round(name.getBoundingClientRect().width) : 0,
    name_trunc: name ? name.scrollWidth > name.clientWidth + 1 : null,
    sub_px: sub ? getComputedStyle(sub).fontSize : '',
    x_fg: x ? getComputedStyle(x).color : '',
    thumb: th ? [Math.round(th.getBoundingClientRect().width),
                 Math.round(th.getBoundingClientRect().height)] : null,
  };
}"""


def main():
    data = {}
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

            # 快捷键表
            pg.click("#sncKeysBtn")
            pg.wait_for_timeout(320)
            pg.screenshot(path=os.path.join(OUT, "b5-keys-%s.png" % t))
            data.setdefault("keys", {})[t] = pg.evaluate(KEYS_JS)
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(200)

            # 队列：1 个在跑 + 3 个排队
            pg.evaluate("() => window.SNC_TEST_API.queueProbe(4, 1)")
            pg.wait_for_timeout(250)
            pg.click("#sncQueue")
            pg.wait_for_timeout(320)
            data.setdefault("queue", {})[t] = pg.evaluate(QUEUE_JS)
            pg.screenshot(path=os.path.join(OUT, "b5-queue-%s.png" % t))

            # 缩放条特写（含 ? 入口）
            pg.keyboard.press("Escape")
            pg.evaluate("() => window.SNC_TEST_API.queueClear()")
            pg.wait_for_timeout(300)
            pg.locator(".snc-zoomer").screenshot(path=os.path.join(OUT, "b5-zoomer-%s.png" % t))

            if errs:
                print("JS 错误 @%s: %s" % (t, errs))
            ctx.close()
        b.close()

    print("=== 快捷键表 ===")
    for t in THEMES:
        d = data["keys"][t]
        print("%-6s card=%-9s box=%sx%s scroll=%sx%s title=%s dd=%s kbd_fg=%s bd=%s"
              % (t, d["card"], d["box"][0], d["box"][1], d["scroll"][0], d["scroll"][1],
                 d["title_px"], d["dd_px"], d["kbd_fg"], d["kbd_bd"]))

    print()
    print("=== 队列面板 ===")
    for t in THEMES:
        d = data["queue"][t]
        print("%-6s rows=%s size=%sx%s name_w=%s trunc=%s sub=%s x_fg=%s thumb=%s"
              % (t, d["rows"], d["w"], d["h"], d["name_w"], d["name_trunc"],
                 d["sub_px"], d["x_fg"], d["thumb"]))


if __name__ == "__main__":
    main()
