# -*- coding: utf-8 -*-
"""无边框三方案：渲染截图自检。"""
import pathlib
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
PAGE = (HERE / "ui-borderless-3.html").as_uri()
OUT = HERE / "shots2"
OUT.mkdir(exist_ok=True)


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": 1560, "height": 940}, device_scale_factor=1)
        pg.goto(PAGE)
        pg.wait_for_timeout(900)

        for m in ("e", "f", "g"):
            pg.click(f'#modeSeg button[data-mode="{m}"]')
            pg.wait_for_timeout(500)
            pg.screenshot(path=str(OUT / f"1{m}-{m}.png"))

        pg.click('#modeSeg button[data-mode="all"]')
        pg.wait_for_timeout(500)
        pg.screenshot(path=str(OUT / "00-all.png"))

        pg.click('#thSeg button[data-th="light"]')
        pg.wait_for_timeout(400)
        for m in ("e", "f", "g"):
            pg.click(f'#modeSeg button[data-mode="{m}"]')
            pg.wait_for_timeout(450)
            pg.screenshot(path=str(OUT / f"2{m}-light.png"))

        print("console errors:", pg.evaluate("() => (window.__errs || [])"))
        b.close()
    print("shots ->", OUT)


if __name__ == "__main__":
    main()
