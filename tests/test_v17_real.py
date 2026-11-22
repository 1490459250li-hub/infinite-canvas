# -*- coding: utf-8 -*-
"""v1.8 真实链路抽查：跑一次「增强」验证派生卡真的拿到上游出图、原图字节不变、
连线存在；再对这张派生卡打开「对比预览」，确认滑条左右两侧是两张真图。
其余交互由 test_v17.py 走存根覆盖。"""
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
                src: img ? (img.getAttribute('src')||'').slice(0, 24) : '',
                len: img ? (img.getAttribute('src')||'').length : 0,
                busy: !!d.querySelector('.snc-gen-wait'),
                failed: !!d.querySelector('.snc-gen-fail')};
    })""")


with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    ctx = br.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(1500)

    before = cards(page)
    target = [c for c in before if c["label"].strip() == "图片 1"][0]
    edges0 = page.evaluate("() => document.querySelectorAll('#sncEdges path').length")

    page.mouse.click(target["x"] + target["w"] / 2, target["y"] + target["h"] / 2)
    page.wait_for_timeout(300)
    page.click('#sncImgBar button[data-act="enhance"]')

    # 最多等 150 秒
    child = None
    for _ in range(75):
        page.wait_for_timeout(2000)
        now = cards(page)
        made = [c for c in now if "增强" in c["label"]]
        if made and not made[0]["busy"]:
            child = made[0]
            if child["failed"]:
                print("FAIL  上游返回失败")
            break

    after = cards(page)
    orig = [c for c in after if c["id"] == target["id"]][0]
    print("增强卡：", child["label"] if child else None,
          "| 尺寸徽标", (child or {}).get("badge"))
    print("原图字节：", target["len"], "->", orig["len"])
    print("连线：", edges0, "->", page.evaluate("() => document.querySelectorAll('#sncEdges path').length"))
    print("报错：", errs[:2])
    page.screenshot(path=os.path.join(SHOT_DIR, "v18-真实增强-完成.png"))

    # 对比预览：左原图 / 右改后，拖动滑条
    if child:
        page.mouse.click(child["x"] + child["w"] / 2, child["y"] + child["h"] / 2)
        page.wait_for_timeout(350)
        page.click('#sncImgBar button[data-act="compare"]')
        page.wait_for_timeout(500)
        cmp0 = page.evaluate("""() => {
            const b = document.querySelector('.snc-cmp-b');
            if(!b) return null;
            const imgs = Array.from(b.querySelectorAll('img')).map(i => (i.getAttribute('src')||'').length);
            const clip = b.querySelector('.snc-cmp-clip');
            const grip = b.querySelector('.snc-cmp-grip');
            const r = b.getBoundingClientRect();
            const gr = grip.getBoundingClientRect();
            return {imgs: imgs, clip: getComputedStyle(clip).clipPath,
                    x: r.x, y: r.y, w: r.width, h: r.height,
                    gx: gr.x + gr.width / 2, gy: gr.y + gr.height / 2};
        }""")
        print("对比层：", cmp0 and {"imgs": cmp0["imgs"], "clip": cmp0["clip"]})
        if cmp0:
            page.mouse.move(cmp0["gx"], cmp0["gy"])
            page.mouse.down()
            page.mouse.move(cmp0["x"] + cmp0["w"] * 0.3, cmp0["gy"], steps=12)
            page.mouse.up()
            page.wait_for_timeout(300)
            page.screenshot(path=os.path.join(SHOT_DIR, "v18-真实对比-派生前后.png"))
            print("拖动后 clip：", page.evaluate(
                "() => getComputedStyle(document.querySelector('.snc-cmp-clip')).clipPath"))
    print("报错：", errs[:2])
    br.close()
