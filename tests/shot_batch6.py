# -*- coding: utf-8 -*-
"""v3.7.4 第六批视觉探针：画布规模角标 + 内容搜索结果，三套主题各出一张。

  b6-scale-<theme>.png   顶栏规模角标（警告态）与展开的建议面板
  b6-search-<theme>.png  侧栏「画布名命中 + 卡片内容命中」两段结果

用法：python tests/shot_batch6.py [SNC_BASE]
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SNC_BASE", "http://127.0.0.1:8321"))
URL = BASE + "/canvas.html"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "截图")
THEMES = ["warm", "dark", "light"]

SCALE_JS = """() => {
  const snc = document.getElementById('snc');
  const cs = getComputedStyle(snc);
  const chip = document.getElementById('sncScale');
  const pop = document.getElementById('sncScalePop');
  const cc = chip ? getComputedStyle(chip) : null;
  const prime = pop ? pop.querySelector('.snc-sp-btn.primary') : null;
  const p = pop ? getComputedStyle(pop) : null;
  return {
    theme: snc.getAttribute('data-theme') || '(none)',
    accent: cs.getPropertyValue('--accent').trim(),
    warn_fg: cs.getPropertyValue('--warn-fg').trim(),
    chip: chip ? chip.textContent : '',
    chip_fg: cc ? cc.color : '', chip_bd: cc ? cc.borderTopColor : '',
    chip_bg: cc ? cc.backgroundColor : '',
    pop_w: pop ? Math.round(pop.getBoundingClientRect().width) : 0,
    pop_bg: p ? p.backgroundColor : '',
    prime_fg: prime ? getComputedStyle(prime).color : '',
    prime_bg: prime ? getComputedStyle(prime).backgroundColor : ''
  };
}"""

SEARCH_JS = """() => {
  const list = document.getElementById('sncDocList');
  const secs = [...list.querySelectorAll('.snc-doc-sec')].map(e => e.textContent);
  const hits = [...list.querySelectorAll('.snc-doc-hit')];
  const mk = list.querySelector('mark');
  const first = hits[0];
  const t = first ? first.querySelector('.snc-hit-t') : null;
  return {
    secs: secs,
    items: list.querySelectorAll('.snc-doc-item').length,
    hits: hits.length,
    hit_h: first ? Math.round(first.getBoundingClientRect().height) : 0,
    line_h: t ? getComputedStyle(t).lineHeight : '',
    t_px: t ? getComputedStyle(t).fontSize : '',
    mark_bg: mk ? getComputedStyle(mk).backgroundColor : '',
    mark_fg: mk ? getComputedStyle(mk).color : '',
    overflow: list.scrollWidth > list.clientWidth + 1
  };
}"""


def main():
    os.makedirs(OUT, exist_ok=True)
    data = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge")
        for t in THEMES:
            errs = []
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_init_script(
                "try{if(!sessionStorage.getItem('snc.probe6s.init')){"
                "localStorage.removeItem('snc.scalehint.v1');"
                "sessionStorage.setItem('snc.probe6s.init','1');}"
                "localStorage.setItem('snc.eula.v1','1');"
                "localStorage.setItem('snc.theme.v2','%s')}catch(e){}" % t
            )
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(URL)
            pg.wait_for_selector(".snc-node")
            pg.wait_for_timeout(700)

            # ---- 规模角标：80 张卡 → 警告态；选 3 张让面板里的按钮可用
            pg.evaluate("""() => {
              const api = window.SNC_TEST_API;
              const N = api.nodes(); N.length = 0;
              for(let i = 0; i < 80; i++){
                N.push({ id: 'p6-' + i, type: 'note', title: '卡片 ' + (i + 1),
                         text: '占位内容', x: (i % 10) * 210, y: Math.floor(i / 10) * 150,
                         w: 180, h: 110 });
              }
              api.render();
            }""")
            pg.wait_for_timeout(250)
            ids = pg.evaluate("() => window.SNC_TEST_API.nodes().slice(0, 3).map(n => n.id)")
            pg.click('.snc-node[data-id="%s"] .snc-node-body' % ids[0])
            for nid in ids[1:]:
                pg.click('.snc-node[data-id="%s"] .snc-node-body' % nid, modifiers=["Shift"])
            pg.wait_for_timeout(150)
            pg.click("#sncScale")
            pg.wait_for_timeout(320)
            data.setdefault("scale", {})[t] = pg.evaluate(SCALE_JS)
            box = pg.evaluate("""() => {
              const c = document.getElementById('sncScale').getBoundingClientRect();
              const p = document.getElementById('sncScalePop').getBoundingClientRect();
              return {x: Math.round(Math.min(c.x, p.x) - 26), y: 0,
                      width: Math.round(c.right + 26 - Math.min(c.x, p.x) + 26),
                      height: Math.round(p.bottom + 26)};
            }""")
            pg.screenshot(path=os.path.join(OUT, "b6-scale-%s.png" % t), clip=box)
            pg.mouse.click(700, 500)          # 点空白收起面板

            # ---- 内容搜索：当前画布放含「球场灯」的提示词，另一张画布放笔记
            pg.evaluate("""() => {
              const api = window.SNC_TEST_API;
              const N = api.nodes(); N.length = 0;
              N.push({ id: 'p6a-1', type: 'gen', status: 'done', label: '生成',
                       x: 80, y: 80, w: 260, h: 190, vIndex: 0,
                       prompt: '夜间鸟瞰的社区体育公园，暖色球场灯把跑道照出层次' });
              N.push({ id: 'p6a-2', type: 'note', title: '待办',
                       text: '补两张清晨的人流参考', x: 380, y: 80, w: 200, h: 130 });
              api.render();
            }""")
            pg.wait_for_timeout(200)
            beach = pg.evaluate("() => document.getElementById('sncTitle').textContent")
            pg.click("#sncDocNew")
            pg.wait_for_timeout(600)
            second = pg.evaluate("() => document.getElementById('sncTitle').textContent")
            pg.evaluate("""() => {
              const api = window.SNC_TEST_API;
              const N = api.nodes(); N.length = 0;
              N.push({ id: 'p6b-1', type: 'note', title: '材质备忘',
                       text: '儿童活动场橡胶地垫 50mm，EPDM 颗粒；球场灯 3000K、显色 80 以上',
                       x: 100, y: 100, w: 220, h: 140 });
              N.push({ id: 'p6b-2', type: 'note', title: '照明',
                       text: '草坪灯沿步道布置，间距 8 米', x: 360, y: 100, w: 200, h: 130 });
              api.render();
            }""")
            pg.wait_for_timeout(220)
            pg.fill("#sncDocSearch", "球场灯")
            pg.wait_for_timeout(320)
            data.setdefault("search", {})[t] = pg.evaluate(SEARCH_JS)
            lbox = pg.evaluate("""() => {
              const l = document.getElementById('sncDocList').getBoundingClientRect();
              return {x: 0, y: Math.round(Math.max(0, l.y - 74)),
                      width: Math.round(l.right + 6),
                      height: Math.round(Math.min(620, l.height + 84))};
            }""")
            pg.screenshot(path=os.path.join(OUT, "b6-search-%s.png" % t), clip=lbox)

            # ---- 清理：删掉这一轮造的画布
            pg.fill("#sncDocSearch", "")
            pg.wait_for_timeout(250)
            for name in [second]:
                if not name:
                    continue
                loc = pg.locator("#sncDocList .snc-doc-item", has_text=name)
                if loc.count():
                    loc.first.hover()
                    loc.first.locator(".snc-doc-act.del").click()
                    pg.wait_for_timeout(180)
                    pg.click("#sncConfirmYes")
                    pg.wait_for_timeout(300)
            if errs:
                print("JS 错误 @%s: %s" % (t, errs))
            ctx.close()
        b.close()

    print("=== 规模角标 ===")
    for t in THEMES:
        d = data["scale"][t]
        print("%-6s chip=%-16s fg=%s bg=%s bd=%s | pop w=%s bg=%s | btn fg=%s bg=%s"
              % (t, d["chip"], d["chip_fg"], d["chip_bg"], d["chip_bd"],
                 d["pop_w"], d["pop_bg"], d["prime_fg"], d["prime_bg"]))
    print()
    print("=== 搜索两段 ===")
    for t in THEMES:
        d = data["search"][t]
        print("%-6s secs=%s items=%s hits=%s hit_h=%s t=%s lh=%s mark=%s/%s overflow=%s"
              % (t, d["secs"], d["items"], d["hits"], d["hit_h"], d["t_px"],
                 d["line_h"], d["mark_fg"], d["mark_bg"], d["overflow"]))


if __name__ == "__main__":
    main()
