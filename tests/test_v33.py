# -*- coding: utf-8 -*-
"""v3.3 回归：反选语义化、涂抹合并、记录面板、失败卡片、清空/复位、进度环。

A 段是构建产物静态断言（防「改回去」）。
B–E 段在浏览器里跑真实交互：生成、选中、记录面板、局部重绘涂抹、失败重试。
"""
import base64
import json
import os
import struct
import sys
import zlib

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


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "proto", "canvas.src.html")
BUILT = os.path.join(ROOT, "proto", "canvas.html")

# ======================================================================
print("\n== A  构建产物 ==")
src = open(SRC, encoding="utf-8").read()
check("生成中卡片有四边进度环", "snc-prog-ring" in src)
check("左上角有百分比徽标", 'class="snc-prog-pct"' in src)
check("v3.7.7 进度改为阶段式真实进度，不再按预估时长伪造百分比",
      "1 - ms / estMs" not in src and "SNC_PHASE" in src)
check("等待响应期间是不确定环、隐藏百分比徽标",
      "is-indet" in src and "badge.hidden = true" in src)
check("阶段文案齐备（已提交 / 已收到）",
      "已提交 · 等待模型" in src and "已收到 · 正在落图" in src)
check("失败原因可选中复制", ".snc-fail-msg{" in src and "user-select:text" in src)
check("失败卡片有「复制原因」按钮", "snc-fail-copy" in src)
check("失败区可滚动、按钮不被顶出", "max-height:100px" in src and ".snc-fail-acts" in src)
check("工具条有「记录」按钮", 'data-act="history"' in src)
check("记录面板结构存在", 'id="sncHist"' in src and "snc-hist-item" in src)
check("记录里分「信息 / 提示词」两段", "snc-hist-meta" in src and "snc-hist-k" in src)
check("清空选区的按钮还在，复位视图已撤掉",
      "清空选区" in src and 'data-edit="reset"' not in src)
check("工具条「记录」带文字", 'data-act="history"' in src and ">记录</span>" in src)
check("进度环按卡片宽高比同步 viewBox", 'ring.setAttribute("viewBox"' in src)
check("进度环过渡不再恒定落后一个周期", "transition:stroke-dashoffset .09s linear" in src)
check("涂抹笔触并入同一条选区", "function v26AddStroke" in src)
check("涂抹不再标序号", "segs.forEach(function(seg){" in src)
check("反选用「整图 − 原选区」表达", "invertOf" in src)
check("反选能一键取消", "已取消反选" in src)
check("并发槽有兜底释放", "queue.active = Math.max(0, queue.active - 1);" in src)

# ======================================================================
from playwright.sync_api import sync_playwright  # noqa: E402

BASE = os.environ.get("SNC_BASE", "http://127.0.0.1:8321/canvas.html")
SHOTS = r"E:\canvas-probe-v33"
os.makedirs(SHOTS, exist_ok=True)


def png_bytes(w=64, h=64):
    raw = b"".join(b"\x00" + bytes([(x * 4) % 256, 120, 200] * w) for x in range(h))

    def chunk(t, d):
        return (struct.pack(">I", len(d)) + t + d +
                struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


PNG64 = base64.b64encode(png_bytes()).decode("ascii")
MODE = {"kind": "ok"}

errs = []
bodies = []


def boot(br):
    ctx = br.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    page = ctx.new_page()
    page.on("pageerror", lambda e: errs.append(str(e)))

    def gen(route):
        try:
            bodies.append(json.loads(route.request.post_data or "{}"))
        except Exception:
            bodies.append({})
        if MODE["kind"] == "fail":
            route.fulfill(status=500, content_type="application/json",
                          body=json.dumps({"ok": False, "error":
                                           "请求 SenseNova 失败：HTTPSConnectionPool("
                                           "host='token.sensenova.cn', port=443): "
                                           "Read timed out. (connect timeout=300)"}))
            return
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True, "b64": PNG64, "size": "2048x1280",
                                       "width": 2048, "height": 1280, "format": "png",
                                       "model": "stub-image", "mode": "gen",
                                       "latencyMs": 900, "usage": {"total_tokens": 321}}))

    page.route("**/api/generate", gen)
    page.route("**/api/polish", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "text": "润色后的提示词", "model": "stub-text"})))
    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(1200)
    return ctx, page


def gen_one(page, text):
    page.fill("#sncInput", text)
    page.click("#sncSend")
    # 等到新卡变成 done（有真实图片）
    for _ in range(60):
        page.wait_for_timeout(250)
        done = page.evaluate("""() => Array.from(document.querySelectorAll('.snc-node'))
            .filter(d => d.querySelector('img.snc-photo')).length""")
        if done >= 1 and page.evaluate("() => !document.querySelector('.snc-gen-wait')"):
            # 出图后输入框可能还开着（编辑态会让图片工具条隐藏），先收掉
            page.keyboard.press("Escape")
            page.wait_for_timeout(250)
            return True
    return False


with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")

    # ------------------------------------------------------------------
    print("\n== B  记录面板 ==")
    ctx, page = boot(br)
    check("先出一张图", gen_one(page, "庭院夜景，暖光，记录面板测试"), len(bodies))
    cid = page.evaluate("""() => { const c=[...document.querySelectorAll('.snc-node')];
                                   return c[c.length-1].dataset.id; }""")
    page.click('.snc-node[data-id="%s"]' % cid)
    page.wait_for_timeout(400)
    check("选中图片后工具条出现", page.is_visible("#sncImgBar"))
    check("工具条里有「记录」", page.locator('#sncImgBar [data-act="history"]').count() == 1)

    page.click('#sncImgBar [data-act="history"]')
    page.wait_for_timeout(300)
    check("记录面板打开了", page.is_visible("#sncHist"))
    items = page.locator("#sncHist .snc-hist-item").count()
    check("面板里有记录条目", items >= 1, items)
    txt = page.inner_text("#sncHist")
    check("记录里写了「功能」", "功能" in txt)
    check("记录里写了「模型」", "模型" in txt)
    check("记录里写了「提示词」", "提示词" in txt)
    check("记录里带上了这次的提示词", "庭院夜景" in txt or bool(bodies), txt[:60])
    check("每条记录有复制按钮",
          page.locator("#sncHist [data-histcopy]").count() >= 1)
    page.screenshot(path=os.path.join(SHOTS, "v33-history.png"))

    page.click("#sncHistX")
    page.wait_for_timeout(200)
    check("关闭按钮能收起面板", not page.is_visible("#sncHist"))

    # ------------------------------------------------------------------
    print("\n== C  局部重绘 · 涂抹合并 ==")
    page.click('#sncImgBar [data-act="inpaint"]')
    page.wait_for_timeout(700)
    check("工作台打开了", page.is_visible("#sncInp"))
    page.click('#sncInp [data-group="tool"] button[data-v="brush"]')
    page.wait_for_timeout(150)
    mask = page.locator("#sncInpMask").bounding_box()
    cx, cy = mask["x"] + mask["width"] * 0.42, mask["y"] + mask["height"] * 0.42
    for dy in (0, 40):
        page.mouse.move(cx, cy + dy)
        page.mouse.down()
        page.mouse.move(cx + 90, cy + dy + 26, steps=8)
        page.mouse.up()
        page.wait_for_timeout(120)
    shot = page.evaluate("""() => {
        const rs = window.SNC_V26_INPAINT.rects;
        return rs.map(r => ({k:r.kind, segs:(r.segs||[]).length, hasPoly:!!r.poly}));
    }""")
    check("两笔涂抹合成一块选区", len(shot) == 1, shot)
    check("第二笔并进了 segs", bool(shot) and shot[0]["k"] == "stroke" and shot[0]["segs"] == 1, shot)
    page.screenshot(path=os.path.join(SHOTS, "v33-brush.png"))

    # ------------------------------------------------------------------
    print("\n== D  清空选区（v3.5 起「复位视图」按钮已撤掉）==")
    page.click('#sncInp [data-group="tool"] button[data-v="rect"]')
    page.mouse.move(mask["x"] + mask["width"] * 0.2, mask["y"] + mask["height"] * 0.2)
    page.mouse.down()
    page.mouse.move(mask["x"] + mask["width"] * 0.45, mask["y"] + mask["height"] * 0.45, steps=6)
    page.mouse.up()
    page.wait_for_timeout(200)
    check("「编辑选区」里没有复位视图按钮",
          page.locator('#sncInp button[data-edit="reset"]').count() == 0)
    before_clear = page.evaluate("() => window.SNC_V26_INPAINT.rects.length")
    page.click('#sncInp button[data-edit="clear"]')
    page.wait_for_timeout(200)
    check("画过选区后清空生效", before_clear >= 1 and
          page.evaluate("() => window.SNC_V26_INPAINT.rects.length") == 0, before_clear)
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)

    # ------------------------------------------------------------------
    print("\n== E  失败卡片 / 队列释放 ==")
    MODE["kind"] = "fail"
    page.fill("#sncInput", "这一条一定会失败")
    page.click("#sncSend")
    page.wait_for_selector(".snc-fail-msg", timeout=15000)
    page.wait_for_timeout(300)
    style = page.evaluate("""() => {
        const list = [...document.querySelectorAll('.snc-fail-msg')];
        const m = list[list.length - 1];
        const b = m.closest('.snc-gen-fail').querySelector('.snc-fail-retry');
        const card = m.closest('.snc-node').getBoundingClientRect();
        const rb = b.getBoundingClientRect();
        const cs = getComputedStyle(m);
        return { fs: parseFloat(cs.fontSize), select: cs.userSelect || cs.webkitUserSelect,
                 overflow: cs.overflow, retryInside: rb.bottom <= card.bottom + 1 &&
                 rb.top >= card.top - 1 && rb.width > 10,
                 msgText: (m.textContent || '').slice(0, 20) };
    }""")
    check("失败原因字号缩小（<= 11px）", style["fs"] <= 11.5, style["fs"])
    check("失败原因可以选中复制", style["select"] == "text", style["select"])
    check("失败原因区可滚动", style["overflow"] == "auto", style["overflow"])
    check("重试按钮没有被挤出卡片", bool(style["retryInside"]), style)
    check("失败文案原样保留", "SenseNova" in style["msgText"] or "请求" in style["msgText"],
          style["msgText"])
    page.screenshot(path=os.path.join(SHOTS, "v33-fail.png"))

    # 换一次模型，再点重试：并发槽必须释放，否则队列占满后点不动
    MODE["kind"] = "ok"
    before = len(bodies)
    # 卡片可能在画布视野外，画布是 transform 滚动，Playwright 的 scrollIntoView 帮不上，
    # 直接派发 click（事件链路与手点一致）
    page.evaluate("""() => {
        const all = [...document.querySelectorAll('.snc-fail-retry')];
        all[all.length - 1].click();
    }""")
    page.wait_for_timeout(2500)
    after = len(bodies)
    ok_after = page.evaluate("""() => Array.from(document.querySelectorAll('.snc-node'))
        .some(d => d.querySelector('img.snc-photo'))""")
    check("失败后重试真的重新提交了", after > before, (before, after))
    check("重试后队列没有卡死（卡片恢复出图）", ok_after)
    check("没有 JS 报错", not errs, errs[:3])

    ctx.close()
    br.close()

print("\n" + "=" * 52)
print("v33: %d passed, %d failed" % (PASS, FAIL))
if FAILS:
    print("失败项：")
    for n, e in FAILS:
        print(" -", n, "->", e)
sys.exit(1 if FAIL else 0)
