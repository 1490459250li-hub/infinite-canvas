# -*- coding: utf-8 -*-
"""第九批（v3.7.5 候选）自检：图文润色 / 进度环 / 套餐语言模型 / 空白启动 / 保存退出。

跑法：
    python tests/serve.py                       # 另开一个终端，端口 8321
    python tests/probe_batch9.py http://127.0.0.1:8321

服务端部分全部走离线打桩，不打任何真实上游、不消耗额度；
界面部分用 msedge + 网络存根，验的是真实 DOM 与真实请求体。
"""
import json
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
OK_CHAT = json.dumps({"choices": [{"message": {"content": "润色后的完整提示词"}}],
                      "model": "stub-text", "usage": {}})


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + "   -> " + repr(detail)[:400])


class FakeResp(object):
    def __init__(self, status, text="{}"):
        self.status_code = status
        self.text = text

    def json(self):
        try:
            return json.loads(self.text)
        except ValueError:
            return {}


# ---------------------------------------------------------------- 服务端
def probe_server_side():
    sys.path.insert(0, os.path.join(ROOT, "proto"))
    import server

    spec = server.provider_spec("seedream")
    ids = [t["id"] for t in spec.get("text") or []]
    wanted = ["doubao-seed-2.1-pro", "doubao-seed-2.1-lite", "doubao-seed-evolving",
              "glm-5.3", "glm-5.3-flash", "deepseek-v4.1-flash", "deepseek-v4-pro",
              "kimi-k3", "kimi-k3.1-pro", "kimi-k2.8-preview", "ark-code-latest"]
    print("== 火山方舟 Agent Plan 语言模型 ==")
    check("套餐端点指向 /api/plan/v3", spec.get("plan_base") == server.ARK_PLAN_BASE
          and "/api/plan/v3" in (spec.get("plan_base") or ""), spec.get("plan_base"))
    check("11 个常用套餐模型全部在册", all(m in ids for m in wanted),
          [m for m in wanted if m not in ids])
    check("套餐模型都打了 plan 标记",
          all(t.get("plan") for t in spec["text"] if t["id"] in wanted),
          [t for t in spec["text"] if t["id"] in wanted and not t.get("plan")])
    check("纯文本模型如实标 vision=False",
          server.text_entry("seedream", "glm-5.3").get("vision") is False
          and server.text_entry("seedream", "deepseek-v4-pro").get("vision") is False)
    check("多模态模型如实标 vision=True",
          server.text_entry("seedream", "glm-5.3-flash").get("vision") is True
          and server.text_entry("seedream", "kimi-k3").get("vision") is True)

    print("== 多模态 payload 组装 ==")
    imgs = [PNG, PNG]
    c = server.polish_user_content("把地面改成石材", imgs)
    check("带图时 content 是数组且含 image_url",
          isinstance(c, list) and sum(1 for p in c if "image_url" in p) == 2, c)
    check("不带图时 content 仍是字符串",
          isinstance(server.polish_user_content("一句话", []), str))
    gp = server.polish_google_parts("SYS", "一句话", imgs)
    check("Google 走 inline_data",
          sum(1 for p in gp if "inline_data" in p) == 2
          and all(p["inline_data"].get("data") for p in gp if "inline_data" in p), gp)
    check("带图才追加看图规则",
          "参考图" in server.polish_system(True)
          and "参考图" not in server.polish_system(False))
    clean = server.clean_polish_images({"images": [PNG, "http://x/a.png", PNG, PNG, PNG, PNG]})
    check("图片清洗：只收 data:image 且最多 4 张", len(clean) == 4, len(clean))
    big = server.clean_polish_images({"images": ["data:image/png;base64," + "x" * 2000000]})
    check("图片清洗：拒绝超大图", big == [], big)

    real_post, real_get = server.requests.post, server.requests.get
    real_catalog = server.fetch_catalog
    calls = []

    def record(status=200, body=OK_CHAT):
        def _post(url, headers=None, data=None, json=None, timeout=None, **kw):
            calls.append({"url": url,
                          "payload": __import__("json").loads(data) if data else (json or {})})
            return FakeResp(status, body)
        return _post

    try:
        print("== 润色：图真的进了请求体 ==")
        calls[:] = []
        server.requests.post = record()
        r = server.polish_with("openai", "k", "gpt-4.1-mini", "把地面改成石材",
                               "正在编辑「图片 1」", [PNG])
        content = calls[0]["payload"]["messages"][1]["content"]
        check("OpenAI 兼容：content 含 image_url",
              r.get("ok") and isinstance(content, list)
              and any("image_url" in p for p in content), (r, content))
        check("响应回报 imagesUsed=1", r.get("imagesUsed") == 1, r)
        check("system 带看图规则",
              "参考图" in calls[0]["payload"]["messages"][0]["content"])

        print("== 模型不收图时自动降级，润色不失败 ==")
        seq = [FakeResp(400, '{"error":{"message":"unsupported content: image_url"}}'),
               FakeResp(200, OK_CHAT)]

        def once(*a, **kw):
            return seq.pop(0)

        calls[:] = []
        server.requests.post = once
        r = server.polish_with("openai", "k", "text-only", "一句话", "", [PNG])
        check("400 后重发成功", r.get("ok") is True, r)
        check("降级后 imagesUsed=0", r.get("imagesUsed") == 0, r)

        print("== Seedream 套餐 Key 自动换通道 ==")
        calls[:] = []

        def plan_switch(url, headers=None, data=None, json=None, timeout=None, **kw):
            calls.append({"url": url,
                          "payload": __import__("json").loads(data) if data else {}})
            if "/api/v3/" in url:
                return FakeResp(401, '{"error":{"message":"invalid api key"}}')
            return FakeResp(200, OK_CHAT)

        server.requests.post = plan_switch
        r = server.polish_with("seedream", "k", "doubao-seed-2.1-pro",
                               "把地面改成石材", "", [PNG], True)
        check("按量通道 401 后打到套餐通道",
              r.get("ok") and any("/api/plan/v3/chat/completions" in c["url"] for c in calls),
              [c["url"] for c in calls])
        check("返回 channel=plan", r.get("channel") == "plan", r)
        check("套餐通道里仍然带了图",
              any(any("image_url" in p for p in c["payload"].get("messages", [{}])[1].get("content", [])
                      if isinstance(p, dict))
                  for c in calls if "/api/plan/v3/" in c["url"]), calls)

        print("== SenseNova 润色也带图 ==")
        calls[:] = []
        server.fetch_catalog = lambda key: {"data": []}
        server.requests.post = record()
        r = server.polish_prompt("k", "把地面改成石材", "sensenova-6.8-flash", "", [PNG])
        content = calls[0]["payload"]["messages"][1]["content"]
        check("SenseNova content 含 image_url",
              r.get("ok") and isinstance(content, list)
              and any("image_url" in p for p in content), (r, content))

        print("== 套餐 Key 验证会列出语言模型 ==")
        server.requests.get = lambda *a, **kw: FakeResp(401, '{"error":{"message":"auth"}}')
        server.requests.post = lambda *a, **kw: FakeResp(404, '{"error":{"code":"UnsupportedModel"}}')
        v = server.probe_provider("seedream", "ark-plan-key")
        check("套餐通道验证通过", v.get("ok") is True and v.get("channel") == "plan", v)
        check("验证结果含套餐语言模型", "glm-5.3-flash" in (v.get("models") or []), v)
        check("提示里说明套餐语言模型数量", "套餐语言模型" in (v.get("message") or ""), v)
    finally:
        server.requests.post, server.requests.get = real_post, real_get
        server.fetch_catalog = real_catalog


# ---------------------------------------------------------------- 界面
def probe_ui():
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge")
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
        pg = ctx.new_page()
        pg.goto(BASE + "/canvas.html?plain=1")
        pg.wait_for_selector(".snc-stage")
        pg.wait_for_timeout(900)

        print("== 冷启动落在一张空白画布 ==")
        st = pg.evaluate("""() => ({
          nodes: window.SNC_TEST_API.nodes().length,
          title: (document.getElementById('sncTitle')||{}).textContent || '',
          emptyHint: !!document.querySelector('.snc-empty, .snc-empty-hint, .snc-empty-chip'),
          docs: document.querySelectorAll('.snc-doc-item').length
        })""")
        check("首屏没有任何卡片", st["nodes"] == 0, st)
        check("标题是新的未命名画布", "未命名画布" in st["title"], st)

        print("== 保存按钮 / Ctrl+S / 脏标记 ==")
        check("顶栏有保存按钮", pg.locator("#sncSaveBtn").count() == 1)
        dirty = pg.evaluate("() => window.SNC_TEST_API.dirty()")
        check("改动后出现未保存标记", dirty == "未保存", dirty)
        pg.keyboard.press("Control+s")
        pg.wait_for_timeout(700)
        saved = pg.evaluate("() => (document.getElementById('sncBadge')||{}).textContent")
        check("Ctrl+S 后落到已保存", saved == "已保存", saved)
        pg.locator("#sncSaveBtn").click()
        pg.wait_for_timeout(500)
        check("保存按钮也能落盘", pg.evaluate(
            "() => (document.getElementById('sncBadge')||{}).textContent") == "已保存")

        print("== 退出前保存确认 ==")
        pg.evaluate("() => window.__sncQuitProbe = 0")
        pg.evaluate("""() => {
          window.pywebview = {api: {app_quit: function(){ window.__sncQuitProbe = 1; }}};
        }""")
        pg.evaluate("() => window.__sncRequestQuit()")
        check("退出确认框弹出", pg.locator("#sncQuit").is_visible())
        pg.locator('#sncQuit [data-act="cancel"]').click()
        check("取消后框收起、没有退出",
              not pg.locator("#sncQuit").is_visible()
              and pg.evaluate("() => window.__sncQuitProbe") == 0)
        pg.evaluate("() => window.__sncRequestQuit()")
        pg.locator('#sncQuit [data-act="save"]').click()
        pg.wait_for_timeout(900)
        check("保存并退出：保存完成后才关窗",
              pg.evaluate("() => window.__sncQuitProbe") == 1
              and not pg.locator("#sncQuit").is_visible(),
              pg.evaluate("() => window.__sncQuitProbe"))
        pg.evaluate("() => { try{ delete window.pywebview; }catch(e){} }")

        print("== 进度环：起点 / 周长 / 百分比 ==")
        r50 = pg.evaluate("() => window.SNC_TEST_API.progressRing(50)")
        r99 = pg.evaluate("() => window.SNC_TEST_API.progressRing(99)")
        # v3.7.7：按真实圆角 R=12 同心画，inset=2、r=R-inset=10；周长 = 4 段直线 + 4 段 1/4 圆弧
        import math
        R, D, r = 12, 2, 10
        P = 2 * ((240 - 2 * D) + (160 - 2 * D)) - 8 * r + 2 * math.pi * r
        check("viewBox 与图片框像素 1:1", r99["viewBox"] == "0 0 240 160", r99)
        check("周长含 4 段圆角弧", abs(r99["perimeter"] - P) < 0.1, (r99["perimeter"], P))
        check("起点在上边正中、顺时针", r99["d"].startswith("M120.00 2.00 H228.00 A10.00"), r99["d"])
        check("四角都是圆弧（不再被圆角裁断）",
              r99["d"].count(" A10.00 10.00 0 0 1 ") == 4, r99["d"])
        check("圆角与裁切同心：右上弧终点落在 (238,12)",
              "A10.00 10.00 0 0 1 238.00 12.00" in r99["d"], r99["d"])
        check("50% 恰好画半圈", abs(r50["drawn"] / P - 0.5) < 0.002, r50)
        check("99% 几乎画满（不再只有一半）", abs(r99["drawn"] / P - 0.99) < 0.002, r99)
        check("左上角数字与进度一致", r99["badge"] == "99%" and r50["badge"] == "50%",
              (r50["badge"], r99["badge"]))

        print("== AI 润色：文字 + 图片一起 POST ==")
        captured = []
        pg.route("**/api/polish", lambda route: (
            captured.append(route.request.post_data),
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": True, "text": "润色后的完整提示词",
                                           "model": "stub", "latencyMs": 12,
                                           "imagesUsed": 1}))))
        pg.evaluate("""(png) => {
          window.SNC_TEST_API.attach(png);
          document.getElementById('sncComposeInput').value = '把地面改成石材';
        }""", PNG)
        pg.evaluate("() => document.getElementById('sncPolish').click()")
        pg.wait_for_timeout(1200)
        check("润色请求已发出", len(captured) == 1, len(captured))
        if captured:
            body = json.loads(captured[0])
            check("请求体带 images", len(body.get("images") or []) == 1, body.get("images"))
            check("图片已统一成 JPEG",
                  (body.get("images") or [""])[0].startswith("data:image/jpeg"),
                  (body.get("images") or [""])[0][:40])
            check("文字仍在", body.get("text") == "把地面改成石材", body.get("text"))
            check("带上了所选供应商 / 模型",
                  bool(body.get("provider")) and bool(body.get("model")), body)
            check("润色结果写回输入框",
                  pg.input_value("#sncComposeInput") == "润色后的完整提示词",
                  pg.input_value("#sncComposeInput"))
        else:
            check("请求体带 images", False, "no request")
            check("图片已统一成 JPEG", False, "no request")
            check("文字仍在", False, "no request")
            check("带上了所选供应商 / 模型", False, "no request")
            check("润色结果写回输入框", False, "no request")

        b.close()


def main():
    probe_server_side()
    probe_ui()
    print("\n== 汇总 ==")
    print("PASS %d / FAIL %d" % (PASS, FAIL))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
