# -*- coding: utf-8 -*-
"""测试用静态服务：不起窗口，只跑 HTTP 桥接。"""
import os
import sys
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "proto"))
import server  # noqa: E402

PORT = int(os.environ.get("SNC_PORT", "8321"))

class TestHandler(server.Handler):
    """回归用的页面仍按旧版启动（示例卡 / 恢复最近画布）。

    v3.7.5 把正式启动改成了「每次新建空白画布」，而几十个老自检都假设
    首屏就有示例卡。与其逐个改测试，不如只在测试服务这一层注入 ?sncseed=1；
    正式包和 8321 之外的访问都不带这个参数，行为不受影响。
    想验空白启动本身，访问 /canvas.html?plain=1（本层不会追加）。
    """

    def do_GET(self):
        if self.path.startswith("/canvas.html") and \
                "sncseed=" not in self.path and "plain=" not in self.path:
            target = self.path + ("&" if "?" in self.path else "?") + "sncseed=1"
            self.send_response(302)
            self.send_header("Location", target)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        return server.Handler.do_GET(self)


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), TestHandler)
    srv.daemon_threads = True
    print("serving on %d" % PORT, flush=True)
    srv.serve_forever()
