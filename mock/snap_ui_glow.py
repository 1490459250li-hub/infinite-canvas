import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "shots7"
OUT.mkdir(exist_ok=True)

POS = {
    "p1-center":  (0.62, 0.50),
    "p2-top":     (0.62, 0.06),
    "p3-seam":    (0.03, 0.42),
    "p4-corner":  (0.96, 0.94),
}

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    pg = b.new_page(viewport={"width": 1600, "height": 1020}, device_scale_factor=1.4)
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto((ROOT / "ui-a-glow.html").resolve().as_uri())
    pg.wait_for_timeout(900)

    rect = pg.evaluate("() => { const r = document.getElementById('frame').getBoundingClientRect(); return {l:r.left, t:r.top, w:r.width, h:r.height}; }")

    def move(fx, fy):
        x = rect["l"] + fx * rect["w"]
        y = rect["t"] + fy * rect["h"]
        pg.evaluate(f"window.__move({x}, {y})")
        pg.wait_for_timeout(140)

    for name, (fx, fy) in POS.items():
        move(fx, fy)
        pg.locator("#frame").screenshot(path=str(OUT / f"{name}.png"))

    # 单独看边缘光
    move(0.62, 0.12)
    pg.click('#isoSeg button[data-iso="rim"]')
    pg.wait_for_timeout(160)
    pg.locator("#frame").screenshot(path=str(OUT / "q-rim.png"))
    pg.click('#isoSeg button[data-iso="all"]')

    # 单独看光晕
    move(0.5, 0.45)
    pg.click('#isoSeg button[data-iso="bloom"]')
    pg.wait_for_timeout(160)
    pg.locator("#frame").screenshot(path=str(OUT / "q-bloom.png"))
    pg.click('#isoSeg button[data-iso="all"]')

    # 亮色主题
    pg.click('#thSeg button[data-th="light"]')
    move(0.55, 0.30)
    pg.wait_for_timeout(220)
    pg.locator("#frame").screenshot(path=str(OUT / "p5-light.png"))

    # 整页
    pg.click('#thSeg button[data-th="dark"]')
    move(0.62, 0.5)
    pg.wait_for_timeout(220)
    pg.screenshot(path=str(OUT / "00-page.png"), full_page=True)

    print("errors:", errs)
    b.close()
