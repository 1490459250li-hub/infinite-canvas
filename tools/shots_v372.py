# -*- coding: utf-8 -*-
"""v3.7.2 截图：六家供应商卡片（真实注册表）+ 出图下拉里的新模型名。

不碰开发用的 .env：把密钥写进临时 .env，直接把 providers_payload() 打桩给页面。
产物落在 截图/v372/。
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "proto"))
import server  # noqa: E402

OUT = os.path.join(ROOT, "截图", "v372")
os.makedirs(OUT, exist_ok=True)
BASE = os.environ.get("SNC_BASE", "http://127.0.0.1:8321/canvas.html")

TMP = tempfile.mkdtemp(prefix="snc-shot-v372-")
server._ENV_PATH = os.path.join(TMP, ".env")
with open(server._ENV_PATH, "w", encoding="utf-8") as f:
    f.write("SNC_KEY_SENSENOVA_1_=sk-demo-sensenova-0000000000000000\n")
    f.write("SNC_KEY_SENSENOVA_1_NAME=主账号\n")
    f.write("SNC_KEY_GOOGLE_1_=AIzaDEMO0000000000000000000000000\n")
    f.write("SNC_KEY_GOOGLE_1_NAME=主号\n")
    f.write("SNC_KEY_GOOGLE_2_=AIzaDEMO1111111111111111111111111\n")
    f.write("SNC_KEY_GOOGLE_2_NAME=备用\n")
    f.write("SNC_KEY_OPENAI_1_=sk-demo-openai-0000000000000000000\n")
    f.write("SNC_KEY_OPENAI_1_NAME=主账号\n")
    f.write("SNC_KEY_MINIMAX_1_=sk-demo-minimax-000000000000000\n")
    f.write("SNC_KEY_MINIMAX_1_NAME=国内站\n")

PAYLOAD = server.providers_payload()
print("providers:", [p["id"] for p in PAYLOAD["providers"]])
for p in PAYLOAD["providers"]:
    print("  %-10s %-14s %s" % (p["id"], p["tag"], [m["id"] for m in p["image"]]))


def jstub(payload):
    def fn(route):
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(payload, ensure_ascii=False))
    return fn


from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as pw:
    br = pw.chromium.launch(channel="msedge")
    ctx = br.new_context(viewport={"width": 1180, "height": 880}, device_scale_factor=2)
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    page = ctx.new_page()
    page.route("**/api/providers", jstub(PAYLOAD))
    page.route("**/api/health", jstub({
        "ok": True, "version": "3.7.2", "hasUpdate": False, "latest": "3.7.2",
        "providers": [p["id"] for p in PAYLOAD["providers"]],
        "routes": PAYLOAD["routes"], "models": [], "imageModels": [], "textModels": []}))
    page.goto(BASE, wait_until="load")
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(800)

    # 设置 → 模型页
    page.click(".snc-doc-foot [data-set]")
    page.wait_for_timeout(500)
    page.click('#sncSetNav button[data-pane="model"]')
    page.wait_for_timeout(1200)
    page.screenshot(path=os.path.join(OUT, "01-六家供应商.png"))
    n = page.evaluate("() => document.querySelectorAll('#sncProvList .snc-prov').length")
    print("卡片数:", n)

    # 整个设置对话框单独一张：说明页里放大看「供应商 4 / 6 已连接」才看得清
    dlg = page.query_selector("#sncSettings")
    if dlg:
        dlg.screenshot(path=os.path.join(OUT, "05-设置面板.png"))

    # 滚到 MiniMax 那张卡
    page.evaluate("""() => {
        var el = document.querySelector('#sncProvList .snc-prov[data-pid="minimax"]');
        if (el) el.scrollIntoView({block: 'center'});
    }""")
    page.wait_for_timeout(500)
    page.screenshot(path=os.path.join(OUT, "02-滚到MiniMax.png"))
    card = page.query_selector('#sncProvList .snc-prov[data-pid="minimax"]')
    if card:
        card.screenshot(path=os.path.join(OUT, "03-MiniMax卡片.png"))
    info = page.evaluate("""() => {
        var el = document.querySelector('#sncProvList .snc-prov[data-pid="minimax"]');
        return el ? el.innerText : '';
    }""")
    print("MiniMax 卡片文案:", info.replace("\n", " | "))

    page.click("#sncSetClose")
    page.wait_for_timeout(400)

    # 出图模型下拉：点开 #sncGModel
    page.click("#sncGModel")
    page.wait_for_timeout(700)
    page.screenshot(path=os.path.join(OUT, "04-出图模型清单.png"))
    opts = page.evaluate(
        "() => Array.from(document.querySelectorAll('#sncGModel option')).map(o => [o.value, o.textContent.trim()])")
    print("出图下拉:", opts)

    br.close()
print("done ->", OUT)
