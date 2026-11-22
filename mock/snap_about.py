# -*- coding: utf-8 -*-
"""v3.8.14 自检：设置 → 关于 里的应用图标。"""
import pathlib
import threading
import functools
import http.server
import socketserver

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
PROTO = HERE.parent / "proto"
OUT = HERE / "shots15"


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    port = 8751
    handler = functools.partial(Quiet, directory=str(PROTO))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": 1280, "height": 860}, device_scale_factor=2)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{port}/canvas.html", wait_until="networkidle")
        pg.wait_for_timeout(800)
        try:
            pg.click("#sncEulaAgree", timeout=2500)
        except Exception:
            pass
        pg.evaluate("""() => {
            document.getElementById('sncScrim').hidden = false;
            document.getElementById('sncSettings').hidden = false;
            var b = document.querySelector('#sncSetNav button[data-pane="about"]');
            if (b) b.click();
        }""")
        pg.wait_for_timeout(500)
        pg.locator("#sncSettings").screenshot(path=str(OUT / "about-dlg.png"))
        print("about mark:", pg.evaluate("""() => {
            var m = document.querySelector('.snc-about-mark img');
            if (!m) return null;
            var r = m.getBoundingClientRect();
            return {w: r.width, h: r.height, complete: m.complete, nw: m.naturalWidth};
        }"""))
        print("errors:", errs)
        b.close()
    httpd.shutdown()


if __name__ == "__main__":
    main()
