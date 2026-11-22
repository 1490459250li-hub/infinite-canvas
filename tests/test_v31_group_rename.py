# -*- coding: utf-8 -*-
"""v3.1 回归：图层成组后组名可改（双击 / 小笔 / Esc 放弃 / 空名拒绝 / 24 字上限 / 刷新后仍生效）。

不依赖真实接口：整页只打开图层面板，不发任何生成请求。
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = os.environ.get("SNC_BASE", "http://127.0.0.1:8321/canvas.html")
SHOTS = r"E:\canvas-probe2\shots-v31"
os.makedirs(SHOTS, exist_ok=True)
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


errs = []

with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    ctx = br.new_context(viewport={"width": 1560, "height": 940})
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
    pg.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" else None)

    pg.goto(BASE)
    pg.wait_for_selector(".snc-node")
    pg.wait_for_timeout(700)

    def open_layers():
        if pg.evaluate("() => !!document.getElementById('sncLayers').hidden"):
            pg.click("#sncLayersBtn")
            pg.wait_for_timeout(320)

    def group_name():
        return pg.locator("#sncLayersBody .snc-layer-row.is-grp .snc-layer-t").first.inner_text()

    def start_edit(how="dblclick"):
        if how == "dblclick":
            pg.dblclick("#sncLayersBody .snc-layer-row.is-grp .snc-layer-t")
        else:
            pg.click("#sncLayersBody .snc-layer-row.is-grp button[data-gedit]")
        pg.wait_for_timeout(180)

    # ================= A. 先成组 =================
    print("\n== A 成组 ==")
    open_layers()
    check("图层面板已打开", pg.evaluate("() => !document.getElementById('sncLayers').hidden"))

    rows = pg.locator("#sncLayersBody .snc-layer-row[data-lid]").count()
    check("面板里有可成组的行", rows >= 3, rows)

    ids = pg.evaluate("""() => [...document.querySelectorAll('#sncLayersBody .snc-layer-row[data-lid]')]
        .slice(0, 2).map(r => r.dataset.lid)""")
    pg.click('.snc-layer-row[data-lid="%s"]' % ids[0])
    pg.keyboard.down("Shift")
    pg.click('.snc-layer-row[data-lid="%s"]' % ids[1])
    pg.keyboard.up("Shift")
    pg.wait_for_timeout(180)
    pg.click("#sncLayersGroup")
    pg.wait_for_timeout(320)

    check("出现组行", pg.locator("#sncLayersBody .snc-layer-row.is-grp").count() == 1)
    check("组内两行成员", pg.locator("#sncLayersBody .snc-layer-row.is-kid").count() == 2,
          pg.locator("#sncLayersBody .snc-layer-row.is-kid").count())
    auto = group_name()
    check("默认组名是「组 N」", auto.startswith("组") and auto.strip() != "组", auto)
    check("组名后面的数字单独成徽标",
          pg.locator("#sncLayersBody .snc-layer-row.is-grp .snc-layer-num").inner_text() == "2",
          pg.locator("#sncLayersBody .snc-layer-row.is-grp .snc-layer-num").inner_text())
    check("组行有改名小笔", pg.locator("#sncLayersBody .snc-layer-row.is-grp button[data-gedit]").count() == 1)

    # ================= B. 双击改名 =================
    print("\n== B 双击改名 ==")
    start_edit("dblclick")
    check("双击组名出现输入框", pg.locator("#sncLayersBody .snc-layer-input").count() == 1)
    check("输入框预填原组名",
          pg.input_value("#sncLayersBody .snc-layer-input") == auto,
          pg.input_value("#sncLayersBody .snc-layer-input"))
    check("改名时该行暂时不可拖动",
          pg.evaluate("""() => document.querySelector('#sncLayersBody .snc-layer-row.is-grp').draggable === false"""))

    pg.fill("#sncLayersBody .snc-layer-input", "庭院组")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(300)
    check("回车后组名已改", group_name() == "庭院组", group_name())
    check("回车后输入框收起", pg.locator("#sncLayersBody .snc-layer-input").count() == 0)
    check("改名后行恢复可拖动",
          pg.evaluate("""() => document.querySelector('#sncLayersBody .snc-layer-row.is-grp').draggable === true"""))
    check("改名后成员数不变", pg.locator("#sncLayersBody .snc-layer-row.is-kid").count() == 2)
    pg.screenshot(path=os.path.join(SHOTS, "v31-group-renamed.png"))

    # ================= C. 小笔入口 =================
    print("\n== C 小笔入口 ==")
    start_edit("btn")
    check("点小笔也能进编辑态", pg.locator("#sncLayersBody .snc-layer-input").count() == 1)
    pg.fill("#sncLayersBody .snc-layer-input", "主庭院")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(280)
    check("小笔改名生效", group_name() == "主庭院", group_name())

    # ================= D. Esc 放弃 / 空名拒绝 =================
    print("\n== D 放弃与校验 ==")
    start_edit()
    pg.fill("#sncLayersBody .snc-layer-input", "临时改的名")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(280)
    check("Esc 放弃后组名不变", group_name() == "主庭院", group_name())
    check("Esc 后输入框收起", pg.locator("#sncLayersBody .snc-layer-input").count() == 0)

    start_edit()
    pg.fill("#sncLayersBody .snc-layer-input", "   ")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(280)
    check("空白名被拒绝、保留原名", group_name() == "主庭院", group_name())

    start_edit()
    pg.fill("#sncLayersBody .snc-layer-input", "<b>带标签</b>")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(280)
    got = group_name()
    check("尖括号被清掉、不会注入标签", "<b>" not in got and "带标签" in got, got)

    start_edit()
    pg.fill("#sncLayersBody .snc-layer-input", "很长很长很长很长很长很长很长很长的组名字测试")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(280)
    check("组名最长 24 字", len(group_name()) <= 24, (len(group_name()), group_name()))

    # 收尾：改回一个有意义的名字，供持久化验证
    start_edit()
    pg.fill("#sncLayersBody .snc-layer-input", "庭院主景")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(240)

    # ================= E. 折叠展开与重开面板 =================
    print("\n== E 折叠 / 重开 ==")
    pg.click("#sncLayersBody .snc-layer-row.is-grp button[data-twist]")
    pg.wait_for_timeout(250)
    check("收起后成员行隐藏", pg.locator("#sncLayersBody .snc-layer-row.is-kid").count() == 0)
    check("收起后组名仍是新名字", group_name() == "庭院主景", group_name())
    pg.click("#sncLayersBody .snc-layer-row.is-grp button[data-twist]")
    pg.wait_for_timeout(250)
    check("展开后成员回来", pg.locator("#sncLayersBody .snc-layer-row.is-kid").count() == 2)

    pg.click("#sncLayersBtn")
    pg.wait_for_timeout(200)
    open_layers()
    check("关掉面板再打开，组名还在", group_name() == "庭院主景", group_name())

    # ================= F. 刷新后仍生效（真落盘） =================
    print("\n== F 持久化 ==")
    pg.wait_for_timeout(1600)
    pg.reload()
    pg.wait_for_selector(".snc-node")
    pg.wait_for_timeout(900)
    open_layers()
    check("刷新后组名仍是「庭院主景」", group_name() == "庭院主景", group_name())
    check("刷新后组内成员仍是 2 张", pg.locator("#sncLayersBody .snc-layer-row.is-kid").count() == 2,
          pg.locator("#sncLayersBody .snc-layer-row.is-kid").count())

    # ================= G. 无 JS 报错 =================
    print("\n== G 控制台 ==")
    real = [e for e in errs if "favicon" not in e.lower()]
    check("全程无 JS 报错", not real, real[:3])

    br.close()

print("\n" + "=" * 46)
print("%d / %d 通过" % (PASS, PASS + FAIL))
if FAILS:
    for n, e in FAILS:
        print("  FAIL", n, "->", e)
sys.exit(0 if FAIL == 0 else 1)
