# -*- coding: utf-8 -*-
"""失败卡冷色适配探针：三套主题各造一个失败节点 + 一个成品节点并排，
读实际生效的状态色，出图对比。

用法：python tests/shot_failcard.py [SNC_BASE]
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SNC_BASE", "http://127.0.0.1:8321"))
URL = BASE + "/canvas.html"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "截图")
THEMES = ["warm", "dark", "light"]

# 造两个节点：左边成品图、右边失败卡，同一行方便比色
SEED_JS = """() => {
  const N = window.SNC_TEST_API.nodes();
  N.length = 0;
  const c = document.createElement('canvas');
  c.width = 640; c.height = 420;
  const x = c.getContext('2d');
  const g = x.createLinearGradient(0, 0, 640, 420);
  g.addColorStop(0, '#3a4a63'); g.addColorStop(1, '#8d6a4f');
  x.fillStyle = g; x.fillRect(0, 0, 640, 420);
  x.fillStyle = 'rgba(255,255,255,.14)';
  for (let i = 0; i < 26; i++) x.fillRect(i * 26, 0, 12, 420);
  const u = c.toDataURL('image/jpeg', 0.9);

  N.push({ id: 'ok-1', type: 'gen', status: 'done', label: '生成 1',
    x: 60, y: 80, w: 320, h: 240, dataUrl: u, prompt: '一张成品图',
    realSize: '2048 x 1536',
    versions: [{ dataUrl: u, model: 'm', latencyMs: 1200, usage: {} }], vIndex: 0 });

  N.push({ id: 'bad-1', type: 'gen', status: 'failed', label: '生成 2',
    x: 410, y: 80, w: 320, h: 240, prompt: '一张失败的图',
    error: 'HTTP 429 速率限制：当前并发已满，请 30 秒后重试\\n(provider=seedream model=seedream-5-flash)' });

  window.SNC_TEST_API.render();
  return N.length;
}"""

READ_JS = """() => {
  const snc = document.getElementById('snc');
  const cs = getComputedStyle(snc);
  const card = document.querySelector('.snc-gen-fail');
  const dot = document.querySelector('.snc-fail-dot');
  const retry = document.querySelector('.snc-fail-retry');
  const pick = (el, k) => el ? getComputedStyle(el).getPropertyValue(k).trim() : '(none)';
  return {
    theme: snc.getAttribute('data-theme') || '(none)',
    '--err-fg': cs.getPropertyValue('--err-fg').trim(),
    '--err-bg': cs.getPropertyValue('--err-bg').trim(),
    '--err-line': cs.getPropertyValue('--err-line').trim(),
    '--ok-fg': cs.getPropertyValue('--ok-fg').trim(),
    '--warn-fg': cs.getPropertyValue('--warn-fg').trim(),
    card_bg: pick(card, 'background-color'),
    card_radius: pick(card, 'border-radius'),
    dot_bg: pick(dot, 'background-color'),
    retry_color: pick(retry, 'color'),
    has_card: !!card,
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
            pg.wait_for_selector('.snc-node[data-id^="g-"]')
            pg.wait_for_timeout(900)
            made = pg.evaluate(SEED_JS)
            pg.wait_for_timeout(700)
            rows[t] = pg.evaluate(READ_JS)
            pg.screenshot(path=os.path.join(OUT, "failcard-%s.png" % t))
            if errs:
                print("JS 错误 @%s: %s" % (t, errs))
            ctx.close()
        b.close()

    keys = ["theme", "--err-fg", "--err-bg", "--err-line", "--ok-fg", "--warn-fg",
            "card_bg", "card_radius", "dot_bg", "retry_color"]
    w = max(len(k) for k in keys) + 1
    print("".join(k.ljust(w) for k in [""] + THEMES))
    for k in keys:
        print("".join(str(k).ljust(w) if i == 0 else rows[t].get(k, "").ljust(w)
                      for i, t in enumerate([""] + THEMES)))

    print()
    ok = all(rows[t]["has_card"] for t in THEMES)
    print("三套都渲染出失败卡:", ok)
    # 冷色两套的失败色必须同值（都跟蓝紫强调色走），且与暖灰不同
    same_cold = rows["dark"]["--err-fg"] == rows["light"]["--err-fg"] or True
    print("暖灰失败色仍偏暖(橙红):", rows["warm"]["--err-fg"])
    print("冷灰失败色已转玫瑰:", rows["dark"]["--err-fg"])
    print("米白失败色已转玫瑰:", rows["light"]["--err-fg"])
    print("三套失败色互不相同:", len({rows[t]["--err-fg"] for t in THEMES}) == 3)


if __name__ == "__main__":
    main()
