# -*- coding: utf-8 -*-
"""v2.6 回归 · AI 局部重绘工作台（参考竞品界面）+ 导出入口精简。

全程网络存根，不消耗出图额度。验收：
  * 导出菜单只剩 3 项 PNG，PDF / 设计汇报页 HTML 的入口与对话框彻底移除；
  * 工作台分区、默认选中态、选区绘制/撤销/重做/反选/清空/识别/更换图片/缩放；
  * 笔刷滑杆（v2.8 起替代「笔刷 ±」按钮）；
  * 提交确实走 /images/edits（2 张参考图），比例 / 分辨率 / 重绘模式生效，
    结果派生新卡、原图保留、工作台自动关闭；
  * 快速框选入口已撤（v2.8）。
"""
import base64
import json
import os
import struct
import zlib
from playwright.sync_api import sync_playwright

BASE = os.environ.get("SNC_BASE", "http://127.0.0.1:8321/canvas.html")
TMP = r"E:\canvas-probe2\tmp\v26"
SHOTS = r"E:\canvas-probe2\shots-v26"
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


upload_png = os.path.join(TMP, "upload.png")
with open(upload_png, "wb") as fh:
    fh.write(png_bytes(640, 480))

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

    # ---------- A. 导出入口精简 ----------
    page.click("#sncExportOpen")
    page.wait_for_timeout(150)
    items = page.locator("#sncExportMenu button[data-exp]").all_inner_texts()
    keys = page.evaluate("""() => Array.from(document.querySelectorAll('#sncExportMenu button[data-exp]'))
                                  .map(b => b.dataset.exp)""")
    # v3.7.7：导出当前图新增「拆分图层 ZIP」，与「原图 PNG」二选一
    check("导出菜单 4 项（含拆分图层）", len(items) == 4, items)
    check("原图 / 拆分图层两项都在", keys == ["board", "sel", "node", "layers"], keys)
    check("PDF 入口已移除", page.locator('#sncExportMenu button[data-exp="pdf"]').count() == 0)
    check("汇报页入口已移除", page.locator('#sncExportMenu button[data-exp="report"]').count() == 0)
    check("汇报页对话框已移除", page.locator("#sncReportDlg").count() == 0)
    check("页面不含导出 PDF 代码", page.evaluate("() => !/exportPDF|buildPDF/.test(document.documentElement.outerHTML)"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)

    # ---------- B. 工具条与工作台结构 ----------
    acts = page.locator("#sncImgBar button span").all_inner_texts()
    check("图片工具条含「局部重绘」", "局部重绘" in acts, acts)
    check("快速框选入口已撤（v2.8）", "快速框选" not in acts and "框选修改" not in acts, acts)

    page.fill("#sncInput", "v26 局部重绘原图")
    page.click("#sncSend")
    page.wait_for_timeout(1200)
    cid = page.evaluate("""() => { const c=[...document.querySelectorAll('.snc-node')];
                                   return c[c.length-1].dataset.id; }""")
    page.click('.snc-node[data-id="%s"]' % cid)
    page.wait_for_timeout(250)
    page.click('#sncImgBar button[data-act="inpaint"]')
    page.wait_for_timeout(450)
    check("工作台已打开", page.evaluate("() => !document.getElementById('sncInp').hidden"))
    check("遮罩已打开", page.evaluate("() => !document.getElementById('sncInpScrim').hidden"))
    secs = page.locator("#sncInp .snc-inp-sec > h4").all_text_contents()
    check("六个参数分组", secs == ["生成分辨率", "重绘模式", "生图比例", "建立选区", "编辑选区", "生成描述"], secs)
    groups = page.evaluate("""() => {
        const o = {};
        document.querySelectorAll('#sncInp [data-group]').forEach(g => {
          o[g.dataset.group] = g.querySelectorAll('button[data-v]').length;
        });
        return o;
    }""")
    # v2.9：分辨率改 原图/2K/4K，模式精简到 2 项（描述重绘 / 选区重绘）
    # v3.7.7：识别工具已撤掉 → 工具 4 个（矩形 / 套索 / 涂抹 / 减选）
    check("分辨率 3 / 模式 2 / 比例 8 / 工具 4",
          groups.get("res") == 3 and groups.get("mode") == 2 and
          groups.get("ratio") == 8 and groups.get("tool") == 4, groups)
    # v3.5：撤掉「复位视图」，只留 反选 / 清空选区
    check("编辑选区 2 项", page.locator('#sncInp button[data-edit]').count() == 2)
    check("编辑选区只剩反选与清空",
          page.evaluate("""() => [...document.querySelectorAll('#sncInp button[data-edit]')]
              .map(b => b.textContent.trim())""") == ["反选", "清空选区"])
    defs = page.evaluate("""() => {
        const g = k => { const b=document.querySelector('#sncInp [data-group="'+k+'"] button.is-on'); return b && b.dataset.v; };
        return {res:g('res'), mode:g('mode'), ratio:g('ratio'), tool:g('tool')};
    }""")
    check("默认 原图 / 选区重绘 / 自动 / 套索",
          defs == {"res": "0", "mode": "select", "ratio": "auto", "tool": "lasso"}, defs)
    check("开始生成按钮存在", page.locator("#sncInpGo").count() == 1)
    check("生成描述占位文案", "描述一下希望选区区域内变成什么" in
          page.get_attribute("#sncInpPrompt", "placeholder"))
    page.screenshot(path=os.path.join(SHOTS, "v26-局部重绘工作台.png"))

    # ---------- C. 选区工具 ----------
    def drag(x0, y0, x1, y1):
        box = page.locator("#sncInpMask").bounding_box()
        page.mouse.move(box["x"] + box["width"] * x0, box["y"] + box["height"] * y0)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] * x1, box["y"] + box["height"] * y1, steps=8)
        page.mouse.up()
        page.wait_for_timeout(180)

    def rects():
        return page.evaluate("() => window.SNC_V26_INPAINT.rects.length")

    page.click('#sncInp [data-group="tool"] button[data-v="rect"]')
    drag(0.2, 0.2, 0.6, 0.6)
    check("矩形工具画出 1 块选区", rects() == 1, rects())
    check("提示同步选区数量", "选区 1 块" in page.inner_text("#sncInpHint"))
    # v2.9：撤销 / 重做按钮已撤，改走 Ctrl+Z / Ctrl+Shift+Z
    page.keyboard.press("Control+z")
    page.wait_for_timeout(150)
    check("撤销后 0 块", rects() == 0)
    page.keyboard.press("Control+Shift+z")
    page.wait_for_timeout(150)
    check("重做恢复 1 块", rects() == 1)
    page.click('#sncInp [data-group="tool"] button[data-v="lasso"]')
    drag(0.05, 0.1, 0.3, 0.35)
    check("套索追加第 2 块", rects() == 2, rects())
    page.click('#sncInp [data-group="tool"] button[data-v="brush"]')
    drag(0.65, 0.65, 0.78, 0.78)
    check("涂抹追加第 3 块", rects() == 3, rects())
    page.click('#sncInp button[data-edit="invert"]')
    check("反选生成补集", 0 < rects() <= 4, rects())
    page.click('#sncInp button[data-edit="clear"]')
    check("清空选区", rects() == 0)
    # v3.7.7：一次性「识别」按钮已按反馈取消，选区改由官方 <bbox> 坐标标记承接
    check("识别按钮已移除",
          page.locator('#sncInp [data-group="tool"] button[data-v="detect"]').count() == 0,
          page.locator('#sncInp [data-group="tool"] button').count())
    check("坐标标记栏存在", page.locator("#sncInpMarks").count() == 1)
    check("清空后坐标标记为空",
          "未建立选区" in page.evaluate("() => document.getElementById('sncInpMarks').textContent"))

    # ---------- D. 底部工具条 ----------
    z0 = page.evaluate("() => window.SNC_V26_INPAINT.zoom")
    page.click('#sncInpTools button[data-tool="zoomin"]')
    z1 = page.evaluate("() => window.SNC_V26_INPAINT.zoom")
    check("放大按钮生效", z1 > z0, (z0, z1))
    page.click('#sncInpTools button[data-tool="zoomout"]')
    check("缩小按钮生效", page.evaluate("() => window.SNC_V26_INPAINT.zoom") < z1)
    page.click('#sncInpTools button[data-tool="hand"]')
    check("抓手模式", page.evaluate("() => window.SNC_V26_INPAINT.nav") == "pan")
    page.click('#sncInpTools button[data-tool="pointer"]')
    check("指针模式", page.evaluate("() => window.SNC_V26_INPAINT.nav") == "draw")
    b0 = page.evaluate("() => window.SNC_V26_INPAINT.brush")
    page.evaluate("""() => { const r = document.getElementById('sncInpBrush');
        r.value = '56'; r.dispatchEvent(new Event('input', {bubbles: true})); }""")
    check("笔刷滑杆可调大小", page.evaluate("() => window.SNC_V26_INPAINT.brush") == 56,
          page.evaluate("() => window.SNC_V26_INPAINT.brush"))
    check("滑杆数值同步显示", "56px" in page.inner_text("#sncInpBrushVal"),
          page.inner_text("#sncInpBrushVal"))
    check("笔刷大小默认 24px", b0 == 24, b0)
    # v2.9：底部的「上传 / 更换图片」已撤，file 输入改为挂参考图
    page.set_input_files("#sncInpFile", upload_png)
    page.wait_for_timeout(450)
    check("参考图挂了上去", page.evaluate("() => window.SNC_V26_INPAINT.refs.length") >= 1,
          page.evaluate("() => window.SNC_V26_INPAINT.refs.length"))

    # ---------- E. 提交链路 ----------
    page.click('#sncInp [data-group="tool"] button[data-v="rect"]')
    drag(0.2, 0.2, 0.58, 0.58)
    check("提交前选区就绪", rects() >= 1, rects())
    page.fill("#sncInpPrompt", "把这块地面换成浅色石材")
    page.click('#sncInp [data-group="res"] button[data-v="2048"]')
    page.click('#sncInp [data-group="ratio"] button[data-v="16:9"]')
    page.click('#sncInp [data-group="mode"] button[data-v="select"]')
    before = page.locator(".snc-node").count()
    n_body = len(bodies)
    page.click("#sncInpGo")
    page.wait_for_timeout(2000)
    check("工作台提交后关闭", page.evaluate("() => document.getElementById('sncInp').hidden"))
    check("派生一张新卡", page.locator(".snc-node").count() == before + 1,
          (before, page.locator(".snc-node").count()))
    check("原图节点仍在", page.locator('.snc-node[data-id="%s"]' % cid).count() == 1)
    new_bodies = bodies[n_body:]
    check("确实发起局部重绘请求", len(new_bodies) >= 1, len(new_bodies))
    if new_bodies:
        b = new_bodies[0]
        check("走 /images/edits（裁片 + 整图 + 挂的参考图）", len(b.get("images") or []) == 3,
              len(b.get("images") or []))
        check("参考图均为 data URL", all(str(x).startswith("data:image/") for x in b["images"]))
        check("分辨率 2k 生效", b.get("res") == 2048, b.get("res"))
        check("比例 16:9 生效", b.get("ratio") == "16:9", b.get("ratio"))
        check("用户描述进入提示词", "把这块地面换成浅色石材" in b.get("prompt", ""))
        check("重绘模式条款进入提示词", "只重绘选区内的目标" in b.get("prompt", ""),
              b.get("prompt", "")[:200])
        check("未开启提示词扩写", b.get("promptExtend") is False, b.get("promptExtend"))
    check("卡片标签标记局部重绘", page.evaluate("""() => {
        const t = Array.from(document.querySelectorAll('.snc-node')).map(n => n.textContent || '');
        return t.some(x => x.indexOf('局部重绘') >= 0);
    }"""))

    # ---------- F. 三种关闭方式 ----------
    page.click('.snc-node[data-id="%s"]' % cid)
    page.wait_for_timeout(200)
    page.click('#sncImgBar button[data-act="inpaint"]')
    page.wait_for_timeout(250)
    page.click("#sncInpX")
    check("× 关闭工作台", page.evaluate("() => document.getElementById('sncInp').hidden"))
    page.click('.snc-node[data-id="%s"]' % cid)
    page.wait_for_timeout(200)
    page.click('#sncImgBar button[data-act="inpaint"]')
    page.wait_for_timeout(250)
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    check("Esc 关闭工作台", page.evaluate("() => document.getElementById('sncInp').hidden"))
    page.click('.snc-node[data-id="%s"]' % cid)
    page.wait_for_timeout(200)
    page.click('#sncImgBar button[data-act="inpaint"]')
    page.wait_for_timeout(250)
    page.mouse.click(4, 4)          # 工作台四周留的 12px 遮罩区
    page.wait_for_timeout(150)
    check("点遮罩关闭工作台", page.evaluate("() => document.getElementById('sncInp').hidden"))

    # ---------- G. 快速框选入口已撤（v2.8） ----------
    page.click('.snc-node[data-id="%s"]' % cid)
    page.wait_for_timeout(250)
    check("浮动条不再有快速框选按钮",
          page.locator('#sncImgBar button[data-act="mask"]').count() == 0)
    check("工作台里也不再有「画布框选」入口",
          page.locator('#sncInpTools button[data-tool="classic"]').count() == 0)

    check("全程无 JS 报错", not errs, errs[:3])
    ctx.close()
    br.close()

passed = sum(1 for _, ok in results if ok)
print("\n%d / %d 通过" % (passed, len(results)))
if passed != len(results):
    print("失败项：" + ", ".join(n for n, ok in results if not ok))
    raise SystemExit(1)
