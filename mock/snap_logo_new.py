# -*- coding: utf-8 -*-
"""v3.8.14 自检：新 logo 在顶栏（浏览器态）与标题栏（shell 态）里的实际渲染。"""
import pathlib
import threading
import functools
import http.server
import socketserver
import sys

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
PROTO = HERE.parent / "proto"
OUT = HERE / "shots15"
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


def shoot(pg, name, sel):
    el = pg.locator(sel).first
    box = el.bounding_box()
    print(name, "box", box)
    shot = el.screenshot(path=str(OUT / (name + ".png")))
    pg.locator("#snc").screenshot(path=str(OUT / (name + "-ctx.png")))
    return shot


def main():
    port = 8741
    httpd = serve(port)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        errs = []
        pg = b.new_page(viewport={"width": 1280, "height": 820}, device_scale_factor=2)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{port}/canvas.html", wait_until="networkidle")
        pg.wait_for_timeout(900)
        try:
            pg.click("#sncEulaAgree", timeout=2500)
        except Exception:
            pass
        pg.wait_for_timeout(500)
        shoot(pg, "topbar", "#snc .snc-top")
        print("mark css:", pg.evaluate(
            "() => { var b=document.getElementById('sncBrandBtn'); if(!b) return null;"
            "var cs=getComputedStyle(b), r=b.getBoundingClientRect(), im=b.querySelector('img');"
            "return {w:r.width,h:r.height,cssW:cs.width,cssH:cs.height,"
            "img: im?{w:im.getBoundingClientRect().width,h:im.getBoundingClientRect().height,complete:im.complete,nw:im.naturalWidth}:null}; }"))

        pg2 = b.new_page(viewport={"width": 1280, "height": 820}, device_scale_factor=2)
        pg2.on("pageerror", lambda e: errs.append(str(e)))
        pg2.goto(f"http://127.0.0.1:{port}/canvas.html?shell=1", wait_until="networkidle")
        pg2.wait_for_timeout(900)
        try:
            pg2.click("#sncEulaAgree", timeout=2500)
        except Exception:
            pass
        pg2.wait_for_timeout(500)
        shoot(pg2, "winbar", "#sncWinbar")
        print("winbar mark css:", pg2.evaluate(
            "() => { var b=document.getElementById('sncWinBrandBtn'); if(!b) return null;"
            "var r=b.getBoundingClientRect(), im=b.querySelector('img');"
            "return {w:r.width,h:r.height,"
            "img: im?{w:im.getBoundingClientRect().width,h:im.getBoundingClientRect().height,complete:im.complete,nw:im.naturalWidth}:null}; }"))
        print("errors:", errs)
        b.close()
    httpd.shutdown()
    print("shots ->", OUT)


if __name__ == "__main__":
    sys.exit(main())
