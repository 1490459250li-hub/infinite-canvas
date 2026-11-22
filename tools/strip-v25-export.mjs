/* v2.6：按用户要求撤回「汇报用 PDF」与「设计汇报页 HTML」两项导出。
   只按唯一标记切除，幂等；不触碰 exportBoard / exportNode / readAllFonts。 */
import fs from "node:fs";

const file = "proto/canvas.src.html";
let h = fs.readFileSync(file, "utf8");
const before = h.length;

function cut(startMark, endMark, label) {
  const a = h.indexOf(startMark);
  if (a < 0) { console.log("skip (no start):", label); return; }
  const b = h.indexOf(endMark, a);
  if (b < 0) { console.log("skip (no end):", label); return; }
  h = h.slice(0, a) + h.slice(b);
  console.log("cut:", label, (b - a), "chars");
}

// CSS：汇报页配置对话框专用样式
cut("/* ---------- v2.5 · 设计汇报页导出对话框 ---------- */",
    "/* ---------- 图片放大预览（双击画布卡片） ----------", "report CSS");

// DOM：汇报页对话框 + 遮罩
cut("  <!-- v2.5 · 设计汇报页导出：单文件离线 HTML",
    "  <!-- 最终用户许可协议（EULA） -->", "report DOM");

// JS：exportPDF / buildPDF / reportCSS / reportHTML / exportReport / 对话框事件
cut("  /* 汇报用 PDF：A4 横版，整板图按比例居中，单页，纯前端生成 */",
    "  /* 顶栏导出菜单 */", "PDF + report JS");

// 菜单项
h = h.replace('          <button type="button" role="menuitem" data-exp="pdf">汇报用 PDF（A4 横）</button>\n', "");
h = h.replace('          <button type="button" role="menuitem" data-exp="report">设计汇报页 HTML</button>\n', "");
// 菜单分支
h = h.replace('      else if(k === "pdf") exportPDF();\n', "");
h = h.replace('      else if(k === "report") openReportDlg();\n', "");

fs.writeFileSync(file, h, "utf8");
console.log("bytes:", before, "->", h.length);
const left = ["exportPDF", "buildPDF", "sncReportDlg", "openReportDlg", "escReport", "data-exp=\"pdf\"", "data-exp=\"report\""];
left.forEach(k => console.log("leftover", k, ":", (h.match(new RegExp(k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g")) || []).length));
