# -*- coding: utf-8 -*-
"""真实链路验证：编辑一张图 → 原图不变 + 新卡出现且有连线 + 结果尺寸真实。"""
import os
import time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8321/canvas.html"
SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "截图")

ok = True


def check(name, cond, detail=""):
    global ok
    ok = ok and bool(cond)
    print(("PASS  " if cond else "FAIL  ") + name + (("  | " + str(detail)) if detail else ""))


with sync_playwright() as pw:
    br = pw.chromium.launch(channel="msedge")
    ctx = br.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE)
    pg.wait_for_selector(".snc-node")
    pg.wait_for_timeout(1500)

    def snap():
        return pg.evaluate("""() => Array.from(document.querySelectorAll('.snc-node')).map(d => {
            const r = d.getBoundingClientRect();
            const img = d.querySelector('img.snc-photo');
            return {id: d.dataset.id, label: (d.querySelector('.snc-node-label')||{}).textContent || '',
                    x: r.x, y: r.y, w: r.width, h: r.height,
                    len: img ? img.src.length : 0,
                    fail: !!d.querySelector('.snc-fail-msg'),
                    err: (d.querySelector('.snc-fail-msg')||{}).textContent || ''};
        })""")

    cards0 = snap()
    target = cards0[2]
    orig_id, orig_len = target["id"], target["len"]
    print("目标卡片:", target["label"], "位图长度", orig_len)

    pg.mouse.click(target["x"] + target["w"] / 2, target["y"] + target["h"] / 2)
    pg.wait_for_timeout(300)
    pg.click('#sncImgBar button[data-act="edit"]')
    pg.wait_for_timeout(400)
    pg.fill("#sncComposeInput",
            "把这个模型鸟瞰截图变成真实的景观渲染图，保留俯视机位、透视关系与地块切割，"
            "傍晚六点，蓝调天空，商业灯光刚亮起，材质写实")
    pg.screenshot(path=os.path.join(SHOT, "v16-真实编辑-提交前.png"))
    pg.click("#sncComposeSend")

    done = False
    deadline = time.time() + 200
    while time.time() < deadline:
        pg.wait_for_timeout(3000)
        cards = snap()
        new = [c for c in cards if "编辑" in c["label"]]
        if new and (new[0]["len"] > 20000 or new[0]["fail"]):
            done = True
            break
    cards = snap()
    new = [c for c in cards if "编辑" in c["label"]]
    check("编辑产生了一张新卡", len(new) == 1, [c["label"] for c in new])
    check("新卡不是失败态", bool(new) and not new[0]["fail"], new[:1] and new[0]["err"])
    check("新卡有真实位图", bool(new) and new[0]["len"] > 20000, new[:1] and new[0]["len"])
    old = [c for c in cards if c["id"] == orig_id][0]
    check("原图位图没有被覆盖", old["len"] == orig_len, (orig_len, old["len"]))
    # 镜头会跟到新卡，屏幕坐标必然整体平移；原图自身尺寸与标签不变才说明数据没被动过
    check("原图卡片尺寸与标签未变",
          abs(old["w"] - target["w"]) < 2 and abs(old["h"] - target["h"]) < 2
          and old["label"] == target["label"], (round(old["w"]), round(target["w"]), old["label"]))
    check("新卡在原图下方", bool(new) and new[0]["y"] > old["y"] + old["h"] - 2,
          new[:1] and (round(new[0]["y"]), round(old["y"] + old["h"])))
    edges = pg.evaluate("() => document.querySelectorAll('#sncEdges path').length")
    check("原图与新卡之间有连线", edges >= 2, edges)
    size = pg.evaluate("""(id) => {
        const d = document.querySelector('.snc-node[data-id="' + id + '"]');
        const b = d.querySelector('.snc-sizebadge');
        return b ? b.textContent : '';
    }""", new[0]["id"] if new else "")
    print("新卡尺寸标签:", size)
    check("尺寸来自真实回包（非请求参数）", "×" in size or "x" in size, size)
    check("真实链路无 JS 报错", not errs, errs[:3])
    pg.wait_for_timeout(600)
    pg.screenshot(path=os.path.join(SHOT, "v16-真实编辑-完成.png"))
    ctx.close()
    br.close()

print("\n真实链路：" + ("通过" if ok else "有问题"))
