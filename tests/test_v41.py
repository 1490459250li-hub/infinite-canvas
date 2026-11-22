# -*- coding: utf-8 -*-
"""v3.7.2 回归：MiniMax H3-Image 接入（预留位）。

A 段：注册表 / 源码断言（模型 ID、端点、官方限制写在哪）。
B 段：纯 Python 打桩 —— 文生图与编辑走两个端点、size 只给像素不给 aspect_ratio、
      部分失败要看 data[].error、只回 url 时自己下载。**不联网、不消耗额度**。
C 段：浏览器里确认设置页自动多出一张 MiniMax 卡片（前端按 /api/providers 渲染）。
"""
import base64
import json
import os
import socket
import subprocess
import sys
import time

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
SERVER_PY = os.path.join(ROOT, "proto", "server.py")

sys.path.insert(0, os.path.join(ROOT, "proto"))
import server  # noqa: E402

src = open(SRC, encoding="utf-8").read()
py = open(SERVER_PY, encoding="utf-8").read()
body_src = py.split("def render_minimax")[1].split("def render_image")[0]

print("\n== A  注册表 / 源码 ==")
check("版本号 >= 3.7.2", server._ver_key(server.APP_VERSION) >= server._ver_key("3.7.2"),
      server.APP_VERSION)
check("PROVIDER_ORDER 里有 minimax", "minimax" in server.PROVIDER_ORDER,
      server.PROVIDER_ORDER)
check("minimax 排在最后一个（不打乱老顺序）",
      server.PROVIDER_ORDER[-1] == "minimax", server.PROVIDER_ORDER)

spec = server.provider_spec("minimax")
check("规格已注册", bool(spec))
check("显示名 MiniMax / 标签 H3", spec.get("label") == "MiniMax" and spec.get("tag") == "H3")
check("国内域名 api.minimaxi.com", spec.get("base") == "https://api.minimaxi.com/v1",
      spec.get("base"))
check("key 前缀 sk-", spec.get("key_prefix") == "sk-")
check("提示里写了海外域名", "api.minimax.io" in spec.get("hint", ""))
check("提示里写了 4K 与 16 张参考图",
      "4K" in spec.get("hint", "") and "16" in spec.get("hint", ""), spec.get("hint"))

ids = [m["id"] for m in (spec.get("image") or [])]
check("两个模型：MiniMax-H3-Image / Highspeed",
      ids == ["MiniMax-H3-Image", "MiniMax-H3-Image-Highspeed"], ids)
for m in (spec.get("image") or []):
    check("%s 最大边长 4096（4K）" % m["key"], m.get("max_side") == 4096, m.get("max_side"))
    check("%s 最多 16 张参考图" % m["key"], m.get("max_refs") == 16, m.get("max_refs"))
    check("%s 不走蒙版（官方明确不支持）" % m["key"], m.get("mask") is False)
check("标准档标了 4K", spec["image"][0].get("badge") == "4K", spec["image"][0].get("badge"))
check("note 里如实写了不支持蒙版与透明底",
      "不支持蒙版" in spec["image"][0].get("note", ""), spec["image"][0].get("note"))

texts = [t["id"] for t in (spec.get("text") or [])]
check("文本模型走 MiniMax-M3 系列（M2.5/M2.7 已在退役名单）", "MiniMax-M3" in texts, texts)

check("分发到 render_minimax", 'if pid == "minimax":' in py and
      "return render_minimax(key, entry, req)" in py)
check("文生图打 /v1/images/generations", '"/images/generations"' in body_src)
check("有参考图改打 /v1/images/edits", '"/images/edits"' in body_src)
check("size 给的是「宽x高」像素", '"size": _minimax_size(' in body_src)
check("不传 aspect_ratio / area（混用会 400）",
      '"aspect_ratio"' not in body_src and '"area"' not in body_src)
check("要 b64_json 不要 url", '"response_format": "b64_json"' in body_src)
check("参考图放进 images[].image_url",
      '"image_url": u' in body_src)
check("参考图按 max_refs 截断", "images[:cap]" in body_src)
check("部分失败看 data[].error，不只看 HTTP 码", 'item.get("error")' in body_src)
check("补了总像素上下限（官方 65.5 万–2000 万）",
      "MINIMAX_PIXEL_MIN" in py and "MINIMAX_PIXEL_MAX" in py)
check("前端没有硬编码 minimax（卡片照旧自动渲染）", "minimax" not in src)

print("\n== B  纯 Python 打桩 ==")


def size_of(v):
    w, h = [int(x) for x in v.split("x")]
    return w, h


for ratio, res in (("1:1", 1024), ("16:9", 2048), ("3:2", 2048), ("9:16", 2048),
                   ("21:9", 2048), ("auto", 4096)):
    v = server._minimax_size(ratio, res)
    w, h = size_of(v)
    total = w * h
    check("%s/%d 落在官方像素区间 (%s)" % (ratio, res, v),
          server.MINIMAX_PIXEL_MIN <= total <= server.MINIMAX_PIXEL_MAX, total)
    check("%s/%d 单边不超 4096" % (ratio, res), w <= 4096 and h <= 4096, (w, h))
    check("%s/%d 宽高比在 1:3–3:1" % (ratio, res),
          abs(w / float(h)) <= 3.0 and abs(h / float(w)) <= 3.0, round(w / float(h), 2))

check("auto 给正方形", size_of(server._minimax_size("auto", 2048))[0] ==
      size_of(server._minimax_size("auto", 2048))[1])
check("auto 跟 res 走", server._minimax_size("auto", 4096) == "4096x4096",
      server._minimax_size("auto", 4096))

PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

sent = {}


class FakeResp:
    def __init__(self, status=200, payload=None, text=None):
        self.status_code = status
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {})

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


_orig_post = server.requests.post
_orig_get = server.requests.get


def fake_post(resp):
    def _p(url, **kw):
        sent["url"] = url
        sent["body"] = json.loads(kw.get("data") or "{}")
        sent["headers"] = kw.get("headers") or {}
        return resp
    return _p


entry = server.model_entry("minimax", "h3-image")
REF = "data:image/png;base64," + PNG_B64


def run(images=None, ratio="16:9", res=2048, prompt="把外墙换成暖色石材", resp=None):
    sent.clear()
    server.requests.post = fake_post(resp or FakeResp(200, {
        "data": [{"b64_json": PNG_B64, "revised_prompt": "x"}],
        "usage": {"total_tokens": 10}}))
    try:
        return server.render_minimax("sk-test", entry, {
            "prompt": prompt, "ratio": ratio, "res": res, "images": images or [],
            "fmt": "png"})
    finally:
        server.requests.post = _orig_post


try:
    check("选中 H3-Image 标准档", entry.get("id") == "MiniMax-H3-Image", entry.get("id"))

    out = run()
    body = sent["body"]
    check("无参考图走 /v1/images/generations",
          sent["url"].endswith("/v1/images/generations"), sent["url"])
    check("带 Bearer 鉴权", sent["headers"].get("Authorization") == "Bearer sk-test")
    check("model 是 MiniMax-H3-Image", body.get("model") == "MiniMax-H3-Image")
    check("size 是宽x高", "x" in (body.get("size") or ""), body.get("size"))
    check("没有 aspect_ratio / area",
          "aspect_ratio" not in body and "area" not in body, list(body.keys()))
    check("要 b64_json", body.get("response_format") == "b64_json")
    check("只要一张", body.get("n") == 1)
    check("prompt 原样发出", body.get("prompt") == "把外墙换成暖色石材")
    check("正常回包拿到 base64", out.get("ok") and out.get("b64") == PNG_B64, out.get("error"))
    check("format 由内容嗅出来", out.get("format") == "png", out.get("format"))
    check("标记为文生图通道", out.get("channel") == "gen", out.get("channel"))

    # 编辑通道
    out2 = run(images=[REF])
    check("有参考图走 /v1/images/edits",
          sent["url"].endswith("/v1/images/edits"), sent["url"])
    imgs = sent["body"].get("images") or []
    check("参考图塞进 images[].image_url", len(imgs) == 1 and
          imgs[0].get("image_url") == REF, imgs[:1])
    check("标记为编辑通道", out2.get("channel") == "edit", out2.get("channel"))

    # 16 张上限
    run(images=[REF] * 20)
    check("超过 16 张只发前 16 张",
          len(sent["body"].get("images") or []) == 16,
          len(sent["body"].get("images") or []))

    # max_refs=0 的模型拒绝参考图
    zero = dict(entry, max_refs=0)
    server.requests.post = fake_post(FakeResp(200, {"data": []}))
    try:
        bad = server.render_minimax("sk-test", zero, {
            "prompt": "x", "ratio": "1:1", "res": 1024, "images": [REF], "fmt": "png"})
    finally:
        server.requests.post = _orig_post
    check("max_refs=0 时明确报错而不是硬发",
          not bad.get("ok") and "不接受参考图" in (bad.get("error") or ""),
          bad.get("error"))

    # 部分失败：HTTP 200 但 data[0].error
    r = run(resp=FakeResp(200, {"data": [{"error": {"message": "content policy"}}]}))
    check("data[].error 被翻出来", not r.get("ok") and
          "content policy" in (r.get("error") or ""), r.get("error"))
    check("内容拦截标成 content", r.get("code") == "content", r.get("code"))

    # 空 data
    r = run(resp=FakeResp(200, {"data": []}))
    check("空 data 不崩，给明确提示",
          not r.get("ok") and "没有返回图片数据" in (r.get("error") or ""), r.get("error"))

    # HTTP 层错误
    r = run(resp=FakeResp(401, {"error": {"message": "invalid key"}},
                          text='{"error":"invalid key"}'))
    check("HTTP 401 走统一分类", not r.get("ok") and r.get("code") == "auth", r.get("code"))

    # 只回 url
    def fake_get(url, **kw):
        class B:
            status_code = 200
            content = base64.b64decode(PNG_B64)
        return B()

    server.requests.post = fake_post(FakeResp(200, {"data": [{"url": "https://x/a.png"}]}))
    server.requests.get = fake_get
    try:
        r = server.render_minimax("sk-test", entry, {
            "prompt": "x", "ratio": "1:1", "res": 1024, "images": [], "fmt": "png"})
    finally:
        server.requests.post = _orig_post
        server.requests.get = _orig_get
    check("只回 url 时自己下载成 base64", r.get("ok") and r.get("b64") == PNG_B64,
          r.get("error"))

    # 注册表下发
    state = server.provider_state("minimax")
    check("provider_state 能拿到 minimax", state.get("id") == "minimax")
    check("下发的 image 条目 value=minimax:h3-image",
          state["image"][0]["value"] == "minimax:h3-image", state["image"][0]["value"])
    check("默认没配密钥时 configured=False", state.get("configured") is False)
    payload = server.providers_payload()
    check("providers_payload 里六家齐了", len(payload["providers"]) == 6,
          [p["id"] for p in payload["providers"]])
    check("order 里 minimax 在末尾", payload["order"][-1] == "minimax", payload["order"])

    print("\n== C  浏览器：设置页卡片 ==")
    from playwright.sync_api import sync_playwright  # noqa: E402
    import requests  # noqa: E402

    def free_port():
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    PORT = free_port()
    BASE = "http://127.0.0.1:%d" % PORT
    proc = subprocess.Popen([sys.executable, os.path.join(HERE, "serve.py")],
                            env=dict(os.environ, SNC_PORT=str(PORT)),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            requests.get(BASE + "/api/update/check", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(channel="msedge")
            ctx = br.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
            page = ctx.new_page()
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(BASE + "/canvas.html")
            page.wait_for_selector(".snc-node")
            page.wait_for_timeout(1000)

            # 直接从接口读，顺便验证服务端下发
            prov = page.evaluate("""async () => {
                const r = await fetch('/api/providers');
                const j = await r.json();
                return (j.providers || []).map(p => ({id:p.id, label:p.label,
                                                      images:(p.image||[]).map(i=>i.label)}));
            }""")
            check("接口下发 6 家供应商", len(prov) == 6, [x["id"] for x in prov])
            mm = [x for x in prov if x["id"] == "minimax"]
            check("MiniMax 在列表里", bool(mm), prov)
            check("下发的模型名是 H3-Image",
                  bool(mm) and any("H3-Image" in n for n in mm[0]["images"]),
                  mm[0]["images"] if mm else None)

            page.evaluate("() => { const b=document.getElementById('sncSettings');"
                          " if(b) b.hidden=false; }")
            page.wait_for_timeout(400)
            cards = page.evaluate("""() => {
                const box = [...document.querySelectorAll('#sncSettings [class*="prov"]')];
                return box.map(c => (c.textContent||'').replace(/\\s+/g,' ').trim())
                          .filter(t => t.length > 10).slice(0, 12);
            }""")
            check("设置页渲染出 MiniMax 卡片",
                  any("MiniMax" in c for c in cards), cards[-2:])
            check("卡片里能看见 H3-Image",
                  any("H3-Image" in c for c in cards), cards[-1:])
            print("    卡片片段数:", len(cards))
            check("全程没有 JS 报错", not errs, errs[:3])
            br.close()
    finally:
        proc.terminate()
finally:
    server.requests.post = _orig_post
    server.requests.get = _orig_get

print("\n== 合计 %d 项 · 失败 %d ==" % (PASS + FAIL, FAIL))
if FAILS:
    for n, e in FAILS:
        print("  -", n, "->", e)
    sys.exit(1)
