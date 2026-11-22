# -*- coding: utf-8 -*-
"""v2.1 修复回归：参考图规范化。

背景：4K/8K 放大派生出来的卡是 4096+ 的大 PNG，拿它当主编辑图会被上游
「单边 256–4096 / ≤10MB / 比例 ≤3:1」拒掉（400），界面上表现成
「编辑/技能没从原图派生，变成了重新生成」。

本测试用网络存根把指定尺寸的图塞进卡片，再从它派生，检查发出的
/api/generate 请求里 images[0] 是否已规范化，且仍然走 edits（带参考图）。
全部走存根，不消耗出图额度。
"""
import base64
import json
import os
import random
import struct
import sys
import zlib
from playwright.sync_api import sync_playwright

# 默认端口留给老用法，但在跑整套回归时用 SNC_BASE 指向当前那个桥接服务，
# 免得端口一变这三个文件就集体 ERR_CONNECTION_REFUSED。
BASE = os.environ.get("SNC_BASE") or "http://127.0.0.1:8321/canvas.html"
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + (("  | " + str(detail)) if detail else ""))


def png_bytes(w, h, noise=False):
    if noise:
        rnd = random.Random(42)
        raw = b"".join(b"\x00" + bytes(rnd.randrange(256) for _ in range(w * 3))
                       for _ in range(h))
    else:
        row = bytes([190, 120, 90]) * w
        raw = b"".join(b"\x00" + row for _ in range(h))

    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def dims(blob):
    """纯标准库读 PNG / JPEG 宽高。"""
    if blob[:8] == b"\x89PNG\r\n\x1a\n" and len(blob) >= 24:
        return struct.unpack(">II", blob[16:24])
    if blob[:2] == b"\xff\xd8":
        i = 2
        while i < len(blob) - 9:
            if blob[i] != 0xFF:
                i += 1
                continue
            m = blob[i + 1]
            if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                     0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", blob[i + 5:i + 9])
                return w, h
            if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7:
                i += 2
                continue
            seg = struct.unpack(">H", blob[i + 2:i + 4])[0]
            if seg < 2:
                break
            i += 2 + seg
    return 0, 0


def inspect(u):
    head, _, b64 = u.partition(",")
    blob = base64.b64decode(b64)
    w, h = dims(blob)
    return {"fmt": head[:24], "w": w, "h": h,
            "chars": len(u), "bytes": len(blob)}


def run_case(br, label, stub_png, expect_changed=True):
    bodies = []
    ctx = br.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))

    def gen(route):
        bodies.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True, "b64": base64.b64encode(stub_png).decode("ascii"),
                                       "size": "stub", "width": 1, "height": 1,
                                       "format": "png", "model": "stub-image", "mode": "gen",
                                       "latencyMs": 100, "usage": {}}))

    page.route("**/api/generate", gen)
    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(900)

    before_ids = page.evaluate("""() => Array.from(document.querySelectorAll('.snc-node')).map(d=>d.dataset.id)""")

    # 1) 底部输入框生成一张「大原图」卡片（默认会出 2 张，多选时工具条按设计隐藏）
    page.fill("#sncInput", "测试用原图")
    page.click("#sncSend")
    page.wait_for_timeout(1400)

    new_id = page.evaluate("""(old) => {
        const cs = Array.from(document.querySelectorAll('.snc-node'));
        const n = cs.find(d => !old.includes(d.dataset.id));
        return n ? n.dataset.id : '';
    }""", before_ids)

    # 2) 从这张卡派生（走编辑面板）
    if not new_id:
        check(label + "：生成出可编辑卡片", False, "找不到新卡")
        ctx.close()
        return
    card = page.locator('.snc-node[data-id="%s"]' % new_id)
    card.click()
    page.wait_for_timeout(400)
    bar = page.evaluate("""() => {
        const b = document.getElementById('sncImgBar');
        return {hidden: b ? b.hidden : null, rect: b ? Math.round(b.getBoundingClientRect().width) : 0};
    }""")
    if bar["hidden"]:
        print("      诊断：工具条未显示", bar, "卡片数",
              page.evaluate("() => document.querySelectorAll('.snc-node').length"))
        check(label + "：新卡可选中并出现图片工具条", False, bar)
        ctx.close()
        return
    page.click('#sncImgBar button[data-act="edit"]')
    page.wait_for_timeout(250)
    page.fill("#sncComposeInput", "把这张图改成清晨，保持机位与构图")
    page.click("#sncComposeSend")
    page.wait_for_timeout(1200)

    last = bodies[-1] if bodies else {}
    imgs = last.get("images") or []
    check(label + "：派生请求仍带 1 张参考图（走 edits 而非文生图）",
          len(imgs) == 1, len(imgs))
    check(label + "：sizeMode=auto（按原图比例出图）",
          last.get("sizeMode") == "auto", last.get("sizeMode"))
    if imgs:
        info = inspect(imgs[0])
        print("      原图:", inspect("data:image/png;base64," +
                                    base64.b64encode(stub_png).decode("ascii")))
        print("      提交:", info)
        check(label + "：参考图单边落在 256–4096",
              256 <= info["w"] <= 4096 and 256 <= info["h"] <= 4096, (info["w"], info["h"]))
        ratio = max(info["w"], info["h"]) / max(1, min(info["w"], info["h"]))
        check(label + "：参考图比例 ≤3:1", ratio <= 3.01 + 1e-9, round(ratio, 3))
        check(label + "：参考图体积 <8MB", info["chars"] < 8 * 1024 * 1024, info["chars"])
        if expect_changed:
            check(label + "：不合规原图被转成 JPEG",
                  info["fmt"].startswith("data:image/jpeg"), info["fmt"])
        else:
            check(label + "：合规图保持原样（不误伤）",
                  info["fmt"].startswith("data:image/png"), info["fmt"])
    else:
        check(label + "：参考图规范化后可解析", False, "无参考图")
    check(label + "：全程无 JS 报错", not errs, errs)
    ctx.close()


with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")

    print("\n=== A. 超尺寸大图（4200×2400 纯色 PNG）===")
    run_case(br, "A 超尺寸", png_bytes(4200, 2400), True)

    print("\n=== B. 超宽比例（5000×1000，5:1）===")
    run_case(br, "B 超比例", png_bytes(5000, 1000), True)

    print("\n=== C. 合规尺寸但体积过大（1600×900 噪声 PNG）===")
    run_case(br, "C 超体积", png_bytes(1600, 900, noise=True), True)

    print("\n=== D. 极小图（160×100，短边 <256）应放大到合规下限 ===")
    run_case(br, "D 过小图", png_bytes(160, 100), True)

    print("\n=== E. 合规小图（800×600）应原样发送，不误伤 ===")
    run_case(br, "E 合规小图", png_bytes(800, 600), False)

    br.close()

passed = sum(1 for _, ok in results if ok)
print("\n%d / %d 通过" % (passed, len(results)))
sys.exit(0 if passed == len(results) else 1)
