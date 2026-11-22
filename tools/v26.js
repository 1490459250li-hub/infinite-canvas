/* ==== V26-JS-START ==== */
/* ---------------------------------------------------------------------------
 * v2.6：AI 局部重绘工作台 + B1/B2/B3/B4 平台能力前端 + A3 分类模板库
 * 本段插入主逻辑 IIFE 内 boot() 之前，可直接复用 runJob / deriveCard / state 等。
 * ------------------------------------------------------------------------- */
function v26El(id){ return document.getElementById(id); }

/* A3 · 提示词分类模板库（自撰，8 类；选中才注入，默认不启用） */
var SNC_V26_CATEGORIES = {
  "arch":     {t:"建筑外观", i:"保持建筑体量、轮廓与透视不变，重点刻画立面材质、光影层次与檐口细节；不新增建筑体块。", k:["体量","立面","材质","光影","檐口"]},
  "interior": {t:"室内空间", i:"保持空间布局、家具位置与尺度关系，强化材质质感、软装层次与自然采光；不改变房间结构。", k:["布局","采光","软装","材质","尺度"]},
  "garden":   {t:"景观园林", i:"保持地形、园路走向与植物配置关系，优化植被层次、铺装纹理与水景反射；不改变场地边界。", k:["地形","园路","植被","铺装","水景"]},
  "lighting": {t:"夜景照明", i:"保持日间可见的构图与材质，只调整人工光的位置、色温、照度与眩光控制；天空与暗部过渡自然。", k:["色温","照度","眩光","灯具","暗部"]},
  "material": {t:"材质细节", i:"只细化选区或指定对象的表面纹理、反射与拼缝，保持几何形状、颜色关系与投影方向。", k:["纹理","反射","拼缝","粗糙度","投影"]},
  "people":   {t:"人物活动", i:"新增或调整人物时保持原透视尺度与光照方向，人物不遮挡主体，不出现文字与标识。", k:["尺度","动线","投影","人群","视线"]},
  "aerial":   {t:"总平鸟瞰", i:"保持轴网、道路与建筑落位完全一致，只优化总图关系、绿化覆盖与图面层次；不移动任何要素。", k:["轴网","落位","道路","绿化","图面层次"]},
  "general":  {t:"通用精修", i:"保持构图、机位与内容不变，只提升画面完成度：对比通透、边缘干净、高光不过曝、暗部有细节。", k:["构图","机位","完成度","对比","细节"]}
};
window.SNC_V26_CATEGORIES = SNC_V26_CATEGORIES;

/* A8 · 运镜词库（来自 SNC_ARCO.CONTROLS.motion），绑定到「视角切换」 */
var SNC_V26_MOTION = (SNC_ARCO && SNC_ARCO.CONTROLS && SNC_ARCO.CONTROLS.motion) || [];
window.SNC_V26_MOTION = SNC_V26_MOTION;

/* ---------------- 局部重绘工作台 ---------------- */
/* 重绘模式只留两项：
   desc   = 不建选区，整张图按描述重绘（和「生成描述」不再重复，因为它就是唯一入口）
   select = 框出选区，只重绘选区（默认）
   其余四项（框选/涂抹/拼贴/智能消除）原先只是往提示词里追加一句风格话术，
   和描述框重复，已经在 v2.9 撤掉。 */
var V26_MODES = {
  desc:    "按描述重绘整张画面，保持原有构图、机位与透视关系，只改动描述里点名的内容。",
  select:  "只重绘选区内的目标，保持原有光照方向、色温、透视与景深，边界与周围自然衔接。"
};

var V26_INP_REF_MAX = 3;

var v26Inp = {
  nodeId: null, src: "", overrideSrc: "", rects: [], tool: "lasso",
  res: 0, ratio: "auto", mode: "select", zoom: 1, panX: 0, panY: 0,
  nav: "draw", brush: 24, undo: [], redo: [], drag: null,
  pending: null, cursor: null, hover: null,
  refs: [],
  viewW: 0, viewH: 0
};
window.SNC_V26_INPAINT = v26Inp;

function v26InpNode(){
  for(var i = 0; i < state.nodes.length; i++){
    if(state.nodes[i].id === v26Inp.nodeId) return state.nodes[i];
  }
  return null;
}
/* 选区条目 = {x,y,w,h} 包围盒 + 可选 {kind:"poly"|"stroke", poly:[{x,y}...]}。
   包围盒给上游裁剪用（接口只吃矩形），poly 只用来画与擦除判断。 */
function v26CloneRec(r){
  var o = {x:r.x, y:r.y, w:r.w, h:r.h};
  if(r.kind) o.kind = r.kind;
  if(r.poly && r.poly.length){
    o.poly = r.poly.map(function(p){ return {x:p.x, y:p.y}; });
  }
  if(r.brush) o.brush = r.brush;
  if(r.segs && r.segs.length){
    o.segs = r.segs.map(function(seg){
      return seg.map(function(p){ return {x:p.x, y:p.y}; });
    });
  }
  if(r.invertOf && r.invertOf.length) o.invertOf = v26CloneRects(r.invertOf);
  return o;
}
function v26CloneRects(a){ return (a || []).map(v26CloneRec); }
function v26PushUndo(){
  v26Inp.undo.push(v26CloneRects(v26Inp.rects));
  if(v26Inp.undo.length > 40) v26Inp.undo.shift();
  v26Inp.redo.length = 0;
}
function v26SyncRects(){
  var n = v26InpNode();
  if(n) n.masks = v26CloneRects(v26Inp.rects);
  var hint = v26El("sncInpHint");
  if(hint) hint.textContent = v26Inp.mode === "desc"
    ? "描述重绘 · 整张图 · 原图保留"
    : "选区 " + v26Inp.rects.length + " 块 · 原图保留";
}
/* 生成描述的参考图：缩略图 + × 删除，最多 V26_INP_REF_MAX 张 */
function v26RenderRefs(){
  var box = v26El("sncInpRefList");
  var add = v26El("sncInpRefAdd");
  if(box){
    box.innerHTML = "";
    v26Inp.refs.forEach(function(u, i){
      var d = document.createElement("div");
      d.className = "snc-inp-ref";
      var im = document.createElement("img");
      im.src = u; im.alt = "参考图 " + (i + 1);
      d.appendChild(im);
      var x = document.createElement("button");
      x.type = "button"; x.textContent = "×"; x.title = "移除这张参考图";
      x.addEventListener("click", function(){
        v26Inp.refs.splice(i, 1);
        v26RenderRefs();
      });
      d.appendChild(x);
      box.appendChild(d);
    });
  }
  if(add) add.disabled = v26Inp.refs.length >= V26_INP_REF_MAX;
}
function v26ApplyTransform(){
  var wrap = v26El("sncInpWrap");
  if(!wrap) return;
  wrap.style.transform = "translate(" + v26Inp.panX + "px," + v26Inp.panY + "px) scale(" + v26Inp.zoom + ")";
  var z = v26El("sncInpZoom");
  if(z) z.textContent = Math.round(v26Inp.zoom * 100) + "%";
}
/* 把归一化点列铺到画布坐标 */
function v26Path(c, cv, pts){
  c.beginPath();
  pts.forEach(function(p, i){
    var x = p.x * cv.width, y = p.y * cv.height;
    if(i === 0) c.moveTo(x, y); else c.lineTo(x, y);
  });
}
function v26Dot(c, cv, p, r, fill){
  c.beginPath();
  c.arc(p.x * cv.width, p.y * cv.height, r, 0, Math.PI * 2);
  c.fillStyle = fill; c.fill();
  c.strokeStyle = "#e0603a"; c.lineWidth = 1.5; c.stroke();
}
/* 把一个选区形状画成「实心块」（矩形 / 多边形 / 涂抹笔触都吃）。
   反选要拿它把补集里的原选区挖掉，所以不能只认矩形。 */
function v26FillShape(c, cv, q){
  if(!q) return;
  if(q.kind === "poly" && q.poly && q.poly.length > 2){
    v26Path(c, cv, q.poly); c.closePath(); c.fill();
  } else if(q.kind === "stroke" && q.poly && q.poly.length > 1){
    c.lineCap = "round"; c.lineJoin = "round";
    c.lineWidth = Math.max(6, q.brush || v26Inp.brush);
    c.strokeStyle = "#000";                 // 挖洞只看 alpha，颜色无所谓
    [q.poly].concat(q.segs || []).forEach(function(seg){
      if(!seg || seg.length < 2) return;
      v26Path(c, cv, seg); c.stroke();
    });
  } else {
    c.fillRect(q.x * cv.width, q.y * cv.height, q.w * cv.width, q.h * cv.height);
  }
}
function v26StrokeShape(c, cv, q){
  if(!q) return;
  if(q.kind === "poly" && q.poly && q.poly.length > 2){
    v26Path(c, cv, q.poly); c.closePath(); c.stroke();
  } else if(q.kind === "stroke" && q.poly && q.poly.length > 1){
    c.lineCap = "round"; c.lineJoin = "round";
    c.lineWidth = Math.max(6, q.brush || v26Inp.brush);
    [q.poly].concat(q.segs || []).forEach(function(seg){
      if(!seg || seg.length < 2) return;
      v26Path(c, cv, seg); c.stroke();
    });
  } else {
    c.strokeRect(q.x * cv.width, q.y * cv.height, q.w * cv.width, q.h * cv.height);
  }
}
function v26Draw(){
  var cv = v26El("sncInpMask");
  if(!cv) return;
  var c = cv.getContext("2d"), W = cv.width, H = cv.height;
  c.clearRect(0, 0, W, H);

  v26Inp.rects.forEach(function(r, i){
    c.save();
    if(r.invertOf && r.invertOf.length){
      /* 反选：整张图铺一层橙，再把原选区挖掉——看得见的红区就是「会被重绘」的范围。
         洞的轮廓用虚线描出来，用户能一眼看出「这块保住不动」。 */
      c.fillStyle = "rgba(224,96,58,.24)";
      c.fillRect(0, 0, W, H);
      c.globalCompositeOperation = "destination-out";
      c.fillStyle = "#000";
      r.invertOf.forEach(function(q){ v26FillShape(c, cv, q); });
      c.globalCompositeOperation = "source-over";
      c.setLineDash([5, 4]);
      c.strokeStyle = "rgba(224,96,58,.92)"; c.lineWidth = 1.6;
      r.invertOf.forEach(function(q){ v26StrokeShape(c, cv, q); });
      c.setLineDash([]);
      c.restore();
      return;
    }
    if(r.kind === "poly" && r.poly && r.poly.length > 2){
      v26Path(c, cv, r.poly); c.closePath();
      c.fillStyle = "rgba(224,96,58,.26)"; c.fill();
      c.strokeStyle = "rgba(224,96,58,.95)"; c.lineWidth = 2; c.stroke();
      c.fillStyle = "#fff"; c.font = "12px sans-serif";
      c.fillText(String(i + 1), r.x * W + 6, r.y * H + 15);
    } else if(r.kind === "stroke" && r.poly && r.poly.length > 1){
      /* 涂抹是「一个选区、多笔叠加」：分次涂抹的每一笔都并进同一条记录，
         画的时候一起描边、不标序号——主流工具（PS 快速蒙版 / 即梦涂抹）都是这样，
         每笔一个编号反而让人以为生成了好几个独立区域。 */
      var segs = [r.poly].concat(r.segs || []);
      segs.forEach(function(seg){
        if(!seg || seg.length < 2) return;
        v26Path(c, cv, seg);
        c.lineCap = "round"; c.lineJoin = "round";
        c.strokeStyle = "rgba(224,96,58,.30)";
        c.lineWidth = Math.max(6, r.brush || v26Inp.brush); c.stroke();
        c.strokeStyle = "rgba(224,96,58,.85)"; c.lineWidth = 1.5; c.stroke();
      });
    } else {
      var x = r.x * W, y = r.y * H, w = r.w * W, h = r.h * H;
      c.fillStyle = "rgba(224,96,58,.26)"; c.fillRect(x, y, w, h);
      c.strokeStyle = "rgba(224,96,58,.95)"; c.lineWidth = 2;
      c.strokeRect(x + 1, y + 1, Math.max(1, w - 2), Math.max(1, h - 2));
      c.fillStyle = "#fff"; c.font = "12px sans-serif";
      c.fillText(String(i + 1), x + 5, y + 15);
    }
    c.restore();
  });

  /* 矩形拖拽中 / 自由套索拖拽中 的预览 */
  var d = v26Inp.drag;
  if(d && d.pts && d.pts.length){
    c.save();
    c.setLineDash([6, 4]); c.strokeStyle = "#e0603a"; c.lineWidth = 2;
    if(d.type === "rect"){
      var a = d.pts[0], b = d.pts[d.pts.length - 1];
      c.strokeRect(Math.min(a.x, b.x) * W, Math.min(a.y, b.y) * H,
                   Math.abs(b.x - a.x) * W, Math.abs(b.y - a.y) * H);
    } else if(d.type === "lasso" && d.moved && d.pts.length > 1){
      v26Path(c, cv, d.pts); c.closePath();
      c.fillStyle = "rgba(224,96,58,.14)"; c.fill();
      c.stroke();
    }
    c.restore();
  }

  /* 多边形套索进行中：已落点 + 到光标的橡皮筋 */
  var pg = v26Inp.pending;
  if(pg && pg.length){
    var live = v26Inp.cursor ? pg.concat([v26Inp.cursor]) : pg;
    c.save();
    if(live.length > 1){
      v26Path(c, cv, live);
      c.setLineDash([6, 4]); c.strokeStyle = "#e0603a"; c.lineWidth = 2; c.stroke();
    }
    if(live.length > 2){
      v26Path(c, cv, live); c.closePath();
      c.fillStyle = "rgba(224,96,58,.12)"; c.fill();
    }
    c.setLineDash([]);
    pg.forEach(function(p, i){ v26Dot(c, cv, p, i === 0 ? 5 : 3.5, i === 0 ? "#fff" : "#e0603a"); });
    c.restore();
  }

  /* 笔尖预览：涂抹 / 橡皮擦时在光标处画一个圈，圈的大小就是这一笔的粗细。
     没有它只能靠「笔刷 ±」盲调，画出来才知道多粗（用户反馈的第 5 条）。 */
  var hv = v26Inp.hover;
  if(hv && !v26Inp.drag && (v26Inp.tool === "brush" || v26Inp.tool === "eraser")){
    var rad = Math.max(2, v26Inp.brush / 2);
    c.save();
    c.beginPath(); c.arc(hv.x * W, hv.y * H, rad, 0, Math.PI * 2);
    c.strokeStyle = "rgba(0,0,0,.55)"; c.lineWidth = 2.5; c.stroke();
    c.beginPath(); c.arc(hv.x * W, hv.y * H, rad, 0, Math.PI * 2);
    c.strokeStyle = v26Inp.tool === "eraser" ? "#7ec7ff" : "#ffffff";
    c.lineWidth = 1.2; c.setLineDash([5, 4]); c.stroke();
    c.restore();
  }
}
function v26LoadImage(){
  var img = v26El("sncInpImg"), wrap = v26El("sncInpWrap"), cv = v26El("sncInpMask");
  var host = v26El("sncInpCanvas");
  if(!img || !wrap || !cv || !host) return;
  var src = v26Inp.overrideSrc || v26Inp.src;
  if(!src){ v26El("sncInpEmpty").hidden = false; return; }
  v26El("sncInpEmpty").hidden = true;
  var im = new Image();
  im.onload = function(){
    var availW = Math.max(200, host.clientWidth * 0.86);
    var availH = Math.max(160, host.clientHeight * 0.86);
    /* 大图缩到窗口内；小图（截图、表情）允许放大一点，别在正中间缩成一个点 */
    var kCap = (im.naturalWidth < 480 || im.naturalHeight < 480) ? 3 : 1.6;
    var k = Math.min(availW / im.naturalWidth, availH / im.naturalHeight, kCap);
    v26Inp.viewW = Math.max(80, Math.round(im.naturalWidth * k));
    v26Inp.viewH = Math.max(60, Math.round(im.naturalHeight * k));
    img.src = src;
    img.style.width = v26Inp.viewW + "px";
    img.style.height = v26Inp.viewH + "px";
    wrap.style.width = v26Inp.viewW + "px";
    wrap.style.height = v26Inp.viewH + "px";
    cv.width = v26Inp.viewW; cv.height = v26Inp.viewH;
    cv.style.width = v26Inp.viewW + "px"; cv.style.height = v26Inp.viewH + "px";
    v26ApplyTransform(); v26Draw();
  };
  im.onerror = function(){ v26El("sncInpEmpty").hidden = false; };
  im.src = src;
}
function v26OpenInpaint(n){
  if(!n || n.status !== "done"){ toast("等这张图生成完再局部重绘"); return; }
  var src = n.dataUrl || photoURL(n.photo);
  if(!src){ toast("这张卡片没有可编辑的位图"); return; }
  v26Inp.nodeId = n.id; v26Inp.src = src; v26Inp.overrideSrc = "";
  v26Inp.rects = v26CloneRects(n.masks || []);
  v26Inp.undo = []; v26Inp.redo = []; v26Inp.drag = null;
  v26Inp.pending = null; v26Inp.cursor = null; v26Inp.hover = null;
  v26Inp.zoom = 1; v26Inp.panX = 0; v26Inp.panY = 0; v26Inp.nav = "draw";
  v26Inp.res = 0; v26Inp.ratio = "auto"; v26Inp.mode = "select"; v26Inp.tool = "lasso";
  v26Inp.refs = [];
  v26El("sncInpScrim").hidden = false;
  v26El("sncInp").hidden = false;
  v26El("sncInpPrompt").value = "";
  v26InpChipsSet("res", "0"); v26InpChipsSet("ratio", "auto");
  v26ResBuild(n.modelOpt);
  v26InpChipsSet("mode", "select"); v26InpChipsSet("tool", "lasso");
  v26InpNavSet(); v26InpBrushInfo(); v26SyncRects();
  v26ApplyMode(); v26RenderRefs();
  v26LoadImage();
  placeImgBar();
}
function v26CloseInpaint(){
  v26SyncRects();
  v26Inp.pending = null; v26Inp.cursor = null; v26Inp.drag = null; v26Inp.hover = null;
  v26El("sncInp").hidden = true;
  v26El("sncInpScrim").hidden = true;
  var n = v26InpNode();
  if(n) paintNode(n);
  placeImgBar();
}
function v26InpChipsSet(group, v){
  var box = document.querySelector('#sncInp [data-group="' + group + '"]');
  if(!box) return;
  Array.prototype.forEach.call(box.querySelectorAll("button[data-v]"), function(b){
    b.classList.toggle("is-on", b.dataset.v === v);
  });
}
function v26InpNavSet(){
  var tools = v26El("sncInpTools");
  if(tools){
    Array.prototype.forEach.call(tools.querySelectorAll('button[data-tool="pointer"],button[data-tool="hand"]'), function(b){
      b.classList.toggle("is-on", b.dataset.tool === (v26Inp.nav === "draw" ? "pointer" : "hand"));
    });
  }
  var wrap = v26El("sncInpWrap");
  if(wrap){
    wrap.classList.toggle("is-pan", v26Inp.nav === "pan");
    wrap.classList.toggle("is-nav", false);
  }
}
/* 「橡皮擦」这名字会让人以为在擦像素，实际是从选区里减掉一块，所以叫「减选」 */
var V26_TOOLNAME = {rect:"矩形", lasso:"套索", brush:"涂抹", eraser:"减选", detect:"识别"};
function v26InpBrushInfo(){
  var el = v26El("sncInpToolInfo");
  if(el) el.textContent = (V26_TOOLNAME[v26Inp.tool] || "") + " · 笔刷 " + v26Inp.brush + "px";
  var val = v26El("sncInpBrushVal");
  if(val) val.textContent = v26Inp.brush + "px";
  var rg = v26El("sncInpBrush");
  if(rg && String(rg.value) !== String(v26Inp.brush)) rg.value = v26Inp.brush;
}
/* v3.0：分辨率档位跟着当前模型的最长边走——
   4096 的模型给「原图 / 2K / 4K」，1536 的模型给「原图 / 1K / 1.5K」。
   档位由 canvas.src.html 的 SNC_RES_TIERS 统一算，这里只负责画按钮。 */
function v26ResBuild(modelValue){
  var box = document.querySelector('#sncInp [data-group="res"]');
  if(!box) return;
  var tiers = (typeof window.SNC_RES_TIERS === "function")
    ? window.SNC_RES_TIERS(modelValue) : null;
  if(!tiers || !tiers.length){
    tiers = [{v:0, label:"原图"}, {v:2048, label:"2K"}, {v:4096, label:"4K"}];
  }
  box.innerHTML = tiers.map(function(t){
    return '<button type="button" data-v="' + t.v + '"' +
      (t.v === 0 ? ' class="is-on"' : '') + '>' + t.label + '</button>';
  }).join("");
  var ok = false;
  tiers.forEach(function(t){ if(t.v === v26Inp.res) ok = true; });
  if(!ok) v26Inp.res = 0;
  v26InpChipsSet("res", String(v26Inp.res));
  v26ResNote();
}
/* 分辨率档位的说明：0 = 原图（不插值）、其它 = 成品长边。
   写清楚是为了不再出现「选了 4K 其实只是插值放大」的误会。 */
function v26ResNote(){
  var el = v26El("sncInpResNote");
  if(!el) return;
  el.textContent = v26Inp.res
    ? "成品长边 " + v26Inp.res + "px：选区按该尺寸重绘后回贴，整图等比重建到同样长边。"
    : "输出尺寸 = 原图像素，只重绘选区，不放大也不缩小。";
}
/* 模式联动：描述重绘不需要选区，把「建立选区 / 编辑选区」整块藏起来，
   切回选区重绘时再显示——否则用户会以为不建选区就用不了描述重绘。 */
function v26ApplyMode(){
  var desc = v26Inp.mode === "desc";
  ["sncInpSecTool", "sncInpSecEdit"].forEach(function(id){
    var el = v26El(id);
    if(el) el.hidden = desc;
  });
  var pr = v26El("sncInpPrompt");
  if(pr){
    pr.placeholder = desc
      ? "描述这张图要变成什么样，例如：改成黄昏时分，暖光从西侧打进来"
      : "描述一下希望选区区域内变成什么...";
  }
  var hint = v26El("sncInpHint");
  if(hint){
    hint.textContent = desc
      ? "描述重绘 · 整张图 · 原图保留"
      : "选区 " + v26Inp.rects.length + " 块 · 原图保留";
  }
  if(desc){
    /* 切到描述模式时收掉画到一半的多边形和已有选区：留着既提交不出去，
       又会在底图上挡视线 */
    v26Inp.pending = null; v26Inp.cursor = null; v26Inp.drag = null;
    if(v26Inp.rects.length){ v26Inp.rects = []; v26SyncRects(); }
    v26Draw();
  }
  v26ResNote();
}
function v26Local(e){
  var cv = v26El("sncInpMask");
  var r = cv.getBoundingClientRect();
  return {
    x: Math.min(1, Math.max(0, (e.clientX - r.left) / (r.width || 1))),
    y: Math.min(1, Math.max(0, (e.clientY - r.top) / (r.height || 1)))
  };
}
function v26Bounds(pts, pad){
  var xs = pts.map(function(p){ return p.x; }), ys = pts.map(function(p){ return p.y; });
  var x0 = Math.min.apply(null, xs) - (pad || 0), x1 = Math.max.apply(null, xs) + (pad || 0);
  var y0 = Math.min.apply(null, ys) - (pad || 0), y1 = Math.max.apply(null, ys) + (pad || 0);
  x0 = Math.max(0, x0); y0 = Math.max(0, y0); x1 = Math.min(1, x1); y1 = Math.min(1, y1);
  return {x:x0, y:y0, w:Math.max(0.012, x1 - x0), h:Math.max(0.012, y1 - y0)};
}
/* 橡皮擦 = 从选区里**减掉**刷过的部分，不是「碰到就整块删」。
   原来是整块 filter 掉，用户点一下半个选区就没了，看着跟涂抹没区别。 */
function v26EraseAt(p){
  /* 反选是「整图 − 原选区」的复合选区，按矩形切分会把它拆坏，
     直接告诉用户先取消反选，比默默画错强。 */
  for(var gi = 0; gi < v26Inp.rects.length; gi++){
    if(v26Inp.rects[gi].invertOf){
      toast("反选状态下不能减选 · 再按一次「反选」可取消");
      return false;
    }
  }
  var rad = Math.max(0.004, (v26Inp.brush / 2) / Math.max(80, v26Inp.viewW));
  var out = [], changed = false;
  v26Inp.rects.forEach(function(q){
    var res = v26Subtract(q, p, rad);
    if(res === null){ changed = true; return; }
    if(res.length === 1 && res[0] === q){ out.push(q); return; }
    changed = true;
    res.forEach(function(x){ out.push(x); });
  });
  if(changed) v26Inp.rects = out.slice(0, 16);
  return changed;
}
function v26CircleHitRect(q, p, r){
  var cx = Math.max(q.x, Math.min(p.x, q.x + q.w));
  var cy = Math.max(q.y, Math.min(p.y, q.y + q.h));
  var dx = p.x - cx, dy = p.y - cy;
  return dx * dx + dy * dy <= r * r;
}
/* 返回：null = 整块被擦掉；[q] = 没碰到；多块 = 减完剩下的部分 */
function v26Subtract(q, p, r){
  function far(pt){
    var dx = pt.x - p.x, dy = pt.y - p.y;
    return dx * dx + dy * dy > r * r;
  }
  if(q.kind === "poly" && q.poly && q.poly.length > 2){
    if(!v26HitPoly(q.poly, p, r)) return [q];
    /* 多边形没法开洞，就先把轮廓加密到 3px 一个点，再删掉刷子范围内的点——
       效果是从边上咬掉一口，而不是整块消失。 */
    var dense = v26Densify(q.poly, 3 / Math.max(80, v26Inp.viewW));
    var keep = dense.filter(far);
    if(keep.length < 3) return null;
    var b = v26Bounds(keep, 0);
    return [{x:b.x, y:b.y, w:b.w, h:b.h, kind:"poly", poly:keep}];
  }
  if(q.kind === "stroke" && q.poly && q.poly.length > 1){
    /* 涂抹可能攒了多笔（q.segs），减选要把每一笔都切一遍 */
    var all = [q.poly].concat(q.segs || []);
    var segs = [], dropped = 0;
    all.forEach(function(seg){
      var cur = [];
      seg.forEach(function(pt){
        if(!far(pt)){ dropped++; if(cur.length > 1) segs.push(cur); cur = []; }
        else cur.push(pt);
      });
      if(cur.length > 1) segs.push(cur);
    });
    if(!segs.length) return null;
    if(!dropped) return [q];
    var pad = (q.brush || v26Inp.brush) / 2 / Math.max(80, v26Inp.viewW);
    var flat = [];
    segs.forEach(function(s){ flat = flat.concat(s); });
    var b0 = v26Bounds(flat, pad);
    return [{x:b0.x, y:b0.y, w:b0.w, h:b0.h, kind:"stroke",
             poly:segs[0], segs:segs.slice(1), brush:q.brush}];
  }
  /* 矩形：绕刷子切成左 / 右 / 上 / 下四块 */
  if(!v26CircleHitRect(q, p, r)) return [q];
  var lx = Math.max(q.x, p.x - r), rx = Math.min(q.x + q.w, p.x + r);
  var ty = Math.max(q.y, p.y - r), by = Math.min(q.y + q.h, p.y + r);
  var pieces = [];
  if(lx > q.x + 0.002) pieces.push({x:q.x, y:q.y, w:lx - q.x, h:q.h, kind:"rect"});
  if(rx < q.x + q.w - 0.002) pieces.push({x:rx, y:q.y, w:q.x + q.w - rx, h:q.h, kind:"rect"});
  if(rx > lx){
    if(ty > q.y + 0.002) pieces.push({x:lx, y:q.y, w:rx - lx, h:ty - q.y, kind:"rect"});
    if(by < q.y + q.h - 0.002) pieces.push({x:lx, y:by, w:rx - lx, h:q.y + q.h - by, kind:"rect"});
  }
  return pieces.length ? pieces : null;
}
/* 把闭合折线按 step 加密（归一化步长），给橡皮擦沿边裁剪用 */
function v26Densify(poly, step){
  var out = [], s = Math.max(0.002, step || 0.01);
  for(var i = 0; i < poly.length; i++){
    var a = poly[i], b = poly[(i + 1) % poly.length];
    out.push({x:a.x, y:a.y});
    var dx = b.x - a.x, dy = b.y - a.y, len = Math.sqrt(dx * dx + dy * dy);
    var n = Math.min(300, Math.max(1, Math.round(len / s)));
    for(var k = 1; k < n; k++) out.push({x:a.x + dx * k / n, y:a.y + dy * k / n});
  }
  return out;
}
/* 点是否落在多边形内 / 边线附近（橡皮擦用） */
function v26HitPoly(poly, p, r){
  var inside = false, i, j;
  for(i = 0, j = poly.length - 1; i < poly.length; j = i++){
    var xi = poly[i].x, yi = poly[i].y, xj = poly[j].x, yj = poly[j].y;
    if(((yi > p.y) !== (yj > p.y)) && (p.x < (xj - xi) * (p.y - yi) / ((yj - yi) || 1e-9) + xi)){
      inside = !inside;
    }
    /* 边线附近也算命中，免得细长套索必须正中才擦得掉 */
    var dx = xj - xi, dy = yj - yi;
    var len2 = dx * dx + dy * dy;
    var t = len2 > 0 ? ((p.x - xi) * dx + (p.y - yi) * dy) / len2 : 0;
    t = Math.max(0, Math.min(1, t));
    var ex = xi + t * dx - p.x, ey = yi + t * dy - p.y;
    if(Math.sqrt(ex * ex + ey * ey) <= r) return true;
  }
  return inside;
}
/* 识别主体：把底图缩到 48px 宽，跟「画面四周的平均色」比差异，挑面积最大的连通区域当主体。
   原来这里只是往中间塞一个固定 0.6×0.6 的框，等于没识别——所以用户觉得「识别」和涂抹橡皮一样。 */
function v26DetectSubject(){
  var im = v26El("sncInpImg");
  if(!im || !im.naturalWidth || !im.naturalHeight) return null;
  var W = 48, H = Math.max(12, Math.round(W * im.naturalHeight / im.naturalWidth));
  var cv = document.createElement("canvas");
  cv.width = W; cv.height = H;
  var c = cv.getContext("2d");
  try{
    c.drawImage(im, 0, 0, W, H);
  }catch(e){ return null; }
  var data;
  try{ data = c.getImageData(0, 0, W, H).data; }catch(e){ return null; }
  var n = W * H, x, y, i;
  function rgb(k){ var j = k * 4; return [data[j], data[j + 1], data[j + 2]]; }

  /* 边框平均色：主体通常和四周环境不一样 */
  var br = [0, 0, 0], bn = 0;
  for(y = 0; y < H; y++) for(x = 0; x < W; x++){
    if(x < 2 || y < 2 || x >= W - 2 || y >= H - 2){
      var p0 = rgb(y * W + x);
      br[0] += p0[0]; br[1] += p0[1]; br[2] += p0[2]; bn++;
    }
  }
  if(!bn) return null;
  br[0] /= bn; br[1] /= bn; br[2] /= bn;

  var dist = new Float32Array(n), sum = 0, sum2 = 0;
  for(i = 0; i < n; i++){
    var p1 = rgb(i);
    var dr = p1[0] - br[0], dg = p1[1] - br[1], db = p1[2] - br[2];
    var d0 = Math.sqrt(dr * dr + dg * dg + db * db) / 441.7;
    dist[i] = d0; sum += d0; sum2 += d0 * d0;
  }
  var mean = sum / n, sd = Math.sqrt(Math.max(0, sum2 / n - mean * mean));
  var thr = Math.max(0.12, mean + sd * 0.7);

  /* 连通域（4 邻），取面积最大的一块 */
  function biggest(t0){
    var mark = new Int8Array(n), best = null;
    for(var s = 0; s < n; s++){
      if(mark[s] || dist[s] < t0) continue;
      var stack = [s], area = 0, x0 = 1e9, y0 = 1e9, x1 = -1, y1 = -1;
      mark[s] = 1;
      while(stack.length){
        var q = stack.pop(), qx = q % W, qy = (q - qx) / W;
        area++;
        if(qx < x0) x0 = qx; if(qx > x1) x1 = qx;
        if(qy < y0) y0 = qy; if(qy > y1) y1 = qy;
        var nb = [q - 1, q + 1, q - W, q + W];
        for(var k = 0; k < 4; k++){
          var t = nb[k];
          if(t < 0 || t >= n || mark[t] || dist[t] < t0) continue;
          if(k === 0 && qx === 0) continue;
          if(k === 1 && qx === W - 1) continue;
          mark[t] = 1; stack.push(t);
        }
      }
      if(!best || area > best.area) best = {area:area, x0:x0, y0:y0, x1:x1, y1:y1};
    }
    return best;
  }
  var box = biggest(thr);
  if(!box || box.area < n * 0.03){ box = biggest(Math.max(0.06, mean * 0.9)); }
  if(!box) return null;

  var bx = box.x0 / W, by = box.y0 / H;
  var bw = (box.x1 + 1 - box.x0) / W, bh = (box.y1 + 1 - box.y0) / H;
  var padX = bw * 0.06, padY = bh * 0.06;
  var rect = {
    x: Math.max(0, bx - padX), y: Math.max(0, by - padY),
    w: Math.min(1, bw + padX * 2), h: Math.min(1, bh + padY * 2)
  };
  if(rect.w < 0.06 || rect.h < 0.06) return null;
  rect.kind = "rect";
  return rect;
}
/* 反选：在离屏栅格上按选区的**真实形状**求补集。
   旧实现按包围盒切竖条带（只认 q.x / q.x+q.w），套索画的是多边形，
   于是补集永远按包围盒算——三角形、L 形一类的选区反选出来还盖着原选区，
   看起来就是「反选没生效」。现在把矩形 / 多边形 / 笔触都栅格化到 96px 网格，
   逐行取未覆盖的连续段，再把上下相邻、x 区间完全相同的段合并成矩形。 */
function v26RasterCover(W, H){
  var cv = document.createElement("canvas");
  cv.width = W; cv.height = H;
  var c = cv.getContext("2d");
  c.clearRect(0, 0, W, H);
  c.fillStyle = "#000";
  c.strokeStyle = "#000";
  v26Inp.rects.forEach(function(r){
    if(r.kind === "poly" && r.poly && r.poly.length > 2){
      v26Path(c, cv, r.poly); c.closePath(); c.fill();
    } else if(r.kind === "stroke" && r.poly && r.poly.length > 1){
      var segList = [r.poly].concat(r.segs || []);
      c.lineCap = "round"; c.lineJoin = "round";
      c.lineWidth = Math.max(2, (r.brush || v26Inp.brush) * W / Math.max(80, v26Inp.viewW));
      segList.forEach(function(seg){
        if(!seg || seg.length < 2) return;
        v26Path(c, cv, seg); c.stroke();
      });
    } else {
      c.fillRect(r.x * W, r.y * H, r.w * W, r.h * H);
    }
  });
  var data;
  try{ data = c.getImageData(0, 0, W, H).data; }catch(e){ return null; }
  var grid = new Uint8Array(W * H);
  for(var i = 0; i < W * H; i++) grid[i] = data[i * 4 + 3] > 40 ? 1 : 0;
  return grid;
}
function v26Invert(){
  v26PushUndo();
  var old = v26Inp.rects;
  if(!old.length){
    v26Inp.rects = [{x:0, y:0, w:1, h:1, kind:"rect"}];
    v26SyncRects(); v26Draw();
    toast("没有选区 · 反选 = 整张图");
    return;
  }
  /* 已经是反选状态 → 再按一次 = 取消反选，回到原来的选区 */
  if(old.length === 1 && old[0].invertOf && old[0].invertOf.length){
    v26Inp.rects = v26CloneRects(old[0].invertOf);
    v26SyncRects(); v26Draw();
    toast("已取消反选 · 回到原来的 " + v26Inp.rects.length + " 块选区");
    return;
  }

  /* 以前这里把补集栅格化成 96px 横条、并且只留最大的 4 块：套索是不规则形状，
     逐行合并出来的就是「一道一道的横条」，大片区域根本没选上，看起来像反选失败。
     现在换成一条语义化选区「整张图 − 原选区」：重绘时整图重绘，贴回之前
     再把原选区按真实形状盖回原图（洞里的像素保证不动）；再按一次反选即取消。 */
  v26Inp.rects = [{x:0, y:0, w:1, h:1, kind:"rect", invertOf:v26CloneRects(old)}];
  v26SyncRects(); v26Draw();
  toast("已反选 · 除原选区外全部重绘（再按一次可取消）");
}
function v26SubmitInpaint(){
  var text = (v26El("sncInpPrompt").value || "").trim();
  var descMode = v26Inp.mode === "desc";
  if(!descMode && !v26Inp.rects.length){ toast("先在图上建立选区"); return; }
  if(!text){
    toast(descMode ? "写一句这张图要变成什么样" : "写一句希望选区里变成什么");
    v26El("sncInpPrompt").focus(); return;
  }
  var parent = v26InpNode();
  if(!parent){ toast("原图已不在画布上"); return; }
  var src = v26Inp.overrideSrc || parent.dataUrl || photoURL(parent.photo);
  var srcNode = {}, k;
  for(k in parent) if(Object.prototype.hasOwnProperty.call(parent, k)) srcNode[k] = parent[k];
  srcNode.dataUrl = src; srcNode.photo = null;

  var refs = (v26Inp.refs || []).slice(0, V26_INP_REF_MAX);
  var rects = v26CloneRects(v26Inp.rects).slice(0, 4);
  snapshot();
  var child = deriveCard(parent, {
    ratio: "auto", prompt: text, tag: "局部重绘",
    w: parent.w, h: parent.h, model: parent.modelOpt, origin: "region"
  });
  state.sel = new Set([child.id]);
  state.userPicked = child.id;
  v26Inp.rects = [];
  v26Inp.pending = null; v26Inp.cursor = null; v26Inp.drag = null;
  v26Inp.refs = [];
  v26SyncRects(); v26RenderRefs();
  v26El("sncInp").hidden = true;
  v26El("sncInpScrim").hidden = true;
  renderAll();
  ensureVisible(child);
  if(typeof scheduleSave === "function") scheduleSave();

  if(descMode){
    /* 描述重绘：不裁剪、不回贴，整张原图当主参考交给 /images/edits。
       分辨率档位在这里是「成品长边」：原图档按原图长边要图，2K / 4K 直接要那一档。 */
    var jobRefs = [{dataUrl: src, role: "main"}];
    refs.forEach(function(u){ jobRefs.push({dataUrl: u, role: "style"}); });
    var wantLong = Number(v26Inp.res) > 0 ? Number(v26Inp.res) : 0;
    runJob(child, {
      refs: jobRefs,
      ratio: v26Inp.ratio === "auto" ? "auto" : v26Inp.ratio,
      res: wantLong || 2048,
      model: parent.modelOpt || "fast",
      postLongSide: wantLong,        // 成品再收口一次，保证尺寸就是所选档位
      struct: null
    });
  } else {
    runJob(child, {region: {
      rects: rects, text: text, mode: v26Inp.mode,
      res: v26Inp.res, ratio: v26Inp.ratio, refs: refs
    }, src: srcNode});
  }
  placeImgBar();
  toast("局部重绘已提交 · 原图保留 · " + (descMode ? "整张图" : rects.length + " 块区域") +
        (refs.length ? " · " + refs.length + " 张参考图" : ""));
}

/* 事件接线 */
(function(){
  var root = v26El("sncInp");
  if(!root) return;

  v26El("sncInpX").addEventListener("click", v26CloseInpaint);
  v26El("sncInpScrim").addEventListener("click", v26CloseInpaint);
  /* capture 阶段拦下 Esc：先取消画到一半的多边形，再按一次才关工作台 */
  document.addEventListener("keydown", function(e){
    if(e.key !== "Escape") return;
    if(v26El("sncInp").hidden) return;
    e.stopPropagation();
    if(e.stopImmediatePropagation) e.stopImmediatePropagation();
    if(v26Inp.pending && v26Inp.pending.length){
      v26CancelPoly();
      return;
    }
    v26CloseInpaint();
  }, true);
  /* [ ] 调笔刷大小（PS 的老习惯），输入框里打字时不拦 */
  document.addEventListener("keydown", function(e){
    if(v26El("sncInp").hidden) return;
    if(e.key !== "[" && e.key !== "]") return;
    var t = e.target, tag = t && t.tagName ? t.tagName.toUpperCase() : "";
    if(tag === "TEXTAREA" || tag === "INPUT") return;
    e.preventDefault();
    e.stopPropagation();
    v26Inp.brush = Math.min(160, Math.max(4, v26Inp.brush + (e.key === "]" ? 4 : -4)));
    v26InpBrushInfo(); v26Draw();
  }, true);

  /* Ctrl+Z / Ctrl+Shift+Z 撤销重做（底部那两个按钮撤了，快捷键保留，
     PS 里也是这个习惯）。输入框里打字时让浏览器自己的撤销生效。 */
  document.addEventListener("keydown", function(e){
    if(v26El("sncInp").hidden) return;
    if(!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z") return;
    var t = e.target, tag = t && t.tagName ? t.tagName.toUpperCase() : "";
    if(tag === "TEXTAREA" || tag === "INPUT") return;
    e.preventDefault(); e.stopPropagation();
    if(e.shiftKey){
      if(!v26Inp.redo.length){ toast("没有可重做的操作"); return; }
      v26Inp.undo.push(v26CloneRects(v26Inp.rects));
      v26Inp.rects = v26Inp.redo.pop();
    } else {
      if(!v26Inp.undo.length){ toast("没有可撤销的操作"); return; }
      v26Inp.redo.push(v26CloneRects(v26Inp.rects));
      v26Inp.rects = v26Inp.undo.pop();
    }
    v26SyncRects(); v26Draw();
  }, true);

  root.addEventListener("click", function(e){
    var chip = e.target.closest("button[data-v]");
    if(chip){
      var group = chip.parentElement.getAttribute("data-group");
      var v = chip.dataset.v;
      if(group === "res"){
        v26Inp.res = parseInt(v, 10) || 0;
        v26InpChipsSet("res", v);
        v26ResNote();
      }
      else if(group === "ratio"){ v26Inp.ratio = v; v26InpChipsSet("ratio", v); }
      else if(group === "mode"){
        v26Inp.mode = v; v26InpChipsSet("mode", v);
        v26ApplyMode();          // 描述重绘要把选区三块藏起来
      }
      else if(group === "tool"){
        /* 识别是「点一下」的动作，不是常驻工具：识别完自动切回矩形，方便继续微调 */
        if(v === "detect"){ v26RunDetect(); return; }
        v26SetTool(v);
      }
      return;
    }
    var ed = e.target.closest("button[data-edit]");
    if(ed){
      var act = ed.dataset.edit;
      if(act === "invert") v26Invert();
      else if(act === "clear"){
        v26PushUndo(); v26Inp.rects = []; v26CancelPoly(); v26SyncRects(); v26Draw(); toast("选区已清空");
      }
      /* 「复位视图」按钮已按反馈撤掉：翻页/缩放用底部抓手 + Ctrl+滚轮就够，
         多一个按钮反而和「清空选区」看着重复。 */
    }
  });

  /* 笔刷大小滑杆：拖动即可改，画布上的笔尖圆圈跟着变 */
  var brushRange = v26El("sncInpBrush");
  if(brushRange) brushRange.addEventListener("input", function(){
    var val = parseInt(this.value, 10);
    if(!isFinite(val)) return;
    v26Inp.brush = Math.max(4, Math.min(160, val));
    v26InpBrushInfo();
    v26Draw();
  });

  /* 监听整个工作台：底部工具条属于 data-tool 组。
     撤销 / 重做 / 上传 / 更换图片 四个按钮已按反馈撤掉（快捷键保留）。 */
  root.addEventListener("click", function(e){
    var b = e.target.closest("button[data-tool]");
    if(!b) return;
    var t = b.dataset.tool;
    if(t === "pointer"){ v26Inp.nav = "draw"; v26InpNavSet(); }
    else if(t === "hand"){ v26Inp.nav = "pan"; v26InpNavSet(); }
    else if(t === "zoomin" || t === "zoomout"){
      v26Inp.zoom = Math.min(3, Math.max(0.5, v26Inp.zoom + (t === "zoomin" ? 0.15 : -0.15)));
      v26ApplyTransform();
    } else if(t === "brushplus" || t === "brushminus"){
      v26Inp.brush = Math.min(160, Math.max(4, v26Inp.brush + (t === "brushplus" ? 8 : -8)));
      v26InpBrushInfo(); v26Draw();
    }
  });

  /* 参考图：生成描述里挂的图，最多 3 张，一起发给模型 */
  var refAdd = v26El("sncInpRefAdd");
  if(refAdd) refAdd.addEventListener("click", function(){
    if(v26Inp.refs.length >= V26_INP_REF_MAX){ toast("最多 " + V26_INP_REF_MAX + " 张参考图"); return; }
    v26El("sncInpFile").click();
  });

  v26El("sncInpFile").addEventListener("change", function(){
    var files = Array.prototype.slice.call(this.files || []);
    this.value = "";
    if(!files.length) return;
    var room = V26_INP_REF_MAX - v26Inp.refs.length;
    files = files.slice(0, Math.max(0, room));
    if(!files.length){ toast("最多 " + V26_INP_REF_MAX + " 张参考图"); return; }
    var pending = files.length;
    files.forEach(function(f){
      var fr = new FileReader();
      fr.onload = function(){
        v26Inp.refs.push(String(fr.result));
        pending -= 1;
        if(pending <= 0){
          v26RenderRefs();
          toast("已添加 " + v26Inp.refs.length + " 张参考图 · 会一起发给模型");
        }
      };
      fr.onerror = function(){ pending -= 1; if(pending <= 0) v26RenderRefs(); };
      fr.readAsDataURL(f);
    });
  });

  var cv = v26El("sncInpMask");

  /* 多边形套索：单击落点，回到起点 / 双击 / 右键 闭合。下面三个都是小工具。 */
  function closeThreshold(){ return 14 / Math.max(80, v26Inp.viewW); }
  function v26CommitPoly(){
    var pg = v26Inp.pending || [];
    v26Inp.pending = null; v26Inp.cursor = null;
    if(pg.length < 3){ v26Draw(); return; }
    var b = v26Bounds(pg, 0);
    v26PushUndo();
    v26Inp.rects.push({
      x: b.x, y: b.y, w: b.w, h: b.h, kind: "poly",
      poly: pg.map(function(p){ return {x:p.x, y:p.y}; })
    });
    if(v26Inp.rects.length > 12) v26Inp.rects.shift();
    v26SyncRects(); v26Draw();
    toast("已添加多边形选区 · " + pg.length + " 个顶点");
  }
  function v26CancelPoly(){
    var had = !!(v26Inp.pending && v26Inp.pending.length);
    v26Inp.pending = null; v26Inp.cursor = null;
    v26Draw();
    if(had) toast("已取消当前多边形");
    return had;
  }
  function v26SetTool(t){
    v26Inp.tool = t;
    v26InpChipsSet("tool", t);
    if(t !== "lasso") v26CancelPoly();
    v26InpBrushInfo();
  }
  /* 识别主体：算完直接把框塞进选区（替换原来的），并把工具切回矩形，
     用户可以接着拖 / 擦，不会再误以为「识别」是个可以一直画画的模式。 */
  function v26RunDetect(){
    var r = v26DetectSubject();
    if(!r){ toast("这张图没识别出主体，用矩形自己框一下吧"); return; }
    v26PushUndo();
    v26Inp.rects = [r];
    v26SetTool("rect");
    v26SyncRects(); v26Draw();
    toast("已识别主体 · 约占画面 " + Math.round(r.w * 100) + "% × " + Math.round(r.h * 100) + "%");
  }
  /* 供测试与外部调用 */
  window.SNC_V26_SET_TOOL = v26SetTool;
  window.SNC_V26_CLOSE_POLY = v26CommitPoly;
  window.SNC_V26_DETECT = v26DetectSubject;

  cv.addEventListener("pointerdown", function(e){
    if(v26El("sncInp").hidden) return;
    if(e.button === 2) return;                 // 右键留给「闭合多边形」
    e.preventDefault();
    var p = v26Local(e);

    /* 抓手：拖动画面，不画选区 */
    if(v26Inp.nav === "pan"){
      try{ cv.setPointerCapture(e.pointerId); }catch(err){}
      v26Inp.drag = {type:"pan", sx:e.clientX, sy:e.clientY, px:v26Inp.panX, py:v26Inp.panY};
      return;
    }

    /* 套索：按下先记一笔。拖出去 = 自由套索；原地单击 = 多边形落点（PS 的多边形套索）。 */
    if(v26Inp.tool === "lasso"){
      try{ cv.setPointerCapture(e.pointerId); }catch(err){}
      v26Inp.drag = {type:"lasso", pts:[p], moved:false, start:p};
      v26Draw();
      return;
    }

    try{ cv.setPointerCapture(e.pointerId); }catch(err){}

    if(v26Inp.tool === "eraser"){
      v26PushUndo();
      if(!v26EraseAt(p)) v26Inp.undo.pop();
      v26Inp.drag = {type:"eraser", pts:[p]};
      v26SyncRects(); v26Draw();
      return;
    }
    v26Inp.drag = {type:v26Inp.tool, pts:[p]};
    v26Draw();
  });

  cv.addEventListener("pointermove", function(e){
    var p = v26Local(e);

    /* 多边形套索：只更新橡皮筋，不需要按下 */
    if(v26Inp.pending && !v26Inp.drag){
      v26Inp.cursor = p;
      v26Draw();
      return;
    }
    var d = v26Inp.drag;
    if(!d){
      /* 没在拖拽时也要跟着鼠标：涂抹 / 橡皮擦要显示笔尖圆圈 */
      if(v26Inp.tool === "brush" || v26Inp.tool === "eraser"){
        v26Inp.hover = p;
        v26Draw();
      }
      return;
    }
    if(d.type === "pan"){
      v26Inp.panX = d.px + (e.clientX - d.sx);
      v26Inp.panY = d.py + (e.clientY - d.sy);
      v26ApplyTransform();
      return;
    }
    if(d.type === "eraser"){
      d.pts.push(p);
      if(v26EraseAt(p)){ v26SyncRects(); v26Draw(); }
      return;
    }
    if(d.type === "lasso"){
      d.pts.push(p);
      if(d.pts.length > 240) d.pts.shift();
      var mx = p.x - d.start.x, my = p.y - d.start.y;
      if(!d.moved && Math.sqrt(mx * mx + my * my) > closeThreshold() * 0.4) d.moved = true;
      v26Draw();
      return;
    }
    d.pts.push(p);
    if(d.pts.length > 240) d.pts.shift();
    v26Draw();
  });

  /* 涂抹：把这一笔并进最后那条涂抹选区（而不是新建一块）。
     连续涂同一个区域时永远只有一块选区，包围盒跟着扩张，
     不会再出现「每笔一个编号、层层叠加」的怪样子。 */
  function v26AddStroke(pts){
    if(!pts || pts.length < 2) return;
    var list = v26Inp.rects;
    var pad = (v26Inp.brush / 2) / Math.max(80, v26Inp.viewW);
    var seg = pts.map(function(q){ return {x:q.x, y:q.y}; });
    var last = list[list.length - 1];
    if(last && last.kind === "stroke"){
      if(!last.segs) last.segs = [];
      last.segs.push(seg);
      var b = v26Bounds(pts, pad);
      var x0 = Math.min(last.x, b.x), y0 = Math.min(last.y, b.y);
      var x1 = Math.max(last.x + last.w, b.x + b.w);
      var y1 = Math.max(last.y + last.h, b.y + b.h);
      last.x = x0; last.y = y0; last.w = x1 - x0; last.h = y1 - y0;
      last.brush = Math.max(last.brush || 0, v26Inp.brush);
      return;
    }
    var bb = v26Bounds(pts, pad);
    var rec = {x:bb.x, y:bb.y, w:bb.w, h:bb.h, kind:"stroke", poly:seg, brush:v26Inp.brush};
    list.push(rec);
    if(list.length > 12) list.shift();
  }

  function endDrag(e){
    var d = v26Inp.drag;
    if(!d) return;
    v26Inp.drag = null;
    if(d.type === "pan" || d.type === "eraser"){ v26Draw(); return; }

    if(d.type === "lasso"){
      var lp = d.pts || [];
      if(d.moved && lp.length >= 3){
        /* 拖出来的自由套索：按下→松开画完就闭合，和老习惯一致 */
        var fb = v26Bounds(lp, 0);
        v26PushUndo();
        v26Inp.rects.push({
          x: fb.x, y: fb.y, w: fb.w, h: fb.h, kind: "poly",
          poly: lp.map(function(q){ return {x:q.x, y:q.y}; })
        });
        if(v26Inp.rects.length > 12) v26Inp.rects.shift();
        v26Inp.pending = null; v26Inp.cursor = null;
        v26SyncRects(); v26Draw();
        return;
      }
      /* 原地单击 = 多边形落下一个顶点 */
      var p0 = lp[0] || {x:0, y:0};
      var pg = v26Inp.pending;
      if(!pg){
        v26Inp.pending = [p0]; v26Inp.cursor = p0; v26Draw();
        return;
      }
      var dx0 = p0.x - pg[0].x, dy0 = p0.y - pg[0].y;
      if(pg.length >= 3 && Math.sqrt(dx0 * dx0 + dy0 * dy0) <= closeThreshold()){
        v26CommitPoly(); return;
      }
      pg.push(p0); v26Inp.cursor = p0; v26Draw();
      return;
    }

    var pts = d.pts || [];
    if(pts.length < 2){ v26Draw(); return; }     // 单击不建选区，避免误触
    v26PushUndo();
    if(d.type === "brush"){
      v26AddStroke(pts);
    } else {
      /* 涂抹的包围盒要按笔刷**半径**外扩（笔刷值是直径），
         原来按整个直径补一圈，框比实际笔触大了一倍。 */
      var b = v26Bounds(pts, 0);
      v26Inp.rects.push({x:b.x, y:b.y, w:b.w, h:b.h, kind:"rect"});
      if(v26Inp.rects.length > 12) v26Inp.rects.shift();
    }
    v26SyncRects(); v26Draw();
  }
  cv.addEventListener("pointerup", endDrag);
  cv.addEventListener("pointercancel", endDrag);
  /* 鼠标移出画布就把笔尖圈收掉 */
  cv.addEventListener("pointerleave", function(){
    if(v26Inp.hover){ v26Inp.hover = null; v26Draw(); }
  });

  /* 双击闭合多边形（PS 的习惯），右键同理 */
  cv.addEventListener("dblclick", function(e){
    if(v26Inp.pending){ e.preventDefault(); v26CommitPoly(); }
  });
  cv.addEventListener("contextmenu", function(e){
    if(v26Inp.pending){ e.preventDefault(); v26CommitPoly(); }
  });

  v26El("sncInpGo").addEventListener("click", v26SubmitInpaint);
})();

/* ---------------- B4 · 整理画布 / 小地图 / 图层 ---------------- */
/* 整理 = 按派生关系做**树形**排布：原图在上，派生图挂在它正下方、水平居中对齐；
   同一父节点的兄弟从左到右排开，一排超过 TIDY_MAXROW 就折行；每棵树算完宽高再按行打包。
   之前是「按派生深度分层、每层都从 x=0 起排」，于是第 5 张图的派生结果全部跑到画布最左边、
   跟原图彻底脱开——用户看到的就是「派生图左对齐」。深度只用来分组的话，永远对不齐父子。
   排完交给画布自带的 fit()，它的内边距按 rail / 顶部栏 / 底部提示条算过，
   这里不要再自己写 leftPad，否则 rail 会被重复扣一次。 */
var TIDY_MAXROW = 1560, TIDY_GAPX = 36, TIDY_GAPY = 46, TIDY_TREEGAP = 96;
function v26Tidy(){
  if(!state.nodes.length){ toast("画布是空的"); return; }
  snapshot();

  var byId = {}, kids = {}, roots = [];
  state.nodes.forEach(function(n){ byId[n.id] = n; });
  state.nodes.forEach(function(n){
    var p = n.derivedFrom && byId[n.derivedFrom];
    if(p && p.id !== n.id) (kids[p.id] = kids[p.id] || []).push(n);
    else roots.push(n);
  });
  function byTime(a, b){
    return (a.createdAt || 0) - (b.createdAt || 0) || String(a.id).localeCompare(String(b.id));
  }
  roots.sort(byTime);
  Object.keys(kids).forEach(function(k){ kids[k].sort(byTime); });

  /* 环（A 派生 B、B 又指回 A）或指向已删卡的孤立节点：从根出发走一遍，
     走不到的当新根单独排，别让它们从画布上消失。 */
  var reached = {};
  function walk(n){
    if(!n || reached[n.id]) return;
    reached[n.id] = 1;
    (kids[n.id] || []).forEach(walk);
  }
  roots.forEach(walk);
  state.nodes.forEach(function(n){
    if(!reached[n.id]){ roots.push(n); walk(n); }
  });

  var wMemo = {}, hMemo = {};
  function nodeW(n){ return n.w || (typeof CARD_W === "number" ? CARD_W : 260); }
  function nodeH(n){ return n.h || (typeof CARD_H === "number" ? CARD_H : 240); }
  /* 孩子那一排怎么排：从左到右，一排超过 TIDY_MAXROW 折行 */
  function rowsOf(n){
    var list = kids[n.id] || [], rows = [], cur = [], cw = 0;
    list.forEach(function(c){
      var w = subW(c);
      if(cur.length && cw + TIDY_GAPX + w > TIDY_MAXROW){
        rows.push({list:cur, w:cw}); cur = []; cw = 0;
      }
      cw += (cur.length ? TIDY_GAPX : 0) + w;
      cur.push(c);
    });
    if(cur.length) rows.push({list:cur, w:cw});
    return rows;
  }
  function subW(n){
    if(wMemo[n.id] != null) return wMemo[n.id];
    wMemo[n.id] = nodeW(n);            // 先占位：环也不会无限递归
    var rows = rowsOf(n), w = nodeW(n);
    rows.forEach(function(r){ if(r.w > w) w = r.w; });
    wMemo[n.id] = w; return w;
  }
  function subH(n){
    if(hMemo[n.id] != null) return hMemo[n.id];
    hMemo[n.id] = nodeH(n);
    var rows = rowsOf(n), h = nodeH(n);
    rows.forEach(function(r){
      var m = 0;
      r.list.forEach(function(c){ m = Math.max(m, subH(c)); });
      r.h = m; h += TIDY_GAPY + m;
    });
    hMemo[n.id] = h; return h;
  }
  function place(n, x, y){
    var w = nodeW(n), h = nodeH(n), box = subW(n);
    n.x = Math.round(x + (box - w) / 2);   // 自己在本子树里居中
    n.y = Math.round(y);
    var cy = y + h + TIDY_GAPY;
    rowsOf(n).forEach(function(r){
      var rh = 0;
      r.list.forEach(function(c){ rh = Math.max(rh, subH(c)); });
      var cx = x + (box - r.w) / 2;         // 一排孩子整体居中于父节点
      r.list.forEach(function(c){
        place(c, cx, cy);
        cx += subW(c) + TIDY_GAPX;
      });
      cy += rh + TIDY_GAPY;
    });
  }
  var x = 0, y = 0, rowH = 0, trees = 0;
  roots.forEach(function(r){
    var w = subW(r), h = subH(r);
    if(x > 0 && x + w > TIDY_MAXROW){ y += rowH + TIDY_TREEGAP; x = 0; rowH = 0; }
    place(r, x, y);
    x += w + TIDY_TREEGAP;
    rowH = Math.max(rowH, h);
    trees++;
  });

  renderAll();
  try{ fit(); }
  catch(e){
    /* fit 万一不可用，至少别把用户留在老视角上 */
    state.view = {x:60, y:70, k:0.8};
    try{ applyView(); }catch(_e){}
  }
  if(typeof scheduleSave === "function") scheduleSave();
  toast("已整理画布 · " + trees + " 组派生链 / " + state.nodes.length + " 张");
}
/* 兼容旧入口：一律走 fit()，不要再自己算内边距 */
function v26FitAll(){ try{ fit(); }catch(e){} }
window.SNC_V26_FIT = v26FitAll;
var v26MiniMap = null;
function v26DrawMini(){
  var box = v26El("sncMini"), cv = v26El("sncMiniCanvas");
  if(!box || box.hidden || !cv) return;
  var c = cv.getContext("2d"), W = cv.width, H = cv.height;
  c.clearRect(0, 0, W, H);
  var ns = state.nodes.filter(function(n){ return isFinite(n.x) && isFinite(n.y); });
  var stage = v26El("sncStage");
  var sw = stage ? stage.clientWidth : 1200, sh = stage ? stage.clientHeight : 700;
  var k0 = state.view.k || 1;
  var vx = -state.view.x / k0, vy = -state.view.y / k0, vw = sw / k0, vh = sh / k0;
  var minX = vx, minY = vy, maxX = vx + vw, maxY = vy + vh;
  ns.forEach(function(n){
    minX = Math.min(minX, n.x); minY = Math.min(minY, n.y);
    maxX = Math.max(maxX, n.x + (n.w || CARD_W));
    maxY = Math.max(maxY, n.y + (n.h || 240));
  });
  var pad = 14;
  var k = Math.min((W - pad * 2) / Math.max(1, maxX - minX), (H - pad * 2) / Math.max(1, maxY - minY));
  v26MiniMap = {minX:minX, minY:minY, k:k, pad:pad};
  function X(v){ return pad + (v - minX) * k; }
  function Y(v){ return pad + (v - minY) * k; }
  ns.forEach(function(n){
    var selected = state.sel.has(n.id);
    c.fillStyle = n.hidden ? "rgba(140,140,140,.28)" :
      (selected ? "rgba(224,96,58,.85)" : (n.type === "gen" ? "rgba(120,160,220,.62)" : "rgba(160,160,160,.42)"));
    c.fillRect(X(n.x), Y(n.y), Math.max(3, (n.w || CARD_W) * k), Math.max(3, (n.h || 240) * k));
    c.strokeStyle = selected ? "#e0603a" : "rgba(255,255,255,.35)";
    c.lineWidth = selected ? 2 : 1;
    c.strokeRect(X(n.x), Y(n.y), Math.max(3, (n.w || CARD_W) * k), Math.max(3, (n.h || 240) * k));
  });
  c.strokeStyle = "#ffd166"; c.lineWidth = 2;
  c.strokeRect(X(vx), Y(vy), vw * k, vh * k);
}
/* ---------------- 图层顺序 / 分组（v2.9 参考 PS） ----------------
   数据全挂在节点上，跟着 board 一起存，不需要额外的表：
     n.layOrder  图层顺序（越大越靠上，列表顶部 = 最上层）
     n.grp       组 id；同组共享同一个值
     n.grpName   组名（成组时写「组 N」，之后双击组名可改，改名写回组内每个成员）
     n.grpOpen   组是否展开（取组内任一节点的值即可，切换时全组一起改）
   原来的图层是「按派生深度分组、只读」，既不能排序也不能成组。 */
var v26Drag = null;     // {id, grpId, zone, overId}

function v26LayerSeq(){
  var ns = state.nodes.slice();
  ns.forEach(function(n, i){ if(typeof n.layOrder !== "number") n.layOrder = i; });
  ns.sort(function(a, b){
    return (b.layOrder || 0) - (a.layOrder || 0) ||
           String(a.id).localeCompare(String(b.id));
  });
  return ns;
}
function v26WriteOrder(list){
  var N = list.length;
  list.forEach(function(n, i){ n.layOrder = N - i; });
}
function v26GrpMembers(gid){
  return v26LayerSeq().filter(function(n){ return n.grp === gid; });
}
function v26GrpOpen(gid){
  var m = v26GrpMembers(gid)[0];
  return !m || m.grpOpen !== false;
}
function v26SetGrpOpen(gid, v){
  v26GrpMembers(gid).forEach(function(n){ n.grpOpen = v; });
}
function v26AllGrpIds(){
  var seen = {}, out = [];
  v26LayerSeq().forEach(function(n){
    if(n.grp && !seen[n.grp]){ seen[n.grp] = 1; out.push(n.grp); }
  });
  return out;
}
function v26LayerName(n){
  return String(n.label || n.prompt || n.title || n.id || "卡片").replace(/[&<>"]/g, "").slice(0, 30);
}
/* PS 那种眼睛：可见 = 睁眼 + 瞳孔；隐藏 = 同轮廓 + 一道斜线（瞳孔去掉） */
var V26_EYE_ON =
  '<svg viewBox="0 0 24 24" aria-hidden="true">' +
  '<path d="M1.6 12S5.7 5.1 12 5.1 22.4 12 22.4 12 18.3 18.9 12 18.9 1.6 12 1.6 12z"/>' +
  '<circle cx="12" cy="12" r="3.1"/></svg>';
var V26_EYE_OFF =
  '<svg viewBox="0 0 24 24" aria-hidden="true">' +
  '<path d="M1.6 12S5.7 5.1 12 5.1 22.4 12 22.4 12 18.3 18.9 12 18.9 1.6 12 1.6 12z"/>' +
  '<path d="M3.4 20.2L20.2 3.4"/></svg>';

function v26RenderLayers(){
  var box = v26El("sncLayers");
  if(!box || box.hidden) return;
  var body = v26El("sncLayersBody");
  if(!body) return;

  var seq = v26LayerSeq();
  var html = "", openGrps = {};

  /* 组整体一次输出：组行 → （展开时）成员行。组的位置取它最上面那个成员的顺序。 */
  seq.forEach(function(n){
    if(!n.grp){
      html += v26LayerRowHTML(n, false);
      return;
    }
    if(openGrps[n.grp]) return;
    openGrps[n.grp] = 1;
    var gid = n.grp;
    var isOpen = v26GrpOpen(gid);
    var gname = String(n.grpName || "组").replace(/[&<>"]/g, "");
    var members = v26GrpMembers(gid);
    var allHidden = members.every(function(x){ return !!x.hidden; });
    var anySel = members.some(function(x){ return state.sel.has(x.id); });
    html += '<div class="snc-layer-row is-grp' + (anySel ? " is-on" : "") +
      (allHidden ? " is-hidden" : "") + '" data-grp="' + gid + '" draggable="true">' +
      '<button type="button" class="snc-layer-twist" data-twist="' + gid + '" title="' +
      (isOpen ? "收起组" : "展开组") + '">' + (isOpen ? "▾" : "▸") + "</button>" +
      '<button type="button" class="snc-layer-eye' + (allHidden ? " is-off" : "") +
      '" data-eyegrp="' + gid + '" title="' + (allHidden ? "显示整组" : "隐藏整组") + '">' +
      (allHidden ? V26_EYE_OFF : V26_EYE_ON) + "</button>" +
      '<span class="snc-layer-t" data-gname="' + gid + '" title="双击改组名">' + gname + "</span>" +
      '<i class="snc-layer-num" title="组内 ' + members.length + ' 张">' + members.length + "</i>" +
      '<button type="button" class="snc-layer-edit" data-gedit="' + gid + '" title="改组名">' +
      '<svg viewBox="0 0 18 18" aria-hidden="true"><path d="M3 13.6V16h2.4L15 6.4 11.6 3 3 13.6z"/>' +
      '<path d="M10.6 4.2L13.8 7.4"/></svg></button></div>';
    if(isOpen) members.forEach(function(m){ html += v26LayerRowHTML(m, true); });
  });

  body.innerHTML = html || '<div class="snc-layers-g">画布是空的</div>';

  var cnt = v26El("sncLayersCount");
  if(cnt){
    var hid = state.nodes.filter(function(n){ return n.hidden; }).length;
    cnt.textContent = state.nodes.length + " 张" + (hid ? " · 隐藏 " + hid : "");
  }
}
function v26LayerRowHTML(n, isKid){
  return '<div class="snc-layer-row' + (isKid ? " is-kid" : "") +
    (state.sel.has(n.id) ? " is-on" : "") + (n.hidden ? " is-hidden" : "") +
    '" data-lid="' + n.id + '" draggable="true" title="' + v26LayerName(n) + '">' +
    '<button type="button" class="snc-layer-eye' + (n.hidden ? " is-off" : "") +
    '" data-eye="' + n.id + '" title="' + (n.hidden ? "显示这张" : "在画布上隐藏这张") + '">' +
    (n.hidden ? V26_EYE_OFF : V26_EYE_ON) + "</button>" +
    '<span class="snc-layer-t">' + v26LayerName(n) + "</span></div>";
}

/* 成组：选中的卡片（含已属于别的组的）合到一个新组里，顺序按当前图层顺序 */
function v26GroupSelected(){
  var ids = Array.from(state.sel);
  if(ids.length < 2){ toast("先选中两张以上卡片（画布上按 Shift 点选）"); return; }
  var used = v26AllGrpIds();
  var name = "组 " + (used.length + 1);
  var gid = "grp" + Date.now().toString(36);
  ids.forEach(function(id){
    var n = state.nodes.find(function(x){ return x.id === id; });
    if(!n) return;
    n.grp = gid; n.grpName = name; n.grpOpen = true;
  });
  v26RenderLayers();
  if(typeof scheduleSave === "function") scheduleSave();
  toast("已成组 · " + name + " · " + ids.length + " 张");
}
function v26UngroupSelected(){
  var ids = Array.from(state.sel);
  if(!ids.length){ toast("先选中要解组的卡片或组"); return; }
  var hit = 0;
  ids.forEach(function(id){
    var n = state.nodes.find(function(x){ return x.id === id; });
    if(n && n.grp){ delete n.grp; delete n.grpName; delete n.grpOpen; hit++; }
  });
  if(!hit){ toast("选中的卡片不在任何组里"); return; }
  v26RenderLayers();
  if(typeof scheduleSave === "function") scheduleSave();
  toast("已解组 · " + hit + " 张");
}

/* 改组名：组名存在每个成员节点的 grpName 上，改名要写全组。
   空名 / 全是非法字符时不动，返回 false 让调用方把界面刷回去。 */
function v26RenameGroup(gid, name){
  var v = String(name || "").replace(/[&<>"]/g, "").replace(/\s+/g, " ").trim().slice(0, 24);
  if(!v) return false;
  var ms = v26GrpMembers(gid);
  if(!ms.length) return false;
  var same = ms.every(function(n){ return n.grpName === v; });
  ms.forEach(function(n){ n.grpName = v; });
  v26RenderLayers();
  if(!same && typeof scheduleSave === "function") scheduleSave();
  if(!same) toast("组名改为「" + v + "」");
  return true;
}
/* 就地改名：把组名换成输入框，回车/失焦保存，Esc 放弃（PS 双击图层名的习惯） */
function v26EditGrpName(gid){
  var body = v26El("sncLayersBody");
  if(!body) return;
  var span = body.querySelector('[data-gname="' + gid + '"]');
  if(!span || span.tagName === "INPUT") return;
  var row = span.closest(".snc-layer-row");
  var old = String(span.textContent || "");
  var inp = document.createElement("input");
  inp.type = "text";
  inp.className = "snc-layer-input";
  inp.value = old;
  inp.maxLength = 24;
  inp.setAttribute("aria-label", "组名");
  /* 行本身可拖动，编辑时必须关掉，否则一按就成了拖拽 */
  if(row) row.draggable = false;
  span.replaceWith(inp);
  inp.focus();
  inp.select();

  var done = false;
  function finish(commit){
    if(done) return;
    done = true;
    if(row) row.draggable = true;
    var ok = commit && inp.value.trim() && inp.value !== old && v26RenameGroup(gid, inp.value);
    if(!ok) v26RenderLayers();
    else if(typeof renderAll === "function") renderAll();
  }
  inp.addEventListener("keydown", function(e){
    if(e.key === "Enter"){ e.preventDefault(); finish(true); }
    else if(e.key === "Escape"){ e.preventDefault(); finish(false); }
    /* 别让画布快捷键（V/H/Esc/Delete…）吃到正在输入的字符 */
    e.stopPropagation();
  });
  inp.addEventListener("blur", function(){ finish(true); });
  inp.addEventListener("click", function(e){ e.stopPropagation(); });
  inp.addEventListener("dblclick", function(e){ e.stopPropagation(); });
}

/* 拖拽落点：上 1/4 插到上面、下 1/4 插到下面、中间放进组 */
function v26DropZone(el, y){
  var r = el.getBoundingClientRect();
  var t = (y - r.top) / Math.max(1, r.height);
  if(t < 0.25) return "before";
  if(t > 0.75) return "after";
  return "into";
}
function v26ClearDropMarks(){
  var body = v26El("sncLayersBody");
  if(!body) return;
  Array.prototype.forEach.call(body.querySelectorAll(".snc-layer-row"), function(r){
    r.classList.remove("is-drop-before", "is-drop-after", "is-drop-into");
  });
}
function v26ApplyDrop(){
  var d = v26Drag;
  if(!d || !d.overId) return;
  var seq = v26LayerSeq(), i;

  /* 拖组行 = 整组一起移动；拖成员行 = 只动这一张 */
  var moving;
  if(d.grpId){
    moving = seq.filter(function(n){ return n.grp === d.grpId; });
    seq = seq.filter(function(n){ return n.grp !== d.grpId; });
  } else {
    moving = [];
    for(i = 0; i < seq.length; i++){
      if(seq[i].id === d.id){ moving = [seq.splice(i, 1)[0]]; break; }
    }
  }
  if(!moving.length) return;

  var target = null, ti = -1;
  for(i = 0; i < seq.length; i++){
    if(seq[i].id === d.overId){ target = seq[i]; ti = i; break; }
  }

  if(!target){
    seq = seq.concat(moving);                 // 拖到列表空白处：放到底部
  } else if(d.zone === "into" && target.grp && !d.grpId){
    /* 放进组：目标在组内 → 同组；顺序插到目标前面 */
    moving[0].grp = target.grp;
    moving[0].grpName = target.grpName;
    moving[0].grpOpen = true;
    seq.splice(ti, 0, moving[0]);
  } else {
    /* before / after：插到目标相邻位置。目标是组内成员就跟着进组，
       目标是组行（或空白）就退出组；整组移动时组关系保持不变。 */
    if(!d.grpId){
      if(target.grp){ moving[0].grp = target.grp; moving[0].grpName = target.grpName; }
      else { delete moving[0].grp; delete moving[0].grpName; delete moving[0].grpOpen; }
    }
    var at = d.zone === "before" ? ti : ti + 1;
    seq.splice.apply(seq, [at, 0].concat(moving));
  }
  v26WriteOrder(seq);
  v26RenderLayers();
  if(typeof scheduleSave === "function") scheduleSave();
}

/* 隐藏 = 真的看不见、点不到，导出也不带上（原来只把透明度压到 0.18，
   节点照样能点、导出照样进图，等于没隐藏） */
function v26SyncHidden(){
  state.nodes.forEach(function(n){
    var h = world.querySelector('[data-id="' + n.id + '"]');
    if(!h) return;
    h.style.opacity = n.hidden ? "0" : "";
    h.style.pointerEvents = n.hidden ? "none" : "";
    h.classList.toggle("is-hidden", !!n.hidden);
  });
}
/* 包装渲染：小地图 / 图层 / 隐藏态随画布变化自动刷新 */
var v26RenderAll0 = renderAll;
renderAll = function(){
  var r = v26RenderAll0.apply(this, arguments);
  try{ v26SyncHidden(); v26DrawMini(); v26RenderLayers(); }catch(e){}
  return r;
};
var v26ApplyView0 = applyView;
applyView = function(){
  var r = v26ApplyView0.apply(this, arguments);
  try{ v26DrawMini(); }catch(e){}
  return r;
};
(function(){
  var tidy = v26El("sncTidyBtn"), miniBtn = v26El("sncMiniBtn"), layersBtn = v26El("sncLayersBtn");
  if(tidy) tidy.addEventListener("click", v26Tidy);
  if(miniBtn) miniBtn.addEventListener("click", function(){
    var m = v26El("sncMini"); m.hidden = !m.hidden; v26DrawMini();
  });
  if(layersBtn) layersBtn.addEventListener("click", function(){
    var l = v26El("sncLayers"); l.hidden = !l.hidden; v26RenderLayers();
  });
  var mx = v26El("sncMiniX");
  if(mx) mx.addEventListener("click", function(){ v26El("sncMini").hidden = true; });
  var lx = v26El("sncLayersX");
  if(lx) lx.addEventListener("click", function(){ v26El("sncLayers").hidden = true; });

  var lg = v26El("sncLayersGroup");
  if(lg) lg.addEventListener("click", v26GroupSelected);
  var lu = v26El("sncLayersUngroup");
  if(lu) lu.addEventListener("click", v26UngroupSelected);
  var la = v26El("sncLayersAll");
  if(la) la.addEventListener("click", function(){
    var n = 0;
    state.nodes.forEach(function(x){ if(x.hidden){ x.hidden = false; n++; } });
    v26SyncHidden(); v26RenderLayers(); v26DrawMini();
    if(typeof scheduleSave === "function") scheduleSave();
    toast(n ? ("已显示 " + n + " 张隐藏卡片") : "当前没有隐藏的卡片");
  });

  var cv = v26El("sncMiniCanvas");
  if(cv) cv.addEventListener("click", function(e){
    if(!v26MiniMap) return;
    var r = cv.getBoundingClientRect();
    var px = (e.clientX - r.left) / r.width * cv.width;
    var py = (e.clientY - r.top) / r.height * cv.height;
    var wx = v26MiniMap.minX + (px - v26MiniMap.pad) / v26MiniMap.k;
    var wy = v26MiniMap.minY + (py - v26MiniMap.pad) / v26MiniMap.k;
    var stage = v26El("sncStage");
    state.view.x = stage.clientWidth / 2 - wx * state.view.k;
    state.view.y = stage.clientHeight / 2 - wy * state.view.k;
    applyView();
  });

  function pickRow(n, e){
    if(e && (e.shiftKey || e.ctrlKey || e.metaKey)) state.sel.add(n.id);
    else state.sel = new Set([n.id]);
    state.userPicked = n.id;
  }

  var body = v26El("sncLayersBody");
  if(body) body.addEventListener("click", function(e){
    /* 展开 / 收起 */
    var tw = e.target.closest("button[data-twist]");
    if(tw){
      var gid0 = tw.dataset.twist;
      v26SetGrpOpen(gid0, !v26GrpOpen(gid0));
      v26RenderLayers();
      return;
    }
    /* 组的眼睛：整组一起显隐 */
    var eg = e.target.closest("button[data-eyegrp]");
    if(eg){
      var gid = eg.dataset.eyegrp;
      var ms = v26GrpMembers(gid);
      var hide = !ms.every(function(x){ return !!x.hidden; });
      ms.forEach(function(x){ x.hidden = hide; });
      v26SyncHidden(); v26RenderLayers(); v26DrawMini();
      if(typeof scheduleSave === "function") scheduleSave();
      toast(hide ? ("已隐藏 " + ms.length + " 张 · 导出不会带上") : ("已显示 " + ms.length + " 张"));
      return;
    }
    /* 单张的眼睛 */
    var eye = e.target.closest("button[data-eye]");
    if(eye){
      var n = state.nodes.find(function(x){ return x.id === eye.dataset.eye; });
      if(n){
        n.hidden = !n.hidden;
        v26SyncHidden(); v26RenderLayers(); v26DrawMini();
        if(typeof scheduleSave === "function") scheduleSave();
        toast(n.hidden ? "已在画布上隐藏 · 导出不会带上" : "已恢复显示");
      }
      return;
    }
    /* 改名：行尾小笔（双击组名走下面的 dblclick） */
    var ed = e.target.closest("button[data-gedit]");
    if(ed){
      e.stopPropagation();
      v26EditGrpName(ed.dataset.gedit);
      return;
    }
    /* 双击组名：这里必须用 click 的 detail 计数，
       因为第一次点击会 renderAll → 图层面板重建，span 被换掉，
       第二次的 dblclick 落在已从文档里摘掉的旧节点上，冒泡不到 body。 */
    var gname = e.target.closest("[data-gname]");
    if(gname && e.detail >= 2){
      e.preventDefault();
      e.stopPropagation();
      v26EditGrpName(gname.dataset.gname);
      return;
    }
    /* 行：组行选中全组，成员行选中自己 */
    var gRow = e.target.closest(".snc-layer-row.is-grp");
    if(gRow){
      var ms2 = v26GrpMembers(gRow.dataset.grp);
      state.sel = new Set(ms2.map(function(x){ return x.id; }));
      state.userPicked = ms2.length ? ms2[0].id : null;
      renderAll();
      return;
    }
    var row = e.target.closest(".snc-layer-row");
    if(row){
      var t = state.nodes.find(function(x){ return x.id === row.dataset.lid; });
      if(t){ pickRow(t, e); renderAll(); ensureVisible(t); }
    }
  });

  /* 双击组名直接改（比先点小笔快） */
  if(body) body.addEventListener("dblclick", function(e){
    var nm = e.target.closest("[data-gname]");
    if(nm){
      e.preventDefault();
      e.stopPropagation();
      v26EditGrpName(nm.dataset.gname);
    }
  });

  /* ---------- 拖动排序 / 拖进组 ---------- */
  if(body) body.addEventListener("dragstart", function(e){
    var row = e.target.closest(".snc-layer-row");
    if(!row) return;
    var id = row.dataset.lid || null;
    var gid = row.dataset.grp || null;
    if(!id && !gid) return;
    /* 拖组行 = 拖整组：拿组里最上面那张当锚，落点按组处理 */
    var anchor = id || (v26GrpMembers(gid)[0] || {}).id;
    if(!anchor) return;
    v26Drag = {id: anchor, grpId: gid, zone: "", overId: ""};
    try{ e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", anchor); }catch(err){}
  });
  if(body) body.addEventListener("dragover", function(e){
    if(!v26Drag) return;
    var row = e.target.closest(".snc-layer-row");
    e.preventDefault();
    try{ e.dataTransfer.dropEffect = "move"; }catch(err){}
    v26ClearDropMarks();
    if(!row){ v26Drag.overId = ""; return; }
    var tid = row.dataset.lid || null;
    var tgid = row.dataset.grp || null;
    var targetId = tid || (v26GrpMembers(tgid)[0] || {}).id;
    if(!targetId || targetId === v26Drag.id) return;
    var zone = v26DropZone(row, e.clientY);
    /* 组行整行都可以当「放进这个组」 */
    if(tgid && zone === "into") row.classList.add("is-drop-into");
    else if(tid && tid !== v26Drag.id) row.classList.add(zone === "before" ? "is-drop-before" : "is-drop-after");
    else row.classList.add("is-drop-into");
    v26Drag.overId = targetId;
    v26Drag.zone = zone;
  });
  if(body) body.addEventListener("dragleave", function(e){
    if(!e.relatedTarget || !body.contains(e.relatedTarget)) v26ClearDropMarks();
  });
  if(body) body.addEventListener("drop", function(e){
    if(!v26Drag) return;
    e.preventDefault();
    v26ApplyDrop();
    v26Drag = null; v26ClearDropMarks();
  });
  if(body) body.addEventListener("dragend", function(){
    v26Drag = null; v26ClearDropMarks();
  });
})();

/* ---------------- B2 自动更新 / B3 日志排障（前端入口） ---------------- */
function v26AboutOut(text){
  var out = v26El("sncAboutOut");
  if(!out) return;
  out.hidden = false;
  out.textContent = String(text || "");
}
(function(){
  var chk = v26El("sncAboutCheckUpdate");
  if(chk) chk.addEventListener("click", function(){
    v26AboutOut("正在检查更新…");
    fetch("/api/update/check").then(function(r){ return r.json(); }).then(function(j){
      if(!j.ok){ v26AboutOut("检查失败：" + (j.error || "未知错误")); return; }
      if(j.hasUpdate){
        v26AboutOut("发现新版本 " + j.latest + "（当前 " + j.current + "）\n" +
                    (j.notes || "无更新说明") + "\n下载地址：" + (j.url || "未配置"));
        toast("发现新版本 " + j.latest);
      } else {
        v26AboutOut("已是最新版本 " + j.current + "\n" + (j.notes || "版本清单：" + (j.manifest || "未配置")));
        toast("已是最新版本");
      }
    }).catch(function(e){ v26AboutOut("检查更新失败：" + e.message + "\n可在「关于」打开日志排查"); });
  });
  var op = v26El("sncAboutOpenLogs");
  if(op) op.addEventListener("click", function(){
    fetch("/api/logs/open").then(function(r){ return r.json(); }).then(function(j){
      toast(j.ok ? "已打开日志文件夹" : ("打开失败：" + (j.error || "")));
    }).catch(function(){ toast("本地服务未连接，无法打开日志"); });
  });
  var tl = v26El("sncAboutTailLogs");
  if(tl) tl.addEventListener("click", function(){
    fetch("/api/logs/tail").then(function(r){ return r.json(); }).then(function(j){
      v26AboutOut(j.ok ? (j.text || "（日志为空）") : ("读取失败：" + (j.error || "")));
    }).catch(function(e){ v26AboutOut("读取日志失败：" + e.message); });
  });
  var st = v26El("sncSplashStatus");
  if(st){
    fetch("/api/health").then(function(r){ return r.json(); }).then(function(j){
      st.textContent = "本地服务已就绪 · " + (j.keyPresent ? "密钥已配置" : "尚未配置密钥");
    }).catch(function(){
      st.textContent = "本地服务未响应 · 可在「设置 → 关于」查看日志";
      st.classList.add("is-err");
    });
  }
})();
/* ==== V26-JS-END ==== */
