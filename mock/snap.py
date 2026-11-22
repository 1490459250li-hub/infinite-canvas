# -*- coding: utf-8 -*-
"""界面质感三方案：渲染截图自检。"""
import pathlib, sys
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
PAGE = (HERE / "ui-polish-3.html").as_uri()
OUT = HERE / "shots"
OUT.mkdir(exist_ok=True)


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": 1560, "height": 940}, device_scale_factor=1)
        pg.goto(PAGE)
        pg.wait_for_timeout(900)
        pg.screenshot(path=str(OUT / "00-all.png"))

        for m in ("a", "b", "c"):
            pg.click(f'#modeSeg button[data-mode="{m}"]')
            pg.wait_for_timeout(500)
            pg.screenshot(path=str(OUT / f"0{m}-{m}.png"))

        # 亮色主题：验证 B 的磨砂输入条不会变成黑块
        pg.click('#thSeg button[data-th="light"]')
        pg.wait_for_timeout(400)
        for m in ("b", "c"):
            pg.click(f'#modeSeg button[data-mode="{m}"]')
            pg.wait_for_timeout(450)
            pg.screenshot(path=str(OUT / f"9{m}-light.png"))
        pg.click('#modeSeg button[data-mode="all"]')
        pg.wait_for_timeout(500)
        pg.screenshot(path=str(OUT / "90-all-light.png"))

        pg.click('#thSeg button[data-th="dark"]')
        pg.click('#modeSeg button[data-mode="d"]')
        pg.wait_for_timeout(500)
        pg.screenshot(path=str(OUT / "80-detail.png"))

        errs = pg.evaluate("() => (window.__errs || [])")
        print("console errors:", errs)
        b.close()
    print("shots ->", OUT)


if __name__ == "__main__":
    main()
