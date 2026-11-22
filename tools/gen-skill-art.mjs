// 为 12 条内置技能各生成一张效果预览图（真实调用 SenseNova）
import fs from 'node:fs';
import path from 'node:path';

const BASE = 'https://token.sensenova.cn/v1';
const OUT = 'E:\\canvas-probe\\skills';
fs.mkdirSync(OUT, { recursive: true });

const env = fs.readFileSync('E:/无限画布/proto/.env', 'utf8');
const KEY = (env.match(/SENSENOVA_API_KEY=(.+)/) || [])[1].trim();
const MODEL = 'sensenova-u1.5-fast';

const html = fs.readFileSync('E:/无限画布/proto/canvas.html', 'utf8');
const skills = [];
const re = /\{id:"(bi-[a-z]+)"([^}]*?)prompt:"((?:[^"\\]|\\.)*)"/g;
for (const m of html.matchAll(re)) {
  skills.push({ id: m[1], prompt: m[3].replace(/\\"/g, '"') });
}
console.log('skills found:', skills.length, skills.map((s) => s.id).join(','));

const H = { 'Content-Type': 'application/json', Authorization: 'Bearer ' + KEY };

async function call(endpoint, payload) {
  const r = await fetch(BASE + endpoint, { method: 'POST', headers: H, body: JSON.stringify(payload) });
  const txt = await r.text();
  if (!r.ok) throw new Error(endpoint + ' ' + r.status + ' ' + txt.slice(0, 200));
  const j = JSON.parse(txt);
  const b64 = j?.data?.[0]?.b64_json;
  if (!b64) throw new Error('no b64: ' + txt.slice(0, 200));
  return Buffer.from(b64, 'base64');
}

async function genImage(prompt, size) {
  return call('/images/generations', {
    model: MODEL, prompt, size, n: 1, response_format: 'b64_json',
    output_format: 'jpeg', watermark: false, prompt_extend: true,
  });
}

async function editImage(prompt, dataUrl) {
  return call('/images/edits', {
    model: MODEL, prompt, images: [{ image_url: dataUrl }], size: 'auto', n: 1,
    response_format: 'b64_json', output_format: 'jpeg', watermark: false, prompt_extend: true,
  });
}

const BASE_PROMPT = '现代社区庭院日景效果图：浅灰色花岗岩铺装广场，两侧列植落叶乔木，' +
  '中央有休憩座椅与低矮景墙，背景为三层住宅立面与大面积玻璃窗。白天晴朗，自然光柔和，' +
  '一点透视构图稳定，材质真实，画面干净，专业建筑景观效果图质感。';

const PLAN_PROMPT = '一张黑白建筑总平面线稿图，正交俯视：包含建筑轮廓、内部房间分隔、' +
  '道路、广场铺装分格、绿地边界与乔木树冠符号，线条粗细统一，纯黑白无颜色、无阴影、' +
  '无任何文字标注，白底黑线，标准图纸风格。';

async function main() {
  const report = {};
  const t0 = Date.now();

  let baseJpg;
  const basePath = path.join(OUT, '_base.jpg');
  if (fs.existsSync(basePath)) {
    baseJpg = fs.readFileSync(basePath);
    console.log('base cached');
  } else {
    console.log('gen base…');
    baseJpg = await genImage(BASE_PROMPT, '1024x576');
    fs.writeFileSync(basePath, baseJpg);
  }
  const baseUrl = 'data:image/jpeg;base64,' + baseJpg.toString('base64');

  let planJpg;
  const planPath = path.join(OUT, '_plan.jpg');
  if (fs.existsSync(planPath)) {
    planJpg = fs.readFileSync(planPath);
    console.log('plan cached');
  } else {
    console.log('gen plan…');
    planJpg = await genImage(PLAN_PROMPT, '1024x1024');
    fs.writeFileSync(planPath, planJpg);
  }
  const planUrl = 'data:image/jpeg;base64,' + planJpg.toString('base64');

  for (const s of skills) {
    const dest = path.join(OUT, s.id + '.jpg');
    if (fs.existsSync(dest) && fs.statSync(dest).size > 8000) {
      console.log('skip', s.id);
      report[s.id] = 'cached';
      continue;
    }
    const src = s.id === 'bi-plan' ? planUrl : baseUrl;
    const started = Date.now();
    try {
      const buf = await editImage(s.prompt, src);
      fs.writeFileSync(dest, buf);
      const ms = Date.now() - started;
      report[s.id] = { bytes: buf.length, ms };
      console.log('ok', s.id, buf.length, ms + 'ms');
    } catch (e) {
      report[s.id] = 'FAIL ' + e.message;
      console.log('FAIL', s.id, e.message);
    }
  }

  report._elapsed = Math.round((Date.now() - t0) / 1000) + 's';
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 2), 'utf8');
  console.log('DONE');
}

main().catch((e) => { console.error('FATAL', e.message); process.exit(1); });
