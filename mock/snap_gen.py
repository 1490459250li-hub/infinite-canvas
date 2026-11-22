# -*- coding: utf-8 -*-
"""在真实页面里造一张「生成中」卡，拍特写并读出环形参数，用来跟 ai.html 对齐。"""
import pathlib
import threading
import functools
import http.server
import socketserver
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROTO = ROOT / "proto"
OUT = ROOT / "mock" / "shots12"
OUT.mkdir(parents=True, exist_ok=True)

INJECT = """
() => {
  const api = window.SNC_TEST_API;
  const ns = api.nodes();
  const n = {
    id: "probe-wait", type: "gen", status: "waiting",
    x: 80, y: 80, w: 300, h: 220, progress: 0, queueAhead: 0,
    prompt: "把场景换成傍晚蓝调夜景：暖色路灯与室内窗光为主光源",
    modelOpt: "sensenova:seedream-5.5", res: 2048, seed: 7
  };
  ns.push(n);
  api.render();
  const h = document.querySelector('[data-id="probe-wait"]');
  if (h) {
    const app = document.getElementById("sncApp") || document.getElementById("snc");
    window.__probe = h;
  }
  return !!h;
}
"""


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
    port = 8742
    httpd = serve(port)
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=2)
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{port}/canvas.html", wait_until="networkidle")
        pg.wait_for_timeout(900)
        try:
            pg.click("#sncEulaAgree", timeout=2000)
        except Exception:
            pass
        pg.wait_for_timeout(500)
        ok = pg.evaluate(INJECT)
        pg.wait_for_timeout(1200)
        print("node injected:", ok)
        node = pg.locator('[data-id="probe-wait"]')
        node.screenshot(path=str(OUT / "our-waiting.png"))
        info = pg.evaluate(
            """() => {
              const h = document.querySelector('[data-id="probe-wait"]');
              const a = h.querySelector('.snc-prog-arc');
              const t = h.querySelector('.snc-prog-track');
              const l = h.querySelector('.snc-gen-latent');
              if (!a) return {err: 'no arc'};
              const cs = getComputedStyle(a);
              return {
                dash: a.style.strokeDasharray, off: a.style.strokeDashoffset,
                attrStroke: a.getAttribute('stroke'), cssStroke: cs.stroke,
                width: cs.strokeWidth,
                trackOpacity: t ? getComputedStyle(t).opacity : null,
                latent: l ? getComputedStyle(l).opacity : null,
                box: h.getBoundingClientRect().width + 'x' + h.getBoundingClientRect().height,
                perim: a.dataset.perimeter
              };
            }"""
        )
        print(info)
        print("errors:", errs[:5])
        b.close()
    httpd.shutdown()
    print("shot ->", OUT / "our-waiting.png")


if __name__ == "__main__":
    sys.exit(main())
