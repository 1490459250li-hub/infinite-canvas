# -*- coding: utf-8 -*-
"""第四批（v3.7.4）改动自检：快捷键表 / 队列面板 / 导出尺寸上限。

跑法：
    python tests/probe_batch5.py http://127.0.0.1:8321

三个断言原则：
1. 快捷键表里的每一组都数出来，不靠"看起来有"；
2. 队列用假任务灌，验证的是渲染与取消链路，不是网络；
3. 导出必须给出**旧代码会爆、新代码不爆**的那组尺寸，否则测不出修复。
"""
import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8321"
PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + "   -> " + repr(detail))


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge")
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script(
            "try{localStorage.setItem('snc.eula.v1','1');"
            "localStorage.setItem('snc.theme.v2','dark')}catch(e){}"
        )
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(BASE + "/canvas.html")
        pg.wait_for_selector(".snc-node")
        pg.wait_for_timeout(900)

        # ============ 1. 快捷键表 ============
        print("== 快捷键表 ==")
        st = pg.evaluate("""() => {
          const el = document.getElementById('sncKeys');
          return {
            exists: !!el,
            hidden: el ? el.hidden : null,
            groups: document.querySelectorAll('#sncKeys .snc-keys-g').length,
            kbds: document.querySelectorAll('#sncKeys kbd').length,
            rows: document.querySelectorAll('#sncKeys .snc-keys-g dl > div').length,
            btn: !!document.getElementById('sncKeysBtn')
          };
        }""")
        check("快捷键表节点存在且初始隐藏", st["exists"] and st["hidden"] is True, st)
        check("四个分组", st["groups"] == 4, st["groups"])
        check("条目数 >= 18", st["rows"] >= 18, st["rows"])
        check("kbd 标签齐全", st["kbds"] >= 18, st["kbds"])
        check("有可点击的入口按钮", st["btn"] is True, st["btn"])

        # 按 ? 打开
        pg.keyboard.press("?")
        pg.wait_for_timeout(220)
        opened = pg.evaluate("() => !document.getElementById('sncKeys').hidden")
        check("按 ? 打开", opened is True, opened)

        # Esc 关
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(180)
        check("Esc 关闭", pg.evaluate("() => document.getElementById('sncKeys').hidden") is True)

        # 入口按钮
        pg.click("#sncKeysBtn")
        pg.wait_for_timeout(200)
        check("入口按钮能打开", pg.evaluate("() => !document.getElementById('sncKeys').hidden") is True)

        # 表内按下不关（否则拖选文字会误关）
        pg.evaluate("""() => {
          const t = document.querySelector('#sncKeys .snc-keys h2');
          const r = t.getBoundingClientRect();
          t.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true, clientX:r.x+4, clientY:r.y+4}));
        }""")
        pg.wait_for_timeout(150)
        check("表内按下不误关", pg.evaluate("() => !document.getElementById('sncKeys').hidden") is True)

        # 点遮罩关闭
        pg.mouse.click(8, 8)
        pg.wait_for_timeout(200)
        check("点遮罩关闭", pg.evaluate("() => document.getElementById('sncKeys').hidden") is True)

        # 输入框里按 ? 不该弹（在输入框打字时快捷键要闭嘴）
        pg.click("#sncInput")
        pg.keyboard.type("?")
        pg.wait_for_timeout(200)
        check("输入框里按 ? 不弹表",
              pg.evaluate("() => document.getElementById('sncKeys').hidden") is True)
        pg.fill("#sncInput", "")

        # 单键快捷只在"焦点不在输入框"时生效 —— 这是设计如此（在输入框里就该打字）。
        # 测试要先把焦点从刚才的输入框移开，否则按 H 只会往框里打一个 h。
        pg.evaluate("() => { if(document.activeElement && document.activeElement.blur) document.activeElement.blur(); }")
        pg.wait_for_timeout(120)

        # V / H 真的能切
        pg.keyboard.press("h")
        pg.wait_for_timeout(150)
        is_hand = pg.evaluate("() => document.getElementById('snc').classList.contains('tool-hand')")
        check("H 切到抓手", is_hand is True, is_hand)

        pressed = pg.evaluate("""() => [...document.querySelectorAll('.snc-tool[data-tool]')]
          .filter(b => b.getAttribute('aria-pressed') === 'true').map(b => b.dataset.tool)""")
        check("抓手按钮 aria 同步", pressed == ["hand"], pressed)

        pg.keyboard.press("v")
        pg.wait_for_timeout(150)
        is_hand = pg.evaluate("() => document.getElementById('snc').classList.contains('tool-hand')")
        check("V 切回选择", is_hand is False, is_hand)

        # Ctrl+T 不该新建笔记（单键快捷必须排除修饰键）
        n0 = pg.evaluate("() => window.SNC_TEST_API.nodes().length")
        pg.keyboard.press("Control+t")
        pg.wait_for_timeout(250)
        n1 = pg.evaluate("() => window.SNC_TEST_API.nodes().length")
        check("Ctrl+T 不误建笔记", n1 == n0, [n0, n1])

        pg.keyboard.press("t")
        pg.wait_for_timeout(250)
        n2 = pg.evaluate("() => window.SNC_TEST_API.nodes().length")
        check("T 正常新建笔记", n2 == n1 + 1, [n1, n2])

        # ============ 2. 队列面板 ============
        print("== 队列面板 ==")
        seed = pg.evaluate("() => window.SNC_TEST_API.queueProbe(4, 1)")
        check("灌注 4 个假任务", seed == {"running": 1, "wait": 3}, seed)
        pg.wait_for_timeout(200)

        qs = pg.evaluate("() => window.SNC_TEST_API.queueState()")
        check("角标显示 1/2", "1/2" in (qs.get("badge") or ""), qs.get("badge"))
        check("角标显示等待 3", "等待 3" in (qs.get("badge") or ""), qs.get("badge"))
        check("角标可见", qs.get("badge", "") != "", qs)

        pg.click("#sncQueue")
        pg.wait_for_timeout(300)
        qs = pg.evaluate("() => window.SNC_TEST_API.queueState()")
        check("点角标打开面板", qs.get("popOpen") is True, qs)
        check("面板列出 4 行", qs.get("rows") == 4, qs.get("rows"))

        subs = pg.evaluate(
            "() => [...document.querySelectorAll('#sncQueuePop .snc-qsub, #sncQueuePop .snc-qmeta span')]"
            ".map(e => e.textContent)"
        )
        check("运行中显示进度", any("生成中 40%" in s for s in subs), subs)
        check("排队中显示排位", any("排队 · 前面 1 个" in s for s in subs), subs)

        # 进度会变，面板必须跟着动。syncQueueBadge 只在任务进出队列时触发，
        # 靠它刷新的话「40%」会永远停在打开那一刻 —— 这里验 tick 真的在跑
        pg.evaluate("() => window.SNC_TEST_API.queueBump(85)")
        pg.wait_for_timeout(900)
        subs2 = pg.evaluate("() => window.SNC_TEST_API.queueState().subs")
        check("进度会自己刷新（40% → 85%）",
              any("生成中 85%" in s for s in subs2), subs2)
        check("刷新不重建整行（排队行仍在）",
              any("排队" in s for s in subs2), subs2)

        # 取消一个排队中的
        pg.evaluate("""() => {
          const btns = [...document.querySelectorAll('#sncQueuePop .snc-qx')];
          btns[btns.length - 1].click();
        }""")
        pg.wait_for_timeout(300)
        qs2 = pg.evaluate("() => window.SNC_TEST_API.queueState()")
        check("取消后排队数 -1", qs2.get("wait") == 2, qs2)
        check("取消后行数 -1", qs2.get("rows") == 3, qs2.get("rows"))

        # 点面板外关闭
        pg.mouse.click(700, 500)
        pg.wait_for_timeout(250)
        check("点面板外关闭",
              pg.evaluate("() => window.SNC_TEST_API.queueState().popOpen") is False)

        pg.evaluate("() => window.SNC_TEST_API.queueClear()")
        pg.wait_for_timeout(250)
        qs3 = pg.evaluate("() => window.SNC_TEST_API.queueState()")
        check("清空后角标隐藏", qs3.get("badge", "") == "", qs3)

        # ============ 3. 导出尺寸上限 ============
        print("== 导出尺寸上限 ==")
        lim = pg.evaluate("() => window.SNC_TEST_API.exportLimits()")
        check("上限常量已定义", lim.get("side") == 16000 and abs(lim.get("area", 0) - 1.5e8) < 1,
              lim)

        # 3.1 纵向超长：旧代码 scale 被 0.6 顶住，高度 8 万，直接爆
        tall = pg.evaluate("""async () => {
          const cv = await window.SNC_TEST_API.compose([
            {id:'t1', type:'gen', x:0, y:0, w:400, h:40000, dataUrl:''}
          ], {pad:56});
          return {w: cv.width, h: cv.height, scale: cv._scale, clamped: cv._clamped};
        }""")
        check("纵向 4 万高：单边不超限",
              tall["h"] <= 16000 and tall["w"] <= 16000, tall)
        check("纵向 4 万高：被主动降 scale", tall["clamped"] is True, tall)
        # 旧实现会算成 scale=2 -> h=80112，这里确认新值远小于那个数
        check("纵向 4 万高：确实缩了（scale < 1）", tall["scale"] < 1, tall["scale"])

        # 3.2 横向超宽：旧代码 scale=0.6 -> 宽 1.8 万
        wide = pg.evaluate("""async () => {
          const cv = await window.SNC_TEST_API.compose([
            {id:'w1', type:'gen', x:0, y:0, w:300, h:300, dataUrl:''},
            {id:'w2', type:'gen', x:30000, y:0, w:300, h:300, dataUrl:''}
          ], {pad:56});
          return {w: cv.width, h: cv.height, scale: cv._scale, clamped: cv._clamped};
        }""")
        check("横向 3 万宽：单边不超限", wide["w"] <= 16000, wide)
        # 老代码是 0.6 -> 18292；新代码应该尽量保住 0.6 的观感，只在超限时收到上限附近
        check("横向 3 万宽：贴在安全上限内（不是被压成小图）",
              wide["w"] > 15000 and wide["w"] <= 16000, wide["w"])

        # 3.3 正常尺寸不被误降
        normal = pg.evaluate("""async () => {
          const cv = await window.SNC_TEST_API.compose([
            {id:'n1', type:'gen', x:0, y:0, w:400, h:300, dataUrl:''},
            {id:'n2', type:'gen', x:520, y:0, w:400, h:300, dataUrl:''}
          ], {pad:56});
          return {w: cv.width, h: cv.height, scale: cv._scale, clamped: cv._clamped};
        }""")
        check("正常尺寸按 2 倍超采样", abs(normal["scale"] - 2) < 1e-6, normal)
        check("正常尺寸标记未降级", normal["clamped"] is False, normal)
        # 内容宽 920（0..920）×2 倍 + 两侧 56px pad = 1952
        check("正常尺寸输出 920×2+112", normal["w"] == 1952, normal["w"])

        # 3.4 面积极限：正方形 2 万见方 —— 单边不超但面积必然超
        huge = pg.evaluate("""async () => {
          const cv = await window.SNC_TEST_API.compose([
            {id:'h1', type:'gen', x:0, y:0, w:20000, h:20000, dataUrl:''}
          ], {pad:56});
          return {w: cv.width, h: cv.height, area: cv.width * cv.height, scale: cv._scale};
        }""")
        check("2 万见方：面积进安全区", huge["area"] <= 1.5e8 * 1.05, huge["area"])
        check("2 万见方：单边不超限",
              huge["w"] <= 16000 and huge["h"] <= 16000, [huge["w"], huge["h"]])
        # 回归保护：这张图在旧代码里是 12112，改成"按 2600 目标"后会掉到 2712 —— 那是倒退
        check("2 万见方：没有退化成 2600 小图", huge["w"] > 10000, huge["w"])

        print()
        print("PASS=%d FAIL=%d" % (PASS, FAIL))
        if errs:
            print("页面错误 %d 条：" % len(errs))
            for e in errs[:5]:
                print("  " + e)
        b.close()
        return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
