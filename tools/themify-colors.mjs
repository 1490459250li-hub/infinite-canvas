// 把 canvas.html 主样式表里的硬编码颜色换成语义变量，为双主题做准备
import fs from 'node:fs';

const file = 'E:/无限画布/proto/canvas.html';
const raw = fs.readFileSync(file, 'utf8');
const lines = raw.split('\n');

let start = -1, end = -1;
for (let i = 0; i < lines.length; i++) {
  if (/^\s*<style/.test(lines[i])) start = i;
  else if (/^\s*<\/style>/.test(lines[i]) && start >= 0) end = i;
}
if (start < 0 || end < 0) throw new Error('style block not found');

const MAP = {
  // 背景阶梯（深 → 浅）
  '0d0e10': 'paper', '0f1113': 'paper', '0f1114': 'paper', '101215': 'paper',
  '131519': 'panel', '141619': 'panel', '14161a': 'panel', '14171a': 'panel',
  '14181c': 'panel', '15181c': 'panel', '171a1e': 'panel', '181b1f': 'panel', '181c21': 'panel',
  '1a1d21': 'card', '1b1e22': 'card', '1b1e23': 'card', '1b1f24': 'card',
  '1c1f24': 'card', '1c2026': 'card', '1d2126': 'raise', '1e2126': 'raise',
  '1e2227': 'raise', '1e2228': 'raise', '1f2329': 'raise', '20242a': 'raise',
  '22262c': 'hover', '22272e': 'hover', '232830': 'hover', '24282e': 'hover',
  '242830': 'hover', '26292e': 'hover', '262a30': 'hover', '23272d': 'raise',
  // 分隔线阶梯
  '262b32': 'line', '272c33': 'line',
  '2a2e34': 'line2', '2a2f36': 'line2', '2a3038': 'line2', '2b3037': 'line2',
  '2c3138': 'line2', '2e333a': 'line2',
  '30353c': 'line3', '333941': 'line3', '333a42': 'line3', '3a4149': 'line3',
  '4a5058': 'edge',
  // 文字阶梯（弱 → 强）
  '5d5a54': 'faint2', '5f5b55': 'faint2', '5f5c56': 'faint2',
  '66635d': 'faint', '6b6760': 'faint', '6f6b64': 'faint', '736f68': 'faint',
  '77736c': 'faint', '7d7972': 'faint',
  '807c75': 'muted', '8d8980': 'muted', '8f8c85': 'muted', '8d9096': 'muted', '9a958c': 'muted',
  'a9a196': 'ink3', 'a8a49c': 'ink3',
  'b8b2a8': 'ink2', 'b8b3aa': 'ink2', 'c9c5bd': 'ink2', 'cdc9c1': 'ink2',
  'd8d4cc': 'ink', 'd9d5cd': 'ink', 'dcd8d1': 'ink', 'e2dfd8': 'ink',
  'e9e7e2': 'ink', 'f0eee9': 'inkStrong', 'f1eee8': 'inkStrong',
  'f2efe8': 'inkStrong', 'f3efe8': 'inkStrong', 'f7f4ee': 'inkStrong',
};

// 语义彩色：保留原值（状态/强调），不做映射
const KEEP = new Set([
  '1b1614', '1d1614', '1d1a14', '241a17', '241c18', '16211c', '2c221c', '3a2019',
  '33241f', '3a2b26', '3d2a23', '3d3527', '5a3d31', '2f4a3c',
  'ba4525', 'c9532f', 'e0603a', 'e0704f', 'e9a68e', 'ffb4a4', 'ffd6c6', 'ffd9c8',
  'f0b9a4', 'f0c9b6', 'f0d3a4', 'c9a86a', 'd8b98a', 'cbb98f', 'e6dfd2',
  '9fb2c9', '9cc6f0', 'b7c6dd', '8fc9a8', 'b9d3bd',
]);

const css = lines.slice(start, end + 1);
// 变量定义这一段单独保护（#snc{ ... }）
let varStart = -1, varEnd = -1;
for (let i = 0; i < css.length; i++) {
  if (/^#snc\{/.test(css[i])) {
    varStart = i;
    for (let j = i; j < css.length; j++) if (css[j] === '}') { varEnd = j; break; }
    break;
  }
}

const counts = {};
let unknown = {};
const out = css.map((line, i) => {
  if (i >= varStart && i <= varEnd) return line;
  return line.replace(/#([0-9a-fA-F]{6})\b/g, (m, h) => {
    const k = h.toLowerCase();
    if (KEEP.has(k)) return m;
    const name = MAP[k];
    if (!name) { unknown[k] = (unknown[k] || 0) + 1; return m; }
    counts[name] = (counts[name] || 0) + 1;
    return `var(--${name})`;
  });
});

fs.writeFileSync('E:/canvas-probe/css-backup.txt', css.join('\n'), 'utf8');
const next = [...lines.slice(0, start), ...out, ...lines.slice(end + 1)];
fs.writeFileSync(file, next.join('\n'), 'utf8');

console.log('replaced:', JSON.stringify(counts, null, 0));
console.log('unknown hex left:', JSON.stringify(unknown, null, 0));
console.log('var block lines:', varStart, '..', varEnd);
