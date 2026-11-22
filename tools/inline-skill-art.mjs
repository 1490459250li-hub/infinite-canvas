// 把压缩好的技能预览图注入 canvas.html 的 SKILL_ART
import fs from 'node:fs';

const index = JSON.parse(fs.readFileSync('E:\\canvas-probe\\skills\\thumbs\\index.json', 'utf8'));
const file = 'E:/无限画布/proto/canvas.html';
let html = fs.readFileSync(file, 'utf8');

if (!html.includes('/* SKILL_ART_PLACEHOLDER */')) {
  console.error('placeholder missing — already inlined?');
  process.exit(1);
}

const entries = Object.entries(index).map(([id, b64]) => {
  if (!b64 || b64.length < 2000) throw new Error('art too small: ' + id);
  return `    "${id}": "data:image/jpeg;base64,${b64}"`;
});

const block = entries.join(',\n');
html = html.replace('/* SKILL_ART_PLACEHOLDER */', block);
fs.writeFileSync(file, html, 'utf8');

console.log('inlined', entries.length, 'arts');
console.log('file size:', (fs.statSync(file).size / 1024).toFixed(0) + 'KB');
