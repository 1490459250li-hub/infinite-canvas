# -*- coding: utf-8 -*-
"""把 ai.html 参考稿在三个阶段各拍一张卡片特写，作为 1:1 对齐的基准。"""
import pathlib
from playwright.sync_api import sync_playwright

REF = pathlib.Path(r"C:\Users\Flish\Desktop\ai.html")
OUT = pathlib.Path(r"E:\无限画布\mock\shots12")
OUT.mkdir(parents=True, exist_ok=True)


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        pg.goto(REF.as_uri())
        pg.wait_for_timeout(700)
        for stage in ("queued", "submitted", "generating", "done"):
            pg.click(f'.stage-step[data-stage="{stage}"]')
            pg.wait_for_timeout(900)
            card = pg.locator("#genCard")
            card.screenshot(path=str(OUT / f"ref-{stage}.png"))
            info = pg.evaluate(
                """() => {
                    const a = document.querySelector('#ringComet');
                    const t = document.querySelector('#ringTrack');
                    const cs = getComputedStyle(a);
                    return {
                      dash: a.style.strokeDasharray,
                      off: a.style.strokeDashoffset,
                      opacity: a.style.opacity,
                      stroke: cs.stroke,
                      width: cs.strokeWidth,
                      trackOpacity: getComputedStyle(t).opacity,
                      latent: getComputedStyle(document.querySelector('.gen-latent')).opacity
                    };
                }"""
            )
            print(stage, info)
        b.close()
    print("ref shots ->", OUT)


if __name__ == "__main__":
    main()
