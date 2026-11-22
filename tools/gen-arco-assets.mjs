// 生成 S1+S2+S3 资产层（v2.4）
// 数据源：E:/canvas-probe2/extract/ 下由 D5 Arco app.asar 解包得到的只读抽取产物。
//
// 合规口径（见《D5 Arco 全量复用盘点.md》第 6 节）：
//   * 借鉴的是「功能结构 / 控件 schema / 命名体系 / 提示词写法与规则模板」；
//   * 控件 value / label / 两级分类、8 维风格维度、结构化 JSON 的字段骨架按原体系复刻；
//   * 所有提示词正文按同一写法自撰，不整段复制业务 JS；
//   * 不复制任何 PNG / MP4 / JPG / 汇报页 HTML / 业务代码。
//
// 用法：node tools/gen-arco-assets.mjs
// 输出：proto/arco-assets.snippet.js（供 inject-arco-assets.mjs 插入主逻辑块）
import fs from 'node:fs';
import path from 'node:path';

const EX = path.resolve('E:/canvas-probe2/extract');
const P = (f) => JSON.parse(fs.readFileSync(path.join(EX, 'parsed', f), 'utf8'));
const R = (f) => fs.readFileSync(path.join(EX, 'raw', f), 'utf8');
const OUT = path.resolve('E:/无限画布/proto/arco-assets.snippet.js');

/* ---------- 1. 控件字典（label / value / 两级分类按原体系复刻） ---------- */
const time = P('TIME_TRANSFER_OPTIONS.json').map(o => ({
  v: o.value, l: o.label, p: o.label + '时段光照'
}));

// render_time / render_weather：从工厂函数式源码里取 value + label
const envRaw = R('RENDER_ENVIRONMENT_CONTROLS.txt');
function envOptions(key) {
  const seg = envRaw.split('key: "' + key + '"')[1].split('key: "')[0];
  const out = [];
  const re = /option\$2\(\s*"([^"]*)"\s*,\s*"([^"]*)"/g;
  let m;
  while ((m = re.exec(seg))) out.push({ v: m[1], l: m[2], p: m[2] });
  // twilight 的显式 prompt 覆盖
  if (key === 'render_time') {
    const t = out.find(x => x.v === 'twilight');
    if (t) t.p = '暮光，日落后的微光阶段，天空仍有亮度';
  }
  return out;
}
const renderTime = envOptions('render_time');
const weather = envOptions('render_weather').map(o => ({ ...o, p: o.p + '天气氛围' }));

const season = P('SEASON_TRANSFER_PRESET.json').controls
  .find(c => c.key === 'target_season').options
  .map(o => ({ v: o.value, l: o.label, p: o.label + '季相' }));

const style = P('ART_STYLE_TRANSFER_PRESET.json').controls
  .find(c => c.key === 'target_style').options
  .map(o => ({ v: o.value, l: o.label, p: o.prompt }));

const layout = P('STORYBOARD_PRESET.json').controls
  .find(c => c.key === 'storyboard_layout').options
  .map(o => ({ v: o.value, l: o.label, p: o.prompt }));

function styleOpts(file) {
  return P(file).controls.find(c => c.key === 'design_style').options
    .map(o => ({ v: o.value, l: o.label, p: o.prompt || o.label }));
}
const interiorStyle = styleOpts('INTERIOR_PRESET.json');
const publicInteriorStyle = styleOpts('PUBLIC_INTERIOR_PRESET.json');

// 两级分类：一级是 ...option$1(...)，children 数组里是 option$1(...)
function twoLevel(file, factory) {
  const raw = R(file);
  const chunks = raw.split('...' + factory + '(').slice(1);
  return chunks.map(seg => {
    const head = seg.match(/^\s*"([^"]*)"\s*,\s*"([^"]*)"/);
    if (!head) return null;
    const body = seg.slice(0, seg.indexOf('\n  },'));
    const kids = [];
    const re = new RegExp(factory.replace('$', '\\$') + '\\(\\s*"([^"]*)"\\s*,\\s*"([^"]*)"', 'g');
    let m;
    while ((m = re.exec(body))) {
      if (m[1] !== head[1]) kids.push({ v: m[1], l: m[2], p: m[2] });
    }
    return { v: head[1], l: head[2], p: head[2], children: kids };
  }).filter(Boolean);
}
const building = twoLevel('ARCHITECTURE_BUILDING_CATEGORIES.txt', 'option$1');
const landscape = twoLevel('LANDSCAPE_CATEGORIES.txt', 'option');

const camera = P('CAMERA_SCENE_PRESETS.json').map(o => ({
  v: o.body, l: o.body + ' · ' + o.lens + ' ' + o.focal + ' ' + o.aperture,
  p: o.body + ' 机身，' + o.lens + ' ' + o.focal + 'mm 镜头，光圈 ' + o.aperture
}));
const crop = P('CROP_PRESETS.json').map(o => ({ v: o.key, l: o.label || '自由', p: o.label || '跟随原图' }));
const count = [1, 2, 3, 4].map(n => ({ v: String(n), l: n + ' 张', p: '输出 ' + n + ' 张' }));
const upscale = ['4k', '6k', '8k'].map(v => ({ v, l: v.toUpperCase(), p: v.toUpperCase() + ' 放大' }));
const motion = P('MOTION_TEMPLATES.json').map(o => ({
  v: o.id, l: o.promptSnippetZh, p: o.promptSnippetZh + '（' + o.promptSnippet + '）'
}));

// 8 条风格识别正则：只保留 id / confidence / 正则源码，运行时再 new RegExp
const styleRulesRaw = R('STYLE_RULES.txt');
const styleRules = [];
{
  const re = /\{\s*id:\s*"([^"]+)"\s*,\s*confidence:\s*"([^"]+)"\s*,\s*patterns:\s*\[\s*\/(.+?)\/i\s*\]\s*\}/g;
  let m;
  while ((m = re.exec(styleRulesRaw))) {
    styleRules.push({ id: m[1], confidence: m[2], re: m[3] });
  }
}

/* ---------- 2. S1 结构化预设（schema 复刻，正文按同一写法自撰） ---------- */
// 8 维英文风格表按原维度保留（属于数据字典，不是业务代码）
const styleMap = P('styleMap.json');

// 3 个中文结构化 JSON：沿用「任务/指令/调整/调色逻辑/氛围效果/保留规则/摄影参数/渲染精度」骨架
const d5Structured = P('builtinSampleStructuredPrompts.structured.json');
function structSkeleton(task, instruction, dimensionName, dimension) {
  return {
    '任务': task,
    '指令': instruction,
    [dimensionName]: dimension,
    '调色逻辑': {
      '高光': '按目标状态塑造高光色调与曝光，保持自然的照片级真实感。',
      '中间调': '由主导配色控制气候感知与材质响应，明暗关系连续。',
      '阴影': '阴影色彩与目标环境一致，同时保持原图几何关系。',
      '饱和度': '按目标状态自适应调整，平衡鲜明色彩与真实感。'
    },
    '氛围效果': {
      '天气提示': '在不改变几何的前提下，可包含与目标状态一致的气象迹象。',
      '环境': '空气通透度与能见度按目标状态调整，保持空间纵深。',
      '情绪': '与目标状态匹配的、克制而有电影感的氛围。'
    },
    '保留规则': {
      '保持': '原始构图、建筑几何、行人位置和物体摆放。',
      '避免': '不得改变主体形态、布局或相机透视。'
    },
    '摄影参数': {
      '镜头参数': '标准镜头', '相机型号': '尼康 Z9 (Nikon Z9)',
      '光圈': 'f/8', '快门': '1/60s',
      '拍摄技术': '高动态范围 (HDR) 拍摄，包围曝光，确保细节与阴影层次同时完美呈现。'
    },
    '渲染精度': {
      '分辨率': '超清',
      '画面表现': '摄影，质感通透，细节丰富，植物叶片与材质纹理纤毫毕现。电影级后期调色。'
    }
  };
}
const STRUCT = {
  night: structSkeleton('将图像风格转换为夜景',
    '将输入图像的光照与氛围转换到目标时刻，同时保留所有原有物体、建筑和构图。',
    '光照调整', {
      '时段': d5Structured.Image_Style_Transfer_to_Night['光照调整']['时段'],
      '光源': '低强度天空环境光，加上场景中已有的人工光源。',
      '色温': '以冷色为主（4500K–8000K），辅以暖色灯光点缀。',
      '强度': '控制低照度曝光，保留高光平滑过渡与暗部细节可读性。'
    }),
  winter: structSkeleton('将图像风格转换为冬季',
    '将场景转换为冬季状态，降低植被活跃度，营造寒冷季节氛围，同时保留所有原有物体、建筑和构图。',
    '季节调整', {
      '目标季节': '冬季休眠期，枝叶稀疏，环境呈现寒冷状态。',
      '光照调整': '冷色日光，暖色克制，具有低湿度空气的干净对比。',
      '配色变化': '冷蓝灰中性色、低饱和度大地色，以及少量暖色点缀。',
      '植被变化': '落叶或稀疏树冠、休眠地被，以及符合季节的植物状态。'
    }),
  autumn: structSkeleton('将图像风格转换为秋季',
    '将场景转换为秋季状态，调整季节性叶色并营造平静氛围，同时保留所有原有物体、建筑和构图。',
    '季节调整', {
      '目标季节': '秋季过渡期，叶色转暖，植被密度降低。',
      '光照调整': '较低太阳角度的暖色定向日光，季节性对比更加柔和。',
      '配色变化': '琥珀色、赭石色、锈色、柔和绿色和大地中性色。',
      '植被变化': '局部叶片变色与落叶迹象，同时遵循真实树种的生长规律。'
    }),
  spring: structSkeleton('将图像风格转换为春季',
    '将场景转换为春季状态，恢复植被活跃度并营造和煦氛围，同时保留所有原有物体、建筑和构图。',
    '季节调整', {
      '目标季节': '春季萌发期，新叶嫩绿，花境初开。',
      '光照调整': '柔和明亮的春日天光，暖调克制，对比通透。',
      '配色变化': '嫩绿、浅粉、米白与低饱和大地中性色。',
      '植被变化': '新叶与少量花境，地被返青，避免盛夏般的浓荫。'
    }),
  summer: structSkeleton('将图像风格转换为夏季',
    '将场景转换为夏季状态，强化植被浓荫与明亮通透感，同时保留所有原有物体、建筑和构图。',
    '季节调整', {
      '目标季节': '夏季盛长期，树冠饱满，地被浓密。',
      '光照调整': '高位明亮日光，投影清晰，天空通透。',
      '配色变化': '饱和绿、深绿与明亮的暖灰中性色。',
      '植被变化': '完整树冠、浓密地被，避免秋季色叶与落叶迹象。'
    })
};

// 画风长提示词：按 D5「保持原图已有元素 / 只换表现语言 / 目标画风 / 负面约束」四段式自撰
const ART_STYLE = {
  ink_pen: '保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素，不新增人物、植物、建筑、文字或标注。目标画风：钢笔建筑速写。以高精度钢笔线条、粗细变化、排线与轮廓层级塑造体积，保留门窗、构件与材料分缝；黑白对比强，辅以极少量点缀色。避免粗黑涂抹、脏污和结构模糊。',
  watercolor: '保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素，不新增景物或文字。目标画风：水彩建筑表现。轮廓边界柔和或局部溶解，以分层透明罩染、颜料渗色与纸纹颗粒建立层次；色相过渡柔和、饱和度克制，留白形成呼吸感。避免写实 CG 质感与浓重描边。',
  pencil_sketch: '保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素，不新增人物、植物、建筑、文字或标注。目标画风：石墨铅笔建筑素描。用清晰的主次轮廓、细密排线和轻微擦抹表达体积，保留门窗、构件和材料分缝；以纸白和石墨灰建立层次，背景轻描、主体线条明确。避免粗黑涂抹、脏污和模糊结构。',
  marker_rendering: '保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素。目标画风：建筑马克笔手绘表现。保留利落的细线骨架，以透明叠色、可辨笔触和局部留白表达材质、阴影与空间；采用克制的暖灰、冷灰和低饱和辅助色。避免卡通轮廓、荧光色和写实 CG 质感。',
  technical_linework: '保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素。目标画风：精确的黑白建筑技术线稿。白底黑线，以轮廓、遮挡边界和构件细节的线宽差异组织层级，少量细排线区分现有表面；移除照片纹理及连续明暗渐变。仅描绘原图可见结构，不生成尺寸、标注、剖切线或隐藏构造。',
  white_model: '保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素。目标画风：实体建筑白模摄影质感。将现有建筑和环境表面转译为哑光白色模型材料，玻璃与开口保留通透性、位置及深度；通过统一柔光、接触阴影和灰阶区分体块。不新增模型底座或摄影棚背景，不封堵门窗或抹平细部。',
  ink_wash: '保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素。目标画风：水墨淡彩建筑表现。建筑以细而清晰的墨线保留构造，原有景观和背景以淡墨晕染、干湿变化及克制的灰绿赭石色处理；纸白形成呼吸感。不添加山水、书法、印章或原图不存在的景物。',
  postdigital: '保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素。目标画风：后数字建筑插画。以精密细线叠加低饱和扁平色块、扫描纹理和微弱纸张颗粒；原有建筑使用暖白与灰色，原有植被采用冷灰绿，少量深红点缀形成视觉重点。避免写实 CG、浓重光晕和新增装饰元素。',
  vintage_collage: '保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素。目标画风：复古建筑竞赛拼贴。以原图已有元素作为剪贴内容，组合褪色照片纹理、米白纸底、低饱和暖灰及局部砖红，边缘带细微剪切痕迹和印刷颗粒。不拼入陌生建筑、人物、文字、边框或新场景。',
  risograph: '保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素。目标画风：双色或三色孔版印刷建筑插画。转为清晰线条、有限平涂色块及半调网点，以靛蓝、陶土红和纸白形成层次，使用轻微油墨颗粒。套印偏差仅作为表面质感，不移动建筑轮廓；避免写实渐变与新增海报文字。',
  fresh_collage: '保持原有主体、建筑几何、空间布局与透视，只转换表现语言。目标画风：现代建筑图解风微质感矢量插画。弱化粗重轮廓，用极细干净线条勾勒窗框、栏杆、墙面分缝与地面铺装；低饱和柔和配色，植物用浅绿与雾绿，建筑主体用米白与奶杏色。保留硬边缘矢量阴影塑造体量，大面积纯色中加入极微妙颗粒。拒绝 3D 物理渲染、模糊手绘感与高饱和色彩。',
  pop_art: '保持原有空间布局，只转换表现语言。目标画风：波普拼贴建筑插画，极端 2D 扁平。以黑白灰为主调、砖红色为唯一强调色，用清晰密集的黑色 CAD 硬线勾勒所有结构与细部；移除物理材质与写实光影，局部暗面用半调网点或规则排线。砖红色自由分布在部分建筑体块、地台或雨棚，与大面积留白交织形成平面张力。拒绝立体空间感与除砖红外的任何彩色。'
};

/* ---------- 3. S2 规则常量（按 D5 的 11 组规则分组自撰） ---------- */
const RULES = {
  // ① 最高准则：{最高准则, 要求} 包装法的固定头
  supreme: '执行图中命令：严格保持原图比例、原视角、原机位与 1:1 的空间对齐，在此前提下生成顶尖的可视化效果。',
  // ② 鸟瞰空间对齐（借鉴 AERIAL_RENDER_ALIGNMENT_RULE 的条款结构）
  aerialAlign: '空间对齐：建筑、地形和视角原位不变。道路及水体逐段原位保留，锁定两侧边界、宽度、转折、交叉口、桥涵和出画位置；不得平移、拓宽、拉直、改弯或新增支路。道路只改善原范围内的材质、标线与车辆，植物与配景服从现有边界，不遮盖线位。不明确的线条保留，不猜测补路。',
  // ③ 室内结构保留
  interiorSupreme: '保持原图宽高比、视点、相机角度与 1:1 空间对齐，把给定设计渲染为真实可信的室内摄影。',
  interiorStructure: '原图定义了既定室内设计：保留房间尺寸、墙顶地、门窗洞口、固定柜体、家具轮廓、位置、比例与动线；保持原有画幅、透视、视场与空间关系。不新增房间、洞口、隔墙或家具，不移动物体、不改变层高。所选风格只能在上述边界内调整饰面、材质与现有软装；相机参数只描述摄影质感，不得重新取景或改变透视。',
  publicInteriorStructure: '在室内结构保留条款基础上：仅商业照明补完时，可在既有吊顶、柜体或展示面的合理位置补入小型射灯与隐藏灯带，保留原有灯具；不得新增吊顶造型、灯槽、墙体凹槽、展示构件或结构洞口。',
  // ④ 分镜网格
  storyboard: '所有分格表现同一主体、同一环境：保持身份、数量、衣着、物件设计、建筑、材质与空间关系；机位、景别与景深可变化，但不得为凑镜头而移动物体或重构场景。时段、天气、光线方向与色调保持一致，反射、透视与遮挡随机位自洽。不臆造未见房间或立面，不添加标题、字幕或水印。',
  // ⑤ 时段光照
  timeLighting: '先辨认原图的天空与天气、既有光源、日照投影与亮斑、材质反射、窗洞与遮挡，再决定移除、保留与替换哪些光。夜间必须去掉全部日间直射日光、亮斑与太阳投影（含射入室内的阳光），不是简单压暗或调色；室内窗不再作为强日光发射面，需重建该区域材质本貌后再布光。白天目标需去掉月亮、星空与过量灯光，并按新的太阳方向重算投影方向、长度与软硬。天空亮度、光源方向、表面高光、投影、玻璃与水面反射、室内窗光必须构成同一套相干解；不透明墙体与屋顶必须挡光。保留接触阴影与环境遮蔽，保留原有材质与物体颜色，不做全局染色。',
  // ⑥ 去除标注条款
  annotationRemoval: '最终成片中去除图上用于标注辅助编辑的红色矩形框、箭头、编号气泡等标记，不要保留任何编辑标注。',
  // ⑦ 8 条风格识别（正则 + id + confidence）
  styleRules: styleRules,
  // ⑧ 系统提示词（精简版）
  system: '把附图、所选目标与用户要求合起来，写出针对这张图的编辑指令。只描述图像支持且有明确要求的改动；看不清或未见的特征保持原样，不臆造。这是一次定向图像编辑，不是重新做设计，也不是把图换成建筑摄影。用户手写要求优先于选项，选项优先于推断偏好；不套用固定天气、调色、植被、相机参数或电影特效，不主动补配景。',
  // ⑨ 提示词优化器模板（3 类）
  optimizer: {
    t2i: '把用户的文生图需求整理成可直接使用的自然语言提示词：保留原始意图与硬约束，补全主体、环境、构图、光线、色彩、材质、氛围与可见细节；逐字保留变量占位符、比例、尺寸、数量、位置、文字与禁止项；不输出解释、JSON 包装或代码块。',
    i2i: '把用户的图生图需求整理成自然语言编辑指令：直接写出修改对象、部位与目标状态；原图主体、构图、透视、比例与设计布局作为内部判断依据；未指定时段时默认清晨或白天自然光，未指定机位时保持与原图一致的观察视角与构图；逐字保留变量、比例、尺寸、文字与明确禁止项。',
    multi: '把多图输入整理成自然语言指令：第一张是主体依据，后续图片只作为风格、材质、光影、氛围、构图或细节参考；不混淆主图主体与参考图主体，不把参考图里的无关对象加进最终画面；尽量自然描述参考关系，不机械堆叠「图1/图2」；保持与第一张主图一致的视角与构图。'
  },
  // ⑩ 摄影参数块 / ⑪ 渲染精度块（attachCanvasRenderMetadata 的固定尾段结构）
  photo: { '镜头参数': '标准镜头', '相机型号': '尼康 Z9 (Nikon Z9)', '光圈': 'f/8', '快门': '1/60s', '拍摄技术': '高动态范围 (HDR) 拍摄，包围曝光，确保细节与阴影层次同时完美呈现。' },
  render: { '分辨率': '超清', '画面表现': '摄影，质感通透，细节丰富，植物叶片与材质纹理纤毫毕现。电影级后期调色。' }
};

/* ---------- 4. 组装 ---------- */
const SNC_ARCO = {
  VERSION: '2.4-s123',
  SOURCE: 'D5 Arco 结构化提示词/控件字典体系（仅借鉴 schema 与写法，提示词正文自撰）',
  RULES,
  STRUCT,
  STYLE_MAP: styleMap,
  ART_STYLE,
  CONTROLS: {
    time, renderTime, weather, season, style, layout,
    building, landscape, interiorStyle, publicInteriorStyle,
    camera, crop, count, upscale, motion
  },
  SKILL_KIND: { 'bi-time': 'time', 'bi-season': 'season', 'bi-style': 'style', 'bi-story': 'story' },
  // 控件显示名（S3 参数浮层的分组标题）
  CONTROL_META: [
    { k: 'time', t: '时段', hint: '8 时段 · 时间迁移' },
    { k: 'renderTime', t: '渲染时间', hint: '8 档 · 含暮光覆盖' },
    { k: 'weather', t: '天气', hint: '8 种天气氛围' },
    { k: 'season', t: '季节', hint: '4 季相' },
    { k: 'style', t: '目标画风', hint: '12 种画风' },
    { k: 'layout', t: '分镜布局', hint: '4 / 9 / 16 / 25 宫格' },
    { k: 'building', t: '建筑类型', hint: '两级分类', two: true },
    { k: 'landscape', t: '景观类型', hint: '两级分类', two: true },
    { k: 'interiorStyle', t: '室内风格', hint: '21 项' },
    { k: 'publicInteriorStyle', t: '公装风格', hint: '13 项' },
    { k: 'camera', t: '相机机位', hint: '8 套机身镜头' },
    { k: 'crop', t: '裁剪比例', hint: '8 种画幅' },
    { k: 'count', t: '输出张数', hint: '1–4 张' },
    { k: 'upscale', t: '放大档位', hint: '4K / 6K / 8K' },
    { k: 'motion', t: '运镜描述', hint: motion.length + ' 条中文短句' }
  ]
};

const banner = `/* ============================================================================
 * S1 + S2 + S3 资产层（v2.4）· 由 tools/gen-arco-assets.mjs 生成，请勿手改
 * ----------------------------------------------------------------------------
 * 借鉴 D5 Arco 的「结构化提示词 schema / 控件字典体系 / 规则分组」，
 * 控件 value 与中文 label、两级分类、8 维风格维度、结构化 JSON 字段骨架按原体系复刻；
 * 所有提示词正文按同一写法自撰。未复制任何图片、视频、汇报页 HTML 或业务 JS。
 * 详见《D5 Arco 全量复用盘点.md》第 4 / 6 节。
 * ============================================================================ */
`;
const body = banner + 'var SNC_ARCO = ' + JSON.stringify(SNC_ARCO, null, 2) + ';\n' +
  'if(typeof window !== "undefined"){ try{ window["SNC_ARCO"] = SNC_ARCO; }catch(e){} }\n';

fs.writeFileSync(OUT, body, 'utf8');
console.log('已写入', OUT, fs.statSync(OUT).size, 'bytes');
console.log('控件组:', SNC_ARCO.CONTROL_META.length,
  '| 建筑一级:', building.length, '建筑二级:', building.reduce((a, b) => a + b.children.length, 0),
  '| 景观一级:', landscape.length, '景观二级:', landscape.reduce((a, b) => a + b.children.length, 0),
  '| 风格识别:', styleRules.length,
  '| 画风库:', Object.keys(ART_STYLE).length,
  '| 结构化预设:', Object.keys(STRUCT).length);
