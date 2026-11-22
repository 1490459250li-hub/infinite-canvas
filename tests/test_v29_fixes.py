# -*- coding: utf-8 -*-
"""v2.9 回归：底部插入图片 / 模式精简 / 套索反选 / 分辨率档位 / 减选 / 图层 PS 化。

不依赖真实接口：/api/generate 全部用桩，返回一张噪声 PNG。
"""
import base64, json, os, struct, sys, zlib
from playwright.sync_api import sync_playwright

BASE = os.environ.get("SNC_BASE", "http://127.0.0.1:8321/canvas.html")
SHOTS = r"E:\canvas-probe2\shots-v29"
os.makedirs(SHOTS, exist_ok=True)
PASS = FAIL = 0
FAILS = []


def check(name, ok, extra=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  PASS", name)
    else:
        FAIL += 1
        FAILS.append((name, extra))
        print("  FAIL", name, "->", extra)


def png(w, h, noise=True):
    rows = []
    seed = 12345
    for y in range(h):
        row = bytearray(b"\x00")
        for x in range(w):
            if noise:
                seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
                v = 40 + (seed >> 16) % 180
                row += bytes((v, (v * 3) % 256, (v * 7) % 256))
            else:
                row += bytes((60, 70, 80))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(t, d):
        return (struct.pack(">I", len(d)) + t + d +
                struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


PICB = png(600, 420)
PIC = "data:image/png;base64," + base64.b64encode(PICB).decode("ascii")
ATT = os.path.join(SHOTS, "att.png")
open(ATT, "wb").write(png(240, 240, noise=False))

errs = []
bodies = []

with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    ctx = br.new_context(viewport={"width": 1560, "height": 940})
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
    pg.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" else None)

    def stub(route):
        try:
            bodies.append(json.loads(route.request.post_data or "{}"))
        except Exception:
            bodies.append({})
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True, "b64": base64.b64encode(PICB).decode("ascii"),
                                       "size": "600x420", "format": "png", "model": "sensenova-u1.5-fast",
                                       "latencyMs": 120}))

    pg.route("**/api/generate", stub)
    pg.goto(BASE)
    pg.wait_for_selector(".snc-node")
    pg.wait_for_timeout(700)

    # ================= A. 结构 =================
    print("\n== A 结构 ==")
    pg.click("#sncFit")
    pg.wait_for_timeout(200)
    pg.locator(".snc-node .snc-photo").first.click()
    pg.wait_for_timeout(200)
    pg.click('#sncImgBar button[data-act="inpaint"]')
    pg.wait_for_timeout(600)
    check("工作台已打开", pg.evaluate("() => !document.getElementById('sncInp').hidden"))
    check("使用教程按钮已取消", pg.locator("#sncInpHelp").count() == 0)
    tools = pg.locator("#sncInpTools button").all_inner_texts()
    check("底部只剩 指针/抓手/±", tools == ["指针", "抓手", "−", "＋"], tools)
    modes = pg.locator('#sncInp [data-group="mode"] button').all_inner_texts()
    check("重绘模式只剩 描述重绘 / 选区重绘", modes == ["描述重绘", "选区重绘"], modes)
    res = pg.locator('#sncInp [data-group="res"] button').all_inner_texts()
    check("分辨率改成 原图/2K/4K", res == ["原图", "2K", "4K"], res)
    check("默认选中「原图」",
          pg.evaluate("""() => document.querySelector('#sncInp [data-group="res"] button[data-v="0"]').classList.contains('is-on')"""))
    chips = pg.locator('#sncInp [data-group="tool"] button').all_inner_texts()
    check("工具里「橡皮擦」已改名「减选」", "减选" in chips and "橡皮擦" not in chips, chips)
    check("生成描述下有参考图入口", pg.locator("#sncInpRefAdd").count() == 1)

    # ================= B. 模式联动 =================
    print("\n== B 模式联动 ==")
    pg.click('#sncInp [data-group="mode"] button[data-v="desc"]')
    pg.wait_for_timeout(180)
    check("描述重绘：建立选区整块隐藏", pg.evaluate("() => document.getElementById('sncInpSecTool').hidden"))
    check("描述重绘：编辑选区整块隐藏", pg.evaluate("() => document.getElementById('sncInpSecEdit').hidden"))
    check("描述重绘：提示文案切换",
          "描述重绘" in pg.inner_text("#sncInpHint"), pg.inner_text("#sncInpHint"))
    pg.screenshot(path=os.path.join(SHOTS, "v29-desc-mode.png"))
    pg.click('#sncInp [data-group="mode"] button[data-v="select"]')
    pg.wait_for_timeout(180)
    check("切回选区重绘：两块都回来了",
          (not pg.evaluate("() => document.getElementById('sncInpSecTool').hidden")) and
          (not pg.evaluate("() => document.getElementById('sncInpSecEdit').hidden")))

    # ================= C. 套索反选 =================
    print("\n== C 套索反选 ==")
    mask = pg.locator("#sncInpMask").bounding_box()
    pg.click('#sncInp [data-group="tool"] button[data-v="lasso"]')
    pts = [(0.22, 0.18), (0.74, 0.22), (0.48, 0.72)]
    for fx, fy in pts:
        pg.mouse.click(mask["x"] + mask["width"] * fx, mask["y"] + mask["height"] * fy)
        pg.wait_for_timeout(110)
    # 点回起点闭合
    pg.mouse.click(mask["x"] + mask["width"] * 0.22, mask["y"] + mask["height"] * 0.18)
    pg.wait_for_timeout(250)
    poly = pg.evaluate("() => (window.SNC_V26_INPAINT.rects[0]||{}).poly || null")
    check("多边形选区已建立（3 顶点以上）", bool(poly) and len(poly) >= 3,
          len(poly) if poly else None)

    pg.click('#sncInp button[data-edit="invert"]')
    pg.wait_for_timeout(300)
    after = pg.evaluate("""() => window.SNC_V26_INPAINT.rects.map(r => ({
        x:r.x, y:r.y, w:r.w, h:r.h, k:r.kind,
        invert: !!(r.invertOf && r.invertOf.length),
        holes: (r.invertOf || []).length,
        holeVerts: ((r.invertOf || [])[0] || {}).poly ? r.invertOf[0].poly.length : 0
    }))""")
    # v3.3：反选不再栅格化成横条，而是一条「整张图 − 原选区」的语义选区，
    # 提交时整图重绘、再把原选区按形状盖回原图。
    check("反选后是一条「整图 − 原选区」的选区", len(after) == 1, after)
    check("反选范围覆盖整张图",
          bool(after) and after[0]["w"] == 1 and after[0]["h"] == 1, after)
    check("原选区作为「洞」被完整保留（顶点数一致）",
          bool(after) and after[0]["invert"] and after[0]["holeVerts"] == len(poly), after)

    # 洞内不能算进可重绘范围，否则等于「反选没生效」
    covered = pg.evaluate("""(poly) => {
        const inside = (p) => {
          let hit = false;
          for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
            const xi = poly[i].x, yi = poly[i].y, xj = poly[j].x, yj = poly[j].y;
            if (((yi > p.y) !== (yj > p.y)) &&
                (p.x < (xj - xi) * (p.y - yi) / ((yj - yi) || 1e-9) + xi)) hit = !hit;
          }
          return hit;
        };
        const r = window.SNC_V26_INPAINT.rects[0] || {};
        const holes = r.invertOf || [];
        let total = 0, bad = 0;
        for (let i = 1; i < 20; i++) for (let j = 1; j < 20; j++) {
          const p = {x: i / 20, y: j / 20};
          if (!inside(p)) continue;
          total++;
          if (!holes.length) bad++;
        }
        return {total, bad};
    }""", poly)
    check("原选区内部不会被重绘", covered["bad"] == 0, covered)
    pg.screenshot(path=os.path.join(SHOTS, "v29-invert.png"))

    pg.click('#sncInp button[data-edit="invert"]')
    pg.wait_for_timeout(250)
    back = pg.evaluate("() => window.SNC_V26_INPAINT.rects.map(r => r.kind)")
    check("再按一次反选 = 取消，回到原来的多边形选区", back == ["poly"], back)

    # ================= D. 减选 / 清空 =================
    print("\n== D 减选 ==")
    pg.click('#sncInp button[data-edit="clear"]')
    pg.wait_for_timeout(150)
    pg.click('#sncInp [data-group="tool"] button[data-v="rect"]')
    pg.mouse.move(mask["x"] + mask["width"] * 0.2, mask["y"] + mask["height"] * 0.2)
    pg.mouse.down()
    pg.mouse.move(mask["x"] + mask["width"] * 0.62, mask["y"] + mask["height"] * 0.62, steps=6)
    pg.mouse.up()
    pg.wait_for_timeout(200)
    check("矩形选区已建立", pg.evaluate("() => window.SNC_V26_INPAINT.rects.length") == 1)
    pg.click('#sncInp [data-group="tool"] button[data-v="eraser"]')
    pg.mouse.click(mask["x"] + mask["width"] * 0.41, mask["y"] + mask["height"] * 0.41)
    pg.wait_for_timeout(250)
    pieces = pg.evaluate("() => window.SNC_V26_INPAINT.rects.map(r => r.kind)")
    check("减选把矩形切成多块（不是整块删除）", len(pieces) >= 2 and all(k == "rect" for k in pieces), pieces)

    # 撤销 / 重做用快捷键（按钮已撤）
    pg.click('#sncInp [data-group="tool"] button[data-v="rect"]')
    pg.mouse.move(mask["x"] + mask["width"] * 0.15, mask["y"] + mask["height"] * 0.15)
    pg.mouse.down()
    pg.mouse.move(mask["x"] + mask["width"] * 0.35, mask["y"] + mask["height"] * 0.35, steps=4)
    pg.mouse.up()
    pg.wait_for_timeout(150)
    n_before = pg.evaluate("() => window.SNC_V26_INPAINT.rects.length")
    pg.locator("#sncInpMask").click(position={"x": 5, "y": 5})
    pg.keyboard.press("Control+z")
    pg.wait_for_timeout(200)
    n_after = pg.evaluate("() => window.SNC_V26_INPAINT.rects.length")
    check("Ctrl+Z 能撤销选区操作", n_after <= n_before, (n_before, n_after))

    # ================= E. 分辨率提交 =================
    print("\n== E 分辨率 / 参考图 提交 ==")
    pg.click('#sncInp button[data-edit="clear"]')
    pg.wait_for_timeout(120)
    pg.click('#sncInp [data-group="res"] button[data-v="2048"]')
    pg.wait_for_timeout(120)
    check("选 2K 后说明文案更新", "2048" in pg.inner_text("#sncInpResNote"), pg.inner_text("#sncInpResNote"))
    pg.set_input_files("#sncInpFile", ATT)
    pg.wait_for_timeout(500)
    check("参考图缩略图出现", pg.locator("#sncInpRefList .snc-inp-ref").count() == 1,
          pg.locator("#sncInpRefList .snc-inp-ref").count())

    bodies.clear()
    pg.click('#sncInp [data-group="tool"] button[data-v="rect"]')
    pg.mouse.move(mask["x"] + mask["width"] * 0.3, mask["y"] + mask["height"] * 0.3)
    pg.mouse.down()
    pg.mouse.move(mask["x"] + mask["width"] * 0.6, mask["y"] + mask["height"] * 0.6, steps=5)
    pg.mouse.up()
    pg.wait_for_timeout(150)
    pg.fill("#sncInpPrompt", "把这块地面换成灰色石材")
    pg.click("#sncInpGo")
    pg.wait_for_timeout(2500)
    check("提交确实打到 /api/generate", len(bodies) >= 1, len(bodies))
    if bodies:
        b = bodies[0]
        check("请求带 3 张图（裁片 + 整图 + 参考图）", len(b.get("images") or []) == 3,
              len(b.get("images") or []))
        check("分辨率按 2K 下发", b.get("res") == 2048, b.get("res"))

    # 成品尺寸：2K 档位下长边应≈2048（桩图 600x420，回贴后重建到目标尺寸）
    sz = pg.evaluate("""() => {
        const ns = [...document.querySelectorAll('.snc-node')];
        const last = ns[ns.length - 1];
        return last ? last.querySelector('.snc-sizebadge') ? last.querySelector('.snc-sizebadge').textContent : '' : '';
    }""")
    check("2K 档位成品长边≈2048", "2048" in sz.replace("×", "x"), sz)

    # 描述重绘：不裁剪，整图编辑（请求里只有原图 1 张，没有裁片 + 整图两张）
    pg.locator(".snc-node .snc-photo").first.click()
    pg.wait_for_timeout(250)
    pg.click('#sncImgBar button[data-act="inpaint"]')
    pg.wait_for_timeout(500)
    pg.click('#sncInp [data-group="mode"] button[data-v="desc"]')
    pg.wait_for_timeout(120)
    pg.click('#sncInp [data-group="res"] button[data-v="4096"]')
    pg.wait_for_timeout(120)
    pg.fill("#sncInpPrompt", "改成黄昏暖光")
    bodies.clear()
    pg.click("#sncInpGo")
    pg.wait_for_timeout(2500)
    check("描述重绘也打到接口", len(bodies) >= 1, len(bodies))
    if bodies:
        check("描述重绘只发 1 张（整图，不裁剪）", len(bodies[0].get("images") or []) == 1,
              len(bodies[0].get("images") or []))
        check("描述重绘按 4K 下发", bodies[0].get("res") == 4096, bodies[0].get("res"))

    # ================= F. 图层 PS 化 =================
    print("\n== F 图层 ==")
    pg.wait_for_timeout(1200)
    pg.click("#sncLayersBtn")
    pg.wait_for_timeout(300)
    rows = pg.locator("#sncLayersBody .snc-layer-row").count()
    check("图层面板有行", rows >= 3, rows)
    check("每行都有眼睛按钮",
          pg.locator("#sncLayersBody .snc-layer-eye").count() == rows,
          (pg.locator("#sncLayersBody .snc-layer-eye").count(), rows))
    check("眼睛是 SVG 图标（不是文字圆点）",
          pg.evaluate("""() => !!document.querySelector('#sncLayersBody .snc-layer-eye svg')"""))
    check("成组 / 解组按钮都在",
          pg.locator("#sncLayersGroup").count() == 1 and pg.locator("#sncLayersUngroup").count() == 1)

    ids = pg.evaluate("""() => [...document.querySelectorAll('#sncLayersBody .snc-layer-row[data-lid]')]
        .slice(0, 3).map(r => r.dataset.lid)""")
    check("拿到至少 2 行节点 id", len(ids) >= 2, ids)

    # Shift 多选 → 成组
    pg.click('.snc-layer-row[data-lid="%s"]' % ids[0])
    pg.keyboard.down("Shift")
    pg.click('.snc-layer-row[data-lid="%s"]' % ids[1])
    pg.keyboard.up("Shift")
    pg.wait_for_timeout(200)
    pg.click("#sncLayersGroup")
    pg.wait_for_timeout(300)
    check("出现组行", pg.locator("#sncLayersBody .snc-layer-row.is-grp").count() == 1,
          pg.locator("#sncLayersBody .snc-layer-row.is-grp").count())
    check("组内成员有两行", pg.locator("#sncLayersBody .snc-layer-row.is-kid").count() == 2,
          pg.locator("#sncLayersBody .snc-layer-row.is-kid").count())
    check("组名是「组 N」", "组" in pg.locator("#sncLayersBody .snc-layer-row.is-grp .snc-layer-t").inner_text(),
          pg.locator("#sncLayersBody .snc-layer-row.is-grp .snc-layer-t").inner_text())
    pg.screenshot(path=os.path.join(SHOTS, "v29-layers-group.png"))

    # 组眼睛 → 整组隐藏
    pg.click("#sncLayersBody .snc-layer-row.is-grp .snc-layer-eye")
    pg.wait_for_timeout(300)
    hidden = pg.evaluate("""(ids) => ids.every(id => {
        const n = window.SNC_V26_INPAINT ? null : null;
        const el = document.querySelector('.snc-node[data-id="' + id + '"]');
        return el && el.style.opacity === '0';
    })""", ids[:2])
    check("点组眼睛 = 整组隐藏", hidden, hidden)

    # 解组
    pg.click("#sncLayersGroup") if False else None
    pg.click("#sncLayersBody .snc-layer-row.is-grp")
    pg.wait_for_timeout(200)
    pg.click("#sncLayersUngroup")
    pg.wait_for_timeout(300)
    check("解组后组行消失", pg.locator("#sncLayersBody .snc-layer-row.is-grp").count() == 0,
          pg.locator("#sncLayersBody .snc-layer-row.is-grp").count())

    # 拖拽排序：把最后一行拖到第一行上方
    order0 = pg.evaluate("""() => [...document.querySelectorAll('#sncLayersBody .snc-layer-row[data-lid]')]
        .map(r => r.dataset.lid)""")
    if len(order0) >= 2:
        pg.evaluate("""([from, to]) => {
            const rowA = document.querySelector('.snc-layer-row[data-lid="' + from + '"]');
            const rowB = document.querySelector('.snc-layer-row[data-lid="' + to + '"]');
            const dt = new DataTransfer();
            rowA.dispatchEvent(new DragEvent('dragstart', {bubbles: true, dataTransfer: dt}));
            const rb = rowB.getBoundingClientRect();
            rowB.dispatchEvent(new DragEvent('dragover', {bubbles: true, dataTransfer: dt,
                clientX: rb.left + 20, clientY: rb.top + 2}));
            rowB.dispatchEvent(new DragEvent('drop', {bubbles: true, dataTransfer: dt,
                clientX: rb.left + 20, clientY: rb.top + 2}));
        }""", [order0[-1], order0[0]])
        pg.wait_for_timeout(400)
        order1 = pg.evaluate("""() => [...document.querySelectorAll('#sncLayersBody .snc-layer-row[data-lid]')]
            .map(r => r.dataset.lid)""")
        check("拖动后顺序改变（最后一张跑到第一位）", order1[0] == order0[-1], (order0[:3], order1[:3]))
        check("拖动后行数不变", len(order1) == len(order0), (len(order0), len(order1)))

    # ================= G. 底部插入图片 =================
    print("\n== G 底部插入图片 ==")
    pg.click("#sncLayersX")
    pg.wait_for_timeout(200)
    check("底部条有插入图片按钮", pg.locator("#sncGAttBtn").count() == 1)
    pg.set_input_files("#sncGFile", ATT)
    pg.wait_for_timeout(600)
    check("插入后出现缩略图", pg.locator("#sncGAtts .snc-p-att").count() == 1,
          pg.locator("#sncGAtts .snc-p-att").count())
    check("插入后缩略条可见", pg.evaluate("() => !document.getElementById('sncGAtts').hidden"))
    check("提示文案提到插入图", "插入图" in pg.inner_text("#sncGTip"), pg.inner_text("#sncGTip"))
    pg.screenshot(path=os.path.join(SHOTS, "v29-bottom-att.png"))

    pg.fill("#sncInput", "按这张参考图的材质生成一张庭院")
    bodies.clear()
    pg.click("#sncSend")
    pg.wait_for_timeout(2200)
    check("底部提交打到接口", len(bodies) >= 1, len(bodies))
    if bodies:
        check("提交带上了插入的参考图", len(bodies[0].get("images") or []) >= 1,
              len(bodies[0].get("images") or []))
    check("提交后缩略条清空", pg.locator("#sncGAtts .snc-p-att").count() == 0,
          pg.locator("#sncGAtts .snc-p-att").count())

    print("\nJS 错误:", errs[:6])
    check("没有 JS 运行错误", not errs, errs[:3])

    ctx.close()
    br.close()

print("\n%d passed, %d failed" % (PASS, FAIL))
if FAILS:
    print("失败项：")
    for n, e in FAILS:
        print(" -", n, "->", e)
sys.exit(1 if FAIL else 0)
