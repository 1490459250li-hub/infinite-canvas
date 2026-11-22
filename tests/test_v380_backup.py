# -*- coding: utf-8 -*-
"""v3.8.0 浏览器实测：存档导出 / 恢复（换电脑继承记录）。

只验真流程，不碰真实数据：服务的 LOCALAPPDATA 被指到临时目录，
所以自动备份、IndexedDB 兜底都在沙箱里完成。

A 段：页面里 SNC_BACKUP 能用，导出真的落盘且是 gzip；
B 段：改一份存档再导入，画布/技能被正确写回；
C 段：导出的文件能被 readFile 重新读出来（等价于新电脑选文件）；
D 段：关于面板的四个按钮都在，且升级按钮默认隐藏。

跑法：python tests/test_v380_backup.py
"""
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

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


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "proto"))
import server  # noqa: E402  (只为借 free_port)


def free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


from playwright.sync_api import sync_playwright  # noqa: E402
import requests  # noqa: E402

TMP = tempfile.mkdtemp(prefix="snc-v380-e2e-")
PORT = free_port()
BASE = "http://127.0.0.1:%d" % PORT
env = dict(os.environ, SNC_PORT=str(PORT), LOCALAPPDATA=TMP)
proc = subprocess.Popen([sys.executable, os.path.join(HERE, "serve.py")],
                        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(100):
    try:
        requests.get(BASE + "/api/update/check", timeout=1)
        break
    except Exception:
        time.sleep(0.2)

errs = []
BACKUP_DIR = os.path.join(TMP, "SenseNovaCanvas", "backups")

try:
    with sync_playwright() as p:
        br = p.chromium.launch(channel="msedge")
        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(BASE + "/canvas.html", wait_until="domcontentloaded")
        page.wait_for_selector(".snc-node", timeout=30000)
        page.wait_for_timeout(1200)

        print("== A 页面能力与导出 ==")
        has_api = page.evaluate("() => !!(window.SNC_BACKUP && window.SNC_BACKUP.export)")
        check("页面暴露 SNC_BACKUP", has_api)

        gathered = page.evaluate("""() => window.SNC_BACKUP.gather().then(d => ({
            format: d.format, ver: d.ver, boards: d.boards.length,
            skills: d.skills.length, nodes: (d.boards[0] || {}).nodes
                    ? d.boards[0].nodes.length : -1,
            created: d.created
        }))""")
        check("存档格式标记正确",
              gathered["format"] == "snc-backup" and gathered["ver"] == 1, str(gathered))
        check("能读到既有画布", gathered["boards"] >= 1, str(gathered["boards"]))
        check("画布里有节点", gathered["nodes"] >= 1, str(gathered["nodes"]))

        exp = page.evaluate("""() => window.SNC_BACKUP.export(true).then(r => ({
            ok: !!(r.res && r.res.ok), path: (r.res || {}).path || '',
            bytes: r.bytes, boards: r.boards, error: (r.res || {}).error || ''
        }))""")
        check("自动备份成功", exp["ok"] is True, str(exp))
        check("落盘路径在 backups 目录",
              os.path.dirname(exp["path"]) == BACKUP_DIR, exp["path"])
        check("文件真实存在", os.path.isfile(exp["path"]), exp["path"])
        raw = open(exp["path"], "rb").read() if os.path.isfile(exp["path"]) else b""
        check("文件是 gzip（前两字节 1f 8b）", raw[:2] == b"\x1f\x8b", raw[:4].hex())
        try:
            payload = json.loads(gzip.decompress(raw).decode("utf-8"))
            good = payload.get("format") == "snc-backup" and len(payload.get("boards") or []) >= 1
        except Exception as exc:
            payload, good = {}, False
            print("   解压失败:", exc)
        check("解压后是合法存档 JSON", good)
        check("压缩确实比原 JSON 小",
              len(raw) < len(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
              "%d vs %d" % (len(raw), len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))))

        print("\n== B 导入写回 ==")
        # 在存档里加一块「来自另一台电脑」的画布 + 一条技能，导入后应当出现
        payload.setdefault("boards", []).append({
            "id": "b-probe-import", "name": "另一台电脑的画布",
            "nodes": [{"id": "n-import-1", "kind": "note", "text": "继承过来的记录",
                       "x": 40, "y": 40, "w": 200, "h": 120, "status": "idle"}],
            "view": {"x": 0, "y": 0, "z": 1}
        })
        payload["skills"] = list(payload.get("skills") or []) + [
            {"id": "sk-probe", "name": "迁移技能", "prompt": "probe", "builtin": False}
        ]
        applied = page.evaluate("""(obj) => window.SNC_BACKUP.apply(obj).then(
            n => ({count: n}), e => ({count: -1, error: String(e && e.message || e)}))""",
            payload)
        check("导入返回画布数", applied.get("count", -1) >= 2, str(applied))

        after = page.evaluate("""() => window.SNC_BACKUP.gather().then(d => ({
            ids: d.boards.map(b => b.id),
            skillIds: d.skills.map(s => s.id),
            text: ((d.boards.find(b => b.id === 'b-probe-import') || {}).nodes || [])
                   .map(n => n.text)
        }))""")
        check("导入的画布已写回", "b-probe-import" in after["ids"], str(after["ids"])[:120])
        check("导入的画布内容完整",
              "继承过来的记录" in (after["text"] or []), str(after["text"]))
        check("导入的技能已写回", "sk-probe" in after["skillIds"], str(after["skillIds"])[:120])

        print("\n== C 用导出的文件反向读取 ==")
        b64 = __import__("base64").b64encode(raw).decode("ascii")
        reread = page.evaluate("""(b64) => {
            const bin = atob(b64);
            const u8 = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
            const f = new File([u8], 'x.sncbak', {type: 'application/gzip'});
            return window.SNC_BACKUP.readFile(f).then(
                o => ({format: o.format, boards: (o.boards || []).length}),
                e => ({error: String(e && e.message || e)}));
        }""", b64)
        check("readFile 能解析导出的备份",
              reread.get("format") == "snc-backup" and reread.get("boards", 0) >= 1, str(reread))

        bad = page.evaluate("""() => {
            const f = new File([new TextEncoder().encode('{"a":1}')], 'bad.sncbak');
            return window.SNC_BACKUP.readFile(f).then(
                () => 'no-error', e => String(e && e.message || e));
        }""")
        check("坏文件给出可读错误", "不是无限画布的存档文件" in bad, bad)

        print("\n== D 关于面板 ==")
        for bid, label in [("sncAboutBackup", "导出存档"), ("sncAboutRestore", "导入存档"),
                           ("sncAboutCheckUpdate", "检查更新"), ("sncAboutUpgrade", "下载并升级")]:
            exists = page.evaluate("(id) => { const e = document.getElementById(id); "
                                   "return !!e && e.textContent.trim(); }", bid)
            check("按钮存在：" + label, exists == label, str(exists))
        hidden = page.evaluate("() => document.getElementById('sncAboutUpgrade').hidden")
        check("升级按钮默认隐藏", hidden is True, str(hidden))

        check("全程没有 JS 报错", not errs, " | ".join(errs[:3]))
        br.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    shutil.rmtree(TMP, ignore_errors=True)

print("\n----------------------------------------------")
print("PASS %d  FAIL %d" % (PASS, FAIL))
for n, x in FAILS:
    print("  -", n, "->", x)
sys.exit(1 if FAIL else 0)
