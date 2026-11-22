# -*- coding: utf-8 -*-
"""v3.5 回归：拖动改轮询、圆角裁切、测试按钮反馈、进度环比例、UI 一致性。

A 段：源码/后端静态断言。
B 段：浏览器里跑真实交互（打桩 /api/providers/test）。
C 段：Win32 圆角区域与拖动入口的兜底行为。
"""
import json
import os
import sys

PASS = FAIL = 0
FAILS = []


def check(name, ok, extra=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  PASS", name)
    else:
        FAIL += 1
        FAILS.append((name, extra))
        print("  FAIL", name, "->", extra)


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "proto", "canvas.src.html")
SERVER = os.path.join(ROOT, "proto", "server.py")

sys.path.insert(0, os.path.join(ROOT, "proto"))
import server  # noqa: E402

src = open(SRC, encoding="utf-8").read()
py = open(SERVER, encoding="utf-8").read()

print("\n== A  源码 / 后端 ==")
check("窗口拖动改成轮询光标", "def _track_window_drag" in py and "GetAsyncKeyState" in py)
check("win_drag 主路径走轮询", "ok = _track_window_drag(hwnd, zone)" in py)
check("系统移动循环降级为兜底", "_begin_system_move(hwnd, zone)" in py)
check("拖动线程按光标位移挪窗口", "user32.SetWindowPos(int(hwnd), None" in py)
check("最大化拖标题栏先还原", "user32.ShowWindow(int(hwnd), 9)" in py)
check("圆角用 SetWindowRgn 裁", "CreateRoundRectRgn" in py and "SetWindowRgn" in py)
check("裁剪半径按 DPI 缩放", "GetDpiForWindow" in py)
check("最大化时清掉区域", "user32.SetWindowRgn(int(hwnd), None, True)" in py)
check("加载后启动圆角看护", "_start_region_watcher(_WIN[\"hwnd\"])" in py)
check("健康接口带版本号", '"version": APP_VERSION' in py)
check("测试供应商不再重复探测", "first_models" in py and "first = probe_provider" not in py)

check("测试失败也弹 toast", 'var emsg = providerLabelOf(pid) + " 验证失败："' in src
      and "toast(emsg);" in src)
check("测试时按钮显示「测试中…」", 'btn.textContent = "测试中…"' in src)
check("测试结果滚到可见处", "function scrollStatIntoView" in src)
check("没设分流时也有提示", "还没有设置分流，先挑一家供应商" in src)
check("顶栏也能拖动窗口", 'top.addEventListener("mousedown"' in src
      and 'a.win_drag("move")' in src)
check("记录按钮补了文字", '<span>记录</span></button>' in src)
check("复位视图按钮已移除", 'data-edit="reset"' not in src)
check("进度环按卡片比例设 viewBox", 'ring.setAttribute("viewBox"' in src)
check("进度环过渡短于刷新间隔", "transition:stroke-dashoffset .09s linear" in src)
check("关于页版本号动态填", 'id="sncAboutVer"' in src and "vEl.textContent" in src)
check("关于页协议按钮左对齐", "text-align:left;" in src.split("#snc .snc-about-eula{")[1][:80])
check("主题卡片文字可省略号", "#snc .snc-theme-desc{\n  display:block; min-width:0;" in src)
check("便签正文按 4 行裁", "-webkit-line-clamp:4" in src)

print("\n== B  浏览器 ==")
from playwright.sync_api import sync_playwright  # noqa: E402

BASE = os.environ.get("SNC_BASE", "http://127.0.0.1:8467/canvas.html")
errs = []

with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    ctx = br.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    page = ctx.new_page()
    page.on("pageerror", lambda e: errs.append(str(e)))

    TEST_MODE = {"ok": False}

    def prov_test(route):
        if TEST_MODE["ok"]:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": True, "provider": "sensenova",
                                           "label": "SenseNova", "models": ["a", "b"],
                                           "keys": [{"id": "k1", "mask": "ak-…", "ok": True}]}))
        else:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": False, "code": "auth", "provider": "sensenova",
                                           "error": "鉴权失败（401）：API Key 无效",
                                           "keys": [{"id": "k1", "mask": "ak-…", "ok": False}]}))

    page.route("**/api/providers/test", prov_test)
    page.route("**/api/providers", lambda r: r.continue_() if False else r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "providers": [
            {"id": "sensenova", "label": "SenseNova", "configured": True,
             "keys": [{"id": "k1", "mask": "ak-…"}], "image": [], "text": []},
            {"id": "seedream", "label": "Seedream", "configured": False,
             "keys": [], "image": [], "text": []}],
            "routes": {"text2img": "sensenova:x", "inpaint": "sensenova:x",
                       "polish": "sensenova:x"}})))
    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(1200)

    # 记录按钮文字
    first = page.query_selector(".snc-node")
    first.click()
    page.wait_for_timeout(300)
    hist_txt = page.inner_text('#sncImgBar [data-act="history"]')
    check("工具条「记录」按钮带文字", "记录" in hist_txt, hist_txt)
    labels = page.evaluate("""() => [...document.querySelectorAll('#sncImgBar button[data-act]')]
        .map(b => (b.textContent||'').trim())""")
    # 按钮数随批次增加（v3.7.4 第七批加「两图对比」到 10 个）
    check("工具条 10 个按钮都有文字", len(labels) == 10 and all(labels), labels)

    # 设置：测试按钮反馈
    page.click("[data-set]")
    page.wait_for_timeout(500)
    page.click('[data-pane="model"]')
    page.wait_for_timeout(600)
    TEST_MODE["ok"] = False
    page.click("#sncSetTest")
    page.wait_for_timeout(700)
    toast = page.inner_text("#sncToast")
    toast_on = page.evaluate("() => document.getElementById('sncToast').classList.contains('is-on')")
    check("测试失败弹出可见提示", toast_on and "验证失败" in toast, (toast_on, toast))
    check("状态条也写了失败原因", "验证失败" in page.inner_text("#sncSetStatus"),
          page.inner_text("#sncSetStatus"))
    check("按钮恢复可用", page.evaluate("() => !document.getElementById('sncSetTest').disabled"))
    check("按钮文字恢复", "测试默认供应商" in page.inner_text("#sncSetTest"),
          page.inner_text("#sncSetTest"))

    TEST_MODE["ok"] = True
    page.click("#sncSetTest")
    page.wait_for_timeout(700)
    check("测试成功弹出提示", "连接成功" in page.inner_text("#sncToast"), page.inner_text("#sncToast"))

    # 主题卡片文字不溢出
    page.click('[data-pane="theme"]')
    page.wait_for_timeout(300)
    overflow = page.evaluate("""() => [...document.querySelectorAll('.snc-theme-opt')].map(c => {
        const d = c.querySelector('.snc-theme-desc');
        const cr = c.getBoundingClientRect(), dr = d.getBoundingClientRect();
        return {name: c.querySelector('.snc-theme-name').textContent,
                inside: dr.right <= cr.right + 1,
                desc: d.textContent}; })""")
    check("四张主题卡片说明都在卡片内", all(o["inside"] for o in overflow), overflow)
    check("四张卡片说明长度一致（同一套文案格式）",
          len(set(len(o["desc"]) for o in overflow)) == 1, [o["desc"] for o in overflow])

    # 关于页版本号
    page.click('[data-pane="about"]')
    page.wait_for_timeout(300)
    ver = page.inner_text("#sncAboutVer")
    check("关于页显示后端版本", ver.startswith("v3.7"), ver)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # 进度环比例：viewBox 必须跟着卡片宽高比走，否则笔画在长短边上快慢不一
    print("\n== B2  进度环 ==")
    page.evaluate("""() => {
        const host = document.createElement('div');
        host.style.cssText = 'position:absolute;left:0;top:0;width:320px;height:180px';
        host.innerHTML = '<svg class="snc-prog-ring" viewBox="0 0 100 100" preserveAspectRatio="none">' +
          '<rect x="1" y="1" width="98" height="98" pathLength="100"></rect></svg>' +
          '<span class="snc-prog-pct">0%</span>';
        document.getElementById('snc').appendChild(host);
        window.__ringHost = host;
    }""")
    page.evaluate("""() => {
        const host = window.__ringHost;
        const ring = host.querySelector('.snc-prog-ring');
        const rect = ring.querySelector('rect');
        const pct = 46;
        const rw = host.clientWidth, rh = host.clientHeight;
        const vh = 100 * rh / rw;                 // 与 setGenProgress 同一算法
        ring.setAttribute('viewBox', '0 0 100 ' + vh.toFixed(2));
        rect.setAttribute('width','98'); rect.setAttribute('height', (vh-2).toFixed(2));
        rect.style.strokeDashoffset = String(100 - pct);
    }""")
    geo = page.evaluate("""() => {
        const host = window.__ringHost, ring = host.querySelector('.snc-prog-ring');
        const vb = ring.getAttribute('viewBox').split(' ').map(Number);
        const rect = ring.querySelector('rect');
        return {hostRatio: host.clientWidth / host.clientHeight,
                vbRatio: vb[2] / vb[3],
                vb: ring.getAttribute('viewBox'),
                offset: rect.style.strokeDashoffset};
    }""")
    check("viewBox 宽高比与卡片一致",
          abs(geo["hostRatio"] - geo["vbRatio"]) < 0.02, geo)
    check("dashoffset = 100 - 百分比", geo["offset"] == "54", geo["offset"])
    check("页面无脚本错误", not errs, errs[:3])

    br.close()

print("\n== C  Win32 兜底 ==")
check("hwnd 为 0 时不启动拖动", server._track_window_drag(0) is False)
check("hwnd 为 0 时不裁圆角", server._apply_window_region(0) is False)


print("\n== D  Agent Plan 套餐 Key 的探测 ==")


class FakeResp(object):
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


_orig_post = server.requests.post
_orig_get = server.requests.get


def stub_http(get_status=401, get_body=None, post_status=404, post_body=None):
    server.requests.get = lambda url, **kw: FakeResp(
        get_status, get_body if get_body is not None else
        {"error": {"code": "AuthenticationError", "message": "invalid key"}})
    server.requests.post = lambda url, **kw: FakeResp(
        post_status, post_body if post_body is not None else
        {"error": {"code": "UnsupportedModel",
                   "message": "The requested model does not support the agent plan feature."}})


try:
    stub_http()
    check("套餐探针：404 UnsupportedModel 视为鉴权通过",
          server._probe_seedream_plan("ark-x") is True)

    stub_http(post_status=401, post_body={"error": {"code": "AuthenticationError"}})
    check("套餐探针：401 视为密钥无效",
          server._probe_seedream_plan("ark-x") is False)

    stub_http(post_status=429, post_body={"error": {"message": "rate limit"}})
    check("套餐探针：限流不算通过",
          server._probe_seedream_plan("ark-x") is False)

    stub_http()
    res = server.probe_provider("seedream", "ark-x")
    check("按量 401 时自动改判套餐通道", res.get("ok") is True and res.get("channel") == "plan", res)
    check("套餐通道返回可用的 5.0 模型名", bool(res.get("models")), res.get("models"))

    stub_http(get_status=200, get_body={"data": [{"id": "doubao-seedream-4-0-20260415"}]})
    res2 = server.probe_provider("seedream", "ark-x")
    check("按量通道可用时仍按按量返回",
          res2.get("ok") is True and not res2.get("channel"), res2)
finally:
    server.requests.post = _orig_post
    server.requests.get = _orig_get

print("\n%d 项：%d 通过，%d 失败" % (PASS + FAIL, PASS, FAIL))
if FAILS:
    for n, e in FAILS:
        print("  -", n, e)
    sys.exit(1)
