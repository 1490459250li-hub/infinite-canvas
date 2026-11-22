# -*- coding: utf-8 -*-
"""v3.7.4 第一批回归：启动反馈 + 撤销栈瘦身 + 两处视觉。

A 段：源码 / 后端断言（惰性 import、启动画面、撤销栈结构、CSS）
B 段：浏览器里真跑 —— 快照体积、撤销正确性、层数上限、引用释放、失败卡与技能卡样式
"""
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
SERVER_PY = os.path.join(ROOT, "proto", "server.py")

sys.path.insert(0, os.path.join(ROOT, "proto"))
import server  # noqa: E402

# 必须在任何 HTTP 调用之前检查
LAZY_BEFORE = server._REQ["mod"] is None
PROXY = type(server.requests).__name__
FIRST = server.requests.post                      # 第一次访问才真的 import
LAZY_AFTER = server._REQ["mod"] is not None
SECOND_SAME = server.requests is server._REQ["mod"]   # 全局名已被真模块顶替

src = open(SRC, encoding="utf-8").read()
py = open(SERVER_PY, encoding="utf-8").read()

# ======================================================================
# A. 惰性 import
# ======================================================================
print("\n== A  启动反馈 ==")
check("版本 >= 3.7.3", server._ver_key(server.APP_VERSION) >= server._ver_key("3.7.3"),
      server.APP_VERSION)
check("有 ensure_requests", hasattr(server, "ensure_requests"))
check("import 完 requests 还没加载", LAZY_BEFORE, "已加载")
check("全局名上放的是惰性代理", PROXY == "_LazyRequests", PROXY)
check("第一次用到属性时才真的 import", LAZY_AFTER)
check("之后全局名换成真模块（后续零开销）", SECOND_SAME)
check("顶层没有裸 import requests", "\ntry:\n    import requests" not in py)
check("没退回模块级 __getattr__（裸名查找不走它）", "def __getattr__(name)" not in py)
# 测试常靠 server.requests.post = fake 打桩，代理必须像真模块一样能被赋值
server.requests._probe_attr = 1
check("代理可被赋值（打桩不会炸）", getattr(server.requests, "_probe_attr", 0) == 1)

# ---- 启动画面 ----
check("splash_show / splash_text / splash_close 都在",
      all(hasattr(server, f) for f in ("splash_show", "splash_text", "splash_close")))
check("不依赖 tkinter（精简版 Python 没有 tcl/tk）", "import tkinter" not in py)
check("窗口类名固定，便于外部识别", "SncSplashWnd" in py)
check("置顶 + 不占任务栏（TOPMOST|TOOLWINDOW）", "0x00000008 | 0x00000080" in py)
check("圆角靠 SetWindowRgn 裁", "CreateRoundRectRgn" in py and "SetWindowRgn" in py)
check("窗口加载后自动让位", "splash_close()" in py.split("def on_loaded")[1].split("def ")[0])
check("main 里先出框、再起服务",
      py.index("splash_show()") < py.index("server.serve_forever"),
      "顺序反了")
check("启动时会给一句「正在启动渲染内核」", "正在启动渲染内核" in py)

if os.name == "nt":
    import ctypes
    u = ctypes.windll.user32
    shown = server.splash_show()
    time.sleep(0.35)
    hwnd = u.FindWindowW("SncSplashWnd", None)
    check("启动画面真的画出来了", shown and bool(hwnd), "show=%s hwnd=%s" % (shown, hwnd))
    check("窗口可见", bool(u.IsWindowVisible(hwnd)) if hwnd else False)
    server.splash_text("正在启动渲染内核…")
    server.splash_close()
    time.sleep(0.5)
    check("关掉之后窗口不存在", not u.FindWindowW("SncSplashWnd", None))
    server.splash_close()
    check("重复关闭不报错", not server._SPLASH.get("hwnd"))

# ======================================================================
# B. 撤销栈
# ======================================================================
print("\n== B  撤销栈 ==")
check("层数上限 50", "var UNDO_MAX = 50;" in src)
check("短字符串不外置（ART_MIN）", "var ART_MIN = 2048;" in src)
for name in ("function snapOut", "function snapIn", "function artDrop", "function undoReset"):
    check("有 %s" % name.replace("function ", ""), name in src)
check("快照不再把整份节点序列化进栈",
      "undoStack.push(JSON.stringify(state.nodes))" not in src)
check("快照走 snapOut + stringify", "JSON.stringify(snapOut(state.nodes, ids))" in src)
without_reset = src.replace(src.split("function undoReset")[1].split("}")[0], "")
check("切画布时整栈重置",
      "undoReset();" in src and "undoStack.length = 0;" not in without_reset)
check("撤销时把图贴回去", "snapIn(JSON.parse(rec.snap))" in src)
check("撤销后释放没人引用的图", "artDrop(rec)" in src)
check("快照统计入口给测试用", "window.SNC_UNDO_STATS" in src)
check("测试入口只暴露必要方法", "window.SNC_TEST_API" in src)

# ======================================================================
# C. 两处视觉（源码层）
# ======================================================================
print("\n== C  视觉 ==")
check("失败卡有小圆点", 'class="snc-fail-dot"' in src and "#snc .snc-fail-dot{" in src)
check("失败卡标题改中性色", "#snc .snc-gen-fail b{" in src and "color:var(--ink2)" in
      src.split("#snc .snc-gen-fail b{")[1].split("}")[0])
check("失败卡按钮不再用 err 描边",
      "background:transparent; color:var(--ink3); border:1px solid var(--line2);" in src)
check("技能卡缩略图有渐变遮罩",
      "#snc .snc-skp-tile.has-art .snc-skp-art::after" in src
      and "rgba(6,7,9,.95)" in src)
check("技能名字不再靠自身渐变（改由遮罩承担）",
      "background:linear-gradient(transparent, rgba(5,6,8,.96))" not in src)
check("技能名字加双层投影", "0 1px 2px rgba(0,0,0,.95), 0 0 10px rgba(0,0,0,.55)" in src)

# ======================================================================
# D. 浏览器
# ======================================================================
print("\n== D  浏览器 ==")
try:
    from playwright.sync_api import sync_playwright  # noqa: E402
    import requests  # noqa: E402

    def free_port():
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

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
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(channel="msedge")
            ctx = br.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1');"
                                "localStorage.setItem('snc.theme.v1','dark');}catch(e){}")
            page = ctx.new_page()
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(BASE + "/canvas.html")
            page.wait_for_selector(".snc-node")
            page.wait_for_timeout(1000)

            check("页面加载无报错", not errs, errs[:2])
            check("自检入口可用",
                  page.evaluate("() => typeof window.SNC_TEST_API === 'object'"))

            made = page.evaluate("""() => {
                function mk(seed){
                    const c = document.createElement('canvas');
                    c.width = 800; c.height = 600;
                    const x = c.getContext('2d');
                    x.fillStyle = 'rgb(' + (seed*37%255) + ',' + (seed*91%255) + ',' +
                                   (seed*53%255) + ')';
                    x.fillRect(0,0,800,600);
                    for(let i=0;i<600;i++){
                        x.fillStyle = 'rgba(' + (i*seed%255) + ',' + (i*7%255) + ',' +
                                       (i*13%255) + ',.75)';
                        x.fillRect((i*seed*13)%800, (i*seed*7)%600, 26, 20);
                    }
                    return c.toDataURL('image/jpeg', 0.9);
                }
                const imgs = [mk(3), mk(11), mk(29)];
                const N = window.SNC_TEST_API.nodes();
                const before = N.length;
                for(let i=0;i<12;i++){
                    const u = imgs[i % 3];
                    N.push({id:'t'+i, kind:'image', status:'done',
                        x:(i%4)*320, y:Math.floor(i/4)*280, w:280, h:210,
                        dataUrl:u, prompt:'p'+i,
                        versions:[{dataUrl:u, model:'m', latencyMs:100, usage:{}}],
                        vIndex:0});
                }
                return {before, after:N.length, kb: Math.round(imgs[0].length/1024)};
            }""")
            check("12 个带图节点造出来了", made["after"] - made["before"] == 12, made)

            fp_js = """() => {
                const n = window.SNC_TEST_API.nodes().find(
                    x => x.versions && x.versions.length && (x.dataUrl || '').length > 1000);
                const u = n.versions[0].dataUrl;
                return {len: u.length, head: u.slice(0, 60), tail: u.slice(-40)};
            }"""
            fp = page.evaluate(fp_js)

            for _ in range(6):
                page.evaluate("() => { window.SNC_TEST_API.snapshot();"
                              " window.SNC_TEST_API.nodes().pop(); }")
            st = page.evaluate("() => window.SNC_UNDO_STATS()")
            check("6 层快照都在", st["layers"] == 6, st)
            check("三张不同的图只存了一份", st["arts"] == 3, st["arts"])
            check("快照体积远小于图本身",
                  st["snapBytes"] < st["artBytes"] // 4,
                  "snap=%d art=%d" % (st["snapBytes"], st["artBytes"]))
            print("       快照 %d B / 图池 %d B（老实现约 %d B）"
                  % (st["snapBytes"], st["artBytes"], st["artBytes"] * 6))

            for _ in range(5):
                page.evaluate("() => window.SNC_TEST_API.undo()")
                page.wait_for_timeout(50)
            page.wait_for_timeout(250)
            check("撤销后节点数对得上",
                  page.evaluate("() => window.SNC_TEST_API.nodes().length")
                  == made["after"] - 1)
            check("撤销后图一个字节不差", page.evaluate(fp_js) == fp)

            page.evaluate("""() => {
                for(let i=0;i<56;i++){
                    const c = document.createElement('canvas');
                    c.width = 600; c.height = 400;
                    const x = c.getContext('2d');
                    x.fillStyle = 'rgb(' + (i*17%255) + ',90,' + (i*29%255) + ')';
                    x.fillRect(0,0,600,400);
                    const u = c.toDataURL('image/jpeg',0.9);
                    window.SNC_TEST_API.nodes().push({id:'x'+i, kind:'image',
                        status:'done', x:0, y:0, w:200, h:140, dataUrl:u, prompt:'q'+i,
                        versions:[{dataUrl:u, model:'m', latencyMs:1, usage:{}}],
                        vIndex:0});
                    window.SNC_TEST_API.snapshot();
                }
            }""")
            st2 = page.evaluate("() => window.SNC_UNDO_STATS()")
            check("超过 50 层后自动丢最老的", st2["layers"] == 50, st2["layers"])

            for _ in range(50):
                page.evaluate("() => window.SNC_TEST_API.undo()")
            page.wait_for_timeout(300)
            st3 = page.evaluate("() => window.SNC_UNDO_STATS()")
            check("撤到底层数归零", st3["layers"] == 0, st3["layers"])
            check("没人引用的图被放掉", st3["arts"] == 0, st3["arts"])
            check("快照统计也归零", st3["snapBytes"] == 0, st3["snapBytes"])
            check("反复撤销没有新报错", not errs, errs[:2])

            # ---- 失败卡样式 ----
            page.evaluate("""() => {
                const N = window.SNC_TEST_API.nodes();
                N.push({id:'failcase', kind:'image', status:'failed', x:0, y:0,
                        w:280, h:210, prompt:'失败示例',
                        error:'connect timeout after 90s', versions:[], vIndex:0});
                window.SNC_TEST_API.render();
            }""")
            page.wait_for_timeout(400)
            fail = page.evaluate("""() => {
                const b = document.querySelector('.snc-gen-fail');
                if(!b) return null;
                const dot = b.querySelector('.snc-fail-dot');
                const t = b.querySelector('b');
                const btn = b.querySelector('.snc-fail-retry');
                const cd = dot ? getComputedStyle(dot) : null;
                return {hasDot: !!dot,
                        dotW: cd ? Math.round(parseFloat(cd.width)) : -1,
                        title: t ? t.textContent : '',
                        titleColor: t ? getComputedStyle(t).color : '',
                        btnBg: btn ? getComputedStyle(btn).backgroundColor : ''};
            }""")
            check("失败卡渲染出来了", bool(fail), fail)
            if fail:
                check("有小圆点且是 6px", fail["hasDot"] and fail["dotW"] == 6, fail)
                check("标题文案没变", fail["title"] == "生成失败", fail["title"])
                check("标题不再是亮橙", fail["titleColor"] != "rgb(224, 112, 79)",
                      fail["titleColor"])
                check("按钮透明底（不抢眼）",
                      fail["btnBg"].startswith("rgba(0, 0, 0, 0)") or fail["btnBg"] == "transparent",
                      fail["btnBg"])

            # ---- 技能卡名字可读 ----
            pt = page.evaluate("""() => {
                const t = Array.from(document.querySelectorAll('.snc-node')).find(
                    n => n.querySelector('.snc-gen img'));
                const r = t.getBoundingClientRect();
                return {x: r.x + r.width/2, y: r.y + r.height/2};
            }""")
            page.mouse.click(pt["x"], pt["y"])
            page.wait_for_timeout(350)
            page.click('#sncImgBar button[data-act="skill"]')
            page.wait_for_timeout(600)
            tile = page.evaluate("""() => {
                const t = document.querySelector('#sncSkpBody .snc-skp-tile.has-art');
                if(!t) return null;
                const art = t.querySelector('.snc-skp-art');
                const em = t.querySelector('em');
                const after = art ? getComputedStyle(art, '::after') : null;
                return {afterBg: after ? after.backgroundImage : '',
                        emShadow: em ? getComputedStyle(em).textShadow : '',
                        emBg: em ? getComputedStyle(em).backgroundImage : ''};
            }""")
            check("技能卡存在", bool(tile), tile)
            if tile:
                check("缩略图底部有渐变遮罩", "gradient" in tile["afterBg"], tile["afterBg"])
                check("名字有投影", tile["emShadow"] not in ("none", ""), tile["emShadow"])
                check("名字自身不再叠一层渐变", tile["emBg"] == "none", tile["emBg"])

            br.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
except Exception as exc:  # noqa: BLE001
    import traceback
    traceback.print_exc()
    check("浏览器段没崩", False, str(exc)[:160])

print("\n== 合计 %d 项 · 失败 %d ==" % (PASS + FAIL, FAIL))
if FAILS:
    print("\n失败明细：")
    for n, e in FAILS:
        print("  -", n, "->", e)
    sys.exit(1)
