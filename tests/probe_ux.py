# -*- coding: utf-8 -*-
"""v3.7.4 第四批 UX 探针。

覆盖四件事：
  1. 比例图形选择器 —— 按钮组存在、形状比例对、点击写回 select、tip 跟着变、方向键能走
  2. 空态引导     —— 空画布时出引导块、三个示例 chip、点一下填进输入框
  3. content-visibility —— 离屏卡片跳过绘制，但节点 rect 尺寸不被 intrinsic size 顶替
  4. warmThumbs   —— 拦截 world.querySelectorAll 直接数调用次数（旧实现 = N 次）

用法：python tests/probe_ux.py [SNC_BASE]
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SNC_BASE", "http://127.0.0.1:8321"))
URL = BASE + "/canvas.html"

FAILS = []


def check(name, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("  " + str(extra)) if extra != "" else ""))
    if not cond:
        FAILS.append(name)


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge")
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1');"
                            "localStorage.setItem('snc.theme.v2','dark')}catch(e){}")
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(URL)
        pg.wait_for_selector(".snc-node")
        pg.wait_for_timeout(800)

        # ---------------- 1. 比例图形选择器 ----------------
        print("== 比例图形选择器 ==")
        info = pg.evaluate("""() => {
          const box = document.getElementById('sncGRatioPick');
          const sel = document.getElementById('sncGRatio');
          if(!box || !sel) return {missing:true};
          const btns = [...box.querySelectorAll('button[data-r]')];
          const cs = getComputedStyle(sel);
          const shapes = btns.map(b => {
            const i = b.querySelector('i');
            if(!i) return null;
            const r = i.getBoundingClientRect();
            return [Math.round(r.width), Math.round(r.height)];
          });
          return {
            n: btns.length,
            rs: btns.map(b => b.dataset.r),
            checked: btns.filter(b => b.getAttribute('aria-checked') === 'true').map(b => b.dataset.r),
            selVal: sel.value,
            selHidden: cs.position === 'absolute' && cs.width === '1px' && cs.height === '1px',
            selTabIndex: sel.getAttribute('tabindex'),
            groupRole: box.getAttribute('role'),
            btnRole: btns.length ? btns[0].getAttribute('role') : '',
            shapes: shapes,
            tip: (document.getElementById('sncGTip') || {}).textContent || ''
          };
        }""")
        check("按钮组存在且是 radiogroup", info.get("groupRole") == "radiogroup", info.get("groupRole"))
        check("六个比例档位齐全", info.get("n") == 6 and info.get("rs") ==
              ["auto", "1:1", "4:3", "3:4", "16:9", "9:16"], info.get("rs"))
        check("按钮带 radio 语义", info.get("btnRole") == "radio", info.get("btnRole"))
        check("默认选中「自动」", info.get("checked") == ["auto"], info.get("checked"))
        check("select 被移出视觉但仍在 DOM", bool(info.get("selHidden")) and
              info.get("selTabIndex") == "-1", [info.get("selHidden"), info.get("selTabIndex")])
        # 形状：横向比例必须真的比较宽，纵向比例必须真的比较高
        sh = info.get("shapes") or []
        check("1:1 画成正方形", len(sh) > 1 and sh[1][0] == sh[1][1], sh[1] if len(sh) > 1 else None)
        check("16:9 明显宽于高", len(sh) > 4 and sh[4][0] >= sh[4][1] * 1.6, sh[4] if len(sh) > 4 else None)
        check("9:16 明显高于宽", len(sh) > 5 and sh[5][1] >= sh[5][0] * 1.6, sh[5] if len(sh) > 5 else None)
        check("4:3 与 3:4 互为倒转", len(sh) > 3 and sh[2][0] == sh[3][1] and sh[2][1] == sh[3][0],
              [sh[2], sh[3]] if len(sh) > 3 else None)
        check("初始 tip 是有内容的默认文案", len(info.get("tip") or "") > 4, info.get("tip"))

        # 点击 → 写回 select + tip 更新
        pg.click('#sncGRatioPick button[data-r="9:16"]')
        pg.wait_for_timeout(180)
        r = pg.evaluate("""() => ({
          v: document.getElementById('sncGRatio').value,
          checked: [...document.querySelectorAll('#sncGRatioPick button[data-r]')]
                     .filter(b => b.getAttribute('aria-checked') === 'true').map(b => b.dataset.r),
          tip: (document.getElementById('sncGTip') || {}).textContent || '',
          aria: document.querySelector('#sncGRatioPick button[data-r="9:16"]').getAttribute('aria-checked')
        })""")
        check("点 9:16 写回 select.value", r.get("v") == "9:16", r.get("v"))
        check("选中态跟着切（只有一个 checked）", r.get("checked") == ["9:16"], r.get("checked"))
        check("aria-checked 同步", r.get("aria") == "true", r.get("aria"))
        check("底部 tip 跟着变成 9:16（改动真的进了 state.gRatio 链路）",
              "9:16" in (r.get("tip") or ""), r.get("tip"))

        # 方向键
        pg.focus('#sncGRatioPick button[data-r="9:16"]')
        pg.keyboard.press("ArrowRight")
        pg.wait_for_timeout(150)
        kv = pg.evaluate("""() => ({
          v: document.getElementById('sncGRatio').value,
          focus: document.activeElement ? document.activeElement.dataset.r : ''
        })""")
        check("方向键从最后一个绕回第一个（环形）", kv.get("v") == "auto" and kv.get("focus") == "auto", kv)

        # ---------------- 3. content-visibility （先测，节点还在） ----------------
        print("== content-visibility ==")
        # 注意：getBoundingClientRect 返回的是变换后尺寸（world 有 scale），不能拿来比内联宽高。
        # 真正要证明的是「离屏时布局尺寸不被 contain-intrinsic-size 顶替」—— 把节点挪到屏幕外再读 offsetWidth。
        near = pg.evaluate("""() => {
          const n = [...document.querySelectorAll('.snc-node')][0];
          if(!n) return {missing:true};
          const cs = getComputedStyle(n);
          return {
            cv: cs.contentVisibility, cis: cs.containIntrinsicSize,
            offW: n.offsetWidth, offH: n.offsetHeight,
            inlineW: parseFloat(n.style.width), inlineH: parseFloat(n.style.height)
          };
        }""")
        check("节点启用 content-visibility:auto", near.get("cv") == "auto", near.get("cv"))
        check("contain-intrinsic-size 有兜底值", bool(near.get("cis")), near.get("cis"))

        far = pg.evaluate("""() => {
          const N = window.SNC_TEST_API.nodes();
          const first = N[0];
          const keep = { x: first.x, y: first.y };
          first.x = 40000; first.y = 40000;      // 挪到画布外地带
          window.SNC_TEST_API.render();
          const n = document.querySelector('.snc-node[data-id="' + first.id + '"]');
          const out = n ? { offW: n.offsetWidth, offH: n.offsetHeight,
                            inlineW: parseFloat(n.style.width), inlineH: parseFloat(n.style.height),
                            cv: getComputedStyle(n).contentVisibility } : null;
          first.x = keep.x; first.y = keep.y;    // 还原
          window.SNC_TEST_API.render();
          return out;
        }""")
        check("离屏后布局尺寸仍等于内联宽高（intrinsic size 没顶替真实尺寸 → 连线定位安全）",
              far and far["offW"] == far["inlineW"] and far["offH"] == far["inlineH"], far)

        # ---------------- 2. 空态引导 ----------------
        print("== 空态引导 ==")
        pg.evaluate("() => { const N = window.SNC_TEST_API.nodes(); N.length = 0; window.SNC_TEST_API.render(); }")
        pg.wait_for_timeout(400)
        e = pg.evaluate("""() => {
          const el = document.getElementById('sncEmpty');
          if(!el) return {missing:true};
          const cs = getComputedStyle(el);
          const chips = [...el.querySelectorAll('.snc-empty-chip')];
          return {
            hidden: el.hidden,
            title: (el.querySelector('.snc-empty-t') || {}).textContent.trim ? el.querySelector('.snc-empty-t').textContent.trim() : '',
            sub: (el.querySelector('.snc-empty-s') || {}).textContent ? el.querySelector('.snc-empty-s').textContent.trim() : '',
            chips: chips.map(c => c.textContent.trim()),
            chipPE: chips.length ? getComputedStyle(chips[0]).pointerEvents : '',
            rootPE: cs.pointerEvents,
            prompts: chips.map(c => c.getAttribute('data-p') || '')
          };
        }""")
        check("空画布时引导块显示", e.get("hidden") is False, e.get("hidden"))
        check("标题换成「拖一张图进来，或说一句话」", "拖一张图进来" in (e.get("title") or ""), e.get("title"))
        check("副标题说明三种起步方式",
              all(k in (e.get("sub") or "") for k in ["新建笔记", "拖入", "继续编辑"]), e.get("sub"))
        check("三个示例 chip", len(e.get("chips") or []) == 3, e.get("chips"))
        check("引导块本身不吃指针（拖图仍能穿透）", e.get("rootPE") == "none", e.get("rootPE"))
        check("chip 本身可点击", e.get("chipPE") == "auto", e.get("chipPE"))
        check("每句示例都是完整提示词（不是空壳）",
              all(len(p) > 18 for p in (e.get("prompts") or [])), [len(p) for p in (e.get("prompts") or [])])

        pg.click("#sncEmpty .snc-empty-chip")
        pg.wait_for_timeout(200)
        fill = pg.evaluate("""() => {
          const inp = document.getElementById('sncInput');
          const first = document.querySelector('#sncEmpty .snc-empty-chip').getAttribute('data-p');
          return { val: inp.value, want: first, focused: document.activeElement === inp,
                   caret: inp.selectionStart, len: inp.value.length };
        }""")
        check("点 chip 把整句填进输入框", fill.get("val") == fill.get("want") and len(fill.get("val") or "") > 18,
              (fill.get("val") or "")[:32] + "…")
        check("填完自动聚焦并把光标放末尾", fill.get("focused") is True and
              fill.get("caret") == fill.get("len"), [fill.get("focused"), fill.get("caret"), fill.get("len")])

        # 有节点后引导块必须消失
        pg.evaluate("""() => {
          const N = window.SNC_TEST_API.nodes();
          N.push({ id:'probe-1', type:'gen', status:'done', label:'生成',
            x:120, y:120, w:320, h:220, dataUrl:'data:image/gif;base64,R0lGODlhAQABAAAAACw=',
            prompt:'p', vIndex:0, versions:[] });
          window.SNC_TEST_API.render();
        }""")
        pg.wait_for_timeout(300)
        hid = pg.evaluate("() => document.getElementById('sncEmpty').hidden")
        check("有节点后引导块自动收起", hid is True, hid)

        # ---------------- 4. warmThumbs 查询次数 ----------------
        print("== warmThumbs 索引化 ==")
        # 拦截 world.querySelectorAll —— 页面里 world 这个变量就是 #sncWorld，
        # 换掉元素上的方法就能数到真实调用次数（旧实现在 .then 里查，N 张大图 = N 次）
        pg.evaluate("""() => {
          const world = document.getElementById('sncWorld');
          const orig = world.querySelectorAll.bind(world);
          window.__qs = 0;
          window.__qsSel = [];
          world.querySelectorAll = function(sel){
            window.__qs++; window.__qsSel.push(sel);
            return orig(sel);
          };
        }""")

        made = pg.evaluate("""() => {
          const N = window.SNC_TEST_API.nodes();
          N.length = 0;
          function big(seed){
            const c = document.createElement('canvas');
            c.width = 1800; c.height = 1200;
            const x = c.getContext('2d');
            for(let i=0;i<1500;i++){
              x.fillStyle = 'hsl(' + ((seed*40+i*7)%360) + ',65%,' + (38 + (i%34)) + '%)';
              x.fillRect((i*137+seed*53)%1800, (i*89+seed*31)%1200, 90, 90);
            }
            return c.toDataURL('image/jpeg', 0.94);
          }
          for(let k=0;k<12;k++){
            const u = big(k);
            N.push({ id:'big-'+k, type:'gen', status:'done', label:'生成',
              x: 60 + (k%4)*380, y: 80 + Math.floor(k/4)*300, w: 340, h: 240,
              dataUrl: u, prompt:'p', vIndex:0,
              versions:[{dataUrl:u, model:'m', latencyMs:1, usage:{}}] });
          }
          window.SNC_TEST_API.render();
          return N.map(n => n.dataUrl.length);
        }""")
        pg.wait_for_timeout(3500)
        w = pg.evaluate("""() => {
          const N = window.SNC_TEST_API.nodes();
          const out = [];
          N.forEach(n => {
            const img = document.querySelector('.snc-node[data-id="' + n.id + '"] .snc-photo');
            out.push({ id: n.id, orig: n.dataUrl.length,
                       shown: img ? (img.currentSrc || img.src || '').length : -1,
                       nat: img ? img.naturalWidth : -1,
                       complete: img ? img.complete : false });
          });
          return { nodes: out, qs: window.__qs, sels: window.__qsSel.slice(0, 20) };
        }""")
        nodes = w.get("nodes") or []
        check("造出 12 张大图（每张 > 40KB）", len(nodes) == 12 and all(o["orig"] > 40000 for o in nodes),
              [o["orig"] for o in nodes][:4])
        check("全部换成了缩略图（显示用 src 比原图短）",
              all(o["shown"] > 0 and o["shown"] < o["orig"] for o in nodes),
              [(o["shown"], o["orig"]) for o in nodes][:3])
        check("缩略图真的解码出来了（content-visibility 没挡住加载）",
              all(o["complete"] and o["nat"] > 0 for o in nodes),
              [(o["nat"], o["complete"]) for o in nodes][:3])

        # 关键断言：12 张图不该产生 12 次全画布扫描
        check("全画布 querySelectorAll 次数远小于图数（旧实现是 12 次）",
              w.get("qs", 999) <= 4, "实测 %s 次: %s" % (w.get("qs"), w.get("sels")))

        check("页面无 JS 报错", not errs, errs[:3])
        b.close()

    print()
    if FAILS:
        print("FAIL %d 项: %s" % (len(FAILS), FAILS))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
