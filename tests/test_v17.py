# -*- coding: utf-8 -*-
"""v1.8 回归：技能面板 / 放大选尺寸 / 对比滑条 / 框选与增强派生、
滚动条收细、设置入口在左下角、技能 / 链接(MCP) / 记录 三个工作台页面。
出图全部走存根，不消耗额度。"""
import base64
import json
import os
import struct
import tempfile
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
    errs, bodies = [], []
    page.on("pageerror", lambda e: errs.append(str(e)))

    def gen(route):
        bodies.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True, "b64": PNG64, "size": "2048x1280",
                                       "width": 2048, "height": 1280, "format": "png",
                                       "model": "stub-image", "mode": "gen",
                                       "latencyMs": 800, "usage": {"total_tokens": 300}}))

    def polish(route):
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"ok": True, "text": "润色后的完整提示词", "model": "stub-text",
                                       "latencyMs": 500}, ensure_ascii=False))

    page.route("**/api/generate", gen)
    page.route("**/api/polish", polish)
    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(1300)
    return ctx, page, errs, bodies


def cards(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll('.snc-node')).map(d => {
        const r = d.getBoundingClientRect();
        const img = d.querySelector('.snc-gen img');
        return {id: d.dataset.id,
                label: (d.querySelector('.snc-node-label')||{}).textContent || '',
                x: r.x, y: r.y, w: r.width, h: r.height,
                srcLen: img ? (img.getAttribute('src')||'').length : 0,
                status: d.querySelector('.snc-gen-wait') ? 'busy' :
                        (d.querySelector('.snc-gen-fail') ? 'failed' : 'done')};
    })""")


def edges(page):
    return page.evaluate("() => document.querySelectorAll('#sncEdges path').length")


def select(page, card):
    page.mouse.click(card["x"] + card["w"] / 2, card["y"] + card["h"] / 2)
    page.wait_for_timeout(260)


def open_wb(page, tab):
    page.click('#sncDocNav button[data-wb="%s"]' % tab)
    page.wait_for_selector("#sncWb:not([hidden])", timeout=3000)
    page.wait_for_timeout(220)


with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    ctx, page, errs, bodies = boot(br)

    # ---------- 1. 技能面板 ----------
    start = cards(page)
    target = [c for c in start if c["label"].strip().startswith("图片 1")][0]
    select(page, target)
    page.click('#sncImgBar button[data-act="skill"]')
    page.wait_for_timeout(330)
    pop = page.evaluate("""() => {
        const p = document.getElementById('sncSkillPop');
        if(p.hidden) return null;
        const r = p.getBoundingClientRect();
        const tiles = document.querySelectorAll('.snc-skp-tile');
        return {x: r.x, y: r.y, w: r.width, h: r.height, tiles: tiles.length,
                inbox: r.x >= 0 && r.y >= 0 && r.x + r.width <= innerWidth &&
                       r.y + r.height <= innerHeight,
                withArt: document.querySelectorAll('.snc-skp-tile.has-art').length,
                withImg: document.querySelectorAll('.snc-skp-tile.has-img').length,
                srcs: Array.from(document.querySelectorAll('#sncSkpBody .snc-skp-tile img'))
                            .map(i => i.getAttribute('src') || ''),
                loaded: Array.from(document.querySelectorAll('#sncSkpBody .snc-skp-tile img'))
                            .filter(i => i.complete && i.naturalWidth > 0).length,
                tabs: Array.from(document.querySelectorAll('#sncSkpTabs button')).map(b => b.textContent.trim())};
    }""")
    check("工具条「技能」弹出技能面板", bool(pop), pop)
    check("通用技能列表非空且整块在窗口内",
          bool(pop) and pop["tiles"] >= 6 and pop["inbox"], pop)
    # v1.9：内置技能改用各自的效果预览图；v3.7 渲染 4 条并回通用页并补齐了预览图
    check("每条技能都带自己的效果预览图",
          bool(pop) and pop["withArt"] == pop["tiles"] and pop["withImg"] == 0, pop)
    # v3.7.4：预览图从内联 base64 改成 /art/ 外链，src 不再是几万字符的 data URL。
    # 原来的判据（src 长度 >2000 且互不相同）语义是「每张都是独立的一张图」，
    # 换成路径后仍能表达：互不相同的 /art/ 路径 + 真的加载出来了（naturalWidth > 0）。
    check("每张预览图内容不同（不是同一张图重复）",
          bool(pop) and len(set(pop["srcs"])) == len(pop["srcs"])
          and all(x.startswith("/art/") for x in pop["srcs"]),
          pop["srcs"] if pop else None)
    check("预览图都真的加载出来了",
          bool(pop) and pop["loaded"] == len(pop["srcs"]), pop["loaded"] if pop else None)
    check("有「通用技能 / 专项技能」两个分组",
          bool(pop) and len(pop["tabs"]) >= 2 and "专项" in pop["tabs"][1], pop["tabs"] if pop else None)

    page.click('#sncSkpTabs button[data-g="pro"]')
    page.wait_for_timeout(220)
    pro_n = page.evaluate("() => document.querySelectorAll('#sncSkpBody .snc-skp-tile').length")
    check("专项技能分组可切换", pro_n >= 4, pro_n)

    page.click('#sncSkpBody .snc-skp-tile')
    page.wait_for_timeout(600)
    # v3.7：点技能不再把指令灌进编辑面板，而是弹技能工作台，提示词就在窗里的输入框
    filled = page.evaluate("""() => {
        const w = document.getElementById('sncSkWin');
        const t = document.getElementById('sncSkWinText');
        return {open: !w.hidden, len: (t.value || '').length,
                pop: !document.getElementById('sncSkillPop').hidden,
                compose: !document.getElementById('sncCompose').hidden,
                editing: document.activeElement === t};
    }""")
    check("点技能后弹出技能工作台并带上提示词",
          bool(filled) and filled["open"] and filled["len"] > 60, filled)
    check("点技能不再打开编辑面板", bool(filled) and not filled["compose"], filled)
    check("套用后技能面板自动收起", bool(filled) and not filled["pop"], filled)
    check("光标落在输入框里可以直接改", bool(filled) and filled["editing"], filled)
    same0 = [c for c in cards(page) if c["id"] == target["id"]]
    check("只看技能不烧额度（没有发出请求）", len(bodies) == 0, len(bodies))
    page.keyboard.press("Escape")
    page.wait_for_timeout(250)

    # 搜索
    select(page, target)
    page.click('#sncImgBar button[data-act="skill"]')
    page.wait_for_timeout(300)
    page.fill("#sncSkpSearch", "夜景")
    page.wait_for_timeout(260)
    hit = page.evaluate("""() => Array.from(document.querySelectorAll('#sncSkpBody .snc-skp-tile em'))
        .map(e => e.textContent)""")
    check("技能面板可搜索", len(hit) >= 1 and any("夜景" in h for h in hit), hit)
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)

    # ---------- 2. 增强派生 ----------
    before_e = cards(page)
    img_card = [c for c in before_e if c["label"].strip().startswith("图片 2")][0]
    e1 = edges(page)
    select(page, img_card)
    page.click('#sncImgBar button[data-act="enhance"]')
    page.wait_for_timeout(2200)
    after_e = cards(page)
    enh = [c for c in after_e if "增强" in c["label"]]
    check("增强生成 1 张派生卡", len(after_e) == len(before_e) + 1, (len(before_e), len(after_e)))
    check("增强卡标签带「增强」", len(enh) == 1, [c["label"] for c in enh])
    check("增强卡与父图连线", edges(page) >= e1 + 1, (e1, edges(page)))
    same2 = [c for c in after_e if c["id"] == img_card["id"]]
    check("增强不改原图", bool(same2) and same2[0]["srcLen"] == img_card["srcLen"])

    # ---------- 3. 放大：先选尺寸 ----------
    before_u = cards(page)
    pick = [c for c in before_u if c["label"].strip().startswith("图片 4")][0]
    select(page, pick)
    page.click('#sncImgBar button[data-act="upscale"]')
    page.wait_for_timeout(320)
    menu = page.evaluate("""() => {
        const m = document.getElementById('sncUpMenu');
        if(m.hidden) return null;
        return {items: Array.from(m.querySelectorAll('button[data-up]'))
                        .map(b => ({up: b.dataset.up, bd: b.disabled}))};
    }""")
    check("放大先弹尺寸菜单（2K / 4K / 8K）",
          bool(menu) and [i["up"] for i in menu["items"]] == ["2048", "4096", "8192"], menu)
    page.click('#sncUpMenu button[data-up="4096"]')
    page.wait_for_timeout(2600)
    after_u = cards(page)
    up = [c for c in after_u if "4K" in c["label"]]
    check("放大生成 1 张派生卡", len(after_u) == len(before_u) + 1, (len(before_u), len(after_u)))
    check("放大卡标签带「4K」", len(up) == 1, [c["label"] for c in up])
    up_body = bodies[-1] if bodies else {}
    check("放大请求 res=4096 且不交给 auto",
          str(up_body.get("res")) == "4096" and up_body.get("sizeMode") != "auto",
          (up_body.get("res"), up_body.get("sizeMode")))
    same3 = [c for c in after_u if c["id"] == pick["id"]]
    check("放大不改原图", bool(same3) and same3[0]["srcLen"] == pick["srcLen"])
    check("尺寸菜单选完自动收起", page.is_hidden("#sncUpMenu"))

    # ---------- 3.1 8K：4K 重绘之后本地再 2 倍 ----------
    before8 = cards(page)
    pick8 = [c for c in before8 if c["label"].strip().startswith("图片 4")][0]
    select(page, pick8)
    page.click('#sncImgBar button[data-act="upscale"]')
    page.wait_for_timeout(320)
    page.click('#sncUpMenu button[data-up="8192"]')
    page.wait_for_timeout(2600)
    after8 = cards(page)
    up8 = [c for c in after8 if "8K" in c["label"]]
    check("8K 生成派生卡", len(up8) == 1, [c["label"] for c in up8])
    real8 = page.evaluate("""() => {
        const n = Array.from(document.querySelectorAll('.snc-node'))
            .find(d => (d.querySelector('.snc-node-label')||{}).textContent.indexOf('8K') >= 0);
        const b = n && n.querySelector('.snc-sizebadge');
        const img = n && n.querySelector('.snc-gen img');
        return JSON.stringify({badge: b ? b.textContent : '',
            head: img ? (img.getAttribute('src')||'').slice(0,22) : '',
            len: img ? img.getAttribute('src').length : 0});
    }""")
    # 存根图是 160×100，2 倍后应当报 320×200 —— 证明本地超采样真的执行了
    check("8K 做了本地 2 倍（尺寸翻倍）",
          '"badge":"320 × 200"' in real8 and "jpeg" in real8, real8)
    up8_body = bodies[-1] if bodies else {}
    check("8K 的模型请求仍是 4K 上限",
          str(up8_body.get("res")) == "4096", up8_body.get("res"))

    # ---------- 3.2 对比预览：派生前后同位置对照 ----------
    select(page, up[0])
    page.click('#sncImgBar button[data-act="compare"]')
    page.wait_for_timeout(400)
    cmp0 = page.evaluate("""() => {
        const b = document.querySelector('.snc-node.is-sel .snc-cmp-b') ||
                  document.querySelector('.snc-cmp-b');
        if(!b) return null;
        const clip = b.querySelector('.snc-cmp-clip');
        const tags = Array.from(b.querySelectorAll('.snc-cmp-tag')).map(t => t.textContent.trim());
        const grip = b.querySelector('.snc-cmp-grip');
        const r = b.getBoundingClientRect();
        const gr = grip.getBoundingClientRect();
        return {clip: getComputedStyle(clip).clipPath, tags: tags,
                x: r.x, y: r.y, w: r.width, h: r.height,
                gx: gr.x + gr.width / 2, gy: gr.y + gr.height / 2,
                imgs: b.querySelectorAll('img').length};
    }""")
    check("点对比预览后卡片进入左右对照", bool(cmp0) and cmp0["imgs"] == 2, cmp0)
    check("对照两侧标注「原图 / 改后」",
          bool(cmp0) and len(cmp0["tags"]) == 2 and "图片" in cmp0["tags"][0], cmp0["tags"] if cmp0 else None)
    if cmp0:
        page.mouse.move(cmp0["gx"], cmp0["gy"])
        page.mouse.down()
        page.mouse.move(cmp0["x"] + cmp0["w"] * 0.78, cmp0["gy"], steps=10)
        page.mouse.up()
        page.wait_for_timeout(260)
        clip_after = page.evaluate("""() => {
            const c = document.querySelector('.snc-cmp-clip');
            return c ? getComputedStyle(c).clipPath : '';
        }""")
        check("拖动中间滑条改变可见分界", clip_after != cmp0["clip"], (cmp0["clip"], clip_after))
    page.click('#sncImgBar button[data-act="compare"]')
    page.wait_for_timeout(300)
    check("再点一次退出对比", page.evaluate("() => !document.querySelector('.snc-cmp-b')"))

    # ---------- 3.5 局部重绘也派生（v2.8 起统一走工作台，快速框选已撤） ----------
    before_m = cards(page)
    mcard = [c for c in before_m if c["label"].strip().startswith("图片 5")][0]
    e2 = edges(page)
    select(page, mcard)
    page.click('#sncImgBar button[data-act="inpaint"]')
    page.wait_for_timeout(600)
    maskbox = page.locator("#sncInpMask").bounding_box()
    page.mouse.move(maskbox["x"] + maskbox["width"] * 0.25, maskbox["y"] + maskbox["height"] * 0.3)
    page.mouse.down()
    page.mouse.move(maskbox["x"] + maskbox["width"] * 0.7, maskbox["y"] + maskbox["height"] * 0.75,
                    steps=8)
    page.mouse.up()
    page.wait_for_timeout(240)
    page.fill("#sncInpPrompt", "把这块地面换成深灰色花岗岩铺装，保留接缝走向")
    page.click("#sncInpGo")
    page.wait_for_timeout(2600)
    after_m = cards(page)
    reg = [c for c in after_m if "局部" in c["label"]]
    check("局部重绘派生新卡", len(after_m) == len(before_m) + 1, (len(before_m), len(after_m)))
    check("局部卡与父图连线", edges(page) >= e2 + 1, (e2, edges(page)))
    same_m = [c for c in after_m if c["id"] == mcard["id"]]
    check("局部重绘不改原图",
          len(reg) == 1 and bool(same_m) and same_m[0]["srcLen"] == mcard["srcLen"],
          [c["label"] for c in reg])

    # ---------- 4. 编辑面板滚动条 ----------
    sel_card = [c for c in cards(page) if c["label"].strip().startswith("图片 1")][0]
    select(page, sel_card)
    page.click('#sncImgBar button[data-act="edit"]')
    page.wait_for_timeout(420)
    page.fill("#sncComposeInput", "把地面换成深色木平台，保留机位与构图。" * 22)
    page.wait_for_timeout(220)
    css = page.evaluate("""() => {
        const t = document.getElementById('sncComposeInput');
        const cs = getComputedStyle(t);
        return {sw: cs.scrollbarWidth, color: cs.scrollbarColor, maxH: cs.maxHeight,
                sh: t.scrollHeight, ch: t.clientHeight, ow: t.offsetWidth, cw: t.clientWidth};
    }""")
    check("编辑框滚动条改细（scrollbar-width: thin）", css["sw"] == "thin", css["sw"])
    check("滚动条颜色压成半透明", "rgba" in str(css["color"]).lower(), css["color"])
    check("多行提示词时输入框限高并可滚动",
          css["sh"] > css["ch"] and int(css["maxH"].replace("px", "")) <= 120, (css["sh"], css["ch"], css["maxH"]))
    page.screenshot(path=os.path.join(SHOT_DIR, "v17-编辑面板-细滚动条.png"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)

    # ---------- 4.5 设置入口在左下角 ----------
    gear = page.evaluate("""() => {
        const b = document.querySelector('.snc-doc-foot .snc-gear');
        if(!b) return null;
        const r = b.getBoundingClientRect();
        const nav = document.querySelector('.snc-doc-nav').getBoundingClientRect();
        return {x: r.x, y: r.y, w: r.width, h: r.height,
                vw: innerWidth, vh: innerHeight,
                belowNav: r.y > nav.y + nav.height};
    }""")
    check("设置按钮移到了左下角（侧栏底部）", bool(gear), gear)
    check("设置按钮在窗口左下区域",
          bool(gear) and gear["x"] < 240 and gear["y"] > gear["vh"] - 120, gear)
    if gear:
        page.mouse.click(gear["x"] + gear["w"] / 2, gear["y"] + gear["h"] / 2)
        page.wait_for_timeout(400)
        check("点左下角齿轮打开设置", page.evaluate("() => !document.getElementById('sncSettings').hidden"))
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)

    # ---------- 5. 技能页 ----------
    open_wb(page, "skills")
    sk = page.evaluate("() => document.querySelectorAll('[data-pane=\"skills\"] .snc-sk').length")
    check("内置技能全部渲染", sk == 21, sk)
    check("侧栏技能计数 = 21", page.inner_text("#sncNavSkill").strip() == "21",
          page.inner_text("#sncNavSkill"))
    page.screenshot(path=os.path.join(SHOT_DIR, "v17-技能页.png"))

    page.click('#sncWbTabs button[data-wb="skills"]')
    page.locator('[data-pane="skills"] .snc-sk button[data-sk="use"]').first.click()
    page.wait_for_timeout(260)
    val = page.input_value("#sncInput")
    check("「用这个」把指令灌进输入框", len(val) > 60 and "夜景" in val, len(val))
    check("套用后回到画布", page.is_hidden("#sncWb"))

    # 新建技能
    open_wb(page, "skills")
    page.click("#sncWbNew")
    page.wait_for_selector("#sncSkillDlg:not([hidden])")
    page.fill("#sncSkillName", "测试技能")
    page.fill("#sncSkillDesc", "自动化测试用")
    page.fill("#sncSkillPrompt", "把这张图改成阴天柔光，保持构图与物体位置不变。")
    page.click("#sncSkillSave")
    page.wait_for_timeout(320)
    mine = page.evaluate("() => document.querySelectorAll('[data-pane=\"skills\"] .snc-sk .snc-tag.mine').length")
    check("自建技能出现在「我的技能」", mine == 1, mine)

    # 导入 SKILL.md
    md = "---\nname: 夜间照明检查\ndescription: 检查灯具布置是否有眩光与暗区\n---\n\n" \
         "逐项检查这张夜景效果图的灯具位置：是否出现眩光、地面是否有暗区、灯具有没有穿模，给出修改建议。"
    tmpdir = tempfile.mkdtemp()
    mdp = os.path.join(tmpdir, "SKILL.md")
    with open(mdp, "w", encoding="utf-8") as f:
        f.write(md)
    page.set_input_files("#sncSkillImport", mdp)
    page.wait_for_timeout(520)
    names = page.evaluate("""() => Array.from(document.querySelectorAll('[data-pane="skills"] .snc-sk b'))
        .map(b => b.textContent)""")
    check("导入 SKILL.md 读到 YAML 里的 name", "夜间照明检查" in names, names[:4])
    check("导入的技能标为「导入」",
          page.evaluate("() => document.querySelectorAll('[data-pane=\"skills\"] .snc-tag.imp').length") == 1)

    # ---------- 6. 链接（MCP） ----------
    page.click('#sncWbTabs button[data-wb="mcp"]')
    page.wait_for_timeout(240)
    page.click("#sncWbNew")
    page.wait_for_selector("#sncMcpDlg:not([hidden])")
    page.fill("#sncMcpText", json.dumps({"mcpServers": {
        "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "E:\\无限画布"]}
    }}, ensure_ascii=False))
    page.click("#sncMcpSave")
    page.wait_for_timeout(360)
    mcp_names = page.evaluate("() => Array.from(document.querySelectorAll('.snc-mcp b')).map(b => b.textContent)")
    check("JSON 配置解析成连接", mcp_names == ["filesystem"], mcp_names)
    check("stdio 传输识别正确",
          page.evaluate("() => (document.querySelector('.snc-mcp .snc-tag')||{}).textContent") == "stdio")
    check("侧栏链接计数 = 1", page.inner_text("#sncNavMcp").strip() == "1")

    page.click("#sncWbNew")
    page.wait_for_selector("#sncMcpDlg:not([hidden])")
    page.fill("#sncMcpText", '[mcp_servers.remote]\nurl = "https://example.com/mcp"\n')
    page.click("#sncMcpSave")
    page.wait_for_timeout(360)
    check("Codex 的 TOML 写法也能解析",
          page.evaluate("() => document.querySelectorAll('.snc-mcp').length") == 2,
          page.evaluate("() => document.querySelectorAll('.snc-mcp').length"))
    tags = page.evaluate("""() => Array.from(document.querySelectorAll('.snc-mcp')).map(c =>
        c.querySelectorAll('.snc-tag')[0].textContent)""")
    check("url 连接识别为 http", "http" in tags, tags)
    page.screenshot(path=os.path.join(SHOT_DIR, "v17-链接页.png"))

    # 坏配置要有明确报错
    page.click("#sncWbNew")
    page.wait_for_selector("#sncMcpDlg:not([hidden])")
    page.fill("#sncMcpText", "{ 这不是 json }")
    page.click("#sncMcpSave")
    page.wait_for_timeout(200)
    st = page.inner_text("#sncMcpStatus")
    check("坏配置给出解析错误", "失败" in st or "解析" in st, st[:40])
    page.click("#sncMcpCancel")

    # ---------- 7. 记录 ----------
    page.click('#sncWbTabs button[data-wb="records"]')
    page.wait_for_timeout(420)
    rec = page.evaluate("() => document.querySelectorAll('.snc-rec').length")
    check("记录页列出所有出过的图", rec >= 5, rec)
    check("记录有日期分组",
          page.evaluate("() => document.querySelectorAll('.snc-rec-date').length") >= 1)
    page.screenshot(path=os.path.join(SHOT_DIR, "v17-记录页.png"))

    page.click('[data-pane="records"] .snc-rec')
    page.wait_for_timeout(420)
    check("点记录跳回画布并选中该图",
          page.is_hidden("#sncWb") and
          page.evaluate("() => document.querySelectorAll('.snc-node.is-sel').length") >= 1)
    check("跳转后镜头落在该卡片上", page.evaluate("""() => {
        const el = document.querySelector('.snc-node.is-sel');
        if(!el) return false;
        const r = el.getBoundingClientRect();
        return r.top > 0 && r.bottom < window.innerHeight;
    }"""))

    # ---------- 8. 窄窗口不破版 ----------
    page.set_viewport_size({"width": 1024, "height": 700})
    page.wait_for_timeout(420)
    open_wb(page, "skills")
    box = page.evaluate("""() => {
        const w = document.getElementById('sncWb').getBoundingClientRect();
        const top = document.querySelector('.snc-wb-top');
        return {w: w.width, h: w.height, scrollX: document.documentElement.scrollWidth > window.innerWidth,
                topOverflow: top.scrollWidth > top.clientWidth + 1};
    }""")
    check("窄窗口下工作台铺满且无横向溢出",
          box["w"] > 700 and not box["scrollX"] and not box["topOverflow"], box)
    page.screenshot(path=os.path.join(SHOT_DIR, "v17-窄窗-技能页.png"))
    page.keyboard.press("Escape")

    # ---------- 9. 刷新后数据还在 ----------
    page.reload()
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(1200)
    check("刷新后技能计数仍为 23", page.inner_text("#sncNavSkill").strip() == "23",
          page.inner_text("#sncNavSkill"))
    check("刷新后链接计数仍为 2", page.inner_text("#sncNavMcp").strip() == "2",
          page.inner_text("#sncNavMcp"))

    check("全程无 JS 报错", not errs, errs[:2])

    total = len(results)
    ok = sum(1 for _, v in results if v)
    print("\n%d / %d 通过" % (ok, total))
    br.close()
