# -*- coding: utf-8 -*-
"""v2.7 回归：整理画布布局 / 多边形套索 / 关闭按钮 / B1 分片读回 / 导出落盘回退。

跑法：先 `python tests/serve.py`（8321），再 `python tests/test_v27_fixes.py`
"""
import base64
import json
import os
import random
import struct
import sys
import zlib

from playwright.sync_api import sync_playwright

BASE = os.environ.get("SNC_BASE", "http://127.0.0.1:8321/canvas.html")
SHOTS = r"E:\canvas-probe2\shots-v27"
os.makedirs(SHOTS, exist_ok=True)

passed = 0
failed = []


def check(name, cond, extra=""):
    global passed
    if cond:
        passed += 1
        print("PASS", name)
    else:
        failed.append(name)
        print("FAIL", name, "->", extra)


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


# 噪声图压缩后仍远大于 20KB，B1 才会真的把它外置成分片
PIC = "data:image/png;base64," + base64.b64encode(png(560, 420, noise=True)).decode("ascii")

errs = []
bodies = []

with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    ctx = br.new_context(viewport={"width": 1560, "height": 940}, accept_downloads=True)
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    page = ctx.new_page()

    page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))

    def stub(route):
        try:
            bodies.append(json.loads(route.request.post_data or "{}"))
        except Exception:
            bodies.append({})
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True, "b64": PIC.split(",")[1],
                                       "size": "560x420"}))

    page.route("**/api/generate", stub)

    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(900)

    # ============ A. 关闭按钮几何 ============
    def make_card(tag):
        page.fill("#sncInput", tag)
        page.click("#sncSend")
        page.wait_for_timeout(900)
        return page.evaluate("""() => { const c=[...document.querySelectorAll('.snc-node')];
                                       return c[c.length-1].dataset.id; }""")

    def open_inpaint(cid):
        page.click('.snc-node[data-id="%s"]' % cid)
        page.wait_for_timeout(200)
        page.click('#sncImgBar button[data-act="inpaint"]')
        page.wait_for_timeout(500)

    cid = make_card("v27 主图")
    open_inpaint(cid)
    check("工作台已打开", page.evaluate("() => !document.getElementById('sncInp').hidden"))

    geo = page.evaluate("""() => {
        const x = document.getElementById('sncInpX').getBoundingClientRect();
        const d = document.getElementById('sncInp').getBoundingClientRect();
        const h4 = document.querySelector('#sncInp .snc-inp-sec h4').getBoundingClientRect();
        const cx = Math.round(x.left + x.width/2), cy = Math.round(x.top + x.height/2);
        const hit = document.elementFromPoint(cx, cy);
        const overlap = !(x.bottom <= h4.top || x.top >= h4.bottom ||
                          x.right <= h4.left || x.left >= h4.right);
        return {
            inside: x.left >= d.left && x.right <= d.right && x.top >= d.top && x.bottom <= d.bottom,
            overlap: overlap,
            hit: hit ? (hit.id || hit.className) : null,
            gapTop: Math.round(h4.top - x.bottom),
            xRight: Math.round(d.right - x.right)
        };
    }""")
    check("关闭按钮完整落在工作台内", geo["inside"], geo)
    check("关闭按钮压住第一个分组标题", not geo["overlap"], geo)
    check("关闭按钮在右上角（距右边 < 24px）", 0 <= geo["xRight"] <= 24, geo)
    check("关闭按钮可点中（命中自身）", geo["hit"] == "sncInpX", geo)

    page.click("#sncInpX")
    page.wait_for_timeout(300)
    check("点 × 关闭工作台", page.evaluate("() => document.getElementById('sncInp').hidden"))

    # ============ B. 多边形套索 ============
    open_inpaint(cid)
    page.click('#sncInp [data-group="tool"] button[data-v="lasso"]')
    page.wait_for_timeout(150)
    box = page.locator("#sncInpMask").bounding_box()

    def click_at(fx, fy):
        page.mouse.click(box["x"] + box["width"] * fx, box["y"] + box["height"] * fy)
        page.wait_for_timeout(90)

    pts = [(0.20, 0.20), (0.62, 0.22), (0.66, 0.60), (0.24, 0.58)]
    for (fx, fy) in pts:
        click_at(fx, fy)
    state1 = page.evaluate("""() => {
        const v = window.SNC_V26_INPAINT;
        return {pending: v.pending ? v.pending.length : 0,
                rects: v.rects.length};
    }""")
    check("多边形套索：逐个落点累积顶点", state1["pending"] == 4, state1)
    check("多边形：落点过程中还不生成选区", state1["rects"] == 0, state1)

    click_at(0.20, 0.20)          # 回到起点 → 闭合
    state2 = page.evaluate("""() => {
        const v = window.SNC_V26_INPAINT;
        const r = v.rects[0] || {};
        return {pending: v.pending ? v.pending.length : 0,
                rects: v.rects.length, kind: r.kind,
                verts: (r.poly || []).length,
                w: Math.round((r.w||0)*100), h: Math.round((r.h||0)*100)};
    }""")
    check("点回起点闭合多边形", state2["rects"] == 1 and state2["pending"] == 0, state2)
    check("选区类型是多边形", state2["kind"] == "poly", state2)
    check("多边形顶点数正确（4 个）", state2["verts"] == 4, state2)
    check("多边形包围盒覆盖四角", state2["w"] >= 35 and state2["h"] >= 30, state2)

    # 双击闭合
    for (fx, fy) in [(0.10, 0.70), (0.40, 0.72), (0.40, 0.90)]:
        click_at(fx, fy)
    page.mouse.dblclick(box["x"] + box["width"] * 0.10, box["y"] + box["height"] * 0.80)
    page.wait_for_timeout(300)
    r2 = page.evaluate("() => window.SNC_V26_INPAINT.rects.length")
    check("双击也能闭合多边形", r2 >= 2, r2)

    # Esc 优先取消未完成的多边形
    before = page.evaluate("() => window.SNC_V26_INPAINT.rects.length")
    click_at(0.75, 0.30)
    click_at(0.85, 0.45)
    page.keyboard.press("Escape")
    page.wait_for_timeout(250)
    after = page.evaluate("""() => ({rects: window.SNC_V26_INPAINT.rects.length,
                                     pending: window.SNC_V26_INPAINT.pending,
                                     hidden: document.getElementById('sncInp').hidden})""")
    check("Esc 先撤销未完成的多边形", after["pending"] in (None, []) and after["rects"] == before, after)
    check("撤销多边形时工作台仍开着", after["hidden"] is False, after)

    page.keyboard.press("Escape")
    page.wait_for_timeout(250)
    check("再按 Esc 才关闭工作台", page.evaluate("() => document.getElementById('sncInp').hidden"))

    # ============ C. 其它选区工具仍可用 ============
    open_inpaint(cid)
    page.click('#sncInp button[data-edit="clear"]')   # 上一次关闭时把选区存进了 n.masks
    page.wait_for_timeout(150)

    def drag(fx0, fy0, fx1, fy1):
        b = page.locator("#sncInpMask").bounding_box()
        page.mouse.move(b["x"] + b["width"] * fx0, b["y"] + b["height"] * fy0)
        page.mouse.down()
        page.mouse.move(b["x"] + b["width"] * fx1, b["y"] + b["height"] * fy1, steps=10)
        page.mouse.up()
        page.wait_for_timeout(200)

    def rects():
        return page.evaluate("() => window.SNC_V26_INPAINT.rects.length")

    page.click('#sncInp [data-group="tool"] button[data-v="rect"]')
    drag(0.2, 0.2, 0.55, 0.55)
    check("矩形工具可用", rects() == 1, rects())

    page.click('#sncInp [data-group="tool"] button[data-v="lasso"]')
    drag(0.05, 0.05, 0.35, 0.30)
    check("自由套索（拖拽）仍可用", rects() == 2, rects())
    k2 = page.evaluate("""() => { const r = window.SNC_V26_INPAINT.rects[1];
                                   return {kind: r.kind, v: (r.poly||[]).length}; }""")
    check("自由套索也记成多边形（保留轨迹）", k2["kind"] == "poly" and k2["v"] >= 5, k2)

    page.click('#sncInp [data-group="tool"] button[data-v="brush"]')
    drag(0.62, 0.62, 0.76, 0.76)
    check("涂抹工具可用", rects() == 3, rects())

    page.click('#sncInp [data-group="tool"] button[data-v="eraser"]')
    b = page.locator("#sncInpMask").bounding_box()
    page.mouse.click(b["x"] + b["width"] * 0.69, b["y"] + b["height"] * 0.69)
    page.wait_for_timeout(250)
    kinds_after = page.evaluate("() => window.SNC_V26_INPAINT.rects.map(r => r.kind)")
    check("橡皮擦从选区里减掉刷过的部分（不误删整块）",
          len([k for k in kinds_after if k != "stroke"]) == 2, kinds_after)

    # v3.7.7：识别工具已按反馈移除
    check("识别按钮已移除",
          page.locator('#sncInp [data-group="tool"] button[data-v="detect"]').count() == 0)

    page.click('#sncInp button[data-edit="invert"]')
    check("反选可用", 0 <= rects() <= 4, rects())
    page.click('#sncInp button[data-edit="clear"]')
    check("清空可用", rects() == 0)

    # 提交一次，确认多边形也能走通
    page.click('#sncInp [data-group="tool"] button[data-v="lasso"]')
    for (fx, fy) in [(0.25, 0.25), (0.60, 0.25), (0.60, 0.60), (0.25, 0.60)]:
        click_at(fx, fy)
    click_at(0.25, 0.25)
    page.fill("#sncInpPrompt", "多边形选区换成浅色石材")
    n_before = page.locator(".snc-node").count()
    n_body = len(bodies)
    page.click("#sncInpGo")
    page.wait_for_timeout(4200)
    check("多边形选区可提交", page.locator(".snc-node").count() == n_before + 1,
          (n_before, page.locator(".snc-node").count()))
    check("多边形提交走 /images/edits", len(bodies) > n_body and
          len((bodies[-1].get("images") or [])) == 2,
          {"bodies": len(bodies), "before": n_body,
           "last": list(bodies[-1].keys()) if bodies else None,
           "imgs": len((bodies[-1].get("images") or [])) if bodies else -1})

    # ============ D. 整理画布 ============
    # 底部「1 2 3」已删（一句话一张才是实际用法），批量铺卡走测试钩子
    page.evaluate("() => window.SNC_TEST_API.spawn('v27 批量一', 3)")
    page.wait_for_timeout(900)
    page.evaluate("() => window.SNC_TEST_API.spawn('v27 批量二', 3)")
    page.wait_for_timeout(900)

    total = page.locator(".snc-node").count()
    check("整理前有足够多的卡片", total >= 10, total)

    page.click("#sncTidyBtn")
    page.wait_for_timeout(800)

    lay = page.evaluate("""() => {
        const s = document.getElementById('sncStage').getBoundingClientRect();
        const ns = [...document.querySelectorAll('.snc-node')].map(n => {
            const r = n.getBoundingClientRect();
            return {x: r.left - s.left, y: r.top - s.top, r: r.right - s.left, b: r.bottom - s.top};
        });
        const rows = new Set(ns.map(n => Math.round(n.y / 8)));
        const minX = Math.min(...ns.map(n => n.x));
        const maxR = Math.max(...ns.map(n => n.r));
        const minY = Math.min(...ns.map(n => n.y));
        return {rows: rows.size, minX: Math.round(minX),
                leftGap: Math.round(minX), rightGap: Math.round(s.width - maxR),
                topGap: Math.round(minY), stageW: Math.round(s.width),
                inView: ns.filter(n => n.x >= -2 && n.r <= s.width + 2 &&
                                       n.y >= -2 && n.b <= s.height + 2).length,
                total: ns.length};
    }""")
    check("整理后自动折行（不止一行）", lay["rows"] >= 2, lay)
    check("整理后所有卡片都在视口内", lay["inView"] == lay["total"], lay)
    check("左侧留白合理（不再被 280 顶开）", 40 <= lay["leftGap"] <= 200, lay)
    check("左右留白大致均衡", abs(lay["leftGap"] - lay["rightGap"]) <= 110, lay)
    page.screenshot(path=os.path.join(SHOTS, "v27-tidy-fixed.png"))

    # ============ E. B1 分片：读回后图片不丢 ============
    page.wait_for_timeout(1400)          # 等自动保存
    idb = page.evaluate("""() => new Promise((resolve) => {
        const q = indexedDB.open('sensenova-canvas', 3);
        q.onsuccess = () => {
            const db = q.result;
            const tx = db.transaction(['boards','chunks'], 'readonly');
            const bq = tx.objectStore('boards').getAll();
            const cq = tx.objectStore('chunks').getAll();
            tx.oncomplete = () => {
                const keys = new Set((cq.result || []).map(c => c.id));
                let refs = 0, dangling = 0, verRefs = 0, verDangling = 0;
                (bq.result || []).forEach(b => (b.nodes || []).forEach(n => {
                    if (n.__imgChunk) { refs++; if (!keys.has(n.__imgChunk)) dangling++; }
                    (n.versions || []).forEach(v => {
                        if (v.__imgChunk) { verRefs++; if (!keys.has(v.__imgChunk)) verDangling++; }
                    });
                }));
                resolve({refs: refs, dangling: dangling,
                         verRefs: verRefs, verDangling: verDangling,
                         chunks: keys.size});
            };
        };
    })""")
    check("B1 · 确实产生了分片", idb["chunks"] > 0 and idb["refs"] > 0, idb)
    check("B1 · 节点分片引用无悬空", idb["dangling"] == 0, idb)
    check("B1 · 版本分片引用无悬空", idb["verDangling"] == 0, idb)

    before_reload = page.evaluate("""() => [...document.querySelectorAll('.snc-node img')]
        .filter(i => i.getAttribute('src')).length""")
    page.reload()
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(1800)
    after_reload = page.evaluate("""() => {
        const imgs = [...document.querySelectorAll('.snc-node img')];
        return {withSrc: imgs.filter(i => i.getAttribute('src')).length,
                loaded: imgs.filter(i => i.complete && i.naturalWidth > 0).length,
                total: imgs.length};
    }""")
    check("B1 · 刷新后图片仍在", after_reload["withSrc"] >= max(1, before_reload - 1), after_reload)
    check("B1 · 刷新后图片能解码显示", after_reload["loaded"] >= 1, after_reload)

    # ============ F. 导出：优先系统另存为，取不到就回退下载 ============
    # 这里用 route 拦下 /api/save-file，既能断言两条分支，也避免打包版真的弹窗。
    saved = []
    page.route("**/api/save-file", lambda r: saved.append(json.loads(r.request.post_data or "{}"))
               or r.fulfill(status=200, content_type="application/json",
                            body=json.dumps({"ok": True, "path": r"C:\导出\测试.png"})))
    page.wait_for_timeout(200)

    gid = page.evaluate("""() => { const n = [...document.querySelectorAll('.snc-node')]
        .find(x => x.querySelector('img'));
        return n ? n.dataset.id : ''; }""")
    page.click('.snc-node[data-id="%s"]' % gid)
    page.wait_for_timeout(200)
    page.click("#sncExportOpen")
    page.click('#sncExportMenu button[data-exp="node"]')
    page.wait_for_timeout(1200)
    check("导出先交给系统另存为接口", len(saved) >= 1, saved[:1])
    check("导出请求带文件名与真实字节",
          bool(saved) and saved[-1].get("name", "").lower().endswith(".png") and
          len(saved[-1].get("b64") or "") > 100,
          {k: (v[:24] if isinstance(v, str) else v) for k, v in (saved[-1] if saved else {}).items()})
    toast_txt = page.evaluate("""() => {
        const t = document.querySelector('.snc-toast, #sncToast');
        return t ? t.textContent : '';
    }""")
    check("保存成功后提示了保存路径", "已保存到" in toast_txt or "测试.png" in toast_txt, toast_txt)

    # 服务端说不行 → 必须回退成浏览器下载，不能静默失败
    page.unroute("**/api/save-file")
    page.route("**/api/save-file", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": False, "error": "当前运行方式不支持系统另存为窗口"})))
    page.wait_for_timeout(150)
    with page.expect_download(timeout=20000) as dl:
        page.click("#sncExportOpen")
        page.click('#sncExportMenu button[data-exp="node"]')
    d = dl.value
    check("接口不可用时回退浏览器下载", bool(d.suggested_filename), d.suggested_filename if d else "")
    check("回退下载的文件名带 .png", d.suggested_filename.lower().endswith(".png"),
          d.suggested_filename if d else "")

    check("全程无 JS 报错", not errs, errs[:4])

    ctx.close()
    br.close()

print()
print("=" * 46)
print("%d / %d 通过" % (passed, passed + len(failed)))
if failed:
    print("失败项：")
    for f in failed:
        print(" -", f)
    sys.exit(1)
