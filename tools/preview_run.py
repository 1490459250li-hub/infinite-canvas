# -*- coding: utf-8 -*-
"""跑技能预览图：母图 -> 上游出图 -> 缩到 512 宽存 jpg。

用法：
    python tools/preview_run.py                 # 跑全部（PROMPTS 里的每一条）
    python tools/preview_run.py bi-night r-hand # 只跑指定几条
    python tools/preview_run.py --list          # 只列出还有哪些没跑

提示词按 v3.7 的 schema 拼（head + chips 的 say + body），和将来 buildPrompt() 出来的
文本一致；改 schema 时同步改这里的 PROMPTS。

母图按技能区分（SRC）：
    mock/base.jpg               实景母图（CHILL PARK），绝大多数据此跑
    assets/skill-art/_sketch.jpg 线稿 -> bi-hand 手绘转效果图
    assets/skill-art/_plan.jpg   平面线稿 -> bi-plan 平面转彩图
    mock/base-aerial.jpg        高处机位母图 -> r-aerial 鸟瞰渲染（由 bi-view 抬机位得到）
"""
import base64, json, os, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "mock", "base.jpg")
BASE_AERIAL = os.path.join(ROOT, "mock", "base-aerial.jpg")
SKETCH = os.path.join(ROOT, "assets", "skill-art", "_sketch.jpg")
PLAN = os.path.join(ROOT, "assets", "skill-art", "_plan.jpg")
DISTORTED = os.path.join(ROOT, "mock", "base-distorted.jpg")
OUT = os.path.join(ROOT, "截图", "v37", "preview")
API = os.environ.get("SNC_API", "http://127.0.0.1:8488/api/generate")
MODEL, PROVIDER = "seedream-5-flash", "seedream"

# 每条技能用哪张母图、什么比例（不给就是 base.jpg / 3:2）
SRC = {
    "bi-hand": (SKETCH, "3:2"),
    "bi-plan": (PLAN, "1:1"),
    "r-aerial": (BASE_AERIAL, "3:2"),
    # 透视校正要拿"有畸变的图"当输入才能看出来，拿已经校正过的照片等于空跑
    "bi-persp": (DISTORTED, "3:2"),
}

BODY_KEEP = ("严格保持原图的画面比例、视角、机位与 1:1 空间对齐：建筑体量、层数、开窗、材质分缝、"
             "铺装分格、植物与小品的数量与位置全部不变，只提升渲染质量与光色，不改方案、不增删物体。"
             "不添加文字、标注、水印或图框。")

PROMPTS = {
    "bi-night": ("把整体画面转换为夜景效果，空间结构、建筑体量与构图完全保持不变。天空呈深蓝到靛青的渐变，"
                 "点缀微弱星光与月光清辉；建筑与景观轮廓在夜幕中清晰可辨。人工光源成为主要照明：暖黄色灯光从窗内透出，"
                 "路灯、庭院灯与地埋灯散发柔和光晕，明暗对比增强。玻璃与水面反射夜色光泽，材质细节在低光下呈现细腻质感。"
                 "整体氛围宁静而富有层次，色温偏冷、局部暖光点缀。"),
    "bi-story": ("把这张图变成一张分镜图，九宫格（九个画面）。每个画面表现同一场景的不同景别与角度，"
                 "覆盖远景全景、中景入口、近景材质与植物细节、另一侧人视角度等不同观看距离与方向。"
                 "各格保持相同的设计语言、时间段与色调，格与格之间留细白缝，画面内不出现任何文字、编号、箭头或标注。"),
    "r-bldg": ("把这张图渲染成一张照片级的建筑表现图，场景类型为「办公建筑 · 高层办公」。"
               "时间与天气：傍晚，黄金时刻，橙红侧光打在迎光面，投影拉长，室内暖灯刚亮起；"
               "晴朗，天空干净通透，云量极少，投影边缘硬朗，远景清晰。" + BODY_KEEP),
    "r-hand": ("钢笔画：白底、黑色细线，线条干净利落，排线表现阴影与材质，不施彩色，留白充分，像建筑师的钢笔速写。"
               "目标画风：钢笔画。只把表现语言换成钢笔画，保留原有建筑轮廓、铺装分格、树木位置、透视关系与构图；"
               "去掉照片纹理与写实光影，整体像一张风格统一的建筑表现图。不添加任何文字、标注、图框或纸张背景。"),
    "bi-blue": ("把时间改为日落后约 20 分钟的蓝调时刻：天空保留深蓝天色与最后一抹暖霞，环境光冷而通透。"
                "建筑与景观的室内外灯光刚好亮起，暖色光源与冷色天光形成对比。阴影柔和，地面略带湿润反射，"
                "整体克制、干净、有高级感。构图、机位与所有物体位置保持不变。"),
    "r-land": ("把这张图渲染成一张照片级的景观表现图，场景类型为「城市开放空间 · 城市公园」。"
               "时间与天气：傍晚，黄金时刻，橙红侧光打在迎光面，投影拉长，室内暖灯刚亮起；"
               "晴朗，天空干净通透，云量极少，投影边缘硬朗，远景清晰。"
               "严格保持原图的场地边界、园路走向、水景轮廓、铺装分格、植物点位与所有小品的数量、位置和比例，"
               "只提升渲染质量与光色，不新增也不删除任何要素。植物按成年尺度还原冠形与疏密，"
               "乔木、灌木、地被、花境形成清楚的层次与季相；铺装接缝、材质肌理与湿润反射可信；"
               "水面反射与岸线收边自然；人物、座椅与灯具只作尺度与氛围参照。不添加文字、标注、水印或图框。"),
    "r-aerial": ("把这张图渲染成一张照片级的鸟瞰表现图，视角改为 45° 左右的俯视，视野覆盖完整场地，"
                 "场景类型为「商业建筑 · 通用商业建筑」。时间与天气：上午，明亮天光，太阳高度中等，"
                 "投影方向清楚、边缘利落；少云，少量云片点缀，光线仍通透，云影稀疏。"
                 "机位保持在屋顶上方，向下俯视：屋顶平面、门前广场铺装的分格、园路走向与绿化带轮廓都要看清楚，"
                 "地平线抬到画面上部或画面之外。建筑层数、体量、屋面形式与周边树木种类保持不变，"
                 "场地边界、道路与水体走向、植物与小品的数量位置全部不变，只调整机位高度与俯角；"
                 "道路及水体逐段原位保留，不平移、不拓宽、不拉直、不改弯、不新增支路。"
                 "地面铺装、屋顶与场地高差按原图还原，材质写实，投影方向与太阳高度角自洽。"
                 "不添加文字、标注、指北针或图框。"),
    "bi-mat": ("保持构图、视角、光照方向与所有物体位置不变，只替换指定区域的地面材质："
               "改为浅灰花岗岩铺装（可按需改成深色木平台、透水混凝土或水洗石）。"
               "新材质需符合原透视与尺度，保留接缝线走向、细微纹理与自然磨损，"
               "反射与粗糙度与原场景光照匹配，不要新增或删除任何物体。"),

    # ---- v3.7.3 补跑的 13 条（原来还是旧示意图）----
    # bi-time：母图本身是蓝调傍晚，改成"正午"差异最大，才看得出这条技能做了什么
    "bi-time": ("把画面时间改为：正午，接近顶光，投影短而深，明暗对比强，高光收住不过曝。"
                "只改变时段与由此带来的光色：太阳高度角与入射方向随之调整，天空颜色、环境光、"
                "投影长度与方向、材质受光与反射同步改变。建筑体量、物体位置、铺装分格、"
                "构图与机位完全不变，不新增也不删除任何物体。"),
    # bi-season：夏 -> 秋，叶色与季相变化最直观
    "bi-season": ("把画面季节改为秋季。调整植被季相、地被状态与光照色温，同步改变植物叶色、"
                  "地面植被与天气氛围。建筑体量、铺装分格、小品位置、构图与机位完全不变，"
                  "不新增也不删除任何物体。"),
    # bi-style：照片 -> 水彩，一眼能看出表现语言变了
    "bi-style": ("只把表现语言换成水彩渲染（晕染、留白、纸纹质感）。"
                 "保留原有建筑轮廓、铺装分格、树木位置、透视关系与构图；去掉照片纹理与写实光影，"
                 "整体像一张风格统一的建筑表现图。不添加任何文字、标注、图框或纸张背景，"
                 "物体位置与数量完全不变。"),
    # bi-view：这条的产物同时当 r-aerial 的高处机位母图
    "bi-view": ("在保持场地布局、建筑体量、植物位置与设计要素完全一致的前提下，"
                "把视角改为 35° 俯视鸟瞰（也可指定人视 1.6m 高或正轴测）。"
                "透视关系与消失点正确，不新增也不删除任何物体，画面比例与原图一致。"),
    "bi-plant": ("在保持建筑、铺装与构图不变的前提下，补足植被层次：高层乔木形成天际线，"
                 "中层灌木与观赏草柔化边界，地被与花境填充近景；注意季相与色叶搭配。"
                 "植物尺度符合透视，不要遮挡主要设计要素。"),
    "bi-hand": ("把这张线稿 / 草图转换成照片级的建筑景观效果图：按原有线条与比例上色建模，"
                "材质写实（石材、木材、玻璃、金属、植被），加真实天光与阴影，人物与植物点缀自然。"
                "不要改变原有的空间结构、物体位置与构图。"),
    "bi-plan": ("把这张平面图转换成彩色分析图：保留原有线稿与标注层级，"
                "按功能分区上色（铺装、绿化、水体、建筑、道路各用一个色系），"
                "加轻微阴影与图例色块。整体干净、克制、色调统一，可直接放进汇报 PPT。"),
    "bi-light": ("保持构图、机位与内容完全不变，只强化明暗层次与材质质感：对比更通透，"
                 "暗部保留细节，高光不过曝，石材与木材纹理更清晰，整体锐利干净。"
                 "不要改变任何物体、位置与色彩关系。"),
    "bi-people": ("在保持场景与构图不变的前提下，自然加入人物活动：散步、交谈、儿童玩耍、"
                  "推婴儿车等。人物比例与透视正确，光线方向与原场景一致，不遮挡主要设计要素；"
                  "人数适度、有生活气息但不喧闹。"),
    # bi-sky：原句是"多云晴空（也可指定黄昏火烧云）"，预览图直接指定火烧云，变化才看得出
    "bi-sky": ("只替换天空：改为黄昏火烧云。云层透视与光源方向与原场景一致，边缘过渡自然，"
               "建筑与树木轮廓保留，地面反射与阴影色温随之协调，其余内容完全不变。"),
    "bi-persp": ("校正这张图的透视与水平线：竖线垂直、水平线水平，镜头畸变拉直，"
                 "建筑比例恢复正常。同时保持原有内容、材质与光照不变，"
                 "不新增或删除任何物体，画面四边不出现拉伸变形。"),
    "bi-water": ("强化水景表现：水面加入真实反射与轻微涟漪，倒影随距离扩散，薄雾沿水面缓慢升起；"
                 "夜景时添加灯光在水面的拉长倒影。其余空间结构、材质与构图保持不变。"),
    "bi-channel": ("把这张图转换成材质通道图：每一类材质用一种纯色平涂填充，"
                   "完全去掉光影、阴影、纹理细节与明暗渐变。分类配色为——地面铺装=纯红，"
                   "草地与种植区=纯绿，乔木与灌木=深绿，建筑墙体=纯蓝，玻璃门窗=纯青，"
                   "座椅与景墙等小品=纯黄，天空=纯白。色块边界严格贴合原物体边缘，"
                   "区域内部完全平涂，不添加描边、网格、文字、图例或边框。"
                   "成图用于后期软件里做选区与蒙版。"),
}


def dataurl(p):
    with open(p, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


def gen(tag):
    src, ratio = SRC.get(tag, (BASE, "3:2"))
    if not os.path.exists(src):
        print("FAIL %-10s 母图不存在：%s" % (tag, src))
        return False
    body = {"prompt": PROMPTS[tag], "ratio": ratio, "res": 2048, "model": MODEL,
            "provider": PROVIDER, "images": [dataurl(src)], "format": "png",
            "promptExtend": True}
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 本机地址别走系统代理
    t0 = time.time()
    with op.open(req, timeout=300) as r:
        j = json.load(r)
    ms = int((time.time() - t0) * 1000)
    if not j.get("ok"):
        print("FAIL %-10s %s" % (tag, j.get("error")))
        return False
    raw = os.path.join(OUT, tag + ".png")
    with open(raw, "wb") as f:
        f.write(base64.b64decode(j["b64"]))
    small = os.path.join(OUT, tag + ".jpg")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw,
                    "-vf", "scale=512:-1", "-q:v", "4", small], check=True)
    print("OK   %-10s %6dms  %-10s %3d KB" % (tag, ms, j.get("size"), os.path.getsize(small) // 1024))
    return True


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    if "--list" in sys.argv:
        for t in PROMPTS:
            j = os.path.join(OUT, t + ".jpg")
            print("%-11s %s" % (t, "已有" if os.path.exists(j) else "缺"))
        sys.exit(0)
    todo = sys.argv[1:] or list(PROMPTS)
    fail = []
    for t in todo:
        if t not in PROMPTS:
            print("SKIP %-10s 不在 PROMPTS 里" % t)
            continue
        if not gen(t):
            fail.append(t)
    if fail:
        print("失败：%s" % " ".join(fail))
        sys.exit(1)
