# -*- coding: utf-8 -*-
"""第十二批（v3.7.7）自检：阶段式进度 / 分层导出 / 坐标标记 / 取消识别 / 涂抹重影。

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
    # v3.7.8 发版后版本断言跟随发版清单；这批仍检查 v3.7.7 的五项能力没被改坏
    check("APP_VERSION 与 update.json 一致",
          'APP_VERSION = "%s"' % info.get("latest") in p)
    # 版本号每次发版都会变，这里只查「两边一致」，别再把具体版本写死
    ver = info.get("latest") or ""
    check("update.json latest 是合法版本号",
          bool(ver) and ver.count(".") == 2, ver)
    # update.json 只放最新一版的说明；v3.7.7 的五项能力改从 README 的版本摘要里查
    readme = read(os.path.join(ROOT, "README.md"))
    check("发版说明含本批五项", all(k in readme
          for k in ("阶段式", "拆分图层 ZIP", "bbox", "识别", "重影")))

    print("\n== B  方案 B：阶段式真实进度 ==")
    check("阶段注册表挂在 window（跨 IIFE 可见）",
          "var SNC_PHASE = window.SNC_PHASE = {};" in s and "sncPhase(" in s
          and "window.SNC_PHASE[n.id]" in s)
    check("六个真实阶段齐备", all(k in s for k in
          ('queued:    {pct:0', 'prepared:  {pct:15', 'submitted: {pct:20',
           'waiting:   {pct:-1', 'received:  {pct:95', 'done:      {pct:100')))
    check("不再用时间幂函数伪造百分比", "1 - ms / estMs" not in s and "estMs" not in s)
    check("等待期是不确定环、隐藏百分比", "is-indet" in s and "badge.hidden = true" in s)
    check("requestReal 回传 submitted / waiting / received",
          all(('sncPhase(spec.nodeId, "%s")' % k) in s
              for k in ("submitted", "waiting", "received")))
    check("普通生成与局部重绘都带 nodeId",
          "nodeId: n.id" in s and "nodeId: region.nodeId" in s)
    check("构建产物里保留了不确定环", "is-indet" in b)

    print("\n== C  方案 C：导出原图 / 拆分图层 ==")
    check("导出菜单有原图项", 'data-exp="node"' in s and "原图 PNG" in s)
    check("导出菜单有拆分图层项", 'data-exp="layers"' in s and "拆分图层 ZIP" in s)
    check("前端 exportLayers / systemSaveZip", "function exportLayers(" in s
          and "function systemSaveZip(" in s)
    check("请求带 layerDecomposition",
          "if(spec.layerDecomposition){" in s
          and "body.layerDecomposition = true;" in s)
    check("后端 /api/save-zip 路由", 'if path == "/api/save-zip":' in p)
    check("后端 save_zip 用 zipfile 打包", "def save_zip(" in p
          and "zipfile.ZipFile" in p and "import zipfile" in p)
    check("后端图层拆分函数", "def split_seedream_layers(" in p
          and '"layer_decomposition": True' in p)
    check("图层拆分只收 1 张原图、size 用档位",
          '"size": _seedream_tier(entry, want_res) if want_res > 0 else "auto"' in p
          and "len(images) != 1" in p)
    check("响应解析 z_index / bounding_box", '"z_index": z' in p
          and '"bounding_box": it.get("bounding_box")' in p)
    check("生成结果直通 layers，不取单张 b64",
          'if isinstance(result.get("layers"), list):' in p)
    check("构建产物里保留两个导出项", 'data-exp="layers"' in b)

    print("\n== D  官方坐标标记落到三种选区工具 ==")
    check("选区工具只剩 4 个", 'data-v="detect"' not in s and s.count('data-v="eraser"') == 1)
    check("识别算法整体移除", "v26DetectSubject" not in s and "SNC_V26_DETECT" not in s)
    check("坐标标记栏存在", 'id="sncInpMarks"' in s and "v26MarkTokens" in s)
    check("0–999 归一化 + <bbox>", "999" in s and '"<bbox>"' in s)
    check("矩形/套索/涂抹各自出标记", "r.kind === \"stroke\"" in s
          and "out.push(tok(r))" in s and "v26Bounds(seg, 0)" in s)
    check("提交时把 marks 传给后端", "marks: marks, nodeId: child.id" in s)
    check("Seedream 5.0 专属坐标通道", "function seedream5Row(" in s
          and "function coordinateRegionEdit(" in s)
    check("只认 5.0 pro / flash", "/^seedream-5-(pro|flash)$/.test(k)" in s)
    check("反选仍走老链路", "if(!invRec && seedream5Row(" in s)
    check("prompt 里真的拼了坐标标签", "marks.map(function(t){ return \"图 1 \" + t; })" in s)

    print("\n== E  涂抹显示修复 ==")
    check("新增追加路径函数", "function v26AppendPath(" in s)
    seg = s[s.index('r.kind === "stroke" && r.poly && r.poly.length > 1'):]
    seg = seg[:seg.index("} else {")]
    check("涂抹分支无 1.5px 中心线、无亮橙细描边",
          "c.lineWidth = 1.5" not in seg
          and 'c.strokeStyle = "rgba(224,96,58,.85)"' not in seg)
    check("所有笔触合成一条路径一次描边",
          "c.beginPath();\n      [r.poly].concat(r.segs || []).forEach" in s)
    check("拖拽预览同样一次描边", 'd.type === "brush" && d.pts.length > 1' in s)

    print("\n== F  产物 ==")
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
