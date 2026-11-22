# -*- coding: utf-8 -*-
"""v1.6 回归：拖入/粘贴导入、编辑派生新卡、编辑面板不遮挡+可拖+可关、
模型清单补全、AI 润色、底部参数条。全部走网络存根，不消耗出图额度。"""
import json
import os
import struct
import zlib
from playwright.sync_api import sync_playwright

# 默认端口留给老用法，但在跑整套回归时用 SNC_BASE 指向当前那个桥接服务，
# 免得端口一变这三个文件就集体 ERR_CONNECTION_REFUSED。
BASE = os.environ.get("SNC_BASE") or "http://127.0.0.1:8321/canvas.html"
SHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "截图")
os.makedirs(SHOT_DIR, exist_ok=True)

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + (("  | " + str(detail)) if detail else ""))


def png_bytes(w=160, h=100, rgb=(190, 120, 90)):
    raw = b"".join(b"\x00" + bytes(list(rgb) * w) for _ in range(h))

    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


PNG = png_bytes()
import base64
PNG64 = base64.b64encode(PNG).decode("ascii")


def boot(br, w=1440, h=900):
    ctx = br.new_context(viewport={"width": w, "height": h})
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    page = ctx.new_page()
    errs = []
    bodies = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    def gen(route):
        bodies.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True, "b64": PNG64, "size": "2048x1280",
                                       "width": 2048, "height": 1280, "format": "png",
                                       "model": "stub-image", "mode": "gen",
                                       "latencyMs": 900, "usage": {"total_tokens": 321}}))

    def polish(route):
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True, "text": "润色后的完整提示词：傍晚六点，暖色商业灯光，俯视鸟瞰机位，材质写实。",
                                       "model": "stub-text", "latencyMs": 700}, ensure_ascii=False))

    page.route("**/api/generate", gen)
    page.route("**/api/polish", polish)
    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(1400)
    return ctx, page, errs, bodies


def nodes(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll('.snc-node')).map(d => {
        const r = d.getBoundingClientRect();
        return {id: d.dataset.id, label: (d.querySelector('.snc-node-label')||{}).textContent || '',
                x: r.x, y: r.y, w: r.width, h: r.height,
                src: (d.querySelector('img.snc-photo')||{}).src || ''};
    })""")


def compose_box(page):
    return page.evaluate("""() => {
        const c = document.getElementById('sncCompose');
        const r = c.getBoundingClientRect();
        return {hidden: c.hidden, x: r.x, y: r.y, w: r.width, h: r.height,
                dock: c.dataset.dock || ''};
    }""")


def close_all(page):
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)


with sync_playwright() as pw:
    br = pw.chromium.launch(channel="msedge")

    # ---------- A. 启动 + 模型清单 ----------
    ctx, page, errs, bodies = boot(br)

    page.click(".snc-doc-foot [data-set]")
    page.wait_for_selector("#sncProvList .snc-prov", state="attached")  # v3.0：等卡片渲染（面板此时是隐藏的）
    page.wait_for_timeout(600)
    roster = page.evaluate("""() => ({
        chips: Array.from(document.querySelectorAll('#sncRosterList .snc-model-chip')).map(c => c.textContent),
        img: document.querySelectorAll('#sncRosterList .snc-model-chip.is-img').length,
        count: (document.getElementById('sncRosterCount')||{}).textContent,
        textOpts: document.querySelectorAll('#sncRoutePolish option').length,
        gModelOpts: document.querySelectorAll('#sncGModel option').length,
        cModelOpts: document.querySelectorAll('#sncModel option').length
    })""")
    # 账号里可用的模型会随上游发版变化（3.5.1 时是 6 图片 + 8 文本），
    # 这里只验「清单读到了、图片分类没串」，不锁死具体数字。
    check("模型清单读到（图片 + 文本都分类了）",
          roster["img"] >= 2 and len(roster["chips"]) >= 8, roster["count"])
    check("文本模型进入润色下拉框（v3.0 走分流下拉）", roster["textOpts"] >= 6, roster["textOpts"])
    check("出图下拉框只列真实图片模型",
          roster["gModelOpts"] == roster["img"] and roster["cModelOpts"] == roster["img"],
          (roster["gModelOpts"], roster["cModelOpts"], roster["img"]))
    params = page.evaluate("""() => {
        const p = document.querySelector('.snc-p-params').getBoundingClientRect();
        const sel = document.getElementById('sncGModel').getBoundingClientRect();
        const bar = document.querySelector('.snc-prompt').getBoundingClientRect();
        return {h: p.height, selW: sel.width, barW: bar.width, barR: bar.right};
    }""")
    check("参数行单行显示且模型名不被挤掉",
          params["h"] < 36 and params["selW"] >= 96, params)
    page.screenshot(path=os.path.join(SHOT_DIR, "v16-设置-模型清单.png"))
    page.click("#sncSetClose")
    page.wait_for_timeout(300)

    # ---------- B. 拖入图片导入 ----------
    before = len(nodes(page))
    page.evaluate("""([b64, x, y]) => {
        const bin = atob(b64), arr = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
        const file = new File([arr], 'dragged.png', {type: 'image/png'});
        const dt = new DataTransfer();
        dt.items.add(file);
        const stage = document.getElementById('sncStage');
        const opt = {bubbles: true, cancelable: true, dataTransfer: dt, clientX: x, clientY: y};
        stage.dispatchEvent(new DragEvent('dragenter', opt));
        stage.dispatchEvent(new DragEvent('dragover', opt));
        stage.dispatchEvent(new DragEvent('drop', opt));
    }""", [PNG64, 760, 380])
    page.wait_for_timeout(1500)
    after_nodes = nodes(page)
    imported = [n for n in after_nodes if n["src"].startswith("data:image/png")]
    check("拖拽导入生成了新卡片", len(after_nodes) == before + 1, (before, len(after_nodes)))
    check("导入卡片带真实位图", len(imported) >= 1, imported[:1] and imported[0]["label"])
    check("导入卡片落在拖放点附近（不跳到别处）",
          bool(imported) and abs(imported[0]["x"] - 760) < 200 and imported[0]["y"] >= 380 - 40,
          imported[:1] and (round(imported[0]["x"]), round(imported[0]["y"])))
    overlap = page.evaluate("""(id) => {
        const me = document.querySelector('.snc-node[data-id="' + id + '"]').getBoundingClientRect();
        return Array.from(document.querySelectorAll('.snc-node')).filter(d => d.dataset.id !== id)
          .some(d => { const r = d.getBoundingClientRect();
            return !(r.right <= me.left || r.left >= me.right || r.bottom <= me.top || r.top >= me.bottom); });
    }""", imported[0]["id"] if imported else "")
    check("导入卡片不压住已有卡片", not overlap)

    # ---------- C. 粘贴导入 ----------
    before = len(nodes(page))
    page.evaluate("""([b64]) => {
        const bin = atob(b64), arr = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
        const file = new File([arr], 'pasted.png', {type: 'image/png'});
        const dt = new DataTransfer();
        dt.items.add(file);
        const ev = new Event('paste', {bubbles: true, cancelable: true});
        Object.defineProperty(ev, 'clipboardData', {value: dt});
        document.dispatchEvent(ev);
    }""", [PNG64])
    page.wait_for_timeout(1400)
    check("Ctrl+V 粘贴也能导入", len(nodes(page)) == before + 1, (before, len(nodes(page))))

    # 工具栏「导入图片」按钮（内嵌 WebView 里拖拽不可靠时的兜底入口）
    before = len(nodes(page))
    page.set_input_files("#sncImportInput", files=[{
        "name": "picker.png", "mimeType": "image/png", "buffer": PNG}])
    page.wait_for_timeout(1200)
    check("工具栏导入按钮可用", len(nodes(page)) == before + 1, (before, len(nodes(page))))

    # ---------- D. 编辑面板：默认在下方、不挡原图 ----------
    target = nodes(page)[2]
    page.mouse.click(target["x"] + target["w"] / 2, target["y"] + target["h"] / 2)
    page.wait_for_timeout(350)
    page.click('#sncImgBar button[data-act="edit"]')
    page.wait_for_timeout(500)
    box = compose_box(page)
    gap = box["y"] - (target["y"] + target["h"])
    check("编辑面板默认弹在原图下方", (not box["hidden"]) and box["dock"] == "below" and gap > 0,
          (box["dock"], round(gap)))
    check("编辑面板完全不遮挡原图",
          box["y"] >= target["y"] + target["h"] - 1 or box["x"] >= target["x"] + target["w"] - 1
          or box["x"] + box["w"] <= target["x"] + 1, box)

    # 关闭按钮
    page.click("#sncComposeX")
    page.wait_for_timeout(300)
    check("编辑面板有关闭按钮且能关闭", compose_box(page)["hidden"])

    # 拖动标题栏
    page.click('#sncImgBar button[data-act="edit"]')
    page.wait_for_timeout(400)
    b0 = compose_box(page)
    head = page.evaluate("""() => { const r = document.getElementById('sncComposeHead').getBoundingClientRect();
        return {x: r.x + 40, y: r.y + r.height/2}; }""")
    page.mouse.move(head["x"], head["y"])
    page.mouse.down()
    page.mouse.move(head["x"] - 140, head["y"] + 70, steps=12)
    page.mouse.up()
    page.wait_for_timeout(300)
    b1 = compose_box(page)
    check("编辑面板可拖动", abs(b1["x"] - b0["x"]) > 40 and abs(b1["y"] - b0["y"]) > 30,
          (round(b0["x"]), round(b1["x"]), round(b0["y"]), round(b1["y"])))
    page.screenshot(path=os.path.join(SHOT_DIR, "v16-编辑面板-下方不遮挡.png"))

    # ---------- E. AI 润色 ----------
    page.fill("#sncComposeInput", "把模型截图变成真实渲染图")
    page.click("#sncPolish")
    page.wait_for_timeout(1200)
    polished = page.input_value("#sncComposeInput")
    check("AI 润色替换了提示词", "润色后的完整提示词" in polished, polished[:24])
    check("润色后可一键还原", not page.is_hidden("#sncPolishUndo"))
    page.click("#sncPolishUndo")
    page.wait_for_timeout(250)
    check("还原回润色前文本", page.input_value("#sncComposeInput") == "把模型截图变成真实渲染图")

    # ---------- F. 编辑 → 新卡，原图不动 ----------
    src_before = nodes(page)[2]["src"]
    total_before = len(nodes(page))
    page.fill("#sncComposeInput", "把这个截图变成真实夜景渲染图，保留机位")
    page.click("#sncComposeSend")
    page.wait_for_timeout(2600)
    cards = nodes(page)
    src_after = cards[2]["src"]
    new_card = [c for c in cards if "编辑" in c["label"]]
    check("编辑后卡片数 +1（不是覆盖）", len(cards) == total_before + 1, (total_before, len(cards)))
    check("原图位图未被覆盖", src_before == src_after, (src_before[:30], src_after[:30]))
    check("新卡标签标明是编辑产物", bool(new_card), new_card[:1] and new_card[0]["label"])
    edges = page.evaluate("""() => document.querySelectorAll('#sncEdges path').length""")
    check("新卡与原图之间有连线", edges >= 1, edges)
    geom = page.evaluate("""(id) => {
        const d = document.querySelector('.snc-node[data-id="' + id + '"]').getBoundingClientRect();
        const p = document.querySelector('.snc-prompt').getBoundingClientRect();
        return {cardBottom: Math.round(d.bottom), promptTop: Math.round(p.top)};
    }""", new_card[0]["id"] if new_card else "")
    check("出图后新卡完整露出（不被输入条压住）",
          bool(new_card) and geom["cardBottom"] <= geom["promptTop"] + 1, geom)
    body = bodies[-1] if bodies else {}
    check("编辑请求带原图作主编辑图",
          bool(body.get("images")) and len(body["images"]) == 1, len(body.get("images") or []))
    check("编辑请求比例跟随原图（sizeMode=auto）", body.get("sizeMode") == "auto", body.get("sizeMode"))

    # ---------- G. 底部参数条真正生效 ----------
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    page.click("#sncFit")
    page.wait_for_timeout(300)
    page.select_option("#sncGRatio", "1:1")
    page.select_option("#sncGRes", "4096")
    page.select_option("#sncGModel", "sensenova:lite")   # v3.0：下拉值是 provider:key
    page.fill("#sncInput", "庭院夜景，暖光")
    page.click("#sncSend")
    # 真实接口出 4K 要十几秒，别用固定 sleep 猜：等这条 prompt 的请求真的发出去
    deadline = 60
    while deadline > 0:
        hits = [b for b in bodies if "庭院夜景" in str(b.get("prompt") or "")]
        if hits:
            break
        page.wait_for_timeout(500)
        deadline -= 0.5
    body = ([b for b in bodies if "庭院夜景" in str(b.get("prompt") or "")] or [{}])[-1]
    check("底部参数进入请求（比例 1:1 / 4K / lite）",
          body.get("ratio") == "1:1" and str(body.get("res")) == "4096"
          and body.get("model") == "lite" and body.get("provider") == "sensenova", body)
    new_after = len(nodes(page))
    check("生成结果仍然是新卡", new_after >= total_before + 2, new_after)

    check("全程没有 JS 报错", not errs, errs[:3])
    page.screenshot(path=os.path.join(SHOT_DIR, "v16-整体画布.png"))
    ctx.close()

    # ---------- H. 窄窗口：编辑面板仍不挡图 ----------
    ctx, page, errs2, _ = boot(br, 1024, 680)
    t = nodes(page)[2]
    page.mouse.click(t["x"] + t["w"] / 2, t["y"] + t["h"] / 2)
    page.wait_for_timeout(300)
    page.click('#sncImgBar button[data-act="edit"]')
    page.wait_for_timeout(500)
    b = compose_box(page)
    check("1024×680 下编辑面板不压原图",
          not b["hidden"] and (b["y"] >= t["y"] + t["h"] - 1 or b["x"] >= t["x"] + t["w"] - 1
                               or b["x"] + b["w"] <= t["x"] + 1), (b["dock"], b["y"], t["y"] + t["h"]))
    check("窄窗口下无 JS 报错", not errs2, errs2[:2])
    page.screenshot(path=os.path.join(SHOT_DIR, "v16-窄窗-编辑面板.png"))
    ctx.close()

    # ---------- I. 更窄的窗口：输入条与缩放控件不打架 ----------
    ctx, page, errs3, _ = boot(br, 900, 640)
    geo = page.evaluate("""() => {
        const bar = document.querySelector('.snc-prompt').getBoundingClientRect();
        const zoom = document.querySelector('.snc-zoomer').getBoundingClientRect();
        return {bar: {l: bar.left, r: bar.right, t: bar.top, b: bar.bottom},
                zoom: {l: zoom.left, r: zoom.right, t: zoom.top, b: zoom.bottom},
                iw: innerWidth, ih: innerHeight};
    }""")
    sep = (geo["bar"]["r"] < geo["zoom"]["l"] or geo["zoom"]["r"] < geo["bar"]["l"] or
           geo["bar"]["b"] < geo["zoom"]["t"] or geo["zoom"]["b"] < geo["bar"]["t"])
    check("900×640 输入条与缩放控件不重叠", sep, geo)
    check("900×640 输入条不出界",
          geo["bar"]["l"] >= 0 and geo["bar"]["r"] <= geo["iw"] + 1 and geo["bar"]["b"] <= geo["ih"] + 1,
          (round(geo["bar"]["r"]), geo["iw"]))
    check("900×640 无 JS 报错", not errs3, errs3[:2])
    ctx.close()
    br.close()

print("\n%d / %d 通过" % (sum(1 for _, ok in results if ok), len(results)))
