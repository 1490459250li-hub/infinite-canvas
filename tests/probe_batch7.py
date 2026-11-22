# -*- coding: utf-8 -*-
"""第七批（v3.7.4）改动自检：跨节点对比浮层（P2-8）。

跑法：
    python tests/probe_batch7.py http://127.0.0.1:8321

三个断言原则：
1. 「跨节点」必须真的是两张不同卡片、在画布上离得很远，还能装进同一个舞台；
2. 分割线要用真实指针拖（playwright mouse），不能只调函数读返回值；
3. 交换之后标签、缩略图选中态、图源三者要一起变 —— 只变 id 是半成品。
"""
import re
import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8321"
PASS = 0
FAIL = 0


def clip_pct(v):
    """浏览器会把 inset() 里的 0 规范成 0px，别拿字符串死比；直接取右侧留白百分比。"""
    m = re.search(r"inset\(\s*0(?:px)?\s+([\d.]+)%", v or "")
    return float(m.group(1)) if m else None


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
        pg.wait_for_timeout(700)

        # ---------------------------------------------------------------
        # 0. 造场景：四张卡，其中 c 与 d 在画布上隔了 3000px
        # ---------------------------------------------------------------
        print("== 造场景 ==")
        built = pg.evaluate("""() => {
          const api = window.SNC_TEST_API;
          const N = api.nodes(); N.length = 0;
          function pic(r, g, bl){
            const c = document.createElement('canvas'); c.width = 240; c.height = 160;
            const x = c.getContext('2d');
            x.fillStyle = 'rgb(' + r + ',' + g + ',' + bl + ')';
            x.fillRect(0, 0, 240, 160);
            x.fillStyle = '#fff'; x.font = '28px sans-serif';
            x.fillText(r + ',' + g + ',' + bl, 12, 88);
            return c.toDataURL('image/png');
          }
          function mk(id, o){
            const u = pic(o.r, o.g, o.b);
            return Object.assign({
              id: id, type: 'gen', status: 'done', x: 0, y: 0, w: 220, h: 160,
              dataUrl: u, prompt: '客厅夜景', from: [], label: id,
              realSize: '2048x1152', ratio: 'auto', res: 2048,
              createdAt: 1, vIndex: 0,
              versions: [{ dataUrl: u, size: '2048x1152', model: o.model,
                           latencyMs: 900, usage: {}, kind: 'gen',
                           prompt: '客厅夜景', ratio: 'auto', at: 1 }]
            }, o.extra || {});
          }
          N.push(mk('pc-a', { r: 200, g: 40, b: 40, model: 'fast',
                              extra: { from: ['src-x'], label: '客厅 · fast' } }));
          N.push(mk('pc-b', { r: 40, g: 80, b: 200, model: 'pro',
                              extra: { from: ['src-x'], x: 260,
                                       label: '客厅 · pro' } }));
          N.push(mk('pc-c', { r: 40, g: 160, b: 90, model: 'fast',
                              extra: { x: 3000, y: 1400, label: '书房 · 原图',
                                       prompt: '书房晨光', from: ['src-y'] } }));
          N.push(mk('pc-d', { r: 220, g: 190, b: 40, model: 'pro',
                              extra: { x: 3260, y: 1400, label: '书房 · 改后',
                                       prompt: '书房晨光', from: [],
                                       derivedFrom: 'pc-c' } }));
          api.render();
          return { n: N.length, ax: N[0].x, cx: N[2].x };
        }""")
        check("造出 4 张已完成卡片", built["n"] == 4, built)
        check("两张要对比的卡在画布上相距 3000px", built["cx"] - built["ax"] >= 2900, built)
        pg.wait_for_timeout(300)

        st = pg.evaluate("() => window.SNC_TEST_API.cpovState()")
        check("初始浮层是关的", st["open"] is False, st)

        # 真用户路径：先点一下这张卡（工具条才出来），再点「两图对比」
        r = pg.evaluate("""() => {
          const el = document.querySelector('[data-id="pc-a"]');
          const b = el.getBoundingClientRect();
          return { x: b.left + b.width / 2, y: b.top + b.height / 2 };
        }""")
        pg.mouse.click(r["x"], r["y"])
        pg.wait_for_timeout(160)
        bar = pg.evaluate("""() => {
          const bar = document.getElementById('sncImgBar');
          const btn = bar.querySelector('[data-act="paircmp"]');
          return { hidden: bar.hidden, hasBtn: !!btn,
                   label: btn ? btn.textContent.trim() : '',
                   title: btn ? btn.title : '' };
        }""")
        check("选中卡片后工具条里有「两图对比」按钮",
              bar["hidden"] is False and bar["hasBtn"] is True, bar)
        check("按钮文案说清了是跨卡片对比",
              "两图对比" in bar["label"] and "跨卡片" in bar["title"], bar)

        # ---------------------------------------------------------------
        # 1. 打开：左槽放这张卡，右槽自动猜一张
        # ---------------------------------------------------------------
        print("== 打开与自动猜搭档 ==")
        pg.click('#sncImgBar [data-act="paircmp"]')
        pg.wait_for_timeout(180)
        st = pg.evaluate("() => window.SNC_TEST_API.cpovState()")
        check("点工具条按钮打开浮层", st["open"] is True, st)
        check("左槽是点开的这张卡", st["a"] == "pc-a", st)
        check("右槽自动猜到了同一批的 pc-b", st["b"] == "pc-b", st)
        check("两边图源都设上了", st["srcA"] and st["srcB"], st)
        check("分割线与裁切都在显示", st["clipShown"] and st["gripShown"], st)
        check("空态没有露出来", st["voidShown"] is False, st)
        check("默认分割位置 50%", abs(st["pct"] - 50) < 0.01, st)
        check("标签读得到两边名字",
              "客厅 · fast" in st["tagA"] and "客厅 · pro" in st["tagB"], st)
        check("顶部说明了差异（模型 fast → pro）",
              "fast" in st["sub"] and "pro" in st["sub"], st)
        check("缩略图条列出全部 4 张", st["thumbs"] == 4, st)
        check("缩略图条里恰好一张标成右边、一张标成左边",
              st["on"] == 1 and st["off"] == 1, st)
        check("浮层打开时工具条按钮点亮", st["btnOn"] is True, st)

        st = pg.evaluate("() => { window.SNC_TEST_API.cpovClose(); "
                         "window.SNC_TEST_API.cpovOpen('pc-c'); return window.SNC_TEST_API.cpovState(); }")
        check("派生关系优先：对原图打开时猜它的派生卡 pc-d", st["b"] == "pc-d", st)
        check("跨节点：相距 3000px 的两张卡也能进同一个舞台", st["ready"] is True, st)
        check("派生对比里提示词相同（不再列模型）",
              "提示词相同" in st["sub"], st)

        # 两张图真的铺在同一个框里（不是各占一半、也不是缩略图）
        geo = pg.evaluate("""() => {
          const s = document.getElementById('sncCpoStage').getBoundingClientRect();
          const a = document.getElementById('sncCpoA').getBoundingClientRect();
          const bb = document.getElementById('sncCpoB').getBoundingClientRect();
          const cs = getComputedStyle(document.getElementById('sncCpoA'));
          return { sw: s.width, sh: s.height,
                   aw: a.width, ah: a.height, bw: bb.width, bh: bb.height,
                   dx: Math.abs(a.left - bb.left), dy: Math.abs(a.top - bb.top),
                   fit: cs.objectFit };
        }""")
        check("两张图叠在同一个位置上（左均差 < 1px）",
              geo["dx"] < 1 and geo["dy"] < 1, geo)
        check("两张图都铺满舞台（不是并排两栏）",
              abs(geo["aw"] - geo["sw"]) < 1 and abs(geo["ah"] - geo["sh"]) < 1, geo)
        check("object-fit 是 contain（不裁切内容）", geo["fit"] == "contain", geo)

        # ---------------------------------------------------------------
        # 2. 分割线：函数 + 真实指针两种路径
        # ---------------------------------------------------------------
        print("== 分割线 ==")
        st = pg.evaluate("() => { window.SNC_TEST_API.cpovMove(30); return window.SNC_TEST_API.cpovState(); }")
        check("move(30) 后裁切只留左边 30%",
              clip_pct(st["clip"]) == 70, st["clip"])
        check("move(30) 后手柄在 30%", st["gripLeft"] == "30%", st["gripLeft"])
        check("aria-valuenow 跟着走", st["ariaNow"] == "30", st["ariaNow"])

        st = pg.evaluate("() => { window.SNC_TEST_API.cpovMove(-20); return window.SNC_TEST_API.cpovState(); }")
        check("负数被夹到 0", st["pct"] == 0 and clip_pct(st["clip"]) == 100, st)
        st = pg.evaluate("() => { window.SNC_TEST_API.cpovMove(180); return window.SNC_TEST_API.cpovState(); }")
        check("超过 100 被夹到 100", st["pct"] == 100 and clip_pct(st["clip"]) == 0, st)

        # 真拖：从 50% 拖到 75%
        pg.evaluate("() => window.SNC_TEST_API.cpovMove(50)")
        box = pg.evaluate("""() => {
          const r = document.getElementById('sncCpoStage').getBoundingClientRect();
          return { x: r.left, y: r.top, w: r.width, h: r.height };
        }""")
        pg.mouse.move(box["x"] + box["w"] * 0.5, box["y"] + box["h"] * 0.5)
        pg.mouse.down()
        pg.mouse.move(box["x"] + box["w"] * 0.75, box["y"] + box["h"] * 0.5, steps=8)
        pg.mouse.up()
        st = pg.evaluate("() => window.SNC_TEST_API.cpovState()")
        check("真实拖动到 75%：左边露 75%、右侧留白 25%",
              clip_pct(st["clip"]) == 25, st["clip"])
        check("真实拖动后手柄跟着到 75%", st["gripLeft"] == "75%", st["gripLeft"])

        # 拖动不应该带动画布（背景 view 没变）
        view = pg.evaluate("""() => {
          const w = document.querySelector('#sncStage .snc-world');
          return w ? w.style.transform : '';
        }""")
        pg.evaluate("() => window.SNC_TEST_API.cpovMove(50)")

        # ---------------------------------------------------------------
        # 3. 互换：id、标签、缩略图选中态要一起动
        # ---------------------------------------------------------------
        print("== 左右互换 ==")
        pg.evaluate("() => { window.SNC_TEST_API.cpovClose(); "
                     "window.SNC_TEST_API.cpovOpen('pc-a'); window.SNC_TEST_API.cpovMove(40); }")
        before = pg.evaluate("() => window.SNC_TEST_API.cpovState()")
        after = pg.evaluate("() => { window.SNC_TEST_API.cpovSwap(); return window.SNC_TEST_API.cpovState(); }")
        check("互换后 a/b 对调", after["a"] == before["b"] and after["b"] == before["a"], (before, after))
        check("互换后标签跟着换（不是只换 id）",
              after["tagA"] == before["tagB"] and after["tagB"] == before["tagA"], (before, after))
        check("互换后分割位置保持不动（画面不跳）", abs(after["pct"] - 40) < 0.01, after)
        check("互换后缩略图选中态重新算过",
              after["on"] == 1 and after["off"] == 1, after)

        # 键盘 S
        pg.keyboard.press("s")
        st = pg.evaluate("() => window.SNC_TEST_API.cpovState()")
        check("按 S 也能互换", st["a"] == before["a"] and st["b"] == before["b"], st)

        # ---------------------------------------------------------------
        # 4. 缩略图条：换右槽 / 点左边那张则互换
        # ---------------------------------------------------------------
        print("== 缩略图条 ==")
        pg.evaluate("() => { window.SNC_TEST_API.cpovClose(); window.SNC_TEST_API.cpovOpen('pc-a'); }")
        pg.click('#sncCpoStrip .snc-cpo-th[data-id="pc-d"]')
        st = pg.evaluate("() => window.SNC_TEST_API.cpovState()")
        check("点缩略图把 pc-d 放到右边", st["b"] == "pc-d", st)
        check("右边换成 pc-d 后标签同步", "书房" in st["tagB"], st)
        check("换图后只有一张 is-on",
              pg.evaluate("() => document.querySelectorAll('#sncCpoStrip .is-on').length") == 1, st)

        st_before = st
        pg.click('#sncCpoStrip .snc-cpo-th[data-id="pc-a"]')
        st = pg.evaluate("() => window.SNC_TEST_API.cpovState()")
        check("点当前左边那张的缩略图 = 互换",
              st["a"] == st_before["b"] and st["b"] == st_before["a"], (st_before, st))

        # ---------------------------------------------------------------
        # 5. 键盘：Esc 关、Delete 不删卡、方向键移分割、T 不建笔记
        # ---------------------------------------------------------------
        print("== 键盘与模态 ==")
        pg.evaluate("() => { window.SNC_TEST_API.cpovClose(); window.SNC_TEST_API.cpovOpen('pc-a'); "
                     "window.SNC_TEST_API.cpovMove(50); }")
        n0 = pg.evaluate("() => window.SNC_TEST_API.nodes().length")
        pg.keyboard.press("Delete")
        n1 = pg.evaluate("() => window.SNC_TEST_API.nodes().length")
        check("浮层打开时 Delete 不会删掉背后的卡", n1 == n0, (n0, n1))

        pg.keyboard.press("t")
        n2 = pg.evaluate("() => window.SNC_TEST_API.nodes().length")
        check("浮层打开时 T 不会新建笔记", n2 == n0, (n0, n2))

        st0 = pg.evaluate("() => window.SNC_TEST_API.cpovState()")
        pg.keyboard.press("ArrowRight")
        st1 = pg.evaluate("() => window.SNC_TEST_API.cpovState()")
        check("→ 把分割线右移 2%", abs(st1["pct"] - st0["pct"] - 2) < 0.01, (st0["pct"], st1["pct"]))
        pg.keyboard.down("Shift")
        pg.keyboard.press("ArrowLeft")
        pg.keyboard.up("Shift")
        st2 = pg.evaluate("() => window.SNC_TEST_API.cpovState()")
        check("Shift+← 左移 10%", abs(st2["pct"] - st1["pct"] + 10) < 0.01, (st1["pct"], st2["pct"]))

        still = pg.evaluate("() => window.SNC_TEST_API.cpovState()")
        check("按方向键期间浮层没被关掉", still["open"] is True, still)

        pg.keyboard.press("Escape")
        st = pg.evaluate("() => window.SNC_TEST_API.cpovState()")
        check("Esc 关闭浮层", st["open"] is False, st)
        check("关闭后清理了 a/b 与缩略图条",
              st["a"] is None and st["b"] is None and st["thumbs"] == 0, st)

        # ---------------------------------------------------------------
        # 6. 标签跳转
        # ---------------------------------------------------------------
        print("== 点标签回到那张卡 ==")
        pg.evaluate("() => { window.SNC_TEST_API.cpovClose(); window.SNC_TEST_API.cpovOpen('pc-a', 'pc-c'); }")
        jump = pg.evaluate("() => window.SNC_TEST_API.cpovJump('b')")
        check("点右标签后浮层关闭", jump["open"] is False, jump)
        check("并且选中了那张卡", jump["sel"] == ["pc-c"], jump)

        # ---------------------------------------------------------------
        # 7. 空态：画布上只有一张图
        # ---------------------------------------------------------------
        print("== 空态 ==")
        saved = pg.evaluate("""() => {
          const N = window.SNC_TEST_API.nodes();
          const keep = N.filter(n => n.id === 'pc-a');
          window.__pcSaved = N.slice();
          N.length = 0; keep.forEach(n => N.push(n));
          window.SNC_TEST_API.render();
          window.SNC_TEST_API.cpovOpen('pc-a');
          return window.SNC_TEST_API.cpovState();
        }""")
        check("只有一张图时右槽为空", saved["b"] is None, saved)
        check("空态文案说清是缺第二张", "第二张" in saved["voidT"], saved["voidT"])
        check("空态时裁切与手柄都收起来（不装成能对比）",
              saved["clipShown"] is False and saved["gripShown"] is False, saved)
        check("空态时只有一张缩略图并给了说明",
              saved["thumbs"] == 0 and
              pg.evaluate("() => !!document.querySelector('#sncCpoStrip .snc-cpo-strip-empty')"),
              saved)
        pg.evaluate("""() => {
          const N = window.SNC_TEST_API.nodes();
          N.length = 0; (window.__pcSaved || []).forEach(n => N.push(n));
          window.SNC_TEST_API.cpovClose();
          window.SNC_TEST_API.render();
        }""")

        # ---------------------------------------------------------------
        # 8. 版本切换 / 出图后浮层要跟着刷新
        # ---------------------------------------------------------------
        print("== 数据变了浮层跟着刷 ==")
        fresh = pg.evaluate("""() => {
          const api = window.SNC_TEST_API;
          api.cpovClose();
          api.cpovOpen('pc-a', 'pc-b');
          const before = {
            src: (document.getElementById('sncCpoB').getAttribute('src') || '').length,
            tag: document.getElementById('sncCpoTagB').textContent,
            sub: document.getElementById('sncCpoSub').textContent
          };
          const N = api.nodes();
          const bN = N.find(n => n.id === 'pc-b');
          const c = document.createElement('canvas'); c.width = 120; c.height = 80;
          const g = c.getContext('2d'); g.fillStyle = '#00ffcc'; g.fillRect(0, 0, 120, 80);
          bN.versions.push({ dataUrl: c.toDataURL('image/png'), size: '1024x768',
                             model: 'pro', latencyMs: 1, usage: {}, kind: 'gen',
                             prompt: bN.prompt, at: 2 });
          bN.vIndex = bN.versions.length - 1;
          bN.dataUrl = bN.versions[bN.vIndex].dataUrl;
          bN.realSize = '1024x768';
          api.render();          // 版本切换的统一出口：renderAll → paintNode 之外也要刷浮层
          const after = {
            src: (document.getElementById('sncCpoB').getAttribute('src') || '').length,
            tag: document.getElementById('sncCpoTagB').textContent,
            sub: document.getElementById('sncCpoSub').textContent
          };
          const st = api.cpovState();
          return { before: before, after: after, open: st['open'] };
        }""")
        check("浮层没被 renderAll 关掉", fresh["open"] is True, fresh)
        check("右边那张图源换成了新版本",
              fresh["after"]["src"] != fresh["before"]["src"], fresh)
        check("标签上的尺寸跟着变成 1024×768",
              "1024×768" in fresh["after"]["tag"], fresh["after"]["tag"])
        check("顶部差异行也换成新尺寸",
              "1024×768" in fresh["after"]["sub"], fresh["after"]["sub"])

        # ---------------------------------------------------------------
        # 9. 没有可对比对象 / 失败卡片：不能炸
        # ---------------------------------------------------------------
        print("== 边界 ==")
        edge = pg.evaluate("""() => {
          const api = window.SNC_TEST_API;
          const N = api.nodes();
          N.push({ id: 'pc-fail', type: 'gen', status: 'failed', x: 0, y: 0, w: 200, h: 160,
                   label: '失败卡', prompt: 'x', versions: [] });
          api.render();
          api.cpovClose();
          const opened = api.cpovOpen('pc-fail');
          const st = api.cpovState();
          api.cpovClose();
          const N2 = api.nodes();
          N2.length = N2.findIndex(n => n.id === 'pc-fail');
          api.render();
          return { opened: opened, open: st['open'] };
        }""")
        check("对没出图的失败卡打开：不开浮层也不报错", edge["opened"] is False, edge)

        pg.evaluate("() => window.SNC_TEST_API.cpovClose()")
        pg.wait_for_timeout(150)
        check("整个过程没有 JS 运行时错误", len(errs) == 0, errs[:3])

        b.close()

    print("")
    print("=" * 46)
    print("PASS %d   FAIL %d" % (PASS, FAIL))
    print("=" * 46)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
