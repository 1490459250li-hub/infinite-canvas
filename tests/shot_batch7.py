# -*- coding: utf-8 -*-
"""v3.7.4 第七批视觉探针：跨节点对比浮层，三套主题 + 一档窄窗。

  b7-cpov-<theme>.png   1440×900 下的对比浮层
  b7-cpov-narrow.png    1180×760 下同一层，看头部/底部会不会挤坏

用法：python tests/shot_batch7.py [SNC_BASE]
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SNC_BASE", "http://127.0.0.1:8321"))
URL = BASE + "/canvas.html"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "截图")
THEMES = ["warm", "dark", "light"]

# 两张"假效果图"：渐变天空 + 地平线 + 几块体量，够看对比版式，不必真调模型
SEED_JS = """() => {
  const api = window.SNC_TEST_API;
  const N = api.nodes(); N.length = 0;
  function poster(sky1, sky2, ground, warm){
    const c = document.createElement('canvas'); c.width = 640; c.height = 400;
    const g = c.getContext('2d');
    const sky = g.createLinearGradient(0, 0, 0, 260);
    sky.addColorStop(0, sky1); sky.addColorStop(1, sky2);
    g.fillStyle = sky; g.fillRect(0, 0, 640, 260);
    g.fillStyle = ground; g.fillRect(0, 260, 640, 140);
    g.fillStyle = warm;
    g.fillRect(60, 250, 120, 90); g.fillRect(210, 268, 70, 72); g.fillRect(500, 244, 90, 96);
    g.fillStyle = 'rgba(255,236,200,.9)';
    for(let i = 0; i < 5; i++) g.fillRect(70 + i * 24, 300, 8, 22);
    g.strokeStyle = 'rgba(255,255,255,.18)'; g.lineWidth = 2;
    for(let i = 0; i < 6; i++){ g.beginPath(); g.moveTo(0, 60 + i * 34);
      g.lineTo(640, 40 + i * 34); g.stroke(); }
    return c.toDataURL('image/png');
  }
  function mk(id, u, o){
    return Object.assign({
      id: id, type: 'gen', status: 'done', x: 0, y: 0, w: 300, h: 190,
      dataUrl: u, label: id, prompt: '社区体育公园 · 夜间鸟瞰，暖色球场灯',
      realSize: '2048x1280', ratio: '16:9', res: 2048, createdAt: 1, vIndex: 0,
      versions: [{ dataUrl: u, size: '2048x1280', model: o.model, latencyMs: 14200,
                   usage: {}, kind: 'gen', prompt: '社区体育公园 · 夜间鸟瞰，暖色球场灯',
                   ratio: '16:9', at: Date.now() }]
    }, o.extra || {});
  }
  const u1 = poster('#1b2a4a', '#3d5a7a', '#20242a', '#8a6a3a');
  const u2 = poster('#141b2b', '#2a3a52', '#14171b', '#c8a26a');
  N.push(mk('p7-a', u1, { model: 'SenseNova-Vision · fast',
                          extra: { x: 80, y: 90, label: '体育公园 · fast' } }));
  N.push(mk('p7-b', u2, { model: 'SenseNova-Vision · pro',
                          extra: { x: 2600, y: 1500, label: '体育公园 · pro' } }));
  api.render();
  api.cpovOpen('p7-a', 'p7-b');
  api.cpovMove(46);
  return true;
}"""

GEO_JS = """() => {
  const r = (id) => {
    const e = document.getElementById(id);
    if(!e) return null;
    const b = e.getBoundingClientRect();
    return { w: Math.round(b.width), h: Math.round(b.height),
             x: Math.round(b.x), y: Math.round(b.y) };
  };
  const sub = document.getElementById('sncCpoSub');
  const foot = document.querySelector('.snc-cpo-foot');
  const strip = document.getElementById('sncCpoStrip');
  const tagA = document.getElementById('sncCpoTagA');
  const tagB = document.getElementById('sncCpoTagB');
  return {
    win: [innerWidth, innerHeight],
    head: r('sncCpov') && document.querySelector('.snc-cpo-hd').getBoundingClientRect().height,
    stage: r('sncCpoStage'),
    strip: r('sncCpoStrip'),
    subCut: sub ? sub.scrollWidth > sub.clientWidth + 1 : null,
    subText: sub ? sub.textContent : '',
    footOver: foot ? foot.scrollWidth > foot.clientWidth + 1 : null,
    footH: foot ? Math.round(foot.getBoundingClientRect().height) : 0,
    stripScroll: strip ? strip.scrollWidth - strip.clientWidth : null,
    tagA: tagA ? tagA.textContent : '',
    tagB: tagB ? tagB.textContent : '',
    tagAW: tagA ? Math.round(tagA.getBoundingClientRect().width) : 0,
    tagBW: tagB ? Math.round(tagB.getBoundingClientRect().width) : 0,
    thumbs: document.querySelectorAll('#sncCpoStrip .snc-cpo-th').length,
    docScroll: [document.documentElement.scrollWidth, document.documentElement.clientWidth]
  };
}"""


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge")
        shots = [(t, 1440, 900) for t in THEMES] + [("narrow", 1180, 760)]
        for tag, w, h in shots:
            theme = "warm" if tag == "narrow" else tag
            errs = []
            ctx = b.new_context(viewport={"width": w, "height": h})
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
            pg.wait_for_timeout(420)
            rows.append((tag, pg.evaluate(GEO_JS)))
            name = "b7-cpov-%s.png" % tag
            pg.screenshot(path=os.path.join(OUT, name))
            if errs:
                print("JS 错误 @%s: %s" % (tag, errs))
            ctx.close()
        b.close()

    print("%-8s %-10s %-16s %-7s %-6s %-6s %-7s %-7s" %
          ("shot", "stage", "sub", "foot", "strip", "cut", "tagW", "docScroll"))
    for tag, d in rows:
        print("%-8s %-10s %-16s %-7s %-6s %-6s %-7s %-7s" % (
            tag,
            "%sx%s" % (d["stage"]["w"], d["stage"]["h"]),
            d["subText"][:15],
            d["footH"],
            d["stripScroll"],
            d["subCut"],
            "%s/%s" % (d["tagAW"], d["tagBW"]),
            "%s/%s" % tuple(d["docScroll"])))
        print("         tagA=%-22s tagB=%-22s thumbs=%s footOver=%s"
              % (d["tagA"], d["tagB"], d["thumbs"], d["footOver"]))


if __name__ == "__main__":
    main()
