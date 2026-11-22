# 接上真实的 SenseNova

画布本身跑在离线 iframe 里（无 fetch、无外链），所以它不能直接调 `token.sensenova.cn`，
更不能持有 key。真实调用走一个本机小服务做中转。

## 三步

打包版：双击 `无限画布.exe` → 齿轮 → 粘贴 key → 保存。
面板会用 `GET /v1/models` 做一次真实鉴权（不消耗出图积分），成功后徽章变为「**SenseNova · 已连接**」。

密钥落盘为 `SENSENOVA_API_KEY_ENC=`（机器码加密）：机器码 = MachineGuid + 计算机名 + 用户名 +
CPU 标识，经 PBKDF2-HMAC-SHA256（20 万轮）派生 32 字节密钥，再以 HMAC 计数器流加密，
密文带 salt / nonce / tag，篡改即解密失败。换一台机器无法解密，需重填 key；本机迁移目录不受影响。
旧明文 `SENSENOVA_API_KEY=` 仍可读，保存时自动迁移为加密项。

源码运行：

```bash
cd sensenova-canvas/proto
pip install requests
python server.py --window native    # 内嵌窗口；--window app / browser 可换
```

窗口没起来时按 native → 无边框 Edge → 浏览器 的顺序退让，日志在
`%LOCALAPPDATA%\SenseNovaCanvas\app.log`。

## 它是怎么工作的

```
内嵌窗口 (canvas.html)
   │  POST /api/generate   {prompt, ratio, res, model, images}
   ▼
server.py (127.0.0.1:8000)      ← key 只在这里，来自 .env（机器码加密）
   │  Authorization: Bearer ***
   ▼
token.sensenova.cn/v1/images/generations | /images/edits
```

页面**永远拿不到 key**。它只做四件事：

- `GET /api/health` → 拿 key 状态、图片模型、文本模型、能力清单（含 edits 上限 5 张、无 mask、`size` 可 auto）
- `GET /api/models?refresh=1` → 账号可用模型，按"能出图 / 只能文本"分列（缓存 5 分钟）
- `POST /api/verify` → 用 `/v1/models` 校验 key，不消耗出图额度
- `POST /api/generate` → 拿回 base64 + 真实像素尺寸，直接渲染
- `POST /api/polish` → 文本模型润色提示词（`/v1/chat/completions`），不消耗出图额度

有参考图时走 `/images/edits`（最多 5 张，第一张为主编辑图）；
没有参考图时走 `/images/generations`。

### 模型清单：9 个模型，只有 2 个能出图

这个 key 的 `GET /v1/models` 返回 8 个 id，加上没列出来但确实能出图的 `u1.5-fast`，一共 9 个。
**逐个打 `/images/generations` 验证过**，能出图的只有两个：

| model | 图片接口 |
|---|---|
| `sensenova-u1.5-fast` | 200 |
| `sensenova-u1.5-lite` | 200 |
| `sensenova-6.8-flash` / `-lite` / `deepseek-*` / `glm-*` / `kimi-*` | 404 model is not found |

所以界面上分两栏展示：出图下拉框只列 U1.5，设置面板列出全部 9 个并标注「图片 / 文本」，
文本模型进「AI 润色提示词」的下拉框——它们确实被用上了，只是不该出现在图片模型里。

请求体里 `images` 必须是**对象数组**：`"images": [{"image_url": "data:image/png;base64,..."}]`。
v1.3 之前这里发的是字符串数组，带参考图的请求一次都没成功过，v1.4 已修正并有真实回包验证。

### 关于 mask（局部重绘）

`/v1/images/edits` 的官方参数只有
`model / images / prompt / n / size / watermark / prompt_extend / response_format`，**没有 `mask`**。
所以"只改框选区域"不是靠蒙版，而是客户端做：裁出选区（含上下文）→ 重绘 → 只取选区内的像素羽化回贴。
上游对输入图的硬约束：单边 **256–4096**（上下限都要看）、比例 ≤3:1、PNG/JPEG/WebP、
单张 ≤10MB —— 裁剪框会被自动补成合规矩形；多张合计还要留请求体余量（本地按 20MB 兜底）。

### 参考图的硬约束（v2.1 修的真实故障）

`/images/edits` 的 `images[0].image_url` 同样受上面那组约束。上游违反时只回一句通用的 400：

```
invalid images[0].image_url: image should be PNG, JPEG, or WebP, no larger than 10MB,
width and height in [256,4096] px, and aspect ratio should be within 3:1
```

**踩过的坑**：4K / 8K 放大派生出来的卡是 4096+ 的 PNG（十几 MB），拿它当主编辑图必被 400 拒绝。
页面表现为「编辑 / 技能提交后没从原图派生，得到一张毫不相干的图」——其实 edits 根本没成功，
用户只能退回底部输入框做纯文生图。日志里会是 `generate(edit) failed: 400` 紧跟 `generate(gen) ok`。

**修法**：前端在 `runRealJob` 发请求前调 `normalizeRefURLs()`，逐张把参考图规范化——
等比缩到 ≤4096、**短边 <256 时等比放大到 256**（不拉伸、不变形）、比例 >3:1 时补边（不裁内容）、
大 PNG 转 JPEG 并按质量逐级降体积；合规小图原样发。局部重绘的 `crop` / `full` 两张走同一条规范化。
**判断阈值按 data URL 字符串长度算**（base64 比原图大 1/3，按解码字节算会漏掉
「原图 8MB、传输 10.6MB」这种擦边超限）。

v2.2 又补了两处：多张时按张数分摊体积预算（合计 ≤16MB 字符），避免 5 张各 8MB 把请求体撑到 40MB；
服务端 `_handle_generate` 增加 `validate_ref_images()` 本地预校验（格式 / 单张字节 / 合计 20MB /
宽高 256–4096 / 比例 ≤3:1），不合规直接回一句可读的中文错误，不再浪费一次上游 400。

## 关键参数处理

| 参数 | 处理方式 | 原因 |
|---|---|---|
| `model` | 只有 `sensenova-u1.5-fast`（快）和 `sensenova-u1.5-lite`（稳）两个白名单 | 用真实 key 逐个打过端点验证。`sensenova-6.8-flash` 是语言模型，图片接口回 404 model is not found —— v1.4 的第三档"6.8 Flash"一次都没成功过，v1.5 已删掉 |
| `ratio` + `res` | 换算成合法 `WxH`，snap 到 32 的倍数，限制 512–4096、比例 ≤3:1；长边严格等于 res | 接口会直接拒绝不合规尺寸。竖图以前写的是 `long_side*2`，选 2K 会悄悄出 4K，白烧积分 |
| `size`（参考图编辑） | 传 `"auto"`，交给上游按输入图比例自己定 | 官方 edits 的默认值就是 auto。以前强制按页面比例算，4:3 的原图会被改成 16:9，构图就丢了 |
| `output_format` | 主图 `png`，局部重绘的中间产物 `jpeg` | 同样 2.5K 级别，PNG 6.3MB、JPEG 2.2MB；中间图只用来贴回原图，没必要存无损 |
| `prompt_extend` | 文生图 / 参考图编辑 `true`；局部重绘 `false` | 局部指令要照字面执行，扩写会把用户的指定改掉 |
| `response_format` | 固定 `b64_json` | 返回的 url 只有 24 小时有效期，落库即失效 |
| `watermark` | 固定 `false` | 默认是 `true`，不显式传会带官方 Logo |
| `n` | 固定 `1` | 文档写明只支持 1，多张靠多次调用（前端队列并发 2） |
| 尺寸回显 | 从返回的 base64 头部解 PNG/JPEG/WebP 宽高 | 上游 `data[0]` 只有 `b64_json`，没有 `size` 字段；以前拿请求参数冒充结果尺寸，编辑类请求标出来的数字是错的 |

## 已验证 / 未验证

**已验证**（用无效 key 打真实端点）：

- `/api/health` 正确报告 key 是否存在
- 401 被识别成「key 无效或已注销，请在控制台重新签发后更新 .env」
- 该错误**准确落到卡片上**，带重试按钮
- 尺寸换算四组全部合法：`1:1→2048x2048`、`16:9→2048x1152`、`9:16→2304x4096`、`4:3→1024x768`

**v1.1 已验证**（有效 key，打包版与源码版各一遍）：

- 保存 key → `/api/config` 200 → `/api/verify` 200（8 个模型）→ 徽章切换到「已连接」
- 生成 → `/api/generate` 200 → 出图 `2048x1152`，耗时 `10.1s`
- 打包版 `--self-test`：WebView2 初始化成功，页面 `/canvas.html` 200 并回报 health

**v1.5 已验证**（有效 key，端点逐个实测）：

- 模型白名单：`u1.5-fast` → 200、`u1.5-lite` → 200、`sensenova-6.8-flash` → 404、编造的名字 → 404（现在页面会先拦下来，报"模型不可用"）
- `size` 传 `"auto"`：输入 900x600 → 输出 2528x1696（比例 1.4906，按 32 对齐后与原图一致）
- `output_format`：同一次请求 png 6.3MB / jpeg 2.27MB
- 文生图 16:9 2K → 实收 2048x1152（从像素解出来的，不是回显请求参数）
- 参考图编辑（`编辑` 按钮）→ `mode=edit`，2496x1696，13.5s
- 局部重绘 → `mode=edit` + `format=jpeg`，2976x1440，7.7s，只回贴选区
- `prompt_extend=false` 被接受，局部指令按字面执行
- 界面回归 22/23（唯一未过是测试自己把"首次出图=v1"当成 v2 断言），含 1440/1024/900 三档窗口铺满、新建/删除/切换画布、导出菜单四项、无 JS 报错

**v1.6 已验证**：

- `GET /api/models`：返回 `image=2 / text=7`，`total=8`；`sensenova-u1.5-fast` 虽未出现在上游列表里，仍保留在图片模型（实测可出图）
- `POST /api/polish`：`sensenova-6.8-flash` 5.3s 返回完整提示词；`kimi-k3` 的 `temperature` 400 会自动重试；思考型模型 content 为空时自动加预算重试，**不会把 CoT 当答案返回**
- 真实编辑（界面点击 → `/api/generate`）：`mode=edit`，`size=auto`，新卡 2816×1536 / 13.8s，**原图位图字节数不变**，新卡与原图之间有连线
- 界面回归 30/30（存根替换 `/api/generate`）：拖入导入、Ctrl+V 导入、编辑派生新卡、原图不变、面板下方不遮挡 + 可拖动 + 可关闭、AI 润色与还原、底部参数（1:1 / 4K / lite）真实进入请求、900×640 与 1024×680 布局、全程无 JS 报错
- 打包版 `--self-test` 退出码 0，日志可见 `/canvas.html 200` → `/api/models 200` → `/api/health 200`

**v1.8 已验证**（有效 key，逐个端点实测）：

- `GET /v1/models` 原始字段：8 个模型里只有 `sensenova-u1.5-lite` 的
  `output_modalities` 含 `image`（`u1.5-fast` 未列出但实测能出图）；`sensenova-6.8-flash(-lite)`
  是 `input:[text,image] / output:[text]` —— **能读图、不能出图**
- `sensenova-6.8-flash-lite` 读图：实拍照片走 `chat/completions` 的 `image_url` data URL，
  4.0s 返回准确描述；`sensenova-6.8-flash` 同期把 token 全烧在 reasoning 上、`content` 为空
- 扩图端点：`/v1/images/outpaint`、`/expand`、`/variations`、`/upscale` 全部 `404 page not found`
- 用 `size` 指定更宽画幅（2048×864）能出"全景"，但内容会重排（椅子被复制），不是像素级外扩
- 内置技能「夜景转换」原样提示词 + 实拍图 → 200 / 13.5s / 3.1MB jpeg / HD，机位与构图保留
- 8K 链路：`res=4096` 请求 → 本地 2× 重采样（`drawImage` + `imageSmoothingQuality:high`，jpeg 0.94）
- 界面回归 57/57（存根）+ 32/32（v16 无退化）

**v2.1 已验证**（存根回归 + 打包版抽查）：

- 密钥加密：往返一致、密文不含明文 key、篡改后解密返回 `None`、真实机器码环境往返一致
- 前端混淆：`canvas.src.html` → `canvas.html` 由 terser 生成，混淆版跑 v20 回归 43/43 无退化
- 打包版：exe `--self-test` 退出码 0；起服务后重跑 v20 回归 43/43（EULA 首次弹窗 / 技能子选项 /
  方案三 logo / v2.1 版本号全部命中）
- 回归矩阵：v20 43/43、v19 34/34、v17 58/58、v16 32/32 全绿

**参考图规范化已验证**（`tests/test_v21_refs.py`，35/35）：

| 原图 | 提交给 /api/generate 的参考图 |
|---|---|
| 4200×2400 纯色 PNG | 4096×2341 JPEG（等比缩到 ≤4096） |
| 5000×1000（5:1） | 4096×1366（2.999:1，补边不裁内容） |
| 1600×900 噪声 PNG（5.76MB） | 1600×900 JPEG（1.59MB） |
| 160×100 过小图 | 410×256 JPEG（v2.2 等比放大到短边 256） |
| 800×600 合规小图 | 原样 PNG（不误伤） |

五种情况都仍带 1 张参考图 + `sizeMode=auto`，即确认走 `/images/edits` 而非文生图。

**v2.2 已验证**（存根回归 + 打包版抽查）：

- `test_v22_ui.py` 25/25：三段式顺序、参数在底部同一行不换行、一次选 3 张 → 4 张参考图进 edits、
  亮色主题浅底深字（`rgb(255,255,255)` / `rgb(34,36,42)`）
- 服务端 `validate_ref_images()` 8 个构造用例全部按预期拦截（超边 / 过小 / 比例 / 格式 /
  单张 10MB / 合计 20MB / 合规 / 无图）
- 回归矩阵：v22_ui 25/25、v21_refs 35/35、v20 43/43、v19 34/34、v17 58/58、
  v16 32/32、v15 23/23、stub 10/10

**v2.3 已验证**（纯前端功能，不涉及上游接口；存根回归 + 打包版抽查）：

- `test_v23_viewer.py` 34/34：双击打开预览、预览读原图（1600×1000 PNG）而画布显示
  1280 JPEG 缩略图、滚轮缩放 / 拖动平移 / 1:1 / 适应窗口、← → 翻图、
  Esc / × / 点空白三种关闭、点图片本身不误关、双击空白仍能新建笔记、
  亮色主题下看图底对比度足够、无 JS 报错
- 回归矩阵合计 **294 项全绿**：v23 34、v22_ui 25、v21_refs 35、v20 43、v19 34、
  v17 58、v16 32、v15 23、stub 10
- 打包版抽查：v23 34/34、v22_ui 25/25、v21_refs 35/35、v20 43/43

## 这个接口**没有**的能力（别照着做需求）

| 想要 | 现实 | 本项目的处理 |
|---|---|---|
| `mask` 蒙版重绘 | 官方 params 里没有 mask | 裁切重绘 + 只回贴选区（已实现） |
| `n>1` 一次出多张 | 只支持 1 | 前端队列并发 2，连发多次 |
| 超分 | 没有独立端点 | 「放大」用 edits + 4096 尺寸重绘；8K 再本地 2× 插值 |
| 扩图（outpaint） | `/images/outpaint`、`/expand`、`/upscale` 全 404 | 不提供假按钮；只能改 `size` 重排画幅，会重排内容 |
| 用 6.8 Flash 生图 | `output_modalities` 只有 text | 只把它当"读图 + 写提示词"的文本模型 |
| 消除 / 换背景 | 没有独立端点 | 走「框选修改」的局部重绘 |
| seed 复现 | 无 seed 参数 | 用「参考图角色 + 提示词模板」稳定调性 |

## 常见错误

| 提示 | 原因 | 处理 |
|---|---|---|
| `key 无效或已注销` | key 错/过期/被撤销 | 控制台重签，在设置面板「清除密钥」后重填 |
| `该模型未对当前账号开通` | 403 | 控制台开通对应模型 |
| `积分窗口已满或并发超限` | 429 | 等滚动窗口恢复；本版已把并发压到 2 |
| `尺寸不合法` | 比例/分辨率组合超出约束 | 换 `1:1` 或 `16:9` 试 |
| `参考图不合规` | 单边超出 256–4096、比例 >3:1、格式或体积不合规 | 换 PNG/JPEG/WebP；局部重绘的裁剪框会自动补合规 |
| `参考图不可用` | 超过 5 张 | 减少参考图 |
| 徽章一直是「未连接」 | 桥接没起 / 没有 key | 点徽章打开设置，面板会写明当前状态 |

## 出图后发生什么

真实返回的 base64 会替换卡片内容，并记录：

- `realSize`：接口回报的实际尺寸
- `modelUsed`：实际调用的 model_id
- `usage`：token 消耗（含 `input_tokens_details.image_tokens`）
- `latencyMs`：服务端往返耗时

这些都能在右侧详情面板看到——**这正是 P0 要测的延迟与积分数据，现在是真数了**。
