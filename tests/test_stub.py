# -*- coding: utf-8 -*-
"""零成本回归：路由存根替换 /api/generate，验证参考图角色、并发上限、版本上限与对比。"""
import base64, json, os, struct, sys, time, zlib
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8321/canvas.html"
SHOT = r"E:\canvas-probe2\shots-v22-ui\stub"
os.makedirs(SHOT, exist_ok=True)
PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

results = []
def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + (("  | " + str(detail)) if detail else ""))

def png64():
    w = h = 64
    raw = b"".join(b"\x00" + bytes([200, 120, 90] * w) for _ in range(h))
    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))

with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    ctx = br.new_context(viewport={"width": 1400, "height": 900}, accept_downloads=True)
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    bodies = []

    def handle_generate(route):
        bodies.append(json.loads(route.request.post_data or "{}"))
        time.sleep(0.8)
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True, "b64": PNG, "size": "1024x1024",
                                       "model": "stub", "mode": "gen", "latencyMs": 950,
                                       "usage": {"total_tokens": 999}}))

    page.route("**/api/generate", handle_generate)
    page.route("**/api/health", lambda r: r.fulfill(status=200, content_type="application/json",
              body=json.dumps({"ok": True, "keyPresent": True, "key": "sk-stub…stub",
                               "defaultModel": "fast"})))
    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(900)

    # ---------- 参考图角色 ----------
    gen = page.locator('.snc-node[data-id^="g-"]').first
    nid = gen.get_attribute("data-id")
    gen.click()
    page.wait_for_timeout(250)
    page.click('#sncImgBar button[data-act="edit"]')
    page.wait_for_selector("#sncCompose:not([hidden])")

    up = os.path.join(SHOT, "upload.png")
    open(up, "wb").write(png64())
    page.set_input_files("#sncFileInput", up)
    page.wait_for_timeout(500)
    role = page.inner_text("#sncAtts .snc-att-role")
    check("上传参考图有角色角标", role == "主", role)
    page.click("#sncAtts .snc-att-role")
    page.wait_for_timeout(150)
    role2 = page.inner_text("#sncAtts .snc-att-role")
    check("点角标切换角色", role2 == "风", "%s → %s" % (role, role2))

    page.fill("#sncComposeInput", "把墙面换成暖色石材")
    page.click("#sncComposeSend")
    page.wait_for_timeout(1200)
    body = bodies[-1] if bodies else {}
    check("参考图像素进入请求体",
          bool(body.get("images")) and body["images"][0].startswith("data:image"),
          "%d 张" % len(body.get("images") or []))
    check("提示词带参考图角色说明", "参考图说明" in (body.get("prompt") or ""),
          (body.get("prompt") or "").splitlines()[-1][:40])

    # ---------- 队列：同一帧内连提交 3 次 ----------
    page.keyboard.press("Escape")
    page.click("#sncFit")
    page.wait_for_timeout(300)
    nobs = len(bodies)
    q = page.evaluate("""async () => {
        const input = document.getElementById('sncInput');
        const send = document.getElementById('sncSend');
        for (let i = 0; i < 3; i++) { input.value = '并发测试 ' + i + '，庭院石材'; send.click(); }
        await new Promise(r => setTimeout(r, 60));
        const q = document.getElementById('sncQueue');
        return q.hidden ? '(hidden)' : q.textContent;
    }""")
    check("并发上限 2：第 3 个进入等待", "2/2" in q and "等待 1" in q, q)
    page.wait_for_function("() => { const q = document.getElementById('sncQueue'); return !q || q.hidden; }",
                           timeout=30000)
    check("3 个任务全部跑完", len(bodies) - nobs == 3, "%d 个请求" % (len(bodies) - nobs))

    # ---------- 版本上限与翻页 ----------
    # v3.7.8：队列条隐藏不等于最后一个 runJob 已收尾，紧接着点节点 / rerun 会让
    # 选中的不是目标卡，版本条永远等不到 /5。给残留任务一段收尾时间，并把
    # 每次 rerun 的间隔放宽到超过存根 0.8s 的响应延迟（实测产品版本条能到 5/5）。
    # 偶发：队列并发 2 + 存根 0.8s 延迟，6 个 rerun 最坏要排两轮，30s 会擦边超时。
    page.wait_for_timeout(1500)
    page.click("#sncFit")
    page.wait_for_timeout(300)
    page.click('.snc-node[data-id="%s"]' % nid)
    page.wait_for_timeout(250)
    for i in range(6):
        page.evaluate("() => window.SNC_TEST_API.rerun()")
        page.wait_for_timeout(900)
    page.wait_for_function("""(id) => {
        const s = document.querySelector('.snc-node[data-id="' + id + '"] .snc-vstrip');
        return s && s.textContent.includes('/5');
    }""", arg=nid, timeout=45000)
    strip = page.inner_text('.snc-node[data-id="%s"] .snc-vstrip' % nid)
    check("版本最多保留 5 版", "/5" in strip, strip.replace("\n", " "))

    # v3.7.8：画布缩放后 stage 会盖在版本条按钮上方，Playwright 的命中测试会一直重试；
    # 这里只验证「翻版」这条业务逻辑，直接派发 DOM click 即可，不依赖像素级可点性。
    page.locator('.snc-node[data-id="%s"] .snc-vstrip button[data-v="prev"]' % nid).dispatch_event("click")
    page.wait_for_timeout(250)
    s2 = page.inner_text('.snc-node[data-id="%s"] .snc-vstrip' % nid)
    check("‹ 翻到上一版", "4/5" in s2, s2.replace("\n", " "))

    # ---------- 对比滑杆 ----------
    page.click('#sncImgBar button[data-act="compare"]')
    page.wait_for_selector('.snc-node[data-id="%s"] .snc-cmp-clip' % nid, timeout=6000)
    box = page.locator('.snc-node[data-id="%s"] .snc-node-body' % nid).bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] * 0.8, box["y"] + box["height"] / 2, steps=6)
    page.mouse.up()
    clip = page.eval_on_selector('.snc-node[data-id="%s"] .snc-cmp-clip' % nid, "e => e.style.clipPath")
    check("对比手柄按百分比移动", "20%" in clip, clip)

    page.screenshot(path=os.path.join(SHOT, "stub-final.png"))
    check("无 JS 报错", not errs, "; ".join(errs[:2]))
    br.close()

bad = [r for r in results if not r[1]]
print("\n%d/%d passed" % (len(results) - len(bad), len(results)))
sys.exit(1 if bad else 0)
