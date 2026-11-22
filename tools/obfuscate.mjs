// 前端 JS 混淆（v3.2 起支持多个逻辑块）：把 canvas.src.html 的脚本块用 terser 混淆，
// 输出 canvas.html（打包用）。源码版保持可读，开发继续改 canvas.src.html。
//
// 保留不混淆的块：
//   - block 0：首帧主题 / 无边框 shell 判定（必须在 DOM 解析前可读，且体积极小）
//   - block 1：window.SNC_PHOTOS 图片数据（base64，数据非逻辑，混淆无意义）
// 其余块（主逻辑、窗口外壳……）逐个混淆。
//
// 用法：node tools/obfuscate.mjs
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { minify } from 'terser';

// 路径跟着脚本自己走，不写死盘符。两种目录结构都要认：
//   开发目录：E:\无限画布\tools\  →  源码在 ..\proto\
//   归档目录：…\v3.7.3\01-未加密版\tools\  →  源码就在 ..\
const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = fs.existsSync(path.join(HERE, '..', 'canvas.src.html'))
  ? path.resolve(HERE, '..')
  : path.resolve(HERE, '..', 'proto');
const SRC = path.join(ROOT, 'canvas.src.html');
const OUT = path.join(ROOT, 'canvas.html');

const KEEP = 2;      // 前 2 块原样保留

const html = fs.readFileSync(SRC, 'utf8');

const scriptRe = /<script[^>]*>([\s\S]*?)<\/script>/g;
const blocks = [];
let m;
while ((m = scriptRe.exec(html)) !== null) {
  blocks.push({ full: m[0], code: m[1], start: m.index, end: m.index + m[0].length });
}
if (blocks.length <= KEEP) {
  console.error(`至少需要 ${KEEP + 1} 个 script 块，实际`, blocks.length);
  process.exit(1);
}

async function minifyBlock(code) {
  const result = await minify(code, {
    compress: {
      // 保守压缩：不做过激的 dead_code 消除，避免误删看似无副作用实则有用的调用
      dead_code: true,
      drop_console: false,
      passes: 2,
    },
    mangle: {
      // 打乱顶层与局部变量名（字符串、属性名不动，不影响 DOM 操作）
      toplevel: true,
    },
    format: {
      // 单行输出，进一步抹掉结构可读性
      beautify: false,
      comments: false,
    },
  });
  if (!result || !result.code) throw new Error('混淆失败');
  return result.code;
}

async function main() {
  let out = html;
  const report = [];
  // 从后往前替换，前面块的 start/end 才不会因为长度变化而错位
  for (let i = blocks.length - 1; i >= KEEP; i--) {
    const blk = blocks[i];
    const code = await minifyBlock(blk.code);
    report.unshift(`block${i}: ${blk.code.length} -> ${code.length} chars`);
    out = out.slice(0, blk.start) + `<script>\n${code}\n</script>` + out.slice(blk.end);
  }
  fs.writeFileSync(OUT, out, 'utf8');

  const a = fs.statSync(SRC).size;
  const b = fs.statSync(OUT).size;
  report.forEach((line) => console.log(line));
  console.log('文件:', a, '->', b, 'bytes (', (100 * b / a).toFixed(1), '%)');
  console.log('已写入', OUT);
}

main().catch((e) => { console.error(e); process.exit(1); });
