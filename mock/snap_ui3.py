import pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "shots7"; OUT.mkdir(exist_ok=True)
POS = {
    "p1-center": (0.62, 0.50),
    "p2-top":    (0.55, 0.03),
    "p3-seam":   (0.04, 0.42),
    "p4-corner": (0.95, 0.93),
    "p5-right":  (0.985, 0.55),
}
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    pg = b.new_page(viewport={"width":1600,"height":1020}, device_scale_factor=1.5)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto((ROOT/"ui-a-glow.html").resolve().as_uri()); pg.wait_for_timeout(700)
    r = pg.evaluate("() => { const r=document.getElementById('frame').getBoundingClientRect(); return {l:r.left,t:r.top,w:r.width,h:r.height}; }")

    def move(fx, fy):
        pg.evaluate(f"window.__move({r['l']+fx*r['w']}, {r['t']+fy*r['h']})")
        pg.wait_for_timeout(160)

    for name, (fx, fy) in POS.items():
        move(fx, fy)
        pg.locator("#frame").screenshot(path=str(OUT/f"{name}.png"))

    for iso in ("rim", "bloom", "seam"):
        pg.evaluate(f"document.body.dataset.iso='{iso}'")
        move(0.55, 0.06) if iso == "rim" else move(0.5, 0.45)
        pg.locator("#frame").screenshot(path=str(OUT/f"q-{iso}.png"))
    pg.evaluate("document.body.dataset.iso='all'")

    pg.evaluate("document.getElementById('app').dataset.th='light'")
    move(0.55, 0.10); pg.wait_for_timeout(150)
    pg.locator("#frame").screenshot(path=str(OUT/"p6-light.png"))
    pg.evaluate("document.getElementById('app').dataset.th='dark'")

    move(0.62, 0.5); pg.wait_for_timeout(200)
    pg.screenshot(path=str(OUT/"00-page.png"), full_page=True)
    print("errors:", errs)
    b.close()
