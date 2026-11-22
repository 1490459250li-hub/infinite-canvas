# -*- coding: utf-8 -*-
"""v3.7.9 回归：接入 Seedream 5.5（doubao-seedream-5-5-261028）。

A 段查模型表与下发能力；B 段用 mock 校验生成请求（RGBA / output_format）；
C 段校验图层拆分的 5.5 扩展参数与 OCR 解析；
D 段查前端接线（档位、坐标编辑、背景选择器、分层导出）。
全部离线，不打真实接口。

跑法：python tests/probe_batch14.py
"""
import base64
import json
import os
import struct
import sys
import tempfile
import zlib

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


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROTO = os.environ.get("SNC_PROTO", os.path.join(ROOT, "proto"))
sys.path.insert(0, PROTO)
import server  # noqa: E402

SRC = open(os.path.join(PROTO, "canvas.src.html"), encoding="utf-8").read()


def png(w, h):
    rows = []
    for _y in range(h):
        rows.append(b"\x00" + bytes([200, 120, 90] * w))
    raw = b"".join(rows)

    def chunk(t, d):
        return (struct.pack(">I", len(d)) + t + d +
                struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


PICB = png(64, 64)
PIC = "data:image/png;base64," + base64.b64encode(PICB).decode("ascii")

TMP = tempfile.mkdtemp(prefix="snc-v379-")
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
    CAPTURED.append({"url": url, **kw})
    return FakeResp(200, {"data": [{"b64_json": base64.b64encode(PICB).decode("ascii"),
                                   "size": "2048x1152"}], "usage": {"images": 1}})


def last():
    """把 data=json.dumps() 归一成 body（渲染层都是这么发的）。"""
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


server.requests.post = fake_post


def entry(key):
    for m in server.provider_spec("seedream")["image"]:
        if m["key"] == key:
            return m
    return {}


def req(**kw):
    base = {"prompt": "测试", "images": [], "ratio": "16:9", "res": 2048,
            "fmt": "png", "mask": "", "extend": True, "size_mode": ""}
    base.update(kw)
    return base


print("\n== A  模型表与能力下发 ==")
e55 = entry("seedream-5-5")
check("5.5 已进 Seedream 模型表", bool(e55), list(entry(k) for k in ()))
check("Model ID = doubao-seedream-5-5-261028",
      e55.get("id") == "doubao-seedream-5-5-261028", e55.get("id"))
check("参考图上限 10 张", e55.get("max_refs") == 10, e55.get("max_refs"))
check("档位 1K / 1.5K / 2K，最长边 2048",
      tuple(e55.get("size_tiers") or ()) == ("1K", "1.5K", "2K") and e55.get("max_side") == 2048,
      (e55.get("size_tiers"), e55.get("max_side")))
check("像素区间 921600–4624220",
      (e55.get("pixel_min"), e55.get("pixel_max")) == (921600, 4624220),
      (e55.get("pixel_min"), e55.get("pixel_max")))
check("output_format 开关打开", e55.get("out_fmt") is True)
check("原生 RGBA 标记", e55.get("rgba") is True)
check("图层拆分 99 层 + OCR 标记",
      e55.get("layers_max") == 99 and e55.get("layer_ocr") is True,
      (e55.get("layers_max"), e55.get("layer_ocr")))
check("Agent Plan 通道 + 套餐写法 doubao-seedream-5.5",
      str(e55.get("plan_base") or "").endswith("/api/plan/v3") and
      e55.get("plan_id") == "doubao-seedream-5.5", e55.get("plan_id"))

payload = server.providers_payload({})
sd = [p for p in payload["providers"] if p["id"] == "seedream"][0]
row = [m for m in sd["image"] if m["key"] == "seedream-5-5"][0]
check("providers 快照带 value=seedream:seedream-5-5",
      row["value"] == "seedream:seedream-5-5", row.get("value"))
check("providers 快照带 rgba / layers_max / layer_ocr",
      row.get("rgba") is True and row.get("layers_max") == 99 and row.get("layer_ocr") is True,
      (row.get("rgba"), row.get("layers_max"), row.get("layer_ocr")))

print("\n== B  生成请求：RGBA / 输出格式 ==")
CAPTURED.clear()
server.render_seedream("ark-test", e55, req(fmt="png"))
b = last()["body"]
check("5.5 走套餐通道 + 官方 Model ID",
      last()["url"].endswith("/api/plan/v3/images/generations") and
      b["model"] == "doubao-seedream-5-5-261028", (last()["url"], b["model"]))
check("5.5 显式下发 output_format=png", b.get("output_format") == "png", b.get("output_format"))
check("默认不下发 background（等于官方 auto）", "background" not in b, list(b.keys()))

CAPTURED.clear()
server.render_seedream("ark-test", e55, req(fmt="jpeg", background="transparent"))
b = last()["body"]
check("transparent 透传 background", b.get("background") == "transparent", b.get("background"))
check("transparent 强制 output_format=png（jpeg 会 400）",
      b.get("output_format") == "png", b.get("output_format"))

CAPTURED.clear()
server.render_seedream("ark-test", e55, req(fmt="jpeg", background="opaque"))
b = last()["body"]
check("opaque 透传且保留 jpeg", b.get("background") == "opaque" and
      b.get("output_format") == "jpeg", (b.get("background"), b.get("output_format")))

CAPTURED.clear()
server.render_seedream("ark-test", entry("seedream-5-pro"), req(background="transparent"))
b = last()["body"]
check("5.0 pro 不下发 background（官方不认这个字段）",
      "background" not in b, list(b.keys()))

print("\n== C  图层拆分：5.5 扩展参数与 OCR ==")
CAPTURED.clear()
LAYERS = {"data": [
    {"b64_json": base64.b64encode(PICB).decode("ascii"), "z_index": 0, "name": "底图"},
    {"b64_json": base64.b64encode(PICB).decode("ascii"), "z_index": 1, "name": "标题",
     "bounding_box": {"absolute": [10, 20, 210, 80], "normalized": [50, 90, 980, 380]},
     "text_recognition": {"text": "THANK YOU", "lines": [
         {"bounding_box": {"absolute": [12, 24, 200, 60], "normalized": [60, 110, 940, 280]},
          "runs": [{"text": "THANK YOU",
                    "style": {"similar_font_family": "Helvetica Neue",
                              "foreground_color": "#193366", "bold": True}}]}]}},
    {"b64_json": base64.b64encode(PICB).decode("ascii"), "z_index": 2, "name": "建筑"},
]}


def fake_layers_post(url, **kw):
    CAPTURED.append({"url": url, **kw})
    return FakeResp(200, LAYERS)


server.requests.post = fake_layers_post
server._SEEDREAM_CHANNEL.clear()
r = server.split_seedream_layers("ark-test", e55,
                                 req(images=[PIC], layers=True, res=2048,
                                     layer_max=30, layer_ocr=True))
b = last()["body"]
check("5.5 图层拆分被接受", r.get("ok") is True, r.get("error"))
check("layer_decomposition=true", b.get("layer_decomposition") is True)
check("max_images 透传（2–100）",
      (b.get("layer_decomposition_options") or {}).get("max_images") == 30,
      b.get("layer_decomposition_options"))
check("text_recognition 打开",
      (b.get("layer_decomposition_options") or {}).get("text_recognition") is True)
check("size 按档位给 2K（图层拆分只认档位）", b.get("size") == "2K", b.get("size"))
check("图层拆分不下发 background", "background" not in b, list(b.keys()))
check("解析出 3 张（1 底图 + 2 层）", len(r.get("layers") or []) == 3,
      len(r.get("layers") or []))
ocr = [L for L in (r.get("layers") or []) if L.get("text_recognition")]
check("文字图层的 OCR 被解析出来",
      len(ocr) == 1 and ocr[0]["text_recognition"]["text"] == "THANK YOU",
      ocr[0].get("text_recognition") if ocr else None)
check("图层已按 z_index 排序",
      [L["z_index"] for L in (r.get("layers") or [])] == [0, 1, 2],
      [L["z_index"] for L in (r.get("layers") or [])])

CAPTURED.clear()
server._SEEDREAM_CHANNEL.clear()
r55 = server.split_seedream_layers("ark-test", entry("seedream-5-pro"),
                                   req(images=[PIC], layers=True))
b = last()["body"]
check("5.0 pro 仍然可以拆分（向下兼容）", r55.get("ok") is True, r55.get("error"))
check("5.0 不下发 layer_decomposition_options（官方不认）",
      "layer_decomposition_options" not in b, list(b.keys()))

CAPTURED.clear()
r4 = server.split_seedream_layers("ark-test", entry("seedream-4"),
                                  req(images=[PIC], layers=True))
check("4.0 被拒（code=model）", r4.get("ok") is False and r4.get("code") == "model", r4)

CAPTURED.clear()
rbad = server.split_seedream_layers("ark-test", e55, req(images=[PIC, PIC], layers=True))
check("多图请求被拒（只能 1 张原图）",
      rbad.get("ok") is False and rbad.get("code") == "image", rbad)

print("\n== D  前端接线 ==")
check("resTiers 认 5.5（1K / 1.5K 推荐 / 2K）",
      "/seedream-5-(5|0-(pro|flash))/" in SRC)
check("坐标编辑判定包含 5.5",
      "/^seedream-5-5$/" in SRC and "/seedream-5-(0-(pro|flash)|5)/" in SRC)
check("requestReal 下发 background",
      'if(spec.background && spec.background !== "auto") body.background = spec.background;' in SRC)
check("层级拆分透传 layerMax / layerOcr",
      "body.layerMax = spec.layerMax" in SRC and "body.layerOcr = true" in SRC)
check("分层导出用 5.5 + 30 张 + OCR",
      "Seedream 5.5 拆分图层" in SRC and "layerMax: 30, layerOcr: true" in SRC)
check("图层清单写入 OCR 文字与逐行样式",
      "text_recognition" in SRC and "字体 ≈ " in SRC and "颜色 " in SRC)
check("生成条与编辑框都有背景选择器",
      'id="sncGBg"' in SRC and 'id="sncBg"' in SRC and 'id="sncGBgWrap"' in SRC)
check("背景选择器按 rgba 能力显隐",
      "function bgCapFor(" in SRC and "window.SNC_SYNC_BG" in SRC and
      "row.rgba" in SRC.replace("m.rgba", "row.rgba"))
check("applyProviders 携带 rgba / layers 能力",
      "rgba:!!m.rgba, layersMax:m.layers_max || 0, layerOcr:!!m.layer_ocr" in SRC)
check("底部生成与编辑提交都传 background",
      "background: opts.background || \"auto\"" in SRC and
      "background: background});" in SRC)

print("\n----------------------------------------------")
print("PASS %d  FAIL %d" % (PASS, FAIL))
for n, x in FAILS:
    print("  -", n, "->", x)
sys.exit(1 if FAIL else 0)
