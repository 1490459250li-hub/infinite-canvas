# -*- coding: utf-8 -*-
"""启动画面三方案：定格关键帧截图（动画由 t 决定，可复现）。"""
import pathlib
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
PAGE = (HERE / "splash-3.html").as_uri()
OUT = HERE / "shots3"
OUT.mkdir(exist_ok=True)


def seek(pg, t):
    pg.evaluate("(t) => window.sncSeek(t)", t)
    pg.wait_for_timeout(140)


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": 1480, "height": 900}, device_scale_factor=2)
        errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(PAGE)
        pg.wait_for_timeout(1000)

        # 并排终态
        pg.click('#modeSeg button[data-mode="all"]')
        pg.wait_for_timeout(500)
        seek(pg, 2.6)
        pg.screenshot(path=str(OUT / "00-all.png"), full_page=True)

        # 单屏 + 关键帧
        for k in ("s1", "s2", "s3"):
            pg.click(f'#modeSeg button[data-mode="{k}"]')
            pg.wait_for_timeout(400)
            seek(pg, 2.6)
            pg.screenshot(path=str(OUT / f"1{k}-{k}.png"), full_page=True)

        # S1 逐帧：点火 / 汇聚中 / 落位
        pg.click('#modeSeg button[data-mode="s1"]')
        pg.wait_for_timeout(400)
        for name, t in (("a", 0.30), ("b", 0.62), ("c", 0.95), ("d", 1.55)):
            seek(pg, t)
            pg.screenshot(path=str(OUT / f"2s1-{name}.png"), full_page=True)

        # S2 的中段：环形波前扫过，形状正在"显影"
        pg.click('#modeSeg button[data-mode="s2"]')
        pg.wait_for_timeout(400)
        seek(pg, 1.02)
        pg.screenshot(path=str(OUT / "2s2-wave.png"), full_page=True)

        print("errors:", errs)
        b.close()
    print("shots ->", OUT)


if __name__ == "__main__":
    main()
