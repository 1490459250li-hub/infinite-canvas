# -*- coding: utf-8 -*-
"""v1.5 回归：布局自适应 + 多画布 + SenseNova 能力调用（编辑 / 局部重绘）+ 导出菜单。"""
import os
import sys
from playwright.sync_api import sync_playwright

URL = os.environ.get("SNC_BASE", "http://127.0.0.1:8321/canvas.html")
SHOT = r"C:\Users\Flish\WorkBuddy\2026-11-07-19-49-41\_inspect\cap"
res = []
def check(name, cond, extra=""):
    res.append((name, bool(cond), extra))
    print(("PASS " if cond else "FAIL ") + name + ("  " + str(extra) if extra else ""))

def boot(b, w=1440, h=900):
    ctx = b.new_context(viewport={"width": w, "height": h})
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL)
    pg.wait_for_selector('.snc-node[data-id^="g-"]')
    pg.wait_for_timeout(1300)
    return ctx, pg, errs

def wait_toast(pg, words, rounds=70):
    for _ in range(rounds):
        pg.wait_for_timeout(1500)
        t = pg.inner_text("#sncToast")
        if any(w in t for w in words):
            return t
    return pg.inner_text("#sncToast")

with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge")

    # ---------- A. 布局自适应 ----------
    for w, h in [(1440, 900), (1024, 680), (900, 640)]:
        ctx, pg, errs = boot(b, w, h)
        m = pg.evaluate("""() => {
            const r = document.getElementById('snc').getBoundingClientRect();
            return {w: r.width, h: r.height, iw: innerWidth, ih: innerHeight,
                    sx: document.documentElement.scrollWidth - innerWidth,
                    sy: document.documentElement.scrollHeight - innerHeight};
        }""")
        check("%dx%d 铺满视口且无滚动" % (w, h),
              abs(m["w"] - m["iw"]) < 2 and abs(m["h"] - m["ih"]) < 2
              and m["sx"] <= 1 and m["sy"] <= 1, m)
        if w == 900:
            ok_ = pg.evaluate("""() => {
                const bar = document.querySelector('.snc-prompt').getBoundingClientRect();
                const zoom = document.querySelector('.snc-zoomer').getBoundingClientRect();
                return bar.right < zoom.left || zoom.right < bar.left ||
                       bar.bottom < zoom.top || zoom.bottom < bar.top;
            }""")
            check("窄窗下输入框与缩放控件不重叠", ok_)
        check("%dx%d 无 JS 报错" % (w, h), not errs, errs[:2])
        ctx.close()

    # ---------- B. 多画布 ----------
    ctx, pg, errs = boot(b)
    before = pg.locator(".snc-doc-item").count()
    pg.click(".snc-doc-new")
    pg.wait_for_timeout(700)
    after = pg.locator(".snc-doc-item").count()
    check("新建画布后列表 +1", after == before + 1, "%d -> %d" % (before, after))
    check("新画布是空白态", pg.locator(".snc-node").count() == 0,
          "nodes=%d" % pg.locator(".snc-node").count())
    item = pg.locator(".snc-doc-item.is-on").first
    item.hover()
    pg.wait_for_timeout(300)
    pg.locator(".snc-doc-item.is-on .snc-doc-act.del").first.click()
    pg.wait_for_timeout(400)
    pg.click("#sncConfirmYes")
    pg.wait_for_timeout(900)
    check("删除画布后列表回到原数量",
          pg.locator(".snc-doc-item").count() == before,
          pg.locator(".snc-doc-item").count())
    pg.locator(".snc-doc-item", has_text="情绪板").first.click()
    pg.wait_for_timeout(900)
    check("切回原画布节点还在", pg.locator('.snc-node[data-id^="g-"]').count() > 0,
          pg.locator(".snc-node").count())
    check("多画布流程无 JS 报错", not errs, errs[:2])
    ctx.close()

    # ---------- C. 编辑：参考图必须进请求 ----------
    ctx, pg, errs = boot(b)
    node = pg.locator('.snc-node[data-id^="g-"]').first
    nid = node.get_attribute("data-id")
    node.click()
    pg.wait_for_timeout(300)
    acts = pg.locator("#sncImgBar button span").all_inner_texts()
    # 动作数随批次增加：v3.7 加「记录」、v3.7.4 第七批加「两图对比」
    check("浮动条 10 个动作", len(acts) == 10, acts)
    check("原有动作全在（顺序即优先级：对比预览后面紧跟两图对比）", all(a in acts for a in
          ["重新生成", "对比预览", "两图对比", "编辑", "技能", "局部重绘", "增强", "放大", "记录", "导出"]), acts)
    check("两图对比排在对比预览之后（同一类操作挨着）",
          acts.index("两图对比") == acts.index("对比预览") + 1, acts)
    pg.click('#sncImgBar button[data-act="edit"]')
    pg.wait_for_timeout(500)
    check("编辑自动带上原图作主编辑图", pg.locator("#sncCompose .snc-att").count() == 1)
    check("编辑默认跟随原图", pg.input_value("#sncRatio") == "auto", pg.input_value("#sncRatio"))
    opts = pg.locator("#sncModel option").all_inner_texts()
    # v3.0 起是多供应商，下拉里是「所有已配置供应商」的模型，不再只有 SenseNova 两家
    check("模型下拉列的是真实模型（标签都带能力徽标）",
          len(opts) >= 2 and all("·" in o for o in opts), opts)

    pg.fill("#sncComposeInput", "把地面换成浅灰木纹地板，其他都不要变")
    pg.click("#sncComposeSend")
    t = wait_toast(pg, ["已生成", "失败"])
    check("参考图编辑成功", "已生成" in t, t)
    badge = pg.locator('.snc-node[data-id="%s"] .snc-sizebadge' % nid).inner_text()
    check("尺寸徽标是真实像素", "×" in badge, badge)
    pg.screenshot(path=SHOT + "_A-edit.png")
    ctx.close()

    # ---------- D. 局部重绘 + 版本 + 导出 ----------
    ctx, pg, errs = boot(b)
    node = pg.locator('.snc-node[data-id^="g-"]').first
    nid = node.get_attribute("data-id")
    nodes_before = pg.locator('.snc-node').count()
    node.click()
    pg.wait_for_timeout(300)
    # v2.8：快速框选入口撤掉了，局部重绘统一走工作台
    pg.click('#sncImgBar button[data-act="inpaint"]')
    pg.wait_for_timeout(600)
    box = pg.locator("#sncInpMask").bounding_box()
    pg.mouse.move(box["x"] + box["width"] * 0.2, box["y"] + box["height"] * 0.6)
    pg.mouse.down()
    pg.mouse.move(box["x"] + box["width"] * 0.7, box["y"] + box["height"] * 0.88, steps=10)
    pg.mouse.up()
    pg.wait_for_timeout(300)
    check("工作台记录 1 块选区", "选区 1 块" in pg.inner_text("#sncInpHint"),
          pg.inner_text("#sncInpHint").replace("\n", " "))
    pg.fill("#sncInpPrompt", "这块换成米色水磨石，接缝自然")
    pg.click("#sncInpGo")
    t = wait_toast(pg, ["局部重绘完成", "失败"])
    check("局部重绘完成", "局部重绘完成" in t, t)
    pg.screenshot(path=SHOT + "_B-region.png")

    pg.locator('.snc-node[data-id="%s"]' % nid).click()
    pg.wait_for_timeout(300)
    # v1.8 起编辑 / 框选 / 增强 / 放大一律「派生成新卡，原图与版本树不动」，
    # 所以不再断言原卡版本条涨到 2 版，改为验证派生新卡 + 原卡完好。
    nodes_after = pg.locator('.snc-node').count()
    check("局部重绘派生新卡且原图保留",
          nodes_after > nodes_before and
          pg.locator('.snc-node[data-id="%s"]' % nid).count() == 1,
          (nodes_before, nodes_after))
    pg.click("#sncExportOpen")
    pg.wait_for_timeout(400)
    items = pg.locator("#sncExportMenu button").all_inner_texts()
    # v3.7.7：新增「拆分图层 ZIP」，与「原图 PNG」二选一
    check("导出菜单 4 项（v2.6 撤回 PDF，v3.7.7 新增拆分图层）", len(items) == 4, items)
    pg.keyboard.press("Escape")
    check("能力流程无 JS 报错", not errs, errs[:3])
    ctx.close()
    b.close()

bad = [n for n, c, _ in res if not c]
print("\n%d/%d 通过" % (len(res) - len(bad), len(res)))
if bad:
    print("失败:", bad)
sys.exit(1 if bad else 0)
