# -*- coding: utf-8 -*-
"""侧栏改造自检：起本地静态服务，抓侧栏区域截图。"""
import pathlib
import threading
import functools
import http.server
import socketserver
import sys

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
PROTO = HERE.parent / "proto"
OUT = HERE / "shots11"
OUT.mkdir(exist_ok=True)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(port):
    handler = functools.partial(Quiet, directory=str(PROTO))
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main():
    port = 8731
    httpd = serve(port)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": 1400, "height": 880}, device_scale_factor=2)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{port}/canvas.html", wait_until="networkidle")
        pg.wait_for_timeout(1000)
        try:
            pg.click("#sncEulaAgree", timeout=2500)
        except Exception:
            pass
        pg.wait_for_timeout(700)
        pg.screenshot(path=str(OUT / "rail-1.png"))
        rail = pg.locator("#snc .snc-doc")
        rail.screenshot(path=str(OUT / "rail-only.png"))
        print("rail box:", rail.bounding_box())
        print("first child:", pg.evaluate("() => { var d=document.querySelector('#snc .snc-doc'); return d && d.children[0] ? d.children[0].className : null; }"))
        print("errors:", errs)
        b.close()
    httpd.shutdown()
    print("shots ->", OUT)


if __name__ == "__main__":
    sys.exit(main())
