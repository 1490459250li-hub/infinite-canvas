// 把 arco-assets.snippet.js 注入 canvas.src.html 的主逻辑块（可重复执行）
// 用法：node tools/inject-arco-assets.mjs
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve('E:/无限画布/proto');
const SRC = path.join(ROOT, 'canvas.src.html');
const SNIP = path.join(ROOT, 'arco-assets.snippet.js');

const START = '/* ============================================================================\n * S1 + S2 + S3 资产层';
const END = 'if(typeof window !== "undefined"){ try{ window["SNC_ARCO"] = SNC_ARCO; }catch(e){} }\n';
const ANCHOR = '  /* ---- 内置技能：按效果图 / 照明设计最常见的改图动作整理 ----';

let html = fs.readFileSync(SRC, 'utf8');
const snippet = fs.readFileSync(SNIP, 'utf8');

// 先移除旧片段（幂等）
const a = html.indexOf(START);
if (a >= 0) {
  const b = html.indexOf(END, a);
  if (b < 0) { console.error('找到资产起始但找不到结束标记，已中止'); process.exit(1); }
  html = html.slice(0, a) + html.slice(b + END.length);
  console.log('已移除旧资产片段');
}
const at = html.indexOf(ANCHOR);
if (at < 0) { console.error('找不到注入锚点，已中止'); process.exit(1); }

html = html.slice(0, at) + snippet + '\n' + html.slice(at);
fs.writeFileSync(SRC, html, 'utf8');
console.log('已注入', snippet.length, 'chars →', SRC, '总', fs.statSync(SRC).size, 'bytes');
