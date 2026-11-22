// 补一张手绘线稿（bi-hand 的对比左半）
import fs from 'node:fs';

const BASE = 'https://token.sensenova.cn/v1';
const OUT = 'E:\\canvas-probe\\skills';
const env = fs.readFileSync('E:/无限画布/proto/.env', 'utf8');
const KEY = (env.match(/SENSENOVA_API_KEY=(.+)/) || [])[1].trim();

const base = fs.readFileSync(OUT + '\\_base.jpg');
const url = 'data:image/jpeg;base64,' + base.toString('base64');

const prompt = '把这张建筑景观照片转换成黑白手绘线稿：只用黑色细线勾勒建筑轮廓、窗框、' +
  '铺装分缝、树木枝干与灌木边界，去掉所有颜色、阴影与材质纹理，保留原有透视与构图，' +
  '白底黑线，像建筑师现场画的徒手草图，线条略有手绘抖动。';

const r = await fetch(BASE + '/images/edits', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + KEY },
  body: JSON.stringify({
    model: 'sensenova-u1.5-fast', prompt, images: [{ image_url: url }], size: 'auto',
    n: 1, response_format: 'b64_json', output_format: 'jpeg', watermark: false, prompt_extend: true,
  }),
});
const txt = await r.text();
if (!r.ok) { console.error('FAIL', r.status, txt.slice(0, 300)); process.exit(1); }
const j = JSON.parse(txt);
const b64 = j?.data?.[0]?.b64_json;
if (!b64) { console.error('no b64'); process.exit(1); }
const buf = Buffer.from(b64, 'base64');
fs.writeFileSync(OUT + '\\_sketch.jpg', buf);
console.log('sketch ok', buf.length);
