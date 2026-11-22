// 把 canvas.src.html 里的内联 base64 预览图抽成 proto/art/*.jpg 外链。
//
// 以前 21 张技能预览图 + 2 张示例照片全以 data URL 内联，共约 1.6 MB，
// 占源码七成多 —— 页面每次启动都要把这 1.6 MB 一并 parse。
// 抽成文件后由 server 的 /art/ 路由按需加载，还能吃到浏览器缓存。
//
// 幂等：已经是 /art/xxx.jpg 的条目会跳过；可反复执行。
//
// 用法：node tools/extract-art.mjs [--dry]

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const PROTO = path.join(ROOT, 'proto');
const SRC = path.join(PROTO, 'canvas.src.html');
const ARTDIR = path.join(PROTO, 'art');
const DRY = process.argv.includes('--dry');

// 这两张是示例照片，命名上跟技能预览图区分开
const PHOTO_KEYS = new Set(['courtyard', 'aerial']);

// 版本查询串：从 server.py 的 APP_VERSION 取，发版升版本号后重跑本脚本即自动失效旧缓存
const PY = fs.readFileSync(path.join(PROTO, 'server.py'), 'utf8');
const VER = (PY.match(/APP_VERSION\s*=\s*"([\d.]+)"/) || [])[1] || '0';
const VQ = VER.replace(/\./g, '');

// 键有两种写法：SKILL_ART 里是带引号的 "bi-night"，SNC_PHOTOS 里是不带引号的 courtyard
const RE = /"?([\w-]+)"?\s*:\s*"data:image\/(jpeg|jpg|png|webp);base64,([A-Za-z0-9+/=\s]+)"/g;

let html = fs.readFileSync(SRC, 'utf8');
let bytes = Buffer.byteLength(html, 'utf8');

if (!fs.existsSync(ARTDIR) && !DRY) fs.mkdirSync(ARTDIR, { recursive: true });

const written = [];
html = html.replace(RE, (whole, key, ext, b64) => {
  const clean = b64.replace(/\s+/g, '');
  const buf = Buffer.from(clean, 'base64');
  if (buf.length < 8000) {
    console.log(`  跳过 ${key}：只有 ${buf.length} B，可能不是有效图`);
    return whole;
  }
  const prefix = PHOTO_KEYS.has(key) ? 'photo-' : 'skill-';
  const name = `${prefix}${key}.${ext === 'jpeg' ? 'jpg' : ext}`;
  if (!DRY) fs.writeFileSync(path.join(ARTDIR, name), buf);
  written.push({ key, name, b64: clean.length, file: buf.length });
  // 带版本查询串：页面本身 no-store，图片走一天缓存，发版改 v 即可失效
  return `"${key}": "/art/${name}?v=${VQ}"`;
});

if (DRY) {
  console.log('[dry] 将抽出', written.length, '张');
  written.forEach(w => console.log('  ', w.key, '->', w.name, w.file, 'B'));
  process.exit(0);
}

fs.writeFileSync(SRC, html, 'utf8');
const after = Buffer.byteLength(html, 'utf8');

console.log(`抽出 ${written.length} 张到 proto/art/`);
written.forEach(w => console.log(`  ${w.key.padEnd(12)} -> ${w.name.padEnd(24)} ${(w.file / 1024).toFixed(1)} KB`));
const total = written.reduce((a, b) => a + b.file, 0);
console.log(`\n图片合计 ${(total / 1024).toFixed(0)} KB（base64 后约 ${(total * 4 / 3 / 1024).toFixed(0)} KB）`);
console.log(`canvas.src.html: ${(bytes / 1024).toFixed(0)} KB -> ${(after / 1024).toFixed(0)} KB`);
