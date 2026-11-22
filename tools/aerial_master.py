# -*- coding: utf-8 -*-
"""生成「高处机位母图」：把 CHILL PARK 那张低机位人视照片抬成无人机俯拍。

为什么单独做：模型的默认倾向是"保留原构图"，直接在鸟瞰技能的提示词里写
"把机位抬高"只会微微抬头（试过两轮，都只抬了几度）。所以要先把母图本身换成
俯拍照片，鸟瞰技能才有东西可渲染。

用法：
    python tools/aerial_master.py            # 生成 mock/base-aerial.jpg
    python tools/aerial_master.py --from X   # 换一张源图
    python tools/aerial_master.py --steeper  # 在第一版基础上再抬一次（接近 55°）
"""
import base64, json, os, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "mock", "base.jpg")
OUT_RAW = os.path.join(ROOT, "mock", "base-aerial.png")
OUT = os.path.join(ROOT, "mock", "base-aerial.jpg")
API = os.environ.get("SNC_API", "http://127.0.0.1:8488/api/generate")
MODEL, PROVIDER = "seedream-5-pro", "seedream"

PROMPT = ("把这张照片改成无人机 45° 俯拍机位：镜头抬到屋顶以上、向下俯视，"
          "能同时看清咖啡厅屋顶的整片平面、门前广场铺装的完整分格、园路的走向，"
          "以及两侧绿化带的平面轮廓。透视按俯视重建，地平线移到画面上部、天空只占一条窄边，"
          "地面在画面中占七成以上。保持同一栋建筑、同一片场地、同样的傍晚蓝调天色"
          "与暖黄室内灯光，建筑造型与周边树木种类不变。真实航拍质感，不添加文字、标注或图框。")

# 第二遍：在第一版已经 30° 的基础上再压一档，接近 55°，屋顶成为画面主体
PROMPT_HIGH = ("把这张航拍照片的机位再抬高：改为接近 55° 的高空俯拍，镜头几乎在屋顶正上方偏前一点。"
               "屋顶平面要占据画面中心且完整可辨，门前广场铺装的分格、园路曲线、"
               "两侧绿化带的平面轮廓全部清楚展开；建筑立面只保留一小部分，天空只出现在画面最上沿。"
               "保持同一栋建筑、同样的白色波浪屋面造型、同样的傍晚蓝调天色与暖黄灯光，"
               "树木位置与场地边界不变。真实航拍质感，画面不出现文字、标注或图框。")


def dataurl(p):
    with open(p, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


def main():
    src = SRC
    prompt = PROMPT
    out_raw, out = OUT_RAW, OUT
    if "--from" in sys.argv:
        src = sys.argv[sys.argv.index("--from") + 1]
    if "--steeper" in sys.argv:
        prompt = PROMPT_HIGH
        if src == SRC:
            src = OUT                       # 默认拿第一版当输入
        out_raw = os.path.join(ROOT, "mock", "base-aerial-high.png")
        out = os.path.join(ROOT, "mock", "base-aerial-high.jpg")
    body = {"prompt": prompt, "ratio": "3:2", "res": 2048, "model": MODEL,
            "provider": PROVIDER, "images": [dataurl(src)], "format": "png",
            "promptExtend": False}
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    t0 = time.time()
    with op.open(req, timeout=300) as r:
        j = json.load(r)
    ms = int((time.time() - t0) * 1000)
    if not j.get("ok"):
        print("FAIL", j.get("error"))
        return 1
    with open(out_raw, "wb") as f:
        f.write(base64.b64decode(j["b64"]))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", out_raw,
                    "-q:v", "3", out], check=True)
    print("OK %6dms %-10s -> %s %.0f KB" % (ms, j.get("size"), out,
                                            os.path.getsize(out) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
