import pathlib
from playwright.sync_api import sync_playwright
ROOT = pathlib.Path(__file__).parent
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    pg = b.new_page(viewport={"width":1600,"height":1020}, device_scale_factor=1)
    pg.goto((ROOT/"ui-a-glow.html").resolve().as_uri()); pg.wait_for_timeout(600)
    r = pg.evaluate("() => { const r=document.getElementById('frame').getBoundingClientRect(); return {l:r.left,t:r.top,w:r.width,h:r.height}; }")
    # 直接切光层，避免点击导致 pointerleave
    pg.evaluate("document.body.dataset.iso='rim'")
    x = r["l"] + 0.62*r["w"]; y = r["t"] + 0.02*r["h"]
    pg.evaluate(f"window.__move({x},{y})")
    pg.wait_for_timeout(200)
    print(pg.evaluate("() => { const e=document.querySelector('[data-l=\"rim\"]'); return [e.style.opacity, getComputedStyle(e).opacity]; }"))
    pg.locator("#frame").screenshot(path=str(ROOT/"shots7/_dbg_rim.png"))
    b.close()
