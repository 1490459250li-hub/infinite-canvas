import pathlib, re

src = pathlib.Path("ui-polish-3.html").read_text(encoding="utf-8")

# ---------- 1. 追加光层样式 ----------
GLOW_CSS = r'''
  /* ================================================================
     画布边缘光（鼠标跟随）
     纯 CSS 渐变 + CSS 变量，rAF 只更新几个 px 值，不产生 layout
     ================================================================ */
  .app{
    --gx-blend:screen;
    --gx-b1:rgba(104,140,255,.030);
    --gx-b2:rgba(206,224,255,.028);
    --gx-r1:rgba(176,202,255,.130);
    --gx-s1:rgba(186,208,255,.38);
    --gx-p1:rgba(112,152,255,.08);
    --gx-bleed:rgba(136,170,255,.043);
    --gx-amb:rgba(92,126,240,.028);
  }
  .app[data-th="light"]{
    --gx-blend:normal;
    --gx-b1:rgba(88,116,255,.011);
    --gx-b2:rgba(120,146,255,.010);
    --gx-r1:rgba(64,96,238,.15);
    --gx-s1:rgba(64,96,238,.14);
    --gx-p1:rgba(88,116,255,.04);
    --gx-bleed:rgba(88,116,255,.035);
    --gx-amb:rgba(92,126,240,0);
  }
  .app[data-th="warm"]{
    --gx-b1:rgba(150,168,255,.13);
    --gx-b2:rgba(220,225,255,.11);
    --gx-r1:rgba(178,198,255,.86);
    --gx-bleed:rgba(150,176,255,.20);
    --gx-amb:rgba(92,126,240,.055);
  }

  .stage{ --sx:50%; --sy:44%; }
  /* 指针标记：只在预览里用，用来肉眼核对光心 */
  #ptr{position:absolute; left:0; top:0; width:0; height:0; z-index:20; pointer-events:none; display:none;}
  #ptr::before{content:""; position:absolute; left:-11px; top:-11px; width:22px; height:22px;
    border:1px dashed rgba(255,86,120,.85); border-radius:50%;}
  #ptr::after{content:""; position:absolute; left:-1px; top:-1px; width:2px; height:2px;
    background:rgba(255,86,120,.95); border-radius:50%;}
  body[data-ptr="1"] #ptr{display:block;}
  .rail{ --ry:50%; }

  /* 真实 logo（432×170 彩色 ∞）：按比例摆进原来的方图位置 */
  img.lg{display:block; object-fit:contain; object-position:left center; flex:none;}
  img.wb-logo{width:22px; height:9px; opacity:.96;}
  img.r-mark{width:19px; height:8px;}

  .gx{position:absolute; pointer-events:none; will-change:background;}

  .gx[data-l="bloom"]{
    inset:0; z-index:3;
    background:
      radial-gradient(340px 340px at var(--sx) var(--sy), var(--gx-b1), transparent 68%),
      radial-gradient(130px 130px at var(--sx) var(--sy), var(--gx-b2), transparent 72%),
      radial-gradient(52px 52px at var(--sx) var(--sy), rgba(230,242,255,.021), transparent 78%),
      radial-gradient(1200px 900px at var(--sx) var(--sy), var(--gx-amb), transparent 72%);
    mix-blend-mode:var(--gx-blend);
    opacity:1;
  }
  /* 四条独立的 1px 边：不用 mask，哪条边离鼠标近哪条亮 */
  .gx[data-l="rim"]{inset:0; z-index:7; mix-blend-mode:var(--gx-blend); opacity:.42;}
  .gx[data-l="rim"] .ed{position:absolute; grid-area:1/1; pointer-events:none;}
  .ed.t{left:0; right:0; top:0; height:1px;
    background:radial-gradient(640px 640px at var(--sx) 0%,
      var(--gx-r1) 0%, rgba(140,172,255,.038) 32%, rgba(120,150,255,.006) 70%, transparent 88%);}
  .ed.b{left:0; right:0; bottom:0; height:1px;
    background:radial-gradient(640px 640px at var(--sx) 100%,
      var(--gx-r1) 0%, rgba(140,172,255,.038) 32%, rgba(120,150,255,.006) 70%, transparent 88%);}
  .ed.l{top:0; bottom:0; left:0; width:1px;
    background:radial-gradient(640px 640px at 0% var(--sy),
      var(--gx-r1) 0%, rgba(140,172,255,.038) 32%, rgba(120,150,255,.006) 70%, transparent 88%);}
  .ed.r{top:0; bottom:0; right:0; width:1px;
    background:radial-gradient(640px 640px at 100% var(--sy),
      var(--gx-r1) 0%, rgba(140,172,255,.038) 32%, rgba(120,150,255,.006) 70%, transparent 88%);}

  /* 向内渗出的柔光：横向半径收窄到刚好覆盖 52px，光才会自然消失 */
  .ed::after{content:""; position:absolute; pointer-events:none;}
  .ed.t::after{left:0; right:0; top:0; height:52px;
    background:radial-gradient(620px 54px at var(--sx) 0%,
      var(--gx-bleed) 0%, rgba(120,155,255,.014) 42%, transparent 100%);}
  .ed.b::after{left:0; right:0; bottom:0; height:52px;
    background:radial-gradient(620px 54px at var(--sx) 100%,
      var(--gx-bleed) 0%, rgba(120,155,255,.014) 42%, transparent 100%);}
  .ed.l::after{top:0; bottom:0; left:0; width:56px;
    background:radial-gradient(58px 620px at 0% var(--sy),
      var(--gx-bleed) 0%, rgba(120,155,255,.014) 42%, transparent 100%);}
  .ed.r::after{top:0; bottom:0; right:0; width:56px;
    background:radial-gradient(58px 620px at 100% var(--sy),
      var(--gx-bleed) 0%, rgba(120,155,255,.014) 42%, transparent 100%);}

  /* 光层单独查看 */
  body[data-iso="rim"]   .gx:not([data-l="rim"]),
  body[data-iso="bloom"] .gx:not([data-l="bloom"]),
  body[data-iso="seam"]  .gx:not([data-l="seam"]),
  body[data-iso="spill"] .gx:not([data-l="spill"]){ display:none; }
  body[data-iso="rim"] .gx[data-l="rim"]{ opacity:1 !important; }

  /* 页面骨架 */
  .wrap{
    display:flex; flex-direction:row; gap:20px; padding:18px 22px 26px;
    align-items:flex-start;
    width:100%; max-width:1620px; margin:0 auto; align-self:stretch;
  }
  .stagebox{flex:1 1 auto; min-width:0;}
  .frame{
    position:relative; width:100%; aspect-ratio:1280 / 760;
    border-radius:10px; overflow:hidden; background:var(--paper,#0b0b0d);
    box-shadow:0 0 0 1px #24242c, 0 26px 60px -34px #000;
  }
  .frame > .app{
    position:absolute; left:0; top:0; width:1280px; height:760px;
    transform-origin:0 0;
  }
  .side{
    position:relative; width:268px; flex:0 0 268px; display:flex; flex-direction:column; gap:12px;
    background:#0e0e12; border:1px solid #1e1e26; border-radius:10px; padding:15px 16px 18px;
  }
  .side h3{margin:0; font-size:11px; letter-spacing:.1em; text-transform:uppercase;
    color:#6a6a74; font-weight:500;}
  .side p{margin:0; font-size:11.5px; line-height:1.65; color:#8a8a94;}
  .layerlist{display:flex; flex-direction:column; gap:9px; margin-top:2px;}
  .layerlist div{display:flex; gap:8px; font-size:11.5px; color:#9c9ca6; line-height:1.5;}
  .layerlist i{font-style:normal; width:7px; height:7px; border-radius:50%; flex:none; margin-top:5px;
    background:#4d6bfe; box-shadow:0 0 8px rgba(77,107,254,.8);}
  .layerlist div:nth-child(2) i{background:#8aa4ff;}
  .layerlist div:nth-child(3) i{background:#5b7bff;}
  .layerlist div:nth-child(4) i{background:#3f5cf2;}
  .layerlist b{color:#dcdce4; font-weight:600;}
  .row{display:flex; align-items:center; justify-content:space-between; gap:10px;}
  .row label{font-size:11.5px; color:#9c9ca6;}
  input[type=range]{-webkit-appearance:none; appearance:none; width:100%; height:3px;
    border-radius:2px; background:#26262f; outline:none; cursor:pointer;}
  input[type=range]::-webkit-slider-thumb{-webkit-appearance:none; width:11px; height:11px;
    border-radius:50%; background:#e8eaf0; border:0; box-shadow:0 0 0 3px rgba(120,140,255,.18);}
  .chk{display:flex; align-items:center; gap:6px; font-size:11.5px; color:#9c9ca6; cursor:pointer;
    user-select:none; white-space:nowrap;}
  .chk input{accent-color:#4d6bfe; width:13px; height:13px;}
  .hint{border-left:2px solid #2c3b7a; padding-left:10px; font-size:11px; color:#6f6b64; line-height:1.65;}
  .tmeter{display:flex; align-items:center; gap:8px; font-size:10px; color:#5f5f68;
    font-variant-numeric:tabular-nums;}
  .bar2{flex:1; height:2px; border-radius:2px; background:#1e1e26; overflow:hidden;}
  .bar2 i{display:block; height:100%; width:0; background:linear-gradient(90deg,#4d6bfe,#9db2ff);}
  @media (max-width:1120px){
    /* 竖排时 align-items:flex-start 会让 .stagebox 按内容宽度塌成 0（frame 是 100% 宽），
       必须显式拉伸，否则窄面板里画布直接消失 */
    .wrap{flex-direction:column; align-items:stretch;}
    .stagebox{width:100%; align-self:stretch;}
    .side{width:100%; flex:0 0 auto;}
  }
'''

src = src.replace("</style>", GLOW_CSS + "\n</style>", 1)

# ---------- 2. 取出模板，替换 body 之后的所有内容 ----------
tpl_start = src.index('<template id="tpl">')
tpl_end = src.index('</template>', tpl_start) + len('</template>')
template = src[tpl_start:tpl_end]

head = src[:src.index('<body>')]

BODY = '''
<body data-iso="all">

<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
  <linearGradient id="lgMark" x1="4" y1="0" x2="60" y2="0" gradientUnits="userSpaceOnUse">
    <stop offset="0"    stop-color="#5c7bfd"/>
    <stop offset=".14"  stop-color="#4589f8"/>
    <stop offset=".28"  stop-color="#36aef0"/>
    <stop offset=".42"  stop-color="#45c6b4"/>
    <stop offset=".52"  stop-color="#6fd683"/>
    <stop offset=".62"  stop-color="#c3d958"/>
    <stop offset=".70"  stop-color="#f5d94e"/>
    <stop offset=".80"  stop-color="#ffbb42"/>
    <stop offset=".90"  stop-color="#fe9145"/>
    <stop offset="1"    stop-color="#fe6a68"/>
  </linearGradient>
</defs></svg>

<header class="bar">
  <div class="bar-l">
    <b>无限画布 · 方案 A + 画布边缘光</b>
    <span>把鼠标移到窗口里：光晕跟着走，画布四边的 1px 边缘靠近时会亮起来</span>
  </div>
  <div class="bar-r">
    <div class="seg" id="isoSeg">
      <span class="seg-lb">光层</span>
      <button data-iso="all" class="on">全部</button>
      <button data-iso="rim">边缘</button>
      <button data-iso="bloom">光晕</button>
      <button data-iso="seam">接缝</button>
      <button data-iso="spill">溢出</button>
    </div>
    <div class="seg" id="thSeg">
      <span class="seg-lb">配色</span>
      <button data-th="dark" class="on">暗色</button>
      <button data-th="warm">暖灰</button>
      <button data-th="light">亮色</button>
    </div>
  </div>
</header>

<main class="wrap">
  <div class="stagebox">
    <div class="frame" id="frame">
      <div class="app" data-s="a" data-th="dark" id="app"></div>
    </div>
  </div>

  <aside class="side">
    <h3>四层光</h3>
    <div class="layerlist">
      <div><i></i><span><b>光晕</b>　画布上一团跟随鼠标的冷光，screen 混合</span></div>
      <div><i></i><span><b>边缘光</b>　画布四边 1px，越靠近边越亮</span></div>
      <div><i></i><span><b>接缝</b>　左栏与画布之间那道 1px，随鼠标纵向滑动</span></div>
      <div><i></i><span><b>溢出</b>　贴边时，光从画布漏到左栏 72px</span></div>
    </div>

    <h3 style="margin-top:6px">参数</h3>
    <div class="row"><label>整体强度</label><span id="vA" style="font-size:11px;color:#9c9ca6">100%</span></div>
    <input type="range" id="iA" min="0" max="240" value="100" step="5">
    <div class="row" style="margin-top:4px; flex-direction:column; align-items:flex-start; gap:6px">
      <label class="chk"><input type="checkbox" id="ptrChk">指针标记</label>
      <label class="chk"><input type="checkbox" id="amb">静止游走</label>
    </div>
    <div class="tmeter"><span>帧间隔</span><div class="bar2"><i id="barF"></i></div><span id="msF">—</span></div>

    <h3 style="margin-top:6px">实现</h3>
    <p>四层全是 CSS 渐变 + <code style="color:#a8b4d8">mix-blend-mode</code>，rAF 里只改 4 个 CSS 变量（<span style="color:#a8b4d8">--sx / --sy / --ry / opacity</span>），不触发重排，GPU 合成。</p>
    <p class="hint">亮色主题下 screen 混合会失效，所以自动切成 normal + 低透明度，读作一层淡淡的蓝。</p>
  </aside>
</main>

''' + template + '''

<script>
/* 新标识（与 splash-final.html 同一套参数：a=27.9 / ys=0.94 / 笔画 4.3） */
const MARK_D = (() => {
  let d = 'M';
  for (let i = 0; i <= 200; i++){
    const t = i / 200 * Math.PI * 2;
    const s = Math.sin(t), c = Math.cos(t), k = 1 + s*s;
    const x = 32 + 27.9 * c / k;
    const y = 32 + 27.9 * s * c / k * 0.94;
    d += (i ? 'L' : '') + x.toFixed(2) + ' ' + y.toFixed(2);
  }
  return d;
})();
const MARK_SVG = '<path d="' + MARK_D + '" fill="none" stroke="url(#lgMark)" stroke-width="4.3" stroke-linejoin="round" stroke-linecap="round"/>';

const app = document.getElementById('app');
const frame = document.getElementById('frame');
const tpl = document.getElementById('tpl');
app.innerHTML = tpl.content.firstElementChild.innerHTML;
app.dataset.s = 'a';

/* 图标换成用户提供的 logo（直接从 logo.png 裁出的彩色 ∞，不做任何重绘） */
app.querySelectorAll('.wb-logo, .r-mark').forEach(el => {
  const im = document.createElement('img');
  im.src = 'real/mark.png';
  im.alt = '';
  im.className = el.getAttribute('class') + ' lg';
  el.replaceWith(im);
});

/* 插入光层 */
const stage = app.querySelector('.stage');
const rail  = app.querySelector('.rail');
stage.insertAdjacentHTML('beforeend',
  '<div class="gx" data-l="bloom"></div>' +
  '<div class="gx" data-l="rim"><i class="ed t"></i><i class="ed r"></i><i class="ed b"></i><i class="ed l"></i></div>');
stage.insertAdjacentHTML('beforeend', '<div id="ptr"></div>');
rail.insertAdjacentHTML('beforeend',
  '<div class="gx" data-l="spill"></div><div class="gx" data-l="seam"></div>');

const bloom = stage.querySelector('[data-l="bloom"]');
const rim   = stage.querySelector('[data-l="rim"]');
const seam  = rail.querySelector('[data-l="seam"]');
const spill = rail.querySelector('[data-l="spill"]');

/* ---------------- 跟随 ---------------- */
let k = 1;                       // 缩放系数
let tx = 640, ty = 330;          // 目标（app 坐标）
let cx = 640, cy = 330;          // 当前
let lastMove = performance.now();
let strength = 1;
let ambient = false;      // 默认不自己游走：光心必须一直在鼠标下面
let running = true;

const box = { sl: 0, st: 0, sw: 1280, sh: 760, rt: 0 };   // stage/rail 在 app 坐标里的真实位置

function measure(){
  k = frame.clientWidth / 1280;
  if (!k || k !== k) k = 1;
  /* 设计稿是 1280×760，必须真的缩放到框里：以前只算了 k 没应用 transform，
     app 会溢出裁掉 12px，鼠标坐标和光心就差了十来像素。 */
  app.style.transform = 'scale(' + k + ')';
  const fr = frame.getBoundingClientRect();
  const s  = stage.getBoundingClientRect();
  const rl = rail.getBoundingClientRect();
  /* 光层挂在 stage / rail 内部，--sx/--sy 必须相对它们自己的盒子 */
  box.sl = (s.left  - fr.left) / k;
  box.st = (s.top   - fr.top)  / k;
  box.sw = s.width  / k;
  box.sh = s.height / k;
  box.rt = (rl.top  - fr.top)  / k;
}

function toApp(e){
  const r = frame.getBoundingClientRect();
  return { x: (e.clientX - r.left) / k, y: (e.clientY - r.top) / k };
}

frame.addEventListener('pointermove', e => {
  const p = toApp(e);
  tx = p.x; ty = p.y;
  lastMove = performance.now();
}, { passive: true });

frame.addEventListener('pointerleave', () => { lastMove = 0; });

/* 空闲时沿一条很慢的椭圆游走，避免画面彻底"死"掉 */
function ambientTarget(now){
  const t = now / 1000;
  return {
    x: 780 + Math.cos(t * 0.31) * 300,
    y: 360 + Math.sin(t * 0.23) * 180,
  };
}

function frameLoop(now){
  const dt = Math.min(50, now - lastStamp);
  lastStamp = now;

  const idle = now - lastMove > 1500;
  if (idle && ambient){
    const a = ambientTarget(now);
    tx += (a.x - tx) * 0.02;
    ty += (a.y - ty) * 0.02;
  }

  cx += (tx - cx) * 0.16;
  cy += (ty - cy) * 0.16;

  if (k !== k || !k) { k = 1; }

  const sx = cx - box.sl;
  const sy = cy - box.st;

  const ptr = document.getElementById('ptr');
  if (ptr) ptr.style.transform = 'translate(' + sx.toFixed(1) + 'px,' + sy.toFixed(1) + 'px)';
  stage.style.setProperty('--sx', sx.toFixed(1) + 'px');
  stage.style.setProperty('--sy', sy.toFixed(1) + 'px');
  rail.style.setProperty('--ry', (cy - box.rt).toFixed(1) + 'px');

  /* 靠近画布边缘时，边缘光才亮 */
  const w = box.sw, h = box.sh;
  const dEdge = Math.min(Math.max(0, sx), Math.max(0, w - sx),
                         Math.max(0, sy), Math.max(0, h - sy));
  const prox = 1 - Math.min(1, dEdge / 200);            // 0..1
  rim.style.opacity = ((0.043 + 0.10 * prox * prox) * strength).toFixed(3);

  /* 接缝：只有贴着左栏右缘时才起 */
  const nearSeam = sx < 130 ? 1 - Math.max(0, sx) / 130 : 0;
  seam.style.opacity = (nearSeam * 0.15 * strength).toFixed(3);
  spill.style.opacity = ((0.045 + 0.060 * nearSeam) * strength).toFixed(3);
  bloom.style.opacity = (0.70 + 0.30 * strength).toFixed(3);

  /* 帧间隔条 */
  if (frameLoop.n % 6 === 0){
    const el = document.getElementById('barF');
    const ms = document.getElementById('msF');
    el.style.width = Math.min(100, dt / 16.7 * 66) + '%';
    ms.textContent = dt.toFixed(1) + ' ms';
  }
  frameLoop.n++;

  requestAnimationFrame(frameLoop);
}
frameLoop.n = 0;
let lastStamp = performance.now();

/* ---------------- 控件 ---------------- */
document.getElementById('iA').oninput = e => {
  strength = e.target.value / 100;
  document.getElementById('vA').textContent = e.target.value + '%';
};
document.getElementById('amb').onchange = e => { ambient = e.target.checked; };
document.getElementById('ptrChk').onchange = e => { document.body.dataset.ptr = e.target.checked ? '1' : '0'; };

document.getElementById('thSeg').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  [...e.currentTarget.querySelectorAll('button')].forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  app.dataset.th = b.dataset.th;
  document.body.classList.toggle('light-bg', b.dataset.th === 'light');
};
document.getElementById('isoSeg').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  [...e.currentTarget.querySelectorAll('button')].forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  document.body.dataset.iso = b.dataset.iso;
};

window.addEventListener('resize', measure);

measure();
requestAnimationFrame(frameLoop);

/* 给截图脚本用 */
window.__move = (x, y) => {
  const r = frame.getBoundingClientRect();
  tx = (x - r.left) / (frame.clientWidth / 1280);
  ty = (y - r.top) / (frame.clientWidth / 1280);
  lastMove = performance.now() + 1e9;   // 关掉空闲游走，锁定目标
  cx = tx; cy = ty;
};
window.__settle = () => { cx = tx; cy = ty; };
window.__idle = v => { ambient = v; };
</script>
</body>
</html>
'''

pathlib.Path("ui-a-glow.html").write_text(head + BODY, encoding="utf-8")
print("written", len(head + BODY))
