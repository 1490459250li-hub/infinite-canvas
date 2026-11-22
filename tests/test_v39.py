# -*- coding: utf-8 -*-
"""v3.7 回归：把「纯文字选项菜单 / 指令回填编辑面板 / 渲染专属窗」三条路径合并成一个技能工作台。

A 段：源码断言（旧路径确实删干净、每条技能都能拼出提示词、chips 的 k 全部可解析、三页签）。
B 段：浏览器实测（零参数 / 单参数 / 三参数是同一个窗、两级下钻、提示词实时拼装、手改保护、
      设置行三个下拉、不点生成不发请求、生成派生新卡且编辑面板不亮）。
出图接口全部打桩，不消耗额度。
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
DIST_HTML = os.path.join(ROOT, "proto", "canvas.html")

sys.path.insert(0, os.path.join(ROOT, "proto"))
import server  # noqa: E402

src = open(SRC, encoding="utf-8").read()
dist = open(DIST_HTML, encoding="utf-8").read()

print("\n== A  源码 ==")
check("版本号 >= 3.7.0", server._ver_key(server.APP_VERSION) >= server._ver_key("3.7.0"),
      server.APP_VERSION)

# ---- 三条旧路径确实删掉了 ----
check("纯文字选项菜单的 DOM 已删", 'id="sncSkillOptMenu"' not in src)
check("纯文字选项菜单的样式已删", ".snc-optmenu" not in src)
check("showSkillOpts 已删", "function showSkillOpts" not in src)
check("回填编辑面板的 applySkillToNode 已删", "function applySkillToNode" not in src)
check("placeSkillOptMenu / closeSkillOptMenu 已删",
      "function placeSkillOptMenu" not in src and "function closeSkillOptMenu" not in src)
check("渲染专属工作台的注释已换成通用版", "v3.7 · 技能工作台" in src)
check("只剩一个入口 useSkillOn → openSkillWin",
      "openSkillWin(n, sk, imgBar.querySelector" in src and src.count("function useSkillOn") == 1)

# ---- 工作台结构：标题 + chips + 提示词 + 设置行 + 生成 ----
for frag, label in [('id="sncSkWinIc"', "技能图标"), ('id="sncSkWinChips"', "参数 chips"),
                    ('id="sncSkWinText"', "提示词输入框"), ('id="sncSkWinRatio"', "比例"),
                    ('id="sncSkWinRes"', "分辨率"), ('id="sncSkWinModel"', "模型"),
                    ('id="sncSkWinGo"', "生成按钮")]:
    check("工作台有%s" % label, frag in src)
check("设置行常驻（不再折叠成指令按钮）",
      ".snc-skwin-opts" in src and "snc-skwin-opts" in src)
check("输入框就是提示词（5 行、可手改）",
      'rows="5"' in src and 'id="sncSkWinText"' in src)
check("手改后不再被参数覆盖", "winState.dirty" in src and "if(!force && winState.dirty) return;" in src)
check("参数变化后重拼提示词", "syncWinText(false)" in src and "function syncWinText(force)" in src)

# ---- 三条带参数的技能都改成 chips ----
for sid, chip in [("bi-time", 'chips:[{k:"time", t:"时段"'),
                  ("bi-season", 'chips:[{k:"season", t:"季节"'),
                  ("bi-story", 'chips:[{k:"layout", t:"宫格"')]:
    i = src.find('id:"%s"' % sid)
    seg = src[i:i + 400]
    check("%s 用 chips 声明参数" % sid, chip in seg, seg[:80])
check("画风迁移用本地 7 个画风（不进公共字典）",
      'chips:[{k:"style", t:"画风", say:"只把表现语言换成{{l}}", opts:[' in src)
check("场景分镜直接吃 layout 字典的整句",
      'chips:[{k:"layout", t:"宫格", usep:true}]' in src)
check("手绘渲染默认钢笔画", 'defaults:[{k:"style", v:"ink_pen"}]' in src)
check("时间天气用 grp 合并成一句",
      src.count('grp:"tw", pre:"时间与天气："') == 6)

# ---- 每条技能都能拼出非空提示词 ----
import re  # noqa: E402
block = src[src.index("var BUILTIN_SKILLS = ["):src.index("\n  ];", src.index("var BUILTIN_SKILLS = ["))]
ids = re.findall(r'\{id:"([a-z\-]+)"', block)
check("内置技能 21 条", len(ids) == 21, len(ids))
missing = []
for sid in ids:
    i = block.index('id:"%s"' % sid)
    nxt = block.find('\n    {id:"', i + 5)
    seg = block[i:nxt if nxt > 0 else len(block)]
    if not any(k in seg for k in ('prompt:"', 'body:"', 'head:"', 'art:true')):
        missing.append(sid)
check("每条技能都有可拼的文本（prompt/body/head）", not missing, missing)

# ---- chips 的 k 必须能解析：本地 opts 或公共字典 ----
ctrl_keys = re.findall(r'^\s{4}(\w+): \[', src, re.M)
bad_k = []
for m in re.finditer(r'\{k:"(\w+)", t:"[^"]+"(\s*,\s*(?:cont|ph|grp|pre|art|usep|say|opts))?', block):
    k = m.group(1)
    if '"k": "%s"' % k in src or '"%s": [' % k in src:
        continue
    seg_start = m.start()
    seg = block[seg_start:seg_start + 260]
    if "opts:[" in seg:
        continue
    bad_k.append(k)
check("chips 的 k 全部能在控件字典/本地 opts 里找到", not bad_k, bad_k)

# ---- 抽屉回到三页签 ----
check("抽屉三个页签（通用/专项/我的）",
      src.count('role="tab" data-g=') == 3 and 'data-g="render"' not in src)
check("渲染 4 条并回通用并排最前",
      "return {general: r.concat(g), pro: p, mine: userSkills.slice()};" in src)
check("关于页技能条数 21 条（通用 14 / 专项 7）", "21 条（通用 14 / 专项 7）" in src)
check("canvas.html 已重建", "snc-skwin-opts" in dist and "sncSkillOptMenu" not in dist)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


print("\n== B  浏览器 ==")
from playwright.sync_api import sync_playwright  # noqa: E402
import requests  # noqa: E402

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
errs, bodies = [], []


def gen(route):
    try:
        bodies.append(json.loads(route.request.post_data or "{}"))
    except Exception:
        bodies.append({})
    route.fulfill(status=200, content_type="application/json",
                  body=json.dumps({"ok": True, "b64": PNG, "size": "1024x1024", "width": 1024,
                                   "height": 1024, "format": "png", "model": "stub-image",
                                   "provider": "sensenova", "latencyMs": 600,
                                   "usage": {"total_tokens": 100}}))


SELECT = """() => {
    const d = [...document.querySelectorAll('.snc-node')]
      .find(x => (x.querySelector('.snc-node-label')||{}).textContent === '图片 1');
    if(!d) return false;
    const r = d.getBoundingClientRect();
    const opt = {bubbles:true, clientX:r.x+40, clientY:r.y+40};
    d.dispatchEvent(new MouseEvent('pointerdown', opt));
    d.dispatchEvent(new MouseEvent('pointerup', opt));
    d.dispatchEvent(new MouseEvent('click', opt));
    return true;
}"""


def boot(page):
    page.click("#sncFit")
    page.wait_for_timeout(420)
    page.evaluate(SELECT)
    page.wait_for_timeout(300)


def open_skill(page, name):
    page.click('#sncImgBar button[data-act="skill"]')
    page.wait_for_timeout(340)
    box = page.evaluate("""(name) => {
        const t = [...document.querySelectorAll('#sncSkpBody .snc-skp-tile')]
          .find(x => (x.querySelector('em')||{}).textContent.trim() === name);
        if(!t) return null;
        const r = t.getBoundingClientRect();
        return {x:r.x+r.width/2, y:r.y+r.height/2};
    }""", name)
    assert box, "找不到技能 " + name
    page.mouse.click(box["x"], box["y"])
    page.wait_for_timeout(380)


def wininfo(page):
    return page.evaluate("""() => {
        const w = document.getElementById('sncSkWin');
        const r = w.getBoundingClientRect();
        return {open: !w.hidden,
                name: document.getElementById('sncSkWinName').textContent,
                chips: [...w.querySelectorAll('.snc-skwin-chip')].map(b=>b.dataset.chip),
                chipText: [...w.querySelectorAll('.snc-skwin-chip')].map(b=>b.textContent.trim()),
                text: document.getElementById('sncSkWinText').value,
                hint: document.getElementById('sncSkWinHint').textContent,
                opts: [...w.querySelectorAll('.snc-skwin-opts select')].map(s=>s.value),
                inbox: r.x >= 0 && r.y >= 0 && r.right <= innerWidth && r.bottom <= innerHeight,
                pop: !document.getElementById('sncSkillPop').hidden,
                compose: !document.getElementById('sncCompose').hidden};
    }""")


def pick(page, chip, *path):
    page.click('#sncSkWinChips button[data-chip="%s"]' % chip)
    page.wait_for_timeout(220)
    for v in path:
        page.click('#sncSkWinMenu button[data-m="%s"]' % v)
        page.wait_for_timeout(220)


try:
    with sync_playwright() as p:
        br = p.chromium.launch(channel="msedge")
        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.route("**/api/generate", gen)
        page.goto(BASE + "/canvas.html")
        page.wait_for_selector(".snc-node")
        page.wait_for_timeout(1100)
        boot(page)

        # ---- B1 零参数：夜景转换 ----
        open_skill(page, "夜景转换")
        w = wininfo(page)
        check("零参数技能也弹同一个窗", w["open"] and w["name"] == "夜景转换", w["name"])
        check("零参数没有 chips", w["chips"] == [], w["chips"])
        check("输入框里直接是整段提示词", w["text"].startswith("把整体画面转换为夜景效果"), w["text"][:40])
        check("窗整块在视口内", w["inbox"])
        check("技能抽屉自动收起", not w["pop"])
        check("看提示词不发请求", len(bodies) == 0, len(bodies))
        page.keyboard.press("Escape")
        page.wait_for_timeout(260)

        # ---- B2 单参数：时间迁移 ----
        open_skill(page, "时间迁移")
        w = wininfo(page)
        check("时间迁移只有一个 chip", w["chips"] == ["time"], w["chips"])
        check("没选时 chip 显示参数名", w["chipText"] == ["时段"], w["chipText"])
        page.click('#sncSkWinChips button[data-chip="time"]')
        page.wait_for_timeout(240)
        opts = page.evaluate("() => [...document.querySelectorAll('#sncSkWinMenu button[data-m]')].map(b=>b.dataset.m)")
        check("时段下拉 8 项 + 不限", len(opts) == 9 and "evening" in opts, opts)
        page.click('#sncSkWinMenu button[data-m="evening"]')
        page.wait_for_timeout(300)
        w = wininfo(page)
        check("选完 chip 显示选项名", w["chipText"] == ["傍晚"], w["chipText"])
        check("提示词用画面级短语（不是控件短标签）", "傍晚，黄金时刻" in w["text"], w["text"][:60])
        check("提示词接着写技能正文", "只改变时段与由此带来的光色" in w["text"])
        page.keyboard.press("Escape")
        page.wait_for_timeout(260)

        # ---- B3 三参数：建筑渲染 + 两级下钻 ----
        open_skill(page, "建筑渲染")
        w = wininfo(page)
        check("建筑渲染三个 chip", w["chips"] == ["building", "time", "weather"], w["chips"])
        check("设置行默认跟随原图 / 2K", w["opts"][0] == "auto" and w["opts"][1] == "2048", w["opts"])
        page.click('#sncSkWinChips button[data-chip="building"]')
        page.wait_for_timeout(240)
        lvl1 = page.evaluate("() => [...document.querySelectorAll('#sncSkWinMenu button[data-m]')].map(b=>b.dataset.m)")
        check("建筑类型一级 12 类 + 不限", len(lvl1) == 13 and "office" in lvl1, lvl1)
        page.click('#sncSkWinMenu button[data-m="office"]')
        page.wait_for_timeout(240)
        lvl2 = page.evaluate("() => [...document.querySelectorAll('#sncSkWinMenu button[data-m]')].map(b=>b.dataset.m)")
        check("点大类自动下钻子类", "high_rise_office" in lvl2, lvl2)
        page.click('#sncSkWinMenu button[data-m="high_rise_office"]')
        page.wait_for_timeout(240)
        w = wininfo(page)
        check("chip 只显示最后一级", w["chipText"][0] == "高层办公", w["chipText"])
        pick(page, "time", "evening")
        pick(page, "weather", "clear")
        w = wininfo(page)
        check("时间与天气合并成一句", "时间与天气：傍晚，黄金时刻" in w["text"] and
              "；晴朗，天空干净通透" in w["text"], w["text"][:160])
        check("场景类型写在第一句里", "，场景类型为「办公建筑 · 高层办公」。" in w["text"], w["text"][:60])
        check("头部不重复（只有一句开头）", w["text"].count("照片级的建筑表现图") == 1,
              w["text"].count("照片级的建筑表现图"))
        page.screenshot(path=os.path.join(ROOT, "截图", "v37b", "20-工作台整屏.png"))

        # ---- B4 手改保护 ----
        page.evaluate("""() => {
            const t = document.getElementById('sncSkWinText');
            t.value = t.value + "\\n补充要求：加强入口雨棚的暖光";
            t.dispatchEvent(new Event('input', {bubbles:true}));
        }""")
        page.wait_for_timeout(200)
        w1 = wininfo(page)
        check("手改后 hint 明确提示", "已手改" in w1["hint"], w1["hint"])
        pick(page, "weather", "mist")
        page.wait_for_timeout(260)
        w2 = wininfo(page)
        check("再动参数不覆盖手改内容",
              "补充要求：加强入口雨棚的暖光" in w2["text"] and "薄雾" not in w2["text"],
              w2["text"][-60:])
        check("chip 本身仍然更新", w2["chipText"][2] == "薄雾", w2["chipText"])

        # ---- B5 生成：派生新卡，一次请求 ----
        before = page.evaluate("() => document.querySelectorAll('.snc-node').length")
        bodies.clear()
        page.click("#sncSkWinGo")
        page.wait_for_timeout(2400)
        after = page.evaluate("() => document.querySelectorAll('.snc-node').length")
        check("生成派生一张新卡", after == before + 1, (before, after))
        check("生成后工作台关闭", page.evaluate("() => document.getElementById('sncSkWin').hidden"))
        check("生成后编辑面板没被亮出来",
              page.evaluate("() => document.getElementById('sncCompose').hidden"))
        check("只发了一次出图请求", len(bodies) == 1, len(bodies))
        pr = (bodies[-1].get("prompt") or "") if bodies else ""
        check("请求提示词 = 输入框里那段", "补充要求：加强入口雨棚的暖光" in pr, pr[-90:])
        check("手改后参数没被偷偷拼回去", "薄雾" not in pr, pr[-120:])
        check("仍然带参考图", "参考图说明" in pr, pr[:60])

        # ---- B6 场景分镜：宫格 ----
        page.reload()
        page.wait_for_selector(".snc-node")
        page.wait_for_timeout(1100)
        boot(page)
        open_skill(page, "场景分镜")
        w = wininfo(page)
        check("场景分镜一个 chip", w["chips"] == ["layout"], w["chips"])
        page.click('#sncSkWinChips button[data-chip="layout"]')
        page.wait_for_timeout(240)
        grids = page.evaluate("() => [...document.querySelectorAll('#sncSkWinMenu button[data-m]')].map(b=>b.textContent.trim())")
        check("宫格四项齐全", all(k in grids for k in ("四宫格", "九宫格", "十六宫格", "二十五宫格")), grids)
        page.click('#sncSkWinMenu button[data-m="grid_16"]')
        page.wait_for_timeout(300)
        w = wininfo(page)
        check("选十六宫格后提示词整句正确",
              "把这张图变成十六宫格的分镜图。" in w["text"], w["text"][:50])
        page.keyboard.press("Escape")
        page.wait_for_timeout(260)

        # ---- B7 画风迁移：7 个本地项 ----
        open_skill(page, "画风迁移")
        page.click('#sncSkWinChips button[data-chip="style"]')
        page.wait_for_timeout(240)
        styles = page.evaluate("() => [...document.querySelectorAll('#sncSkWinMenu button[data-m]')]"
                               ".slice(1).map(b=>b.textContent.trim())")
        check("画风迁移 7 个本地画风", len(styles) == 7, styles)
        check("画风迁移含白模", "白模" in styles, styles)
        page.click('#sncSkWinMenu button[data-m="white"]')
        page.wait_for_timeout(280)
        w = wininfo(page)
        check("画风迁移提示词只换表现语言",
              "只把表现语言换成白模" in w["text"], w["text"][:60])
        page.keyboard.press("Escape")
        page.wait_for_timeout(260)

        # ---- B8 手绘渲染：12 画风 + 默认值 + 长提示词 ----
        open_skill(page, "手绘渲染")
        w = wininfo(page)
        check("手绘渲染带默认画风", w["chipText"] == ["钢笔画"], w["chipText"])
        check("默认画风直接拼出 ART_STYLE 长提示词", "目标画风：钢笔建筑速写" in w["text"], w["text"][:80])
        page.click('#sncSkWinChips button[data-chip="style"]')
        page.wait_for_timeout(240)
        arts = page.evaluate("() => [...document.querySelectorAll('#sncSkWinMenu button[data-m]')].slice(1).length")
        check("手绘 12 种画风", arts == 12, arts)
        page.click('#sncSkWinMenu button[data-m="ink_wash"]')
        page.wait_for_timeout(300)
        w = wininfo(page)
        check("换画风后长提示词整段替换", "水墨" in w["text"] and "钢笔建筑速写" not in w["text"],
              w["text"][:70])
        page.keyboard.press("Escape")
        page.wait_for_timeout(260)

        # ---- B9 Esc / 点窗外 ----
        open_skill(page, "光影增强")
        check("打开后再按 Esc 收起",
              (page.keyboard.press("Escape"), page.wait_for_timeout(260),
               page.evaluate("() => document.getElementById('sncSkWin').hidden"))[2])
        open_skill(page, "光影增强")
        page.mouse.click(200, 700)
        page.wait_for_timeout(300)
        check("点窗外收起",
              page.evaluate("() => document.getElementById('sncSkWin').hidden"))
        check("全程没有 JS 报错", not errs, errs[:3])
        br.close()
finally:
    proc.terminate()

print("\n== 合计 %d 项 · 失败 %d ==" % (PASS + FAIL, FAIL))
if FAILS:
    for n, e in FAILS:
        print("  -", n, "->", e)
    sys.exit(1)
