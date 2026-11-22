# -*- coding: utf-8 -*-
"""v3.2 回归：无边框窗口外壳（方案 B）+ 关闭即隐藏 + P1/P4 两个修复。

A–E 纯 Python（直接 import server，不联网、不碰真 .env）
F–J 浏览器（把 window.pywebview.api 打桩，验证点按钮真的调到了对应接口）

真窗口（透明圆角 / 拖动 / 托盘菜单）依赖系统桌面，不在这份用例里。
"""
import os
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
PROTO = os.path.join(os.path.dirname(HERE), "proto")
sys.path.insert(0, PROTO)

import server  # noqa: E402

# ======================================================================
# A. P1：Google 的分辨率不再是空转
#    当初的问题是「界面承诺 4K、实际只有 1024」，所以这一段的立场是
#    **档位必须和真实能力对上**：给得出 4K 的模型才准写 4K，
#    写不出 4K 的模型（Lite）必须老实标 1K。
# ======================================================================
print("\n== A  P1 · Google 分辨率 ==")
g = server.provider_spec("google")
rows = g["image"]
pro = [m for m in rows if m["key"] == "nano-banana-pro"][0]
lite = [m for m in rows if m["key"] == "nano-banana-2-lite"][0]
check("Pro 档的真实能力是 4K", pro["max_side"] == 4096, pro["max_side"])
check("Pro 才准写 4K 徽标", pro["badge"] == "4K", pro["badge"])
check("Lite 档老实标 1K", lite["max_side"] == 1024 and lite["badge"] == "1K",
      (lite["max_side"], lite["badge"]))
check("1K 档不会出现在 4K 里", all(
    m["max_side"] == 1024 or m["badge"] != "1K" for m in rows), [m["badge"] for m in rows])
# 4K 不是只在界面上写着 —— 请求里真的带了 imageSize
check("4K 档位换算成 imageSize", server._google_image_size(4096) == "4K",
      server._google_image_size(4096))
check("2K 档位换算成 imageSize", server._google_image_size(2048) == "2K",
      server._google_image_size(2048))
check("1K 档位换算成 imageSize", server._google_image_size(1024) == "1K",
      server._google_image_size(1024))
check("imageSize 只认大写 K", server._google_image_size(4096) != "4k")
check("其余五家仍是 1440 以上", all(
    m["max_side"] >= 1440
    for pid in ("sensenova", "openai", "seedream", "qwen", "minimax")
    for m in server.provider_spec(pid)["image"]))

# ======================================================================
# B. P4：密钥派生缓存
# ======================================================================
print("\n== B  P4 · PBKDF2 缓存 ==")
salt = b"v32-test-salt!!!"[:16].ljust(16, b"x")
t0 = time.time()
k1 = server._derive_key(salt)
t1 = time.time()
k2 = server._derive_key(salt)
t2 = time.time()
k3 = server._derive_key(salt)
t3 = time.time()

first = t1 - t0
second = t2 - t1
third = t3 - t2
check("首次派生仍走完整 PBKDF2（>10ms）", first > 0.010, "%.4fs" % first)
check("第二次命中缓存（<1ms）", second < 0.001, "%.5fs" % second)
check("第三次同样命中缓存", third < 0.001, "%.5fs" % third)
check("缓存不改变派生结果", k1 == k2 == k3)
check("不同 salt 派生出不同密钥", server._derive_key(b"y" * 16) != k1)
check("机器码只算一次", server._machine_id() == server._machine_id())

# ======================================================================
# C. 图标：托盘/窗口都从 app.ico 取
# ======================================================================
print("\n== C  应用图标 ==")
ico = server._icon_path()
check("能找到 app.ico", bool(ico) and os.path.exists(ico), ico)
check("app.ico 是合法 ICO（头两字节 0,0,1,0）",
      os.path.exists(ico) and open(ico, "rb").read(4) == b"\x00\x00\x01\x00")

# ======================================================================
# D. js_api 不能把窗口对象当公开属性暴露
# ======================================================================
print("\n== D  js_api 暴露面 ==")
api = server.WindowApi()
public = sorted(n for n in dir(api) if not n.startswith("_"))
allowed = {"win_state", "win_min", "win_max", "win_hide", "win_show",
           "win_quit", "win_close", "win_drag",
           # v3.7.5：退出前保存确认完成后，前端回调的关窗入口
           "app_quit"}
check("只暴露窗口控制方法", set(public) <= allowed, public)
check("没有任何公开的 window 属性",
      "window" not in public and "native" not in public, public)
check("窗口引用挂在下划线属性上", hasattr(api, "_window"))

# ======================================================================
# E. 关闭语义：有托盘→隐藏，无托盘→真关
# ======================================================================
print("\n== E  关闭语义 ==")


class FakeWindow:
    def __init__(self):
        self.hidden = self.destroyed = False

    def hide(self):
        self.hidden = True

    def destroy(self):
        self.destroyed = True

    def show(self):
        self.hidden = False

    def restore(self):
        pass

    def minimize(self):
        pass

    def maximize(self):
        pass


class FakeTray:
    def __init__(self, alive=True):
        self._alive = alive
        self.balloons = []

    def alive(self):
        return self._alive

    def balloon(self, title, text):
        self.balloons.append((title, text))


w1 = FakeWindow()
a1 = server.WindowApi()
a1._window = w1
r = a1.win_hide()
check("没有托盘时 × 退化成真关闭", r.get("ok") and w1.destroyed and not w1.hidden, r)

w2 = FakeWindow()
a2 = server.WindowApi()
a2._window = w2
a2._tray = FakeTray(alive=True)
r = a2.win_hide()
check("有托盘时 × 只是隐藏", r.get("ok") and r.get("hidden") and w2.hidden and not w2.destroyed, r)
check("隐藏后弹一次托盘气泡", len(a2._tray.balloons) == 1, a2._tray.balloons)
check("气泡文案提到右键退出",
      a2._tray.balloons and "右键" in a2._tray.balloons[0][1], a2._tray.balloons)

# ======================================================================
# F. 浏览器：窗口外壳只在 shell 模式出现
# ======================================================================
from playwright.sync_api import sync_playwright  # noqa: E402

BASE = os.environ.get("SNC_BASE", "http://127.0.0.1:8321/canvas.html")
SHOTS = r"E:\canvas-probe2\shots-v32"
os.makedirs(SHOTS, exist_ok=True)

STUB = """
window.__calls = [];
window.__maximized = false;
window.pywebview = { api: {
  win_state: function(){ return Promise.resolve({ok:true, frameless:true,
      maximized:window.__maximized, hwnd:1, tray:true}); },
  win_min: function(){ window.__calls.push('min'); return Promise.resolve({ok:true}); },
  win_max: function(){ window.__calls.push('max'); window.__maximized = !window.__maximized;
      return Promise.resolve({ok:true, maximized:window.__maximized}); },
  win_hide: function(){ window.__calls.push('hide'); return Promise.resolve({ok:true, hidden:true}); },
  win_close: function(){ window.__calls.push('close'); return Promise.resolve({ok:true}); },
  win_drag: function(z){ window.__calls.push('drag:' + z); return Promise.resolve({ok:true}); }
}};
"""

errs = []
with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")

    # ---------- F. 普通浏览器模式 ----------
    print("\n== F  浏览器模式 ==")
    ctx = br.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE)
    pg.wait_for_selector(".snc-node")
    pg.wait_for_timeout(600)
    info = pg.evaluate("""() => ({
        shell: document.documentElement.classList.contains('snc-shell'),
        bar: getComputedStyle(document.getElementById('sncWinbar')).display,
        top: getComputedStyle(document.getElementById('snc')).top,
        bodyBg: getComputedStyle(document.body).backgroundColor
    })""")
    check("没有桥时不挂 snc-shell", info["shell"] is False, info)
    check("细标题栏隐藏", info["bar"] == "none", info["bar"])
    check("画布仍然 top:0", info["top"] == "0px", info["top"])
    check("body 保持透明（圆角靠外壳自己画）", "rgba(0, 0, 0, 0)" in info["bodyBg"], info["bodyBg"])
    ctx.close()

    # ---------- G. 外壳模式 + 三个窗口按钮 ----------
    print("\n== G  窗口按钮 ==")
    ctx = br.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    ctx.add_init_script(STUB)
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(BASE + "?shell=1")
    pg.wait_for_selector(".snc-node")
    pg.wait_for_timeout(800)

    info = pg.evaluate("""() => ({
        shell: document.documentElement.classList.contains('snc-shell'),
        bar: getComputedStyle(document.getElementById('sncWinbar')).display,
        barH: getComputedStyle(document.getElementById('sncWinbar')).height,
        top: getComputedStyle(document.getElementById('snc')).top,
        radius: getComputedStyle(document.getElementById('sncWinFrame')).borderRadius,
        btns: [...document.querySelectorAll('[data-win]')].map(b => b.dataset.win)
    })""")
    check("带 shell=1 时挂了 snc-shell", info["shell"] is True, info)
    check("细标题栏显示", info["bar"] == "flex", info["bar"])
    check("标题栏高 32px", info["barH"] == "32px", info["barH"])
    check("画布下移 32px", info["top"] == "32px", info["top"])
    check("外框 10px 圆角", info["radius"] == "10px", info["radius"])
    check("三个窗口按钮齐全且顺序正确", info["btns"] == ["min", "max", "close"], info["btns"])
    check("细栏显示当前画布名",
          "未命名画布" in pg.inner_text("#sncWinbarDoc"), pg.inner_text("#sncWinbarDoc"))

    pg.click('[data-win="min"]')
    pg.wait_for_timeout(150)
    pg.click('[data-win="close"]')
    pg.wait_for_timeout(150)
    calls = pg.evaluate("() => window.__calls")
    check("点最小化 → win_min", "min" in calls, calls)
    check("点 × → win_hide（不是关窗口）", "hide" in calls, calls)
    check("点 × 没有走 win_close", "close" not in calls, calls)

    # ---------- H. 最大化 / 还原 / 拖动 / 拉伸 ----------
    print("\n== H  最大化与拖动 ==")
    pg.click('[data-win="max"]')
    pg.wait_for_timeout(400)
    st = pg.evaluate("""() => ({
        calls: window.__calls.slice(),
        max: document.getElementById('sncWinFrame').classList.contains('is-max'),
        radius: getComputedStyle(document.getElementById('sncWinFrame')).borderRadius,
        title: document.querySelector('[data-win=max]').title,
        edges: getComputedStyle(document.querySelector('.snc-edge')).display
    })""")
    check("点最大化 → win_max", "max" in st["calls"], st["calls"])
    check("最大化后圆角归零", st["radius"] == "0px", st["radius"])
    check("最大化后按钮变成「还原」", st["title"] == "还原", st["title"])
    check("最大化后关掉边缘拉伸热区", st["edges"] == "none", st["edges"])

    pg.click('[data-win="max"]')
    pg.wait_for_timeout(400)
    st2 = pg.evaluate("""() => ({
        max: document.getElementById('sncWinFrame').classList.contains('is-max'),
        radius: getComputedStyle(document.getElementById('sncWinFrame')).borderRadius,
        title: document.querySelector('[data-win=max]').title
    })""")
    check("再点一次回到还原态", st2["max"] is False, st2)
    check("还原后圆角回来", st2["radius"] == "10px", st2["radius"])
    check("还原后按钮恢复「最大化」", st2["title"] == "最大化", st2["title"])

    pg.evaluate("() => window.__calls.length = 0")
    pg.dispatch_event('[data-edge="right"]', "mousedown", {"button": 0})
    pg.wait_for_timeout(200)
    pg.dispatch_event('[data-edge="topleft"]', "mousedown", {"button": 0})
    pg.wait_for_timeout(200)
    calls = pg.evaluate("() => window.__calls")
    check("右边缘按下 → win_drag(right)", "drag:right" in calls, calls)
    check("左上角按下 → win_drag(topleft)", "drag:topleft" in calls, calls)

    pg.evaluate("() => window.__calls.length = 0")
    pg.dispatch_event("#sncWinbar", "mousedown", {"button": 0})
    pg.wait_for_timeout(200)
    calls = pg.evaluate("() => window.__calls")
    check("细栏空白处按下 → 拖动窗口", "drag:move" in calls, calls)

    pg.evaluate("() => window.__calls.length = 0")
    pg.dblclick("#sncWinbar")
    pg.wait_for_timeout(300)
    calls = pg.evaluate("() => window.__calls")
    check("双击细栏 → 最大化/还原", "max" in calls, calls)

    # ---------- J. 分辨率档位跟着 max_side 走 ----------
    print("\n== J  分辨率档位 ==")
    tiers_google = pg.evaluate("() => window.SNC_RES_TIERS('google:nano-banana-pro').map(t => t.label)")
    check("Google Pro（4096）给三档", tiers_google == ["原图", "2K", "4K"], tiers_google)
    tiers_sense = pg.evaluate("() => window.SNC_RES_TIERS('sensenova:fast').map(t => t.label)")
    check("SenseNova（4096）给三档", tiers_sense == ["原图", "2K", "4K"], tiers_sense)
    tiers_qwen = pg.evaluate("() => window.SNC_RES_TIERS('qwen:qwen-image').map(t => t.label)")
    check("Qwen（1440）给 原图/1K/1.4K", tiers_qwen == ["原图", "1K", "1.4K"], tiers_qwen)

    pg.screenshot(path=os.path.join(SHOTS, "v32-shell.png"))
    ctx.close()
    br.close()

# ======================================================================
print("\n== I  页面没有 JS 报错 ==")
check("全程无 pageerror", not errs, errs[:3])

print("\n" + "=" * 52)
print("v32 shell: %d passed, %d failed" % (PASS, FAIL))
if FAILS:
    for n, e in FAILS:
        print("  FAILED:", n, "->", e)
sys.exit(1 if FAIL else 0)
