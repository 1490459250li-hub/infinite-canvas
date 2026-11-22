# -*- coding: utf-8 -*-
"""探针：工作台面板（笔刷滑杆）+ 涂抹/橡皮/识别 行为。"""
import base64, json, os, struct, zlib
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8321/canvas.html"
SHOTS = r"E:/canvas-probe2/shots-v28"
os.makedirs(SHOTS, exist_ok=True)


def png_gray(w, h, bg=(40, 44, 50), block=(240, 90, 60), bx=(0.10, 0.45), by=(0.30, 0.80)):
    rows = []
    for y in range(h):
        fy = y / h
        row = bytearray(b"\x00")
        for x in range(w):
            fx = x / w
            c = block if (bx[0] <= fx <= bx[1] and by[0] <= fy <= by[1]) else bg
            row += bytes(c)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(t, d):
        return (struct.pack(">I", len(d)) + t + d +
                struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


PIC = "data:image/png;base64," + base64.b64encode(png_gray(560, 420)).decode("ascii")
SUBJ = os.path.join(SHOTS, "subject.png")
open(SUBJ, "wb").write(png_gray(560, 420))
errs = []

with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    ctx = br.new_context(viewport={"width": 1560, "height": 940})
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.route("**/api/generate", lambda r: r.fulfill(status=200, content_type="application/json",
             body=json.dumps({"ok": True, "b64": PIC.split(",")[1], "size": "560x420"})))
    pg.goto(BASE)
    pg.wait_for_selector(".snc-node")
    pg.wait_for_timeout(800)

    pg.fill("#sncInput", "面板探针")
    pg.click("#sncSend")
    pg.wait_for_timeout(1200)
    cid = pg.evaluate("() => [...document.querySelectorAll('.snc-node')].pop().dataset.id")
    pg.click('.snc-node[data-id="%s"]' % cid)
    pg.wait_for_timeout(200)
    pg.click('#sncImgBar button[data-act="inpaint"]')
    pg.wait_for_timeout(700)

    print("slider:", pg.evaluate("""() => { const r=document.getElementById('sncInpBrush');
        return r ? {min:r.min, max:r.max, value:r.value, w:Math.round(r.getBoundingClientRect().width)} : null; }"""))
    pg.screenshot(path=os.path.join(SHOTS, "panel-brush.png"))

    # v3.7.7：识别工具已移除，改看工具组与坐标标记
    pg.set_input_files("#sncInpFile", SUBJ)
    pg.wait_for_timeout(700)
    print("tools:", pg.eval_on_selector_all(
        '#sncInp [data-group="tool"] button', "els => els.map(e => e.dataset.v)"))
    print("marks:", pg.evaluate("() => document.getElementById('sncInpMarks')?.textContent"))
    pg.screenshot(path=os.path.join(SHOTS, "panel-tools.png"))

    # 笔刷滑杆
    pg.evaluate("""() => { const r=document.getElementById('sncInpBrush');
        r.value='72'; r.dispatchEvent(new Event('input', {bubbles:true})); }""")
    print("brush after slider:", pg.evaluate("() => window.SNC_V26_INPAINT.brush"),
          "label:", pg.inner_text("#sncInpBrushVal"), "info:", pg.inner_text("#sncInpToolInfo"))

    # 笔尖预览：涂抹工具下悬停，画布该有像素；矩形工具下没有
    pg.click('#sncInp [data-group="tool"] button[data-v="clear"]') if False else None
    pg.click('#sncInp button[data-edit="clear"]')
    pg.click('#sncInp [data-group="tool"] button[data-v="brush"]')
    box = pg.locator("#sncInpMask").bounding_box()
    pg.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
    pg.wait_for_timeout(200)
    alpha_brush = pg.evaluate("""() => { const c=document.getElementById('sncInpMask');
        const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
        let n=0; for(let i=3;i<d.length;i+=4) if(d[i]>0) n++; return n; }""")
    pg.click('#sncInp [data-group="tool"] button[data-v="rect"]')
    pg.mouse.move(box["x"] + box["width"] * 0.55, box["y"] + box["height"] * 0.55)
    pg.wait_for_timeout(200)
    alpha_rect = pg.evaluate("""() => { const c=document.getElementById('sncInpMask');
        const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
        let n=0; for(let i=3;i<d.length;i+=4) if(d[i]>0) n++; return n; }""")
    print("hover ring pixels: brush=", alpha_brush, "rect=", alpha_rect)

    # 涂抹一笔 → stroke；橡皮擦从中间擦 → 切块
    pg.click('#sncInp [data-group="tool"] button[data-v="rect"]')
    pg.mouse.move(box["x"] + box["width"] * 0.2, box["y"] + box["height"] * 0.2)
    pg.mouse.down()
    pg.mouse.move(box["x"] + box["width"] * 0.8, box["y"] + box["height"] * 0.8, steps=8)
    pg.mouse.up()
    pg.wait_for_timeout(200)
    print("after rect:", pg.evaluate("() => window.SNC_V26_INPAINT.rects.map(r=>({k:r.kind,x:+r.x.toFixed(2),w:+r.w.toFixed(2),h:+r.h.toFixed(2)}))"))
    pg.click('#sncInp [data-group="tool"] button[data-v="eraser"]')
    pg.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
    pg.wait_for_timeout(250)
    print("after erase:", pg.evaluate("() => window.SNC_V26_INPAINT.rects.map(r=>({k:r.kind,x:+r.x.toFixed(2),y:+r.y.toFixed(2),w:+r.w.toFixed(2),h:+r.h.toFixed(2)}))"))

    pg.click('#sncInp [data-group="tool"] button[data-v="brush"]')
    pg.mouse.move(box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.7)
    pg.mouse.down()
    pg.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + box["height"] * 0.7, steps=8)
    pg.mouse.up()
    pg.wait_for_timeout(250)
    print("kinds:", pg.evaluate("() => window.SNC_V26_INPAINT.rects.map(r=>r.kind)"))

    # 多边形进行中点清空，pending 要清掉
    pg.click('#sncInp button[data-edit="clear"]')
    pg.click('#sncInp [data-group="tool"] button[data-v="lasso"]')
    for fx, fy in [(0.2, 0.2), (0.5, 0.2)]:
        pg.mouse.click(box["x"] + box["width"] * fx, box["y"] + box["height"] * fy)
        pg.wait_for_timeout(120)
    print("pending before clear:", pg.evaluate("() => (window.SNC_V26_INPAINT.pending||[]).length"))
    pg.click('#sncInp button[data-edit="clear"]')
    print("pending after clear:", pg.evaluate("() => (window.SNC_V26_INPAINT.pending||[]).length"))
    print("errors:", errs[:6])
    ctx.close()
    br.close()
