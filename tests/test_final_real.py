# -*- coding: utf-8 -*-
"""真实接口收尾：一次生成 + 一次重生成，顺带量一下 5 版历史对保存耗时的影响。"""
import os, json
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8310/canvas.html"
SHOT = r"C:\Users\Flish\WorkBuddy\2026-11-07-19-49-41\_inspect\p0"

with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    ctx = br.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(900)

    gen = page.locator('.snc-node[data-id^="g-"]').first
    nid = gen.get_attribute("data-id")
    gen.click()
    page.wait_for_timeout(250)

    for round_ in (1, 2):
        page.evaluate("() => window.SNC_TEST_API.rerun()")
        if round_ == 1:
            page.wait_for_function(
                """(id) => {
                    const s = document.querySelector('.snc-node[data-id="' + id + '"] .snc-vstrip');
                    return s && !s.hidden && s.textContent.includes('v1');
                }""", arg=nid, timeout=180000)
        else:
            page.wait_for_function(
                """(id) => {
                    const s = document.querySelector('.snc-node[data-id="' + id + '"] .snc-vstrip');
                    return s && !s.hidden && s.textContent.includes('/2');
                }""", arg=nid, timeout=180000)
        page.wait_for_timeout(400)
        print("round %d ok:" % round_, page.inner_text('.snc-node[data-id="%s"] .snc-vstrip' % nid).replace("\n", " "))

    # 量一下当前画布序列化后的体积与保存耗时
    metrics = page.evaluate("""async () => {
        const t0 = performance.now();
        const req = indexedDB.open('sensenova-canvas', 1);
        const db = await new Promise((res, rej) => { req.onsuccess = () => res(req.result); req.onerror = () => rej(req.error); });
        const all = await new Promise((res, rej) => {
            const tx = db.transaction('boards', 'readonly');
            const r = tx.objectStore('boards').getAll();
            r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
        });
        const json = JSON.stringify(all);
        return {boards: all.length, nodes: all[0].nodes.length,
                mb: (json.length / 1048576).toFixed(2), ms: Math.round(performance.now() - t0)};
    }""")
    print("storage:", metrics)

    with page.expect_download(timeout=60000) as dl:
        page.click("#sncExportOpen")
        page.click('#sncExportMenu button[data-exp="board"]')
    png = os.path.join(SHOT, "final.png")
    dl.value.save_as(png)
    print("png", os.path.getsize(png), "bytes")

    page.screenshot(path=os.path.join(SHOT, "final2.png"))
    print("errors:", errs[:3])
    br.close()
