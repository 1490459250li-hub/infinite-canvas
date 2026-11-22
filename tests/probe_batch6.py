# -*- coding: utf-8 -*-
"""第六批（v3.7.4）改动自检：撤销 50 步 / 画布规模预警 / 多画布搜内容。

跑法：
    python tests/probe_batch6.py http://127.0.0.1:8321

三个断言原则：
1. 撤销栈量的是**真实字节**（SNC_UNDO_STATS），不是"代码里写着 50"；
2. 规模角标要在 39 / 40 / 80 三个点上分别看显隐与配色，差一张卡就该不一样；
3. 搜内容必须真的跨画布命中并跳过去，不是"列表里多了一行字"。
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
            # 每次导航都会跑一遍，但静音要跨刷新验证 —— 用 sessionStorage 打标只清一次
            "try{if(!sessionStorage.getItem('snc.probe6.init')){"
            "localStorage.removeItem('snc.scalehint.v1');"
            "sessionStorage.setItem('snc.probe6.init','1');}"
            "localStorage.setItem('snc.eula.v1','1');"
            "localStorage.setItem('snc.theme.v2','dark')}catch(e){}"
        )
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(BASE + "/canvas.html")
        pg.wait_for_selector(".snc-node")
        pg.wait_for_timeout(800)

        made = []          # 本探针造的画布名前缀，跑完要删干净

        # ---------------------------------------------------------------
        # 1. 撤销 50 步
        # ---------------------------------------------------------------
        print("== 撤销上限 ==")
        # 6 张 300 KB 的图 + 连按 60 次 Ctrl+Z 的场景：层数上限、图共享、快照体积
        undo = pg.evaluate("""() => {
          const api = window.SNC_TEST_API;
          const N = api.nodes(); N.length = 0;
          function big(seed){
            const c = document.createElement('canvas'); c.width = 900; c.height = 700;
            const g = c.getContext('2d');
            for(let i = 0; i < 900; i += 4){
              g.fillStyle = 'rgb(' + ((seed * 37 + i) % 255) + ',' +
                             ((seed * 91 + i * 3) % 255) + ',' +
                             ((seed * 13 + i * 7) % 255) + ')';
              g.fillRect(i, 0, 2, 700);
            }
            return c.toDataURL('image/jpeg', .92);
          }
          for(let i = 0; i < 6; i++){
            const u = big(i + 1);
            N.push({ id: 'undo-' + i, type: 'gen', status: 'done', label: '生成',
                     x: 80 + i * 220, y: 120, w: 200, h: 160, dataUrl: u,
                     prompt: '第 ' + i + ' 张', vIndex: 0,
                     versions: [{ dataUrl: u, model: 'm', latencyMs: 1, usage: {} }] });
          }
          api.render();
          const one = N[0].dataUrl.length;
          for(let i = 0; i < 60; i++) api.snapshot();
          const st = api.stats();
          return { layers: st.layers, arts: st.arts, snapBytes: st.snapBytes,
                   artBytes: st.artBytes, oneImg: one, nodes: N.length };
        }""")
        try:
            undo["max"] = pg.evaluate(
                "() => 0")  # 占位，保持结构简单
        except Exception:
            pass
        check("撤销层数封顶 50", undo["layers"] == 50, undo["layers"])
        check("快照里只留图引用、不复制图本体",
              undo["artBytes"] <= undo["oneImg"] * undo["nodes"] * 1.05,
              [undo["artBytes"], undo["oneImg"], undo["nodes"]])
        check("50 层的快照文本总量远小于图本体",
              undo["snapBytes"] < undo["oneImg"] * 2,
              [undo["snapBytes"], undo["oneImg"]])
        per_layer = undo["snapBytes"] / 50.0
        print("       每层快照 %.0f B · 50 层合计 %.1f KB · 6 张图共享 %.1f KB"
              % (per_layer, undo["snapBytes"] / 1024.0, undo["artBytes"] / 1024.0))
        print("       （按此折算：20 层约 %.1f KB，比 50 层省 %.1f KB）"
              % (per_layer * 20 / 1024.0, (undo["snapBytes"] - per_layer * 20) / 1024.0))

        # 撤销真的能回退（不是只把栈撑大）
        back = pg.evaluate("""() => {
          const api = window.SNC_TEST_API;
          const N = api.nodes();
          N.push({ id: 'extra-1', type: 'note', title: '临时', text: 'x',
                   x: 900, y: 500, w: 160, h: 100 });
          api.snapshot();          // 快照里已经有 extra-1
          N.length = 6;            // 模拟删掉它
          api.render();
          api.undo();              // 回到有 extra-1 的那层
          return api.nodes().length;
        }""")
        check("撤销真的把卡恢复回来", back == 7, back)

        # ---------------------------------------------------------------
        # 2. 画布规模预警
        # ---------------------------------------------------------------
        print("== 规模预警 ==")

        def set_count(n):
            pg.evaluate(
                """(n) => {
                  const api = window.SNC_TEST_API;
                  const N = api.nodes(); N.length = 0;
                  for(let i = 0; i < n; i++){
                    N.push({ id: 's-' + i, type: 'note', title: 'T' + i, text: 'x',
                             x: (i % 10) * 220, y: Math.floor(i / 10) * 160,
                             w: 180, h: 110 });
                  }
                  api.render();
                }""", n)
            pg.wait_for_timeout(120)
            return pg.evaluate("() => window.SNC_TEST_API.scale()")

        s39 = set_count(39)
        check("39 张卡不出现角标", s39["hidden"] is True, s39)
        s40 = set_count(40)
        check("40 张卡出现角标", s40["hidden"] is False, s40)
        check("40 张卡只报数、不报警", "40 张卡" in s40["text"] and not s40["warn"], s40)
        s80 = set_count(80)
        check("80 张卡转警告色", s80["warn"] is True, s80)
        check("80 张卡文案含「建议分板」", "建议分板" in s80["text"], s80["text"])

        # 没选区时按钮应该是禁用且提示改选
        pg.click("#sncScale")
        pg.wait_for_timeout(180)
        pop = pg.evaluate("() => window.SNC_TEST_API.scale()")
        check("点角标能开面板", pop["popOpen"] is True, pop)
        check("无选区时「移到新画布」禁用", pop["disabled"] is True and "先选" in pop["btn"], pop["btn"])

        # 选 5 张再开。多选是 Shift+点（画布里 shiftKey 才是加选，Ctrl 不认）
        ids = pg.evaluate("() => window.SNC_TEST_API.nodes().slice(0, 5).map(n => n.id)")
        pg.click('.snc-node[data-id="%s"] .snc-node-body' % ids[0])
        for nid in ids[1:]:
            pg.click('.snc-node[data-id="%s"] .snc-node-body' % nid, modifiers=["Shift"])
        pg.wait_for_timeout(150)
        pg.click("#sncScale")          # 点画布会把面板收掉，重新打开
        pg.wait_for_timeout(200)
        sel = pg.evaluate("() => window.SNC_TEST_API.scale()")
        check("选中 5 张后按钮给出具体张数",
              sel["sel"] == 5 and "5 张" in sel["btn"], sel)

        before_names = pg.evaluate(
            "() => [...document.querySelectorAll('#sncDocList .snc-doc-name')].map(e => e.textContent)")
        pg.evaluate("() => document.querySelector(\"#sncScalePop [data-sp='move']\").click()")
        pg.wait_for_timeout(700)
        after = pg.evaluate("""() => ({
          boards: document.querySelectorAll('#sncDocList .snc-doc-item').length,
          n: window.SNC_TEST_API.nodes().length,
          sel: window.SNC_TEST_API.scale().sel,
          names: [...document.querySelectorAll('#sncDocList .snc-doc-name')].map(e => e.textContent),
          title: document.getElementById('sncTitle').textContent
        })""")
        new_names = [x for x in after["names"] if x not in before_names]
        check("拆板后多出一张画布", after["boards"] == len(before_names) + 1,
              [len(before_names), after["boards"]])
        check("新画布里就是那 5 张", after["n"] == 5, after["n"])
        check("新画布名字是「分板 N」",
              bool(new_names) and new_names[0].startswith("分板"), [new_names, after["names"]])
        check("拆完切到新画布", "分板" in (after["title"] or ""), after["title"])
        made.extend(new_names)
        # 原画布应该只剩 75 张：切回去数一遍，别只看当前画布
        src_name = [x for x in before_names if x][0]
        pg.locator("#sncDocList .snc-doc-item", has_text=src_name).first.click()
        pg.wait_for_timeout(450)
        left_n = pg.evaluate("() => window.SNC_TEST_API.nodes().length")
        check("原画布剩 75 张", left_n == 75, left_n)
        # 切回分板画布继续后面的静音测试
        pg.locator("#sncDocList .snc-doc-item", has_text=new_names[0]).first.click()
        pg.wait_for_timeout(400)

        # 「不再提醒」要持久化
        set_count(80)
        pg.click("#sncScale")
        pg.wait_for_timeout(150)
        pg.evaluate("() => document.querySelector(\"#sncScalePop [data-sp='mute']\").click()")
        pg.wait_for_timeout(200)
        muted = pg.evaluate("() => window.SNC_TEST_API.scale()")
        check("点「不再提醒」后角标收起", muted["hidden"] is True, muted)
        stored = pg.evaluate("() => localStorage.getItem('snc.scalehint.v1') || ''")
        check("静音记在本机（同一张画布不再出现）", ":" in stored and len(stored) > 5, stored)
        pg.reload()
        pg.wait_for_selector(".snc-node")
        pg.wait_for_timeout(700)
        # 刷新后会打开上次的画布，节点应还是 80 张且角标仍隐藏
        after_reload = pg.evaluate("() => window.SNC_TEST_API.scale()")
        check("刷新后仍然记得静音（此时卡数确实过线）",
              after_reload["hidden"] is True and after_reload["n"] >= 40, after_reload)

        # ---------------------------------------------------------------
        # 3. 多画布搜内容
        # ---------------------------------------------------------------
        print("== 内容搜索 ==")
        # 造两张干净画布：A 有提示词，B 有笔记正文
        pg.evaluate("""() => {
          const api = window.SNC_TEST_API;
          const N = api.nodes(); N.length = 0;
          N.push({ id: 'cs-a1', type: 'gen', status: 'done', label: '生成',
                   x: 80, y: 80, w: 240, h: 180, prompt: '夜间鸟瞰的社区体育公园，暖色球场灯',
                   vIndex: 0 });
          N.push({ id: 'cs-a2', type: 'gen', status: 'done', label: '生成',
                   x: 360, y: 80, w: 240, h: 180, prompt: '小区中庭的傍晚人流',
                   vIndex: 0 });
          api.render();
        }""")
        pg.wait_for_timeout(150)
        cur_name = pg.evaluate("() => document.getElementById('sncTitle').textContent")
        pg.click("#sncDocNew")
        pg.wait_for_timeout(600)
        pg.evaluate("""() => {
          const api = window.SNC_TEST_API;
          const N = api.nodes(); N.length = 0;
          N.push({ id: 'cs-b1', type: 'note', title: '材质备忘',
                   text: '儿童活动场橡胶地垫要 50mm 厚，EPDM 颗粒，暗红色',
                   x: 100, y: 100, w: 200, h: 130 });
          N.push({ id: 'cs-b2', type: 'note', title: '照明',
                   text: '球场灯 3000K，显色指数 80 以上',
                   x: 340, y: 100, w: 200, h: 130 });
          api.render();
        }""")
        pg.wait_for_timeout(200)
        second_name = pg.evaluate("() => document.getElementById('sncTitle').textContent")
        made.append(second_name)

        def search(q):
            pg.fill("#sncDocSearch", q)
            pg.wait_for_timeout(220)
            return pg.evaluate("""() => ({
              hits: [...document.querySelectorAll('#sncDocList .snc-doc-hit')].map(e => ({
                b: e.querySelector('.snc-hit-b').textContent,
                t: e.querySelector('.snc-hit-t').textContent,
                marks: [...e.querySelectorAll('mark')].map(m => m.textContent)
              })),
              secs: [...document.querySelectorAll('#sncDocList .snc-doc-sec')].map(e => e.textContent),
              items: document.querySelectorAll('#sncDocList .snc-doc-item').length,
              empty: (document.querySelector('#sncDocList .snc-doc-empty') || {}).textContent || ''
            })""")

        # 3.1 只在另一张画布的内容里出现的关键词
        r1 = search("橡胶")
        check("跨画布搜到卡片正文", len(r1["hits"]) == 1, r1["hits"])
        check("命中行标出所属画布", second_name in (r1["hits"][0]["b"] if r1["hits"] else ""), r1["hits"])
        check("关键词被 mark 标出", r1["hits"] and r1["hits"][0]["marks"] == ["橡胶"], r1["hits"])
        check("片段带上下文而不是从头截", "EPDM" in (r1["hits"][0]["t"] if r1["hits"] else ""), r1["hits"])

        # 3.2 点命中跳过去
        pg.click("#sncDocList .snc-doc-hit")
        pg.wait_for_timeout(600)
        jumped = pg.evaluate("""() => ({
          title: document.getElementById('sncTitle').textContent,
          sel: window.SNC_TEST_API.nodes().filter(n => n.id === 'cs-b1').length,
          isSel: document.getElementById('sncWorld').querySelector('.snc-node.is-sel') ?
                 document.querySelector('.snc-node.is-sel').dataset.id : '',
          view: document.getElementById('sncZoomVal').textContent
        })""")
        check("点击命中后跳到那张卡所在画布", second_name in (jumped["title"] or ""), jumped["title"])
        check("目标卡被选中", jumped["isSel"] == "cs-b1", jumped)

        # 3.3 两张画布都含这个词：两条命中、当前画布那条要标「当前」
        r2 = search("球场灯")
        check("两张画布都命中时都列出来", len(r2["hits"]) == 2, r2["hits"])
        cur_hits = [h for h in r2["hits"] if "当前" in h["b"]]
        check("当前画布那条标了「当前」且内容是笔记正文",
              len(cur_hits) == 1 and "照明" in cur_hits[0]["t"], cur_hits)

        # 3.4 画布名命中与内容命中分段
        r3 = search("画布")
        check("关键词同时命中画布名时出现「画布」段",
              any(s.startswith("画布") for s in r3["secs"]), r3["secs"])
        check("命中画布名时列表项仍然可点", r3["items"] >= 1, r3["items"])

        # 3.5 搜不到
        r4 = search("完全不存在的一串字")
        check("搜不到时明说「画布或卡片」",
              "卡片" in r4["empty"] and len(r4["hits"]) == 0, r4)

        # 3.6 搜提示词（另一张画布）
        r5 = search("鸟瞰")
        check("搜到另一张画布的提示词",
              len(r5["hits"]) == 1 and "鸟瞰" in r5["hits"][0]["t"], r5["hits"])

        # ---------------------------------------------------------------
        # 4. 收尾：清掉本探针造的画布，别把测试数据留给下一次
        # ---------------------------------------------------------------
        print("== 清理 ==")
        pg.fill("#sncDocSearch", "")
        pg.wait_for_timeout(200)
        removed = 0
        for name in made:
            loc = pg.locator("#sncDocList .snc-doc-item", has_text=name)
            if not loc.count():
                continue
            loc.first.hover()
            loc.first.locator(".snc-doc-act.del").click()
            pg.wait_for_timeout(180)
            pg.click("#sncConfirmYes")
            pg.wait_for_timeout(320)
            removed += 1
        left = pg.evaluate(
            "() => [...document.querySelectorAll('#sncDocList .snc-doc-name')].map(e => e.textContent)")
        check("探针造的两张画布已删掉",
              all(n not in left for n in made if n), [made, left])
        check("没有页面异常", not errs, errs[:3])

        print("")
        print("PASS=%d FAIL=%d" % (PASS, FAIL))
        b.close()
        return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
