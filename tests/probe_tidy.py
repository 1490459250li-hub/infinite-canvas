# -*- coding: utf-8 -*-
"""探针：整理画布的树形排布是否把派生图挂回父图下方。"""
import base64, json, os, random, struct, zlib
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8321/canvas.html"
SHOTS = r"E:\canvas-probe2\shots-v28"
os.makedirs(SHOTS, exist_ok=True)


def png(w, h, color=(180, 120, 90), noise=False):
    if noise:
        rnd = random.Random(20261108)
        row = bytes(rnd.randrange(256) for _ in range(w * 3))
        raw = b"".join(b"\x00" + bytes((row[i] + y) % 256 for i in range(len(row)))
                       for y in range(h))
    else:
        raw = b"".join(b"\x00" + bytes(color) * w for _ in range(h))

    def chunk(t, d):
        return (struct.pack(">I", len(d)) + t + d +
                struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


PIC = "data:image/png;base64," + base64.b64encode(png(560, 420, noise=True)).decode("ascii")
errs = []

with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    ctx = br.new_context(viewport={"width": 1560, "height": 940})
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    page = ctx.new_page()
    page.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
    page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)

    def stub(route):
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True, "b64": PIC.split(",")[1], "size": "560x420"}))

    page.route("**/api/generate", stub)
    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(800)

    def make_card(tag):
        page.fill("#sncInput", tag)
        page.click("#sncSend")
        page.wait_for_timeout(800)
        return page.evaluate("""() => { const c=[...document.querySelectorAll('.snc-node')];
                                       return c[c.length-1].dataset.id; }""")

    ids = [make_card("探针 %d" % i) for i in range(5)]
    print("cards:", len(ids), ids)

    def derive(parent):
        page.click('.snc-node[data-id="%s"]' % parent)
        page.wait_for_timeout(250)
        page.click('#sncImgBar button[data-act="inpaint"]')
        page.wait_for_timeout(600)
        box = page.locator("#sncInpMask").bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.3)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + box["height"] * 0.6, steps=6)
        page.mouse.up()
        page.fill("#sncInpPrompt", "探针派生")
        before = page.locator(".snc-node").count()
        page.click("#sncInpGo")
        page.wait_for_timeout(3500)
        after = page.locator(".snc-node").count()
        print("derive:", before, "->", after)
        return page.evaluate("""() => { const c=[...document.querySelectorAll('.snc-node')];
                                       return c[c.length-1].dataset.id; }""")

    c1 = derive(ids[4])
    c2 = derive(ids[4])

    page.click("#sncTidyBtn")
    page.wait_for_timeout(900)

    lay = page.evaluate("""(ids) => {
        const box = id => { const n = document.querySelector('.snc-node[data-id="'+id+'"]');
            const r = n.getBoundingClientRect();
            return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width),
                    h: Math.round(r.height), cx: Math.round(r.x + r.width/2)}; };
        const o = {};
        ids.forEach(id => o[id] = box(id));
        return o;
    }""", ids + [c1, c2])
    for k, v in lay.items():
        print(("child " if k in (c1, c2) else "root  ") + k, v)
    print("parent:", lay[ids[4]], "children:", lay[c1], lay[c2])
    page.screenshot(path=os.path.join(SHOTS, "probe-tidy.png"))
    print("errors:", errs[:5])
    ctx.close()
    br.close()
