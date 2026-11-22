import sys, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "shots6"
OUT.mkdir(exist_ok=True)

TARGETS = [
    ("a1", 0.30),
    ("a2", 0.62),
    ("a3", 0.95),
    ("a4", 1.28),
    ("a5", 1.70),
    ("a6", 2.10),
    ("a7", 2.55),
    ("a8", 3.30),
]

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    pg = b.new_page(viewport={"width": 1480, "height": 1000}, device_scale_factor=1.5)
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto((ROOT / "splash-final.html").resolve().as_uri())
    pg.wait_for_timeout(900)

    for name, t in TARGETS:
        pg.evaluate(f"window.__seek({t})")
        pg.wait_for_timeout(90)
        pg.locator("#screen").screenshot(path=str(OUT / f"{name}.png"))

    # 整页
    pg.evaluate("window.__seek(2.55)")
    pg.wait_for_timeout(150)
    pg.screenshot(path=str(OUT / "00-page.png"), full_page=True)

    # 自动播放 1.2 秒，验证真的在跑
    pg.evaluate("window.__seek(0); window.__play()")
    pg.wait_for_timeout(1300)
    pg.locator("#screen").screenshot(path=str(OUT / "a9-live.png"))

    print("errors:", errs)
    b.close()
