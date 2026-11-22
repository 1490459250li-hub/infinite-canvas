// 打包版抽查：主题 / 设置三分区 / 技能预览图（连真实 exe 起的服务）
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

const SHOTS = 'E:\\canvas-probe\\shots3';
fs.mkdirSync(SHOTS, { recursive: true });
const PORT = 8003;
const PAGE = `http://127.0.0.1:${PORT}/canvas.html`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

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
let exe;

async function waitPage() {
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(PAGE, { method: 'GET' });
      if (r.ok) return true;
    } catch { /* not up yet */ }
    await sleep(500);
  }
  return false;
}

async function main() {
  // 自己拉起打包版，避免后台任务结束把它带走
  exe = spawn('E:\\无限画布\\proto\\dist\\无限画布.exe', ['--no-open', '--port', String(PORT)], {
    stdio: 'ignore',
    env: { ...process.env, TEMP: 'E:\\canvas-probe\\tmp', TMP: 'E:\\canvas-probe\\tmp' },
  });
  const up = await waitPage();
  report.exeUp = up;
  if (!up) throw new Error('packaged exe did not start');
  await sleep(1200);

  edge = spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', [
    '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check',
    '--remote-debugging-port=9338', '--user-data-dir=E:\\canvas-probe\\prof5', '--window-size=1600,1000',
    'about:blank',
  ], { stdio: 'ignore' });

  let ver = null;
  for (let i = 0; i < 40; i++) {
    try { const r = await fetch('http://127.0.0.1:9338/json/version'); if (r.ok) { ver = await r.json(); break; } } catch {}
    await sleep(400);
  }
  if (!ver) throw new Error('cdp down');
  report.browser = ver.Browser;

  const list = await (await fetch('http://127.0.0.1:9338/json/list')).json();
  const page = list.find((t) => t.type === 'page');
  ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.addEventListener('open', res); ws.addEventListener('error', rej); });
  const errs = [];
  ws.addEventListener('message', (e) => {
    let m; try { m = JSON.parse(e.data); } catch { return; }
    if (m.id && pending.has(m.id)) { const f = pending.get(m.id); pending.delete(m.id); f(m); }
    if (m.method === 'Runtime.exceptionThrown') errs.push(m.params?.exceptionDetails?.text || 'exception');
  });

  await cdp('Page.enable');
  await cdp('Runtime.enable');

  await cdp('Page.navigate', { url: PAGE });
  for (let i = 0; i < 40; i++) {
    await sleep(500);
    const n = await ev("document.querySelectorAll('.snc-node').length");
    if (typeof n === 'number' && n >= 1) break;
  }
  await ev("(function(){try{localStorage.removeItem('snc.theme.v1')}catch(e){}})()");
  await cdp('Page.reload');
  for (let i = 0; i < 40; i++) {
    await sleep(500);
    const n = await ev("document.querySelectorAll('.snc-node').length");
    if (typeof n === 'number' && n >= 1) break;
  }
  await sleep(1400);

  report.nodes = await ev("document.querySelectorAll('.snc-node').length");
  report.health = await ev("fetch('/api/health').then(r=>r.json()).then(j=>j.ok+'/'+j.keyPresent)");
  report.rail = await ev("getComputedStyle(document.getElementById('snc')).getPropertyValue('--rail').trim()");
  report.navFont = await ev("getComputedStyle(document.querySelector('.snc-doc-nav button')).fontSize");
  report.shotDark = await shot('p1-dark-main.png');

  // 设置
  await clickSel('.snc-doc-foot [data-set]', 800);
  report.nav = await ev(`(function(){return JSON.stringify(Array.prototype.map.call(
    document.querySelectorAll('#sncSetNav button'), function(b){return b.textContent.trim();}));})()`);
  report.themePane = await ev("!document.querySelector('.snc-pane[data-pane=\"theme\"]').hidden");
  report.shotThemePane = await shot('p2-set-theme.png');

  // 亮色
  await clickSel('#sncThemeGrid [data-theme-opt="light"]', 800);
  report.lightAttr = await ev("document.getElementById('snc').getAttribute('data-theme')");
  report.shotSetThemeLight = await shot('p3-set-theme-light.png');

  // 模型页
  await clickSel('#sncSetNav button[data-pane="model"]', 900);
  report.modelPane = await ev(`(function(){
    var p = document.querySelector('.snc-pane[data-pane="model"]');
    var f = document.querySelector('#sncSettings .snc-dlg-f');
    return JSON.stringify({hidden: p.hidden, foot: f.hidden,
      hasVision: p.textContent.indexOf('读图') >= 0,
      opts: Array.prototype.map.call(p.querySelectorAll('select option'), function(o){return o.textContent.trim();}).slice(0,6)});
  })()`);
  report.shotModelLight = await shot('p4-set-model-light.png');

  // 关于页
  await clickSel('#sncSetNav button[data-pane="about"]', 700);
  report.about = await ev("document.querySelector('.snc-pane[data-pane=\"about\"]').textContent.replace(/\\s+/g,' ').trim().slice(0,120)");
  report.shotAbout = await shot('p5-set-about-light.png');

  // 关设置，看亮色主界面
  await clickSel('#sncSetClose', 700);
  report.shotLightMain = await shot('p6-light-main.png');

  // 技能面板（亮色）
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
    await clickSel('#sncImgBar button[data-act="skill"]', 1000);
    report.skillPop = await ev(`(function(){
      var p = document.getElementById('sncSkillPop');
      if (!p || p.hidden) return JSON.stringify({open:false});
      var t = Array.prototype.slice.call(document.querySelectorAll('#sncSkpBody .snc-skp-tile'));
      return JSON.stringify({open:true, n:t.length,
        art:t.filter(function(x){return x.classList.contains('has-art')}).length,
        lens:t.map(function(x){var i=x.querySelector('img');return i?(i.getAttribute('src')||'').length:0;}),
        names:t.map(function(x){var e=x.querySelector('em');return e?e.textContent.trim():'';})});
    })()`);
    report.shotSkillLight = await shot('p7-skill-light.png');
    await clickSel('#sncSkpTabs button[data-g="pro"]', 700);
    report.shotSkillProLight = await shot('p8-skill-pro-light.png');
    await cdp('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await cdp('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await sleep(400);
  }

  // 切回暗色收尾
  await clickSel('.snc-doc-foot [data-set]', 700);
  await clickSel('#sncSetNav button[data-pane="theme"]', 400);
  await clickSel('#sncThemeGrid [data-theme-opt="dark"]', 600);
  await clickSel('#sncSetClose', 600);
  report.backDark = await ev("document.getElementById('snc').getAttribute('data-theme')");
  report.shotDarkBack = await shot('p9-dark-back.png');

  report.errors = errs;
  fs.writeFileSync('E:\\canvas-probe\\report3.json', JSON.stringify(report, null, 2), 'utf8');
  console.log('REPORT WRITTEN');
}

main()
  .catch((e) => { report.fatal = String(e.stack || e); fs.writeFileSync('E:\\canvas-probe\\report3.json', JSON.stringify(report, null, 2), 'utf8'); console.error('FATAL', e.message); })
  .finally(async () => {
    await sleep(300);
    try { edge?.kill('SIGKILL'); } catch {}
    try { exe?.kill('SIGKILL'); } catch {}
    setTimeout(() => process.exit(0), 600);
  });
