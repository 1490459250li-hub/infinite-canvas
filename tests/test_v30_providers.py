# -*- coding: utf-8 -*-
"""v3.0 回归：多供应商（SenseNova / OpenAI / Google / Seedream / Qwen）。

A–F 段是纯 Python：直接调服务端适配器，校验四家的请求体形状（不联网）。
G–L 段是浏览器：设置页供应商卡片、多密钥、分流、下拉分组、分辨率档位。

跑法：PYTHONUNBUFFERED=1 python tests/test_v30_providers.py
      SNC_BASE=http://127.0.0.1:8400/canvas.html python tests/test_v30_providers.py
"""
import base64, json, os, struct, sys, tempfile, zlib

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


# ---------------------------------------------------------------- 公共夹具
def png(w, h):
    rows = []
    seed = 7
    for _y in range(h):
        row = bytearray(b"\x00")
        for _x in range(w):
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            v = 30 + (seed >> 16) % 200
            row += bytes((v, (v * 5) % 256, (v * 11) % 256))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(t, d):
        return (struct.pack(">I", len(d)) + t + d +
                struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


PICB = png(320, 240)
PIC = "data:image/png;base64," + base64.b64encode(PICB).decode("ascii")
MASK = PIC

PROTO = os.environ.get("SNC_PROTO", r"E:\无限画布\proto")
sys.path.insert(0, PROTO)
import server  # noqa: E402

# 配置写到临时目录，绝不碰开发用的 .env
TMP = tempfile.mkdtemp(prefix="snc-v30-")
server._ENV_PATH = os.path.join(TMP, ".env")


class FakeResp(object):
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = text or json.dumps(self._payload)

    def json(self):
        return self._payload


CAPTURED = []


def fake_post(url, **kw):
    CAPTURED.append({"method": "POST", "url": url, **kw})
    b64 = base64.b64encode(PICB).decode("ascii")
    return FakeResp(200, {"data": [{"b64_json": b64}],
                          "usage": {"images": 1},
                          "candidates": [{"content": {"parts": [
                              {"inline_data": {"mime_type": "image/png", "data": b64}}]}}],
                          "output": {"choices": [{"message": {"content": [
                              {"image": "https://example.invalid/x.png"}]}}]}})


def fake_get(url, **kw):
    CAPTURED.append({"method": "GET", "url": url, **kw})
    return FakeResp(200, {"data": [{"id": "m1"}, {"id": "m2"}],
                          "models": [{"name": "models/gemini-2.5-flash-image"}]})


server.requests.post = fake_post
server.requests.get = fake_get


def last():
    """把 json= 和 data=json.dumps() 两种写法归一成 body。"""
    if not CAPTURED:
        return {}
    item = dict(CAPTURED[-1])
    body = item.get("json")
    if body is None and "data" in item:
        try:
            body = json.loads(item["data"])
        except Exception:
            body = {}
    item["body"] = body or {}
    return item


def entry_of(pid, key):
    return server.model_entry(pid, key)


REQ = {"prompt": "a red cube", "images": [], "ratio": "1:1", "res": 1024,
       "fmt": "png", "mask": "", "extend": True, "size_mode": ""}


def req(**kw):
    out = dict(REQ)
    out.update(kw)
    return out


# ---------------------------------------------------------------- A 注册表
print("\n== A 注册表 ==")
check("六家供应商按顺序注册",
      list(server.PROVIDER_ORDER) == ["sensenova", "openai", "google", "seedream",
                                      "qwen", "minimax"],
      list(server.PROVIDER_ORDER))
for pid, expect in (("sensenova", 2), ("openai", 3), ("google", 3),
                    ("seedream", 4), ("qwen", 2), ("minimax", 2)):
    check("%s 有 %d 个图片模型" % (pid, expect),
          len(server.PROVIDER_SPECS[pid]["image"]) == expect,
          len(server.PROVIDER_SPECS[pid]["image"]))
check("Seedream 5.0 Pro 挂 Agent Plan 通道",
      entry_of("seedream", "seedream-5-pro").get("plan_base", "").endswith("/api/plan/v3"),
      entry_of("seedream", "seedream-5-pro").get("plan_base"))
check("Seedream 5.0 档位只到 2K（官方只给 1K/1.5K/2K）",
      entry_of("seedream", "seedream-5-pro")["max_side"] == 2048,
      entry_of("seedream", "seedream-5-pro")["max_side"])

# v3.4：对照官方文档核过的四条硬约束
keys_seed = [m["key"] for m in server.PROVIDER_SPECS["seedream"]["image"]]
check("3.0 已下线，注册表里不能再出现",
      "seedream-3" not in keys_seed and
      not any("seedream-3" in m["id"] for m in server.PROVIDER_SPECS["seedream"]["image"]),
      keys_seed)
check("4.0 用未下线的主线快照 20260415",
      entry_of("seedream", "seedream-4")["id"] == "doubao-seedream-4-0-20260415",
      entry_of("seedream", "seedream-4")["id"])
check("5.0 声明总像素 921600–4624220（官方 1280x720 ~ 2048²×1.1025）",
      (entry_of("seedream", "seedream-5-pro")["pixel_min"],
       entry_of("seedream", "seedream-5-pro")["pixel_max"]) == (921600, 4624220),
      (entry_of("seedream", "seedream-5-pro")["pixel_min"],
       entry_of("seedream", "seedream-5-pro")["pixel_max"]))
check("5.0 支持 output_format（png/jpeg），4.0 不支持",
      entry_of("seedream", "seedream-5-pro").get("out_fmt") is True and
      entry_of("seedream", "seedream-4").get("out_fmt") is False)
check("Seedream 的文本模型不在下线名单（1.6 已于 2026-09-21 下线）",
      all(m["id"] != "doubao-seed-1-6-250615"
          for m in server.PROVIDER_SPECS["seedream"]["text"]),
      [m["id"] for m in server.PROVIDER_SPECS["seedream"]["text"]])
check("只有 OpenAI 标了真蒙版能力",
      [p for p in server.PROVIDER_ORDER
       if any(m["mask"] for m in server.PROVIDER_SPECS[p]["image"])] == ["openai"])
check("Seedream 4.0 允许 10 张参考图",
      entry_of("seedream", "seedream-4")["max_refs"] == 10)
check("OpenAI 最长边 1536（决定前端 1K/1.5K 档）",
      entry_of("openai", "gpt-image-1")["max_side"] == 1536)
check("Qwen-Image 最长边 1440",
      entry_of("qwen", "qwen-image")["max_side"] == 1440)
check("模型别名 flash 归一为 fast",
      entry_of("sensenova", "flash")["key"] == "fast")

# ---------------------------------------------------------------- B 多密钥
print("\n== B 多密钥 ==")
act, first = server.add_key("openai", "sk-aaaaaaaaaaaaaaaaaaaaaaaa", "主号")
check("第一把钥匙写入 slot 1", act == "added" and first["slot"] == 1, (act, first))
act2, second = server.add_key("openai", "sk-bbbbbbbbbbbbbbbbbbbbbbbb", "备用")
check("第二把钥匙写入 slot 2", act2 == "added" and second["slot"] == 2, (act2, second))
act3, again = server.add_key("openai", "sk-bbbbbbbbbbbbbbbbbbbbbbbb", "备用账号")
check("重复添加同一把只更新标签",
      act3 == "updated" and again["slot"] == 2, (act3, again))
keys = server.load_keys("openai")
check("读到 2 把钥匙", len(keys) == 2, len(keys))
check("标签按顺序保存", [k["label"] for k in keys] == ["主号", "备用账号"],
      [k["label"] for k in keys])
check("打码不泄露明文",
      all("…" in k["mask"] and k["mask"] != k["key"] for k in keys))
for i in range(3, server.KEY_SLOTS + 1):
    server.add_key("openai", "sk-fill-%d-aaaaaaaaaaaaaaaaaa" % i)
act4, _ = server.add_key("openai", "sk-overflow-aaaaaaaaaaaaaaa")
check("超过 %d 把拒绝添加" % server.KEY_SLOTS, act4 == "full", act4)
check("删除一把后剩 %d 把" % (server.KEY_SLOTS - 1),
      server.drop_key("openai", "openai-2") and
      len(server.load_keys("openai")) == server.KEY_SLOTS - 1)
state = server.provider_state("openai")
check("provider_state 不带明文", "key" not in json.dumps(state["keys"]))
check("provider_state 标了已配置", state["configured"] is True)

# ---------------------------------------------------------------- C 分流
print("\n== C 任务分流 ==")
routes = server.save_routes({"text2img": "google:nano-banana",
                             "inpaint": "openai:gpt-image-1",
                             "polish": "seedream:doubao-seed-2-0-lite-260428"})
# v3.7.2：旧模型名（nano-banana / gpt-image-1）写入分流时会被规范化到当前档位，
# 老工程升级后不会因为「模型不存在」直接报错
check("旧模型名被规范化到当前档位",
      routes == {"text2img": "google:nano-banana-2",
                 "inpaint": "openai:gpt-image-2.6-sunburst",
                 "polish": "seedream:doubao-seed-2-0-lite-260428"}, routes)
check("读回来一致", server.load_routes() == routes, server.load_routes())
pid, entry, err = server.pick_target({"task": "text2img"})
check("分流生效：文生图走 Google",
      pid == "google" and entry["key"] == "nano-banana-2", (pid, entry.get("key")))
pid2, entry2, _ = server.pick_target({"task": "inpaint"})
check("分流生效：局部重绘走 OpenAI",
      pid2 == "openai" and entry2["key"] == "gpt-image-2.6-sunburst",
      (pid2, entry2.get("key")))
pid3, entry3, _ = server.pick_target({"provider": "qwen", "model": "qwen-image-edit"})
check("请求里显式 provider 覆盖分流",
      pid3 == "qwen" and entry3["key"] == "qwen-image-edit", (pid3, entry3.get("key")))
_, _, err = server.pick_target({"provider": "sensenova", "model": "gpt-image-1"})
check("跨家模型名被拒并给出可用清单",
      err and err[0] == "model" and "fast" in err[1], err)
bad = server.save_routes({"text2img": "nope:xx", "inpaint": "", "polish": ""})
check("非法供应商回退默认", bad["text2img"] == server.DEFAULT_ROUTES["text2img"], bad)

# ---------------------------------------------------------------- D OpenAI
print("\n== D OpenAI 请求体 ==")
CAPTURED.clear()
r = server.render_openai("sk-test", entry_of("openai", "gpt-image-1"), req(ratio="3:2"))
check("文生图走 /images/generations", last()["url"].endswith("/images/generations"), last().get("url"))
check("3:2 映射成 1536x1024", last()["body"]["size"] == "1536x1024", last()["body"].get("size"))
check("gpt-image-1 带 output_format", last()["body"].get("output_format") == "png", last()["body"])
check("返回 b64 被正确解析", r["ok"] and len(r["b64"]) > 100, r.get("code"))
CAPTURED.clear()
r = server.render_openai("sk-test", entry_of("openai", "gpt-image-1"),
                         req(images=[PIC], ratio="auto", size_mode="auto"))
body = last()
check("有参考图走 /images/edits（multipart）", body["url"].endswith("/images/edits"))
check("multipart 里带 image[]", any(f[0] == "image[]" for f in body.get("files") or []),
      [f[0] for f in body.get("files") or []])
check("auto 尺寸下发 auto", body["data"]["size"] == "auto", body["data"]["size"])
CAPTURED.clear()
r = server.render_openai("sk-test", entry_of("openai", "gpt-image-1"),
                         req(images=[PIC], mask=MASK, ratio="1:1"))
body = last()
names = [f[0] for f in body.get("files") or []]
check("蒙版作为 mask 字段上传", "mask" in names, names)
check("蒙版请求同时只发一张原图", names.count("image[]") == 1, names)

# ---------------------------------------------------------------- E Google
print("\n== E Google 请求体 ==")
CAPTURED.clear()
r = server.render_google("AIza-test", entry_of("google", "nano-banana"),
                         req(images=[PIC], ratio="16:9"))
body = last()
check("走 generateContent 端点",
      ":generateContent" in body["url"] and "gemini-3.1-flash-image" in body["url"],
      body["url"])
check("密钥走 x-goog-api-key 头", body["headers"].get("x-goog-api-key") == "AIza-test")
parts = body["body"]["contents"][0]["parts"]
check("parts = 提示词 + 参考图", len(parts) == 2 and parts[0].get("text"), len(parts))
check("参考图放 inline_data", "inline_data" in parts[1], list(parts[1]))
check("声明要 IMAGE 模态",
      body["body"]["generationConfig"]["responseModalities"] == ["TEXT", "IMAGE"])
check("16:9 作为 aspectRatio 下发",
      body["body"]["generationConfig"]["imageConfig"]["aspectRatio"] == "16:9")
check("解析出图片", r["ok"] and r["b64"], r.get("code"))
CAPTURED.clear()
server.render_google("AIza-test", entry_of("google", "nano-banana"),
                     req(images=[PIC], mask=MASK, ratio="1:1"))
parts = last()["body"]["contents"][0]["parts"]
check("蒙版供应商追加蒙版说明与图片", len(parts) == 4, len(parts))

# ---------------------------------------------------------------- F Seedream / Qwen
print("\n== F Seedream / Qwen 请求体 ==")
CAPTURED.clear()
r = server.render_seedream("ark-test", entry_of("seedream", "seedream-4"), req(ratio="16:9", res=2048))
body = last()
check("Seedream 走方舟 /images/generations",
      body["url"] == "https://ark.cn-beijing.volces.com/api/v3/images/generations", body["url"])
size = body["body"]["size"]
check("Seedream 用精确宽高", "x" in size, size)
w, h = [int(x) for x in size.split("x")]
check("尺寸落在官方总像素区间（不是单边 1024–4096）", 921600 <= w * h <= 16777216, size)
check("要求返回 b64", body["body"]["response_format"] == "b64_json")
check("4.0 不下发 output_format（官方只给 5.0 系列）",
      "output_format" not in body["body"], list(body["body"].keys()))
CAPTURED.clear()
server.render_seedream("ark-test", entry_of("seedream", "seedream-4"), req(images=[PIC, PIC]))
check("多图以数组传给 image 字段",
      isinstance(last()["body"].get("image"), list) and len(last()["body"]["image"]) == 2,
      type(last()["body"].get("image")).__name__)
_txtonly = dict(entry_of("seedream", "seedream-4"), max_refs=0)
r = server.render_seedream("ark-test", _txtonly, req(images=[PIC]))
check("max_refs=0 的模型吃参考图时提前报错", (not r["ok"]) and r["code"] == "model", r)

# 21:9 在 2K 档以前会被误判成非法尺寸而退回 "2K" token，比例直接丢了
CAPTURED.clear()
server.render_seedream("ark-test", entry_of("seedream", "seedream-5-pro"),
                       req(ratio="21:9", res=2048))
s219 = last()["body"]["size"]
w9, h9 = [int(x) for x in s219.split("x")]
check("21:9 保持精确比例，不退回 token",
      "x" in s219 and abs(w9 / float(h9) - 21 / 9.0) < 0.2, s219)
check("21:9 像素仍在 5.0 的合法区间", 921600 <= w9 * h9 <= 4624220, s219)

# 1K 档 16:9 算出来只有 589824 像素，低于官方下限 921600，必须自动放大
CAPTURED.clear()
server.render_seedream("ark-test", entry_of("seedream", "seedream-5-pro"),
                       req(ratio="16:9", res=1024))
s1k = last()["body"]["size"]
w1, h1 = [int(x) for x in s1k.split("x")]
check("低于总像素下限时自动放大到合法区间", w1 * h1 >= 921600, s1k)

# v3.4：套餐通道先打官方 Model ID（官方确认套餐入口接受带日期 ID），
# 并显式下发 output_format —— 不传的话 5.0 永远只给 jpeg。
CAPTURED.clear()
r5 = server.render_seedream("ark-test", entry_of("seedream", "seedream-5-pro"),
                            req(ratio="16:9", res=2048, fmt="png"))
b5 = last()
check("Seedream 5.0 走 Agent Plan 通道",
      b5["url"] == "https://ark.cn-beijing.volces.com/api/plan/v3/images/generations",
      b5["url"])
check("套餐通道先用官方 Model ID",
      b5["body"]["model"] == "doubao-seedream-5-0-pro-260628", b5["body"]["model"])
check("5.0 显式下发 output_format=png（官方默认 jpeg）",
      b5["body"].get("output_format") == "png", b5["body"].get("output_format"))
check("Seedream 5.0 解析出图片", r5["ok"] and len(r5["b64"]) > 100, r5.get("code"))
check("返回的 format 以数据本身为准", r5.get("format") == "png", r5.get("format"))

# 按量 key 撞上套餐入口会 401。v3.3 之前 401 不在可重试名单里，等于 5.0 对按量用户完全不可用
_orig_post = server.requests.post
TRIES = []


def fake_plan_401(url, **kw):
    TRIES.append({"url": url, "data": kw.get("data") or ""})
    if "/api/plan/" in url:
        return FakeResp(401, {"error": {"code": "AuthenticationError",
                                        "message": "The API key is not valid for this plan"}})
    b64 = base64.b64encode(PICB).decode("ascii")
    return FakeResp(200, {"data": [{"b64_json": b64, "size": "2048x1152"}]})


server.requests.post = fake_plan_401
r6 = server.render_seedream("ark-test", entry_of("seedream", "seedream-5-flash"),
                            req(ratio="16:9", res=2048))
server.requests.post = _orig_post
check("套餐入口 401 时自动换按量入口", r6["ok"] and len(TRIES) == 2, len(TRIES))
check("第二次打的是 /api/v3",
      len(TRIES) == 2 and TRIES[1]["url"].endswith("/api/v3/images/generations"),
      [t["url"] for t in TRIES])
check("换通道后模型名还是官方 ID",
      len(TRIES) == 2 and "doubao-seedream-5-0-flash-260915" in TRIES[1]["data"],
      TRIES[1]["data"][:120] if len(TRIES) > 1 else "")
check("上游回传的真实尺寸被采用",
      r6.get("sizeAsked") == "2048x1152", r6.get("sizeAsked"))


def fake_all_404(url, **kw):
    TRIES.append({"url": url, "data": kw.get("data") or ""})
    return FakeResp(404, {"error": {"message": "The model does not exist"}})


TRIES = []
server.requests.post = fake_all_404
r7 = server.render_seedream("ark-test", entry_of("seedream", "seedream-5-pro"),
                            req(ratio="1:1", res=1024))
server.requests.post = _orig_post
check("三个通道全试过才放弃", len(TRIES) == 3, len(TRIES))
check("失败时把上游原文回传",
      (not r7["ok"]) and "does not exist" in r7.get("error", ""), r7.get("error"))

CAPTURED.clear()
r = server.render_qwen("sk-test", entry_of("qwen", "qwen-image"), req(ratio="16:9", res=1024))
body = last()
check("Qwen 文生图走 OpenAI 兼容模式",
      body["url"].endswith("/compatible-mode/v1/images/generations"), body["url"])
qsize = body["body"]["size"]
check("Qwen 尺寸用 星号 分隔", "*" in qsize, qsize)
qw, qh = [int(x) for x in qsize.split("*")]
check("Qwen 每边 512–1440", 512 <= qw <= 1440 and 512 <= qh <= 1440, qsize)
CAPTURED.clear()
server.render_qwen("sk-test", entry_of("qwen", "qwen-image-edit"), req(images=[PIC]))
body = last()
check("Qwen 编辑走原生 multimodal-generation",
      "multimodal-generation" in body["url"], body["url"])
content = body["body"]["input"]["messages"][0]["content"]
check("编辑请求把图放 content 里", content and "image" in content[0], content[:1])
r = server.render_qwen("sk-test", entry_of("qwen", "qwen-image"), req(images=[PIC]))
check("qwen-image 吃参考图时提前报错", (not r["ok"]) and r["code"] == "model", r)

# ---------------------------------------------------------------- G 浏览器
print("\n== G 设置页卡片 ==")
from playwright.sync_api import sync_playwright  # noqa: E402

BASE = os.environ.get("SNC_BASE", "http://127.0.0.1:8321/canvas.html")
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "截图")
os.makedirs(SHOTS, exist_ok=True)

PROVIDERS = {
    "ok": True,
    "order": ["sensenova", "openai", "google", "seedream", "qwen", "minimax"],
    "routes": {"text2img": "sensenova:fast", "inpaint": "sensenova:fast",
               "polish": "sensenova:sensenova-6.8-flash"},
    "anyConfigured": True,
    "providers": [
        {"id": "sensenova", "label": "SenseNova", "tag": "U1.5", "hint": "商汤日日新",
         "base": "https://token.sensenova.cn/v1", "keyPrefix": "sk-", "configured": True,
         "keys": [{"id": "sensenova-1", "slot": 1, "label": "主账号", "mask": "sk-5nVI…PFVF"}],
         "image": [{"provider": "sensenova", "key": "fast", "id": "sensenova-u1.5-fast",
                    "label": "U1.5 Fast", "badge": "快", "max_side": 4096, "mask": False,
                    "max_refs": 5, "value": "sensenova:fast",
                    "ratios": ["auto", "1:1"]},
                   {"provider": "sensenova", "key": "lite", "id": "sensenova-u1.5-lite",
                    "label": "U1.5 Lite", "badge": "稳", "max_side": 4096, "mask": False,
                    "max_refs": 5, "value": "sensenova:lite",
                    "ratios": ["auto", "1:1"]}],
         "text": [{"provider": "sensenova", "id": "sensenova-6.8-flash",
                   "label": "sensenova-6.8-flash", "value": "sensenova:sensenova-6.8-flash"}],
         "defaultImage": "fast", "caps": {}},
        {"id": "openai", "label": "OpenAI", "tag": "GPT Image 2.6",
         "hint": "ChatGPT 生图 · GPT Image 2.6（2026-11 GA），支持真蒙版重绘",
         "base": "https://api.openai.com/v1", "keyPrefix": "sk-", "configured": False,
         "keys": [],
         "image": [{"provider": "openai", "key": "gpt-image-2.6-sunburst",
                    "id": "gpt-image-2.6-sunburst", "label": "GPT Image 2.6 Sunburst",
                    "badge": "新", "max_side": 1536, "mask": True, "max_refs": 5,
                    "value": "openai:gpt-image-2.6-sunburst", "ratios": ["auto", "1:1"]},
                   {"provider": "openai", "key": "gpt-image-2.6-flare",
                    "id": "gpt-image-2.6-flare", "label": "GPT Image 2.6 Flare",
                    "badge": "快", "max_side": 1536, "mask": True, "max_refs": 5,
                    "value": "openai:gpt-image-2.6-flare", "ratios": ["auto", "1:1"]},
                   {"provider": "openai", "key": "gpt-image-2", "id": "gpt-image-2",
                    "label": "GPT Image 2", "badge": "稳", "max_side": 1536, "mask": True,
                    "max_refs": 5, "value": "openai:gpt-image-2", "ratios": ["auto", "1:1"]}],
         "text": [{"provider": "openai", "id": "gpt-4.1-mini", "label": "GPT-4.1 mini",
                   "value": "openai:gpt-4.1-mini"}],
         "defaultImage": "gpt-image-2.6-sunburst", "caps": {}},
        {"id": "google", "label": "Google", "tag": "Nano Banana",
         "hint": "Nano Banana Pro / 2 / 2 Lite · 最多 14 张参考图，支持到 4K",
         "base": "https://generativelanguage.googleapis.com/v1beta", "keyPrefix": "",
         "configured": True,
         "keys": [{"id": "google-1", "slot": 1, "label": "主号", "mask": "AIzaFA…3456"},
                  {"id": "google-2", "slot": 2, "label": "备用", "mask": "AIzaFB…7890"}],
         "image": [{"provider": "google", "key": "nano-banana-pro", "id": "gemini-3-pro-image",
                    "label": "Nano Banana Pro", "badge": "4K", "max_side": 4096, "mask": False,
                    "max_refs": 14, "value": "google:nano-banana-pro", "ratios": ["auto", "16:9"]},
                   {"provider": "google", "key": "nano-banana-2", "id": "gemini-3.1-flash-image",
                    "label": "Nano Banana 2", "badge": "快", "max_side": 4096, "mask": False,
                    "max_refs": 14, "value": "google:nano-banana-2", "ratios": ["auto", "16:9"]},
                   {"provider": "google", "key": "nano-banana-2-lite",
                    "id": "gemini-3.1-flash-lite-image", "label": "Nano Banana 2 Lite",
                    "badge": "1K", "max_side": 1024, "mask": False, "max_refs": 1,
                    "value": "google:nano-banana-2-lite", "ratios": ["auto", "1:1"]}],
         "text": [{"provider": "google", "id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash",
                   "value": "google:gemini-2.5-flash"}],
         "defaultImage": "nano-banana-pro", "caps": {}},
        {"id": "seedream", "label": "Seedream", "tag": "火山方舟", "hint": "字节跳動 Seedream",
         "base": "https://ark.cn-beijing.volces.com/api/v3", "keyPrefix": "", "configured": False,
         "keys": [],
         "image": [{"provider": "seedream", "key": "seedream-4", "id": "doubao-seedream-4-0-250828",
                    "label": "Seedream 4.0", "badge": "10 图", "max_side": 4096, "mask": False,
                    "max_refs": 10, "value": "seedream:seedream-4", "ratios": ["auto", "1:1"]}],
         "text": [], "defaultImage": "seedream-4", "caps": {}},
        {"id": "qwen", "label": "Qwen-Image", "tag": "通义千问", "hint": "阿里云百炼",
         "base": "https://dashscope.aliyuncs.com/compatible-mode/v1", "keyPrefix": "sk-",
         "configured": False, "keys": [],
         "image": [{"provider": "qwen", "key": "qwen-image", "id": "qwen-image",
                    "label": "Qwen-Image", "badge": "文生图", "max_side": 1440, "mask": False,
                    "max_refs": 0, "value": "qwen:qwen-image", "ratios": ["auto", "1:1"]}],
         "text": [], "defaultImage": "qwen-image", "caps": {}},
        {"id": "minimax", "label": "MiniMax", "tag": "H3",
         "hint": "MiniMax H3-Image · 10 秒出 4K · 单次最多 16 张参考图；"
                 "国内 api.minimaxi.com，海外 api.minimax.io",
         "base": "https://api.minimaxi.com/v1", "keyPrefix": "sk-", "configured": False,
         "keys": [],
         "image": [{"provider": "minimax", "key": "h3-image", "id": "MiniMax-H3-Image",
                    "label": "H3-Image", "badge": "4K", "max_side": 4096, "mask": False,
                    "max_refs": 16, "value": "minimax:h3-image", "ratios": ["auto", "1:1"]},
                   {"provider": "minimax", "key": "h3-image-fast",
                    "id": "MiniMax-H3-Image-Highspeed", "label": "H3-Image Highspeed",
                    "badge": "快", "max_side": 4096, "mask": False, "max_refs": 16,
                    "value": "minimax:h3-image-fast", "ratios": ["auto", "1:1"]}],
         "text": [{"provider": "minimax", "id": "MiniMax-M3", "label": "MiniMax-M3",
                   "value": "minimax:MiniMax-M3"}],
         "defaultImage": "h3-image", "caps": {}},
    ],
}

bodies = []
errs = []


def jstub(payload):
    def fn(route):
        try:
            bodies.append(json.loads(route.request.post_data or "{}"))
        except Exception:
            bodies.append({})
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(payload))
    return fn


with sync_playwright() as p:
    br = p.chromium.launch(channel="msedge")
    ctx = br.new_context(viewport={"width": 1560, "height": 940})
    ctx.add_init_script("try{localStorage.setItem('snc.eula.v1','1')}catch(e){}")
    page = ctx.new_page()
    page.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
    page.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" else None)

    page.route("**/api/providers", jstub(PROVIDERS))
    page.route("**/api/health", jstub({
        "ok": True, "keyPresent": True, "key": "sk-5nVI…PFVF",
        "providersReady": ["sensenova", "google"],
        "providers": PROVIDERS["providers"],
        "routes": PROVIDERS["routes"], "models": [], "imageModels": [], "textModels": []}))
    page.route("**/api/providers/key", jstub({"ok": True, "action": "added", "provider": "openai",
                                             "warn": "", "key": {"id": "openai-1", "label": "主号",
                                                                 "mask": "sk-test…abcd"}}))
    page.route("**/api/providers/key/delete", jstub({"ok": True, "provider": "google", "state": {}}))
    page.route("**/api/providers/test", jstub({"ok": True, "models": ["m1", "m2"],
                                              "keys": [{"id": "openai-1", "ok": True, "mask": "x"}]}))
    page.route("**/api/providers/route", jstub({"ok": True, "routes": {
        "text2img": "google:nano-banana", "inpaint": "sensenova:fast",
        "polish": "sensenova:sensenova-6.8-flash"}}))
    page.route("**/api/generate", jstub({"ok": True, "b64": base64.b64encode(PICB).decode("ascii"),
                                        "size": "320x240", "format": "png",
                                        "model": "gemini-2.5-flash-image", "provider": "google",
                                        "latencyMs": 100}))

    page.goto(BASE, wait_until="load")
    page.wait_for_selector(".snc-node")
    page.wait_for_timeout(600)
    page.click(".snc-doc-foot [data-set]")
    page.wait_for_timeout(500)
    page.click('#sncSetNav button[data-pane="model"]')
    page.wait_for_timeout(900)

    names = page.locator("#sncProvList .snc-prov-name").all_inner_texts()
    check("卡片按注册表顺序渲染六家",
          names == ["SenseNova", "OpenAI", "Google", "Seedream", "Qwen-Image", "MiniMax"],
          names)
    states = page.locator("#sncProvList .snc-prov-state").all_inner_texts()
    check("已连接的显示把数", states[0] == "已连接 · 1 把" and states[2] == "已连接 · 2 把", states)
    check("未配置的标未配置", states[1] == "未配置" and states[3] == "未配置", states)
    check("MiniMax 也在列表里且标未配置", len(states) == 6 and states[5] == "未配置", states)
    check("已连接卡片高亮", page.evaluate(
        """() => document.querySelector('.snc-prov[data-pid="sensenova"]').dataset.on === "1" """))
    check("Google 卡片两把钥匙两行",
          page.locator('.snc-prov[data-pid="google"] .snc-prov-key').count() == 2)
    check("卡片里有添加密钥的输入框",
          page.locator('.snc-prov[data-pid="openai"] input[data-role="key"]').count() == 1)
    check("顶部汇总 2 / 6 已连接",
          "2 / 6" in page.inner_text("#sncProvCount"), page.inner_text("#sncProvCount"))

    # 出图下拉只列已配置的两家
    gvals = page.evaluate("() => Array.from(document.querySelectorAll('#sncGModel option')).map(o => o.value)")
    ggroups = page.evaluate("() => Array.from(document.querySelectorAll('#sncGModel optgroup')).map(o => o.label)")
    check("出图下拉按供应商分组", ggroups == ["SenseNova", "Google"], ggroups)
    check("出图下拉只列已配置的两家五档",
          gvals == ["sensenova:fast", "sensenova:lite", "google:nano-banana-pro",
                    "google:nano-banana-2", "google:nano-banana-2-lite"], gvals)
    check("未配置的供应商不出现在出图下拉",
          all("openai" not in (v or "") for v in gvals), gvals)

    # 分流下拉列全六家
    ropts = page.evaluate("() => Array.from(document.querySelectorAll('#sncRouteImg option')).map(o => o.value)")
    check("分流下拉包含全部图片模型（含未配置，6 家共 12 个）", len(ropts) == 12, len(ropts))
    check("分流下拉里有 MiniMax 两档",
          "minimax:h3-image" in ropts and "minimax:h3-image-fast" in ropts, ropts)
    check("分流当前值来自服务端",
          page.evaluate("() => document.getElementById('sncRouteImg').value") == "sensenova:fast")

    # 加钥匙
    bodies.clear()
    page.fill('.snc-prov[data-pid="openai"] input[data-role="key"]', "sk-newkey-1234567890abcdef")
    page.fill('.snc-prov[data-pid="openai"] input[data-role="label"]', "测试号")
    page.click('.snc-prov[data-pid="openai"] button[data-act="add"]')
    page.wait_for_timeout(600)
    add_body = [b for b in bodies if b.get("key")]
    check("添加密钥打到接口", bool(add_body), bodies)
    if add_body:
        check("请求带 provider", add_body[0].get("provider") == "openai", add_body[0])
        check("请求带备注", add_body[0].get("label") == "测试号", add_body[0])
    check("添加后自动验证一次", any(b == {} for b in bodies), bodies)
    key_view = page.evaluate("""() => {
        const e = document.querySelector('.snc-prov[data-pid="openai"] input[data-role="key"]');
        return e ? {value: e.value, masked: e.dataset.masked || '', type: e.type,
                    readonly: e.hasAttribute('readonly')} : null;
    }""")
    check("添加后输入框留脱敏预览（前4 + 掩码 + 后4）",
          key_view and key_view["value"] == "sk-n••••••••cdef", key_view)
    check("预览框只读、非 password、带掩码标记",
          key_view and key_view["masked"] == "1" and key_view["type"] == "text"
          and key_view["readonly"], key_view)
    page.screenshot(path=os.path.join(SHOTS, "v30-设置-供应商卡片.png"))

    # 删钥匙
    bodies.clear()
    page.click('.snc-prov[data-pid="google"] .snc-prov-key button[data-act="del"]')
    page.wait_for_timeout(400)
    del_body = [b for b in bodies if b.get("keyId")]
    check("删除密钥打到接口", bool(del_body), bodies)
    if del_body:
        check("删除请求带 provider 与 keyId",
              del_body[0].get("provider") == "google" and del_body[0].get("keyId") == "google-1",
              del_body[0])

    # 保存分流
    bodies.clear()
    page.select_option("#sncRouteImg", "google:nano-banana-2")
    page.click("#sncSetSave")
    page.wait_for_timeout(500)
    route_body = [b for b in bodies if b.get("routes")]
    check("保存分流打到接口", bool(route_body), bodies)
    if route_body:
        check("分流里文生图改成 Google",
              route_body[0]["routes"].get("text2img") == "google:nano-banana-2", route_body[0])
    check("状态条提示已保存", "分流已保存" in page.inner_text("#sncSetStatus"),
          page.inner_text("#sncSetStatus"))

    # 分辨率档位
    tiers = page.evaluate("""() => ({
        sv: window.SNC_RES_TIERS('sensenova:fast').map(t => t.label),
        gg: window.SNC_RES_TIERS('google:nano-banana-pro').map(t => t.label),
        gl: window.SNC_RES_TIERS('google:nano-banana-2-lite').map(t => t.label),
        oa: window.SNC_RES_TIERS('openai:gpt-image-2.6-sunburst').map(t => t.label),
        mm: window.SNC_RES_TIERS('minimax:h3-image').map(t => t.label),
        qw: window.SNC_RES_TIERS('qwen:qwen-image').map(t => t.label),
        old: window.SNC_RES_TIERS('fast').map(t => t.label)
    })""")
    check("4K 模型给 原图/2K/4K", tiers["sv"] == ["原图", "2K", "4K"], tiers["sv"])
    check("Google Pro 同 4K 档", tiers["gg"] == ["原图", "2K", "4K"], tiers["gg"])
    check("Google Lite 只给两档", tiers["gl"] == ["原图", "1K"], tiers["gl"])
    check("MiniMax H3 也是 4K 档", tiers["mm"] == ["原图", "2K", "4K"], tiers["mm"])
    check("OpenAI 1536 给 原图/1K/1.5K", tiers["oa"] == ["原图", "1K", "1.5K"], tiers["oa"])
    check("Qwen 1440 给 原图/1K/1.4K",
          tiers["qw"] == ["原图", "1K", "1.4K"], tiers["qw"])
    check("老画布纯 key 也能取档位", tiers["old"] == ["原图", "2K", "4K"], tiers["old"])

    # 生成条把 provider 一起下发
    page.click("#sncSetClose")
    page.wait_for_timeout(300)
    bodies.clear()
    page.fill("#sncInput", "一张测试用的红方块")
    page.click("#sncSend")
    page.wait_for_timeout(2600)
    gen = [b for b in bodies if b.get("prompt")]
    check("生成请求打到接口", bool(gen), len(bodies))
    if gen:
        check("请求按 model 值带上 provider",
              gen[0].get("provider") == "sensenova" and gen[0].get("model") == "fast",
              {k: gen[0].get(k) for k in ("provider", "model")})
        check("请求带 task=text2img", gen[0].get("task") == "text2img", gen[0].get("task"))

    check("没有 JS 运行错误", not errs, errs[:3])

    ctx.close()
    br.close()

print("\n%d passed, %d failed" % (PASS, FAIL))
if FAILS:
    print("失败项：")
    for n, e in FAILS:
        print(" -", n, "->", e)
sys.exit(1 if FAIL else 0)
