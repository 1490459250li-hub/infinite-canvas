# -*- coding: utf-8 -*-
"""生成 v3.7.2 落地对照页（demo-v37/v3.7.2-落地对照.html）。

读 demo-v37/img/ 下的 final-*.jpg 与 截图/v37b、v371、v372 里的截图，
全部 base64 内联，单文件可直接发给别人看。
"""
import base64
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(ROOT, "demo-v37", "img")
SHOT = os.path.join(ROOT, "截图", "v37b")
OUT = os.path.join(ROOT, "demo-v37", "v3.7.3-落地对照.html")

sys.path.insert(0, os.path.join(ROOT, "proto"))
import server as SNC  # noqa: E402  模型表直接从注册表读，避免文档和代码漂移


def model_rows(pid):
    spec = SNC.provider_spec(pid) or {}
    rows = []
    for m in spec.get("image") or []:
        rows.append((m.get("label", ""), "<code>%s</code>" % m.get("id", ""),
                     m.get("badge", "") or "—", str(m.get("max_side", "") or "—"),
                     str(m.get("max_refs", 0)), "支持" if m.get("mask") else "—"))
    return rows


def tbl(head, rows):
    h = "".join("<th>%s</th>" % c for c in head)
    b = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % c for c in r) for r in rows)
    return '<table class="mt"><thead><tr>%s</tr></thead><tbody>%s</tbody></table>' % (h, b)


def b64(path, mime):
    with open(path, "rb") as f:
        return "data:%s;base64,%s" % (mime, base64.b64encode(f.read()).decode("ascii"))


def art(name):
    return b64(os.path.join(IMG, name), "image/jpeg")


def shot(name, sub="v37b"):
    return b64(os.path.join(os.path.dirname(SHOT), sub, name), "image/png")


SHOTS = [
    ("02-零参数.png", "零参数 · 只剩 4 行", "时段技能只有 1 个参数，窗口就是图标 + 名字 + 输入框 + 设置行 + 生成。高度 275px，不再是一整块空面板。"),
    ("03-单参数.png", "单参数 · 一行放下", "「时段」chip 展开成一行下拉，选中后整条提示词立刻重拼。"),
    ("04-两级下钻.png", "两级下钻 · 点大类选子类", "点「办公建筑」直接在菜单里展开子类，不用再开第二个下拉。"),
    ("05-三参数.png", "三参数 · 三个下拉并排", "建筑渲染：建筑类型 + 时间 + 天气。时间与天气同一组，拼句子时用「；」并成一句，不会切成两句。"),
    ("07-分镜宫格.png", "场景分镜 · 也进了同一个窗", "原来分镜只有纯文字选项菜单，现在同样一道窗，只是 chip 换成了「宫格」。"),
    ("08-手绘画风.png", "手绘渲染 · 12 种画风", "选画风直接注入 ART_STYLE 里那段长提示词，不是只加个「手绘」两个字。"),
]

ARTS = [
    ("bi-night", "夜景照明", "old-bi-night.jpg"),
    ("bi-blue", "蓝调时刻", "old-bi-blue.jpg"),
    ("bi-story", "场景分镜", "old-bi-story.jpg"),
    ("bi-mat", "材质替换", "old-bi-mat.jpg"),
]

NEW_ONLY = [
    ("r-bldg", "建筑渲染", "本次新增技能"),
    ("r-land", "景观渲染", "本次新增技能"),
    ("r-aerial", "鸟瞰渲染", "本次新增技能"),
    ("r-hand", "手绘渲染", "本次新增技能"),
]

TODO = ["bi-view 视角切换", "bi-hand 手绘改绘", "bi-plan 平面转效果", "bi-plant 植物配置",
        "bi-light 灯光布置", "bi-people 人物植入", "bi-sky 天空替换", "bi-persp 透视校正",
        "bi-water 水体表现", "bi-channel 通道渲染", "bi-time 时段", "bi-season 季节", "bi-style 画风迁移"]

# v3.7.3 补跑的 13 条（id, 名称, 这一版特意选的参数，用来说明预览图为什么长这样）
LATE = [
    ("bi-time", "时间迁移", "母图是蓝调傍晚 → 改成正午顶光，差异最大"),
    ("bi-season", "季节迁移", "夏 → 秋，竹叶转黄、地被枯色"),
    ("bi-style", "画风迁移", "照片 → 水彩，晕染与留白"),
    ("bi-view", "视角切换", "人视 → 30° 俯视，屋顶与场地开始展开"),
    ("bi-hand", "手绘转效果图", "换线稿母图：线稿 → 照片级"),
    ("bi-plan", "平面转彩图", "换平面母图：线稿 → 分区彩色分析图"),
    ("bi-plant", "植物增补", "近景地被与花境加密，主体不遮"),
    ("bi-light", "光影增强", "暗部提亮、材质更清晰"),
    ("bi-people", "人物氛围", "散步、儿童、推车，比例与光向一致"),
    ("bi-sky", "天空替换", "直接指定黄昏火烧云，地面暖调跟随"),
    ("bi-persp", "透视校正", "换畸变母图：桶形畸变的广角 → 竖线拉直"),
    ("bi-water", "水景氛围", "前景加浅水面、倒影与薄雾"),
    ("bi-channel", "AI 通道图", "纯色平涂：铺装红 / 植被绿 / 墙体蓝 / 玻璃青 / 小品黄"),
]

PROMPT = """把这张图渲染成一张照片级的建筑表现图，场景类型为「办公建筑 · 高层办公」。
时间与天气：傍晚，黄金时刻，橙红侧光打在迎光面，投影拉长，室内暖灯刚亮起；
晴朗，天空干净通透，云量极少，投影边缘硬朗，远景清晰。
严格保持原图的画面比例、主体位置与构图关系…"""


def shot_card(name, title, desc):
    return """      <figure class="shot">
        <div class="shot-img"><img src="%s" alt="%s"></div>
        <figcaption><b>%s</b><span>%s</span></figcaption>
      </figure>""" % (shot(name), title, title, desc)


def art_card(key, label, old=None, note=""):
    oldh = ""
    if old:
        oldh = """<div class="pair"><div class="half"><img src="%s"><em>旧</em></div><div class="half"><img src="%s"><em>新</em></div></div>""" % (
            art(old), art("final-%s.jpg" % key))
    else:
        oldh = """<div class="pair solo"><div class="half"><img src="%s"><em>新增</em></div></div>""" % art("final-%s.jpg" % key)
    return """        <figure class="art">
          %s
          <figcaption><b>%s</b><span>%s</span></figcaption>
        </figure>""" % (oldh, label, note or key)


HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>无限画布 v3.7.3 · 技能窗口三合一 + 三浮层可拖 + MiniMax H3-Image + 模型换代（已落地）</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#f4f5f7;color:#1c1f23;
  font:14px/1.75 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:44px 28px 80px}
h1{font-size:26px;line-height:1.35;margin:0 0 10px;letter-spacing:-.3px}
.sub{color:#6b7280;font-size:13.5px;margin:0 0 26px}
.tag{display:inline-block;background:#166534;color:#fff;font-size:11px;font-weight:600;
  padding:2px 9px;border-radius:20px;vertical-align:3px;margin-right:8px;letter-spacing:.4px}
h2{font-size:18px;margin:46px 0 6px;padding-top:22px;border-top:1px solid #e3e5e9}
h2 .n{color:#9aa1ab;font-weight:600;margin-right:8px;font-variant-numeric:tabular-nums}
h3{font-size:14.5px;margin:26px 0 10px;color:#374151}
p{margin:9px 0}
.lead{color:#4b5563;font-size:13.5px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:24px 0 0}
.stat{background:#fff;border:1px solid #e3e5e9;border-radius:10px;padding:13px 14px}
.stat b{display:block;font-size:21px;line-height:1.2;color:#111827;font-variant-numeric:tabular-nums}
.stat span{font-size:11.5px;color:#6b7280}
.merge{display:flex;align-items:center;gap:12px;margin:18px 0 6px;flex-wrap:wrap}
.mbox{flex:1 1 160px;min-width:150px;background:#fff;border:1px solid #e3e5e9;border-radius:9px;padding:12px 13px}
.mbox s{display:block;font-size:12.5px;font-weight:600;color:#9ca3af;text-decoration-color:#d1d5db}
.mbox span{font-size:11.5px;color:#9aa1ab;line-height:1.55}
.arrow{font-size:20px;color:#9aa1ab;flex:0 0 auto}
.done{flex:1 1 200px;min-width:170px;background:#ecfdf5;border:1px solid #a7f3d0;border-radius:9px;padding:12px 13px}
.done s{display:block;font-size:12.5px;font-weight:700;color:#065f46;text-decoration:none}
.done span{font-size:11.5px;color:#047857;line-height:1.55}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px;align-items:start}
.shot{margin:0;background:#fff;border:1px solid #e3e5e9;border-radius:10px;overflow:hidden}
.shot-img{background:#16181d;padding:0;line-height:0}
.shot-img img{width:100%;display:block}
.shot figcaption{padding:11px 13px 13px;border-top:1px solid #eef0f2}
.shot figcaption b{display:block;font-size:12.8px;color:#111827;margin-bottom:2px}
.shot figcaption span{font-size:11.8px;color:#6b7280;line-height:1.6}
pre{background:#1b1e24;color:#e6e9ef;border-radius:10px;padding:16px 18px;overflow:auto;
  font:12.5px/1.85 "Cascadia Code",Consolas,monospace;margin:12px 0 0;
  white-space:pre-wrap;word-break:break-word}
pre .k{color:#7dd3fc}
.note{background:#fff;border-left:3px solid #2563eb;border-radius:0 8px 8px 0;padding:12px 16px;
  margin:14px 0;font-size:13px;color:#374151}
.note b{color:#1d4ed8}
.arts{display:grid;grid-template-columns:repeat(4,1fr);gap:13px;margin-top:16px}
.art{margin:0;background:#fff;border:1px solid #e3e5e9;border-radius:10px;overflow:hidden}
.pair{display:flex;gap:1px;background:#e3e5e9}
.pair.solo{display:block}
.half{position:relative;flex:1;min-width:0;line-height:0;background:#16181d}
.half img{width:100%;display:block;aspect-ratio:3/2;object-fit:cover}
.half em{position:absolute;left:5px;top:5px;font-style:normal;font-size:9.5px;letter-spacing:.5px;
  background:rgba(0,0,0,.62);color:#fff;padding:1px 6px;border-radius:3px}
.pair.solo .half em{background:rgba(6,95,70,.85)}
.art figcaption{padding:8px 10px 10px}
.art figcaption b{display:block;font-size:12px;color:#111827}
.art figcaption span{font-size:10.8px;color:#8b929c}
ul{margin:10px 0;padding-left:20px}
li{margin:5px 0;font-size:13.2px;color:#374151}
.todo{background:#fff;border:1px solid #e3e5e9;border-radius:10px;padding:16px 18px;margin-top:14px}
.chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:9px}
.chip{font-size:11.5px;color:#6b7280;background:#f3f4f6;border:1px solid #e5e7eb;
  border-radius:6px;padding:3px 9px;font-variant-numeric:tabular-nums}
.ok{color:#065f46;font-weight:600}
table.mt{width:100%;border-collapse:separate;border-spacing:0;background:#fff;border:1px solid #e3e5e9;
  border-radius:10px;overflow:hidden;font-size:12.4px;margin-top:14px}
table.mt th{background:#f8f9fb;text-align:left;font-weight:600;color:#374151;padding:8px 11px;
  border-bottom:1px solid #e3e5e9;white-space:nowrap}
table.mt td{padding:8px 11px;border-bottom:1px solid #eef0f2;color:#374151;vertical-align:top}
table.mt tr:last-child td{border-bottom:0}
table.mt code{font-size:11.6px;background:#f3f4f6;border:1px solid #e8eaee;border-radius:4px;padding:0 4px}
.pill{display:inline-block;font-size:10.5px;color:#065f46;background:#ecfdf5;border:1px solid #a7f3d0;
  border-radius:20px;padding:0 7px;line-height:16px}
.pill.gray{color:#6b7280;background:#f3f4f6;border-color:#e5e7eb}
footer{margin-top:54px;padding-top:18px;border-top:1px solid #e3e5e9;font-size:11.5px;color:#9aa1ab}
@media(max-width:860px){.grid2,.arts{grid-template-columns:1fr 1fr}.stats{grid-template-columns:1fr 1fr}}
@media(max-width:560px){.grid2,.arts,.stats{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">

  <h1><span class="tag">已落地</span>三浮层可拖 + MiniMax H3-Image + 模型换代 + 21 条预览图全跑完</h1>
  <p class="sub">v3.7.3 · 2026-11-12 · 原来 3 条弹窗路径合成 1 道，21 条技能全部走同一条链路；参数面板、技能抽屉、技能工作台都能拖；<b>第六家 MiniMax 接通 H3-Image</b>；OpenAI 换到 GPT Image 2.6、Google 换成 Nano Banana Pro / 2 / 2 Lite；<b>21 条技能预览图全部重跑</b>，鸟瞰母图换成高处机位</p>

  <div class="stats">
    <div class="stat"><b>3 → 1</b><span>弹窗路径数</span></div>
    <div class="stat"><b>21</b><span>技能条数（通用 14 / 专项 7）</span></div>
    <div class="stat"><b>6</b><span>供应商（新增 MiniMax）</span></div>
    <div class="stat"><b>3</b><span>可拖动浮层</span></div>
  </div>

  <h2><span class="n">01</span>你说的「把 2、3、4 三窗合并」</h2>
  <p class="lead">改之前，点一条技能会根据它带不带参数落到三种完全不同的界面，用户得先猜「这条技能是哪种」。</p>

  <div class="merge">
    <div class="mbox"><s>① 纯文字选项菜单</s><span>场景分镜、材质替换<br>小浮层，选完直接发</span></div>
    <div class="mbox"><s>② 指令回填编辑面板</s><span>时段、画风这类<br>填进右侧面板，再点箭头提交</span></div>
    <div class="mbox"><s>③ 渲染专属工作台</s><span>建筑 / 鸟瞰 / 景观 / 手绘<br>另开一个窗，布局还不一样</span></div>
    <div class="arrow">→</div>
    <div class="done"><s>一道窗 #sncSkWin</s><span>图标 + 技能名 + 参数下拉 + 提示词输入框 + 设置行 + 生成</span></div>
  </div>

  <p class="lead">四件你拍板的事都实现了：设置行<b>直接平铺在窗里</b>（不再折叠）、点生成后<b>关窗</b>、<b>不要</b>「指令」按钮、提示词<b>直接放在输入框里可改</b>。</p>

  <h2><span class="n">02</span>窗口实际长什么样（真截图，非原型）</h2>
  <p class="lead">窗口高度跟着参数数量走：0 个参数 275px，3 个参数也就多一行下拉，不会撑成大面板。</p>

  <div class="grid2">
<!--SHOTS-->
  </div>

  <h2><span class="n">03</span>输入框里放的就是要发出去的那段</h2>
  <p class="lead">不设「指令」按钮，但提示词必须看得见 —— 选完参数自动拼好整段塞进输入框，想微调直接改字，改完点生成发的就是你改过的那段。</p>

  <pre><!--PROMPT--></pre>

  <div class="note">
    <b>手改保护：</b>你在输入框里动过字之后，再回头改下拉不会把你写的内容冲掉。窗口底部会提示「已手改，调参数不再覆盖」，旁边给一个「恢复自动」把它退回拼装结果。
  </div>

  <h3>拼装规则（不是简单相加）</h3>
  <ul>
    <li><b>开头一句定任务</b>：技能自带 head，比如「把这张图渲染成一张照片级的建筑表现图」</li>
    <li><b>同一组的参数并成一句</b>：时间和天气共用一个 <code>grp</code>，中间用「；」，出来是「时间与天气：傍晚…；晴朗…」</li>
    <li><b>控件短标签换成画面短语</b>：「傍晚时段光照」→「傍晚，黄金时刻，橙红侧光打在迎光面，投影拉长，室内暖灯刚亮起」</li>
    <li><b>画风注入长段落</b>：手绘 12 种画风取的是 <code>ART_STYLE</code> 里原有那段，不是加两个字</li>
    <li><b>末尾锁约束</b>：技能自带 body，写死「严格保持原图比例、主体位置、构图关系」这类不许动的东西</li>
  </ul>

  <h2><span class="n">04</span>先换的 8 条（其余 13 条见下一节）</h2>
  <p class="lead">左旧右新。旧的 17 张是早期用示意小图跑的宣传图，跟真实项目差得远；现在母图统一用你给的那张 CHILL PARK 现场照片，出来的结果才像用户自己会得到的东西。</p>

  <div class="arts">
<!--ARTS-->
  </div>

  <h2><span class="n">05</span>剩下的 13 条也跑完了，21 条一张不剩</h2>
  <p class="lead">上次说「先跑 8 条常用的」，这 13 条还是早期示意图。这轮全部用 CHILL PARK 实图重跑，左旧右新。</p>

  <div class="arts">
<!--LATE-->
  </div>

  <h3>三条换了母图，不然看不出效果</h3>
  <p class="lead">这几条技能吃的是特定类型的输入，拿一张精修过的实景照片去跑等于空转，所以给它们各配了合适的母图：</p>
  <ul>
    <li><b>手绘转效果图</b> → 用线稿当母图，出来才是「线稿变照片级」，而不是把照片再磨一遍</li>
    <li><b>平面转彩图</b> → 用平面线稿当母图，出来才有分区上色与图例</li>
    <li><b>透视校正</b> → 母图先用 <code>lenscorrection</code> 加一道桶形畸变，校正后竖线才看得出被拉直</li>
  </ul>

  <h3>鸟瞰：母图换成高处机位了</h3>
  <p class="lead">之前那张鸟瞰预览图其实是「略微抬高的机位」—— 因为母图本身是低机位人视，模型只肯微微抬头。这次先把母图抬到接近 55° 的高空俯拍，再跑鸟瞰技能。</p>

  <div class="grid2">
    <figure class="shot">
      <div class="shot-img"><img src="<!--SHOT_MASTER-->" alt="高处机位母图"></div>
      <figcaption><b>新的母图：约 55° 高空俯拍</b><span>屋顶平面占画面主体，门前广场铺装分格、园路曲线、两侧绿化带轮廓全部展开。由原照片抬机位得到，建筑造型与场地边界保持。</span></figcaption>
    </figure>
    <figure class="shot">
      <div class="shot-img"><img src="<!--SHOT_AERIAL-->" alt="鸟瞰渲染结果"></div>
      <figcaption><b>鸟瞰渲染的产出</b><span>机位保持在屋顶上方，屋顶面、铺装分格与园路走向都看得清，不再是「站在地面抬头」的构图。</span></figcaption>
    </figure>
  </div>

  <div class="note">
    <b>一句实话：</b>这张母图是用模型从人视照片「抬」出来的，不是实拍航拍片。它的作用是让预览图展示
    「有高机位素材时鸟瞰能到什么程度」；真拿自己的航拍原片去跑，效果只会更稳。
    抬机位这一步本身没进产品，产品里鸟瞰仍然只做「渲染 + 轻微抬视角」。
  </div>

  <h2><span class="n">06</span>v3.7.1 又修了两处</h2>
  <p class="lead">都是你上手之后马上撞到的：浮层挪不动、还有一个会偷偷改所有请求的开关。</p>

  <div class="grid2">
    <figure class="shot">
      <div class="shot-img"><img src="<!--SHOT_POP-->" alt="抽屉拖动"></div>
      <figcaption><b>技能抽屉能拖了</b><span>按住「通用技能 / 专项技能 / 我的」那一行右侧空白，或者底部提示条，整个抽屉跟着走。搜索框照样能点能输入 —— 按下不动 4px 不算拖。</span></figcaption>
    </figure>
    <figure class="shot">
      <div class="shot-img"><img src="<!--SHOT_WIN-->" alt="工作台拖动"></div>
      <figcaption><b>技能工作台能拖了</b><span>按住标题栏图标那一段拖动。提示词输入框、参数下拉、生成按钮都不受影响。</span></figcaption>
    </figure>
    <figure class="shot">
      <div class="shot-img"><img src="<!--SHOT_STRUCT-->" alt="参数面板"></div>
      <figcaption><b>结构化参数面板能拖了</b><span>按标题栏拖动，拖到右下角也不会跑出窗口 —— 装得下就整块可见，装不下至少留一条标题栏给你抓。</span></figcaption>
    </figure>
    <figure class="shot">
      <div class="shot-img"><img src="<!--SHOT_FOOT-->" alt="去掉开关"></div>
      <figcaption><b>「应用到所有生成」已删除</b><span>底部只剩 格式 / 优化器 / 分类模板 三个下拉。手写指令、增强、变体、局部重绘不再被 {最高准则} 包装改写。</span></figcaption>
    </figure>
  </div>

  <div class="note">
    <b>为什么删这个开关：</b>它打开后，<code>buildPrompt()</code> 会给<b>每一个</b>请求套上
    <code>{最高准则, 要求}</code> 包装 —— 包括你手打的一句话。包装本来是给结构化技能用的，
    套到手写指令上，等于在你不知情的时候把请求改写了。现在它只在「技能自带结构化上下文」
    和「参数浮层选过值」这两条路径上生效，其余链路逐字不变。
  </div>

  <div class="note">
    <b>位置会记住：</b>拖完写进 localStorage，下次打开还在老地方；双击那条拖动条就复位回默认锚点。
    三个浮层各有各的记忆键，互不干扰。
  </div>

  <h2><span class="n">07</span>MiniMax 有图像模型了：H3-Image 已经接进来</h2>
  <p class="lead">你点名的是 <b>H3-Image</b>，不是老的 <code>image-01</code>（那个只走 <code>/v1/image_generation</code>、只能做人脸参考）。H3 是另一套接口，能力差得多，所以整块按 H3 重写。</p>

  <div class="grid2">
    <figure class="shot">
      <div class="shot-img"><img src="<!--SHOT_MMCARD-->" alt="MiniMax 卡片"></div>
      <figcaption><b>设置页自动多出第六张卡</b><span>供应商卡片是按 <code>/api/providers</code> 下发的顺序渲染的，前端没有一处硬编码供应商名 —— 注册表加一条，卡片、多密钥、连接测试、模型下拉、分辨率档位全都跟着出来。</span></figcaption>
    </figure>
    <figure class="shot">
      <div class="shot-img"><img src="<!--SHOT_MMSET-->" alt="六家供应商"></div>
      <figcaption><b>4 / 6 已连接</b><span>顶部汇总是按真实配置算的。截图里 SenseNova、Google、OpenAI、MiniMax 四家有钥匙，Seedream 与 Qwen 保留空位。</span></figcaption>
    </figure>
  </div>

  <h3>H3-Image 两档</h3>
<!--TBL_MINIMAX-->

  <ul>
    <li><b>文生图与编辑是两个端点</b>：带参考图走 <code>/v1/images/edits</code>，不带走 <code>/v1/images/generations</code>，代码里自动分流，用户不用选</li>
    <li><b>尺寸只能给「宽x高」</b>：不能同时传 <code>aspect_ratio</code> 或 <code>area</code>，混传直接 400。所以比例先换算成像素，再补到官方的 65.5 万–2000 万区间、单边不超过 4096</li>
    <li><b>取整会掉回下限</b>：9:16 在 1024 档算出 600×1072 = 643200，低于 655360。代码里逐 8px 往上补到过线为止，得 608×1080</li>
    <li><b>200 也可能是失败</b>：H3 会在 HTTP 200 的 <code>data[]</code> 里逐条塞 <code>error</code>，所以回包要一条条看，不能只看状态码</li>
    <li><b>单次最多 16 张参考图</b>，多出来的截断；这家不支持蒙版与透明底，UI 上就标成「—」而不是给个点了会失败的按钮</li>
  </ul>

  <div class="note">
    <b>国内 / 海外两个站：</b>默认打 <code>api.minimaxi.com</code>（国内），海外站是 <code>api.minimax.io</code>。
    两站密钥不通用，卡片提示里写清楚了，免得贴错站报 401 找不到原因。
  </div>

  <h2><span class="n">08</span>GPT 与 Google 的图像模型换成现在这几档</h2>
  <p class="lead">你说的「都不是最新的」确实 —— 原来的 <code>gpt-image-1</code> 已经不在新账号的可用列表里，<code>gemini-2.5-flash-image</code> 更是 2026-10-02 就关停了，等于这两家在新装机器上是「配了钥匙也出不了图」。</p>

  <h3>OpenAI</h3>
<!--TBL_OPENAI-->

  <h3>Google</h3>
<!--TBL_GOOGLE-->

  <div class="note">
    <b>分辨率档位跟着模型走：</b>Nano Banana Pro 支持到 4K，请求里会带
    <code>imageConfig.imageSize</code>（只认大写的 <code>"2K"</code> / <code>"4K"</code>，
    小写会被拒）；1K 档不传这个字段。OpenAI 三档都还是 1536 长边，所以界面给的是「原图 / 1K / 1.5K」。
  </div>

  <div class="note">
    <b>老工程不会因为改名而出不了图：</b>升级后如果画布里存的还是旧模型名，会被别名表指到当前档位 ——
    <code>gpt-image-1</code> → <code>gpt-image-2.6-sunburst</code>，
    <code>nano-banana</code> / <code>gemini-2.5-flash-image</code> → <code>nano-banana-2</code>。
    不这么兜一下，用户升级完点生成只会收到一句「模型不存在」。
  </div>

  <h2><span class="n">09</span>验收</h2>
  <ul>
    <li><span class="ok">回归 1241 项 0 失败</span>（24 个测试文件；<code>test_v15</code> 真调上游按惯例跳过）</li>
    <li><code>test_v19.py</code> 34 项：通用 14 张 + 专项 7 张预览图各带自己的图、互不相同、全是内联 data URL</li>
    <li>旧路径删干净：<code>sncSkillOptMenu</code> / <code>showSkillOpts</code> / <code>applySkillToNode</code> / <code>placeSkillOptMenu</code> 不再存在，测试里也有断言守着</li>
    <li>21 条技能每条都能拼出非空提示词，chips 里的参数键全部能在 <code>SNC_ARCO.CONTROLS</code> 里解析到</li>
    <li>抽屉回到三页签（通用 / 专项 / 我的），渲染 4 条并进通用页最前面</li>
    <li><code>tests/test_v40.py</code> 76 项：三个浮层各自拖动、刷新后位置仍在、双击复位、拖出边界被夹回、按住关闭按钮不误拖、搜索框与提示词框不受影响、开关已无、手写不包装、选参数仍包装</li>
    <li><code>tests/test_v41.py</code> 83 项：MiniMax 注册表、两个端点分流、6 组比例的像素区间与单边合法性、16 张上限、<code>data[].error</code> 翻成可读报错、401 分类；另有浏览器段验六家下发与设置页卡片</li>
    <li><code>tests/test_v30_providers.py</code> 115 项：六家注册表、旧模型名被规范化、分辨率档位、多密钥增删、分流保存</li>
    <li>打包：<code>无限画布.exe</code> 13.7 MB；<code>--self-test</code> 退出码 0</li>
    <li>打包件验收：<code>/api/health</code> 返回 3.7.2、<code>/.env</code> 与 <code>/.git/config</code> 均 404、内嵌页面与源文件 MD5 一致（<code>66b582f9…</code>，2,054,274 B）</li>
  </ul>

  <footer>无限画布 v3.7.3 · 本页所有截图与预览图均来自真实运行，非原型稿</footer>
</div>
</body>
</html>
"""


def main():
    shots = "\n".join(shot_card(*s) for s in SHOTS)
    arts = "\n".join(art_card(k, lab, old, note) for k, lab, old, note in
                     [(k, lab, old, "预览图已重跑") for k, lab, old in ARTS] +
                     [(k, lab, None, note) for k, lab, note in NEW_ONLY])
    chips = "".join('<span class="chip">%s</span>' % t for t in TODO)
    late = "\n".join(art_card(k, lab, "old-%s.jpg" % k, note) for k, lab, note in LATE)
    head = ("模型", "接口里的 id", "标注", "最长边", "参考图", "蒙版")
    html = (HTML.replace("<!--SHOT_POP-->", shot("04-抽屉拖动.png", "v371"))
                .replace("<!--SHOT_WIN-->", shot("05-工作台拖动.png", "v371"))
                .replace("<!--SHOT_STRUCT-->", shot("01-拖到新位置.png", "v371"))
                .replace("<!--SHOT_FOOT-->", shot("03-底部去掉开关.png", "v371"))
                .replace("<!--SHOT_MMCARD-->", shot("03-MiniMax卡片.png", "v372"))
                .replace("<!--SHOT_MMSET-->", shot("05-设置面板.png", "v372"))
                .replace("<!--SHOT_MASTER-->", b64(os.path.join(ROOT, "mock", "base-aerial-high.jpg"),
                                                   "image/jpeg"))
                .replace("<!--SHOT_AERIAL-->", b64(os.path.join(ROOT, "截图", "v37", "preview",
                                                                "r-aerial.jpg"), "image/jpeg"))
                .replace("<!--TBL_MINIMAX-->", tbl(head, model_rows("minimax")))
                .replace("<!--TBL_OPENAI-->", tbl(head, model_rows("openai")))
                .replace("<!--TBL_GOOGLE-->", tbl(head, model_rows("google")))
                .replace("<!--LATE-->", late)
                .replace("<!--SHOTS-->", shots)
                .replace("<!--PROMPT-->", PROMPT)
                .replace("<!--ARTS-->", arts)
                .replace("<!--CHIPS-->", chips))
    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("written %s  %.1f KB" % (OUT, len(html.encode("utf-8")) / 1024.0))


if __name__ == "__main__":
    main()
