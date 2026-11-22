# -*- coding: utf-8 -*-
"""v2.6 回归 · B1 分片存储 / B2 更新通道 / B3 日志排障 / B4 画布工具 / A8 运镜 / A3 模板库。

全程网络存根。要点：新能力全部默认不改变老链路，关闭开关后提示词逐字一致。
"""
import base64
import json
import os
import random
import struct
import zlib
from playwright.sync_api import sync_playwright

# 默认端口留给老用法，但在跑整套回归时用 SNC_BASE 指向当前那个桥接服务，
# 免得端口一变这三个文件就集体 ERR_CONNECTION_REFUSED。
BASE = os.environ.get("SNC_BASE") or "http://127.0.0.1:8321/canvas.html"
SHOTS = r"E:\canvas-probe2\shots-v26"
os.makedirs(SHOTS, exist_ok=True)

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS  " if ok else "FAIL  ") + name + (("  | " + str(detail)) if detail else ""))


def noise_png(w, h):
    """噪声图压缩后仍 >20KB，用来验证 B1 的大图分片确实落盘。"""
    raw = b"".join(b"\x00" + os.urandom(w * 3) for _ in range(h))

    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


NOISE = base64.b64encode(noise_png(320, 240)).decode("ascii")

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
                      body=json.dumps({"ok": True, "b64": NOISE, "size": "stub",
                                       "width": 560, "height": 420, "format": "png",
                                       "model": "stub-image", "mode": "gen",
                                       "latencyMs": 100, "usage": {}}))

    page.route("**/api/generate", gen)
    page.goto(BASE)
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(900)

    def make_card(label):
        before = page.evaluate("() => Array.from(document.querySelectorAll('.snc-node')).map(d=>d.dataset.id)")
        page.fill("#sncInput", label)
        page.click("#sncSend")
        page.wait_for_timeout(1300)
        return page.evaluate("""(old) => {
            const cs = Array.from(document.querySelectorAll('.snc-node'));
            const n = cs.find(d => !old.includes(d.dataset.id));
            return n ? n.dataset.id : '';
        }""", before)

    # ---------- B1 会话分片存储 ----------
    cid = make_card("B1 分片大图测试")
    page.wait_for_timeout(1200)      # 等防抖保存落盘
    db = page.evaluate("""() => new Promise(resolve => {
        const r = indexedDB.open('sensenova-canvas');
        r.onsuccess = () => {
          const d = r.result, names = Array.from(d.objectStoreNames);
          const tx = d.transaction('chunks', 'readonly');
          const q = tx.objectStore('chunks').getAll();
          q.onsuccess = () => {
            const bt = d.transaction('boards', 'readonly');
            const bq = bt.objectStore('boards').getAll();
            bq.onsuccess = () => resolve({
              version: d.version, names: names,
              chunks: q.result.length,
              chunkBytes: q.result.reduce((a,c)=>a+String(c.data).length,0),
              boards: bq.result.length,
              chunked: bq.result.filter(b => b.__chunked).length,
              inlineBig: bq.result.reduce((a,b)=>a+(b.nodes||[]).filter(n=>n.dataUrl && n.dataUrl.length>20000).length,0)
            });
          };
        };
        r.onerror = () => resolve({error: String(r.error)});
    })""")
    check("B1 · IndexedDB 升到 v3", db.get("version") == 3, db)
    check("B1 · chunks store 已建立", "chunks" in db.get("names", []), db.get("names"))
    check("B1 · 大图确实外置成分片", db.get("chunks", 0) > 0 and db.get("chunkBytes", 0) > 20000, db)
    check("B1 · board 标了分片版本", db.get("chunked", 0) >= 1, db)
    check("B1 · board 里不再内联大图", db.get("inlineBig", 1) == 0, db.get("inlineBig"))

    page.reload()
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(1000)
    back = page.evaluate("""() => ({
        nodes: document.querySelectorAll('.snc-node').length,
        imgs: Array.from(document.querySelectorAll('.snc-node img'))
                .filter(i => i.naturalWidth > 0).length
    })""")
    check("B1 · 重载后画布节点仍在", back["nodes"] >= 5, back)
    check("B1 · 重载后图片仍可渲染", back["imgs"] >= 1, back)

    # ---------- B2 自动更新 / B3 日志排障 ----------
    upd = page.evaluate("() => fetch('/api/update/check').then(r=>r.json())")
    check("B2 · 更新检查接口可用", upd.get("ok") is True, upd)
    # 版本号随发版变化，这里只验「返回的是个三段式版本号」，不锁死具体值
    import re as _re
    check("B2 · 返回当前版本号",
          bool(_re.match(r"^\d+\.\d+\.\d+$", str(upd.get("current") or ""))),
          upd.get("current"))
    check("B2 · 版本清单路径存在", bool(upd.get("manifest")), upd.get("manifest"))
    check("B2 · 未配置清单时安全降级", isinstance(upd.get("hasUpdate"), bool), upd.get("hasUpdate"))
    tail = page.evaluate("() => fetch('/api/logs/tail').then(r=>r.json())")
    check("B3 · 日志读取接口可用", tail.get("ok") is True and "text" in tail, str(tail)[:120])
    check("B3 · 日志路径指向 app.log", "app.log" in str(tail.get("path", "")), tail.get("path"))
    # 关于页工程工具（直接展开设置对话框的「关于」分区）
    page.evaluate("""() => {
        document.getElementById('sncSettings').hidden = false;
        const b = Array.from(document.querySelectorAll('#sncSetNav button'))
                       .find(x => x.dataset.pane === 'about');
        if (b) b.click();
    }""")
    page.wait_for_timeout(200)
    check("B2 · 关于页「检查更新」按钮", page.locator("#sncAboutCheckUpdate").count() == 1)
    check("B3 · 关于页「打开日志文件夹」按钮", page.locator("#sncAboutOpenLogs").count() == 1)
    check("B3 · 关于页「查看最近日志」按钮", page.locator("#sncAboutTailLogs").count() == 1)
    check("B3 · 启动画面状态条", page.locator("#sncSplashStatus").count() == 1)
    page.click("#sncAboutCheckUpdate")
    page.wait_for_timeout(500)
    out = page.inner_text("#sncAboutOut")
    check("B2 · 点击后输出检查结果",
          str(upd.get("current") or "") in out or "失败" in out, out[:120])
    page.click("#sncAboutTailLogs")
    page.wait_for_timeout(400)
    check("B3 · 点击后输出日志内容", len(page.inner_text("#sncAboutOut")) > 0)
    page.screenshot(path=os.path.join(SHOTS, "v26-关于页工程工具.png"))
    page.evaluate("() => { document.getElementById('sncSettings').hidden = true; }")

    # ---------- B4 小地图 / 整理画布 / 图层 ----------
    check("B4 · 顶栏三个工具按钮", all(page.locator("#" + i).count() == 1 for i in
          ["sncTidyBtn", "sncMiniBtn", "sncLayersBtn"]))
    page.click("#sncMiniBtn")
    page.wait_for_timeout(250)
    check("B4 · 小地图可打开", page.evaluate("() => !document.getElementById('sncMini').hidden"))
    mini = page.evaluate("""() => {
        const c = document.getElementById('sncMiniCanvas');
        const d = c.getContext('2d').getImageData(0,0,c.width,c.height).data;
        let n = 0; for (let i=3;i<d.length;i+=4) if (d[i] > 0) n++;
        return {w:c.width, h:c.height, drawn:n};
    }""")
    check("B4 · 小地图有实际绘制", mini["drawn"] > 100, mini)
    before_view = page.evaluate("() => document.getElementById('sncWorld') ? document.getElementById('sncWorld').style.transform : document.querySelector('.snc-world').style.transform")
    box = page.locator("#sncMiniCanvas").bounding_box()
    page.mouse.click(box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.35)
    page.wait_for_timeout(250)
    after_view = page.evaluate("() => document.getElementById('sncWorld') ? document.getElementById('sncWorld').style.transform : document.querySelector('.snc-world').style.transform")
    check("B4 · 点小地图能定位视口", before_view != after_view, (before_view, after_view))

    pos0 = page.evaluate("""() => Array.from(document.querySelectorAll('.snc-node'))
                                 .map(n => n.style.transform).join('|')""")
    page.click("#sncTidyBtn")
    page.wait_for_timeout(350)
    pos1 = page.evaluate("""() => Array.from(document.querySelectorAll('.snc-node'))
                                 .map(n => n.style.transform).join('|')""")
    check("B4 · 整理画布重排节点", pos0 != pos1, (pos0, pos1))
    page.click("#sncLayersBtn")
    page.wait_for_timeout(250)
    check("B4 · 图层面板可打开", page.evaluate("() => !document.getElementById('sncLayers').hidden"))
    # v2.9：图层改成 PS 式顺序列表（不再按派生深度分小标题），改验证结构
    check("B4 · 图层面板有列表与成组入口",
          "图层" in page.inner_text("#sncLayers") and
          page.locator("#sncLayersGroup").count() == 1 and
          page.locator("#sncLayersBody .snc-layer-eye").count() > 0)
    rows = page.locator("#sncLayersBody .snc-layer-row").count()
    check("B4 · 图层列出节点", rows > 0, rows)
    if rows:
        first = page.locator("#sncLayersBody .snc-layer-row").first
        lid = first.get_attribute("data-lid")
        page.click('#sncLayersBody button[data-eye="%s"]' % lid)
        page.wait_for_timeout(250)
        op = page.evaluate("""(id) => { const n=document.querySelector('.snc-node[data-id="'+id+'"]'); return n ? n.style.opacity : ''; }""", lid)
        pe = page.evaluate("""(id) => { const n=document.querySelector('.snc-node[data-id="'+id+'"]'); return n ? n.style.pointerEvents : ''; }""", lid)
        # v2.7 起隐藏是真的隐藏：透明且点不到（原来只压到 0.18，还照样能点）
        check("B4 · 图层眼睛可隐藏节点", op == "0" and pe == "none", (op, pe))
        page.click('#sncLayersBody button[data-eye="%s"]' % lid)
        page.wait_for_timeout(200)
    page.click("#sncMiniX")
    page.click("#sncLayersX")
    check("B4 · 两个面板可收起", page.evaluate("""() =>
        document.getElementById('sncMini').hidden && document.getElementById('sncLayers').hidden"""))

    # ---------- A3 分类模板库 ----------
    page.evaluate("""() => {
        try{ localStorage.removeItem('snc.struct.all'); localStorage.removeItem('snc.struct.opt');
             localStorage.removeItem('snc.struct.cat'); }catch(e){}
    }""")
    page.reload()
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(800)
    cats = page.evaluate("() => window.SNC_V26_CATEGORIES && Object.keys(window.SNC_V26_CATEGORIES)")
    check("A3 · 8 类分类模板库", bool(cats) and len(cats) == 8, cats)
    check("A3 · 参数浮层有分类模板下拉", page.locator("#sncStructCat").count() == 1)
    page.evaluate("""() => {
        const s = document.getElementById('sncStructCat');
        s.value = 'lighting';
        s.dispatchEvent(new Event('change', {bubbles: true}));
    }""")
    page.wait_for_timeout(150)
    check("A3 · 分类模板写入 localStorage",
          page.evaluate("() => localStorage.getItem('snc.struct.cat')") == "lighting")
    n0 = len(bodies)
    page.fill("#sncInput", "夜景灯光优化")
    page.click("#sncSend")
    page.wait_for_timeout(1300)
    pr = (bodies[-1].get("prompt") if len(bodies) > n0 else "") or ""
    check("A3 · 提交提示词含分类模板", "提示词分类模板" in pr and "夜景照明" in pr, pr[:160])

    # ---------- A8 运镜词库绑定 ----------
    motion = page.evaluate("() => window.SNC_V26_MOTION && window.SNC_V26_MOTION.length")
    check("A8 · 21 条运镜短句已挂载", motion == 21, motion)
    page.evaluate("""() => { try{ localStorage.removeItem('snc.struct.cat'); }catch(e){} }""")
    page.reload()
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(800)
    gid = page.evaluate("""() => {
        window.SNC_V26_FIT();
        const n = Array.from(document.querySelectorAll('.snc-node')).find(x => x.querySelector('img'));
        return n ? n.dataset.id : '';
    }""")
    page.click('.snc-node[data-id="%s"]' % gid)
    page.wait_for_timeout(250)
    page.click('#sncImgBar button[data-act="skill"]')
    page.wait_for_timeout(350)
    page.fill("#sncSkpSearch", "视角切换")
    page.wait_for_timeout(350)
    hit = page.evaluate("""() => {
        const t = Array.from(document.querySelectorAll('#sncSkpBody .snc-skp-tile'))
          .find(x => (x.querySelector('em')||{}).textContent.trim() === '视角切换');
        if (!t) return null;
        const r = t.getBoundingClientRect();
        return {x: r.x + r.width/2, y: r.y + r.height/2};
    }""")
    check("A8 · 技能面板能找到视角切换", bool(hit), hit)
    if hit:
        page.mouse.click(hit["x"], hit["y"])
        page.wait_for_timeout(400)
        # v3.7：点技能弹的是统一工作台（视角切换没有参数，只有提示词和生成按钮），收起它
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        n1 = len(bodies)
        page.fill("#sncInput", "改成鸟瞰视角")
        page.click("#sncSend")
        page.wait_for_timeout(1300)
        pr2 = (bodies[-1].get("prompt") if len(bodies) > n1 else "") or ""
        check("A8 · 视角切换提交注入运镜词库",
              "运镜词库" in pr2 or "视角切换规则" in pr2, pr2[:200])

    # ---------- 老链路逐字不变 ----------
    page.evaluate("""() => {
        try{ ['snc.struct.all','snc.struct.opt','snc.struct.cat'].forEach(k=>localStorage.removeItem(k)); }catch(e){}
    }""")
    page.reload()
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(800)
    n2 = len(bodies)
    page.fill("#sncInput", "老链路逐字校验")
    page.click("#sncSend")
    page.wait_for_timeout(1300)
    pr3 = (bodies[-1].get("prompt") if len(bodies) > n2 else "") or ""
    check("关闭所有开关后提示词逐字不变", pr3 == "老链路逐字校验", repr(pr3))

    check("全程无 JS 报错", not errs, errs[:3])
    ctx.close()
    br.close()

passed = sum(1 for _, ok in results if ok)
print("\n%d / %d 通过" % (passed, len(results)))
if passed != len(results):
    print("失败项：" + ", ".join(n for n, ok in results if not ok))
    raise SystemExit(1)
