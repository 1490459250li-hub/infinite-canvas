# -*- coding: utf-8 -*-
"""v2.0 回归：启动画面（logo + 淡出）、主题卡片缩小、新增 5 条技能、关于页 logo。
全部走页面自身逻辑，不发出任何生成请求。"""
import json
import os
import re
import struct
import sys
import zlib
from playwright.sync_api import sync_playwright

BASE = os.environ.get("SNC_BASE", "http://127.0.0.1:8321/canvas.html")
SHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "截图")
os.makedirs(SHOT_DIR, exist_ok=True)

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + (("  | " + str(detail)) if detail else ""))


def png_bytes(w=160, h=100, rgb=(190, 120, 90)):
    raw = b"".join(b"\x00" + bytes(list(rgb) * w) for _ in range(h))

    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


PNG64 = "data:image/png;base64," + __import__("base64").b64encode(png_bytes()).decode()


def boot(br, w=1440, h=900):
    ctx = br.new_context(viewport={"width": w, "height": h})
    # 预置 EULA 已同意，避免首次启动弹窗挡住自动化交互
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.route("**/api/generate", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "b64": PNG64, "size": "2048x1280", "width": 2048,
                         "height": 1280, "format": "png", "model": "stub", "mode": "gen",
                         "latencyMs": 300, "usage": {}})))
    return ctx, page, errs


with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")

    # ========== 1. 启动画面 ==========
    ctx = br.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    page = ctx.new_page()
    early_errs = []
    page.on("pageerror", lambda e: early_errs.append(str(e)))
    page.route("**/api/generate", lambda r: r.fulfill(status=200, content_type="application/json",
                                                      body=json.dumps({"ok": True, "b64": PNG64})))

    # 慢一点，好在首帧抓到启动层
    page.route("**/canvas.html", lambda r: r.continue_())
    page.goto(BASE, wait_until="commit")
    page.wait_for_timeout(120)
    early = page.evaluate("""() => {
        const s = document.getElementById('sncSplash');
        if (!s) return null;
        const cs = getComputedStyle(s);
        const r = s.getBoundingClientRect();
        return {display: cs.display, opacity: cs.opacity,
                w: Math.round(r.width), h: Math.round(r.height),
                mark: !!s.querySelector('.snc-splash-mark svg'),
                name: (s.querySelector('.snc-splash-name') || {}).textContent || '',
                bg: cs.backgroundColor};
    }""")
    check("首帧就有启动层（DOM 与样式同时就位）", bool(early) and early["display"] == "grid", early)
    check("启动层铺满整个窗口",
          bool(early) and early["w"] >= 1400 and early["h"] >= 860, early)
    check("启动层里有 logo 与名称",
          bool(early) and early["mark"] and early["name"] == "无限画布", early)
    check("启动层不透明（不是透出后面的空白）",
          bool(early) and early["opacity"] == "1" and early["bg"] not in ("rgba(0, 0, 0, 0)", "transparent"), early)

    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(2200)
    after = page.evaluate("""() => {
        const s = document.getElementById('sncSplash');
        return {cls: s.className, display: getComputedStyle(s).display};
    }""")
    check("首屏画完启动层自动淡出", "is-done" in after["cls"] and after["display"] == "none", after)
    check("启动画面全程无 JS 报错", not early_errs, early_errs)
    page.screenshot(path=os.path.join(SHOT_DIR, "v20-启动画面.png"))
    ctx.close()

    # ========== 2. 主界面 / 主题卡片 ==========
    ctx, page, errs = boot(br)
    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(1400)

    page.click(".snc-doc-foot [data-set]")
    page.wait_for_timeout(450)

    cards = page.evaluate("""() => Array.from(document.querySelectorAll('#sncThemeGrid .snc-theme-opt')).map(c => {
        const r = c.getBoundingClientRect();
        const name = c.querySelector('.snc-theme-name');
        const desc = c.querySelector('.snc-theme-desc');
        return {w: Math.round(r.width), h: Math.round(r.height),
                name: name ? name.textContent.trim() : '',
                dir: getComputedStyle(c).gridTemplateColumns,
                nameClip: name ? name.scrollWidth > name.clientWidth + 1 : null,
                descH: desc ? Math.round(desc.getBoundingClientRect().height) : 0};
    })""")
    # v3.7.4：三套色板（暖灰 / 冷灰 / 米白）+ 跟随系统
    check("主题四个选项都在", [c["name"] for c in cards] == ["暖灰", "冷灰", "米白", "跟随系统"], cards)
    check("主题卡片压到 60px 以内（原来 ~150px）", all(c["h"] <= 60 for c in cards), [c["h"] for c in cards])
    check("四张卡片等宽同高", len(set((c["w"], c["h"]) for c in cards)) == 1, [(c["w"], c["h"]) for c in cards])
    check("卡片内改成横排（图标 + 文字两列）",
          all(c["dir"].count("px") >= 2 for c in cards), [c["dir"] for c in cards])
    check("名称没有被压掉", all(not c["nameClip"] for c in cards), cards)
    page.screenshot(path=os.path.join(SHOT_DIR, "v20-主题卡片.png"))

    page.click("#sncSetClose")
    page.wait_for_timeout(300)

    # ========== 3. 新增技能 ==========
    box = page.evaluate("""() => {
        const ns = Array.from(document.querySelectorAll('.snc-node'));
        for (const n of ns) {
            const im = n.querySelector('.snc-gen img');
            // v3.7.4：图片来源可能是 data URL（几万字符）或 /art/ 路径，
            // 靠「src 很长」判断「是真图」已经不可靠，改成看它是否真的解码出来了
            if (im && im.complete && im.naturalWidth > 64) {
                const r = n.getBoundingClientRect();
                return {x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)};
            }
        }
        return null;
    }""")
    check("画布上有可选的图卡", bool(box), box)
    page.mouse.click(box["x"], box["y"])
    page.wait_for_timeout(600)
    page.click('#sncImgBar button[data-act="skill"]')
    page.wait_for_timeout(700)

    gen = page.evaluate("""() => {
        const tiles = Array.from(document.querySelectorAll('#sncSkpBody .snc-skp-tile'));
        return {names: tiles.map(t => (t.querySelector('em') || {}).textContent.trim()),
                n: tiles.length,
                art: tiles.filter(t => t.querySelector('.snc-skp-art img')).length,
                panel: (() => { const p = document.getElementById('sncSkillPop');
                                const r = p.getBoundingClientRect();
                                return {h: Math.round(r.height), bottom: Math.round(r.bottom),
                                        vh: innerHeight}; })()};
    }""")
    for name in ["时间迁移", "季节迁移", "画风迁移", "场景分镜"]:
        check("通用技能里有「%s」" % name, name in gen["names"], gen["names"])
    # v3.7：渲染 4 条并回通用并排最前，共 14 条，且都补齐了自己的预览图
    check("通用技能 14 条且都带预览图", gen["n"] == 14 and gen["art"] == 14, gen)
    check("技能面板没有超出窗口底部", gen["panel"]["bottom"] <= gen["panel"]["vh"], gen["panel"])

    page.click('#sncSkpTabs button[data-g="pro"]')
    page.wait_for_timeout(600)
    pro = page.evaluate("""() => {
        const tiles = Array.from(document.querySelectorAll('#sncSkpBody .snc-skp-tile'));
        const body = document.getElementById('sncSkpBody');
        return {names: tiles.map(t => (t.querySelector('em') || {}).textContent.trim()),
                n: tiles.length,
                art: tiles.filter(t => t.querySelector('.snc-skp-art img')).length,
                scrollable: body.scrollHeight > body.clientHeight + 2};
    }""")
    check("专项技能里有「AI 通道图」", "AI 通道图" in pro["names"], pro["names"])
    check("专项技能 7 条且全部带预览图", pro["n"] == 7 and pro["art"] == 7, pro)
    page.screenshot(path=os.path.join(SHOT_DIR, "v20-技能面板-专项.png"))

    # 通道图预览不该是照片（应是纯色分区）
    check("「AI 通道图」有独立预览图", page.evaluate("""() => {
        const t = Array.from(document.querySelectorAll('#sncSkpBody .snc-skp-tile'))
          .find(x => (x.querySelector('em') || {}).textContent.trim() === 'AI 通道图');
        const img = t && t.querySelector('.snc-skp-art img');
        // v3.7.4：预览图改外链后 src 只有几十字符，判据换成「路径对得上 + 真解码出来了」
        const src = (img && img.getAttribute('src')) || '';
        return !!(img && src.indexOf('bi-channel') >= 0 && img.complete && img.naturalWidth > 0);
    }"""))

    # ========== 技能子选项（季节/时段/画风/宫格） ==========
    page.click('#sncSkpTabs button[data-g="general"]')
    page.wait_for_timeout(500)

    def click_skill(name):
        box = page.evaluate("""(name) => {
            const t = Array.from(document.querySelectorAll('#sncSkpBody .snc-skp-tile'))
              .find(x => (x.querySelector('em') || {}).textContent.trim() === name);
            if (!t) return null;
            const r = t.getBoundingClientRect();
            return {x: r.x + r.width / 2, y: r.y + r.height / 2};
        }""", name)
        assert box, "找不到技能 " + name
        page.mouse.click(box["x"], box["y"])
        page.wait_for_timeout(500)

    # ===== v3.7：点技能弹的是统一工作台，参数是标题栏里的下拉 =====
    def win_chips():
        return page.eval_on_selector_all(
            "#sncSkWinChips .snc-skwin-chip", "e=>e.map(x=>x.textContent.trim())")

    def win_text():
        return page.evaluate("() => document.getElementById('sncSkWinText').value")

    def win_open():
        return page.evaluate("() => !document.getElementById('sncSkWin').hidden")

    def pick(chip_label, opt_label):
        page.evaluate("""([cl, ol]) => {
            const c = Array.from(document.querySelectorAll('#sncSkWinChips .snc-skwin-chip'))
                .find(b => b.textContent.trim() === cl);
            if (c) c.click();
            const b = Array.from(document.querySelectorAll('#sncSkWinMenu button[data-m]'))
                .find(x => x.textContent.trim() === ol);
            if (b) b.click();
        }""", [chip_label, opt_label])
        page.wait_for_timeout(320)

    # ---- 场景分镜：一个「宫格」下拉，四/九/十六/二十五 ----
    click_skill("场景分镜")
    check("「场景分镜」弹出工作台（不再是纯文字菜单）", win_open())
    check("场景分镜只有一个参数：宫格", win_chips() == ["宫格"], win_chips())
    check("编辑面板没有被技能指令灌开",
          page.evaluate("() => document.getElementById('sncCompose').hidden"))
    page.click('#sncSkWinChips button[data-chip="layout"]')
    page.wait_for_timeout(250)
    story_opts = page.eval_on_selector_all(
        "#sncSkWinMenu button[data-m]", "e=>e.map(x=>x.textContent.trim())")
    check("宫格下拉含四/九/十六/二十五宫格",
          all(k in story_opts for k in ("四宫格", "九宫格", "十六宫格", "二十五宫格")), story_opts)
    page.click('#sncSkWinMenu button[data-m="grid_9"]')
    page.wait_for_timeout(320)
    story_text = win_text()
    check("选九宫格后提示词含九宫格", "九宫格" in story_text, story_text[:80])
    check("选完后 chip 只显示最后一级", win_chips() == ["九宫格"], win_chips())
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # ---- 季节迁移：四个季节 ----
    page.click('#sncImgBar button[data-act="skill"]')
    page.wait_for_timeout(450)
    click_skill("季节迁移")
    page.click('#sncSkWinChips button[data-chip="season"]')
    page.wait_for_timeout(250)
    season_opts = page.eval_on_selector_all(
        "#sncSkWinMenu button[data-m]", "e=>e.map(x=>x.textContent.trim())")
    check("「季节迁移」下拉 4 个季节", len([x for x in season_opts if x != "不限默认"]) == 4, season_opts)
    check("季节含春夏秋冬", "春季" in season_opts and "冬季" in season_opts, season_opts)
    page.click('#sncSkWinMenu button[data-m="winter"]')
    page.wait_for_timeout(320)
    season_text = win_text()
    check("选冬季后提示词含冬季", "冬季" in season_text, season_text[:60])
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # ---- 画风迁移：7 个本地画风（不进公共字典） ----
    page.click('#sncImgBar button[data-act="skill"]')
    page.wait_for_timeout(450)
    click_skill("画风迁移")
    page.click('#sncSkWinChips button[data-chip="style"]')
    page.wait_for_timeout(250)
    style_opts = page.eval_on_selector_all(
        "#sncSkWinMenu button[data-m]", "e=>e.map(x=>x.textContent.trim())")
    check("「画风迁移」下拉 7 个本地画风", len([x for x in style_opts if x != "不限默认"]) == 7, style_opts)
    check("画风含手绘/水彩/白模",
          "手绘插画" in style_opts and "水彩" in style_opts and "白模" in style_opts, style_opts)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # ========== 4. 关于页 logo ==========
    page.click(".snc-doc-foot [data-set]")
    page.wait_for_timeout(400)
    page.click('#sncSetNav button[data-pane="about"]')
    page.wait_for_timeout(350)
    about = page.evaluate("""() => {
        const mark = document.querySelector('.snc-about-mark svg');
        const txt = document.querySelector('.snc-pane[data-pane="about"]').textContent.replace(/\\s+/g, ' ');
        return {svg: !!mark, rects: mark ? mark.querySelectorAll('rect').length : 0,
                canvas: !!(mark && mark.querySelector('.snc-about-canvas')), text: txt,
                eulaBtn: !!document.getElementById('sncEulaOpen')};
    }""")
    check("关于页 logo 换成方案三·层叠画布", about["svg"] and about["rects"] >= 3 and about["canvas"], about)
    # v3.0 起版本号随发版变化，只校验「关于页写有 vX.Y 版本号」
    _vm = re.search(r"v\d+\.\d+", about["text"])
    check("关于页写有 vX.Y 版本号", bool(_vm), _vm and _vm.group(0))
    check("关于页写上内置技能条数", "21 条" in about["text"], about["text"][:80])
    check("关于页有用户协议入口", about["eulaBtn"], about)
    page.screenshot(path=os.path.join(SHOT_DIR, "v20-关于页.png"))

    # ========== EULA 用户协议 ==========
    page.click('#sncEulaOpen')
    page.wait_for_timeout(400)
    eula = page.evaluate("""() => {
        const d = document.getElementById('sncEulaDlg');
        const b = document.getElementById('sncEulaBody');
        return {open: d && !d.hidden, text: b ? b.textContent : ''};
    }""")
    check("点「查看协议」弹出 EULA 对话框", eula["open"] and "逆向工程" in eula["text"], eula["text"][:60])
    check("EULA 含禁止逆向条款", "逆向工程" in eula["text"] and "反编译" in eula["text"], "")
    check("EULA 含授权范围条款", "非独占" in eula["text"] and "不可转让" in eula["text"], "")
    page.screenshot(path=os.path.join(SHOT_DIR, "v20-EULA.png"))
    page.click('#sncEulaAgree')
    page.wait_for_timeout(400)
    eula_closed = page.evaluate("() => document.getElementById('sncEulaDlg').hidden")
    check("点「同意」后关闭对话框", eula_closed, eula_closed)

    check("主流程全程无 JS 报错", not errs, errs)
    ctx.close()

    # ========== 首次启动弹 EULA ==========
    ctx2 = br.new_context(viewport={"width": 1200, "height": 800})
    page2 = ctx2.new_page()
    eula_errs = []
    page2.on("pageerror", lambda e: eula_errs.append(str(e)))
    page2.route("**/api/generate", lambda r: r.fulfill(status=200, content_type="application/json",
                                                       body=json.dumps({"ok": True, "b64": PNG64})))
    page2.goto(BASE)
    page2.wait_for_timeout(1800)
    first_run = page2.evaluate("""() => {
        const d = document.getElementById('sncEulaDlg');
        return {open: d && !d.hidden, agreed: localStorage.getItem('snc.eula.v1')};
    }""")
    check("首次启动（无同意记录）弹出 EULA", first_run["open"], first_run)
    page2.click('#sncEulaAgree')
    page2.wait_for_timeout(300)
    agreed_val = page2.evaluate("() => localStorage.getItem('snc.eula.v1')")
    check("同意后写入本地记录", agreed_val == "1", agreed_val)
    page2.reload()
    page2.wait_for_timeout(1800)
    second_run = page2.evaluate("() => document.getElementById('sncEulaDlg').hidden")
    check("已同意后刷新不再弹 EULA", second_run, second_run)
    check("EULA 流程无 JS 报错", not eula_errs, eula_errs)
    ctx2.close()

    br.close()

passed = sum(1 for _, ok in results if ok)
print("\n%d / %d 通过" % (passed, len(results)))
sys.stdout.flush()   # 管道输出时 os._exit 会丢掉缓冲区
os._exit(0 if passed == len(results) else 1)
