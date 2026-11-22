// v1.9 UI 验证：主题切换 / 设置三分区 / 技能预览图
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

const ROOT = 'E:\\无限画布\\proto';
const SHOTS = 'E:\\canvas-probe\\shots2';
fs.mkdirSync(SHOTS, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const HEALTH = {
  ok: true, backend: 'sensenova', keyPresent: true, key: 'sk-5nVI…PFVF',
  defaultModel: 'fast', model: 'sensenova-u1.5-fast',
  models: [{ key: 'fast', id: 'sensenova-u1.5-fast', label: 'U1.5 Fast', badge: '快' },
           { key: 'lite', id: 'sensenova-u1.5-lite', label: 'U1.5 Lite', badge: '稳' }],
  imageModels: [{ key: 'fast', id: 'sensenova-u1.5-fast', label: 'U1.5 Fast', badge: '快' },
                { key: 'lite', id: 'sensenova-u1.5-lite', label: 'U1.5 Lite', badge: '稳' }],
  textModels: [
    { id: 'sensenova-6.8-flash', label: 'SenseNova · sensenova-6.8-flash', vendor: 'SenseNova', vision: true },
    { id: 'sensenova-6.8-flash-lite', label: 'SenseNova · sensenova-6.8-flash-lite', vendor: 'SenseNova', vision: true },
    { id: 'deepseek-v4-flash', label: 'DeepSeek · deepseek-v4-flash', vendor: 'DeepSeek', vision: false },
    { id: 'glm-5.3', label: '智谱 GLM · glm-5.3', vendor: '智谱 GLM', vision: false },
    { id: 'kimi-k3', label: 'Kimi · kimi-k3', vendor: 'Kimi', vision: false }],
  defaultTextModel: 'sensenova-6.8-flash', modelCount: 8, catalogError: '',
  capabilities: { textToImage: true, referenceEdit: true, maxReferenceImages: 5, mask: false, multiN: false, sizeAuto: true, promptPolish: true, outputFormats: ['png', 'jpeg', 'webp'] },
};

const server = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://127.0.0.1');
  const p = u.pathname;
  if (p === '/' || p === '/canvas.html' || p === '/index.html') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(fs.readFileSync(path.join(ROOT, 'canvas.html')));
    return;
  }
  if (p === '/api/health') { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(HEALTH)); return; }
  if (p === '/api/models') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true, image: HEALTH.imageModels, text: HEALTH.textModels, total: 8, error: '' }));
    return;
  }
  if (p.startsWith('/api/')) { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ ok: false, code: 'stub', error: 'stub' })); return; }
  res.writeHead(404); res.end('no');
});

let cdpId = 0;
const pending = new Map();
let ws;

function cdp(method, params = {}) {
  const id = ++cdpId;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => {
    pending.set(id, resolve);
    setTimeout(() => { if (pending.has(id)) { pending.delete(id); reject(new Error('timeout ' + method)); } }, 25000);
  });
}
async function ev(expression) {
  const r = await cdp('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (r.result?.exceptionDetails) return 'EXC:' + (r.result.exceptionDetails.text || '');
  return r.result?.result?.value;
}
async function shot(name) {
  const r = await cdp('Page.captureScreenshot', { format: 'png' });
  const p = path.join(SHOTS, name);
  fs.writeFileSync(p, Buffer.from(r.result.data, 'base64'));
  return fs.statSync(p).size;
}
async function rect(sel) {
  const raw = await ev(`(function(){var b=document.querySelector(${JSON.stringify(sel)});if(!b)return '';var r=b.getBoundingClientRect();if(!r.width)return '';return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)});})()`);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}
async function clickAt(x, y) {
  await cdp('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y, button: 'none' });
  await cdp('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
  await sleep(25);
  await cdp('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
}
async function clickSel(sel, wait = 400) {
  const r = await rect(sel);
  if (!r) return false;
  await clickAt(r.x, r.y);
  await sleep(wait);
  return true;
}

const report = {};
let edge;

async function main() {
  await new Promise((r) => server.listen(8899, '127.0.0.1', r));

  edge = spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', [
    '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check',
    '--remote-debugging-port=9336', '--user-data-dir=E:\\canvas-probe\\prof4', '--window-size=1600,1000',
    'about:blank',
  ], { stdio: 'ignore' });

  let ver = null;
  for (let i = 0; i < 40; i++) {
    try { const r = await fetch('http://127.0.0.1:9336/json/version'); if (r.ok) { ver = await r.json(); break; } } catch {}
    await sleep(400);
  }
  if (!ver) throw new Error('cdp down');
  const list = await (await fetch('http://127.0.0.1:9336/json/list')).json();
  const page = list.find((t) => t.type === 'page');
  ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej); });
  ws.addEventListener('message', (e) => {
    let m; try { m = JSON.parse(e.data); } catch { return; }
    if (m.id && pending.has(m.id)) { const f = pending.get(m.id); pending.delete(m.id); f(m); }
  });

  await cdp('Page.enable');
  await cdp('Runtime.enable');
  const errs = [];
  ws.addEventListener('message', (e) => {
    try {
      const m = JSON.parse(e.data);
      if (m.method === 'Runtime.exceptionThrown') errs.push(m.params?.exceptionDetails?.text || 'exception');
    } catch {}
  });

  await cdp('Page.navigate', { url: 'http://127.0.0.1:8899/canvas.html' });
  for (let i = 0; i < 40; i++) {
    await sleep(500);
    const n = await ev("document.querySelectorAll('.snc-node').length");
    if (typeof n === 'number' && n >= 1) break;
  }
  // 每次从默认暗色开始，避免上次跑留下的 localStorage 干扰
  await ev("(function(){try{localStorage.removeItem('snc.theme.v1')}catch(e){}})()");
  await cdp('Page.reload');
  for (let i = 0; i < 40; i++) {
    await sleep(500);
    const n = await ev("document.querySelectorAll('.snc-node').length");
    if (typeof n === 'number' && n >= 1) break;
  }
  await sleep(1500);

  report.nodes = await ev("document.querySelectorAll('.snc-node').length");
  report.themeAttr = await ev("document.getElementById('snc').getAttribute('data-theme')");
  report.skillArtKeys = await ev("(function(){try{return Object.keys(SKILL_ART).length}catch(e){return 'n/a'}})()");
  report.navFontSize = await ev("getComputedStyle(document.querySelector('.snc-doc-nav button')).fontSize");
  report.itemFontSize = await ev("getComputedStyle(document.querySelector('.snc-doc-item')||document.querySelector('.snc-doc-new')).fontSize");
  report.featureFont = await ev("getComputedStyle(document.querySelector('.snc-doc-ws')).fontSize");
  report.railWidth = await ev("getComputedStyle(document.getElementById('snc')).getPropertyValue('--rail').trim()");
  report.shotDark = await shot('01-dark.png');

  // 设置 → 主题
  await clickSel('.snc-doc-foot [data-set]', 700);
  report.setNav = await ev(`(function(){
    var n = document.getElementById('sncSetNav');
    return JSON.stringify(Array.prototype.map.call(n.querySelectorAll('button'), function(b){return b.textContent.trim();}));
  })()`);
  report.themePaneVisible = await ev("!document.querySelector('.snc-pane[data-pane=\"theme\"]').hidden");
  report.footHiddenOnTheme = await ev("(function(){var f=document.querySelector('#sncSettings .snc-dlg-f');return f?f.hidden:'none'})()");
  report.shotSetTheme = await shot('02-set-theme.png');

  // 切到亮色
  await clickSel('#sncThemeGrid [data-theme-opt="light"]', 700);
  report.afterLight = await ev("document.getElementById('snc').getAttribute('data-theme')");
  report.lsSaved = await ev("(function(){try{return localStorage.getItem('snc.theme.v1')}catch(e){return 'n/a'}})()");
  report.shotSetLightTheme = await shot('03-set-theme-light.png');

  // 大模型调用页
  await clickSel('#sncSetNav button[data-pane="model"]', 800);
  report.modelPane = await ev(`(function(){
    var p = document.querySelector('.snc-pane[data-pane="model"]');
    var f = document.querySelector('#sncSettings .snc-dlg-f');
    var opt = Array.prototype.map.call(p.querySelectorAll('select option'), function(o){return o.textContent.trim();});
    return JSON.stringify({hidden: p.hidden, foot: f.hidden, options: opt,
      hasVisionTag: p.textContent.indexOf('\\u8bfb\\u56fe') >= 0,
      chips: Array.prototype.map.call(p.querySelectorAll('.snc-model-chip'), function(c){return c.textContent.trim();})});
  })()`);
  report.shotSetModel = await shot('04-set-model-light.png');

  // 关于页
  await clickSel('#sncSetNav button[data-pane="about"]', 700);
  report.aboutPane = await ev(`(function(){
    var p = document.querySelector('.snc-pane[data-pane="about"]');
    return JSON.stringify({hidden: p.hidden, text: p.textContent.replace(/\\s+/g,' ').trim().slice(0,260)});
  })()`);
  report.shotSetAbout = await shot('05-set-about-light.png');

  // 回主题页、关掉设置 —— 此时仍是亮色，截主界面
  await clickSel('#sncSetNav button[data-pane="theme"]', 400);
  await clickSel('#sncSetClose', 600);
  report.dlgClosed = await ev("document.getElementById('sncSettings').hidden");
  report.lightMain = await ev("getComputedStyle(document.getElementById('snc')).backgroundColor");
  report.shotLightMain = await shot('07-light-main.png');

  // 选中一张卡 → 技能面板
  const pick = await ev(`(function(){
    var ns = Array.prototype.slice.call(document.querySelectorAll('.snc-node'));
    var t = ns[0];
    for (var i=0;i<ns.length;i++){ var im = ns[i].querySelector('.snc-gen img');
      if (im && (im.getAttribute('src')||'').length > 200) { t = ns[i]; break; } }
    if (!t) return '';
    var r = t.getBoundingClientRect();
    return JSON.stringify({x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2),
      label: (t.querySelector('.snc-node-label')||{}).textContent||''});
  })()`);
  report.pick = pick;
  if (pick) {
    const pk = JSON.parse(pick);
    await clickAt(pk.x, pk.y);
    await sleep(600);
    await clickSel('#sncImgBar button[data-act="skill"]', 900);
    report.skillPop = await ev(`(function(){
      var p = document.getElementById('sncSkillPop');
      if (!p || p.hidden) return JSON.stringify({open: false});
      var tiles = Array.prototype.slice.call(document.querySelectorAll('#sncSkpBody .snc-skp-tile'));
      return JSON.stringify({open: true, n: tiles.length,
        hasArt: tiles.filter(function(t){return t.classList.contains('has-art')}).length,
        hasImg: tiles.filter(function(t){return t.classList.contains('has-img')}).length,
        names: tiles.map(function(t){var e=t.querySelector('em');return e?e.textContent.trim():'';}),
        srcLen: tiles.map(function(t){var i=t.querySelector('img');return i?(i.getAttribute('src')||'').length:0;})});
    })()`);
    report.shotSkillLight = await shot('08-skill-light.png');

    // 专项技能分组（亮色）
    await clickSel('#sncSkpTabs button[data-g="pro"]', 700);
    report.shotSkillProLight = await shot('09-skill-pro-light.png');
    await cdp('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await cdp('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await sleep(400);
  }

  // 切回暗色，截主界面
  await clickSel('.snc-doc-foot [data-set]', 600);
  await clickSel('#sncSetNav button[data-pane="theme"]', 400);
  await clickSel('#sncThemeGrid [data-theme-opt="dark"]', 500);
  report.backToDark = await ev("document.getElementById('snc').getAttribute('data-theme')");
  report.shotSetThemeDark = await shot('10-set-theme-dark.png');
  await clickSel('#sncSetClose', 600);
  report.shotDarkMain = await shot('11-dark-main.png');

  report.errors = errs;
  fs.writeFileSync('E:\\canvas-probe\\report2.json', JSON.stringify(report, null, 2), 'utf8');
  console.log('REPORT WRITTEN');
}

main()
  .catch((e) => { report.fatal = String(e.stack || e); fs.writeFileSync('E:\\canvas-probe\\report2.json', JSON.stringify(report, null, 2), 'utf8'); console.error('FATAL', e.message); })
  .finally(async () => {
    await sleep(300);
    try { edge?.kill('SIGKILL'); } catch {}
    try { server.close(); } catch {}
    setTimeout(() => process.exit(0), 600);
  });
