# -*- coding: utf-8 -*-
"""v3.5.1 回归：安全边界、保存一致性、拖动残留、重复提交。

A 段：源码断言（白名单 / 跨站 / 单事务 / 防重 / 选区守卫）。
B 段：HTTP 黑盒（自起一个桥接进程，不依赖外部服务）。
C 段：浏览器交互（选中文字后拖顶栏、连点重新生成、切画布不中断、进度环）。
"""
import json
import os
import socket
import subprocess
import sys
import time

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
DIST_HTML = os.path.join(ROOT, "proto", "canvas.html")

sys.path.insert(0, os.path.join(ROOT, "proto"))
import server  # noqa: E402

src = open(SRC, encoding="utf-8").read()
py = open(SERVER, encoding="utf-8").read()
dist = open(DIST_HTML, encoding="utf-8").read()

print("\n== A  源码 / 后端 ==")
check("版本号 >= 3.5.1", server._ver_key(server.APP_VERSION) >= server._ver_key("3.5.1"),
      server.APP_VERSION)

# ---- 静态资源白名单 ----
check("静态目录改成白名单", "STATIC_FILES = {" in py)
check("白名单只有页面与图标",
      '"/canvas.html": "canvas.html"' in py and '"/app.ico": "app.ico"' in py)
check("get 不再拼任意路径", "os.path.join(root, rel)" not in py)
check("白名单外一律 404", 'name = STATIC_FILES.get(path)' in py and '"not found"}, 404' in py)

# ---- 跨站与内容类型 ----
check("POST 先过 _api_guard", "if not self._api_guard():" in py)
check("校验 Origin 只认本机", 'host not in ("127.0.0.1", "localhost", "::1")' in py)
check("跨站请求记日志并 403", "blocked cross-site POST" in py)
check("带 body 必须 application/json", 'ctype != "application/json"' in py)
check("请求体有上限", "MAX_BODY_BYTES" in py and "413" in py)
check("_read_json 超限不读", "if length > MAX_BODY_BYTES:" in py)
check("连接被掐不再刷 traceback", "ConnectionResetError, ConnectionAbortedError, BrokenPipeError" in py)

# ---- 供应商判定 ----
check("未知供应商不再静默回退", "未知的供应商" in py)
check("未知供应商返回 400", '"provider", "未知的供应商' in py and "400)" in py)
check("没指定模型时用该家自己的配置", "want_model = provider_model(pid, env)" in py)
check("参考图校验对所有供应商生效", 'if pid == "sensenova":\n            ref_error' not in py
      and "ref_error = validate_ref_images(images)" in py
      # v3.7.7：图层拆分（want_layers）不套 3:1 校验，交给上游判
      and "if images and not want_layers:" in py)

# ---- 配置读取 ----
check(".env 读取有缓存", '_ENV_CACHE' in py and "_env_sig" in py)
check("写入后缓存失效", '_ENV_CACHE["sig"] = None' in py)

# ---- 版本比较 ----
check("版本号按段比较", "def _ver_key" in py)
check("hasUpdate 只认更大的版本", "_ver_key(latest) > _ver_key(APP_VERSION)" in py)
check("旧清单不提示更新", server._ver_key("3.4.9") < server._ver_key("3.5.1"))
check("更新清单才提示", server._ver_key("3.6.0") > server._ver_key("3.5.1"))

# ---- Seedream 通道缓存 ----
check("通道缓存带 key 指纹", "def _seedream_tag" in py and '(key or "")[-8:]' in py)
check("缓存 key 用 tag", "_SEEDREAM_CHANNEL.get(tag)" in py and "_SEEDREAM_CHANNEL[_seedream_tag(entry, key)]" in py)

# ---- 前端：拖动 ----
check("顶栏选区守卫已删除", "String(window.getSelection()).length) return" not in src)
check("顶栏仍绑定拖动", 'top.addEventListener("mousedown"' in src and 'a.win_drag("move")' in src)

# ---- 前端：任务生命周期 ----
check("cancelJob 不再用 rAF id", "cancelAnimationFrame(n._job); n._job = null;" not in src)
check("cancelJob 有真的 abort", "if(job.abort) job.abort();" in src)
check("取消会收掉定时器", "if(job.tick) clearInterval(job.tick);" in src)
check("取消标记为已取消", '"已取消"' in src)
check("startJob 建 AbortController", "new window.AbortController()" in src)
check("请求带 signal", "if(spec.signal) init.signal = spec.signal;" in src)
check("同一张卡不能重复提交", "if(n._job || inQueue(n))" in src and "function inQueue(n)" in src)
check("排队任务按归属画布判活", "if(!item.n || !boardOf(item.n)) continue;" in src)
check("切画布不再掐断生成", "cancelAllJobs();\n    activeId = id;" not in src)

# ---- 前端：保存一致性 ----
check("分片与元信息同一事务", 'db.transaction([STORE, STORE_CHUNK], "readwrite")' in src)
check("idbPut 不再分两次写", "idbPutChunks" not in src)
check("保存失败有提示", "function saveFailed" in src and "本机保存失败" in src)
check("失败徽标标红", "is-err" in src and "保存失败" in src)
check("失败不再静默", ".then(null, function(){ /* 存不下不阻塞交互 */ })" not in src)
check("分片缺失要标出来", "obj.imgLost = 1" in src)
check("丢图卡片明确报错", "图片数据丢失" in src)
check("分片读失败不当成空", 'idbTx(STORE_CHUNK, "readonly", function(s){ return s.getAll(); }).then(null, function(){ return []; })' not in src)
check("结果存回自己的画布", "var owner = boardOf(n);" in src and "else saveBoard(owner);" in src)

# ---- 前端：体积与显示 ----
check("进度环过渡短于刷新周期", "transition:stroke-dashoffset .09s linear" in src)
check("缩略图 JPEG 铺白底", 'ctx.fillStyle = "#fff";' in src)
check("历史版本 JPEG 也铺白底", 'cx.fillStyle = "#fff";' in src)
check("窗口状态轮询降到 1.2s", "}, 1200);" in src and "if(document.hidden) return;" in src)

# ---- 打包产物是新的 ----
check("dist 页面已重建", "transition:stroke-dashoffset .09s linear" in dist)
check("dist 页面含新的保存逻辑", "本机保存失败" in dist)

print("\n== B  HTTP 黑盒 ==")
import requests  # noqa: E402


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


PORT = free_port()
BASEP = "http://127.0.0.1:%d" % PORT
proc = subprocess.Popen([sys.executable, os.path.join(HERE, "serve.py")],
                        env=dict(os.environ, SNC_PORT=str(PORT)),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
up = False
for _ in range(80):
    try:
        requests.get(BASEP + "/api/update/check", timeout=1)
        up = True
        break
    except Exception:
        time.sleep(0.2)
check("桥接进程已起", up, PORT)

if up:
    for path in ("/.env", "/server.py", "/canvas.src.html", "/update.json", "/../server.py"):
        r = requests.get(BASEP + path, timeout=5)
        check("GET %s 被挡" % path, r.status_code == 404, r.status_code)
    r = requests.get(BASEP + "/canvas.html", timeout=10)
    check("GET /canvas.html 正常", r.status_code == 200 and len(r.content) > 100000,
          (r.status_code, len(r.content)))
    r = requests.get(BASEP + "/", timeout=10)
    check("根路径仍指向页面", r.status_code == 200 and b"snc" in r.content[:4000], r.status_code)

    r = requests.post(BASEP + "/api/verify", data=json.dumps({}),
                      headers={"Origin": "https://evil.example",
                               "Content-Type": "application/json"}, timeout=5)
    check("跨站 Origin 被拒", r.status_code == 403, r.status_code)
    r = requests.post(BASEP + "/api/verify", data="{}",
                      headers={"Origin": "https://evil.example",
                               "Content-Type": "text/plain"}, timeout=5)
    check("跨站 simple request 被拒", r.status_code == 403, r.status_code)
    r = requests.post(BASEP + "/api/verify", data="{}",
                      headers={"Origin": "http://127.0.0.1:%d" % PORT,
                               "Content-Type": "text/plain"}, timeout=5)
    check("本机但非 JSON 也被拒", r.status_code == 415, r.status_code)
    r = requests.post(BASEP + "/api/generate", data=json.dumps({}),
                      headers={"Origin": "http://127.0.0.1:%d" % PORT,
                               "Content-Type": "application/json"}, timeout=5)
    check("本机 JSON 正常放行", r.status_code == 400 and "prompt" in r.text, r.text[:80])
    r = requests.post(BASEP + "/api/generate",
                      data=json.dumps({"prompt": "x", "provider": "nope"}),
                      headers={"Content-Type": "application/json"}, timeout=5)
    check("未知供应商返回 400 而不是偷偷出图",
          r.status_code == 400 and "未知的供应商" in r.text, (r.status_code, r.text[:120]))

    # 超大 Content-Length：只发头不发 body，服务端应当在读之前就 413
    try:
        s = socket.create_connection(("127.0.0.1", PORT), timeout=5)
        s.sendall(b"POST /api/verify HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                  b"Content-Type: application/json\r\nContent-Length: 999999999\r\n\r\n")
        head = s.recv(200).decode("latin-1")
        s.close()
        check("超大请求体直接 413", " 413 " in head.split("\r\n")[0], head.split("\r\n")[0])
    except OSError as exc:
        check("超大请求体直接 413", False, exc)

proc.terminate()
try:
    proc.wait(timeout=5)
except subprocess.TimeoutExpired:
    proc.kill()

print("\n== C  浏览器 ==")
from playwright.sync_api import sync_playwright  # noqa: E402

# 这一段自己起一个桥接进程，不依赖外部服务
PORT = free_port()
BASE = "http://127.0.0.1:%d" % PORT
proc = subprocess.Popen([sys.executable, os.path.join(HERE, "serve.py")],
                        env=dict(os.environ, SNC_PORT=str(PORT)),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(80):
    try:
        requests.get(BASE + "/api/update/check", timeout=1)
        break
    except Exception:
        time.sleep(0.2)

PNG = ("iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAAWklEQVR4nO3QMQEAAAjDMMC/56"
       "EBT1JQ1M3tOQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
       "AAAA4G8GmAABkVXyWQAAAABJRU5ErkJggg==")
errs = []
hits = {"n": 0, "mode": "fail"}

CARD = ".snc-node:has(.snc-photo)"
REGEN = '#sncImgBar [data-act="regen"]'


def click_regen(page, times=1, gap=0):
    """连点直接重跑测试钩子，模拟用户手快连击。

    v3.7.6 起 UI 的「重新生成」改成「回填编辑框 + 派生新卡」（不发请求），
    版本链 / 并发上限 / 进度环这些自检需要一条不走编辑框的入口。
    """
    page.evaluate("""(n) => {
        for(let i = 0; i < n; i++) window.SNC_TEST_API.rerun();
    }""", times)


def vstrip(page):
    return page.evaluate("""() => {
        const h = document.querySelector('.snc-node .snc-vstrip span');
        return h ? h.textContent : '';
    }""")


with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    ctx = br.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    # 假桥：只为验证拖动入口会不会被调，不进真实窗口
    ctx.add_init_script("""
      window.__drag = 0;
      window.pywebview = {api: {
        win_state: function(){ return Promise.resolve({ok:true, maximized:false}); },
        win_drag: function(z){ window.__drag++; return Promise.resolve({ok:true, zone:z}); },
        win_max: function(){ return Promise.resolve({ok:true, maximized:true}); },
        win_hide: function(){ return Promise.resolve({ok:true}); },
        win_close: function(){ return Promise.resolve({ok:true}); }
      }};
    """)
    page = ctx.new_page()
    page.on("pageerror", lambda e: errs.append(str(e)))

    def gen(route):
        hits["n"] += 1
        if hits["mode"] == "fail":
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": False, "code": "auth",
                                           "provider": "sensenova",
                                           "error": "鉴权失败（401）：API Key 无效，请到控制台重新签发后再试"}))
            return
        page.wait_for_timeout(1500)
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True, "b64": PNG, "size": "1024x1024",
                                       "width": 1024, "height": 1024, "format": "png",
                                       "model": "sensenova-u1.5-fast", "provider": "sensenova",
                                       "latencyMs": 1500}))

    page.route("**/api/generate", gen)
    page.goto(BASE + "/canvas.html")
    page.wait_for_selector(CARD)
    page.wait_for_timeout(900)

    # ---- C1 页面上留着选区时，顶栏还能拖 ----
    page.click(CARD)
    page.wait_for_timeout(350)
    hits["mode"] = "fail"
    click_regen(page)
    page.wait_for_timeout(900)
    sel_len = page.evaluate("""() => {
        const el = document.querySelector('.snc-fail-msg');
        if(!el) return -1;
        const r = document.createRange(); r.selectNodeContents(el);
        const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
        return String(s).length;
    }""")
    before = page.evaluate("() => window.__drag")
    page.evaluate("""() => {
        const top = document.querySelector('#snc .snc-top');
        top.dispatchEvent(new MouseEvent('mousedown',
          {bubbles:true, cancelable:true, button:0, clientX:430, clientY:6}));
    }""")
    page.wait_for_timeout(150)
    after = page.evaluate("() => window.__drag")
    check("失败卡上选中文字后顶栏仍可拖", sel_len > 0 and after > before, (sel_len, before, after))

    # ---- C2 连点两次「重新生成」只发一个请求 ----
    page.evaluate("() => window.getSelection().removeAllRanges()")
    page.wait_for_timeout(200)
    hits["mode"] = "slow"
    hits["n"] = 0
    click_regen(page, times=2)
    page.wait_for_timeout(500)
    mid = hits["n"]
    again = page.inner_text("#sncToast")
    page.wait_for_timeout(2000)
    check("连点两次只发一个请求", mid == 1 and hits["n"] == 1, (mid, hits["n"]))
    check("连点第二次给了提示", "正在生成中" in again or "队列里" in again, again)
    page.wait_for_timeout(400)

    # ---- C3 生成中切画布，结果回到自己那张画布并落盘 ----
    page.click(CARD)
    page.wait_for_timeout(300)
    vorher = vstrip(page)
    hits["mode"] = "slow"
    click_regen(page)
    page.wait_for_timeout(200)
    page.click("#sncDocNew")
    page.wait_for_timeout(1900)
    items = page.query_selector_all(".snc-doc-item")
    check("新建画布后列表有两张", len(items) >= 2, len(items))
    if len(items) >= 2:
        items[1].click()
        page.wait_for_timeout(800)
    nachher = vstrip(page)
    check("切回来能看到新增的那一版", nachher and nachher != vorher, (vorher, nachher))
    page.reload()
    page.wait_for_selector(CARD)
    page.wait_for_timeout(1000)
    nach_reload = vstrip(page)
    check("重新加载后新版本仍在（存进了原画布）", nach_reload == nachher,
          (nachher, nach_reload))

    # ---- C4 进度环不落后于数字 ----
    page.click(CARD)
    page.wait_for_timeout(300)
    hits["mode"] = "slow"
    click_regen(page)
    worst = 0
    seen = 0
    for _ in range(9):
        page.wait_for_timeout(230)
        # v3.7.5：进度环从 rect + pathLength=100 换成 path + 真实周长，
        # dasharray / dashoffset 都是像素了，要按周长折算回百分比再和徽标比。
        s = page.evaluate("""() => {
            const b = document.querySelector('.snc-prog-pct');
            const r = document.querySelector('.snc-prog-ring path');
            if(!b || !r) return null;
            const cs = getComputedStyle(r);
            const P = parseFloat((cs.strokeDasharray || '0').split(/[\\s,]+/)[0]) || 0;
            const off = parseFloat(cs.strokeDashoffset || '0');
            return {badge: parseFloat(b.textContent) || 0,
                    drawn: P ? (1 - off / P) * 100 : 0};
        }""")
        if s:
            seen += 1
            worst = max(worst, abs(s["badge"] - s["drawn"]))
    check("采到进度环", seen >= 3, seen)
    check("进度环与数字偏差 ≤3 个百分点", worst <= 3.0, "%.1f" % worst)

    check("页面无 JS 异常", not errs, errs[:2])
    br.close()

proc.terminate()
try:
    proc.wait(timeout=5)
except subprocess.TimeoutExpired:
    proc.kill()

print("\nv3.5.1 结果：%d 项通过，%d 项失败" % (PASS, FAIL))
if FAILS:
    for name, extra in FAILS:
        print("  -", name, extra)
sys.exit(1 if FAIL else 0)
