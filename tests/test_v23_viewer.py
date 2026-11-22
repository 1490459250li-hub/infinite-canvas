# -*- coding: utf-8 -*-
"""v2.3 回归：双击画布图片 → 弹出放大预览窗口。

覆盖：显示原图（不是 P0 的 1280 缩略图）、滚轮缩放 / 拖动平移 / 1:1 / 适应窗口、
左右翻图、三种关闭方式、点图片本身不误关、模态键盘拦截、双击空白仍能新建笔记、
亮色主题下的可读性、下载原图的文件名与格式。
全程走网络存根，不消耗出图额度。
"""
import base64
import json
import os
import random
import re
import struct
import sys
import zlib
from playwright.sync_api import sync_playwright

BASE = os.environ.get("SNC_BASE", "http://127.0.0.1:8321/canvas.html")
TMP = r"E:\canvas-probe2\tmp\v23"
SHOTS = r"E:\canvas-probe2\shots-v23-viewer"
os.makedirs(TMP, exist_ok=True)
os.makedirs(SHOTS, exist_ok=True)

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + (("  | " + str(detail)) if detail else ""))


def chunk(t, d):
    c = t + d
    return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)


def png_bytes(w, h):
    row = bytes([190, 120, 90]) * w
    raw = b"".join(b"\x00" + row for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def noise_png_bytes(w, h, step=16):
    """逐像素随机、每 16 行复用一次：体积约 300KB，能真正触发 P0 缩略图缓存
    （warmThumbs 会跳过 dataUrl 长度 < 40000 的小图）。"""
    rnd = random.Random(11)
    rows = [bytes(rnd.randrange(256) for _ in range(w * 3)) for _ in range(h // step + 1)]
    raw = b"".join(b"\x00" + rows[(y // step) % len(rows)] for y in range(h))
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    ctx = br.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    def gen(route):
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True,
                                       "b64": base64.b64encode(noise_png_bytes(1600, 1000)).decode("ascii"),
                                       "size": "1600x1000", "width": 1600, "height": 1000,
                                       "format": "png", "model": "stub-image", "mode": "gen",
                                       "latencyMs": 100, "usage": {}}))

    page.route("**/api/generate", gen)
    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(900)

    # 造一张 1600×1000 的大图卡片：P0 会给它生成 ≤1280 的 JPEG 缩略图，
    # 于是"预览显示原图"可以被严格断言（预览 PNG ≠ 卡片缩略图）。
    before_ids = page.evaluate(
        "() => Array.from(document.querySelectorAll('.snc-node')).map(d=>d.dataset.id)")
    page.fill("#sncInput", "预览测试原图")
    page.click("#sncSend")
    page.wait_for_timeout(2200)   # 等 P0 异步缩略图生成完
    new_id = page.evaluate("""(old) => {
        const cs = Array.from(document.querySelectorAll('.snc-node'));
        const n = cs.find(d => !old.includes(d.dataset.id));
        return n ? n.dataset.id : '';
    }""", before_ids)
    check("生成出 1600×1000 的原图卡片", bool(new_id), new_id)

    card_src = page.evaluate("""(id) => {
        const im = document.querySelector('.snc-node[data-id="'+id+'"] .snc-photo');
        return im ? im.src : '';
    }""", new_id)
    check("画布卡片用的是 P0 缩略图", card_src.startswith("data:image/jpeg"), card_src[:32])

    def tf():
        return page.evaluate("""() => {
            const s = document.getElementById('sncViewerImg').style.transform || '';
            const m = s.match(/scale\\(([-0-9.]+)\\)/);
            const t = s.match(/translate\\(([-0-9.]+)px,\\s*([-0-9.]+)px\\)/);
            const im = document.getElementById('sncViewerImg');
            return {scale: m ? parseFloat(m[1]) : 1,
                    x: t ? parseFloat(t[1]) : 0, y: t ? parseFloat(t[2]) : 0,
                    raw: im.classList.contains('is-raw'),
                    w: im.naturalWidth, h: im.naturalHeight,
                    src: im.getAttribute('src') || ''};
        }""")

    def open_it():
        page.locator('.snc-node[data-id="%s"] .snc-photo' % new_id).dblclick()
        page.wait_for_timeout(450)

    def is_open():
        return page.evaluate("() => !document.getElementById('sncViewer').hidden")

    # ---------- ① 双击打开 + 显示原图 ----------
    count_before = page.evaluate("() => document.querySelectorAll('.snc-node').length")
    open_it()
    check("双击图片卡片打开预览窗口", is_open())
    v0 = tf()
    check("预览载入的是 1600×1000 原图", v0["w"] == 1600 and v0["h"] == 1000, (v0["w"], v0["h"]))
    check("预览 src 是 PNG 原图而非画布缩略图",
          v0["src"].startswith("data:image/png") and v0["src"] != card_src, v0["src"][:36])
    info = page.locator("#sncViewerInfo").inner_text()
    check("信息栏显示真实尺寸与「画布原图」", "1600 × 1000" in info and "画布原图" in info, info)
    title = page.locator("#sncViewerTitle").inner_text()
    check("标题栏有卡片名", len(title) > 0 and title != "图片预览", title)
    cnt = page.locator("#sncViewerCount").inner_text()
    check("底部显示第几张 / 共几张", bool(re.search(r"\d+\s*/\s*\d+", cnt)), cnt)
    check("双击图片没有误建笔记", page.evaluate(
        "() => document.querySelectorAll('.snc-node').length") == count_before)
    page.screenshot(path=os.path.join(SHOTS, "v23-双击图片放大预览.png"), full_page=False)

    # ---------- ② 缩放 / 1:1 / 适应 / 平移 ----------
    stage_box = page.locator("#sncViewerStage").bounding_box()
    cx = stage_box["x"] + stage_box["width"] / 2
    cy = stage_box["y"] + stage_box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.wheel(0, -240)
    page.wait_for_timeout(160)
    check("滚轮向上放大（scale > 1）", tf()["scale"] > 1, tf()["scale"])
    page.mouse.wheel(0, 240)
    page.wait_for_timeout(160)
    check("滚轮向下缩小", tf()["scale"] < 1.01, tf()["scale"])
    page.click("#sncViewerFit")
    check("「适应窗口」把缩放复位", abs(tf()["scale"] - 1) < 1e-6, tf()["scale"])

    page.click("#sncViewerOne")
    raw = tf()
    cssw = page.evaluate("() => document.getElementById('sncViewerImg').style.width")
    check("「1:1」按原始像素显示", raw["raw"] and cssw == "1600px", (raw["raw"], cssw))
    page.click("#sncViewerOne")
    check("再点 1:1 回到适应窗口", not tf()["raw"])

    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + 90, cy + 50, steps=6)
    page.mouse.up()
    page.wait_for_timeout(120)
    check("拖动可平移图片", abs(tf()["x"]) > 30 and is_open(), (tf()["x"], tf()["y"]))
    page.click("#sncViewerFit")
    check("适应窗口同时复位平移", tf()["x"] == 0 and tf()["y"] == 0)

    # ---------- ③ 左右翻图 ----------
    src0 = tf()["src"]
    total = int(re.search(r"/\s*(\d+)", cnt).group(1))
    check("可切换的图片多于一张", total > 1, total)
    page.click("#sncViewerNext")
    page.wait_for_timeout(220)
    check("点「下一张」换了图", tf()["src"] != src0 and is_open())
    page.screenshot(path=os.path.join(SHOTS, "v23-预览-真实效果图.png"), full_page=False)
    cnt2 = page.locator("#sncViewerCount").inner_text()
    check("计数随切换更新", cnt2 != cnt, cnt2)
    page.keyboard.press("ArrowLeft")
    page.wait_for_timeout(220)
    check("键盘 ← 切回上一张", tf()["src"] == src0)
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(220)
    check("键盘 → 切到下一张", tf()["src"] != src0)

    # ---------- ④ 模态键盘拦截 ----------
    n_before = page.evaluate("() => document.querySelectorAll('.snc-node').length")
    page.keyboard.press("Delete")
    page.keyboard.press("t")
    page.wait_for_timeout(150)
    check("预览开着时 Delete / T 不作用到背后画布",
          page.evaluate("() => document.querySelectorAll('.snc-node').length") == n_before)

    # ---------- ⑤ 下载原图（此时停在切换后的那张，格式随图片走） ----------
    cur_src = tf()["src"]
    # 图片来源两种：data URL 和 /art/ 路径（内置示例照片）。两种都要按真实格式判。
    if cur_src.startswith("data:image/png"):
        want_ext = ".png"
    elif cur_src.startswith("data:image/jpeg"):
        want_ext = ".jpg"
    elif cur_src.startswith("/art/"):
        want_ext = "." + cur_src.split("?")[0].rsplit(".", 1)[-1].lower()
        if want_ext == ".jpeg":
            want_ext = ".jpg"
    else:
        want_ext = ".webp"
    dl = page.evaluate("""() => {
        const orig = HTMLAnchorElement.prototype.click;
        let got = null;
        HTMLAnchorElement.prototype.click = function(){
            // 存原始属性而不是 this.href：后者会被浏览器解析成绝对地址，
            // /art/ 这类相对路径就和 cur_src 对不上了
            got = {download: this.download, href: (this.href || '').slice(0, 30),
                   rel: this.getAttribute('href')};
        };
        document.getElementById('sncViewerSave').click();
        HTMLAnchorElement.prototype.click = orig;
        return got;
    }""")
    check("「下载原图」按当前图片格式生成下载链接",
          bool(dl) and dl["download"].endswith(want_ext) and dl["rel"] == cur_src,
          (want_ext, dl))

    # ---------- ⑥ 三种关闭方式 + 点图片不误关 ----------
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)
    check("Esc 关闭预览", not is_open())

    open_it()
    page.click("#sncViewerClose")
    page.wait_for_timeout(150)
    check("右上角 × 关闭预览", not is_open())

    open_it()
    # 图片 fit 后左右各有约 97px 留白，x+20 一定落在图片外
    blank_hit = page.evaluate("""(pt) => {
        const e = document.elementFromPoint(pt.x, pt.y);
        return e ? (e.id || e.className) : null;
    }""", {"x": stage_box["x"] + 20, "y": cy})
    check("图片外确实是可点击的空白区", blank_hit == "sncViewerCanvas", blank_hit)
    page.mouse.click(stage_box["x"] + 20, cy)
    page.wait_for_timeout(150)
    check("点击图片外空白处关闭预览", not is_open())

    open_it()
    page.locator("#sncViewerImg").click()
    page.wait_for_timeout(150)
    check("点击图片本身不会误关", is_open())
    page.click("#sncViewerClose")

    # ---------- ⑦ 原功能不退化：双击空白仍能新建笔记 ----------
    blank = page.evaluate("""() => {
        const st = document.getElementById('sncStage').getBoundingClientRect();
        for(let y = st.top + 60; y < st.bottom - 60; y += 18){
            for(let x = st.left + 60; x < st.right - 60; x += 18){
                const e = document.elementFromPoint(x, y);
                if(e && !e.closest('.snc-node, .snc-prompt, .snc-top, .snc-insp, .snc-rail, .snc-zoomer, .snc-imgbar, .snc-compose'))
                    return {x: x, y: y};
            }
        }
        return null;
    }""")
    check("找得到画布空白点", bool(blank), blank)
    if blank:
        n0 = page.evaluate("() => document.querySelectorAll('.snc-node').length")
        page.mouse.dblclick(blank["x"], blank["y"])
        page.wait_for_timeout(320)
        check("双击空白处仍新建笔记",
              page.evaluate("() => document.querySelectorAll('.snc-node').length") == n0 + 1)

    # ---------- ⑧ 亮色主题下预览依然清晰 ----------
    page.evaluate("() => { try{localStorage.setItem('snc.theme.v1','light')}catch(e){} }")
    page.reload()
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(900)
    check("亮色主题已生效",
          page.evaluate("() => document.getElementById('snc').getAttribute('data-theme')") == "light")
    # reload 后画布视角会被记下来、卡片可能整体滚出视口；真实双击已在暗色段验证过，
    # 这里只验样式，直接给图片派发 dblclick（事件链路与真实双击一致）。
    opened_light = page.evaluate("""() => {
        const im = document.querySelector('.snc-node .snc-photo');
        if(!im) return false;
        im.dispatchEvent(new MouseEvent('dblclick',
            {bubbles: true, cancelable: true, clientX: 0, clientY: 0}));
        return !document.getElementById('sncViewer').hidden;
    }""")
    page.wait_for_timeout(350)
    check("亮色主题下也能双击打开预览", opened_light and is_open())
    colors = page.evaluate("""() => ({
        bg: getComputedStyle(document.getElementById('sncViewer')).backgroundColor,
        ink: getComputedStyle(document.getElementById('sncViewerTitle')).color
    })""")

    def lum(rgb):
        v = [float(x.strip()) for x in
             rgb.replace("rgba(", "").replace("rgb(", "").replace(")", "").split(",")[:3]]
        return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]

    check("看图底始终是深色、文字浅色（对比度足够）",
          lum(colors["bg"]) < 60 and lum(colors["ink"]) > 150, colors)
    page.screenshot(path=os.path.join(SHOTS, "v23-亮色主题下的预览.png"), full_page=False)
    page.keyboard.press("Escape")

    check("全程无 JS 报错", not errs, errs[:3])

    ctx.close()
    br.close()

passed = sum(1 for _, ok in results if ok)
print("\n%d / %d 通过" % (passed, len(results)))
sys.exit(0 if passed == len(results) else 1)
