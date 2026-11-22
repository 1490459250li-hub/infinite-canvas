# -*- coding: utf-8 -*-
"""第十三批（v3.7.8 / P0-②）自检：1K·1.5K 档位 + 参考图上限 10 张。

静态断言为主，不消耗出图额度、不依赖上游服务。
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "proto", "canvas.src.html")
BUILT = os.path.join(ROOT, "proto", "canvas.html")
PY = os.path.join(ROOT, "proto", "server.py")
UPD = os.path.join(ROOT, "proto", "update.json")

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


def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def main():
    s, b, p = read(SRC), read(BUILT), read(PY)
    info = json.loads(read(UPD))

    print("\n== A  版本 ==")
    # v3.8.0 起不写死版本号：只要求 server.py 与清单一致，发版不用再改测试
    check("APP_VERSION 与 update.json 一致",
          'APP_VERSION = "%s"' % info.get("latest") in p, info.get("latest"))
    check("update.json latest 是合法版本号",
          bool(info.get("latest")) and info["latest"].count(".") == 2, info.get("latest"))
    # update.json 只放最新一版的说明，本批（v3.7.8）的两项从 README 的版本摘要里查
    readme = read(os.path.join(ROOT, "README.md"))
    check("发版说明写清两项", all(k in readme for k in ("1.5K", "10 张")))

    print("\n== B  1K / 1.5K 分辨率档位 ==")
    check("后端 LONG_SIDES 放行 1536",
          "LONG_SIDES = (1024, 1536, 2048, 4096)" in p)
    check("生成条 / 编辑框都新增 1.5K 选项",
          s.count('<option value="1536">') == 2, s.count('<option value="1536">'))
    check("1.5K 标了推荐", s.count("1.5K · 推荐") >= 2)
    check("resTiers 认 Seedream 5.5 与 5.0 pro / flash",
          "/seedream-5-(5|0-(pro|flash))/" in s
          and "/seedream-5-(pro|flash)/.test(sig)" in s)
    check("5.0 档位恰好 原图/1K/1.5K/2K",
          '{v:0, label:"原图"}, {v:1024, label:"1K"},\n'
          '              {v:1536, label:"1.5K", rec:true}, {v:2048, label:"2K"}' in s)
    check("其它模型档位未被改动",
          'if(side >= 4096) return [{v:0, label:"原图"}, {v:2048, label:"2K"}, {v:4096, label:"4K"}];' in s)
    check("工作台渲染推荐徽标", "is-rec" in s and "class=\"is-rec\"" in s
          and 'title="推荐：与 1K 同价' in s)
    check("推荐徽标有样式", ".snc-inp-chips button.is-rec::after" in s)
    check("未配置模型时也能按 value 取到档位",
          "String(value || \"\")].join(\" \")" in s)

    print("\n== B2  后端真实换算（直接调 server 模块） ==")
    sys.path.insert(0, os.path.join(ROOT, "proto"))
    import server
    pro = next(m for m in server.PROVIDER_SPECS["seedream"]["image"]
               if m["key"] == "seedream-5-pro")
    check("pixel_size 不再把 1536 静默改成 2048",
          server.pixel_size("16:9", 1536)[0] == 1536, server.pixel_size("16:9", 1536))
    check("_seedream_tier 把 1536 落到官方 1.5K",
          server._seedream_tier(pro, 1536) == "1.5K", server._seedream_tier(pro, 1536))
    check("1K / 2K 档位换算不变",
          server._seedream_tier(pro, 1024) == "1K"
          and server._seedream_tier(pro, 2048) == "2K")
    check("5.0 pro / flash 的 max_refs 都是 10",
          all(m["max_refs"] == 10 for m in server.PROVIDER_SPECS["seedream"]["image"]
              if m["key"] in ("seedream-5-pro", "seedream-5-flash")))

    print("\n== C  参考图上限 3 / 5 → 10 ==")
    check("硬上限常量 10 且挂到 window",
          "var SNC_REF_HARD_MAX = 10;" in s and "window.SNC_REF_HARD_MAX = SNC_REF_HARD_MAX;" in s)
    check("工作台 / 底部条 / 编辑框都改用硬上限",
          "var V26_INP_REF_MAX = window.SNC_REF_HARD_MAX || 10;" in s
          and "var GATT_MAX = window.SNC_REF_HARD_MAX || 10;" in s
          and "var MAX_REF = window.SNC_REF_HARD_MAX || 10;" in s)
    check("不再有写死 3 张的 refs 截断", ".slice(0, 3)" not in s)
    check("参考图角色说明按 10 张截", "urls.slice(0, window.SNC_REF_HARD_MAX || 10)" in s)
    check("按模型 max_refs 计算上限", "function refCapFor(modelValue)" in s
          and "window.SNC_REF_CAP = refCapFor" in s)
    check("工作台预留 1 张原图", "function v26RefMax()" in s and "cap - 1" in s)
    check("发请求前收口并明确提示",
          "if(body.images.length > cap)" in s and "已按顺序取前 " in s
          and "body.images = body.images.slice(0, Math.max(0, cap));" in s)
    check("图层拆分固定 1 张原图不进收口分支",
          "if(!spec.layerDecomposition && body.images.length)" in s)
    check("底部条 / 编辑框都动态算 cap",
          "function gAttCap()" in s and "function composeRefCap()" in s)
    check("编辑框空位卡最多 5 个，不撑爆面板", "var slots = Math.min(5, room);" in s)
    check("UI 文案不再写死 3 / 5 张",
          "最多 3 张" not in s and "最多 5 张" not in s)
    check("同源相对路径参考图转成 data URL",
          "var sameOrigin = false;" in s
          and "new URL(u, location.href).origin === location.origin" in s
          and "var need = !isData || W > REF_MAX_SIDE" in s)
    check("外域图不强转，避免 canvas 跨域报错",
          "if(!isData && !sameOrigin) return Promise.resolve(u);" in s)

    print("\n== D  构建产物 ==")
    # 混淆器会改局部函数名，所以这里查「挂到 window 的属性名 + 中文提示串」
    for key in ("1.5K · 推荐", "SNC_REF_HARD_MAX", "SNC_REF_CAP", "is-rec",
                "当前模型最多收 ", "已按顺序取前 ", "当前模型最多挂 "):
        check("产物含 " + key, key in b)
    md5 = hashlib.md5(open(BUILT, "rb").read()).hexdigest()
    check("canvas.html 非空", os.path.getsize(BUILT) > 400000, os.path.getsize(BUILT))
    print("  canvas.html: %d B / md5 %s" % (os.path.getsize(BUILT), md5))

    print("\n%d passed, %d failed" % (PASS, FAIL))
    if FAILS:
        for n, e in FAILS:
            print("  -", n, e)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
