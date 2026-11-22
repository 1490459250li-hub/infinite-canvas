# -*- coding: utf-8 -*-
"""v1.9 回归：暗/亮双主题、设置三分区（主题 / 大模型调用 / 关于）、
左侧栏字号加大、技能各自带效果预览图、去掉「读图」标注。
全部走页面自身逻辑，不发出任何生成请求。"""
import base64
import json
import os
import struct
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

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


PNG64 = base64.b64encode(png_bytes()).decode("ascii")


def boot(br, w=1440, h=900):
    ctx = br.new_context(viewport={"width": w, "height": h})
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.route("**/api/generate", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "b64": PNG64, "size": "2048x1280", "width": 2048,
                         "height": 1280, "format": "png", "model": "stub", "mode": "gen",
                         "latencyMs": 500, "usage": {}})))
    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(1200)
    return ctx, page, errs


def css(page, sel, prop):
    return page.evaluate("""([s, p]) => {
        const el = document.querySelector(s);
        return el ? getComputedStyle(el).getPropertyValue(p) : '';
    }""", [sel, prop])


def open_settings(page):
    page.click(".snc-doc-foot [data-set]")
    page.wait_for_timeout(450)


def pane_state(page):
    return page.evaluate("""() => {
        const panes = Array.from(document.querySelectorAll('#sncSettings .snc-pane'));
        const nav = Array.from(document.querySelectorAll('#sncSetNav button'));
        const foot = document.querySelector('#sncSettings .snc-dlg-f');
        return {visible: panes.filter(p => !p.hidden).map(p => p.dataset.pane),
                nav: nav.map(b => b.textContent.trim()),
                on: nav.filter(b => b.classList.contains('is-on')).map(b => b.dataset.pane),
                footHidden: foot ? foot.hidden : null};
    }""")


with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    ctx, page, errs = boot(br)
    page.evaluate("() => { try{ localStorage.removeItem('snc.theme.v1'); }catch(e){} }")
    page.reload()
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(1200)

    # ---------- 1. 左侧工作区栏字号 ----------
    sizes = page.evaluate("""() => {
        const g = s => { const el = document.querySelector(s); return el ? parseFloat(getComputedStyle(el).fontSize) : 0; };
        return {ws: g('.snc-doc-ws'), nav: g('.snc-doc-nav button'),
                item: g('.snc-doc-item') || g('.snc-doc-new'), h: g('.snc-doc-h'),
                search: g('.snc-doc-search input'),
                rail: parseFloat(getComputedStyle(document.getElementById('snc')).getPropertyValue('--rail'))};
    }""")
    check("工作区标题字号 ≥13px", sizes["ws"] >= 13, sizes)
    check("工具入口（技能/链接/记录）字号 ≥13px", sizes["nav"] >= 13, sizes)
    check("画布列表项字号 ≥13px", sizes["item"] >= 13, sizes)
    check("搜索框字号 ≥12.5px", sizes["search"] >= 12.5, sizes)
    check("侧栏宽度加到 248px", sizes["rail"] >= 244, sizes)
    check("加大后文字不溢出（列表项单行省略）",
          page.evaluate("() => getComputedStyle(document.querySelector('.snc-doc-item')).textOverflow") in ("ellipsis", "clip"),
          page.evaluate("() => getComputedStyle(document.querySelector('.snc-doc-item')).textOverflow"))

    # ---------- 2. 设置分三块 ----------
    open_settings(page)
    st = pane_state(page)
    check("设置只有三项：主题 / 大模型调用 / 关于",
          st["nav"] == ["主题", "大模型调用", "关于"], st["nav"])
    check("打开设置默认停在「主题」", st["visible"] == ["theme"] and st["on"] == ["theme"], st)
    check("主题页不显示保存/测试按钮（那是模型页的）", st["footHidden"] is True, st)

    page.click('#sncSetNav button[data-pane="model"]')
    page.wait_for_timeout(350)
    st = pane_state(page)
    check("切到「大模型调用」显示模型设置与底部按钮",
          st["visible"] == ["model"] and st["footHidden"] is False, st)
    # v3.0：单表单换成供应商卡片列表，字段变成卡片里的输入框与下拉
    check("模型页有供应商卡片与分流字段",
          page.evaluate("() => document.querySelectorAll('#sncProvList .snc-prov').length >= 1 && "
                        "document.querySelectorAll('#sncProvList input[data-role=\\'key\\']').length >= 1 && "
                        "!!document.getElementById('sncRouteImg') && "
                        "!!document.getElementById('sncRoutePolish')"))

    page.click('#sncSetNav button[data-pane="about"]')
    page.wait_for_timeout(350)
    st = pane_state(page)
    about = page.evaluate("() => document.querySelector('.snc-pane[data-pane=\"about\"]').textContent.replace(/\\s+/g,' ')")
    check("切到「关于」隐藏底部按钮", st["visible"] == ["about"] and st["footHidden"] is True, st)
    import re as _re
    check("关于页有版本号", bool(_re.search(r"v\d+\.\d+", about)), about[:80])
    check("关于页写了图像能力", "文生图" in about and "局部重绘" in about, about[:120])
    check("关于页显示真实服务端口", ":%s" % (page.url.split(":")[2].split("/")[0]) in about, about[about.find("本地服务"):][:40])
    check("关于页说明密钥本机加密保存", "加密" in about, about[-80:])

    # ---------- 3. 去掉「可读图」标注 ----------
    tags = page.evaluate("""() => {
        const p = document.querySelector('.snc-pane[data-pane="model"]');
        const opts = Array.from(p.querySelectorAll('select option')).map(o => o.textContent);
        return {text: p.textContent, opts: opts,
                chips: Array.from(p.querySelectorAll('.snc-model-chip')).map(c => c.textContent.trim())};
    }""")
    check("下拉里不再标「可读图」", not any("可读图" in o for o in tags["opts"]), tags["opts"])
    check("说明文字里不再提「读图」", "读图" not in tags["text"], tags["text"][-90:])
    # v3.0：图片 chip 的前缀从「图片」改成供应商名（SenseNova / Google …），
    # 文本 chip 仍是「文本」，两类之外不该有第三种
    img_labels = {"SenseNova", "OpenAI", "Google", "Seedream", "Qwen-Image"}
    check("模型 chip 只有图片（带供应商名）与文本两类",
          all(c.startswith("文本") or any(c.startswith(lb) for lb in img_labels)
              for c in tags["chips"]), tags["chips"])

    # ---------- 4. 主题切换 ----------
    page.click('#sncSetNav button[data-pane="theme"]')
    page.wait_for_timeout(300)
    # v3.7.4：默认主题换成暖灰（三套色板：暖灰 / 冷灰 / 米白）
    check("默认是暖灰（data-theme=warm）",
          page.evaluate("() => document.getElementById('snc').getAttribute('data-theme')") == "warm")
    dark_bg = css(page, "#snc", "background-color")

    page.click('#sncThemeGrid [data-theme-opt="light"]')
    page.wait_for_timeout(400)
    light = page.evaluate("""() => ({
        attr: document.getElementById('snc').getAttribute('data-theme'),
        ls: (() => { try { return localStorage.getItem('snc.theme.v2') || localStorage.getItem('snc.theme.v1'); } catch(e){ return null; } })(),
        pressed: Array.from(document.querySelectorAll('#sncThemeGrid [data-theme-opt]'))
                    .filter(b => b.getAttribute('aria-pressed') === 'true').map(b => b.dataset.themeOpt),
        bg: getComputedStyle(document.getElementById('snc')).backgroundColor,
        ink: getComputedStyle(document.getElementById('snc')).color,
        card: getComputedStyle(document.querySelector('.snc-dlg')).backgroundColor,
        now: document.getElementById('sncThemeNow').textContent.trim()
    })""")
    check("点亮色后 data-theme=light", light["attr"] == "light", light)
    check("亮色背景确实变浅", light["bg"] != dark_bg and light["bg"].startswith("rgb(2"), light["bg"])

    def lum(s):
        nums = [int(x) for x in s.replace("rgb(", "").replace(")", "").split(",")[:3]]
        return sum(nums) / 3.0

    check("亮色下正文是深色（对比度足够）", lum(light["ink"]) < 110 < lum(light["bg"]),
          "%s on %s" % (light["ink"], light["bg"]))
    check("主题选择记在本机（下次启动沿用）", light["ls"] == "light", light["ls"])
    check("卡片选中态跟着走到亮色", light["pressed"] == ["light"], light["pressed"])
    check("主题页底部的「当前」文案同步", "米白" in light["now"], light["now"])

    page.screenshot(path=os.path.join(SHOT_DIR, "v19-亮色-主题页.png"))

    # 刷新后保持
    page.reload()
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(900)
    check("刷新后仍是亮色",
          page.evaluate("() => document.getElementById('snc').getAttribute('data-theme')") == "light")
    page.screenshot(path=os.path.join(SHOT_DIR, "v19-亮色-主界面.png"))

    # 切到冷灰（即梦暗色那套）
    open_settings(page)
    page.click('#sncThemeGrid [data-theme-opt="dark"]')
    page.wait_for_timeout(350)
    cool = page.evaluate("""() => ({
        attr: document.getElementById('snc').getAttribute('data-theme'),
        bg: getComputedStyle(document.getElementById('snc')).backgroundColor,
        accent: getComputedStyle(document.getElementById('snc')).getPropertyValue('--accent').trim(),
        pressed: Array.from(document.querySelectorAll('#sncThemeGrid [data-theme-opt]'))
                    .filter(b => b.getAttribute('aria-pressed') === 'true').map(b => b.dataset.themeOpt),
        now: document.getElementById('sncThemeNow').textContent.trim()
    })""")
    check("切到冷灰后 data-theme=dark", cool["attr"] == "dark", cool)
    check("冷灰用蓝紫强调色", cool["accent"].lower() == "#4d6bfe", cool["accent"])
    check("冷灰卡片选中态正确", cool["pressed"] == ["dark"], cool["pressed"])
    check("底部文案同步为冷灰", "冷灰" in cool["now"], cool["now"])
    page.click("#sncSetClose")
    page.wait_for_timeout(300)

    # ---------- 5. 技能预览图 ----------
    cards = page.evaluate("""() => {
        const ns = Array.from(document.querySelectorAll('.snc-node'));
        // 预览图改外链后 src 只有几十字符，不能再靠「src 很长」认图卡；
        // 改成「这张 img 真的解码出来了」，并且优先挑生成卡（笔记卡点了不出工具条）
        const t = ns.filter(d => { const i = d.querySelector('.snc-gen img');
                                   return i && i.complete && i.naturalWidth > 64; })
                    .concat(ns.filter(d => d.querySelector('.snc-gen')))
                    .concat(ns)[0];
        const r = t.getBoundingClientRect();
        return {x: r.x + r.width / 2, y: r.y + r.height / 2};
    }""")
    page.mouse.click(cards["x"], cards["y"])
    page.wait_for_timeout(350)
    page.click('#sncImgBar button[data-act="skill"]')
    page.wait_for_timeout(500)

    art = page.evaluate("""() => {
        const tiles = Array.from(document.querySelectorAll('#sncSkpBody .snc-skp-tile'));
        return {n: tiles.length,
                withArt: tiles.filter(t => t.classList.contains('has-art')).length,
                withImg: tiles.filter(t => t.classList.contains('has-img')).length,
                srcs: tiles.map(t => { const i = t.querySelector('img');
                                       return i ? (i.getAttribute('src') || '') : ''; }),
                loaded: tiles.filter(t => { const i = t.querySelector('img');
                                            return i && i.complete && i.naturalWidth > 0; }).length,
                names: tiles.map(t => (t.querySelector('em') || {}).textContent || '')};
    }""")
    check("通用技能 14 条全部带自己的预览图", art["withArt"] == 14 and art["withImg"] == 0, art["withArt"])
    # v3.7.4：预览图从内联 base64 改成 /art/ 外链，两条判据跟着改语义
    check("14 张预览图互不相同",
          len(set(art["srcs"])) == 14 and all(x.startswith("/art/") for x in art["srcs"]),
          art["srcs"])
    check("预览图都从本机 /art/ 取，不依赖外网",
          all(x.startswith("/art/") for x in art["srcs"]) and art["loaded"] == 14,
          {"srcs": art["srcs"][:3], "loaded": art["loaded"]})
    page.screenshot(path=os.path.join(SHOT_DIR, "v19-技能预览图.png"))

    page.click('#sncSkpTabs button[data-g="pro"]')
    page.wait_for_timeout(400)
    pro = page.evaluate("""() => {
        const tiles = Array.from(document.querySelectorAll('#sncSkpBody .snc-skp-tile'));
        return {n: tiles.length, withArt: tiles.filter(t => t.classList.contains('has-art')).length,
                srcs: tiles.map(t => { const i = t.querySelector('img');
                                       return i ? (i.getAttribute('src') || '') : ''; })};
    }""")
    check("专项技能 7 条也各带预览图", pro["n"] == 7 and pro["withArt"] == 7, pro)
    check("专项 7 张预览图互不相同", len(set(pro["srcs"])) == 7, pro["srcs"])
    page.screenshot(path=os.path.join(SHOT_DIR, "v19-专项技能预览图.png"))

    check("全程无 JS 报错", not errs, errs[:3])

    br.close()

print()
ok = sum(1 for _, v in results if v)
print("%d / %d 通过" % (ok, len(results)))
