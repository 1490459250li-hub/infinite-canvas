# -*- coding: utf-8 -*-
"""第十批（v3.7.6 候选）自检：600 字润色 / 进度环四角 / 重新生成回填派生 /
编辑草稿 / logo 分级菜单 / 启动画面 logo。

跑法：
    python tests/serve.py                        # 另开一个终端，端口 8321
    python tests/probe_batch10.py http://127.0.0.1:8321

不打任何真实上游；/api/generate 全程走本地存根，不消耗额度。
"""
import json
import math
import os
import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8321"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = 0
FAIL = 0

PNG = ("data:image/png;base64,"
       "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAF"
       "AAH/q842iQAAAABJRU5ErkJggg==")
B64 = PNG.split(",", 1)[1]
GEN_OK = json.dumps({"ok": True, "b64": B64, "size": "1024x1024",
                     "width": 1024, "height": 1024, "format": "png",
                     "model": "stub", "provider": "sensenova", "latencyMs": 1})


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + "   -> " + repr(detail)[:400])


# ---------------------------------------------------------------- 服务端
def probe_server_side():
    print("== 润色：字数上限 600，其他规则不变 ==")
    sys.path.insert(0, os.path.join(ROOT, "proto"))
    import server
    src = open(os.path.join(ROOT, "proto", "server.py"), encoding="utf-8").read()

    check("系统规则写明 600 字以内", "长度控制在 600 字以内" in server.POLISH_SYSTEM)
    check("不再有 80–200 字旧上限", "80–200" not in server.POLISH_SYSTEM)
    check("其余硬性规则一条没少",
          all(k in server.POLISH_SYSTEM for k in
              ("只输出润色后的提示词本身", "完整保留用户原意", "不得新增用户没有提到的物体",
               "只改某处、其余保持不变", "画面感优先")))
    check("带图仍追加看图规则", "以画面为准" in server.polish_system(True))
    check("纯文本不带看图规则", "以画面为准" not in server.polish_system(False))
    check("chat/completions 输出预算跟到 1800", '"max_tokens": 1800' in src)
    check("Google 输出预算跟到 1800", '"maxOutputTokens": 1800' in src)
    check("空正文重试预算 2600", "call(0.7, 2600" in src)
    check("无图时 user.content 是纯字符串",
          server.polish_user_content("测试", []) == "测试")
    multi = server.polish_user_content("测试", [PNG])
    check("有图时文字段与图片段成对", isinstance(multi, list)
          and multi[-2].get("type") == "text"
          and multi[-1].get("type") == "image_url", multi)
    gp = server.polish_google_parts("S", "U", [PNG])
    check("Google 用 inline_data 且拆掉 data: 前缀",
          gp[-1]["inline_data"]["data"] == B64, gp[-1])

    print("== 启动画面：换回 app.ico ==")
    check("启动画面调用 LoadImageW 读 ico", "uico.LoadImageW(None, ico, 1, 48, 48, 0x0010)" in src)
    check("用 DrawIconEx 画到品牌位", "uico.DrawIconEx(hdc, 28, 26" in src)
    check("读完 ico 会 DestroyIcon", "uico.DestroyIcon(hicon)" in src)
    check("保留 ico 读不到时的手画回退", "g.Ellipse(hdc, 33, 44, 55, 56)" in src)
    # 光看源码不够：真按启动画面同样的参数加载一次，确认不会走回退分支
    try:
        import ctypes
        from ctypes import wintypes as wt
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT,
                                 ctypes.c_int, ctypes.c_int, wt.UINT]
        u.LoadImageW.restype = wt.HANDLE
        u.DestroyIcon.argtypes = [wt.HANDLE]
        h = u.LoadImageW(None, server._icon_path(), 1, 48, 48, 0x0010)
        check("按启动画面参数真能加载 app.ico", bool(h), server._icon_path())
        if h:
            u.DestroyIcon(h)
    except Exception as exc:
        check("按启动画面参数真能加载 app.ico", False, exc)


# ---------------------------------------------------------------- 界面
def probe_ui():
    gen_calls = []

    def route_gen(route):
        gen_calls.append(route.request.post_data or "")
        route.fulfill(status=200, content_type="application/json", body=GEN_OK)

    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge")
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
        pg = ctx.new_page()
        pg.route("**/api/generate", route_gen)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(BASE + "/canvas.html")
        pg.wait_for_selector(".snc-node:has(.snc-photo)")
        pg.wait_for_timeout(900)

        print("== 进度环：四角连续 ==")
        r99 = pg.evaluate("() => window.SNC_TEST_API.progressRing(99)")
        # v3.7.7：同心圆角，inset=2、r=R-inset=10（R 为卡片真实圆角 12）
        R, D, r = 12, 2, 10
        P = 2 * ((240 - 2 * D) + (160 - 2 * D)) - 8 * r + 2 * math.pi * r
        check("四角各一段 1/4 圆弧", r99["d"].count(" A10.00 10.00 0 0 1 ") == 4, r99["d"])
        check("起点仍在上边正中", r99["d"].startswith("M120.00 2.00 H228.00"), r99["d"])
        check("圆角与裁切同心（四角不再被削薄）",
              "A10.00 10.00 0 0 1 238.00 12.00" in r99["d"], r99["d"])
        check("周长含圆弧长度", abs(r99["perimeter"] - P) < 0.1, (r99["perimeter"], P))
        check("99% 只差 1%", abs(r99["drawn"] / P - 0.99) < 0.002, r99)
        pg.evaluate("() => { const h=document.getElementById('sncProbeRing'); if(h) h.remove(); }")

        print("== 左上角 logo 分级菜单 ==")
        ids = ["sncDocBrandBtn", "sncBrandBtn", "sncWinBrandBtn"]
        info = pg.evaluate("""(ids) => ids.map(id => {
          const b = document.getElementById(id);
          return b ? {id, tag: b.tagName,
                      src: (b.querySelector('img')||{}).getAttribute('src')||'',
                      brand: b.getAttribute('data-brand')} : null;
        })""", ids)
        check("三个 logo 按钮都在", all(info), info)
        check("都换成项目 app.ico", all(x and x["src"] == "/app.ico" for x in info), info)
        check("都是可点按钮", all(x and x["tag"] == "BUTTON" and x["brand"] for x in info), info)
        pg.locator("#sncDocBrandBtn").click()
        check("点 logo 弹出菜单", pg.locator("#sncBrandMenu").is_visible())
        check("菜单分「文件 / 应用」两组", pg.locator("#sncBrandMenu .snc-bm-cap").count() == 2)
        acts = pg.locator("#sncBrandMenu [data-bm]").evaluate_all(
            "els => els.map(e => e.getAttribute('data-bm'))")
        check("保存 / 插入图片 / 退出三项齐全", acts == ["save", "image", "quit"], acts)

        def open_menu():
            """logo 是 toggle：开着就别再点，否则会把菜单关掉。"""
            if not pg.locator("#sncBrandMenu").is_visible():
                pg.locator("#sncDocBrandBtn").click()

        pg.evaluate("() => window.SNC_TEST_API.dirty()")
        open_menu()
        pg.locator('#sncBrandMenu [data-bm="save"]').click()
        pg.wait_for_timeout(700)
        saved = pg.evaluate("() => (document.getElementById('sncBadge')||{}).textContent")
        check("菜单「保存」真落盘", saved == "已保存", saved)

        open_menu()
        with pg.expect_file_chooser(timeout=4000) as fc:
            pg.locator('#sncBrandMenu [data-bm="image"]').click()
        check("菜单「插入图片」唤起文件选择", fc.value is not None)

        open_menu()
        pg.locator('#sncBrandMenu [data-bm="quit"]').click()
        check("菜单「退出」弹保存确认", pg.locator("#sncQuit").is_visible())
        pg.locator('#sncQuit [data-act="cancel"]').click()
        check("点外面 / Esc 能收起菜单", not pg.locator("#sncBrandMenu").is_visible())

        print("== 编辑框草稿：关掉再打开还在 ==")
        card = pg.locator(".snc-node:has(.snc-photo)").first
        card.click()
        pg.wait_for_timeout(250)
        pg.locator('#sncImgBar button[data-act="edit"]').click()
        pg.wait_for_timeout(200)
        DRAFT = "第十批草稿自检：把水景改成清晨薄雾"
        pg.fill("#sncComposeInput", DRAFT)
        pg.evaluate("(u) => window.SNC_TEST_API.attach(u)", PNG)
        n1 = pg.locator("#sncAtts .snc-att").count()
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(200)
        check("Esc 关掉了编辑框", not pg.locator("#sncCompose").is_visible())
        pg.locator(".snc-node:has(.snc-photo)").first.click()
        pg.wait_for_timeout(200)
        pg.locator('#sncImgBar button[data-act="edit"]').click()
        pg.wait_for_timeout(200)
        check("再打开文字还在", pg.input_value("#sncComposeInput") == DRAFT,
              pg.input_value("#sncComposeInput"))
        n2 = pg.locator("#sncAtts .snc-att").count()
        check("再打开插入的图片还在", n1 >= 2 and n2 == n1, (n1, n2))

        print("== 重新生成：回填编辑框 + 派生新卡 ==")
        SUBMIT = "重新生成自检：保持视角，换成清晨光线"
        pg.fill("#sncComposeInput", SUBMIT)
        pg.evaluate("(u) => window.SNC_TEST_API.attach(u)", PNG)
        atts_sent = pg.locator("#sncAtts .snc-att").count()
        before = pg.evaluate("() => window.SNC_TEST_API.nodes().map(n => n.id)")
        pg.locator("#sncComposeSend").click()
        pg.wait_for_timeout(1600)
        after = pg.evaluate("() => window.SNC_TEST_API.nodes().map(n => n.id)")
        child_id = [i for i in after if i not in before]
        check("提交后派生出一张新卡", len(child_id) == 1, (before, after))
        child_id = child_id[0] if child_id else ""

        gen_calls.clear()
        pg.evaluate("""(id) => {
          const el = document.querySelector('.snc-node[data-id="' + id + '"]');
          if(el) el.click();
        }""", child_id)
        pg.wait_for_timeout(300)
        pg.locator('#sncImgBar button[data-act="regen"]').click()
        pg.wait_for_timeout(350)
        check("点重新生成不直接调模型", len(gen_calls) == 0, gen_calls)
        check("编辑框被打开", pg.locator("#sncCompose").is_visible())
        check("标题写明重新生成", "重新生成" in (pg.locator("#sncComposeTitle").inner_text()),
              pg.locator("#sncComposeTitle").inner_text())
        check("当时的文字回填了", pg.input_value("#sncComposeInput") == SUBMIT,
              pg.input_value("#sncComposeInput"))
        n3 = pg.locator("#sncAtts .snc-att").count()
        check("当时的参考图回填了", n3 == atts_sent, (atts_sent, n3))

        child_before = pg.evaluate("""(id) => {
          const n = window.SNC_TEST_API.nodes().find(x => x.id === id);
          return n ? (n.dataUrl || '') : null;
        }""", child_id)
        pg.fill("#sncComposeInput", SUBMIT + "（改过一版）")
        pg.locator("#sncComposeSend").click()
        pg.wait_for_timeout(1600)
        nodes = pg.evaluate("""() => window.SNC_TEST_API.nodes().map(n => ({
          id: n.id, from: n.from || [], url: (n.dataUrl || '').slice(0, 40)
        }))""")
        grand = [n for n in nodes if child_id in n["from"]]
        check("再提交又派生一张（不是改原图）", len(grand) >= 1, grand)
        child_after = pg.evaluate("""(id) => {
          const n = window.SNC_TEST_API.nodes().find(x => x.id === id);
          return n ? (n.dataUrl || '') : null;
        }""", child_id)
        check("原卡图片一个字节没动", child_before == child_after,
              (str(child_before)[:40], str(child_after)[:40]))
        check("新卡 from 指回原卡", all(child_id in g["from"] for g in grand), grand)

        check("全程没有 JS 异常", not errs, errs[:3])
        b.close()


if __name__ == "__main__":
    probe_server_side()
    probe_ui()
    print("-" * 46)
    print("PASS %d / FAIL %d" % (PASS, FAIL))
    sys.exit(1 if FAIL else 0)
