# -*- coding: utf-8 -*-
"""v3.7.4 第八批视觉探针：底栏去掉 1/2/3、编辑面板去掉多余的加图按钮。

  b8-bar-<theme>.png      底部输入条（整条）
  b8-compose-<theme>.png  编辑面板（看「生成」前面那颗图标是不是没了、右侧有没有留空）

用法：python tests/shot_batch8.py [SNC_BASE]
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SNC_BASE", "http://127.0.0.1:8321"))
URL = BASE + "/canvas.html"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "截图")
THEMES = ["warm", "dark", "light"]

SEED_JS = """() => {
  const c = document.createElement('canvas'); c.width = 640; c.height = 400;
  const g = c.getContext('2d');
  const sky = g.createLinearGradient(0, 0, 0, 260);
  sky.addColorStop(0, '#1b2a4a'); sky.addColorStop(1, '#3d5a7a');
  g.fillStyle = sky; g.fillRect(0, 0, 640, 260);
  g.fillStyle = '#20242a'; g.fillRect(0, 260, 640, 140);
  g.fillStyle = '#8a6a3a'; g.fillRect(60, 250, 120, 90); g.fillRect(500, 244, 90, 96);
  const u = c.toDataURL('image/png');
  const N = window.SNC_TEST_API.nodes();
  N.length = 0;
  N.push({ id: 'b8-a', type: 'gen', status: 'done', x: 120, y: 120, w: 340, h: 214,
           dataUrl: u, label: '图片 5', prompt: '水面反射与岸线收边自然；人物、座椅与灯具只作尺度参照',
           realSize: '2048x1280', ratio: '16:9', res: 2048, createdAt: 1, vIndex: 0,
           versions: [{ dataUrl: u, size: '2048x1280', model: 'Seedream 5.0 Pro', latencyMs: 9000,
                        usage: {}, kind: 'gen', prompt: 'x', ratio: '16:9', at: Date.now() }] });
  window.SNC_TEST_API.render();
  return true;
}"""

GEO_JS = """() => {
  const r = (sel) => {
    const e = document.querySelector(sel);
    if(!e) return null;
    const b = e.getBoundingClientRect();
    return { w: Math.round(b.width), h: Math.round(b.height) };
  };
  const row = document.querySelector('.snc-p-row');
  const send = document.getElementById('sncSend');
  const sr = send ? send.getBoundingClientRect() : null;
  const rr = row ? row.getBoundingClientRect() : null;
  const cmp = document.querySelector('.snc-compose-foot');
  return {
    bar: r('.snc-prompt'),
    row: r('.snc-p-row'),
    sendRightGap: rr && sr ? Math.round(rr.right - sr.right) : -1,
    rowOver: row ? row.scrollWidth - row.clientWidth : -1,
    hasCount: !!document.querySelector('.snc-count'),
    foot: r('.snc-compose-foot'),
    footOver: cmp ? cmp.scrollWidth - cmp.clientWidth : -1,
    hasAttBtn: !!document.getElementById('sncAttBtn'),
    slots: document.querySelectorAll('.snc-att-slot').length
  };
}"""


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge")
        for theme in THEMES:
            errs = []
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_init_script(
                "try{localStorage.setItem('snc.eula.v1','1');"
                "localStorage.setItem('snc.theme.v2','%s')}catch(e){}" % theme
            )
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(URL)
            pg.wait_for_selector(".snc-node")
            pg.wait_for_timeout(700)
            pg.evaluate(SEED_JS)
            pg.wait_for_timeout(400)

            pg.locator(".snc-prompt").screenshot(path=os.path.join(OUT, "b8-bar-%s.png" % theme))
            d1 = pg.evaluate(GEO_JS)

            # 选中这张图 → 工具条「编辑」→ 面板
            pg.evaluate("""() => {
              const n = document.querySelector('[data-id="b8-a"]');
              const img = n && n.querySelector('img');
              if(!img) return;
              const r = img.getBoundingClientRect();
              img.dispatchEvent(new PointerEvent('pointerdown',
                {bubbles:true, clientX:r.left+30, clientY:r.top+30, pointerId:1}));
            }""")
            pg.wait_for_timeout(250)
            pg.evaluate("""() => {
              const btn = document.querySelector('#sncImgBar button[data-act="edit"]');
              if(btn) btn.click();
            }""")
            pg.wait_for_timeout(400)
            panel = pg.locator(".snc-compose")
            if panel.count():
                panel.screenshot(path=os.path.join(OUT, "b8-compose-%s.png" % theme))
            d2 = pg.evaluate(GEO_JS)

            print("%-6s bar=%sx%s rowOver=%s sendGap=%s  count=%s | foot=%sx%s footOver=%s attBtn=%s slots=%s"
                  % (theme, d1["bar"]["w"], d1["bar"]["h"], d1["rowOver"], d1["sendRightGap"],
                     d1["hasCount"], (d2["foot"] or {}).get("w"), (d2["foot"] or {}).get("h"),
                     d2["footOver"], d2["hasAttBtn"], d2["slots"]))
            if errs:
                print("  JS 错误:", errs)
            ctx.close()
        b.close()


if __name__ == "__main__":
    main()
