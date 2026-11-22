# -*- coding: utf-8 -*-
"""存档拆分探针：验证
  ① 平移/缩放只写视图小 key，不再触发整块画布重存；
  ② 视图能跨刷新恢复；
  ③ 历史版本落盘时压到 1024 长边并打上 shrunk 标记。

用法：python tests/probe_archive.py [SNC_BASE]
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SNC_BASE", "http://127.0.0.1:8321"))
URL = BASE + "/canvas.html"

# 造一张 2048 的卡 + 两个版本，再把上一版降级，看它变成 1024
SEED = """() => {
  const N = window.SNC_TEST_API.nodes();
  N.length = 0;
  function mk(color) {
    const c = document.createElement('canvas');
    c.width = 2048; c.height = 1536;
    const x = c.getContext('2d');
    x.fillStyle = color; x.fillRect(0, 0, 2048, 1536);
    for (let i = 0; i < 40; i++) {
      x.fillStyle = 'rgba(255,255,255,' + (i % 7) / 20 + ')';
      x.fillRect(i * 50, 0, 24, 1536);
    }
    return c.toDataURL('image/png');   // PNG，模拟接口出图
  }
  const a = mk('#38506e'), b = mk('#6e5040');
  N.push({ id: 'ar-1', type: 'gen', status: 'done', label: '生成',
    x: 120, y: 120, w: 320, h: 240, dataUrl: b, prompt: 'p', vIndex: 1,
    versions: [
      { dataUrl: a, model: 'm', latencyMs: 1000, usage: {}, kind: 'generate', at: Date.now() - 60000 },
      { dataUrl: b, model: 'm', latencyMs: 1000, usage: {}, kind: 'generate', at: Date.now() }
    ] });
  window.SNC_TEST_API.render();
  return { a: a.length, b: b.length };
}"""


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
        pg.wait_for_selector("#snc", timeout=20000)
        pg.wait_for_timeout(1500)

        # 打点：统计真正落盘（idbPut）的次数
        pg.evaluate("""() => {
          window.__puts = 0;
          const raw = window.indexedDB.open.bind(window.indexedDB);
          // 直接盯 transaction 的创建，比包 idbPut 更可靠（idbPut 在闭包里）
          const orig = IDBDatabase.prototype.transaction;
          IDBDatabase.prototype.transaction = function(scope){
            if (scope && String(scope).indexOf('boards') >= 0) window.__puts++;
            return orig.apply(this, arguments);
          };
        }""")

        sizes = pg.evaluate(SEED)
        pg.wait_for_timeout(1200)
        print("造图 PNG 尺寸: v1=%d KB v2=%d KB" % (sizes["a"] // 1024, sizes["b"] // 1024))

        # 历史版降级（模拟 pushVersion 里 demoteVersion(上一版) 的效果）
        pg.evaluate("""() => {
          const n = window.SNC_TEST_API.nodes().find(x => x.id === 'ar-1');
          if (n && n.versions && n.versions[0]) window.SNC_TEST_API.demote(n.versions[0]);
        }""")
        pg.wait_for_timeout(2200)

        # 平移 + 缩放
        pg.evaluate("() => { window.__puts = 0; }")
        v0 = pg.evaluate("() => { const w = document.querySelector('.snc-world') || document.getElementById('sncWorld'); return w ? w.style.transform : ''; }")
        # 空白区域拖动 = 平移；再滚一轮 = 缩放。两者都必须只动视图小 key
        pg.mouse.move(980, 620)
        pg.mouse.down()
        for i in range(14):
            pg.mouse.move(980 - i * 16, 620 - i * 11)
            pg.wait_for_timeout(16)
        pg.mouse.up()
        pg.wait_for_timeout(400)
        pg.mouse.move(760, 450)
        pg.mouse.wheel(0, -400)
        pg.wait_for_timeout(1400)   # 超过 600ms 的防抖窗口
        v1 = pg.evaluate("() => { const w = document.querySelector('.snc-world') || document.getElementById('sncWorld'); return w ? w.style.transform : ''; }")
        print("平移缩放前:", v0)
        print("平移缩放后:", v1)
        print("相机确实变了:", v0 != v1)

        puts = pg.evaluate("() => window.__puts")
        views = pg.evaluate("() => { try{ return JSON.parse(localStorage.getItem('snc.views.v1')||'{}'); }catch(e){ return null; } }")
        inmem = pg.evaluate("() => window.SNC_TEST_API.views()")
        print("内存视图表:", inmem)
        print("平移后 idb 事务数:", puts, "（期望 0）")
        print("视图小 key:", views)

        # 刷新后视图是否还在
        before = pg.evaluate("() => { const s = window.SNC_TEST_API.nodes(); return null; }")
        st = pg.evaluate("""() => {
          const w = document.querySelector('.snc-world') || document.getElementById('sncWorld');
          return w ? w.style.transform : '(no world)';
        }""")
        pg.reload()
        pg.wait_for_selector("#snc", timeout=20000)
        pg.wait_for_timeout(1800)
        st2 = pg.evaluate("""() => {
          const w = document.querySelector('.snc-world') || document.getElementById('sncWorld');
          return w ? w.style.transform : '(no world)';
        }""")
        print("刷新前 transform:", st)
        print("刷新后 transform:", st2)

        # 历史版压缩结果
        ver = pg.evaluate("""() => {
          const n = window.SNC_TEST_API.nodes().find(x => x.id === 'ar-1');
          if (!n || !n.versions) return null;
          return n.versions.map(v => ({shrunk: v.shrunk || 0, len: (v.dataUrl||'').length,
                                       head: (v.dataUrl||'').slice(0, 22)}));
        }""")
        print("版本落盘:", ver)
        if errs:
            print("JS 错误:", errs)
        ctx.close()
        b.close()


if __name__ == "__main__":
    main()
