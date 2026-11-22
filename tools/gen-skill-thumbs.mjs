// 把 12 张技能图压成 16:11 缩略图；bi-hand / bi-persp 做成左右对比图
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

const DIR = 'E:\\canvas-probe\\skills';
const OUT = path.join(DIR, 'thumbs');
fs.mkdirSync(OUT, { recursive: true });

const IDS = ['bi-night', 'bi-blue', 'bi-mat', 'bi-view', 'bi-hand',
  'bi-plan', 'bi-plant', 'bi-light', 'bi-people', 'bi-sky', 'bi-persp', 'bi-water'];

const PAGE = `<!doctype html><meta charset="utf-8"><body style="margin:0;background:#111">
<script>
const IDS = ${JSON.stringify(IDS)};
const W = 400, H = 275;

async function load(u){
  const r = await fetch(u);
  const b = await r.blob();
  return await createImageBitmap(b);
}
function cover(ctx, img, dx, dy, dw, dh){
  const k = Math.max(dw / img.width, dh / img.height);
  const sw = dw / k, sh = dh / k;
  ctx.drawImage(img, (img.width - sw) / 2, (img.height - sh) / 2, sw, sh, dx, dy, dw, dh);
}
// 梯形：上窄下宽，模拟镜头畸变/仰拍倾斜
function warp(ctx, img, dx, dy, dw, dh, topScale){
  const bands = 260;
  for (let i = 0; i < bands; i++) {
    const sy = img.height * i / bands;
    const shh = img.height / bands;
    const t = i / (bands - 1);
    const s = topScale + (1 - topScale) * t;
    const tw = dw * s;
    ctx.drawImage(img, 0, sy, img.width, shh,
      dx + (dw - tw) / 2, dy + dh * i / bands, tw, dh / bands + 0.7);
  }
}

async function run(){
  const out = {};
  for (const id of IDS) {
    const cv = document.createElement('canvas');
    cv.width = W; cv.height = H;
    const ctx = cv.getContext('2d');
    ctx.fillStyle = '#0d0e10';
    ctx.fillRect(0, 0, W, H);

    if (id === 'bi-hand') {
      const sk = await load('/f/_sketch.jpg');
      const res = await load('/f/bi-hand.jpg');
      ctx.save(); ctx.beginPath(); ctx.rect(0, 0, W / 2 - 1, H); ctx.clip();
      cover(ctx, sk, 0, 0, W / 2 - 1, H); ctx.restore();
      ctx.save(); ctx.beginPath(); ctx.rect(W / 2 + 1, 0, W / 2 - 1, H); ctx.clip();
      cover(ctx, res, W / 2 + 1, 0, W / 2 - 1, H); ctx.restore();
      ctx.fillStyle = 'rgba(255,255,255,.75)';
      ctx.fillRect(W / 2 - 1.5, 0, 3, H);
    } else if (id === 'bi-persp') {
      const img = await load('/f/bi-persp.jpg');
      ctx.save(); ctx.beginPath(); ctx.rect(0, 0, W / 2 - 1, H); ctx.clip();
      warp(ctx, img, 0, 0, W / 2 - 1, H, 0.72); ctx.restore();
      ctx.save(); ctx.beginPath(); ctx.rect(W / 2 + 1, 0, W / 2 - 1, H); ctx.clip();
      cover(ctx, img, W / 2 + 1, 0, W / 2 - 1, H); ctx.restore();
      ctx.fillStyle = 'rgba(255,255,255,.75)';
      ctx.fillRect(W / 2 - 1.5, 0, 3, H);
    } else {
      const img = await load('/f/' + id + '.jpg');
      cover(ctx, img, 0, 0, W, H);
    }

    out[id] = cv.toDataURL('image/jpeg', 0.78).split(',')[1];
  }
  await fetch('/save', { method: 'POST', body: JSON.stringify(out) });
  document.title = 'DONE';
}
run().catch((e) => { document.title = 'ERR'; fetch('/err?m=' + encodeURIComponent(e.message)); });
<\/script></body>`;

let edge = null;
let done = false;

const server = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://127.0.0.1');
  if (u.pathname === '/proc.html') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(PAGE);
    return;
  }
  if (u.pathname.startsWith('/f/')) {
    const name = decodeURIComponent(u.pathname.slice(3));
    const p = path.join(DIR, name);
    if (fs.existsSync(p)) {
      res.writeHead(200, { 'Content-Type': 'image/jpeg' });
      res.end(fs.readFileSync(p));
    } else { res.writeHead(404); res.end('no'); }
    return;
  }
  if (u.pathname === '/err') {
    console.error('PAGE ERR:', u.searchParams.get('m'));
    res.end('ok');
    return;
  }
  if (u.pathname === '/save' && req.method === 'POST') {
    let body = '';
    req.on('data', (c) => { body += c; });
    req.on('end', () => {
      const obj = JSON.parse(body);
      let total = 0;
      for (const [id, b64] of Object.entries(obj)) {
        const buf = Buffer.from(b64, 'base64');
        fs.writeFileSync(path.join(OUT, id + '.jpg'), buf);
        total += buf.length;
        console.log(id, Math.round(buf.length / 1024) + 'KB');
      }
      console.log('TOTAL', Math.round(total / 1024) + 'KB');
      fs.writeFileSync(path.join(OUT, 'index.json'), JSON.stringify(obj), 'utf8');
      res.end('ok');
      done = true;
      setTimeout(() => { try { edge.kill('SIGKILL'); } catch {} process.exit(0); }, 400);
    });
    return;
  }
  res.writeHead(404); res.end();
});

server.listen(8899, '127.0.0.1', () => {
  edge = spawn('C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', [
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--user-data-dir=E:\\canvas-probe\\prof3', '--window-size=800,600',
    'http://127.0.0.1:8899/proc.html',
  ], { stdio: 'ignore' });

  setTimeout(() => {
    if (!done) { console.error('TIMEOUT'); try { edge.kill('SIGKILL'); } catch {} process.exit(1); }
  }, 60000);
});
