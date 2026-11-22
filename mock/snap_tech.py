# -*- coding: utf-8 -*-
"""E + 科技感三方案：整体 + 1:1 细节截图。"""
import pathlib
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
PAGE = (HERE / "ui-tech-3.html").as_uri()
OUT = HERE / "shots4"
OUT.mkdir(exist_ok=True)


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": 1560, "height": 940}, device_scale_factor=2)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(PAGE)
        pg.wait_for_timeout(1200)

        def detail(m, tag, dx, dy, w, h):
            box = pg.locator(".app").first.bounding_box()
            k = box["width"] / 1280.0
            pg.screenshot(path=str(OUT / f"3{m}-{tag}.png"), clip={
                "x": box["x"] + dx * k, "y": box["y"] + dy * k,
                "width": w * k, "height": h * k,
            })

        for m in ("h", "i", "j"):
            pg.click(f'#modeSeg button[data-mode="{m}"]')
            pg.wait_for_timeout(600)
            pg.screenshot(path=str(OUT / f"1{m}-{m}.png"))
            # 顶部：标题栏 + 顶栏 + 左栏头部
            detail(m, "top", 0, 0, 640, 250)
            # 左栏右缘 + 画布左缘：看刻度尺与交界线
            detail(m, "seam", 200, 120, 620, 420)

        pg.click('#modeSeg button[data-mode="all"]')
        pg.wait_for_timeout(600)
        pg.screenshot(path=str(OUT / "00-all.png"), full_page=True)

        pg.click('#thSeg button[data-th="light"]')
        pg.wait_for_timeout(400)
        for m in ("h", "i", "j"):
            pg.click(f'#modeSeg button[data-mode="{m}"]')
            pg.wait_for_timeout(500)
            pg.screenshot(path=str(OUT / f"2{m}-light.png"))

        print("errors:", errs)
        b.close()
    print("shots ->", OUT)


if __name__ == "__main__":
    main()
