# -*- coding: utf-8 -*-
"""v2.2 回归：编辑面板三段式布局 + 多张参考图上传。

参考用户给的两张截图：图片缩略图在最上（后面跟着空位卡表示还能加），
中间是提示词编辑区，最下面才是功能 / 模型 / 尺寸选择与发送。
本测试全程走网络存根，不消耗出图额度。
"""
import base64
import json
import os
import struct
import sys
import zlib
from playwright.sync_api import sync_playwright

BASE = os.environ.get("SNC_BASE", "http://127.0.0.1:8321/canvas.html")
TMP = r"E:\canvas-probe2\tmp\ui"
SHOTS = r"E:\canvas-probe2\shots-v22-ui"
os.makedirs(TMP, exist_ok=True)
os.makedirs(SHOTS, exist_ok=True)

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + (("  | " + str(detail)) if detail else ""))


def png_bytes(w, h):
    row = bytes([190, 120, 90]) * w
    raw = b"".join(b"\x00" + row for _ in range(h))

    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


uploads = []
for i, (w, h) in enumerate([(320, 240), (400, 300), (480, 360)]):
    path = os.path.join(TMP, "upload-%d.png" % (i + 1))
    with open(path, "wb") as f:
        f.write(png_bytes(w, h))
    uploads.append(path)

with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    ctx = br.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    bodies = []

    def gen(route):
        bodies.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True,
                                       "b64": base64.b64encode(png_bytes(800, 600)).decode("ascii"),
                                       "size": "stub", "width": 800, "height": 600,
                                       "format": "png", "model": "stub-image", "mode": "gen",
                                       "latencyMs": 100, "usage": {}}))

    page.route("**/api/generate", gen)
    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(900)

    before = page.evaluate(
        "() => Array.from(document.querySelectorAll('.snc-node')).map(d=>d.dataset.id)")
    page.fill("#sncInput", "布局测试原图")
    page.click("#sncSend")
    page.wait_for_timeout(1400)
    new_id = page.evaluate("""(old) => {
        const cs = Array.from(document.querySelectorAll('.snc-node'));
        const n = cs.find(d => !old.includes(d.dataset.id));
        return n ? n.dataset.id : '';
    }""", before)
    check("生成出可编辑卡片", bool(new_id), new_id)

    card = page.locator('.snc-node[data-id="%s"]' % new_id)
    card.click()
    page.wait_for_timeout(350)
    page.click('#sncImgBar button[data-act="edit"]')
    page.wait_for_timeout(350)
    check("编辑面板已打开", page.evaluate("() => !document.getElementById('sncCompose').hidden"))

    # ---- ① 三段式布局 ----
    lay = page.evaluate("""() => {
        const g = s => { const e = document.querySelector(s); return e ? e.getBoundingClientRect() : null; };
        const m = g('#sncComposeMedia'), e = g('.snc-compose-editor'), f = g('.snc-compose-foot');
        return {
            m: m && Math.round(m.top), e: e && Math.round(e.top), f: f && Math.round(f.top),
            ratioInFoot: !!document.querySelector('.snc-compose-foot #sncRatio'),
            resInFoot: !!document.querySelector('.snc-compose-foot #sncRes'),
            modelInFoot: !!document.querySelector('.snc-compose-foot #sncModel'),
            polishInFoot: !!document.querySelector('.snc-compose-foot #sncPolish'),
            textareaInEditor: !!document.querySelector('.snc-compose-editor #sncComposeInput'),
            attsInMedia: !!document.querySelector('#sncComposeMedia #sncAtts'),
            sendInFoot: !!document.querySelector('.snc-compose-foot #sncComposeSend'),
            footHasBorder: getComputedStyle(document.querySelector('.snc-compose-foot')).borderTopWidth,
            sendTop: Math.round(g('.snc-compose-foot #sncComposeSend').top),
            footTop: Math.round(f.top),
            footWrap: getComputedStyle(document.querySelector('.snc-compose-foot')).flexWrap
        };
    }""")
    check("图片区在提示词区上方", lay["m"] is not None and lay["e"] is not None and lay["m"] < lay["e"], lay)
    check("提示词区在参数工具条上方", lay["e"] is not None and lay["f"] is not None and lay["e"] < lay["f"], lay)
    check("缩略图挂在图片区", lay["attsInMedia"])
    check("提示词 textarea 独立占中间一行", lay["textareaInEditor"])
    check("比例 / 分辨率 / 模型都在底部工具条",
          lay["ratioInFoot"] and lay["resInFoot"] and lay["modelInFoot"], lay)
    check("AI 润色与发送按钮都在底部", lay["polishInFoot"] and lay["sendInFoot"])
    check("底部工具条有分隔线", lay["footHasBorder"] != "0px", lay["footHasBorder"])
    check("发送按钮与参数同一行（底部不换行）",
          lay["footWrap"] == "nowrap" and 0 <= lay["sendTop"] - lay["footTop"] < 30,
          (lay["sendTop"], lay["footTop"], lay["footWrap"]))

    # ---- ② 多张上传可视化 ----
    check("打开编辑默认带 1 张原图", page.locator("#sncAtts .snc-att").count() == 1,
          page.locator("#sncAtts .snc-att").count())
    check("剩余空位显示 4 个占位卡", page.locator("#sncAtts .snc-att-slot").count() == 4,
          page.locator("#sncAtts .snc-att-slot").count())
    tip0 = page.inner_text("#sncAttTip")
    check("初始文案说明已附 1 张 / 还可加 4 张 / 可多张",
          "已附 1 张" in tip0 and "还可加 4 张" in tip0 and "多张" in tip0, tip0)

    page.set_input_files("#sncFileInput", uploads)
    page.wait_for_timeout(1000)
    n_att = page.locator("#sncAtts .snc-att").count()
    n_slot = page.locator("#sncAtts .snc-att-slot").count()
    check("一次选 3 张后附件共 4 张", n_att == 4, n_att)
    check("空位卡相应减少到 1 个", n_slot == 1, n_slot)
    tip1 = page.inner_text("#sncAttTip")
    check("文案更新为「已附 4 张 · 还可加 1 张」", "已附 4 张" in tip1 and "还可加 1 张" in tip1, tip1)
    check("每张参考图都有角色标签", page.locator("#sncAtts .snc-att-role").count() == 4)

    # 空位卡本身也能点开选图
    try:
        with page.expect_file_chooser(timeout=3000) as fc:
            page.locator("#sncAtts .snc-att-slot").first.click()
        fc.value.set_files([])          # 取消，不改变附件数量
        check("空位卡可点击打开选图框", True)
    except Exception as ex:
        check("空位卡可点击打开选图框", False, str(ex)[:120])

    page.screenshot(path=os.path.join(SHOTS, "v22-编辑面板-三段式多图.png"), full_page=False)

    # ---- ③ 提交：多张参考图都要进 edits ----
    page.fill("#sncComposeInput", "保持构图与机位，改成清晨光线")
    page.click("#sncComposeSend")
    page.wait_for_timeout(1500)
    last = bodies[-1] if bodies else {}
    imgs = last.get("images") or []
    check("提交携带 4 张参考图（不是纯文生图）", len(imgs) == 4, len(imgs))
    check("请求走 sizeMode=auto", last.get("sizeMode") == "auto", last.get("sizeMode"))
    check("多张参考图合计体积受控（<16MB 预算）",
          sum(len(u) for u in imgs) < 16 * 1024 * 1024,
          sum(len(u) for u in imgs))
    check("全程无 JS 报错", not errs, errs[:3])

    # ---- ④ 亮色主题下三段式布局同样可读 ----
    page.evaluate("() => { try{localStorage.setItem('snc.theme.v1','light')}catch(e){} }")
    page.reload()
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(900)
    check("亮色主题已生效",
          page.evaluate("() => document.getElementById('snc').getAttribute('data-theme')") == "light")
    card2 = page.locator('.snc-node[data-id="%s"]' % new_id)
    if card2.count():
        card2.click()
        page.wait_for_timeout(350)
        if page.evaluate("() => !document.getElementById('sncImgBar').hidden"):
            page.click('#sncImgBar button[data-act="edit"]')
            page.wait_for_timeout(350)
    opened_light = page.evaluate("() => !document.getElementById('sncCompose').hidden")
    check("亮色下编辑面板可正常打开", opened_light)
    if opened_light:
        colors = page.evaluate("""() => ({
            bg: getComputedStyle(document.getElementById('sncCompose')).backgroundColor,
            ink: getComputedStyle(document.getElementById('sncComposeInput')).color,
            slot: getComputedStyle(document.querySelector('.snc-att-slot')).borderColor
        })""")
        def lum(rgb):
            parts = rgb.replace("rgba(", "").replace("rgb(", "").replace(")", "").split(",")[:3]
            v = [float(x.strip()) for x in parts]
            return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
        check("亮色下面板浅底深字（对比度足够）",
              lum(colors["bg"]) > 150 and lum(colors["ink"]) < 120, colors)
        page.screenshot(path=os.path.join(SHOTS, "v22-编辑面板-亮色主题.png"), full_page=False)

    ctx.close()
    br.close()

passed = sum(1 for _, ok in results if ok)
print("\n%d / %d 通过" % (passed, len(results)))
sys.exit(0 if passed == len(results) else 1)
