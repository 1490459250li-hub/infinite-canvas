# -*- coding: utf-8 -*-
"""v1.8 真实链路：点工具条「技能」→ 选「夜景转换」→ 编辑框带着指令 → 出图。
这一次调用会消耗 1 次出图额度，专门用来证明"内置技能是真能出图的"。
跑完顺手对派生卡打开对比预览，把派生前后两张真图并排存一张截图。"""
import os
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8321/canvas.html"
SHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "截图")
os.makedirs(SHOT_DIR, exist_ok=True)


def cards(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll('.snc-node')).map(d => {
        const r = d.getBoundingClientRect();
        const img = d.querySelector('.snc-gen img');
        return {id: d.dataset.id,
                label: (d.querySelector('.snc-node-label')||{}).textContent || '',
                x: r.x, y: r.y, w: r.width, h: r.height,
                badge: (d.querySelector('.snc-sizebadge')||{}).textContent || '',
                len: img ? (img.getAttribute('src')||'').length : 0,
                busy: !!d.querySelector('.snc-gen-wait'),
                failed: !!d.querySelector('.snc-gen-fail')};
    })""")


with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    page = br.new_context(viewport={"width": 1440, "height": 900}).new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(1600)

    before = cards(page)
    target = [c for c in before if c["label"].strip() == "图片 2"][0]
    page.mouse.click(target["x"] + target["w"] / 2, target["y"] + target["h"] / 2)
    page.wait_for_timeout(320)

    page.click('#sncImgBar button[data-act="skill"]')
    page.wait_for_timeout(400)
    tiles = page.evaluate("""() => Array.from(document.querySelectorAll('#sncSkpBody .snc-skp-tile'))
        .map(t => (t.querySelector('em')||{}).textContent)""")
    print("技能面板首屏：", tiles)
    box = page.evaluate("""() => {
        const t = Array.from(document.querySelectorAll('#sncSkpBody .snc-skp-tile'))
            .find(x => ((x.querySelector('em')||{}).textContent || '') === '夜景转换');
        if(!t) return null;
        const r = t.getBoundingClientRect();
        return {x: r.x + r.width / 2, y: r.y + r.height / 2};
    }""")
    assert box, "没有找到「夜景转换」技能块"
    page.mouse.click(box["x"], box["y"])
    page.wait_for_timeout(600)

    state = page.evaluate("""() => {
        const sub = document.getElementById('sncComposeSub').textContent;
        const t = document.getElementById('sncComposeInput').value;
        return {sub: sub, len: t.length, head: t.slice(0, 24)};
    }""")
    print("编辑框：", state)

    page.click("#sncComposeSend")
    child = None
    for _ in range(75):
        page.wait_for_timeout(2000)
        now = cards(page)
        made = [c for c in now if "夜景转换" in c["label"]]
        if made and not made[0]["busy"]:
            child = made[0]
            break
    after = cards(page)
    orig = [c for c in after if c["id"] == target["id"]][0]
    print("技能派生卡：", child and child["label"], "| 尺寸", child and child["badge"],
          "| 失败", child and child["failed"])
    print("原图字节：", target["len"], "->", orig["len"])
    page.screenshot(path=os.path.join(SHOT_DIR, "v18-真实技能-夜景转换.png"))

    if child:
        page.mouse.click(child["x"] + child["w"] / 2, child["y"] + child["h"] / 2)
        page.wait_for_timeout(320)
        page.click('#sncImgBar button[data-act="compare"]')
        page.wait_for_timeout(500)
        cmp0 = page.evaluate("""() => {
            const b = document.querySelector('.snc-cmp-b');
            if(!b) return null;
            const grip = b.querySelector('.snc-cmp-grip');
            const r = b.getBoundingClientRect();
            const gr = grip.getBoundingClientRect();
            return {x: r.x, y: r.y, w: r.width, h: r.height,
                    gx: gr.x + gr.width / 2, gy: gr.y + gr.height / 2,
                    tags: Array.from(b.querySelectorAll('.snc-cmp-tag')).map(t => t.textContent)};
        }""")
        print("对比层：", cmp0 and cmp0["tags"])
        if cmp0:
            page.mouse.move(cmp0["gx"], cmp0["gy"])
            page.mouse.down()
            page.mouse.move(cmp0["x"] + cmp0["w"] * 0.5, cmp0["gy"], steps=10)
            page.mouse.up()
            page.wait_for_timeout(300)
            page.screenshot(path=os.path.join(SHOT_DIR, "v18-真实对比-日景夜景.png"))
    print("报错：", errs[:2])
    br.close()
