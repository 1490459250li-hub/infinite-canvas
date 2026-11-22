# -*- coding: utf-8 -*-
"""预览图外链探针：确认 21 张技能图都能从 /art/ 正常加载（不是坏图占位）。

用法：python tests/probe_art.py [SNC_BASE]
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SNC_BASE", "http://127.0.0.1:8321"))
URL = BASE + "/canvas.html"


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge")
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1');"
                            "localStorage.setItem('snc.theme.v2','dark')}catch(e){}")
        pg = ctx.new_page()
        errs, resp = [], []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("response", lambda r: resp.append((r.url, r.status))
              if "/art/" in r.url else None)
        pg.goto(URL)
        pg.wait_for_selector('.snc-node[data-id^="g-"]')
        pg.wait_for_timeout(900)

        # 预览图瓦片在技能工作台里，要选中一张成品图再点「技能」才出得来
        pg.evaluate("""() => {
          const N = window.SNC_TEST_API.nodes();
          const c = document.createElement('canvas');
          c.width = 640; c.height = 420;
          const x = c.getContext('2d');
          x.fillStyle = '#4a5a70'; x.fillRect(0, 0, 640, 420);
          x.fillStyle = 'rgba(255,255,255,.2)'; x.fillRect(120, 90, 400, 240);
          const u = c.toDataURL('image/jpeg', 0.9);
          N.push({ id: 'probe-ok', type: 'gen', status: 'done', label: '生成',
            x: 200, y: 160, w: 300, h: 200, dataUrl: u, prompt: 'p', vIndex: 0,
            versions: [{ dataUrl: u, model: 'm', latencyMs: 1, usage: {} }] });
          window.SNC_TEST_API.render();
        }""")
        pg.wait_for_timeout(600)
        pg.click('.snc-node[data-id="probe-ok"] .snc-node-body')
        pg.wait_for_timeout(500)
        pg.click('#sncImgBar button[data-act="skill"]')
        pg.wait_for_timeout(1600)

        info = pg.evaluate("""() => {
          const tiles = [...document.querySelectorAll('.snc-skp-tile')];
          const imgs = [...document.querySelectorAll('.snc-skp-tile img')];
          return {
            tiles: tiles.length,
            imgs: imgs.length,
            broken: imgs.filter(i => !i.complete || i.naturalWidth === 0)
                        .map(i => i.getAttribute('src')),
            sample: imgs.slice(0, 3).map(i => ({src: i.getAttribute('src'),
                                                w: i.naturalWidth, h: i.naturalHeight})),
          };
        }""")

        pg.screenshot(path=os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "截图", "art-skills.png"))

        print("技能卡 %d 张，其中带图 %d 张" % (info["tiles"], info["imgs"]))
        print("坏图:", info["broken"] or "无")
        for s in info["sample"]:
            print("  %s  %dx%d" % (s["src"], s["w"], s["h"]))
        art = [r for r in resp if "/art/" in r[0]]
        bad = [r for r in art if r[1] != 200]
        print("/art/ 请求 %d 条，非 200：%s" % (len(art), bad or "无"))
        if errs:
            print("JS 错误:", errs)
        ctx.close()
        b.close()


if __name__ == "__main__":
    main()
