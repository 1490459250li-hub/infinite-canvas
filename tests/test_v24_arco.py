# -*- coding: utf-8 -*-
"""v2.4 回归：S1 结构化预设 + S2 最高准则包装 + S3 控件字典浮层。

验收底线（用户要求「不影响现在软件功能」）：
  * 内置技能仍 17 条、一级选项菜单数量不变、编辑框显示文本不变；
  * 不使用技能 / 参数 / 全局开关时，提交的请求体提示词逐字等于旧版；
  * 三段式布局、参考图说明、EULA、多图等既有链路全部照旧。
本测试全程走网络存根，不消耗出图额度。
"""
import base64
import json
import os
import re
import struct
import sys
import zlib
from playwright.sync_api import sync_playwright

BASE = os.environ.get("SNC_BASE", "http://127.0.0.1:8321/canvas.html")
TMP = r"E:\canvas-probe2\tmp\v24"
SHOTS = r"E:\canvas-probe2\shots-v24-arco"
os.makedirs(TMP, exist_ok=True)
os.makedirs(SHOTS, exist_ok=True)

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + (("  | " + str(detail)) if detail else ""))


def png_bytes(w, h):
    row = bytes([190, 120, 90]) * w
    raw = b"".join(b"\x00" + row for _ in range(h))

    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    ctx = br.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    bodies = []

    def gen(route):
        bodies.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True,
                                       "b64": base64.b64encode(png_bytes(800, 600)).decode("ascii"),
                                       "size": "stub", "width": 800, "height": 600,
                                       "format": "png", "model": "stub-image", "mode": "gen",
                                       "latencyMs": 100, "usage": {}}))

    page.route("**/api/generate", gen)
    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(900)

    def reset_struct():
        page.evaluate("""() => {
            try{ localStorage.removeItem('snc.struct.all');
                 localStorage.setItem('snc.struct.fmt','text'); }catch(e){}
        }""")
        page.reload()
        page.wait_for_selector(".snc-node")
        page.wait_for_timeout(700)

    def make_card(label):
        before = page.evaluate(
            "() => Array.from(document.querySelectorAll('.snc-node')).map(d=>d.dataset.id)")
        page.fill("#sncInput", label)
        page.click("#sncSend")
        page.wait_for_timeout(1100)
        new_id = page.evaluate("""(old) => {
            const cs = Array.from(document.querySelectorAll('.snc-node'));
            const n = cs.find(d => !old.includes(d.dataset.id));
            return n ? n.dataset.id : '';
        }""", before)
        return new_id

    def open_edit(cid):
        page.click('.snc-node[data-id="%s"]' % cid)
        page.wait_for_timeout(250)
        page.click('#sncImgBar button[data-act="edit"]')
        page.wait_for_timeout(250)

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
        page.wait_for_timeout(380)

    def pick_opt(chip_label, opt_label):
        """v3.7：参数不再是独立的纯文字菜单，而是技能工作台标题栏里的下拉。"""
        page.evaluate("""([cl, ol]) => {
            const c = Array.from(document.querySelectorAll('#sncSkWinChips .snc-skwin-chip'))
                .find(b => b.textContent.trim() === cl);
            if (c) c.click();
            const b = Array.from(document.querySelectorAll('#sncSkWinMenu button[data-m]'))
                .find(x => x.textContent.trim() === ol);
            if (b) b.click();
        }""", [chip_label, opt_label])
        page.wait_for_timeout(400)

    def last_body():
        return bodies[-1] if bodies else {}

    # ========== A. 资产层完整性 ==========
    asset = page.evaluate("""() => {
        const A = window.SNC_ARCO;
        if (!A) return null;
        const C = A.CONTROLS;
        return {
            version: A.VERSION,
            rules: Object.keys(A.RULES),
            supreme: A.RULES.supreme,
            aerial: A.RULES.aerialAlign,
            annotation: A.RULES.annotationRemoval,
            styleRules: A.RULES.styleRules.length,
            struct: Object.keys(A.STRUCT),
            structKeys: Object.keys(A.STRUCT.winter),
            styleMap: Object.keys(A.STYLE_MAP),
            styleMapDims: Object.keys(A.STYLE_MAP.ink_pen),
            artStyles: Object.keys(A.ART_STYLE).length,
            controls: Object.keys(C),
            time: C.time.length, renderTime: C.renderTime.length,
            weather: C.weather.length, season: C.season.length,
            style: C.style.length, layout: C.layout.length,
            motion: C.motion.length, camera: C.camera.length,
            crop: C.crop.length, count: C.count.length, upscale: C.upscale.length,
            interior: C.interiorStyle.length, publicInterior: C.publicInteriorStyle.length,
            buildingTop: C.building.length,
            buildingSub: C.building.reduce((a,b)=>a+b.children.length,0),
            landscapeTop: C.landscape.length,
            landscapeSub: C.landscape.reduce((a,b)=>a+b.children.length,0),
            skillKind: A.SKILL_KIND,
            meta: A.CONTROL_META.length,
            source: A.SOURCE
        };
    }""")
    check("资产层已挂载 window.SNC_ARCO", bool(asset), asset and asset["version"])
    check("版本标记 2.4-s123", bool(asset) and asset["version"] == "2.4-s123")
    check("S2 · 11 组规则常量齐备", bool(asset) and len(asset["rules"]) >= 13,
          asset and asset["rules"])
    check("S2 · 最高准则含原图比例/原视角/1:1 对齐", bool(asset) and
          "原图比例" in asset["supreme"] and "原视角" in asset["supreme"] and
          "1:1" in asset["supreme"])
    check("S2 · 鸟瞰对齐含道路边界条款", bool(asset) and "道路" in asset["aerial"])
    check("S2 · 去除标注条款含红色矩形框", bool(asset) and
          "红色矩形框" in asset["annotation"])
    check("S2 · 8 条风格识别正则", bool(asset) and asset["styleRules"] == 8)
    check("S1 · 5 个中文结构化预设", bool(asset) and set(asset["struct"]) ==
          {"night", "winter", "autumn", "spring", "summer"}, asset and asset["struct"])
    check("S1 · 预设沿用 8 段 schema", bool(asset) and
          {"任务", "指令", "调色逻辑", "氛围效果", "保留规则", "摄影参数", "渲染精度"}
          .issubset(set(asset["structKeys"])), asset and asset["structKeys"])
    check("S1 · styleMap 2 项 8 维", bool(asset) and len(asset["styleMap"]) == 2 and
          len(asset["styleMapDims"]) == 8, asset and asset["styleMapDims"])
    check("S1 · 画风长提示词 12 条", bool(asset) and asset["artStyles"] == 12)
    check("S3 · 15 组控件字典", bool(asset) and len(asset["controls"]) == 15 and
          asset["meta"] == 15, asset and asset["controls"])
    check("S3 · 时段 8 / 渲染时间 8 / 天气 8",
          bool(asset) and (asset["time"], asset["renderTime"], asset["weather"]) == (8, 8, 8))
    check("S3 · 季节 4 / 画风 12 / 宫格 4",
          bool(asset) and (asset["season"], asset["style"], asset["layout"]) == (4, 12, 4))
    check("S3 · 相机 8 / 裁剪 8 / 张数 4 / 放大 3 / 运镜 21",
          bool(asset) and (asset["camera"], asset["crop"], asset["count"],
                           asset["upscale"], asset["motion"]) == (8, 8, 4, 3, 21),
          asset and (asset["motion"],))
    check("S3 · 室内 21 / 公装 13",
          bool(asset) and (asset["interior"], asset["publicInterior"]) == (21, 13))
    check("S3 · 建筑两级 12/69、景观两级 12/66",
          bool(asset) and (asset["buildingTop"], asset["buildingSub"],
                           asset["landscapeTop"], asset["landscapeSub"]) == (12, 69, 12, 66),
          asset and (asset["buildingTop"], asset["buildingSub"],
                     asset["landscapeTop"], asset["landscapeSub"]))
    check("S1 · 4 条技能映射到结构化类型",
          bool(asset) and asset["skillKind"] == {
              "bi-time": "time", "bi-season": "season",
              "bi-style": "style", "bi-story": "story"}, asset and asset["skillKind"])
    check("合规声明保留来源说明", bool(asset) and "借鉴" in asset["source"])

    # ========== B. 兼容底线：内置技能数量与一级菜单 ==========
    src = open(r"E:\无限画布\proto\canvas.src.html", encoding="utf-8").read()
    # v3.0 起版本号随发版变化，这里只保证「关于页仍写有 vX.Y 版本号」不被删掉
    check("兼容 · 关于页仍保留 vX.Y 版本号", bool(re.search(r"v\d+\.\d+", src)),
          (re.search(r"v\d+\.\d+", src) or [""])[0])
    check("兼容 · 关于页技能条数与数据一致", "21 条（通用 14 / 专项 7）" in src)

    # ========== C. 参数浮层 UI ==========
    cid = make_card("v24 参数浮层原图")
    check("生成出可编辑卡片", bool(cid), cid)
    page.click('.snc-node[data-id="%s"]' % cid)
    page.wait_for_timeout(250)

    page.click('#sncImgBar button[data-act="skill"]')
    page.wait_for_timeout(350)
    gen_n = page.evaluate("""() => {
        const t = Array.from(document.querySelectorAll('#sncSkpBody .snc-skp-tile em'))
                       .map(x => x.textContent.trim());
        return {n: t.length, names: t};
    }""")
    check("兼容 · 通用技能 10 + 渲染 4 = 14 条", gen_n["n"] == 14, gen_n["n"])
    page.keyboard.press("Escape")
    page.wait_for_timeout(250)

    open_edit(cid)
    check("编辑面板已打开", page.evaluate("() => !document.getElementById('sncCompose').hidden"))
    check("参数按钮在编辑面板标题栏", page.locator("#sncStructBtn").count() == 1)
    check("参数浮层默认隐藏", page.evaluate("() => document.getElementById('sncStructPanel').hidden"))

    lay = page.evaluate("""() => {
        const g = s => { const e=document.querySelector(s); return e?e.getBoundingClientRect():null; };
        const m=g('#sncComposeMedia'), e=g('.snc-compose-editor'), f=g('.snc-compose-foot');
        return {m:m&&Math.round(m.top), e:e&&Math.round(e.top), f:f&&Math.round(f.top),
                wrap:getComputedStyle(document.querySelector('.snc-compose-foot')).flexWrap,
                sendTop:Math.round(g('.snc-compose-foot #sncComposeSend').top),
                footTop:f&&Math.round(f.top)};
    }""")
    check("兼容 · 三段式顺序未被参数浮层破坏",
          lay["m"] < lay["e"] < lay["f"], lay)
    check("兼容 · 底部工具条仍不换行", lay["wrap"] == "nowrap" and
          0 <= lay["sendTop"] - lay["footTop"] < 30, lay)

    page.click("#sncStructBtn")
    page.wait_for_timeout(300)
    panel = page.evaluate("""() => {
        const p = document.getElementById('sncStructPanel');
        const r = p.getBoundingClientRect();
        return {hidden:p.hidden, rows:document.querySelectorAll('#sncStructGrid .snc-struct-row').length,
                selects:document.querySelectorAll('#sncStructGrid select').length,
                two:document.querySelectorAll('#sncStructGrid .snc-struct-row.is-two').length,
                inView:r.left>=0 && r.top>=0 && r.right<=innerWidth+1 && r.bottom<=innerHeight+1,
                rect:[Math.round(r.left),Math.round(r.top),Math.round(r.width),Math.round(r.height)]};
    }""")
    check("点「参数」打开独立浮层", not panel["hidden"])
    check("浮层渲染 15 组控件", panel["rows"] == 15, panel["rows"])
    check("两级分类有 2 个额外 select、共 17 个下拉",
          panel["two"] == 2 and panel["selects"] == 17, panel)
    check("浮层完整落在窗口内", panel["inView"], panel["rect"])

    page.select_option('#sncStructGrid select[data-sk="weather"]', "mist")
    page.wait_for_timeout(150)
    check("选天气后计数变 1", page.inner_text("#sncStructCount") == "已选 1 项",
          page.inner_text("#sncStructCount"))

    page.select_option('#sncStructGrid select[data-sk="building"][data-lv="p"]', "office")
    page.wait_for_timeout(200)
    kids = page.evaluate("""() => {
        const s = document.querySelector('#sncStructGrid select[data-sk="building"][data-lv="c"]');
        return {disabled:s.disabled, n:s.options.length-1, first:s.options[1]&&s.options[1].text};
    }""")
    check("S3 · 建筑大类联动出 7 个子类", not kids["disabled"] and kids["n"] == 7, kids)
    page.select_option('#sncStructGrid select[data-sk="building"][data-lv="c"]', "high_rise_office")
    page.wait_for_timeout(150)
    check("两级值写入参数（计数 2）", page.inner_text("#sncStructCount") == "已选 2 项",
          page.inner_text("#sncStructCount"))

    page.select_option('#sncStructGrid select[data-sk="building"][data-lv="p"]', "commercial")
    page.wait_for_timeout(200)
    check("切大类后子类重置、两级参数自动撤下",
          page.inner_text("#sncStructCount") == "已选 1 项" and
          page.evaluate("""() => document.querySelector(
              '#sncStructGrid select[data-sk="building"][data-lv="c"]').value""") == "__none__",
          page.inner_text("#sncStructCount"))

    page.fill("#sncComposeInput", "把庭院改成清晨薄雾氛围")
    page.click("#sncStructPreviewBtn")
    page.wait_for_timeout(250)
    prev = page.evaluate("""() => {
        const p=document.getElementById('sncStructPreview');
        return {hidden:p.hidden, text:p.textContent};
    }""")
    check("预览可见且含【最高准则】", not prev["hidden"] and "【最高准则】" in prev["text"])
    check("预览逐字保留原提示词在最前", prev["text"].startswith("把庭院改成清晨薄雾氛围"))
    check("预览含控件参数（天气薄雾）", "控件参数" in prev["text"] and "薄雾" in prev["text"])
    page.screenshot(path=os.path.join(SHOTS, "v24-结构化参数浮层.png"))

    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    check("Esc 先收浮层、编辑面板仍在",
          page.evaluate("() => document.getElementById('sncStructPanel').hidden") and
          not page.evaluate("() => document.getElementById('sncCompose').hidden"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    check("再按一次 Esc 才关编辑面板",
          page.evaluate("() => document.getElementById('sncCompose').hidden"))

    # ========== D. 老路径逐字不变 ==========
    reset_struct()
    cid2 = make_card("v24 手写指令原图")
    open_edit(cid2)
    page.fill("#sncComposeInput", "把墙面换成暖色石材，保留构图")
    bodies.clear()
    page.click("#sncComposeSend")
    page.wait_for_timeout(1200)
    b0 = last_body()
    pr0 = b0.get("prompt") or ""
    check("兼容 · 手写提交 prompt 逐字以原句开头", pr0.startswith("把墙面换成暖色石材，保留构图"),
          pr0[:70])
    check("兼容 · 手写提交不带结构化包装", "最高准则" not in pr0 and "【要求" not in pr0)
    check("兼容 · 参考图说明仍在请求体", "参考图说明" in pr0)
    check("兼容 · 编辑提交仍携带参考图", bool(b0.get("images")))

    # ========== E. S1 + S2：四条技能提交时的结构化增强 ==========
    def skill_submit(skill, chip, opt):
        reset_struct()
        c = make_card("v24 技能 " + skill)
        page.click('.snc-node[data-id="%s"]' % c)
        page.wait_for_timeout(250)
        # v3.7：点技能直接弹工作台，提示词就在输入框里，选完参数点「生成」
        page.click('#sncImgBar button[data-act="skill"]')
        page.wait_for_timeout(350)
        click_skill(skill)
        page.wait_for_timeout(350)
        pick_opt(chip, opt)
        filled = page.evaluate("() => document.getElementById('sncSkWinText').value")
        bodies.clear()
        page.click("#sncSkWinGo")
        page.wait_for_timeout(1200)
        return (last_body().get("prompt") or ""), filled

    pr, filled = skill_submit("时间迁移", "时段", "傍晚")
    check("S1 · 时间迁移：编辑框仍是旧的单句指令", "把画面时间改为" in filled and "傍晚" in filled,
          filled[:60])
    check("S2 · 时间迁移提交带【最高准则】", "【最高准则】" in pr)
    check("S1 · 时间迁移提交带光照调整 + 时段光照规则",
          "光照调整" in pr and "时段光照规则" in pr and "傍晚" in pr)
    check("S2 · 固定尾段摄影参数 / 渲染精度齐备",
          "摄影参数" in pr and "渲染精度" in pr and "尼康 Z9" in pr)

    pr, filled = skill_submit("季节迁移", "季节", "冬季")
    check("S1 · 季节迁移：编辑框仍含「冬季」", "冬季" in filled, filled[:60])
    check("S1 · 季节迁移提交带季节调整 + 冬季休眠期",
          "季节调整" in pr and "冬季休眠期" in pr and "落叶或稀疏树冠" in pr)

    pr, filled = skill_submit("画风迁移", "画风", "水彩")
    check("S1 · 画风迁移提交带 8 维风格表",
          "风格维度" in pr and "style_name" in pr and "Watercolor" in pr and
          "texture_logic" in pr, pr[:80])
    check("S1 · 画风迁移提交带中文画风执行细则",
          "画风执行细则" in pr and "水彩" in pr)
    check("S2 · 8 条风格识别规则可用", bool(asset) and asset["styleRules"] == 8)

    pr, filled = skill_submit("场景分镜", "宫格", "九宫格")
    check("S1 · 场景分镜：提示词含九宫格", "九宫格" in filled, filled[:60])
    check("S1 · 场景分镜提交带网格与分镜一致性规则",
          "九宫格" in pr and "分镜一致性规则" in pr)

    # ========== F. S3 参数与全局开关、JSON 格式 ==========
    reset_struct()
    cid3 = make_card("v24 参数注入原图")
    open_edit(cid3)
    page.click("#sncStructBtn")
    page.wait_for_timeout(250)
    page.select_option('#sncStructGrid select[data-sk="camera"]', "Canon EOS R5")
    page.select_option('#sncStructGrid select[data-sk="upscale"]', "8k")
    page.wait_for_timeout(150)
    check("S3 · 选 2 项后计数为 2", page.inner_text("#sncStructCount") == "已选 2 项")
    page.fill("#sncComposeInput", "保持构图，强化材质细节")
    bodies.clear()
    page.click("#sncComposeSend")
    page.wait_for_timeout(1200)
    pr = last_body().get("prompt") or ""
    check("S3 · 手写提交因参数带【最高准则】", "【最高准则】" in pr)
    check("S3 · 相机与放大档写进控件参数",
          "控件参数" in pr and "Canon EOS R5" in pr and "8K" in pr)
    check("S3 · 原提示词仍逐字在最前", pr.startswith("保持构图，强化材质细节"))

    # v3.7.1：「应用到所有生成」开关已移除 —— 手写提交永不被包装，塞旧标记也不管用
    reset_struct()
    page.evaluate("() => localStorage.setItem('snc.struct.all','1')")
    page.reload()
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(700)
    cid4 = make_card("v24 全局开关已移除原图")
    open_edit(cid4)
    page.fill("#sncComposeInput", "只压暗天空")
    bodies.clear()
    page.click("#sncComposeSend")
    page.wait_for_timeout(1200)
    pr = last_body().get("prompt") or ""
    check("S2 · 开关已移除：手写提交不再被包装",
          "【最高准则】" not in pr and "摄影参数" not in pr, pr[:80])
    check("S2 · 旧标记已被自动清掉",
          page.evaluate("() => localStorage.getItem('snc.struct.all')") is None)

    # JSON 格式（v3.7.1：走参数浮层这条明确带上下文的路径，不再靠全局开关）
    page.evaluate("() => localStorage.setItem('snc.struct.fmt','json')")
    cid5 = make_card("v24 JSON 格式原图")
    open_edit(cid5)
    page.click("#sncStructBtn")
    page.wait_for_timeout(320)
    page.select_option('#sncStructGrid select[data-sk="weather"]', "mist")
    page.wait_for_timeout(220)
    page.fill("#sncComposeInput", "改成阴天柔光")
    bodies.clear()
    page.click("#sncComposeSend")
    page.wait_for_timeout(1200)
    pr = last_body().get("prompt") or ""
    json_head = pr.split("\n\n参考图说明")[0]
    try:
        obj = json.loads(json_head)
    except Exception:
        obj = {}
    check("S2 · JSON 格式输出合法 {最高准则, 要求}",
          set(obj.keys()) == {"最高准则", "要求"}, list(obj.keys()))
    check("S2 · JSON 的「要求」保留原始要求",
          obj.get("要求", {}).get("原始要求") == "改成阴天柔光")

    # 关掉开关，恢复逐字不变
    reset_struct()
    cid6 = make_card("v24 回退验证原图")
    open_edit(cid6)
    page.fill("#sncComposeInput", "回退验证：什么都不加")
    bodies.clear()
    page.click("#sncComposeSend")
    page.wait_for_timeout(1200)
    pr = last_body().get("prompt") or ""
    check("兼容 · 关掉开关后老链路恢复逐字不变",
          pr.startswith("回退验证：什么都不加") and "最高准则" not in pr and "参考图说明" in pr,
          pr[:70])

    # ========== G. 亮色主题 + 无 JS 报错 ==========
    page.evaluate("() => { try{localStorage.setItem('snc.theme.v1','light')}catch(e){} }")
    page.reload()
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(800)
    lite = page.evaluate("""() => {
        const s = document.createElement('div');
        s.className = 'snc-struct-panel';
        s.style.position='fixed'; s.style.left='10px'; s.style.top='10px';
        document.getElementById('snc').appendChild(s);
        const c = getComputedStyle(s).backgroundColor;
        s.remove();
        return {theme:document.getElementById('snc').getAttribute('data-theme'), bg:c};
    }""")
    def lum(rgb):
        parts = rgb.replace("rgba(", "").replace("rgb(", "").replace(")", "").split(",")[:3]
        v = [float(x.strip()) for x in parts]
        return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
    check("亮色主题下浮层为浅底", lite["theme"] == "light" and lum(lite["bg"]) > 150, lite)
    page.screenshot(path=os.path.join(SHOTS, "v24-亮色主题.png"))

    check("全程无 JS 报错", not errs, errs[:3])

    ctx.close()
    br.close()

passed = sum(1 for _, ok in results if ok)
print("\n%d / %d 通过" % (passed, len(results)))
sys.exit(0 if passed == len(results) else 1)
