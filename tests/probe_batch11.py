# -*- coding: utf-8 -*-
"""第十一批（v3.7.6 发版）自检：API Key 确认后输入框保留「前 4 + 掩码 + 后 4」。

跑法：
    python tests/serve.py                        # 另开一个终端，端口 8321
    python tests/probe_batch11.py http://127.0.0.1:8321

所有供应商接口都走本地 stub，不会真的写 .env、不会向任何上游发请求。
"""
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8321"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = 0
FAIL = 0
MASK = "•" * 8

RAW1 = "sk-newkey-1234567890abcdef"
RAW2 = "sk-second-9876543210wxyz"


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  PASS  " + name)
    else:
        FAIL += 1
        print("  FAIL  " + name + "   -> " + repr(detail)[:400])


def provider(pid, label, configured, masks):
    return {
        "id": pid, "label": label, "tag": "T", "hint": "自检", "keyPrefix": "sk-",
        "configured": configured,
        "keys": [{"id": pid + "-" + str(i + 1), "slot": i + 1,
                  "label": "主号" if i == 0 else "备用", "mask": m}
                 for i, m in enumerate(masks)],
        "image": [{"provider": pid, "key": "m1", "id": pid + "-m1", "label": "M1",
                   "badge": "快", "max_side": 1024, "mask": False, "max_refs": 4,
                   "value": pid + ":m1", "ratios": ["auto", "1:1"]}],
        "text": [{"provider": pid, "id": pid + "-txt", "label": "TXT",
                  "value": pid + ":" + pid + "-txt"}],
        "defaultImage": "m1", "caps": {},
    }


STATE = {
    "ok": True,
    "order": ["sensenova", "google", "openai"],
    "routes": {"text2img": "sensenova:m1", "inpaint": "sensenova:m1",
               "polish": "sensenova:sensenova-txt"},
    "anyConfigured": True,
    "providers": [
        provider("sensenova", "SenseNova", True, ["sk-5nVI…PFVF"]),
        provider("google", "Google", True, ["AIzaFA…3456", "AIzaFB…7890"]),
        provider("openai", "OpenAI", False, []),
    ],
}


def providers_body():
    return json.dumps(STATE, ensure_ascii=False)


# ---------------------------------------------------------------- 服务端
def probe_server_side():
    print("== 服务端：掩码不可写入 .env ==")
    src = open(os.path.join(ROOT, "proto", "server.py"), encoding="utf-8").read()
    check("写入前拦截脱敏预览",
          'if any(ch in key for ch in "•…") or "..." in key:' in src)
    check("拦截文案可读", "这是脱敏预览，不是完整密钥" in src)

    env_path = os.path.join(ROOT, "proto", ".env")
    before = hashlib.md5(open(env_path, "rb").read()).hexdigest() if os.path.exists(env_path) else ""
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(
        BASE + "/api/providers/key",
        data=json.dumps({"provider": "openai", "key": "sk-n" + MASK + "cdef"}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with op.open(req, timeout=6) as r:
            status, body = r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        status, body = e.code, json.loads(e.read().decode())
    check("POST 掩码返回 400", status == 400, (status, body))
    check("错误提示指向「脱敏预览」",
          "脱敏" in str(body.get("error", "")), body)
    after = hashlib.md5(open(env_path, "rb").read()).hexdigest() if os.path.exists(env_path) else ""
    check("服务端 .env 一个字节没动", before == after, (before, after))


# ---------------------------------------------------------------- 浏览器
def probe_ui():
    bodies = []

    def jstub(obj):
        return lambda route: route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps(obj, ensure_ascii=False))

    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge")
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))

        def route_providers(route):
            route.fulfill(status=200, content_type="application/json",
                          body=providers_body())

        def route_add(route):
            bodies.append(json.loads(route.request.post_data or "{}"))
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": True, "action": "added",
                                           "provider": "openai", "warn": "",
                                           "key": {"id": "openai-1", "label": "主号",
                                                   "mask": "sk-new…cdef"}}))

        pg.route("**/api/providers", route_providers)
        pg.route("**/api/providers/key", route_add)
        pg.route("**/api/providers/key/delete", jstub({"ok": True}))
        pg.route("**/api/providers/test", jstub({"ok": True, "models": ["m1"], "keys": []}))
        pg.route("**/api/config/clear", jstub({"ok": True}))
        pg.route("**/api/health", jstub({"ok": True, "version": "3.7.6",
                                         "providersReady": ["sensenova"],
                                         "providers": STATE["providers"],
                                         "routes": STATE["routes"]}))
        pg.goto(BASE + "/canvas.html")
        # 只验设置面板，不依赖首屏有示例卡：测试服务会 seed，正式包是空白启动
        pg.wait_for_selector(".snc-doc-foot [data-set]")
        pg.wait_for_timeout(700)
        pg.click(".snc-doc-foot [data-set]")
        pg.click('#sncSetNav button[data-pane="model"]')
        pg.wait_for_timeout(700)

        def key_info(pid):
            return pg.evaluate("""(pid) => {
                const e = document.querySelector('.snc-prov[data-pid="'+pid+'"] input[data-role="key"]');
                if(!e) return null;
                return {value: e.value, type: e.type, masked: e.dataset.masked || '',
                        readonly: e.hasAttribute('readonly'),
                        placeholder: e.placeholder, editing: e.dataset.editing || ''};
            }""", pid)

        print("== 冷启动：已配置密钥自动显示 4…4 预览 ==")
        sn = key_info("sensenova")
        check("SenseNova 显示前 4 + 掩码 + 后 4",
              sn and sn["value"] == "sk-5" + MASK + "PFVF", sn)
        check("预览是只读文本框", sn and sn["type"] == "text"
              and sn["readonly"] and sn["masked"] == "1", sn)
        go = key_info("google")
        check("多把密钥取最后一把", go and go["value"] == "AIza" + MASK + "7890", go)
        oa = key_info("openai")
        check("未配置卡片仍是空 password 框",
              oa and oa["value"] == "" and oa["type"] == "password"
              and oa["masked"] == "", oa)

        print("== 掩码边界 ==")
        km = lambda s: pg.evaluate("(s) => window.SNC_TEST_API.keyMask(s)", s)
        check("短 Key 一位明文都不露", km("abc") == MASK, km("abc"))
        check("8–11 位退化为前 2 后 2", km("abcdefgh") == "ab" + MASK + "gh", km("abcdefgh"))
        check("正常 Key 前后各 4 位", km(RAW1) == "sk-n" + MASK + "cdef", km(RAW1))
        check("掩码长度固定，不泄露原长", len(km(RAW1)) == len(km(RAW1 * 4)), km(RAW1 * 4))

        print("== 输入 → 确认 → 脱敏留在输入框 ==")
        pg.fill('.snc-prov[data-pid="openai"] input[data-role="key"]', RAW1)
        pg.click('.snc-prov[data-pid="openai"] button[data-act="add"]')
        pg.wait_for_timeout(700)
        check("POST 里是完整原文", bool(bodies) and bodies[-1].get("key") == RAW1, bodies[-1:])
        ok1 = key_info("openai")
        check("确认后留下 4…4 预览", ok1 and ok1["value"] == "sk-n" + MASK + "cdef", ok1)
        check("预览框 readonly + data-masked",
              ok1 and ok1["masked"] == "1" and ok1["readonly"], ok1)
        check("明文已不在页面 DOM 里",
              RAW1 not in pg.evaluate("() => document.body.innerHTML"))
        check("状态刷新后预览仍在（keyPreview 回填）",
              key_info("openai") and key_info("openai")["value"] == "sk-n" + MASK + "cdef",
              key_info("openai"))
        pg.locator('.snc-prov[data-pid="openai"]').scroll_into_view_if_needed()
        pg.screenshot(path=os.path.join(ROOT, "截图", "b11-Key脱敏预览.png"))
        print("shot: b11-Key脱敏预览.png")

        print("== 脱敏值不会被当成新 Key 提交 ==")
        n_before = len(bodies)
        pg.click('.snc-prov[data-pid="openai"] button[data-act="add"]')
        pg.wait_for_timeout(350)
        check("点添加不发新请求", len(bodies) == n_before, len(bodies))
        check("状态条提示重新粘贴",
              "脱敏预览" in pg.inner_text("#sncSetStatus"), pg.inner_text("#sncSetStatus"))
        reset = key_info("openai")
        check("预览被清空、切回可输入 password",
              reset and reset["value"] == "" and reset["type"] == "password"
              and reset["masked"] == "", reset)

        print("== 点一下就能重新粘贴一把新 Key ==")
        pg.click('.snc-prov[data-pid="openai"] input[data-role="key"]')
        pg.fill('.snc-prov[data-pid="openai"] input[data-role="key"]', RAW2)
        pg.click('.snc-prov[data-pid="openai"] button[data-act="add"]')
        pg.wait_for_timeout(650)
        check("第二把 Key 完整提交", bodies[-1].get("key") == RAW2, bodies[-1])
        check("预览换成第二把的 4…4",
              key_info("openai")["value"] == "sk-s" + MASK + "wxyz", key_info("openai"))

        print("== 清除全部密钥后预览也清掉 ==")
        pg.click("#sncSetClear")
        pg.wait_for_timeout(700)
        check("清除后输入框不再留旧预览",
              key_info("openai")["value"] == "", key_info("openai"))

        check("全程无 JS 异常", not errs, errs[:3])
        b.close()


if __name__ == "__main__":
    probe_server_side()
    probe_ui()
    print("\n== 第十一批：%d 通过 / %d 失败 ==" % (PASS, FAIL))
    sys.exit(1 if FAIL else 0)
