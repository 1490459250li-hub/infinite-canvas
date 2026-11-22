import sys, pathlib
from playwright.sync_api import sync_playwright

BASE = pathlib.Path(__file__).parent
OUT = BASE / "shots5"
OUT.mkdir(exist_ok=True)

URL = (BASE / "ui-logo-3.html").as_uri()

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    pg = b.new_page(viewport={"width": 1420, "height": 760}, device_scale_factor=2)
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL)
    pg.wait_for_timeout(700)

    pg.screenshot(path=str(OUT / "10-all-energy.png"), full_page=True)

    # 三个方案的大图各截一张（1:1 细看）
    for i, k in enumerate(["l1", "l2", "l3"], 1):
        el = pg.query_selector_all(".big")[i - 1]
        el.screenshot(path=str(OUT / f"1{i}-{k}-big.png"))

    # 单色橙
    pg.click('#pseg button[data-p="orange"]')
    pg.wait_for_timeout(350)
    pg.screenshot(path=str(OUT / "20-orange.png"), full_page=True)
    for i, k in enumerate(["l1", "l2", "l3"], 1):
        pg.query_selector_all(".big")[i - 1].screenshot(path=str(OUT / f"2{i}-{k}-orange.png"))

    # 单色蓝
    pg.click('#pseg button[data-p="blue"]')
    pg.wait_for_timeout(350)
    pg.screenshot(path=str(OUT / "30-blue.png"), full_page=True)

    # 亮底 + 四色
    pg.click('#pseg button[data-p="energy"]')
    pg.click('#bseg button[data-bg="light"]')
    pg.wait_for_timeout(350)
    pg.screenshot(path=str(OUT / "40-light.png"), full_page=True)
    for i, k in enumerate(["l1", "l2", "l3"], 1):
        pg.query_selector_all(".big")[i - 1].screenshot(path=str(OUT / f"4{i}-{k}-light.png"))

    print("errors:", errs)
    b.close()

print("done")
