# -*- coding: utf-8 -*-
"""第八批（v3.7.4 收尾）自检：删两处多余控件 + 「Key 贴错家」的识别。

跑法：
    python tests/probe_batch8.py http://127.0.0.1:8321

四条原则：
1. 删掉的东西要真从 DOM 里没了，不能只是 display:none（那样测试点得到、用户也看得到残影）；
2. 删掉之后功能不能跟着没 —— 编辑面板的空位卡原来和那颗按钮干同一件事，必须还能点开选图；
3. 底栏少了一个控件，发送按钮得仍然贴右、不溢出；
4. 「Key 贴错家」的识别用打桩验（离线、确定），不去真打四家上游。
"""
import json
import os
import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8321"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + "   -> " + repr(detail))


# ---------------------------------------------------------------- 服务端逻辑
def probe_server_side():
    sys.path.insert(0, os.path.join(ROOT, "proto"))
    import server

    class FakeResp(object):
        def __init__(self, status, text="{}"):
            self.status_code = status
            self.text = text

        def json(self):
            try:
                return json.loads(self.text)
            except ValueError:
                return {}

    real_get, real_post = server.requests.get, server.requests.post

    def make_get(ok_base_part):
        def _get(url, headers=None, timeout=None):
            # 只有「属于那一家」的地址回 200，其余一律 401
            if ok_base_part and ok_base_part in url:
                return FakeResp(200, '{"data":[{"id":"m1"}]}')
            return FakeResp(401, '{"error":{"message":"invalid api key"}}')
        return _get

    try:
        # ① 把 SenseNova 的钥匙贴进 Seedream：应当认出来，并指出正确的卡片
        server.requests.get = make_get("token.sensenova.cn")
        server.requests.post = lambda *a, **kw: FakeResp(401, "{}")
        res = server.probe_provider("seedream", "sk-test-key-not-real")
        check("贴错家：不是报「钥匙无效」，而是认出来源",
              res.get("code") == "wrong_provider", res)
        check("贴错家：建议里指明了是 SenseNova",
              (res.get("suggest") or {}).get("provider") == "sensenova", res)
        check("贴错家：提示里点名两张卡片",
              "SenseNova" in (res.get("message") or "")
              and "Seedream" in (res.get("message") or ""), res.get("message"))

        # ② 四家都不认：退回原来的鉴权失败，别硬编一个「属于某家」
        server.requests.get = make_get("")
        res = server.probe_provider("seedream", "sk-test-key-not-real")
        check("都不认时仍是 auth 失败", res.get("ok") is False and res.get("code") == "auth", res)
        check("都不认时不乱指供应商", not res.get("suggest"), res)

        # ③ 钥匙本来就是这家的：必须一次就过，别被新逻辑拖慢或误判
        server.requests.get = make_get("ark.cn-beijing.volces.com")
        res = server.probe_provider("seedream", "ark-test-key")
        check("对家钥匙正常通过", res.get("ok") is True and res.get("code") is None, res)

        # ④ 401 文案不再叫人去「更新 .env」
        code, msg = server.classify(401, "")
        check("401 文案不再提 .env", ".env" not in msg, msg)
    finally:
        server.requests.get, server.requests.post = real_get, real_post


# ---------------------------------------------------------------- 界面
def main():
    probe_server_side()

    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge")
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
        pg = ctx.new_page()
        pg.goto(BASE + "/canvas.html")
        pg.wait_for_selector(".snc-node")
        pg.wait_for_timeout(600)

        print("== 底部输入条：1 2 3 已经删了 ==")
        st = pg.evaluate("""() => {
          const bar = document.getElementById('sncStage') || document.body;
          const cnt = document.querySelector('.snc-count');
          const btns = document.querySelectorAll('.snc-count-b');
          const send = document.getElementById('sncSend');
          const row = send ? send.parentElement : null;
          const sr = send ? send.getBoundingClientRect() : null;
          const rr = row ? row.getBoundingClientRect() : null;
          const inp = document.getElementById('sncInput').getBoundingClientRect();
          return { cnt: !!cnt, btns: btns.length,
                   sendVisible: !!(send && sr.width > 8 && sr.height > 8),
                   sendRightGap: rr ? Math.round(rr.right - sr.right) : -1,
                   gapFromInput: sr ? Math.round(sr.left - inp.right) : -1,
                   overflow: row ? row.scrollWidth - row.clientWidth : -1,
                   rowH: rr ? Math.round(rr.height) : -1 };
        }""")
        check("页面上没有 .snc-count", st["cnt"] is False, st)
        check("页面上没有 1/2/3 按钮", st["btns"] == 0, st)
        check("发送按钮还在、可见", st["sendVisible"], st)
        check("发送按钮仍贴右边", 0 <= st["sendRightGap"] <= 40, st)
        check("输入行不溢出", st["overflow"] <= 1, st)
        check("输入行高度没塌", 30 <= st["rowH"] <= 64, st)

        print("== 一次生成只出一张（原来是 2）==")
        n0 = pg.evaluate("() => document.querySelectorAll('.snc-node').length")
        pg.evaluate("() => window.SNC_TEST_API.spawn('第二批测试', 1)")
        pg.wait_for_timeout(300)
        n1 = pg.evaluate("() => document.querySelectorAll('.snc-node').length")
        check("spawn(1) 只多一张卡", n1 == n0 + 1, (n0, n1))

        print("== 编辑面板：多余的「添加参考图」没了，空位卡还能点 ==")
        # 用一张已完成的图开编辑面板（真实入口：工具条 → 编辑）
        ok = pg.evaluate("""() => {
          const img = [...document.querySelectorAll('.snc-node')]
            .find(n => n.querySelector('img'));
          if(!img) return false;
          const r = img.getBoundingClientRect();
          img.dispatchEvent(new PointerEvent('pointerdown',
            {bubbles:true, clientX:r.left+20, clientY:r.top+20, pointerId:1}));
          return true;
        }""")
        pg.wait_for_timeout(200)
        pg.evaluate("""() => {
          const bar = document.getElementById('sncImgBar');
          const btn = bar && bar.querySelector('button[data-act="edit"]');
          if(btn) btn.click();
        }""")
        pg.wait_for_timeout(350)
        st = pg.evaluate("""() => {
          const panel = document.querySelector('.snc-compose');
          const attBtn = document.getElementById('sncAttBtn');
          const slots = document.querySelectorAll('.snc-att-slot');
          const send = document.getElementById('sncComposeSend');
          return { open: !!(panel && panel.offsetParent !== null),
                   attBtn: !!attBtn,
                   slots: slots.length,
                   sendVisible: !!(send && send.getBoundingClientRect().width > 8),
                   overflow: panel ? panel.scrollWidth - panel.clientWidth : -1 };
        }""")
        check("编辑面板打开", st["open"], st)
        check("面板里没有 #sncAttBtn", st["attBtn"] is False, st)
        check("空位卡还在（加图靠它）", st["slots"] >= 1, st)
        check("面板「生成」按钮正常", st["sendVisible"], st)
        check("面板不溢出", st["overflow"] <= 1, st)

        if st["slots"] >= 1:
            picked = pg.evaluate("""() => {
              const inp = document.getElementById('sncFileInput');
              window.__picked = 0;
              inp.click = function(){ window.__picked++; };
              document.querySelector('.snc-att-slot').click();
              return window.__picked;
            }""")
            check("点空位卡确实去选图", picked == 1, picked)

        ctx.close()
        b.close()

    print("-" * 46)
    print("通过 %d / 共 %d 项，失败 %d" % (PASS, PASS + FAIL, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
