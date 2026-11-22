/* v2.6 幂等注入：把 tools/v26.css|html|js 插进 canvas.src.html。
   主逻辑 JS 必须落在 boot() 之前、主 IIFE 之内，才能复用 state / runJob 等。 */
import fs from "node:fs";

const file = "proto/canvas.src.html";
const css = fs.readFileSync("tools/v26.css", "utf8").trim();
const html = fs.readFileSync("tools/v26.html", "utf8").trim();
const js = fs.readFileSync("tools/v26.js", "utf8").trim();
let h = fs.readFileSync(file, "utf8");

function stripBlock(start, end) {
  const a = h.indexOf(start);
  if (a < 0) return;
  const b = h.indexOf(end, a);
  if (b < 0) return;
  h = h.slice(0, a) + h.slice(b + end.length);
}
stripBlock("/* ==== V26-CSS-START ==== */", "/* ==== V26-CSS-END ==== */");
stripBlock("<!-- ==== V26-HTML-START ==== -->", "<!-- ==== V26-HTML-END ==== -->");
stripBlock("/* ==== V26-JS-START ==== */", "/* ==== V26-JS-END ==== */");
// 幂等：清掉上一轮插入的三处小片段
h = h.replace(/<!-- V26-TOP -->.*?<!-- \/V26-TOP -->\s*/s, "");
h = h.replace(/<!-- V26-ABOUT -->.*?<!-- \/V26-ABOUT -->\s*/s, "");
h = h.replace(/<!-- V26-SPLASH -->.*?<!-- \/V26-SPLASH -->\s*/s, "");

function insertBefore(mark, text, label) {
  const i = h.lastIndexOf(mark);
  if (i < 0) throw new Error("anchor not found: " + label);
  h = h.slice(0, i) + text + "\n" + h.slice(i);
  console.log("insert:", label);
}

// CSS：主样式表末尾
insertBefore("</style>", css, "CSS");

// 顶栏工具按钮
const topAnchor = '<span class="snc-queue" id="sncQueue" hidden title="生成队列"></span>';
if (h.indexOf(topAnchor) < 0) throw new Error("top anchor missing");
h = h.replace(topAnchor, topAnchor + `
      <!-- V26-TOP -->
      <button type="button" class="snc-toolbtn" id="sncTidyBtn" title="按派生关系整理画布">整理画布</button>
      <button type="button" class="snc-toolbtn" id="sncMiniBtn" title="打开/关闭小地图">小地图</button>
      <button type="button" class="snc-toolbtn" id="sncLayersBtn" title="打开/关闭图层面板">图层</button>
      <!-- /V26-TOP -->`);
console.log("insert: top buttons");

// 关于页工程工具
const aboutAnchor = '<div class="snc-about-eula">';
if (h.indexOf(aboutAnchor) < 0) throw new Error("about anchor missing");
h = h.replace(aboutAnchor, `<!-- V26-ABOUT -->
          <div class="snc-about-tools">
            <button type="button" id="sncAboutCheckUpdate">检查更新</button>
            <button type="button" id="sncAboutOpenLogs">打开日志文件夹</button>
            <button type="button" id="sncAboutTailLogs">查看最近日志</button>
          </div>
          <pre class="snc-about-out" id="sncAboutOut" hidden></pre>
          <!-- /V26-ABOUT -->
          ` + aboutAnchor);
console.log("insert: about tools");

// 启动画面状态
const splashAnchor = '<span class="snc-splash-bar" aria-hidden="true"><i></i></span>';
if (h.indexOf(splashAnchor) < 0) throw new Error("splash anchor missing");
h = h.replace(splashAnchor, splashAnchor + `
      <!-- V26-SPLASH -->
      <div class="snc-splash-status" id="sncSplashStatus">正在启动本地服务…</div>
      <!-- /V26-SPLASH -->`);
console.log("insert: splash status");

// 主 DOM：工作台 / 小地图 / 图层
const domAnchor = "<!-- 最终用户许可协议（EULA） -->";
const di = h.indexOf(domAnchor);
if (di < 0) throw new Error("dom anchor missing");
h = h.slice(0, di) + html + "\n\n  " + h.slice(di);
console.log("insert: main DOM");

// 主逻辑 JS：boot() 之前
const jsAnchor = "  boot();";
const ji = h.indexOf(jsAnchor);
if (ji < 0) throw new Error("boot anchor missing");
h = h.slice(0, ji) + js + "\n\n" + h.slice(ji);
console.log("insert: main JS");

fs.writeFileSync(file, h, "utf8");
console.log("bytes:", h.length);
