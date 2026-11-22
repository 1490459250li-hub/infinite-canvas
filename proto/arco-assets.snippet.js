/* ============================================================================
 * S1 + S2 + S3 资产层（v2.4）· 由 tools/gen-arco-assets.mjs 生成，请勿手改
 * ----------------------------------------------------------------------------
 * 借鉴 D5 Arco 的「结构化提示词 schema / 控件字典体系 / 规则分组」，
 * 控件 value 与中文 label、两级分类、8 维风格维度、结构化 JSON 字段骨架按原体系复刻；
 * 所有提示词正文按同一写法自撰。未复制任何图片、视频、汇报页 HTML 或业务 JS。
 * 详见《D5 Arco 全量复用盘点.md》第 4 / 6 节。
 * ============================================================================ */
var SNC_ARCO = {
  "VERSION": "2.4-s123",
  "SOURCE": "D5 Arco 结构化提示词/控件字典体系（仅借鉴 schema 与写法，提示词正文自撰）",
  "RULES": {
    "supreme": "执行图中命令：严格保持原图比例、原视角、原机位与 1:1 的空间对齐，在此前提下生成顶尖的可视化效果。",
    "aerialAlign": "空间对齐：建筑、地形和视角原位不变。道路及水体逐段原位保留，锁定两侧边界、宽度、转折、交叉口、桥涵和出画位置；不得平移、拓宽、拉直、改弯或新增支路。道路只改善原范围内的材质、标线与车辆，植物与配景服从现有边界，不遮盖线位。不明确的线条保留，不猜测补路。",
    "interiorSupreme": "保持原图宽高比、视点、相机角度与 1:1 空间对齐，把给定设计渲染为真实可信的室内摄影。",
    "interiorStructure": "原图定义了既定室内设计：保留房间尺寸、墙顶地、门窗洞口、固定柜体、家具轮廓、位置、比例与动线；保持原有画幅、透视、视场与空间关系。不新增房间、洞口、隔墙或家具，不移动物体、不改变层高。所选风格只能在上述边界内调整饰面、材质与现有软装；相机参数只描述摄影质感，不得重新取景或改变透视。",
    "publicInteriorStructure": "在室内结构保留条款基础上：仅商业照明补完时，可在既有吊顶、柜体或展示面的合理位置补入小型射灯与隐藏灯带，保留原有灯具；不得新增吊顶造型、灯槽、墙体凹槽、展示构件或结构洞口。",
    "storyboard": "所有分格表现同一主体、同一环境：保持身份、数量、衣着、物件设计、建筑、材质与空间关系；机位、景别与景深可变化，但不得为凑镜头而移动物体或重构场景。时段、天气、光线方向与色调保持一致，反射、透视与遮挡随机位自洽。不臆造未见房间或立面，不添加标题、字幕或水印。",
    "timeLighting": "先辨认原图的天空与天气、既有光源、日照投影与亮斑、材质反射、窗洞与遮挡，再决定移除、保留与替换哪些光。夜间必须去掉全部日间直射日光、亮斑与太阳投影（含射入室内的阳光），不是简单压暗或调色；室内窗不再作为强日光发射面，需重建该区域材质本貌后再布光。白天目标需去掉月亮、星空与过量灯光，并按新的太阳方向重算投影方向、长度与软硬。天空亮度、光源方向、表面高光、投影、玻璃与水面反射、室内窗光必须构成同一套相干解；不透明墙体与屋顶必须挡光。保留接触阴影与环境遮蔽，保留原有材质与物体颜色，不做全局染色。",
    "annotationRemoval": "最终成片中去除图上用于标注辅助编辑的红色矩形框、箭头、编号气泡等标记，不要保留任何编辑标注。",
    "styleRules": [
      {
        "id": "modern-natural",
        "confidence": "medium",
        "re": "(现代自然|现代风格|现代风|自然现代|modern\\s*natural|modern\\s*style)"
      },
      {
        "id": "retro",
        "confidence": "high",
        "re": "(复古艺术|复古|retro|vintage)"
      },
      {
        "id": "minimal",
        "confidence": "high",
        "re": "(极简主义|极简|简约风|minimalism|minimal)"
      },
      {
        "id": "mediterranean",
        "confidence": "high",
        "re": "(地中海|mediterranean)"
      },
      {
        "id": "new-chinese",
        "confidence": "high",
        "re": "(新中式|中式庭院|new\\s*chinese)"
      },
      {
        "id": "country",
        "confidence": "high",
        "re": "(田园乡村|田园风|乡村风|rustic|country\\s*style|farmhouse)"
      },
      {
        "id": "japandi",
        "confidence": "high",
        "re": "(侘寂日式|侘寂|日式|japandi|wabi[\\s-]*sabi)"
      },
      {
        "id": "eclectic",
        "confidence": "high",
        "re": "(混搭风|混搭|eclectic|mixed\\s*style)"
      }
    ],
    "system": "把附图、所选目标与用户要求合起来，写出针对这张图的编辑指令。只描述图像支持且有明确要求的改动；看不清或未见的特征保持原样，不臆造。这是一次定向图像编辑，不是重新做设计，也不是把图换成建筑摄影。用户手写要求优先于选项，选项优先于推断偏好；不套用固定天气、调色、植被、相机参数或电影特效，不主动补配景。",
    "optimizer": {
      "t2i": "把用户的文生图需求整理成可直接使用的自然语言提示词：保留原始意图与硬约束，补全主体、环境、构图、光线、色彩、材质、氛围与可见细节；逐字保留变量占位符、比例、尺寸、数量、位置、文字与禁止项；不输出解释、JSON 包装或代码块。",
      "i2i": "把用户的图生图需求整理成自然语言编辑指令：直接写出修改对象、部位与目标状态；原图主体、构图、透视、比例与设计布局作为内部判断依据；未指定时段时默认清晨或白天自然光，未指定机位时保持与原图一致的观察视角与构图；逐字保留变量、比例、尺寸、文字与明确禁止项。",
      "multi": "把多图输入整理成自然语言指令：第一张是主体依据，后续图片只作为风格、材质、光影、氛围、构图或细节参考；不混淆主图主体与参考图主体，不把参考图里的无关对象加进最终画面；尽量自然描述参考关系，不机械堆叠「图1/图2」；保持与第一张主图一致的视角与构图。"
    },
    "photo": {
      "镜头参数": "标准镜头",
      "相机型号": "尼康 Z9 (Nikon Z9)",
      "光圈": "f/8",
      "快门": "1/60s",
      "拍摄技术": "高动态范围 (HDR) 拍摄，包围曝光，确保细节与阴影层次同时完美呈现。"
    },
    "render": {
      "分辨率": "超清",
      "画面表现": "摄影，质感通透，细节丰富，植物叶片与材质纹理纤毫毕现。电影级后期调色。"
    }
  },
  "STRUCT": {
    "night": {
      "任务": "将图像风格转换为夜景",
      "指令": "将输入图像的光照与氛围转换到目标时刻，同时保留所有原有物体、建筑和构图。",
      "光照调整": {
        "时段": "夜间 23:00，月光与场景实际灯光。",
        "光源": "低强度天空环境光，加上场景中已有的人工光源。",
        "色温": "以冷色为主（4500K–8000K），辅以暖色灯光点缀。",
        "强度": "控制低照度曝光，保留高光平滑过渡与暗部细节可读性。"
      },
      "调色逻辑": {
        "高光": "按目标状态塑造高光色调与曝光，保持自然的照片级真实感。",
        "中间调": "由主导配色控制气候感知与材质响应，明暗关系连续。",
        "阴影": "阴影色彩与目标环境一致，同时保持原图几何关系。",
        "饱和度": "按目标状态自适应调整，平衡鲜明色彩与真实感。"
      },
      "氛围效果": {
        "天气提示": "在不改变几何的前提下，可包含与目标状态一致的气象迹象。",
        "环境": "空气通透度与能见度按目标状态调整，保持空间纵深。",
        "情绪": "与目标状态匹配的、克制而有电影感的氛围。"
      },
      "保留规则": {
        "保持": "原始构图、建筑几何、行人位置和物体摆放。",
        "避免": "不得改变主体形态、布局或相机透视。"
      },
      "摄影参数": {
        "镜头参数": "标准镜头",
        "相机型号": "尼康 Z9 (Nikon Z9)",
        "光圈": "f/8",
        "快门": "1/60s",
        "拍摄技术": "高动态范围 (HDR) 拍摄，包围曝光，确保细节与阴影层次同时完美呈现。"
      },
      "渲染精度": {
        "分辨率": "超清",
        "画面表现": "摄影，质感通透，细节丰富，植物叶片与材质纹理纤毫毕现。电影级后期调色。"
      }
    },
    "winter": {
      "任务": "将图像风格转换为冬季",
      "指令": "将场景转换为冬季状态，降低植被活跃度，营造寒冷季节氛围，同时保留所有原有物体、建筑和构图。",
      "季节调整": {
        "目标季节": "冬季休眠期，枝叶稀疏，环境呈现寒冷状态。",
        "光照调整": "冷色日光，暖色克制，具有低湿度空气的干净对比。",
        "配色变化": "冷蓝灰中性色、低饱和度大地色，以及少量暖色点缀。",
        "植被变化": "落叶或稀疏树冠、休眠地被，以及符合季节的植物状态。"
      },
      "调色逻辑": {
        "高光": "按目标状态塑造高光色调与曝光，保持自然的照片级真实感。",
        "中间调": "由主导配色控制气候感知与材质响应，明暗关系连续。",
        "阴影": "阴影色彩与目标环境一致，同时保持原图几何关系。",
        "饱和度": "按目标状态自适应调整，平衡鲜明色彩与真实感。"
      },
      "氛围效果": {
        "天气提示": "在不改变几何的前提下，可包含与目标状态一致的气象迹象。",
        "环境": "空气通透度与能见度按目标状态调整，保持空间纵深。",
        "情绪": "与目标状态匹配的、克制而有电影感的氛围。"
      },
      "保留规则": {
        "保持": "原始构图、建筑几何、行人位置和物体摆放。",
        "避免": "不得改变主体形态、布局或相机透视。"
      },
      "摄影参数": {
        "镜头参数": "标准镜头",
        "相机型号": "尼康 Z9 (Nikon Z9)",
        "光圈": "f/8",
        "快门": "1/60s",
        "拍摄技术": "高动态范围 (HDR) 拍摄，包围曝光，确保细节与阴影层次同时完美呈现。"
      },
      "渲染精度": {
        "分辨率": "超清",
        "画面表现": "摄影，质感通透，细节丰富，植物叶片与材质纹理纤毫毕现。电影级后期调色。"
      }
    },
    "autumn": {
      "任务": "将图像风格转换为秋季",
      "指令": "将场景转换为秋季状态，调整季节性叶色并营造平静氛围，同时保留所有原有物体、建筑和构图。",
      "季节调整": {
        "目标季节": "秋季过渡期，叶色转暖，植被密度降低。",
        "光照调整": "较低太阳角度的暖色定向日光，季节性对比更加柔和。",
        "配色变化": "琥珀色、赭石色、锈色、柔和绿色和大地中性色。",
        "植被变化": "局部叶片变色与落叶迹象，同时遵循真实树种的生长规律。"
      },
      "调色逻辑": {
        "高光": "按目标状态塑造高光色调与曝光，保持自然的照片级真实感。",
        "中间调": "由主导配色控制气候感知与材质响应，明暗关系连续。",
        "阴影": "阴影色彩与目标环境一致，同时保持原图几何关系。",
        "饱和度": "按目标状态自适应调整，平衡鲜明色彩与真实感。"
      },
      "氛围效果": {
        "天气提示": "在不改变几何的前提下，可包含与目标状态一致的气象迹象。",
        "环境": "空气通透度与能见度按目标状态调整，保持空间纵深。",
        "情绪": "与目标状态匹配的、克制而有电影感的氛围。"
      },
      "保留规则": {
        "保持": "原始构图、建筑几何、行人位置和物体摆放。",
        "避免": "不得改变主体形态、布局或相机透视。"
      },
      "摄影参数": {
        "镜头参数": "标准镜头",
        "相机型号": "尼康 Z9 (Nikon Z9)",
        "光圈": "f/8",
        "快门": "1/60s",
        "拍摄技术": "高动态范围 (HDR) 拍摄，包围曝光，确保细节与阴影层次同时完美呈现。"
      },
      "渲染精度": {
        "分辨率": "超清",
        "画面表现": "摄影，质感通透，细节丰富，植物叶片与材质纹理纤毫毕现。电影级后期调色。"
      }
    },
    "spring": {
      "任务": "将图像风格转换为春季",
      "指令": "将场景转换为春季状态，恢复植被活跃度并营造和煦氛围，同时保留所有原有物体、建筑和构图。",
      "季节调整": {
        "目标季节": "春季萌发期，新叶嫩绿，花境初开。",
        "光照调整": "柔和明亮的春日天光，暖调克制，对比通透。",
        "配色变化": "嫩绿、浅粉、米白与低饱和大地中性色。",
        "植被变化": "新叶与少量花境，地被返青，避免盛夏般的浓荫。"
      },
      "调色逻辑": {
        "高光": "按目标状态塑造高光色调与曝光，保持自然的照片级真实感。",
        "中间调": "由主导配色控制气候感知与材质响应，明暗关系连续。",
        "阴影": "阴影色彩与目标环境一致，同时保持原图几何关系。",
        "饱和度": "按目标状态自适应调整，平衡鲜明色彩与真实感。"
      },
      "氛围效果": {
        "天气提示": "在不改变几何的前提下，可包含与目标状态一致的气象迹象。",
        "环境": "空气通透度与能见度按目标状态调整，保持空间纵深。",
        "情绪": "与目标状态匹配的、克制而有电影感的氛围。"
      },
      "保留规则": {
        "保持": "原始构图、建筑几何、行人位置和物体摆放。",
        "避免": "不得改变主体形态、布局或相机透视。"
      },
      "摄影参数": {
        "镜头参数": "标准镜头",
        "相机型号": "尼康 Z9 (Nikon Z9)",
        "光圈": "f/8",
        "快门": "1/60s",
        "拍摄技术": "高动态范围 (HDR) 拍摄，包围曝光，确保细节与阴影层次同时完美呈现。"
      },
      "渲染精度": {
        "分辨率": "超清",
        "画面表现": "摄影，质感通透，细节丰富，植物叶片与材质纹理纤毫毕现。电影级后期调色。"
      }
    },
    "summer": {
      "任务": "将图像风格转换为夏季",
      "指令": "将场景转换为夏季状态，强化植被浓荫与明亮通透感，同时保留所有原有物体、建筑和构图。",
      "季节调整": {
        "目标季节": "夏季盛长期，树冠饱满，地被浓密。",
        "光照调整": "高位明亮日光，投影清晰，天空通透。",
        "配色变化": "饱和绿、深绿与明亮的暖灰中性色。",
        "植被变化": "完整树冠、浓密地被，避免秋季色叶与落叶迹象。"
      },
      "调色逻辑": {
        "高光": "按目标状态塑造高光色调与曝光，保持自然的照片级真实感。",
        "中间调": "由主导配色控制气候感知与材质响应，明暗关系连续。",
        "阴影": "阴影色彩与目标环境一致，同时保持原图几何关系。",
        "饱和度": "按目标状态自适应调整，平衡鲜明色彩与真实感。"
      },
      "氛围效果": {
        "天气提示": "在不改变几何的前提下，可包含与目标状态一致的气象迹象。",
        "环境": "空气通透度与能见度按目标状态调整，保持空间纵深。",
        "情绪": "与目标状态匹配的、克制而有电影感的氛围。"
      },
      "保留规则": {
        "保持": "原始构图、建筑几何、行人位置和物体摆放。",
        "避免": "不得改变主体形态、布局或相机透视。"
      },
      "摄影参数": {
        "镜头参数": "标准镜头",
        "相机型号": "尼康 Z9 (Nikon Z9)",
        "光圈": "f/8",
        "快门": "1/60s",
        "拍摄技术": "高动态范围 (HDR) 拍摄，包围曝光，确保细节与阴影层次同时完美呈现。"
      },
      "渲染精度": {
        "分辨率": "超清",
        "画面表现": "摄影，质感通透，细节丰富，植物叶片与材质纹理纤毫毕现。电影级后期调色。"
      }
    }
  },
  "STYLE_MAP": {
    "ink_pen": {
      "task": "Image_Style_Transfer_to_Ink_Pen_Drawing",
      "style_name": "Ink Pen Drawing",
      "instruction": "Transform the input image into a pen-and-ink drawing style while preserving all original objects, architecture, and composition.",
      "line_language": "High-precision pen strokes with varied line weight, hatching, and contour hierarchy",
      "texture_logic": "Cross-hatching and stippling-driven tonal construction with minimal smooth shading",
      "color_logic": "Primarily monochrome or limited accent tones with strong black-white contrast control",
      "atmosphere": "Graphic illustration depth through line density and negative-space rhythm",
      "mood": "Analytical, handcrafted, and editorial"
    },
    "watercolor": {
      "task": "Image_Style_Transfer_to_Watercolor",
      "style_name": "Watercolor Painting",
      "instruction": "Transform the input image into a watercolor painting style while preserving all original objects, architecture, and composition.",
      "line_language": "Soft or partially dissolved contour boundaries with painterly edge variation",
      "texture_logic": "Layered translucent washes, pigment bleed, and paper-grain interaction",
      "color_logic": "Gentle hue transitions, diluted tonal overlays, and atmospheric blending",
      "atmosphere": "Breathable painterly space with soft ambient transitions",
      "mood": "Poetic, light, and tranquil"
    }
  },
  "ART_STYLE": {
    "ink_pen": "保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素，不新增人物、植物、建筑、文字或标注。目标画风：钢笔建筑速写。以高精度钢笔线条、粗细变化、排线与轮廓层级塑造体积，保留门窗、构件与材料分缝；黑白对比强，辅以极少量点缀色。避免粗黑涂抹、脏污和结构模糊。",
    "watercolor": "保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素，不新增景物或文字。目标画风：水彩建筑表现。轮廓边界柔和或局部溶解，以分层透明罩染、颜料渗色与纸纹颗粒建立层次；色相过渡柔和、饱和度克制，留白形成呼吸感。避免写实 CG 质感与浓重描边。",
    "pencil_sketch": "保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素，不新增人物、植物、建筑、文字或标注。目标画风：石墨铅笔建筑素描。用清晰的主次轮廓、细密排线和轻微擦抹表达体积，保留门窗、构件和材料分缝；以纸白和石墨灰建立层次，背景轻描、主体线条明确。避免粗黑涂抹、脏污和模糊结构。",
    "marker_rendering": "保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素。目标画风：建筑马克笔手绘表现。保留利落的细线骨架，以透明叠色、可辨笔触和局部留白表达材质、阴影与空间；采用克制的暖灰、冷灰和低饱和辅助色。避免卡通轮廓、荧光色和写实 CG 质感。",
    "technical_linework": "保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素。目标画风：精确的黑白建筑技术线稿。白底黑线，以轮廓、遮挡边界和构件细节的线宽差异组织层级，少量细排线区分现有表面；移除照片纹理及连续明暗渐变。仅描绘原图可见结构，不生成尺寸、标注、剖切线或隐藏构造。",
    "white_model": "保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素。目标画风：实体建筑白模摄影质感。将现有建筑和环境表面转译为哑光白色模型材料，玻璃与开口保留通透性、位置及深度；通过统一柔光、接触阴影和灰阶区分体块。不新增模型底座或摄影棚背景，不封堵门窗或抹平细部。",
    "ink_wash": "保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素。目标画风：水墨淡彩建筑表现。建筑以细而清晰的墨线保留构造，原有景观和背景以淡墨晕染、干湿变化及克制的灰绿赭石色处理；纸白形成呼吸感。不添加山水、书法、印章或原图不存在的景物。",
    "postdigital": "保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素。目标画风：后数字建筑插画。以精密细线叠加低饱和扁平色块、扫描纹理和微弱纸张颗粒；原有建筑使用暖白与灰色，原有植被采用冷灰绿，少量深红点缀形成视觉重点。避免写实 CG、浓重光晕和新增装饰元素。",
    "vintage_collage": "保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素。目标画风：复古建筑竞赛拼贴。以原图已有元素作为剪贴内容，组合褪色照片纹理、米白纸底、低饱和暖灰及局部砖红，边缘带细微剪切痕迹和印刷颗粒。不拼入陌生建筑、人物、文字、边框或新场景。",
    "risograph": "保持原有主体、建筑几何、空间布局、比例、视角、画幅及元素位置，只转换表现语言；仅处理原图已有元素。目标画风：双色或三色孔版印刷建筑插画。转为清晰线条、有限平涂色块及半调网点，以靛蓝、陶土红和纸白形成层次，使用轻微油墨颗粒。套印偏差仅作为表面质感，不移动建筑轮廓；避免写实渐变与新增海报文字。",
    "fresh_collage": "保持原有主体、建筑几何、空间布局与透视，只转换表现语言。目标画风：现代建筑图解风微质感矢量插画。弱化粗重轮廓，用极细干净线条勾勒窗框、栏杆、墙面分缝与地面铺装；低饱和柔和配色，植物用浅绿与雾绿，建筑主体用米白与奶杏色。保留硬边缘矢量阴影塑造体量，大面积纯色中加入极微妙颗粒。拒绝 3D 物理渲染、模糊手绘感与高饱和色彩。",
    "pop_art": "保持原有空间布局，只转换表现语言。目标画风：波普拼贴建筑插画，极端 2D 扁平。以黑白灰为主调、砖红色为唯一强调色，用清晰密集的黑色 CAD 硬线勾勒所有结构与细部；移除物理材质与写实光影，局部暗面用半调网点或规则排线。砖红色自由分布在部分建筑体块、地台或雨棚，与大面积留白交织形成平面张力。拒绝立体空间感与除砖红外的任何彩色。"
  },
  "CONTROLS": {
    "time": [
      {
        "v": "predawn",
        "l": "凌晨",
        "p": "凌晨时段光照"
      },
      {
        "v": "early_morning",
        "l": "清晨",
        "p": "清晨时段光照"
      },
      {
        "v": "morning",
        "l": "上午",
        "p": "上午时段光照"
      },
      {
        "v": "noon",
        "l": "正午",
        "p": "正午时段光照"
      },
      {
        "v": "afternoon",
        "l": "下午",
        "p": "下午时段光照"
      },
      {
        "v": "evening",
        "l": "傍晚",
        "p": "傍晚时段光照"
      },
      {
        "v": "nightfall",
        "l": "入夜",
        "p": "入夜时段光照"
      },
      {
        "v": "deep_night",
        "l": "深夜",
        "p": "深夜时段光照"
      }
    ],
    "renderTime": [
      {
        "v": "",
        "l": "自动",
        "p": "自动"
      },
      {
        "v": "early_morning",
        "l": "清晨",
        "p": "清晨"
      },
      {
        "v": "morning",
        "l": "上午",
        "p": "上午"
      },
      {
        "v": "noon",
        "l": "正午",
        "p": "正午"
      },
      {
        "v": "afternoon",
        "l": "午后",
        "p": "午后"
      },
      {
        "v": "sunset",
        "l": "日落",
        "p": "日落"
      },
      {
        "v": "twilight",
        "l": "暮光",
        "p": "暮光，日落后的微光阶段，天空仍有亮度"
      },
      {
        "v": "night",
        "l": "夜间",
        "p": "夜间"
      }
    ],
    "weather": [
      {
        "v": "",
        "l": "自动",
        "p": "自动天气氛围"
      },
      {
        "v": "clear",
        "l": "晴朗",
        "p": "晴朗天气氛围"
      },
      {
        "v": "mostly_clear",
        "l": "少云",
        "p": "少云天气氛围"
      },
      {
        "v": "partly_cloudy",
        "l": "多云",
        "p": "多云天气氛围"
      },
      {
        "v": "overcast",
        "l": "阴天",
        "p": "阴天天气氛围"
      },
      {
        "v": "mist",
        "l": "薄雾",
        "p": "薄雾天气氛围"
      },
      {
        "v": "drizzle",
        "l": "细雨",
        "p": "细雨天气氛围"
      },
      {
        "v": "snow",
        "l": "降雪",
        "p": "降雪天气氛围"
      }
    ],
    "season": [
      {
        "v": "spring",
        "l": "春季",
        "p": "春季季相"
      },
      {
        "v": "summer",
        "l": "夏季",
        "p": "夏季季相"
      },
      {
        "v": "autumn",
        "l": "秋季",
        "p": "秋季季相"
      },
      {
        "v": "winter",
        "l": "冬季",
        "p": "冬季季相"
      }
    ],
    "style": [
      {
        "v": "ink_pen",
        "l": "钢笔画",
        "p": "ink pen drawing"
      },
      {
        "v": "watercolor",
        "l": "水彩画",
        "p": "watercolor painting"
      },
      {
        "v": "fresh_collage",
        "l": "小清新拼贴",
        "p": "fresh minimal textured vector architectural illustration"
      },
      {
        "v": "pop_art",
        "l": "波普风艺术",
        "p": "pop art collage architectural line drawing illustration"
      },
      {
        "v": "pencil_sketch",
        "l": "铅笔素描",
        "p": "Pencil Sketch"
      },
      {
        "v": "marker_rendering",
        "l": "马克笔手绘",
        "p": "Marker Rendering"
      },
      {
        "v": "technical_linework",
        "l": "建筑技术线稿",
        "p": "Architectural Linework"
      },
      {
        "v": "white_model",
        "l": "白模表现",
        "p": "White Model"
      },
      {
        "v": "postdigital",
        "l": "后数字建筑插画",
        "p": "Post-digital Illustration"
      },
      {
        "v": "vintage_collage",
        "l": "复古建筑拼贴",
        "p": "Vintage Architectural Collage"
      },
      {
        "v": "ink_wash",
        "l": "水墨淡彩",
        "p": "Ink Wash"
      },
      {
        "v": "risograph",
        "l": "孔版印刷",
        "p": "Risograph"
      }
    ],
    "layout": [
      {
        "v": "grid_4",
        "l": "四宫格",
        "p": "把这张图变成四宫格的分镜图"
      },
      {
        "v": "grid_9",
        "l": "九宫格",
        "p": "把这张图变成九宫格的分镜图"
      },
      {
        "v": "grid_16",
        "l": "十六宫格",
        "p": "把这张图变成十六宫格的分镜图"
      },
      {
        "v": "grid_25",
        "l": "二十五宫格",
        "p": "把这张图变成二十五宫格的分镜图"
      }
    ],
    "building": [
      {
        "v": "office",
        "l": "办公建筑",
        "p": "办公建筑",
        "children": [
          {
            "v": "high_rise_office",
            "l": "高层办公",
            "p": "高层办公"
          },
          {
            "v": "mid_rise_office",
            "l": "多层办公",
            "p": "多层办公"
          },
          {
            "v": "office_park",
            "l": "办公园区",
            "p": "办公园区"
          },
          {
            "v": "corporate_headquarters",
            "l": "企业总部",
            "p": "企业总部"
          },
          {
            "v": "general_office",
            "l": "通用办公建筑",
            "p": "通用办公建筑"
          },
          {
            "v": "office_aerial",
            "l": "办公楼鸟瞰",
            "p": "办公楼鸟瞰"
          },
          {
            "v": "office_park_aerial",
            "l": "产业园鸟瞰",
            "p": "产业园鸟瞰"
          }
        ]
      },
      {
        "v": "commercial",
        "l": "商业建筑",
        "p": "商业建筑",
        "children": [
          {
            "v": "flagship_store",
            "l": "品牌旗舰店",
            "p": "品牌旗舰店"
          },
          {
            "v": "commercial_street",
            "l": "商业街",
            "p": "商业街"
          },
          {
            "v": "shopping_mall",
            "l": "购物中心",
            "p": "购物中心"
          },
          {
            "v": "sales_center",
            "l": "营销中心",
            "p": "营销中心"
          },
          {
            "v": "general_commercial",
            "l": "通用商业建筑",
            "p": "通用商业建筑"
          },
          {
            "v": "commercial_aerial",
            "l": "商业综合体鸟瞰",
            "p": "商业综合体鸟瞰"
          }
        ]
      },
      {
        "v": "residential",
        "l": "住宅建筑",
        "p": "住宅建筑",
        "children": [
          {
            "v": "villa",
            "l": "别墅",
            "p": "别墅"
          },
          {
            "v": "mid_rise_residence",
            "l": "多层住宅",
            "p": "多层住宅"
          },
          {
            "v": "high_rise_residence",
            "l": "高层住宅",
            "p": "高层住宅"
          },
          {
            "v": "apartment",
            "l": "公寓",
            "p": "公寓"
          },
          {
            "v": "general_residential",
            "l": "通用住宅建筑",
            "p": "通用住宅建筑"
          },
          {
            "v": "residential_aerial",
            "l": "住宅区鸟瞰",
            "p": "住宅区鸟瞰"
          }
        ]
      },
      {
        "v": "hospitality",
        "l": "酒店建筑",
        "p": "酒店建筑",
        "children": [
          {
            "v": "urban_hotel",
            "l": "城市酒店",
            "p": "城市酒店"
          },
          {
            "v": "resort_hotel",
            "l": "度假酒店",
            "p": "度假酒店"
          },
          {
            "v": "boutique_inn",
            "l": "民宿",
            "p": "民宿"
          },
          {
            "v": "general_hotel",
            "l": "通用酒店建筑",
            "p": "通用酒店建筑"
          },
          {
            "v": "resort_aerial",
            "l": "度假村鸟瞰",
            "p": "度假村鸟瞰"
          }
        ]
      },
      {
        "v": "education",
        "l": "教育建筑",
        "p": "教育建筑",
        "children": [
          {
            "v": "kindergarten",
            "l": "幼儿园",
            "p": "幼儿园"
          },
          {
            "v": "school_campus",
            "l": "校园建筑",
            "p": "校园建筑"
          },
          {
            "v": "student_housing",
            "l": "学生宿舍",
            "p": "学生宿舍"
          },
          {
            "v": "research_center",
            "l": "科研中心",
            "p": "科研中心"
          },
          {
            "v": "general_education",
            "l": "通用学校建筑",
            "p": "通用学校建筑"
          },
          {
            "v": "campus_aerial",
            "l": "校园鸟瞰",
            "p": "校园鸟瞰"
          }
        ]
      },
      {
        "v": "culture",
        "l": "公共文化",
        "p": "公共文化",
        "children": [
          {
            "v": "museum_gallery",
            "l": "博物馆与美术馆",
            "p": "博物馆与美术馆"
          },
          {
            "v": "theater_concert",
            "l": "剧院与音乐厅",
            "p": "剧院与音乐厅"
          },
          {
            "v": "library",
            "l": "图书馆",
            "p": "图书馆"
          },
          {
            "v": "convention_center",
            "l": "会展中心",
            "p": "会展中心"
          },
          {
            "v": "stadium",
            "l": "体育场馆",
            "p": "体育场馆"
          },
          {
            "v": "religious",
            "l": "宗教建筑",
            "p": "宗教建筑"
          },
          {
            "v": "community_center",
            "l": "社区中心",
            "p": "社区中心"
          },
          {
            "v": "general_culture",
            "l": "通用公共文化建筑",
            "p": "通用公共文化建筑"
          },
          {
            "v": "culture_aerial",
            "l": "文化建筑鸟瞰",
            "p": "文化建筑鸟瞰"
          },
          {
            "v": "sports_aerial",
            "l": "体育建筑鸟瞰",
            "p": "体育建筑鸟瞰"
          }
        ]
      },
      {
        "v": "healthcare",
        "l": "医疗康养",
        "p": "医疗康养",
        "children": [
          {
            "v": "hospital",
            "l": "医院",
            "p": "医院"
          },
          {
            "v": "wellness_center",
            "l": "康养中心",
            "p": "康养中心"
          },
          {
            "v": "general_healthcare",
            "l": "通用医疗建筑",
            "p": "通用医疗建筑"
          }
        ]
      },
      {
        "v": "countryside",
        "l": "乡村农业",
        "p": "乡村农业",
        "children": [
          {
            "v": "rural_house",
            "l": "乡村民居",
            "p": "乡村民居"
          },
          {
            "v": "agricultural",
            "l": "农业建筑",
            "p": "农业建筑"
          },
          {
            "v": "rural_public",
            "l": "乡村公共服务设施",
            "p": "乡村公共服务设施"
          },
          {
            "v": "general_agricultural",
            "l": "通用农业建筑",
            "p": "通用农业建筑"
          },
          {
            "v": "agricultural_aerial",
            "l": "农业鸟瞰",
            "p": "农业鸟瞰"
          }
        ]
      },
      {
        "v": "industrial",
        "l": "工业建筑",
        "p": "工业建筑",
        "children": [
          {
            "v": "factory",
            "l": "工厂",
            "p": "工厂"
          },
          {
            "v": "warehouse",
            "l": "仓储物流",
            "p": "仓储物流"
          },
          {
            "v": "data_center",
            "l": "数据中心",
            "p": "数据中心"
          },
          {
            "v": "industrial_renovation",
            "l": "改造类工业建筑",
            "p": "改造类工业建筑"
          },
          {
            "v": "general_industrial",
            "l": "通用工业建筑",
            "p": "通用工业建筑"
          },
          {
            "v": "industrial_aerial",
            "l": "工业建筑鸟瞰",
            "p": "工业建筑鸟瞰"
          }
        ]
      },
      {
        "v": "transport",
        "l": "交通建筑",
        "p": "交通建筑",
        "children": [
          {
            "v": "bus_station",
            "l": "汽车客运站",
            "p": "汽车客运站"
          },
          {
            "v": "railway_metro",
            "l": "铁路与地铁车站",
            "p": "铁路与地铁车站"
          },
          {
            "v": "airport",
            "l": "机场",
            "p": "机场"
          },
          {
            "v": "bridge",
            "l": "桥梁",
            "p": "桥梁"
          },
          {
            "v": "pedestrian_bridge",
            "l": "人行天桥",
            "p": "人行天桥"
          },
          {
            "v": "parking_structure",
            "l": "停车楼",
            "p": "停车楼"
          },
          {
            "v": "port_terminal",
            "l": "港口与码头",
            "p": "港口与码头"
          },
          {
            "v": "general_transport",
            "l": "通用交通建筑",
            "p": "通用交通建筑"
          },
          {
            "v": "station_aerial",
            "l": "车站鸟瞰",
            "p": "车站鸟瞰"
          }
        ]
      },
      {
        "v": "urban_planning",
        "l": "城市规划",
        "p": "城市规划",
        "children": [
          {
            "v": "cbd",
            "l": "中央商务区",
            "p": "中央商务区"
          },
          {
            "v": "master_plan",
            "l": "城市总体规划",
            "p": "城市总体规划"
          },
          {
            "v": "residential_planning",
            "l": "住宅区规划",
            "p": "住宅区规划"
          },
          {
            "v": "tod",
            "l": "TOD 片区",
            "p": "TOD 片区"
          }
        ]
      },
      {
        "v": "general_architecture",
        "l": "通用建筑",
        "p": "通用建筑",
        "children": [
          {
            "v": "general_building",
            "l": "通用建筑设计",
            "p": "通用建筑设计"
          },
          {
            "v": "mixed_use",
            "l": "城市综合体",
            "p": "城市综合体"
          }
        ]
      }
    ],
    "landscape": [
      {
        "v": "public_realm",
        "l": "城市开放空间",
        "p": "城市开放空间",
        "children": [
          {
            "v": "pocket_park",
            "l": "口袋公园",
            "p": "口袋公园"
          },
          {
            "v": "urban_park",
            "l": "城市公园",
            "p": "城市公园"
          },
          {
            "v": "public_square",
            "l": "城市广场",
            "p": "城市广场"
          },
          {
            "v": "greenway",
            "l": "绿道",
            "p": "绿道"
          },
          {
            "v": "playground",
            "l": "健身及儿童游乐",
            "p": "健身及儿童游乐"
          },
          {
            "v": "general_urban_park",
            "l": "通用城市公园",
            "p": "通用城市公园"
          },
          {
            "v": "park_aerial",
            "l": "公园鸟瞰",
            "p": "公园鸟瞰"
          }
        ]
      },
      {
        "v": "nature_parks",
        "l": "城郊公园",
        "p": "城郊公园",
        "children": [
          {
            "v": "wetland",
            "l": "生态湿地",
            "p": "生态湿地"
          },
          {
            "v": "country_park",
            "l": "郊野公园",
            "p": "郊野公园"
          },
          {
            "v": "national_park",
            "l": "原生态国家公园",
            "p": "原生态国家公园"
          },
          {
            "v": "camping_site",
            "l": "露营公园",
            "p": "露营公园"
          },
          {
            "v": "general_nature_park",
            "l": "通用城郊公园",
            "p": "通用城郊公园"
          }
        ]
      },
      {
        "v": "commercial_office",
        "l": "商业办公",
        "p": "商业办公",
        "children": [
          {
            "v": "pedestrian_street",
            "l": "商业步行街",
            "p": "商业步行街"
          },
          {
            "v": "forecourt",
            "l": "商业办公前广场",
            "p": "商业办公前广场"
          },
          {
            "v": "outdoor_dining",
            "l": "商业外摆",
            "p": "商业外摆"
          },
          {
            "v": "office_campus",
            "l": "办公园区景观",
            "p": "办公园区景观"
          },
          {
            "v": "general_commercial_office",
            "l": "通用商业办公景观",
            "p": "通用商业办公景观"
          }
        ]
      },
      {
        "v": "residential_courtyard",
        "l": "住宅花园",
        "p": "住宅花园",
        "children": [
          {
            "v": "private_garden",
            "l": "私家花园",
            "p": "私家花园"
          },
          {
            "v": "community_space",
            "l": "住宅公共景观",
            "p": "住宅公共景观"
          },
          {
            "v": "sales_center_display",
            "l": "售楼处展示区",
            "p": "售楼处展示区"
          },
          {
            "v": "rooftop_garden",
            "l": "屋顶花园",
            "p": "屋顶花园"
          },
          {
            "v": "entrance_court",
            "l": "入口空间",
            "p": "入口空间"
          },
          {
            "v": "general_courtyard",
            "l": "通用庭院景观",
            "p": "通用庭院景观"
          },
          {
            "v": "courtyard_aerial",
            "l": "庭院鸟瞰",
            "p": "庭院鸟瞰"
          }
        ]
      },
      {
        "v": "hospitality_landscape",
        "l": "酒店度假景观",
        "p": "酒店度假景观",
        "children": [
          {
            "v": "hotel_grounds",
            "l": "酒店场地景观",
            "p": "酒店场地景观"
          },
          {
            "v": "resort_landscape",
            "l": "度假村景观",
            "p": "度假村景观"
          },
          {
            "v": "pool_deck",
            "l": "酒店泳池",
            "p": "酒店泳池"
          },
          {
            "v": "boutique_inn_landscape",
            "l": "民宿景观",
            "p": "民宿景观"
          },
          {
            "v": "general_hospitality",
            "l": "通用酒店景观",
            "p": "通用酒店景观"
          }
        ]
      },
      {
        "v": "cultural_landscape",
        "l": "公共文化景观",
        "p": "公共文化景观",
        "children": [
          {
            "v": "campus_landscape",
            "l": "校园景观",
            "p": "校园景观"
          },
          {
            "v": "cultural_plaza",
            "l": "文化设施景观",
            "p": "文化设施景观"
          },
          {
            "v": "heritage_site",
            "l": "文化遗址",
            "p": "文化遗址"
          },
          {
            "v": "stadium_landscape",
            "l": "体育场馆景观",
            "p": "体育场馆景观"
          },
          {
            "v": "medical_campus",
            "l": "医疗康养景观",
            "p": "医疗康养景观"
          },
          {
            "v": "religious_landscape",
            "l": "宗教景观",
            "p": "宗教景观"
          },
          {
            "v": "general_cultural",
            "l": "通用文化景观",
            "p": "通用文化景观"
          }
        ]
      },
      {
        "v": "rural_agricultural",
        "l": "乡村农业景观",
        "p": "乡村农业景观",
        "children": [
          {
            "v": "agritourism",
            "l": "农业观光园",
            "p": "农业观光园"
          },
          {
            "v": "terraced_landscape",
            "l": "梯田景观",
            "p": "梯田景观"
          },
          {
            "v": "rural_complex",
            "l": "田园综合体",
            "p": "田园综合体"
          },
          {
            "v": "village_landscape",
            "l": "美丽乡村",
            "p": "美丽乡村"
          },
          {
            "v": "themed_town",
            "l": "特色小镇",
            "p": "特色小镇"
          },
          {
            "v": "cultural_tourism",
            "l": "文旅度假",
            "p": "文旅度假"
          },
          {
            "v": "general_rural",
            "l": "通用农业农村景观",
            "p": "通用农业农村景观"
          }
        ]
      },
      {
        "v": "transport_landscape",
        "l": "道路交通",
        "p": "道路交通",
        "children": [
          {
            "v": "boulevard",
            "l": "景观大道",
            "p": "景观大道"
          },
          {
            "v": "overpass_greening",
            "l": "桥梁与高架绿化",
            "p": "桥梁与高架绿化"
          },
          {
            "v": "station_forecourt",
            "l": "站前空间",
            "p": "站前空间"
          },
          {
            "v": "general_transport_landscape",
            "l": "通用交通景观",
            "p": "通用交通景观"
          }
        ]
      },
      {
        "v": "landscape_styles",
        "l": "造园风格",
        "p": "造园风格",
        "children": [
          {
            "v": "chinese_garden",
            "l": "中式园林",
            "p": "中式园林"
          },
          {
            "v": "zen_courtyard",
            "l": "禅意庭院",
            "p": "禅意庭院"
          },
          {
            "v": "tropical_garden",
            "l": "热带风情",
            "p": "热带风情"
          },
          {
            "v": "desert_oasis",
            "l": "沙漠绿洲",
            "p": "沙漠绿洲"
          },
          {
            "v": "european_formal",
            "l": "欧洲皇家园林",
            "p": "欧洲皇家园林"
          },
          {
            "v": "mediterranean_garden",
            "l": "地中海景观",
            "p": "地中海景观"
          }
        ]
      },
      {
        "v": "structures_features",
        "l": "构筑与小品",
        "p": "构筑与小品",
        "children": [
          {
            "v": "landscape_lighting",
            "l": "景观灯具",
            "p": "景观灯具"
          },
          {
            "v": "outdoor_seating",
            "l": "户外座椅",
            "p": "户外座椅"
          },
          {
            "v": "sculpture_installation",
            "l": "艺术装置",
            "p": "艺术装置"
          },
          {
            "v": "landscape_features",
            "l": "景观小品",
            "p": "景观小品"
          },
          {
            "v": "landscape_structures",
            "l": "构筑物",
            "p": "构筑物"
          },
          {
            "v": "landscape_bridge",
            "l": "景观桥",
            "p": "景观桥"
          },
          {
            "v": "general_features",
            "l": "通用景观装置",
            "p": "通用景观装置"
          }
        ]
      },
      {
        "v": "waterscape",
        "l": "水景设计",
        "p": "水景设计",
        "children": [
          {
            "v": "waterscape_garden",
            "l": "水景庭院",
            "p": "水景庭院"
          },
          {
            "v": "fountain_plaza",
            "l": "喷泉广场",
            "p": "喷泉广场"
          },
          {
            "v": "urban_waterfront",
            "l": "滨水界面",
            "p": "滨水界面"
          },
          {
            "v": "natural_waterfront",
            "l": "自然水景",
            "p": "自然水景"
          },
          {
            "v": "general_waterscape",
            "l": "通用水景",
            "p": "通用水景"
          }
        ]
      },
      {
        "v": "general_landscape",
        "l": "通用景观",
        "p": "通用景观",
        "children": [
          {
            "v": "general_landscape_design",
            "l": "通用景观设计",
            "p": "通用景观设计"
          }
        ]
      }
    ],
    "interiorStyle": [
      {
        "v": "",
        "l": "沿用原图",
        "p": "沿用原图"
      },
      {
        "v": "modern",
        "l": "现代简约",
        "p": "modern minimalist"
      },
      {
        "v": "nordic",
        "l": "北欧风",
        "p": "Scandinavian style"
      },
      {
        "v": "mid_century",
        "l": "中古风",
        "p": "mid-century modern"
      },
      {
        "v": "wabi_sabi",
        "l": "侘寂风",
        "p": "wabi-sabi style"
      },
      {
        "v": "french",
        "l": "法式",
        "p": "French classical"
      },
      {
        "v": "light_luxury",
        "l": "轻奢风",
        "p": "light luxury style"
      },
      {
        "v": "new_chinese",
        "l": "新中式",
        "p": "new Chinese style"
      },
      {
        "v": "japanese",
        "l": "日式",
        "p": "Japanese style"
      },
      {
        "v": "american",
        "l": "美式",
        "p": "American style"
      },
      {
        "v": "bauhaus",
        "l": "包豪斯",
        "p": "Bauhaus style"
      },
      {
        "v": "southeast_asian",
        "l": "东南亚",
        "p": "Southeast Asian style"
      },
      {
        "v": "natural_wood",
        "l": "自然原木",
        "p": "natural wood interiors with tactile timber grain and warm neutral textiles"
      },
      {
        "v": "cream",
        "l": "奶油风",
        "p": "soft cream tones, matte finishes and tactile upholstery"
      },
      {
        "v": "japandi",
        "l": "日式北欧",
        "p": "Japandi, restrained natural materials and calm tonal contrast"
      },
      {
        "v": "italian_minimalist",
        "l": "意式极简",
        "p": "Italian minimalism with refined stone, timber and understated finish contrasts"
      },
      {
        "v": "modern_french",
        "l": "现代法式",
        "p": "modern French, soft neutrals and restrained elegance in existing finishes and furnishings"
      },
      {
        "v": "american_country",
        "l": "美式乡村",
        "p": "American country, warm timber, natural woven fabrics and a relaxed domestic palette"
      },
      {
        "v": "industrial",
        "l": "工业风",
        "p": "industrial-inspired concrete, metal and timber finishes, without adding exposed pipes or structures"
      },
      {
        "v": "mediterranean",
        "l": "地中海",
        "p": "Mediterranean, limewash textures, natural fabrics and warm earth tones with restrained blue accents"
      },
      {
        "v": "eclectic",
        "l": "混搭风",
        "p": "a coherent eclectic mix of existing material and textile expressions with a unified palette"
      }
    ],
    "publicInteriorStyle": [
      {
        "v": "",
        "l": "沿用原图",
        "p": "沿用原图"
      },
      {
        "v": "modern_minimalist",
        "l": "现代简约",
        "p": "modern minimalist interior with restrained palette, clean geometry, precise detailing, and balanced negative space"
      },
      {
        "v": "industrial",
        "l": "工业风",
        "p": "industrial finishes using concrete, metal and timber textures within existing surface divisions, without adding exposed structures or services"
      },
      {
        "v": "luxury",
        "l": "轻奢风",
        "p": "light-luxury interior with refined material layering, subtle metallic accents, and controlled premium ambience"
      },
      {
        "v": "tech_futuristic",
        "l": "科技未来风",
        "p": "tech-futuristic finish expression through refined metal, glass and a cool restrained palette within existing geometry, without adding parametric forms or screens"
      },
      {
        "v": "wabi_sabi",
        "l": "侘寂风",
        "p": "wabi-sabi interior with natural imperfections, muted earthy textures, soft light gradients, and tranquil contemplative mood"
      },
      {
        "v": "new_chinese",
        "l": "新中式",
        "p": "new-Chinese interior blending contemporary spatial order with oriental material temperament and elegant cultural details"
      },
      {
        "v": "commercial_general",
        "l": "通用商业风",
        "p": "high-quality commercial interior style with strong function clarity, robust material durability, and coherent brand atmosphere"
      },
      {
        "v": "natural_wood",
        "l": "自然原木",
        "p": "natural timber finishes, tactile grain and warm neutral fabrics within the original commercial interior design"
      },
      {
        "v": "nordic",
        "l": "北欧风",
        "p": "Scandinavian finish palette with light timber, muted textiles and understated material contrasts"
      },
      {
        "v": "mid_century",
        "l": "中古风",
        "p": "mid-century modern color and material expression through warm timber, rich textiles and subtle metal accents on existing furnishings"
      },
      {
        "v": "modern_french",
        "l": "现代法式",
        "p": "modern French finish expression with soft neutrals, refined stone and restrained metallic accents, without adding moldings or arches"
      },
      {
        "v": "art_deco",
        "l": "装饰艺术",
        "p": "Art Deco material and color expression with refined brass, deep tones and polished stone on existing surfaces, without changing the original geometry or furnishings"
      }
    ],
    "camera": [
      {
        "v": "Canon EOS R5",
        "l": "Canon EOS R5 · Canon RF 24 f/8.0",
        "p": "Canon EOS R5 机身，Canon RF 24mm 镜头，光圈 f/8.0"
      },
      {
        "v": "Sony A7R V",
        "l": "Sony A7R V · Sony GM 16 f/5.6",
        "p": "Sony A7R V 机身，Sony GM 16mm 镜头，光圈 f/5.6"
      },
      {
        "v": "Nikon Z8",
        "l": "Nikon Z8 · Nikon Nikkor Z 135 f/4.0",
        "p": "Nikon Z8 机身，Nikon Nikkor Z 135mm 镜头，光圈 f/4.0"
      },
      {
        "v": "Fujifilm GFX 100S",
        "l": "Fujifilm GFX 100S · Zeiss Otus 100 f/2.8",
        "p": "Fujifilm GFX 100S 机身，Zeiss Otus 100mm 镜头，光圈 f/2.8"
      },
      {
        "v": "Sony A7 IV",
        "l": "Sony A7 IV · Sony GM 85 f/1.4",
        "p": "Sony A7 IV 机身，Sony GM 85mm 镜头，光圈 f/1.4"
      },
      {
        "v": "Leica M11",
        "l": "Leica M11 · Leica Noctilux 50 f/1.2",
        "p": "Leica M11 机身，Leica Noctilux 50mm 镜头，光圈 f/1.2"
      },
      {
        "v": "Hasselblad X2D",
        "l": "Hasselblad X2D · Zeiss Batis 20 f/5.6",
        "p": "Hasselblad X2D 机身，Zeiss Batis 20mm 镜头，光圈 f/5.6"
      },
      {
        "v": "ARRI ALEXA 35",
        "l": "ARRI ALEXA 35 · Cooke Anamorphic 40 f/2.0",
        "p": "ARRI ALEXA 35 机身，Cooke Anamorphic 40mm 镜头，光圈 f/2.0"
      }
    ],
    "crop": [
      {
        "v": "free",
        "l": "自由",
        "p": "跟随原图"
      },
      {
        "v": "1:1",
        "l": "1:1",
        "p": "1:1"
      },
      {
        "v": "4:3",
        "l": "4:3",
        "p": "4:3"
      },
      {
        "v": "3:2",
        "l": "3:2",
        "p": "3:2"
      },
      {
        "v": "16:9",
        "l": "16:9",
        "p": "16:9"
      },
      {
        "v": "3:4",
        "l": "3:4",
        "p": "3:4"
      },
      {
        "v": "2:3",
        "l": "2:3",
        "p": "2:3"
      },
      {
        "v": "9:16",
        "l": "9:16",
        "p": "9:16"
      }
    ],
    "count": [
      {
        "v": "1",
        "l": "1 张",
        "p": "输出 1 张"
      },
      {
        "v": "2",
        "l": "2 张",
        "p": "输出 2 张"
      },
      {
        "v": "3",
        "l": "3 张",
        "p": "输出 3 张"
      },
      {
        "v": "4",
        "l": "4 张",
        "p": "输出 4 张"
      }
    ],
    "upscale": [
      {
        "v": "4k",
        "l": "4K",
        "p": "4K 放大"
      },
      {
        "v": "6k",
        "l": "6K",
        "p": "6K 放大"
      },
      {
        "v": "8k",
        "l": "8K",
        "p": "8K 放大"
      }
    ],
    "motion": [
      {
        "v": "dolly-in",
        "l": "平滑推进，相机向前移动",
        "p": "平滑推进，相机向前移动（smooth dolly in, camera moves forward）"
      },
      {
        "v": "dolly-out",
        "l": "平滑拉远，相机向后移动",
        "p": "平滑拉远，相机向后移动（smooth dolly out, camera moves backward）"
      },
      {
        "v": "zoom-in",
        "l": "变焦推进效果，焦距增大",
        "p": "变焦推进效果，焦距增大（zoom in effect, focal length increases）"
      },
      {
        "v": "zoom-out",
        "l": "变焦拉远效果，焦距减小",
        "p": "变焦拉远效果，焦距减小（zoom out effect, focal length decreases）"
      },
      {
        "v": "pan-left",
        "l": "相机平滑向左摇摄",
        "p": "相机平滑向左摇摄（smooth camera pan to the left）"
      },
      {
        "v": "pan-right",
        "l": "相机平滑向右摇摄",
        "p": "相机平滑向右摇摄（smooth camera pan to the right）"
      },
      {
        "v": "tilt-up",
        "l": "相机向上仰拍",
        "p": "相机向上仰拍（camera tilts upward）"
      },
      {
        "v": "tilt-down",
        "l": "相机向下俯拍",
        "p": "相机向下俯拍（camera tilts downward）"
      },
      {
        "v": "truck-left",
        "l": "相机向左平移，保持平行运动",
        "p": "相机向左平移，保持平行运动（camera trucks left, parallel movement）"
      },
      {
        "v": "truck-right",
        "l": "相机向右平移，保持平行运动",
        "p": "相机向右平移，保持平行运动（camera trucks right, parallel movement）"
      },
      {
        "v": "orbit-cw",
        "l": "相机顺时针环绕主体",
        "p": "相机顺时针环绕主体（camera orbits clockwise around the subject）"
      },
      {
        "v": "orbit-ccw",
        "l": "相机逆时针环绕主体",
        "p": "相机逆时针环绕主体（camera orbits counter-clockwise around the subject）"
      },
      {
        "v": "orbit-360",
        "l": "相机围绕主体进行 360 度环绕",
        "p": "相机围绕主体进行 360 度环绕（full 360 degree orbit around the subject）"
      },
      {
        "v": "follow-subject",
        "l": "相机平滑跟随主要主体",
        "p": "相机平滑跟随主要主体（camera follows the main subject smoothly）"
      },
      {
        "v": "tracking-shot",
        "l": "跟随运动的追踪镜头",
        "p": "跟随运动的追踪镜头（tracking shot following movement）"
      },
      {
        "v": "aerial-rise",
        "l": "航拍无人机镜头向上升起，鸟瞰视角",
        "p": "航拍无人机镜头向上升起，鸟瞰视角（aerial drone shot rising upward, bird eye view）"
      },
      {
        "v": "aerial-descend",
        "l": "航拍无人机镜头下降",
        "p": "航拍无人机镜头下降（aerial drone shot descending）"
      },
      {
        "v": "aerial-flyover",
        "l": "航拍无人机飞越镜头",
        "p": "航拍无人机飞越镜头（aerial drone flyover shot）"
      },
      {
        "v": "aerial-reveal",
        "l": "航拍揭示镜头，上升展示完整场景",
        "p": "航拍揭示镜头，上升展示完整场景（aerial reveal shot, ascending to show full scene）"
      },
      {
        "v": "static-fixed",
        "l": "静态相机，固定机位",
        "p": "静态相机，固定机位（static camera, fixed position）"
      },
      {
        "v": "slight-shake",
        "l": "轻微手持相机运动，自然感",
        "p": "轻微手持相机运动，自然感（slight handheld camera movement, natural feel）"
      }
    ]
  },
  "SKILL_KIND": {
    "bi-time": "time",
    "bi-season": "season",
    "bi-style": "style",
    "bi-story": "story"
  },
  "CONTROL_META": [
    {
      "k": "time",
      "t": "时段",
      "hint": "8 时段 · 时间迁移"
    },
    {
      "k": "renderTime",
      "t": "渲染时间",
      "hint": "8 档 · 含暮光覆盖"
    },
    {
      "k": "weather",
      "t": "天气",
      "hint": "8 种天气氛围"
    },
    {
      "k": "season",
      "t": "季节",
      "hint": "4 季相"
    },
    {
      "k": "style",
      "t": "目标画风",
      "hint": "12 种画风"
    },
    {
      "k": "layout",
      "t": "分镜布局",
      "hint": "4 / 9 / 16 / 25 宫格"
    },
    {
      "k": "building",
      "t": "建筑类型",
      "hint": "两级分类",
      "two": true
    },
    {
      "k": "landscape",
      "t": "景观类型",
      "hint": "两级分类",
      "two": true
    },
    {
      "k": "interiorStyle",
      "t": "室内风格",
      "hint": "21 项"
    },
    {
      "k": "publicInteriorStyle",
      "t": "公装风格",
      "hint": "13 项"
    },
    {
      "k": "camera",
      "t": "相机机位",
      "hint": "8 套机身镜头"
    },
    {
      "k": "crop",
      "t": "裁剪比例",
      "hint": "8 种画幅"
    },
    {
      "k": "count",
      "t": "输出张数",
      "hint": "1–4 张"
    },
    {
      "k": "upscale",
      "t": "放大档位",
      "hint": "4K / 6K / 8K"
    },
    {
      "k": "motion",
      "t": "运镜描述",
      "hint": "21 条中文短句"
    }
  ]
};
if(typeof window !== "undefined"){ try{ window["SNC_ARCO"] = SNC_ARCO; }catch(e){} }
