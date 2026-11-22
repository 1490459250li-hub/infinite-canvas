#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""无限画布 · 本地桥接服务（多供应商）。

为什么要这个进程
----------------
canvas.html 是纯静态页面，不能直接调 token.sensenova.cn，也不该持有 key。
本进程做两件事：

  1. 用 http://127.0.0.1:<port> 提供页面（canvas.html）
  2. 暴露 /api/* ，把生成请求转发给 SenseNova，把 base64 结果回抛给页面

key 只存在于本机 .env 与服务内存中：不进页面、不进 URL、不写日志。

用法
----
    python server.py                     # 8000 端口 + 内嵌窗口
    python server.py --port 8080 --open  # 换端口，用默认浏览器
    python server.py --window app        # 无边框 Edge 窗口
    python server.py --self-test         # 起窗即关，验证链路

接口
----
    GET  /api/health     -> {"ok":true,"keyPresent":bool,"key":"sk-xxx...abcd", models:...}
    GET  /api/models     -> 账号可用模型（图片 / 文本分列）
    POST /api/config     -> 写入 .env          {"apiKey","model"}
    POST /api/config/clear
    POST /api/verify     -> 用 /v1/models 鉴权，不消耗出图额度
    POST /api/polish     -> 文本模型润色提示词，不消耗出图额度
    POST /api/generate   -> {"ok":true,"b64":...,"size":...,"latencyMs":...}
    GET  /api/update/check -> 读 exe 同目录 update.json 版本清单
    GET  /api/logs/open   -> 打开日志文件夹（排障入口）
    GET  /api/logs/tail   -> 最近 180 行日志
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import io
import json
import math
import mimetypes
import os
import secrets
import shutil
import socket
import stat
import struct
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# v3.7.4：requests 是启动链上最重的一块（本机实测 import 一次 612 ms，
# 占 Python 侧启动时间的四分之一），而它只在真要发 HTTP 时才用得上。
# 做法是放一个惰性代理在模块全局名上：第一次 `requests.xxx` 才真的 import，
# 并把真模块写回全局名，之后所有调用点零开销 —— 下面 36 处一行都不用改。
#
# 别用模块级 __getattr__（PEP 562）：它只接 `server.requests` 这种属性访问，
# 函数体里的裸名 `requests` 走的是 LOAD_GLOBAL，根本不会触发它。
import importlib

_REQ = {"mod": None}


def ensure_requests():
    """按需导入 requests；成功后把真模块顶替掉代理，后续找名字就是直接命中。"""
    if _REQ["mod"] is not None:
        return _REQ["mod"]
    try:
        mod = importlib.import_module("requests")
    except ImportError:
        sys.stderr.write("missing dependency: pip install requests\n")
        raise SystemExit(1)
    _REQ["mod"] = mod
    globals()["requests"] = mod
    return mod


class _LazyRequests(object):
    """requests 的占位代理：任何读写都先确保模块已加载，再转发过去。

    读要转发（`requests.post(...)`），写也要转发 —— 测试常靠
    `server.requests.post = fake` 打桩，代理要跟真模块一样能被改。
    """

    __slots__ = ()

    def __getattr__(self, name):
        return getattr(ensure_requests(), name)

    def __setattr__(self, name, value):
        setattr(ensure_requests(), name, value)

    def __repr__(self):
        return "<requests 未加载>" if _REQ["mod"] is None else "<requests>"


requests = _LazyRequests()


APP_NAME = "无限画布"
BASE = "https://token.sensenova.cn/v1"

# 图片模型：用真实 key 逐个打过 /images/generations 验证过的一共只有这两个
#   sensenova-u1.5-fast -> 200
#   sensenova-u1.5-lite -> 200
# 其余 6 个（deepseek / glm / kimi / sensenova-6.8）是文本模型，图片接口一律
# 404 model is not found。它们不是没用：提示词润色走的就是它们的
# /v1/chat/completions，所以界面上必须把它们列出来，但要标清能力。
IMAGE_MODELS = {
    "fast": {
        "id": "sensenova-u1.5-fast",
        "label": "U1.5 Fast",
        "note": "速度优先，适合快速迭代",
        "badge": "快",
    },
    "lite": {
        "id": "sensenova-u1.5-lite",
        "label": "U1.5 Lite",
        "note": "质量优先，复杂指令与参考图编辑更稳",
        "badge": "稳",
    },
}
MODELS = {k: v["id"] for k, v in IMAGE_MODELS.items()}
MODEL_NOTE = {k: v["note"] for k, v in IMAGE_MODELS.items()}

# /v1/models 在极少数情况下会超时或 401；兜底清单来自本机真实探测结果，
# 保证界面不会因为一次网络抖动就变成空列表。
FALLBACK_TEXT_MODELS = [
    "sensenova-6.8-flash",
    "sensenova-6.8-flash-lite",
    "deepseek-v4-flash",
    "deepseek-flash",
    "glm-5.3",
    "glm-5.2",
    "kimi-k3",
]

# 文本模型排序：先小快模型，润色提示词不需要最强推理
TEXT_ORDER = [
    "sensenova-6.8-flash",
    "sensenova-6.8-flash-lite",
    "deepseek-v4-flash",
    "deepseek-flash",
    "glm-5.3",
    "glm-5.2",
    "kimi-k3",
]

VENDOR = (
    ("sensenova", "SenseNova"),
    ("deepseek", "DeepSeek"),
    ("glm", "智谱 GLM"),
    ("kimi", "Kimi"),
)
# v3.7.8：补 1536（Seedream 5.0 官方 1.5K 档）。不在白名单里的 res 会被
# pixel_size() 静默改成 2048，前端即使加了 1.5K 选项也只会拿到 2K 图。
LONG_SIDES = (1024, 1536, 2048, 4096)
OUTPUT_FORMATS = ("png", "jpeg", "webp")

# --------------------------------------------------------------------------
# v3.7.5 · 火山方舟 Agent Plan（套餐）语言模型
# --------------------------------------------------------------------------
# 套餐 Key 与方舟按量 Key 不是同一把，端点也不同：
#   OpenAI 兼容   https://ark.cn-beijing.volces.com/api/plan/v3
#   Anthropic 兼容 https://ark.cn-beijing.volces.com/api/plan
# 这里走 OpenAI 兼容的 /chat/completions，Model Name 用官方给的全小写短名。
# vision 一列来自官方 OpenClaw 配置示例里的 input 能力（text / image）；
# 标 False 的几家（glm-5.3、deepseek-v4-flash / pro）只收文字，润色时会自动
# 去掉图片改走纯文本，不会因为多塞一张图就 400。
# 官方依据：
#   https://www.volcengine.com/docs/ark/agent-plan-personal-other-tools
#   https://www.volcengine.com/docs/ark/agent-plan-personal-openclaw
ARK_PLAN_BASE = "https://ark.cn-beijing.volces.com/api/plan/v3"
ARK_PLAN_TEXT = [
    {"id": "ark-code-latest", "label": "AP · Auto（控制台选模型）", "vision": True,
     "plan": True, "note": "控制台切换目标模型，支持 Auto"},
    {"id": "doubao-seed-evolving", "label": "AP · Doubao Seed Evolving", "vision": True,
     "plan": True, "note": "快速迭代 · 深度思考"},
    {"id": "doubao-seed-2.1-pro", "label": "AP · Doubao Seed 2.1 Pro", "vision": True,
     "plan": True, "note": "进阶 · 1024K 上下文"},
    {"id": "doubao-seed-2.1-lite", "label": "AP · Doubao Seed 2.1 Lite", "vision": True,
     "plan": True, "note": "标准 · 高并发"},
    {"id": "doubao-seed-2.0-mini", "label": "AP · Doubao Seed 2.0 Mini", "vision": True,
     "plan": True, "note": "极速 · 256K 上下文"},
    {"id": "glm-5.3-flash", "label": "AP · GLM-5.3 Flash", "vision": True,
     "plan": True, "note": "原生多模态，支持图片输入"},
    {"id": "glm-5.3", "label": "AP · GLM-5.3", "vision": False,
     "plan": True, "note": "默认开启思考 · 仅文字"},
    {"id": "glm-latest", "label": "AP · GLM Latest", "vision": False,
     "plan": True, "note": "GLM-5.3 别名 · 仅文字"},
    {"id": "deepseek-v4.1-flash", "label": "AP · DeepSeek V4.1 Flash", "vision": True,
     "plan": True, "note": "支持图片输入"},
    {"id": "deepseek-v4.1-flash-economy", "label": "AP · DeepSeek V4.1 Flash Economy",
     "vision": True, "plan": True, "note": "经济档 · 支持图片输入"},
    {"id": "deepseek-v4-flash", "label": "AP · DeepSeek V4 Flash", "vision": False,
     "plan": True, "note": "仅文字"},
    {"id": "deepseek-v4-pro", "label": "AP · DeepSeek V4 Pro", "vision": False,
     "plan": True, "note": "仅文字 · Agent 能力强"},
    {"id": "kimi-k3", "label": "AP · Kimi K3", "vision": True,
     "plan": True, "note": "支持图片输入"},
    {"id": "kimi-k3.1-pro", "label": "AP · Kimi K3.1 Pro", "vision": True,
     "plan": True, "note": "进阶 · 支持图片输入"},
    {"id": "kimi-k2.8-preview", "label": "AP · Kimi K2.8 Preview", "vision": True,
     "plan": True, "note": "预览版 · 支持图片输入"},
]

# --------------------------------------------------------------------------
# v3.0 · 多供应商注册表
# --------------------------------------------------------------------------
# 「谁能出图」不再写死在 /api/generate 里：每家一条记录，包含地址、模型、
# 能力与上限。以后加一家只要往这张表里塞一条 + 写一个 render 函数，
# 前端设置页会自动多出一张卡片（卡片是按这张表渲染的）。
#
# max_side 决定前端分辨率档位：4096 → 原图 / 2K / 4K；1536 → 原图 / 1K / 1.5K。
# mask=True 的供应商走「整图 + 蒙版」真重绘，False 的沿用裁剪回贴。
PROVIDER_ORDER = ("sensenova", "openai", "google", "seedream", "qwen", "minimax")

PROVIDER_SPECS = {
    "sensenova": {
        "label": "SenseNova",
        "tag": "U1.5",
        "hint": "商汤日日新 · 国内直连，无需代理",
        "base": "https://token.sensenova.cn/v1",
        "key_prefix": "sk-",
        "image": [
            {"key": "fast", "id": "sensenova-u1.5-fast", "label": "U1.5 Fast", "badge": "快",
             "note": "速度优先，适合快速迭代", "max_side": 4096, "mask": False, "max_refs": 5,
             "ratios": ["auto", "1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "21:9"]},
            {"key": "lite", "id": "sensenova-u1.5-lite", "label": "U1.5 Lite", "badge": "稳",
             "note": "质量优先，复杂指令与参考图编辑更稳", "max_side": 4096, "mask": False,
             "max_refs": 5,
             "ratios": ["auto", "1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "21:9"]},
        ],
        "text": [{"id": m, "label": m} for m in FALLBACK_TEXT_MODELS],
        "text_dynamic": True,
        "caps": {"sizeAuto": True, "promptExtend": True},
    },
    "openai": {
        "label": "OpenAI",
        "tag": "GPT Image 2.6",
        "hint": "ChatGPT 生图 · GPT Image 2.6（2026-11 GA），支持真蒙版重绘",
        "base": "https://api.openai.com/v1",
        "key_prefix": "sk-",
        "image": [
            # 2026-11-04 GA 的 2.6 双档（Sunburst / Flare），编辑保真比 1 代强很多；
            # 尺寸仍按 Image API 的老三档走（1024/1536），别写 2048 —— 会 400。
            {"key": "gpt-image-2.6-sunburst", "id": "gpt-image-2.6-sunburst",
             "label": "GPT Image 2.6 Sunburst", "badge": "新",
             "note": "2026-11 最新 · 跨次编辑保真最好（换背景不掉衣服细节）· 原生支持 mask",
             "max_side": 1536, "mask": True, "max_refs": 5,
             "ratios": ["auto", "1:1", "3:2", "2:3", "16:9", "9:16"]},
            {"key": "gpt-image-2.6-flare", "id": "gpt-image-2.6-flare",
             "label": "GPT Image 2.6 Flare", "badge": "快",
             "note": "同代更快一档 · 适合连续试稿 · 原生支持 mask",
             "max_side": 1536, "mask": True, "max_refs": 5,
             "ratios": ["auto", "1:1", "3:2", "2:3", "16:9", "9:16"]},
            {"key": "gpt-image-2", "id": "gpt-image-2", "label": "GPT Image 2", "badge": "稳",
             "note": "4 月那代 SOTA，价格更低 · 原生支持 mask",
             "max_side": 1536, "mask": True, "max_refs": 5,
             "ratios": ["auto", "1:1", "3:2", "2:3", "16:9", "9:16"]},
        ],
        "text": [
            {"id": "gpt-4.1-mini", "label": "GPT-4.1 mini", "vision": True},
            {"id": "gpt-4o-mini", "label": "GPT-4o mini", "vision": True},
        ],
        "text_dynamic": False,
        "caps": {"sizeAuto": True, "promptExtend": False},
    },
    "google": {
        "label": "Google",
        "tag": "Nano Banana",
        "hint": "Nano Banana Pro / 2 / 2 Lite · 最多 14 张参考图，支持到 4K",
        "base": "https://generativelanguage.googleapis.com/v1beta",
        "key_prefix": "",
        "image": [
            # 2026 换代：gemini-2.5-flash-image 已于 2026-10-02 关停（调了必 404），
            # 现在三档都在 3.x 上。max_side 按各自真实能力写，别再一律 1024 ——
            # 3.x 认 imageConfig.imageSize（"1K"/"2K"/"4K"），选大档是真能出大图。
            {"key": "nano-banana-pro", "id": "gemini-3-pro-image", "label": "Nano Banana Pro",
             "badge": "4K", "note": "指令跟随与文字渲染最强 · 支持 1K/2K/4K · 最多 14 张参考图",
             "max_side": 4096, "mask": False, "max_refs": 14,
             "ratios": ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"]},
            {"key": "nano-banana-2", "id": "gemini-3.1-flash-image", "label": "Nano Banana 2",
             "badge": "快", "note": "高并发出图 · 支持 1K/2K/4K · 最多 14 张参考图",
             "max_side": 4096, "mask": False, "max_refs": 14,
             "ratios": ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"]},
            {"key": "nano-banana-2-lite", "id": "gemini-3.1-flash-lite-image",
             "label": "Nano Banana 2 Lite", "badge": "1K",
             "note": "最便宜最快（约 4 秒）· 只出 1K，不支持多参考与多轮编辑",
             "max_side": 1024, "mask": False, "max_refs": 1,
             "ratios": ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"]},
        ],
        "text": [
            {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash", "vision": True},
            {"id": "gemini-2.5-flash-lite", "label": "Gemini 2.5 Flash Lite", "vision": True},
        ],
        "text_dynamic": False,
        "caps": {"sizeAuto": True, "promptExtend": False},
    },
    "seedream": {
        "label": "Seedream",
        "tag": "火山方舟",
        "hint": "字节跳动 Seedream 5.5 / 5.0 / 4.0 · 1K–2K 直出，支持原生 RGBA，Agent Plan 套餐可用",
        "base": "https://ark.cn-beijing.volces.com/api/v3",
        "key_prefix": "",
        "image": [
            # v3.4：对照官方「图片生成 API」逐字段核过一遍，这里记下几个容易踩的点：
            # ① size 限制的是「总像素区间 + 宽高比 [1/16,16]」，不是单边 1024–4096；
            # ② output_format 只有 5.0 系列支持，且默认 jpeg —— 不传就永远是 jpeg；
            # ③ Agent Plan 入口同样接受带日期的 Model ID，所以套餐通道先试官方 ID；
            # ④ 3.0 已于 2026-05-11 下线（调用直接 model not found），已移除；
            # ⑤ 4.0 的 250828 快照 2026-11-24 下线，换成主线快照 20260415。
            # 5.5（2026-10-28 上线）：交互编辑 / 10 张参考图 / 1K-1.5K-2K 与 5.0 一致，
            # 新增原生 RGBA（文生图也支持透明底）、图层拆分 1 底图 + 最多 99 层、
            # 文字图层富文本 OCR；提示词优化只有标准模式（无 fast）。
            # Agent Plan 抵扣：输出 43.3 AFP/张（≤2.61M 像素），输入图 16.6 AFP/张。
            {"key": "seedream-5-5", "id": "doubao-seedream-5-5-261028",
             "label": "Seedream 5.5", "badge": "RGBA · 99 层",
             "note": "最新 · 透明底直出 · 图层拆分最多 99 层 · 文字图层 OCR",
             "max_side": 2048, "mask": False, "max_refs": 10,
             "pixel_min": 921600, "pixel_max": 4624220,
             "size_tiers": ("1K", "1.5K", "2K"), "out_fmt": True,
             "rgba": True, "layers_max": 99, "layer_ocr": True,
             "plan_base": "https://ark.cn-beijing.volces.com/api/plan/v3",
             "plan_id": "doubao-seedream-5.5",
             "ratios": ["auto", "1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "21:9"]},
            {"key": "seedream-5-pro", "id": "doubao-seedream-5-0-pro-260628",
             "label": "Seedream 5.0 Pro", "badge": "交互编辑",
             "note": "画质优先 · 1K/1.5K/2K · Agent Plan 套餐含此模型",
             "max_side": 2048, "mask": False, "max_refs": 10,
             "pixel_min": 921600, "pixel_max": 4624220,
             "size_tiers": ("1K", "1.5K", "2K"), "out_fmt": True,
             "plan_base": "https://ark.cn-beijing.volces.com/api/plan/v3",
             "plan_id": "doubao-seedream-5-0-pro",
             "ratios": ["auto", "1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "21:9"]},
            {"key": "seedream-5-flash", "id": "doubao-seedream-5-0-flash-260915",
             "label": "Seedream 5.0 Flash", "badge": "快",
             "note": "更快更便宜 · 1K/1.5K/2K · Agent Plan 套餐含此模型",
             "max_side": 2048, "mask": False, "max_refs": 10,
             "pixel_min": 921600, "pixel_max": 4624220,
             "size_tiers": ("1K", "1.5K", "2K"), "out_fmt": True,
             "plan_base": "https://ark.cn-beijing.volces.com/api/plan/v3",
             "plan_id": "doubao-seedream-5.0-flash",
             "ratios": ["auto", "1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "21:9"]},
            {"key": "seedream-4", "id": "doubao-seedream-4-0-20260415", "label": "Seedream 4.0",
             "badge": "4K", "note": "文生图 + 多图参考编辑，尺寸可精确到像素，支持 4K",
             "max_side": 4096, "mask": False, "max_refs": 10,
             "pixel_min": 921600, "pixel_max": 16777216,
             "size_tiers": ("1K", "2K", "4K"), "out_fmt": False,
             "ratios": ["auto", "1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "21:9"]},
        ],
        "text": [
            # 原来的 doubao-seed-1-6-250615 已在 2026-09-21 下线，
            # 换成 LTS 版 2.0 Lite（至少一年生命周期，不会几个月就又没了）。
            # 这一条走按量通道 /api/v3；下面整组走 Agent Plan 套餐 /api/plan/v3。
            {"id": "doubao-seed-2-0-lite-260428", "label": "Doubao Seed 2.0 Lite", "vision": True},
        ] + ARK_PLAN_TEXT,
        "plan_base": ARK_PLAN_BASE,
        "text_dynamic": False,
        "caps": {"sizeAuto": True, "promptExtend": False},
    },
    "qwen": {
        "label": "Qwen-Image",
        "tag": "通义千问",
        "hint": "阿里云百炼 · qwen-image 文生图 / qwen-image-edit 指令编辑",
        "base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "base_native": "https://dashscope.aliyuncs.com/api/v1",
        "key_prefix": "sk-",
        "image": [
            {"key": "qwen-image", "id": "qwen-image", "label": "Qwen-Image", "badge": "文生图",
             "note": "通义千问文生图，中文文字渲染最稳", "max_side": 1440, "mask": False,
             "max_refs": 0,
             "ratios": ["auto", "1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3"]},
            {"key": "qwen-image-edit", "id": "qwen-image-edit", "label": "Qwen-Image Edit",
             "badge": "多图", "note": "指令式编辑，支持多张输入图", "max_side": 1440,
             "mask": False, "max_refs": 3,
             "ratios": ["auto", "1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3"]},
        ],
        "text": [
            {"id": "qwen-flash", "label": "Qwen Flash", "vision": True},
            {"id": "qwen-plus", "label": "Qwen Plus", "vision": True},
        ],
        "text_dynamic": False,
        "caps": {"sizeAuto": True, "promptExtend": False},
    },
    # v3.7.2 · MiniMax H3-Image：2026-11-10 才发布的开源图像模型，这里先接上。
    # 和老的 image-01 不是一套接口，别混：
    #   文生图 POST /v1/images/generations，编辑 POST /v1/images/edits（1–16 张参考图）
    #   模型 ID：MiniMax-H3-Image / MiniMax-H3-Image-Highspeed
    #   size 接受 "宽x高"（65.5 万–2000 万像素，宽高比 1:3–3:1）或 auto；
    #   用 auto 时才配 aspect_ratio + area，两种形式混着传会 400。
    #   4K（4096×4096）标准模式约 10 秒，是它最大的卖点。
    "minimax": {
        "label": "MiniMax",
        "tag": "H3",
        "hint": "MiniMax H3-Image · 10 秒出 4K · 单次最多 16 张参考图；国内 api.minimaxi.com，海外 api.minimax.io",
        "base": "https://api.minimaxi.com/v1",
        "key_prefix": "sk-",
        "image": [
            {"key": "h3-image", "id": "MiniMax-H3-Image", "label": "H3-Image", "badge": "4K",
             "note": "文生图 / 多图参考 / 指令编辑 · 4K 约 10 秒 · 不支持蒙版与透明底",
             "max_side": 4096, "mask": False, "max_refs": 16,
             "ratios": ["auto", "1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "21:9"]},
            {"key": "h3-image-fast", "id": "MiniMax-H3-Image-Highspeed",
             "label": "H3-Image Highspeed", "badge": "快",
             "note": "同画质更快，单价更高 · 适合批量迭代",
             "max_side": 4096, "mask": False, "max_refs": 16,
             "ratios": ["auto", "1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "21:9"]},
        ],
        "text": [
            {"id": "MiniMax-M3", "label": "MiniMax-M3", "vision": True},
            {"id": "MiniMax-M3.1-Flash", "label": "MiniMax-M3.1-Flash", "vision": True},
        ],
        "text_dynamic": False,
        "caps": {"sizeAuto": True, "promptExtend": True},
    },
}

# 一把供应商最多挂几把钥匙（密钥列表上限，超出后 UI 不给加）
KEY_SLOTS = 5

DEFAULT_ROUTES = {
    "text2img": "sensenova:fast",
    "inpaint": "sensenova:fast",
    "polish": "sensenova:sensenova-6.8-flash",
}

_STATE_LOCK = threading.RLock()  # v3.8.6：保护多线程共享缓存（_ENV_CACHE/_KEY_RR/_CATALOG/_SEEDREAM_CHANNEL）
_KEY_RR = {}          # provider -> 下一次先用第几把钥匙


def provider_spec(pid: str) -> dict:
    return PROVIDER_SPECS.get((pid or "").strip().lower()) or {}


def model_entry(pid: str, want: str) -> dict:
    """按 key / 完整 id / 别名找一个图片模型条目，找不到返回 {}。"""
    spec = provider_spec(pid)
    name = str(want or "").strip()
    for item in spec.get("image") or []:
        if name and name in (item["key"], item["id"]):
            return item
    if name:
        # 老工程里存的旧名字要能指回新档位，别让升级后「模型不存在」
        alias = {
            "flash": "fast", "sensenova-u1-fast": "fast",
            # 2026-11 OpenAI 换到 2.6：1 代已经不在新账号的可用列表里
            "gpt-image-1": "gpt-image-2.6-sunburst",
            # 2026-10 Gemini 2.5 图像模型关停，指到 3.1 Flash（同为快档）
            "nano-banana": "nano-banana-2",
            "gemini-2.5-flash-image": "nano-banana-2",
        }
        if name in alias:
            for item in spec.get("image") or []:
                if item["key"] == alias[name]:
                    return item
    items = spec.get("image") or []
    return items[0] if items else {}


def text_entry(pid: str, want: str) -> dict:
    spec = provider_spec(pid)
    name = str(want or "").strip()
    for item in spec.get("text") or []:
        if name and name in (item["id"], item.get("label")):
            return item
    items = spec.get("text") or []
    return items[0] if items else {}


# ---- .env 读写（多密钥：SNC_KEY_<PROVIDER>_<n>_ENC / _NAME）----
# 单次请求里 env_map() 会被调用 6 次以上（分流、密钥、模型、标签各读一遍），
# 全都落到磁盘。按 (mtime, size) 缓存，文件一改签名就变，不需要手动失效。
_ENV_CACHE = {"sig": None, "data": {}}


def _env_sig(path: str):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (path, st.st_mtime_ns, st.st_size)


def env_map() -> dict:
    path = env_path()
    sig = _env_sig(path)
    with _STATE_LOCK:
        if sig is not None and _ENV_CACHE["sig"] == sig:
            return dict(_ENV_CACHE["data"])
    data = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8-sig") as fh:
                for line in fh:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or "=" not in stripped:
                        continue
                    name, value = stripped.split("=", 1)
                    data[name.strip()] = value.strip().strip('"').strip("'")
        except OSError as exc:
            log("read .env failed: %s" % exc)
    if sig is not None:
        with _STATE_LOCK:
            _ENV_CACHE["sig"] = sig
            _ENV_CACHE["data"] = data
    return dict(data)


def env_write(data: dict) -> None:
    target = env_path()
    folder = os.path.dirname(target)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join("%s=%s" % (k, v) for k, v in data.items()) + "\n")
    os.replace(tmp, target)
    # 签名可能因同一时间片内的写入而不变，写完全局失效一次更稳
    with _STATE_LOCK:
        _ENV_CACHE["sig"] = None
        _ENV_CACHE["data"] = {}
    try:
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _slot(pid: str, n: int, suffix: str) -> str:
    return "SNC_KEY_%s_%d_%s" % (pid.upper(), n, suffix)


def load_keys(pid: str, env=None) -> list:
    """读出某家配置的所有密钥（明文，仅服务端内存）。"""
    env = env_map() if env is None else env
    keys = []
    for n in range(1, KEY_SLOTS + 1):
        enc = env.get(_slot(pid, n, "ENC"))
        plain = env.get(_slot(pid, n, ""))
        value = ""
        if enc:
            value = _decrypt_secret(enc) or ""
        if not value and plain:
            value = plain
        if not value:
            continue
        keys.append({
            "id": "%s-%d" % (pid, n),
            "slot": n,
            "label": env.get(_slot(pid, n, "NAME")) or ("密钥 %d" % n),
            "key": value,
        })
    if not keys and pid == "sensenova":
        legacy = env.get("SENSENOVA_API_KEY_ENC")
        value = (_decrypt_secret(legacy) or "") if legacy else ""
        if not value:
            value = env.get("SENSENOVA_API_KEY") or ""
        if value:
            keys.append({"id": "sensenova-1", "slot": 1, "label": "主账号", "key": value})
    for item in keys:
        item["mask"] = mask(item["key"])
    return keys


def add_key(pid: str, key: str, label: str = "") -> dict:
    """追加一把钥匙；已在表里（同一把明文）就更新标签。返回 (action, entry)。"""
    env = env_map()
    keys = load_keys(pid, env)
    key = (key or "").strip()
    for item in keys:
        if item["key"] == key:
            env[_slot(pid, item["slot"], "NAME")] = (label or item["label"]).strip()
            env_write(env)
            return "updated", item
    if len(keys) >= KEY_SLOTS:
        return "full", {}
    used = set(item["slot"] for item in keys)
    slot = next((n for n in range(1, KEY_SLOTS + 1) if n not in used), 1)
    env[_slot(pid, slot, "ENC")] = _encrypt_secret(key)
    env[_slot(pid, slot, "NAME")] = (label or ("密钥 %d" % slot)).strip()
    env.pop(_slot(pid, slot, ""), None)
    env_write(env)
    return "added", {"id": "%s-%d" % (pid, slot), "slot": slot,
                     "label": env[_slot(pid, slot, "NAME")], "key": key, "mask": mask(key)}


def drop_key(pid: str, key_id: str = "", slot: int = 0) -> bool:
    env = env_map()
    keys = load_keys(pid, env)
    target = 0
    for item in keys:
        if (key_id and item["id"] == key_id) or (slot and item["slot"] == slot):
            target = item["slot"]
            break
    if not target:
        return False
    for suffix in ("ENC", "NAME", ""):
        env.pop(_slot(pid, target, suffix), None)
    if pid == "sensenova" and not [n for n in range(1, KEY_SLOTS + 1)
                                   if env.get(_slot(pid, n, "ENC"))]:
        env.pop("SENSENOVA_API_KEY_ENC", None)
        env.pop("SENSENOVA_API_KEY", None)
    env_write(env)
    return True


def provider_model(pid: str, env=None) -> str:
    env = env_map() if env is None else env
    name = env.get("SNC_MODEL_%s" % pid.upper()) or ""
    return model_entry(pid, name).get("key", "")


def _route_model(pid: str, name: str, task: str) -> str:
    """分流里的模型名要按任务分别解析：润色指文本模型，出图指图片模型。"""
    entry = text_entry(pid, name) if task == "polish" else model_entry(pid, name)
    return entry.get("id") if task == "polish" else entry.get("key", "")


def load_routes(env=None) -> dict:
    env = env_map() if env is None else env
    raw = env.get("SNC_ROUTE_JSON") or ""
    routes = dict(DEFAULT_ROUTES)
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                for task, target in data.items():
                    if task in routes and isinstance(target, str) and ":" in target:
                        pid, mkey = target.split(":", 1)
                        if provider_spec(pid):
                            got = _route_model(pid, mkey, task)
                            if got:
                                routes[task] = "%s:%s" % (pid, got)
        except ValueError:
            log("SNC_ROUTE_JSON 解析失败，用默认分流")
    return routes


def save_routes(routes: dict) -> dict:
    clean = dict(DEFAULT_ROUTES)
    for task in clean:
        target = str((routes or {}).get(task) or "").strip()
        if ":" not in target:
            continue
        pid, mkey = target.split(":", 1)
        if not provider_spec(pid):
            continue
        got = _route_model(pid, mkey, task)
        if got:
            clean[task] = "%s:%s" % (pid, got)
    env = env_map()
    env["SNC_ROUTE_JSON"] = json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
    env_write(env)
    return clean


def provider_state(pid: str, env=None) -> dict:
    """给前端用的供应商快照：不含明文，只给打码与能力。"""
    spec = provider_spec(pid)
    if not spec:
        return {}
    env = env_map() if env is None else env
    keys = load_keys(pid, env)
    images = []
    for item in spec.get("image") or []:
        row = dict(item)
        row["provider"] = pid
        row["value"] = "%s:%s" % (pid, item["key"])
        row["ready"] = bool(keys)
        images.append(row)
    text = [dict(item, provider=pid, value="%s:%s" % (pid, item["id"]))
            for item in (spec.get("text") or [])]
    return {
        "id": pid,
        "label": spec["label"],
        "tag": spec.get("tag", ""),
        "hint": spec.get("hint", ""),
        "base": spec["base"],
        "keyPrefix": spec.get("key_prefix", ""),
        "configured": bool(keys),
        "keys": [{"id": k["id"], "slot": k["slot"], "label": k["label"], "mask": k["mask"]}
                 for k in keys],
        "image": images,
        "text": text,
        "defaultImage": model_entry(pid, provider_model(pid, env)).get("key", ""),
        "defaultText": (text[0]["value"] if text else ""),
        "caps": dict(spec.get("caps") or {}),
    }


def providers_payload(env=None) -> dict:
    env = env_map() if env is None else env
    return {
        "ok": True,
        "order": list(PROVIDER_ORDER),
        "providers": [provider_state(pid, env) for pid in PROVIDER_ORDER],
        "routes": load_routes(env),
        "anyConfigured": any(load_keys(pid, env) for pid in PROVIDER_ORDER),
    }


def pick_target(body: dict, env=None):
    """决定这次请求打到哪家、用哪个模型。

    优先级：请求里显式带 provider > 任务分流（task=text2img/inpaint）> 默认分流。
    返回 (provider, entry, error)，error 是 (code, message, http_status) 或 None。
    """
    env = env_map() if env is None else env
    routes = load_routes(env)
    task = str(body.get("task") or "").strip().lower()
    if task not in routes:
        task = "text2img"
    want_pid = str(body.get("provider") or "").strip().lower()
    want_model = str(body.get("model") or "").strip()

    target = routes.get(task) or DEFAULT_ROUTES["text2img"]
    t_pid, t_model = (target.split(":", 1) + [""])[:2]

    if want_pid:
        # 显式点名了供应商就必须是它：以前查不到会静默回落到默认分流并真出图，
        # 用户以为在测别家、额度却花在默认那家上。
        if not provider_spec(want_pid):
            return "", {}, ("provider", "未知的供应商：%s；可选：%s"
                            % (want_pid, " / ".join(PROVIDER_ORDER)), 400)
        pid = want_pid
        if not want_model:
            # 没指定模型时用这家自己设置里存的，而不是别家分流里的模型名
            want_model = provider_model(pid, env)
    else:
        pid = t_pid
        if not want_model:
            want_model = t_model

    spec = provider_spec(pid)
    if not spec:
        return "", {}, ("provider", "供应商 %s 不可用" % (pid or "?"), 400)

    items = spec.get("image") or []
    chosen = {}
    for item in items:
        if want_model and want_model in (item["key"], item["id"]):
            chosen = item
            break
    if not chosen and not want_model:
        chosen = items[0] if items else {}
    if not chosen:
        names = " / ".join(i["key"] for i in items)
        return "", {}, ("model", "%s 没有图片模型 %s；可用：%s"
                        % (spec["label"], want_model, names), 200)
    return pid, chosen, None


def primary_key() -> str:
    """老接口（健康检查 / 润色 / 模型清单）用：按 供应商顺序 取第一把钥匙。"""
    env = env_map()
    routes = load_routes(env)
    order = [routes.get("text2img", "").split(":")[0]] + list(PROVIDER_ORDER)
    for pid in order:
        if not provider_spec(pid):
            continue
        keys = load_keys(pid, env)
        if keys:
            return keys[0]["key"]
    return ""


def migrate_legacy_keys() -> None:
    """老版本只有一把 SENSENOVA_API_KEY[_ENC]，首次启动搬到多密钥槽位 1。"""
    env = env_map()
    if env.get(_slot("sensenova", 1, "ENC")) or env.get(_slot("sensenova", 1, "")):
        return
    legacy_enc = env.get("SENSENOVA_API_KEY_ENC")
    legacy_plain = env.get("SENSENOVA_API_KEY")
    if not legacy_enc and not legacy_plain:
        return
    value = (_decrypt_secret(legacy_enc) or "") if legacy_enc else ""
    if not value:
        value = legacy_plain or ""
    if not value:
        return
    env[_slot("sensenova", 1, "ENC")] = _encrypt_secret(value)
    env[_slot("sensenova", 1, "NAME")] = "主账号"
    if env.get("SENSENOVA_MODEL"):
        env.setdefault("SNC_MODEL_SENSENOVA", env["SENSENOVA_MODEL"])
    env.pop("SENSENOVA_API_KEY_ENC", None)
    env.pop("SENSENOVA_API_KEY", None)
    env_write(env)
    log("migrated legacy key to SNC_KEY_SENSENOVA_1_ENC")


LAST_PAGE_PING = 0.0


# --------------------------------------------------------------------------
# 路径与日志
# --------------------------------------------------------------------------
def app_dir() -> str:
    """打包后是 exe 所在目录，否则是源码目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def asset_dir() -> str:
    """canvas.html 的位置：onefile 时在 PyInstaller 的临时解包目录。"""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", app_dir())
    return os.path.dirname(os.path.abspath(__file__))


def data_dir() -> str:
    """per-user 可写目录：日志与 WebView2 profile 都在这里。"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    target = os.path.join(base, "SenseNovaCanvas")
    try:
        os.makedirs(target, exist_ok=True)
    except OSError:
        target = os.path.expanduser("~")
    return target


LOG_PATH = os.path.join(data_dir(), "app.log")

# v2.6 · B2 自动更新通道：版本清单放在 exe 同目录的 update.json，
# 结构 {"latest":"2.6.0","notes":"...","url":"https://..."}。没有清单也不报错，
# 前端「检查更新」会明确提示"未配置版本清单"。
APP_VERSION = "3.8.11"

# 本次进程实际拿到 / 想要的端口。端口是 IndexedDB 的 origin 的一部分，
# 换了端口就等于换了"站点"，旧画布看不到。这两个数字只用于在页面上说清楚。
PORT_INFO = {"want": 0, "got": 0}
UPDATE_MANIFEST = os.path.join(app_dir(), "update.json")


def _ver_key(text) -> tuple:
    """把 "3.5.1" / "v3.6" 这类版本号变成可比较的元组。解析不出来的按 0 算。"""
    out = []
    for piece in str(text or "").strip().lstrip("vV").split("."):
        digits = ""
        for ch in piece:
            if not ch.isdigit():
                break
            digits += ch
        out.append(int(digits) if digits else 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out[:3])


def update_info() -> dict:
    info = {
        "ok": True,
        "current": APP_VERSION,
        "latest": APP_VERSION,
        "hasUpdate": False,
        "notes": "未配置版本清单（把 update.json 放在程序目录即可启用）",
        "url": "",
        "manifest": UPDATE_MANIFEST,
    }
    try:
        with open(UPDATE_MANIFEST, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        latest = str(data.get("latest") or APP_VERSION).strip()
        info["latest"] = latest
        info["notes"] = str(data.get("notes") or "").strip()
        info["url"] = str(data.get("url") or "").strip()
        # v3.8.0：可选校验，填了就必须对得上，防止下到半个包或被人替换
        info["sha256"] = str(data.get("sha256") or "").strip().lower()
        try:
            info["size"] = int(data.get("size") or 0)
        except (TypeError, ValueError):
            info["size"] = 0
        # 只比大小：以前用 != 判断，清单里写个旧版本号（比如回滚到 3.4.9）
        # 也会提示「有新版本」，点进去下的还是老包。
        info["hasUpdate"] = _ver_key(latest) > _ver_key(APP_VERSION)
    except FileNotFoundError:
        pass
    except Exception as exc:  # 清单写坏了也不该让「检查更新」崩
        info["notes"] = "版本清单读取失败：%s" % exc
    return info


def log_tail(limit: int = 180) -> str:
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        return "".join(lines[-limit:])
    except FileNotFoundError:
        return "（尚无日志文件）"
    except OSError as exc:
        return "（日志读取失败：%s）" % exc


def open_logs_dir() -> dict:
    target = data_dir()
    try:
        if sys.platform.startswith("win"):
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
        return {"ok": True, "path": target, "file": LOG_PATH}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "path": target, "file": LOG_PATH}


_STREAMS_REDIRECTED = False


# v2.7 · 导出落盘：点「导出」要弹系统的另存为窗口，让用户自己挑位置，
# 而不是静默丢进浏览器的下载目录（打包版里根本看不到下到哪了）。
# 默认关闭，只有真正起窗的 main() 会把它打开；tests/serve.py 直接挂 Handler，
# 因此测试里不会弹窗，前端会自动回退成浏览器下载。
NATIVE_DIALOG = False
_SAVE_DIALOG_ENV = os.environ.get("SNC_SAVE_DIALOG", "").strip().lower()
if _SAVE_DIALOG_ENV in ("0", "false", "off"):
    _SAVE_DIALOG_DISABLED = True
else:
    _SAVE_DIALOG_DISABLED = False


def _save_dialog(default_name: str, ext: str, label: str = "文件"):
    """弹 Win32 另存为对话框。

    返回：用户选好的完整路径；空串表示用户取消；None 表示当前环境不支持。
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return None

    class OPENFILENAMEW(ctypes.Structure):
        _fields_ = [
            ("lStructSize", wintypes.DWORD),
            ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("lpstrFilter", wintypes.LPCWSTR),
            ("lpstrCustomFilter", wintypes.LPWSTR),
            ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD),
            ("lpstrFile", wintypes.LPWSTR),
            ("nMaxFile", wintypes.DWORD),
            ("lpstrFileTitle", wintypes.LPWSTR),
            ("nMaxFileTitle", wintypes.DWORD),
            ("lpstrInitialDir", wintypes.LPCWSTR),
            ("lpstrTitle", wintypes.LPCWSTR),
            ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD),
            ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", wintypes.LPCWSTR),
            ("lCustData", wintypes.LPARAM),
            ("lpfnHook", wintypes.LPVOID),
            ("lpTemplateName", wintypes.LPCWSTR),
            ("pvReserved", wintypes.LPVOID),
            ("dwReserved", wintypes.DWORD),
            ("FlagsEx", wintypes.DWORD),
        ]

    OFN_OVERWRITEPROMPT = 0x00000002
    OFN_NOCHANGEDIR = 0x00000008
    OFN_PATHMUSTEXIST = 0x00001000
    OFN_EXPLORER = 0x00080000

    ext = (ext or "png").lstrip(".").lower()
    buf = ctypes.create_unicode_buffer(default_name or ("导出." + ext), 1024)
    # 过滤器必须用 unicode buffer：Python str 里的 \0 会被 ctypes 截断
    flt = ctypes.create_unicode_buffer(
        "%s (*.%s)\0*.%s\0所有文件 (*.*)\0*.*\0" % (label or "文件", ext, ext)
    )
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    try:
        ofn.hwndOwner = ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        ofn.hwndOwner = None
    ofn.lpstrFilter = ctypes.cast(flt, wintypes.LPCWSTR)
    ofn.nFilterIndex = 1
    ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
    ofn.nMaxFile = 1024
    ofn.lpstrDefExt = ext
    ofn.lpstrTitle = "选择保存位置"
    ofn.Flags = OFN_OVERWRITEPROMPT | OFN_NOCHANGEDIR | OFN_PATHMUSTEXIST | OFN_EXPLORER
    try:
        ok = ctypes.windll.comdlg32.GetSaveFileNameW(ctypes.byref(ofn))
    except Exception:
        return None
    return buf.value if ok else ""


def save_export(payload: dict) -> dict:
    """把前端送来的 base64 存到用户选的位置。"""
    name = str(payload.get("name") or "导出").strip()
    ext = str(payload.get("ext") or "png").strip().lstrip(".").lower() or "png"
    data = payload.get("b64") or ""
    if not isinstance(data, str) or not data:
        return {"ok": False, "error": "没有收到文件内容"}
    try:
        raw = base64.b64decode(data, validate=False)
    except Exception as exc:
        return {"ok": False, "error": "数据解码失败：%s" % exc}
    if not raw:
        return {"ok": False, "error": "文件内容是空的"}
    if not NATIVE_DIALOG:
        return {"ok": False, "error": "当前运行方式不支持系统另存为窗口"}
    target = _save_dialog(name, ext, payload.get("label") or "文件")
    if target is None:
        return {"ok": False, "error": "系统对话框不可用"}
    if target == "":
        return {"ok": True, "canceled": True}
    try:
        parent = os.path.dirname(target)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        with open(target, "wb") as fh:
            fh.write(raw)
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    log("导出 %s (%d bytes)" % (target, len(raw)))
    return {"ok": True, "path": target, "bytes": len(raw)}


def save_zip(payload: dict) -> dict:
    """v3.7.7：分层素材包。把多个 base64 文件打成一个 ZIP，只弹一次「另存为」。"""
    name = str(payload.get("name") or "图层拆分.zip").strip()
    if not name.lower().endswith(".zip"):
        name += ".zip"
    files = payload.get("files") or []
    if not isinstance(files, list) or not files:
        return {"ok": False, "error": "没有收到文件内容"}
    buf = io.BytesIO()
    try:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            seen = set()
            for f in files:
                if not isinstance(f, dict):
                    continue
                fn = str(f.get("name") or "").strip().replace("\\", "/").lstrip("/")
                if not fn or fn in seen:
                    continue
                seen.add(fn)
                zf.writestr(fn, base64.b64decode(str(f.get("b64") or ""), validate=False))
        raw = buf.getvalue()
    except Exception as exc:
        return {"ok": False, "error": "打包失败：%s" % exc}
    if not raw:
        return {"ok": False, "error": "文件内容是空的"}
    if not NATIVE_DIALOG:
        return {"ok": False, "error": "当前运行方式不支持系统另存为窗口"}
    target = _save_dialog(name, "zip", "分层素材包")
    if target is None:
        return {"ok": False, "error": "系统对话框不可用"}
    if target == "":
        return {"ok": True, "canceled": True}
    try:
        parent = os.path.dirname(target)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        with open(target, "wb") as fh:
            fh.write(raw)
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    log("导出 ZIP %s (%d bytes)" % (target, len(raw)))
    return {"ok": True, "path": target, "bytes": len(raw)}


# ---------------- v3.8.0 · 存档备份 / 恢复（换电脑继承记录） ----------------
# 画布 / 技能 / MCP 连接全在 IndexedDB 里，跟着 WebView2 profile 走。
# 换一台电脑只装新包是拿不到旧记录的，所以这里让前端把整个库导成一个
# `.sncbak`（gzip 过的 JSON，图片按 data URL 内联）流式落盘。
# 恢复不需要后端读文件：前端用 <input type=file> 自己读、自己写回 IndexedDB，
# 既省一个「任意路径读取」的口子，也不用新开一个下载接口。
BACKUP_EXT = "sncbak"
BACKUP_LIMIT = 3 * 1024 * 1024 * 1024      # 单个备份上限 3 GB


def backup_dialog(name: str):
    """弹系统「另存为」，返回 (ok, target_or_error)。

    注意先弹窗再收请求体：用户可能要想一会儿，而请求体还在 TCP 缓冲里等着，
    本地回环没有那么点容量焦虑。
    """
    raw = str(name or "").strip() or "无限画布存档"
    if not raw.lower().endswith("." + BACKUP_EXT):
        raw += "." + BACKUP_EXT
    if not NATIVE_DIALOG:
        return False, "当前运行方式不支持系统另存为窗口"
    target = _save_dialog(raw, BACKUP_EXT, "无限画布存档")
    if target is None:
        return False, "系统对话框不可用"
    return True, target


def backup_auto_target() -> str:
    """恢复存档前自动留一份底：%LOCALAPPDATA%\\SenseNovaCanvas\\backups\\auto-<时间>.sncbak。

    不弹窗、不问人，只保留最近 5 份，防止「导错文件把当前画布覆盖掉」这种事故。
    """
    root = os.path.join(data_dir(), "backups")
    try:
        os.makedirs(root, exist_ok=True)
    except OSError:
        return ""
    name = "auto-%s.%s" % (time.strftime("%Y%m%d-%H%M%S"), BACKUP_EXT)
    target = os.path.join(root, name)
    try:
        olds = sorted(
            (os.path.join(root, fn) for fn in os.listdir(root)
             if fn.startswith("auto-") and fn.endswith("." + BACKUP_EXT)),
            key=os.path.getmtime, reverse=True,
        )
        for stale in olds[4:]:
            os.remove(stale)
    except OSError:
        pass
    return target


# ---------------- v3.8.0 · 一键更新 ----------------
UPDATE_DIR = os.path.join(data_dir(), "update")
UPDATE_ZIP_LIMIT = 2 * 1024 * 1024 * 1024   # 升级包上限 2 GB


def _ps_quote(text: str) -> str:
    """PowerShell 单引号字符串：单引号自身写两遍。"""
    return "'" + str(text).replace("'", "''") + "'"


def _update_source(url: str):
    """把清单里的 url 解析成 ('file', path) 或 ('http', url)。

    支持三种写法，方便没有服务器的场景：
      https://…/无限画布-v3.8.0-win64.zip   —— 线上分发
      local:releases/无限画布-v3.8.0.zip     —— exe 同目录下的相对路径（局域网共享盘也行）
      直接写相对路径                         —— 同上，省略 local: 前缀
    """
    u = str(url or "").strip()
    if not u:
        return None, "版本清单里没有填 url（升级包地址）"
    low = u.lower()
    if low.startswith("local:"):
        rel = u.split(":", 1)[1].strip().lstrip("/\\")
        target = os.path.abspath(os.path.join(app_dir(), rel))
        if os.path.isfile(target):
            return ("file", target), ""
        return None, "找不到升级包：%s" % target
    if low.startswith(("http://", "https://")):
        return ("http", u), ""
    target = os.path.abspath(os.path.join(app_dir(), u))
    if os.path.isfile(target):
        return ("file", target), ""
    return None, "不认识的升级包地址：%s" % u


def _find_packaged_exe(root: str):
    """在解压出来的目录里找主程序，返回 exe 的绝对路径（找不到返回 ""）。

    发布包里是 `无限画布-vX.Y.Z-win64/无限画布/无限画布.exe`，但版本号目录名
    会随版本变，所以不写死路径：优先同名 exe，其次任意 *无限画布*.exe。
    """
    want = os.path.basename(sys.executable if getattr(sys, "frozen", False) else "无限画布.exe")
    hits = []
    for base, _dirs, files in os.walk(root):
        for fn in files:
            if fn.lower().endswith(".exe"):
                hits.append(os.path.join(base, fn))
    if not hits:
        return ""
    for path in hits:
        if os.path.basename(path) == want:
            return path
    for path in hits:
        if "无限画布" in os.path.basename(path):
            return path
    return hits[0]


def _clean_update_dir(keep: str) -> None:
    """清掉上一版的升级包（一个十几 MB，攒着没意义）。"""
    try:
        for fn in os.listdir(UPDATE_DIR):
            full = os.path.join(UPDATE_DIR, fn)
            if os.path.abspath(full) == os.path.abspath(keep):
                continue
            if fn.lower().endswith((".zip", ".exe")) and os.path.isfile(full):
                try:
                    os.remove(full)
                except OSError:
                    pass
    except OSError:
        pass


def _fetch_to(src, dest: str) -> tuple:
    """把升级包取到本地，返回 (字节数, 错误)。"""
    try:
        if src[0] == "file":
            shutil.copyfile(src[1], dest)
        else:
            with urllib.request.urlopen(src[1], timeout=30) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                if total > UPDATE_ZIP_LIMIT:
                    return 0, "升级包超过 2 GB，请手动下载"
                got = 0
                with open(dest, "wb") as fh:
                    while True:
                        block = resp.read(1 << 20)
                        if not block:
                            break
                        got += len(block)
                        if got > UPDATE_ZIP_LIMIT:
                            raise OSError("升级包超过 2 GB")
                        fh.write(block)
    except Exception as exc:
        return 0, "下载升级包失败：%s" % exc
    try:
        return os.path.getsize(dest), ""
    except OSError:
        return 0, "升级包没落到盘上"


def _verify_sha(path: str, want: str) -> str:
    """清单里填了 sha256 就必须对上，返回错误文本（空串=通过）。"""
    want = str(want or "").strip().lower()
    if not want:
        return ""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
    except OSError as exc:
        return "校验升级包失败：%s" % exc
    if h.hexdigest() != want:
        try:
            os.remove(path)
        except OSError:
            pass
        return "升级包校验不通过（sha256 不匹配），已删除，请重新下载"
    return ""


def update_download() -> dict:
    """下载升级包。

    两种分发物都认：
      · `*.exe` 安装包（推荐）—— 存下来，apply 阶段用 `/S` 静默跑一遍；
        安装包自己会覆盖程序目录、保留 .env 与 %LOCALAPPDATA% 里的存档。
      · `*.zip` 绿色包 —— 解到 update\\v<版本>，apply 阶段 robocopy 覆盖。
    """
    info = update_info()
    if not info.get("hasUpdate"):
        return {"ok": False, "code": "latest",
                "error": "已是最新版本 %s（清单里的 latest 不大于当前版本）" % APP_VERSION}
    url = str(info.get("url") or "").strip()
    src, err = _update_source(url)
    if not src:
        return {"ok": False, "code": "url", "error": err}
    ver = str(info.get("latest") or "").strip() or "next"
    kind = "setup" if url.lower().split("?")[0].endswith(".exe") else "zip"
    stage = os.path.join(UPDATE_DIR, "v" + ver)
    try:
        os.makedirs(UPDATE_DIR, exist_ok=True)
        if os.path.isdir(stage):
            shutil.rmtree(stage, ignore_errors=True)
        os.makedirs(stage, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "error": "创建升级目录失败：%s" % exc}

    if kind == "setup":
        dest = os.path.join(UPDATE_DIR, "v%s-setup.exe" % ver)
        _clean_update_dir(dest)
        size, err = _fetch_to(src, dest)
        if err:
            return {"ok": False, "error": err}
        bad = _verify_sha(dest, info.get("sha256"))
        if bad:
            return {"ok": False, "code": "sha", "error": bad}
        log("update staged: v%s setup -> %s (%d bytes)" % (ver, dest, size))
        return {"ok": True, "kind": "setup", "version": ver, "dir": dest,
                "bytes": size, "setup": dest}

    zip_path = os.path.join(UPDATE_DIR, "v%s.zip" % ver)
    _clean_update_dir(zip_path)
    size, err = _fetch_to(src, zip_path)
    if err:
        return {"ok": False, "error": err}
    bad = _verify_sha(zip_path, info.get("sha256"))
    if bad:
        return {"ok": False, "code": "sha", "error": bad}
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(stage)
    except Exception as exc:
        return {"ok": False, "error": "解压升级包失败：%s" % exc}
    exe = _find_packaged_exe(stage)
    if not exe:
        return {"ok": False, "error": "升级包里没有找到主程序，可能不是发布包"}
    log("update staged: v%s zip -> %s (%d bytes)" % (ver, stage, size))
    return {"ok": True, "kind": "zip", "version": ver, "dir": stage,
            "exe": exe, "bytes": size}


def _update_script(pid: int, stage: str, src_root: str, dst_root: str, exe_dst: str) -> str:
    """生成替换脚本正文。

    抽成独立函数是为了能单独验证：脚本本身没问题、只是被环境挡掉的那种情况，
    总得能把这两件事分开看（tests/verify_update_e2e.py 直接拿它去跑）。
    """
    return "\r\n".join([
        "$ErrorActionPreference = 'SilentlyContinue'",
        "$pid0 = %d" % pid,
        "$stage = %s" % _ps_quote(stage),
        "$src = %s" % _ps_quote(src_root),
        "$dst = %s" % _ps_quote(dst_root),
        "$exe = %s" % _ps_quote(exe_dst),
        "$log = Join-Path $env:LOCALAPPDATA 'SenseNovaCanvas\\update.log'",
        "function Note($m){ Add-Content -LiteralPath $log -Value ((Get-Date).ToString('s') + ' ' + $m) -Encoding UTF8 }",
        "Note ('wait pid ' + $pid0)",
        # 等旧进程退出：最多 120 秒，避免异常情况下无限挂着
        "$n = 0",
        "while ((Get-Process -Id $pid0 -ErrorAction SilentlyContinue) -and $n -lt 240) { Start-Sleep -Milliseconds 500; $n++ }",
        "Start-Sleep -Milliseconds 400",
        "Note 'swap start'",
        # /XF .env：把密钥留在原地，升级不该动它
        "& robocopy $src $dst /E /R:2 /W:1 /NFL /NDL /NJH /NJS /XF .env | Out-Null",
        "Note ('robocopy exit ' + $LASTEXITCODE)",
        "if (Test-Path -LiteralPath $exe) { Start-Process -FilePath $exe -WorkingDirectory $dst; Note 'new exe started' } else { Note 'exe missing after copy' }",
        "Start-Sleep -Milliseconds 800",
        "Remove-Item -LiteralPath $stage -Recurse -Force",
        # 脚本自己收尾（powershell 读完之后就不再占用这个文件了）
        "Remove-Item -LiteralPath $PSCommandPath -Force",
        "",
    ])


def _setup_script(pid: int, setup: str, exe_dst: str) -> str:
    """安装包路线的替换脚本（抽出来方便单测）。

    必须显式带 `/D=<当前程序目录>`：安装器的默认目录是
    `%LOCALAPPDATA%\\Programs\\无限画布`，绿色版用户一键更新时不带这个参数，
    新版会装到另一个目录去 —— 桌面上两份程序，还都以"最新版"自居。
    """
    dst_root = os.path.dirname(exe_dst)
    return "\r\n".join([
        "$ErrorActionPreference = 'SilentlyContinue'",
        "$pid0 = %d" % pid,
        "$setup = %s" % _ps_quote(setup),
        "$dst = %s" % _ps_quote(dst_root),
        "$exe = %s" % _ps_quote(exe_dst),
        "$log = Join-Path $env:LOCALAPPDATA 'SenseNovaCanvas\\update.log'",
        "function Note($m){ Add-Content -LiteralPath $log -Value ((Get-Date).ToString('s') + ' ' + $m) -Encoding UTF8 }",
        "Note ('wait pid ' + $pid0)",
        "$n = 0",
        "while ((Get-Process -Id $pid0 -ErrorAction SilentlyContinue) -and $n -lt 240) { Start-Sleep -Milliseconds 500; $n++ }",
        "Start-Sleep -Milliseconds 500",
        "Note ('run setup -> ' + $dst)",
        # 必须 Start-Process -Wait：安装器是 GUI 子系统程序，用 & 调用会立刻返回，
        # 后面的删除 / 重启会在安装还没写完时就执行（实测就是这么翻的车：
        # 脚本报 setup exit 空值、exe 一个字节没变、setup 文件还占着删不掉）。
        '$p = Start-Process -FilePath $setup -ArgumentList @("/S", ("/D=" + $dst)) -Wait -PassThru',
        "Note ('setup exit ' + $p.ExitCode)",
        "if (Test-Path -LiteralPath $exe) { Start-Process -FilePath $exe -WorkingDirectory $dst; Note 'restarted' } else { Note 'exe missing after setup' }",
        "Start-Sleep -Milliseconds 800",
        "Remove-Item -LiteralPath $setup -Force",
        "Remove-Item -LiteralPath $PSCommandPath -Force",
        "",
    ])


def _apply_setup(setup: str, ver: str) -> dict:
    """安装包路线：等本进程退出 → 静默跑 Setup.exe（/S）→ 重新启动。

    比 robocopy 干净的地方在于"只有一种升级逻辑"：用户双击安装包和程序内点
    「下载并升级」走的是同一段代码，出错面小。
    """
    exe_dst = os.path.join(app_dir(), os.path.basename(
        sys.executable if getattr(sys, "frozen", False) else "无限画布.exe"))
    pid = os.getpid()
    script = _setup_script(pid, setup, exe_dst)
    script_path = os.path.join(UPDATE_DIR, "apply.ps1")
    try:
        with open(script_path, "w", encoding="utf-8-sig") as fh:
            fh.write(script)
    except OSError as exc:
        return {"ok": False, "error": "写升级脚本失败：%s" % exc}
    ps = os.path.join(os.environ.get("SystemRoot") or r"C:\Windows",
                      "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    if not os.path.isfile(ps):
        ps = "powershell.exe"
    flags = 0x00000008 | 0x00000200
    try:
        subprocess.Popen(
            [ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", script_path],
            close_fds=True, creationflags=flags,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        return {"ok": False, "error": "拉起升级进程失败：%s" % exc}
    log("update apply (setup) launched: v%s pid=%d %s" % (ver, pid, setup))
    return {"ok": True, "kind": "setup", "version": ver, "pid": pid,
            "setup": setup, "to": app_dir()}


def update_apply() -> dict:
    """拉起一个独立的替换进程：等本进程退出 → 覆盖程序目录（跳过 .env）→ 启动新版。

    存档在 %LOCALAPPDATA%，不在程序目录里，所以覆盖程序目录天然不动存档；
    唯一要护住的是 exe 旁边的 `.env`（密钥），同步时用 /XF .env 排除。

    返回 ok 之后前端应当立刻退出程序，替换才真正发生。
    """
    if not getattr(sys, "frozen", False):
        return {"ok": False, "code": "dev",
                "error": "当前是 python 直跑的开发模式，不做自替换"}
    if os.name != "nt":
        return {"ok": False, "code": "os", "error": "一键更新目前只支持 Windows"}
    info = update_info()
    ver = str(info.get("latest") or "").strip() or "next"
    setup = os.path.join(UPDATE_DIR, "v%s-setup.exe" % ver)
    if os.path.isfile(setup):
        return _apply_setup(setup, ver)
    stage = os.path.join(UPDATE_DIR, "v" + ver)
    exe_new = _find_packaged_exe(stage)
    if not exe_new:
        return {"ok": False, "code": "stage", "error": "还没下载升级包，请先点「下载更新」"}
    src_root = os.path.dirname(exe_new)
    dst_root = app_dir()
    # 目标目录必须可写，否则替换会静默失败（装到 Program Files 就是这种情况）
    probe = os.path.join(dst_root, ".snc_write_test")
    try:
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
    except OSError as exc:
        return {"ok": False, "code": "perm",
                "error": "程序目录不可写（%s）。请把程序放到用户目录下，或以管理员身份运行。" % exc}
    try:
        os.makedirs(UPDATE_DIR, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "error": "升级目录不可用：%s" % exc}
    pid = os.getpid()
    exe_dst = os.path.join(dst_root, os.path.basename(exe_new))
    script = _update_script(pid, stage, src_root, dst_root, exe_dst)
    # 落地成 .ps1 再 -File 执行。
    # 早先试过 -EncodedCommand（整段 base64，纯 ASCII），但部分安全策略会直接拦
    # 「隐藏实际代码」的调用；-File 更透明，路径作为命令行参数走 Windows 的
    # Unicode 通道，中文目录也不会乱码 —— 前提是文件本身带 BOM，否则
    # PowerShell 5.1 会按 ANSI 解码，中文路径当场变乱码。
    script_path = os.path.join(UPDATE_DIR, "apply.ps1")
    try:
        with open(script_path, "w", encoding="utf-8-sig") as fh:
            fh.write(script)
    except OSError as exc:
        return {"ok": False, "error": "写升级脚本失败：%s" % exc}
    ps = os.path.join(os.environ.get("SystemRoot") or r"C:\Windows",
                      "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    if not os.path.isfile(ps):
        ps = "powershell.exe"
    flags = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(
            [ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", script_path],
            close_fds=True, creationflags=flags,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        return {"ok": False, "error": "拉起升级进程失败：%s" % exc}
    log("update apply launched: v%s pid=%d src=%s dst=%s" % (ver, pid, src_root, dst_root))
    return {"ok": True, "version": ver, "pid": pid,
            "from": src_root, "to": dst_root, "exe": exe_dst}


def _raw_write(text: str) -> None:
    if not text:
        return
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")
    except OSError:
        pass


def log(message: str) -> None:
    """写日志。

    窗口版里 stdout 被改道到日志文件，如果这里再 print() 一次，
    同一行会被写两遍（改道前甚至能递归出几十万字符）。所以改道后只写文件。
    """
    line = "%s  %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), message)
    _raw_write(line)
    if _STREAMS_REDIRECTED:
        return
    try:
        print(line, flush=True)
    except Exception:
        # windowed 构建里 stdout 可能是 None
        pass


def redirect_streams() -> None:
    """窗口版没有控制台，任何 print() 都会抛异常，统一改道到日志文件。"""
    global _STREAMS_REDIRECTED

    class _Sink:
        def write(self, text):
            if text and text.strip():
                _raw_write(text.rstrip())

        def flush(self):
            pass

    sys.stdout = _Sink()
    sys.stderr = _Sink()
    _STREAMS_REDIRECTED = True


def _writable(folder: str) -> bool:
    """os.access 在 Windows ACL 下会说谎，这里真的写一次。"""
    try:
        os.makedirs(folder, exist_ok=True)
        probe = os.path.join(folder, ".snc-write-probe")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("1")
        os.remove(probe)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# 本机密钥保护：API Key 不再明文落盘，用机器码派生密钥加密保存。
#
# 目的：key 被拷到别的机器 / 被直接从 .env 抠出来都没用——解密依赖本机机器码。
# 实现用纯标准库（不引入 cryptography/pycryptodome，避免打包体积与依赖坑）：
#   - 机器码 = 注册表 MachineGuid + 用户名 + 机器名 的混合，sha256 派生密钥
#   - 密文 = salt(16) || iv(16) || HMAC(16) || 流式加密(key)
#   - 流加密用密钥驱动的伪随机字节流（CTR 思路的简化版）
# 强度定位：挡"好奇型/普通拷贝"，不是防国家级别攻击（那需要真 AES + 硬件安全）。
# ---------------------------------------------------------------------------

_MACHINE_ID = None
_DERIVE_CACHE = {}
_DERIVE_LOCK = threading.Lock()


def _machine_id() -> str:
    """尽量稳定的机器指纹。多来源拼一起，任何一源失效都不至于整体崩。

    读注册表要开键，单次约 1ms；但 /api/health 会为每把钥匙各取一次，累计起来也值当缓存。
    """
    global _MACHINE_ID
    if _MACHINE_ID:
        return _MACHINE_ID
    parts = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Cryptography") as k:
            parts.append(winreg.QueryValueEx(k, "MachineGuid")[0])
    except Exception:
        pass
    for name in ("COMPUTERNAME", "USERNAME", "PROCESSOR_IDENTIFIER"):
        v = os.environ.get(name, "")
        if v:
            parts.append(v)
    if not parts:
        # 兜底：拿不到任何稳定标识时用盘符 + 固定盐，至少保证"换机器难猜"
        parts.append(os.environ.get("SYSTEMDRIVE", "C:"))
    _MACHINE_ID = "|".join(parts)
    return _MACHINE_ID


def _derive_key(salt: bytes) -> bytes:
    """由机器码 + 应用固定盐，用 PBKDF2 派生出 32 字节密钥。

    PBKDF2 20 万轮单次要 60ms 左右。原先没有任何缓存，/api/health 与 /api/providers
    会把五家（每家最多 5 把）的钥匙全部解一遍，接口就被拖到 300ms+（P4）。
    salt 是加密时随机生成后写进密文的，同一把钥匙永远同一个 salt，
    所以按 salt 缓存派生结果不会串味；进程重启后重算一次即可。
    """
    hit = _DERIVE_CACHE.get(salt)
    if hit is not None:
        return hit
    secret = ("snc-canvas::" + _machine_id()).encode("utf-8")
    key = hashlib.pbkdf2_hmac("sha256", secret, salt, 200_000, dklen=32)
    with _DERIVE_LOCK:
        if len(_DERIVE_CACHE) > 256:      # 5 家 × 5 槽远远到不了，纯防御
            _DERIVE_CACHE.clear()
        _DERIVE_CACHE[salt] = key
    return key


def _stream_mask(key: bytes, nonce: bytes, length: int) -> bytes:
    """由 key + nonce 生成 length 字节的伪随机掩码流（HMAC 计数器模式）。"""
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def _encrypt_secret(plaintext: str) -> str:
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(16)
    key = _derive_key(salt)
    data = plaintext.encode("utf-8")
    mask = _stream_mask(key, nonce, len(data))
    body = bytes(a ^ b for a, b in zip(data, mask))
    tag = hmac.new(key, nonce + body, hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(salt + nonce + tag + body).decode("ascii")


def _decrypt_secret(payload: str):
    """返回解密后的明文；失败返回 None（机器码变了 / 数据损坏）。"""
    try:
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
    except Exception:
        return None
    if len(raw) < 16 + 16 + 16:
        return None
    salt, nonce, tag, body = raw[:16], raw[16:32], raw[32:48], raw[48:]
    key = _derive_key(salt)
    if not hmac.compare_digest(hmac.new(key, nonce + body, hashlib.sha256).digest()[:16], tag):
        return None
    mask = _stream_mask(key, nonce, len(body))
    return bytes(a ^ b for a, b in zip(body, mask)).decode("utf-8", "replace")


_ENV_PATH = None


def env_path() -> str:
    """配置位置：统一放到 `%LOCALAPPDATA%\\SenseNovaCanvas\\.env`。

    v3.8.1 起不再优先用 exe 旁边那份。原因很实际：升级最省事的做法就是把新包
    解压覆盖到程序目录，或者跑一遍安装包 —— 这两种都会换掉程序目录里的所有
    文件，`.env` 放在那里，用户每升一次级就得重新填一次密钥。

    画布 / 技能 / MCP 本来就在 `%LOCALAPPDATA%`，把密钥也挪过去之后，程序目录
    就彻底无状态了：覆盖、重装、换盘符、换目录，都不影响"我是谁、我的东西在哪"。

    老用户第一次启动时，exe 旁边那份会被复制过来（原件保留，回滚旧版仍能用）。
    """
    global _ENV_PATH
    if _ENV_PATH:
        return _ENV_PATH
    legacy = os.path.join(app_dir(), ".env")
    home = os.path.join(data_dir(), ".env")
    if os.path.exists(home):
        _ENV_PATH = home
        return home
    if os.path.exists(legacy):
        try:
            shutil.copy2(legacy, home)
            log("config migrated: %s -> %s" % (legacy, home))
            _ENV_PATH = home
            return home
        except OSError as exc:
            # 迁移失败也不至于不能启动：退回老位置继续用
            log("config migrate failed (%s), keep using %s" % (exc, legacy))
            _ENV_PATH = legacy
            return legacy
    _ENV_PATH = home
    return home


def load_env():
    """每次调用都重新读盘：页面里保存密钥后要立刻生效。

    Key 优先读加密项 SENSENOVA_API_KEY_ENC（机器码解密）；
    旧版明文 SENSENOVA_API_KEY 作为兜底，读到后会被上层迁移成加密存储。
    """
    key = os.environ.get("SENSENOVA_API_KEY", "")
    model = os.environ.get("SENSENOVA_MODEL", "")
    path = env_path()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8-sig") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    name, value = line.split("=", 1)
                    name = name.strip()
                    value = value.strip().strip('"').strip("'")
                    if name == "SENSENOVA_API_KEY_ENC" and not key and value:
                        dec = _decrypt_secret(value)
                        if dec:
                            key = dec
                    elif name == "SENSENOVA_API_KEY" and not key:
                        key = value
                    elif name == "SENSENOVA_MODEL" and not model:
                        model = value
        except OSError as exc:
            log("read .env failed: %s" % exc)
    return key.strip(), (model.strip() or "fast")


def mask(key: str) -> str:
    key = (key or "").strip()
    if not key:
        return ""
    if len(key) <= 12:
        return key[:2] + "***"
    return key[:7] + "…" + key[-4:]


def _probe_instance(port: int, host: str = "127.0.0.1", timeout: float = 0.8) -> str:
    """端口上跑的是不是本程序？是则返回它的版本号，否则返回 ""。

    为什么要先问这个：端口是 IndexedDB 的 origin 的一部分。同时开两个实例、
    或者一次"被占用就换端口"，都等于换了一个浏览器站点 —— 画布、技能、MCP
    全都看着不见了。所以启动第一个问题不是"端口空不空"，而是"是不是自己"。
    """
    try:
        with urllib.request.urlopen(
                "http://%s:%d/api/health" % (host, port), timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return ""
    if not isinstance(data, dict) or not data.get("ok"):
        return ""
    if data.get("app") == "sensenova-canvas" or data.get("backend") == "multi":
        return str(data.get("version") or "?")
    return ""


def free_port(preferred: int) -> int:
    """端口被占就让系统挑一个，避免双击第二次直接失败。

    Windows 上不要设 SO_REUSEADDR：它允许两个 socket 同时绑同一个端口，
    双击两次 exe 就会出现两个服务共享 8000，请求随机落到旧进程上——
    表现就是"明明换了新版，页面还是老的"。这里必须让第二个实例拿到新端口。
    """
    for candidate in (preferred, 0):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if os.name != "nt":
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", candidate))
            return sock.getsockname()[1]
        except OSError:
            continue
        finally:
            sock.close()
    raise RuntimeError("no free port")


class BridgeServer(ThreadingHTTPServer):
    """同上：Windows 上禁止端口复用，保证一个实例一个端口。"""

    daemon_threads = True
    allow_reuse_address = os.name != "nt"


# --------------------------------------------------------------------------
# SenseNova 参数与错误
# --------------------------------------------------------------------------
def pixel_size(ratio, long_side):
    """"16:9" + 2048 -> 合法 WxH（32 的倍数，512–4096，比例 ≤3:1）。

    长边严格等于 res：以前竖图那一支写的是 long_side * 2，
    选 2K 的 9:16 实际会得到 2304x4096（4K，像素是 2K 的 4 倍），
    等于悄悄多烧积分。
    """
    try:
        rw_s, rh_s = str(ratio).split(":")[:2]
        rw, rh = float(rw_s), float(rh_s)
    except (TypeError, ValueError):
        rw, rh = 16.0, 9.0
    if rw <= 0 or rh <= 0:
        rw, rh = 16.0, 9.0
    if rw / rh > 3:
        rw, rh = 3.0, 1.0
    if rh / rw > 3:
        rw, rh = 1.0, 3.0

    try:
        long_side = int(long_side)
    except (TypeError, ValueError):
        long_side = 2048
    if long_side not in LONG_SIDES:
        long_side = 2048

    if rw >= rh:
        w = float(long_side)
        h = w * rh / rw
    else:
        h = float(long_side)
        w = h * rw / rh

    def snap(value: float) -> int:
        return max(512, min(4096, int(round(value / 32.0) * 32)))

    return snap(w), snap(h)


def image_dimensions(blob: bytes):
    """从返回的二进制里读出真实宽高。

    上游的 data[0] 只有 b64_json，没有 size 字段。以前直接拿请求里的 size
    当作结果尺寸，所以参考图编辑、局部重绘这些改了比例的路径，卡片上标的
    尺寸根本不对。这里读文件头，PNG / JPEG / WebP 都覆盖。
    """
    try:
        if blob[:8] == b"\x89PNG\r\n\x1a\n" and len(blob) >= 24:
            w, h = struct.unpack(">II", blob[16:24])
            return int(w), int(h)

        if blob[:2] == b"\xff\xd8":
            i = 2
            end = len(blob) - 9
            while i < end:
                if blob[i] != 0xFF:
                    i += 1
                    continue
                marker = blob[i + 1]
                # SOF0-SOF15，跳过 DHT(C4)/JPG(C8)/DAC(CC)
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", blob[i + 5:i + 9])
                    return int(w), int(h)
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    i += 2
                    continue
                seg = struct.unpack(">H", blob[i + 2:i + 4])[0]
                i += 2 + seg

        if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
            kind = blob[12:16]
            if kind == b"VP8X":
                w = int.from_bytes(blob[24:27], "little") + 1
                h = int.from_bytes(blob[27:30], "little") + 1
                return w, h
            if kind == b"VP8 ":
                w = int.from_bytes(blob[26:28], "little") & 0x3FFF
                h = int.from_bytes(blob[28:30], "little") & 0x3FFF
                return w, h
            if kind == b"VP8L":
                bits = int.from_bytes(blob[21:25], "little")
                return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    except (IndexError, struct.error):
        pass
    return None


# 上游对 /images/edits 输入图的硬约束。前端已做规范化，服务端再兜一层：
# 直接把不合规的图发过去只会换回一个 400，用户看到的是「改图失败」而不是原因。
REF_IMAGE_MAX_BYTES = 10 * 1024 * 1024
REF_TOTAL_MAX_BYTES = 20 * 1024 * 1024
REF_MIN_SIDE = 256
REF_MAX_SIDE = 4096
REF_MAX_RATIO = 3.0


def validate_ref_images(images):
    """逐张 + 合计校验参考图，返回一句可读的错误说明；全合规返回 None。"""
    total = 0
    for idx, url in enumerate(images, 1):
        head, sep, payload = url.partition(",")
        if not sep or not payload:
            return "第 %d 张参考图数据不完整，请重新添加" % idx
        mime = head[11:].split(";")[0].lower() if head.startswith("data:image/") else ""
        if mime not in ("png", "jpeg", "jpg", "webp"):
            return "第 %d 张参考图格式不支持：只接受 PNG / JPEG / WebP" % idx
        size = len(payload) * 3 // 4      # base64 长度换回字节，不整段解码省内存
        total += size
        if size > REF_IMAGE_MAX_BYTES:
            return "第 %d 张参考图约 %.1fMB，超过单张 10MB 上限" % (idx, size / 1048576.0)
        # PNG / JPEG / WebP 的宽高都在文件头几 KB 内，只解头部即可；
        # 解析不出来就跳过尺寸校验，不误伤合法图。
        prefix = payload[:32768]
        try:
            blob = base64.b64decode(prefix + "=" * (-len(prefix) % 4))
        except Exception:
            blob = b""
        dim = image_dimensions(blob)
        if dim:
            w, h = dim
            if not (REF_MIN_SIDE <= w <= REF_MAX_SIDE and
                    REF_MIN_SIDE <= h <= REF_MAX_SIDE):
                return "第 %d 张参考图 %dx%d，单边需在 256–4096 之间" % (idx, w, h)
            ratio = max(w, h) / max(1, min(w, h))
            if ratio > REF_MAX_RATIO + 0.01:
                return "第 %d 张参考图比例 %.1f:1，超过 3:1 上限" % (idx, ratio)
    if total > REF_TOTAL_MAX_BYTES:
        return "参考图合计约 %.1fMB，超过 %dMB 请求体上限，请减少张数或换小图" % (
            total / 1048576.0, REF_TOTAL_MAX_BYTES // 1048576)
    return None


def classify(status: int, body: str):
    """把上游状态码翻成人能看懂的一句话。"""
    text = (body or "").strip()
    low = text.lower()

    # 尽量把上游的 error.message 挖出来，比裸 JSON 有用
    detail = ""
    if text.startswith("{"):
        try:
            data = json.loads(text)
            err = data.get("error")
            if isinstance(err, dict):
                detail = str(err.get("message") or err.get("code") or "")
            elif isinstance(err, str):
                detail = err
            if not detail:
                detail = str(data.get("message") or "")
        except ValueError:
            detail = ""

    if status == 401:
        return "auth", "密钥没被这家接受（401）：先确认整把都复制进来了、没有多余空格；确实是这一家的 Key，再去控制台重新签发"
    if status == 403:
        if "model" in low or "model" in detail.lower():
            return "model", "该模型未对当前账号开通，请在控制台开通后重试"
        return "forbidden", "没有权限调用该接口（403）"
    if status == 429:
        return "quota", "积分窗口已满或并发超限，请稍后重试或降低并发"
    if status in (400, 404, 422):
        # 参考图不合规时上游会在 message 里点名 images[0].image_url，
        # 这条比"尺寸不合法"精确得多，必须优先识别。
        if "image_url" in low or "images[" in low:
            return "image", "参考图不合规：" + (detail or "单边 256–4096、比例 ≤3:1、PNG/JPEG/WebP、≤10MB")
        if any(k in low for k in ("size", "width", "height", "resolution", "dimension")):
            return "size", "尺寸不合法：换 1:1 / 16:9，或降低分辨率再试"
        if "image" in low:
            return "image", "参考图不可用：最多 5 张，格式用 PNG / JPEG / WebP"
        if "model" in low:
            return "model", "模型名不被接受：" + (detail or "请换一个模型再试")
        return "bad_request", "请求被拒绝：" + (detail or text[:180] or "参数不合法")
    if status >= 500:
        return "server", "SenseNova 服务异常（%d），稍后重试" % status
    return "unknown", "请求失败（HTTP %d）%s" % (status, ("：" + (detail or text[:160])) if (detail or text) else "")


def resolve_model(value):
    """把页面上的别名（fast/lite）或完整 model_id 变成真实 model_id。

    不认识的名字直接拒掉并列出可用项——以前是原样转发，上游回 404
    model is not found，用户只看到一句"请求被拒绝"，根本不知道是模型选错了。
    """
    name = str(value or "").strip()
    if not name:
        return MODELS["fast"], ""
    if name in MODELS:
        return MODELS[name], ""
    for real in MODELS.values():
        if name == real:
            return real, ""
    return "", ("模型 %s 不是图片模型。图片生成/编辑只能用 %s（快）或 %s（稳）；"
                "账号里的 deepseek / glm / kimi / sensenova-6.8 是文本模型，已用于「AI 润色提示词」。"
                % (name, MODELS["fast"], MODELS["lite"]))


def verify_key(key: str):
    """GET /v1/models 校验凭据：不消耗出图积分，错 key 直接 401。"""
    if not key:
        return {"ok": False, "code": "missing", "message": "尚未配置密钥"}
    try:
        resp = requests.get(
            BASE + "/models",
            headers={"Authorization": "Bearer " + key},
            timeout=10,
        )
    except requests.RequestException as exc:
        return {"ok": False, "code": "network", "message": "无法连接 SenseNova：%s" % exc}

    if resp.status_code == 200:
        models = []
        try:
            data = resp.json()
        except ValueError:
            data = {}
        for item in (data.get("data") or []):
            if isinstance(item, dict) and item.get("id"):
                models.append(item["id"])
        return {"ok": True, "models": models}

    code, message = classify(resp.status_code, resp.text)
    return {"ok": False, "code": code, "message": message}


# --------------------------------------------------------------------------
# 模型清单：账号能调什么，就如实列什么
# --------------------------------------------------------------------------
_CATALOG = {"at": 0.0, "image": [], "text": [], "raw": [], "error": ""}
CATALOG_TTL = 300.0          # 正常缓存 5 分钟
CATALOG_TTL_ERR = 45.0       # 拉取失败时更快重试


def _vendor_of(model_id: str) -> str:
    low = (model_id or "").lower()
    for prefix, name in VENDOR:
        if low.startswith(prefix):
            return name
    return "其他"


def _text_label(model_id: str) -> str:
    """把 id 变成人能读的短标签，保留原始 id 便于排错。"""
    return "%s · %s" % (_vendor_of(model_id), model_id)


def fetch_catalog(key: str, force: bool = False) -> dict:
    """拉 /v1/models 并按能力分类。图片模型只认白名单里验证过的两个。"""
    now = time.time()
    with _STATE_LOCK:
        ttl = CATALOG_TTL_ERR if _CATALOG["error"] else CATALOG_TTL
        if not force and _CATALOG["at"] and (now - _CATALOG["at"]) < ttl:
            return dict(_CATALOG)

    raw, error, vision = [], "", set()
    if key:
        try:
            resp = requests.get(BASE + "/models",
                                headers={"Authorization": "Bearer " + key},
                                timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                items = [item for item in (data.get("data") or []) if isinstance(item, dict)]
                raw = [str(item.get("id")) for item in items if item.get("id")]
                # 能读图的模型单独标出来：6.8 Flash 这类只能看图写文字，出不了图
                vision = set(str(item.get("id")) for item in items
                             if "image" in (item.get("input_modalities") or []))
            else:
                error = "HTTP %d" % resp.status_code
        except (requests.RequestException, ValueError) as exc:
            error = str(exc)

    if not raw:
        raw = list(FALLBACK_TEXT_MODELS)

    image_ids = set(MODELS.values())
    text = [m for m in raw if m not in image_ids]
    # 账号里没列出 fast 也要保留：它确实能出图，只是没出现在 /models 里
    image = [
        {
            "key": k,
            "id": v["id"],
            "label": v["label"],
            "note": v["note"],
            "badge": v["badge"],
        }
        for k, v in IMAGE_MODELS.items()
    ]

    def text_key(m):
        return TEXT_ORDER.index(m) if m in TEXT_ORDER else 99

    text.sort(key=lambda m: (text_key(m), m))
    with _STATE_LOCK:
        _CATALOG.update({
            "at": now,
            "image": image,
            "text": [{"id": m, "label": _text_label(m), "vendor": _vendor_of(m),
                      "vision": m in vision} for m in text],
            "raw": raw,
            "error": error,
        })
        return dict(_CATALOG)


def default_text_model(catalog: dict) -> str:
    for item in catalog.get("text") or []:
        if item["id"] in TEXT_ORDER:
            return item["id"]
    for item in catalog.get("text") or []:
        return item["id"]
    return ""


POLISH_SYSTEM = (
    "你是资深 AI 图像提示词工程师，服务对象是建筑、景观与室内的效果图创作。"
    "任务：把用户的一句话扩写成可直接投喂图像模型的提示词。"
    "硬性要求："
    "1) 只输出润色后的提示词本身，中文，一段话，不分点、不解释、不加引号、不写“提示词：”；"
    "2) 完整保留用户原意、专有名词、地名和具体数值，不得替换或删掉；"
    "3) 可以补充镜头焦段与视角、光线方向与色温、材质与表面细节、色彩关系、氛围与时间，"
    "但不得新增用户没有提到的物体、人物、品牌或文字；"
    "4) 若用户在做局部修改，明确写出“只改某处、其余保持不变”；"
    "5) 长度控制在 600 字以内，画面感优先，避免空泛形容词堆砌。"
)

# v3.7.5：润色改成图文一起读之后，才追加的看图规则。纯文本润色时不带这几条，
# 免得模型对着空气「参考画面」。
POLISH_VISION_RULE = (
    "\n6) 已附参考图，按张序阅读：第 1 张通常是待修改的原图，其余是风格 / 构图 / 材质参考；"
    "\n7) 以画面为准：保留已有的视角、构图、光线方向与主要材质，补写的描述不得与画面冲突；"
    "\n8) 用户没提到、画面里也没有的物体、人物、文字或品牌一律不要新增。"
)

POLISH_MAX_IMAGES = 4                 # 一次最多带 4 张，够覆盖原图 + 3 张参考
POLISH_MAX_IMAGE_CHARS = 1600000     # 单张 data URL 字符上限（约 1.2MB 原图）
POLISH_MAX_TOTAL_CHARS = 4000000     # 整个请求里图片的总预算


def polish_system(with_images: bool) -> str:
    return POLISH_SYSTEM + (POLISH_VISION_RULE if with_images else "")


def clean_polish_images(body: dict) -> list:
    """前端压缩之外的一道闸：只收 data:image，按张数和总体积截断。"""
    out, total = [], 0
    for u in (body.get("images") or []):
        if not isinstance(u, str) or not u.startswith("data:image/"):
            continue
        if len(u) > POLISH_MAX_IMAGE_CHARS or total + len(u) > POLISH_MAX_TOTAL_CHARS:
            continue
        if "," not in u:
            continue
        out.append(u)
        total += len(u)
        if len(out) >= POLISH_MAX_IMAGES:
            break
    return out


def polish_user_content(user: str, images: list):
    """OpenAI 兼容 content：纯文本模型收字符串，多模态模型收数组。"""
    if not images:
        return user
    content = [{"type": "text", "text": user},
               {"type": "text", "text": "以下是本次要参考的画面，按张序理解："}]
    for i, u in enumerate(images, 1):
        content.append({"type": "text", "text": "参考图 %d" % i})
        content.append({"type": "image_url", "image_url": {"url": u}})
    return content


def _message_text(content) -> str:
    """多模态模型偶尔把 content 回成 [{type:text,text:...}] 数组。"""
    if isinstance(content, list):
        return "".join(str(p.get("text") or "") for p in content
                       if isinstance(p, dict)).strip()
    return str(content or "").strip()


def polish_google_parts(system: str, user: str, images: list) -> list:
    parts = [{"text": system + "\n\n" + user}]
    for i, u in enumerate(images, 1):
        parts.append({"text": "参考图 %d" % i})
        parts.append({"inline_data": {"mime_type": _mime_of(u), "data": _b64_of(u)}})
    return parts


def polish_image_rejected(resp) -> bool:
    """有些模型只收文字，塞 image_url 会 400。识别出来就自动去掉图片重发一次。"""
    if resp.status_code not in (400, 403, 404, 415, 422):
        return False
    low = (resp.text or "").lower()
    keys = ("image_url", "inline_data", "multimodal", "vision", "image input",
            "image content", "unsupported content", "only text", "text only", "图片")
    return any(k in low for k in keys)


def polish_prompt(key: str, text: str, model: str, context: str,
                  images=None) -> dict:
    """用文本模型润色提示词。不消耗出图额度；v3.7.5 起可带参考图一起读。"""
    images = list(images or [])
    catalog = fetch_catalog(key)
    model = (model or default_text_model(catalog)).strip()
    if not model:
        return {"ok": False, "code": "model", "message": "没有可用的文本模型"}

    user = text
    if context:
        user = "画面背景：%s\n需要润色的内容：%s" % (context, text)

    def call(temp, max_tokens=1800, suffix="", ims=None):
        use = images if ims is None else ims
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": polish_system(bool(use))},
                {"role": "user", "content": polish_user_content(user + suffix, use)},
            ],
            "max_tokens": max_tokens,
            "stream": False,
        }
        if temp is not None:
            payload["temperature"] = temp
        resp = requests.post(BASE + "/chat/completions",
                             headers={"Authorization": "Bearer " + key,
                                      "Content-Type": "application/json"},
                             data=json.dumps(payload), timeout=90)
        # kimi-k3 这类模型只接受 temperature=1
        if resp.status_code == 400 and "temperature" in resp.text.lower():
            payload.pop("temperature", None)
            payload["temperature"] = 1
            resp = requests.post(BASE + "/chat/completions",
                                 headers={"Authorization": "Bearer " + key,
                                          "Content-Type": "application/json"},
                                 data=json.dumps(payload), timeout=90)
            if resp.status_code == 400 and "temperature" in resp.text.lower():
                payload.pop("temperature", None)
                resp = requests.post(BASE + "/chat/completions",
                                     headers={"Authorization": "Bearer " + key,
                                              "Content-Type": "application/json"},
                                     data=json.dumps(payload), timeout=90)
        return resp

    started = time.time()
    try:
        resp = call(0.7)
        # 只收文字的老模型看到 image_url 会 400：自动去掉图片重发一次，
        # 别因为多附了一张图就让整次润色失败。
        if images and polish_image_rejected(resp):
            log("polish: %s rejected image input, retry text-only" % model)
            resp = call(0.7, ims=[])
            images = []
    except requests.RequestException as exc:
        return {"ok": False, "code": "network", "message": "润色请求失败：%s" % exc}

    latency = int((time.time() - started) * 1000)
    if resp.status_code >= 400:
        code, message = classify(resp.status_code, resp.text)
        if code == "quota":
            message = "该文本模型触发限流（tpm/rpm），等几秒再试或换个模型"
        return {"ok": False, "code": code, "message": message, "status": resp.status_code}

    def pick(resp_obj):
        try:
            data = resp_obj.json()
        except ValueError:
            return "", None
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        text_out = _message_text(msg.get("content"))
        text_out = text_out.strip('"').strip("“”").strip()
        return text_out, data

    out, data = pick(resp)
    if not out:
        # 推理型模型可能把预算全花在思考上，content 为空。
        # 加预算并明确要求直接给结果，绝不把 reasoning 当答案返回。
        try:
            resp2 = call(0.7, 2600,
                         "\n\n直接输出润色后的提示词正文，不要任何分析、思考过程或解释。")
            latency = int((time.time() - started) * 1000)
            if resp2.status_code < 400:
                out, data = pick(resp2)
        except requests.RequestException:
            pass
    if not out:
        return {"ok": False, "code": "empty",
                "message": "模型没有返回正文（多半是思考过程吃满了输出预算），换个文本模型再试"}

    return {
        "ok": True,
        "text": out,
        "model": (data or {}).get("model") or model,
        "latencyMs": latency,
        "usage": (data or {}).get("usage") or {},
        "imagesUsed": len(images),
    }


# --------------------------------------------------------------------------
# v3.0 · 三家渲染适配器
# --------------------------------------------------------------------------
# 上层只给一套统一参数（prompt / images / ratio / res / format / mask），
# 每家在这里翻译成自己的协议，再把结果折回统一格式：
#   {"ok": True,  "b64":..., "format":..., "model":..., "usage":..., "sizeAsked":...}
#   {"ok": False, "code":..., "error":..., "status":...}
def _mime_of(data_url: str) -> str:
    if isinstance(data_url, str) and data_url.startswith("data:"):
        head = data_url.split(",", 1)[0]
        return head[5:].split(";", 1)[0] or "image/png"
    return "image/png"


def _b64_of(data_url: str) -> str:
    if not isinstance(data_url, str):
        return ""
    return data_url.split(",", 1)[1] if "," in data_url else data_url


def _bytes_of(data_url: str):
    b64 = _b64_of(data_url)
    b64 += "=" * (-len(b64) % 4)
    try:
        return base64.b64decode(b64), _mime_of(data_url)
    except Exception:
        return b"", _mime_of(data_url)


def _ext_of(mime: str) -> str:
    low = (mime or "").lower()
    if "jpeg" in low or "jpg" in low:
        return "jpg"
    if "webp" in low:
        return "webp"
    return "png"


def render_sensenova(key, entry, req):
    """SenseNova：/images/generations 与 /images/edits（JSON，参考图走 image_url）。"""
    images = req["images"]
    fmt = req["fmt"]
    if images:
        url = BASE + "/images/edits"
        if req["size_mode"] == "auto" or req["ratio"] == "auto":
            size = "auto"
        else:
            width, height = pixel_size(req["ratio"], req["res"])
            size = "%dx%d" % (width, height)
        payload = {
            "model": entry["id"], "prompt": req["prompt"],
            "images": [{"image_url": u} for u in images],
            "size": size, "n": 1, "response_format": "b64_json",
            "output_format": fmt, "watermark": False,
            "prompt_extend": bool(req.get("extend", True)),
        }
    else:
        url = BASE + "/images/generations"
        width, height = pixel_size(req["ratio"], req["res"])
        size = "%dx%d" % (width, height)
        payload = {
            "model": entry["id"], "prompt": req["prompt"], "size": size, "n": 1,
            "response_format": "b64_json", "output_format": fmt, "watermark": False,
            "prompt_extend": bool(req.get("extend", True)),
        }
    resp = requests.post(url, headers={"Authorization": "Bearer " + key,
                                       "Content-Type": "application/json"},
                         data=json.dumps(payload), timeout=300)
    if resp.status_code >= 400:
        code, message = classify(resp.status_code, resp.text)
        return {"ok": False, "code": code, "error": message, "status": resp.status_code,
                "raw": resp.text[:400]}

    try:
        data = resp.json()
    except ValueError:
        return {"ok": False, "code": "server", "error": "接口返回的不是 JSON"}

    item = (data.get("data") or [{}])
    item = item[0] if item else {}
    b64 = ""
    if isinstance(item, dict):
        b64 = item.get("b64_json") or ""
        if not b64 and item.get("url"):
            try:
                blob = requests.get(item["url"], timeout=120)
                if blob.status_code == 200:
                    b64 = base64.b64encode(blob.content).decode("ascii")
            except requests.RequestException as exc:
                log("fetch url failed: %s" % exc)
    if b64.startswith("data:") and "," in b64:
        b64 = b64.split(",", 1)[1]
    if not b64:
        err = data.get("error")
        msg = err.get("message") if isinstance(err, dict) else ""
        return {"ok": False, "code": "server", "error": str(msg or "接口没有返回图片数据")}
    return {"ok": True, "b64": b64, "format": fmt, "model": entry["id"],
            "usage": data.get("usage") or {}, "sizeAsked": size}


# gpt-image-1 只认固定的三档尺寸；比例不在表里就按最接近的给
OPENAI_SIZES = {
    "1:1": "1024x1024",
    "3:2": "1536x1024", "16:9": "1536x1024", "4:3": "1536x1024", "21:9": "1536x1024",
    "2:3": "1024x1536", "9:16": "1024x1536", "3:4": "1024x1536",
}


def render_openai(key, entry, req):
    """OpenAI：无参考图走 /images/generations，有图（或蒙版）走 /images/edits（multipart）。"""
    base = provider_spec("openai")["base"]
    headers = {"Authorization": "Bearer " + key}
    ratio = req["ratio"]
    auto = req["size_mode"] == "auto" or ratio == "auto"
    size = "auto" if auto else OPENAI_SIZES.get(ratio, "1024x1024")
    images = req["images"]
    mask = req.get("mask") or ""
    extra = {}
    if req["fmt"] in OUTPUT_FORMATS:
        extra["output_format"] = req["fmt"]

    if images or mask:
        files = []
        for i, u in enumerate(images):
            blob, mime = _bytes_of(u)
            if not blob:
                continue
            files.append(("image[]", ("image%d.%s" % (i, _ext_of(mime)), blob, mime)))
        data = {"model": entry["id"], "prompt": req["prompt"], "size": size, "n": "1"}
        data.update(extra)
        if mask:
            mblob, _mm = _bytes_of(mask)
            if mblob:
                files.append(("mask", ("mask.png", mblob, "image/png")))
        # requests 的 multipart 不接受空 files（没图只有蒙版是不可能的，兜一下）
        if not files:
            return {"ok": False, "code": "bad_request", "error": "没有可用的参考图数据"}
        resp = requests.post(base + "/images/edits", headers=headers,
                             data=data, files=files, timeout=300)
    else:
        payload = {"model": entry["id"], "prompt": req["prompt"], "size": size, "n": 1}
        payload.update(extra)
        resp = requests.post(base + "/images/generations", headers=headers,
                             json=payload, timeout=300)

    if resp.status_code >= 400:
        code, message = classify(resp.status_code, resp.text)
        if code == "unknown" or code == "bad_request":
            message = "OpenAI 拒绝请求：" + message
        return {"ok": False, "code": code, "error": message, "status": resp.status_code,
                "raw": resp.text[:400]}
    try:
        data = resp.json()
    except ValueError:
        return {"ok": False, "code": "server", "error": "接口返回的不是 JSON"}
    item = (data.get("data") or [{}])
    item = item[0] if item else {}
    b64 = (item or {}).get("b64_json") or ""
    if b64.startswith("data:") and "," in b64:
        b64 = b64.split(",", 1)[1]
    if not b64:
        err = data.get("error")
        msg = err.get("message") if isinstance(err, dict) else ""
        return {"ok": False, "code": "server", "error": str(msg or "接口没有返回图片数据")}
    return {"ok": True, "b64": b64, "format": req["fmt"], "model": entry["id"],
            "usage": data.get("usage") or {}, "sizeAsked": size}


def _google_parts(resp_json):
    """从 generateContent 的返回里挖出第一张图和它的说明文字。"""
    for cand in resp_json.get("candidates") or []:
        parts = ((cand.get("content") or {}).get("parts") or [])
        text, image = "", None
        for part in parts:
            if part.get("text"):
                text += str(part["text"])
            inline = part.get("inline_data") or part.get("inlineData") or {}
            if inline.get("data") and image is None:
                image = inline
        if image:
            return image, text
    return None, ""


def _google_image_size(res) -> str:
    """前端的分辨率数字 → Gemini 的 imageSize 档位（只认 1K/2K/4K 这种大写写法）。"""
    try:
        n = int(res or 0)
    except (TypeError, ValueError):
        n = 0
    if n >= 4000:
        return "4K"
    if n >= 1800:
        return "2K"
    return "1K"


def render_google(key, entry, req):
    """Google：generateContent + responseModalities=[TEXT, IMAGE]，参考图走 inline_data。"""
    base = provider_spec("google")["base"]
    parts = [{"text": req["prompt"]}]
    for u in req["images"]:
        data = _b64_of(u)
        if data:
            parts.append({"inline_data": {"mime_type": _mime_of(u), "data": data}})
    mask = req.get("mask") or ""
    if mask:
        parts.append({"text": "另外附了一张黑白蒙版：白色区域是需要重绘的范围，"
                              "黑色区域保持像素级不动，交界处自然过渡。"})
        parts.append({"inline_data": {"mime_type": "image/png", "data": _b64_of(mask)}})
    payload = {"contents": [{"role": "user", "parts": parts}]}
    gc = {"responseModalities": ["TEXT", "IMAGE"]}
    ratio = req["ratio"]
    img_cfg = {}
    if ratio and ratio != "auto" and ratio in (entry.get("ratios") or []):
        img_cfg["aspectRatio"] = ratio
    # 3.x 才认 imageSize，而且只认大写 K（"2K" 行，"2k" 直接被拒）；
    # 只能出 1K 的 Lite 不传，让服务端用默认值，免得白报一次参数错。
    if int(entry.get("max_side") or 0) > 1024:
        img_cfg["imageSize"] = _google_image_size(req.get("res"))
    if img_cfg:
        gc["imageConfig"] = img_cfg
    payload["generationConfig"] = gc

    url = "%s/models/%s:generateContent" % (base, entry["id"])
    resp = requests.post(url, headers={"x-goog-api-key": key,
                                       "Content-Type": "application/json"},
                         data=json.dumps(payload), timeout=300)
    if resp.status_code >= 400:
        code, message = classify(resp.status_code, resp.text)
        if code in ("unknown", "bad_request"):
            message = "Google 拒绝请求：" + message
        return {"ok": False, "code": code, "error": message, "status": resp.status_code,
                "raw": resp.text[:400]}
    try:
        data = resp.json()
    except ValueError:
        return {"ok": False, "code": "server", "error": "接口返回的不是 JSON"}

    inline, note = _google_parts(data)
    if not inline:
        block = ""
        for cand in data.get("candidates") or []:
            block = str(cand.get("finishReason") or "")
        msg = "模型没有返回图片"
        if block in ("SAFETY", "PROHIBITED_CONTENT"):
            msg = "被安全策略拦截（%s），换个说法或换张参考图再试" % block
        return {"ok": False, "code": "server", "error": msg}
    b64 = inline.get("data") or ""
    mime = inline.get("mime_type") or inline.get("mimeType") or "image/png"
    fmt = "png" if "png" in mime else ("webp" if "webp" in mime else "jpeg")
    usage = data.get("usageMetadata") or {}
    return {"ok": True, "b64": b64, "format": fmt, "model": entry["id"],
            "usage": usage, "sizeAsked": ratio, "note": note}


def sniff_image_b64(b64: str, fallback: str = "png") -> str:
    """从 base64 头判断真实图片格式。

    方舟的 output_format 只对 5.0 系列生效、而且默认 jpeg；4.0 固定 jpeg。
    以前直接把前端选的 fmt 当成结果格式回抛，用户选 png 却拿到 jpeg 数据，
    存盘的扩展名就是错的。以数据本身为准最稳。
    """
    head = (b64 or "")[:12]
    if head.startswith("iVBORw0KG"):
        return "png"
    if head.startswith("/9j/"):
        return "jpeg"
    if head.startswith("UklGR"):
        return "webp"
    if head.startswith("R0lGOD"):
        return "gif"
    return fallback


def _seedream_tier(entry, res) -> str:
    """把前端的像素档位折成官方认的分辨率档位。

    官方档位不通用：5.0 只有 1K/1.5K/2K，4.0 只有 1K/2K/4K，
    传一个模型不支持的档位是直接 400 的，所以这里按 entry 的 size_tiers 挑最近的。
    """
    tiers = tuple(entry.get("size_tiers") or ("1K", "2K", "4K"))
    try:
        want = int(res or 0)
    except (TypeError, ValueError):
        want = 0
    if want <= 0:
        return "2K" if "2K" in tiers else tiers[0]
    best, gap = tiers[0], None
    for name in tiers:
        try:
            px = float(str(name).rstrip("K")) * 1024.0
        except ValueError:
            continue
        d = abs(px - want)
        if gap is None or d < gap:
            gap, best = d, name
    return best


def _seedream_size(entry, ratio, res) -> str:
    """按官方图片生成 API 的 size 规则算出尺寸字符串。

    官方卡的是「总像素区间 + 宽高比 [1/16,16]」，不是单边 1024–4096。
    以前按单边判断，21:9 在 2K 档算出 2048x878 会被误判成非法、退回档位 token，
    比例就丢了（模型会自己出 1:1，用户选 21:9 却拿到方图）。
    现在改成等比缩放到合法像素区间，比例始终保住。
    """
    lo = int(entry.get("pixel_min") or 921600)
    hi = int(entry.get("pixel_max") or 16777216)
    if not ratio or ratio == "auto":
        return _seedream_tier(entry, res)

    try:
        # res=0 是「原图」档：拿不到原图尺寸，统一按 2K 出，
        # 不能拿 max_side 当默认——4.0 的 max_side 是 4096，会把「原图」
        # 悄悄变成 4K，出图成本翻四倍。
        width, height = pixel_size(ratio, res or 2048)
    except (TypeError, ValueError):
        return _seedream_tier(entry, res)
    if width <= 0 or height <= 0:
        return _seedream_tier(entry, res)

    px = float(width) * float(height)
    if px < lo:
        k = math.sqrt(lo / px) * 1.005          # 多给 0.5%，8 对齐时不会掉回下限以下
        width = int(math.ceil(width * k / 8.0)) * 8
        height = int(math.ceil(height * k / 8.0)) * 8
    elif px > hi:
        k = math.sqrt(hi / px)
        width = int(math.floor(width * k / 8.0)) * 8
        height = int(math.floor(height * k / 8.0)) * 8

    if width <= 0 or height <= 0:
        return _seedream_tier(entry, res)
    if width / float(height) > 16.0 or height / float(width) > 16.0:
        return _seedream_tier(entry, res)
    if not (lo <= width * height <= hi):
        return _seedream_tier(entry, res)
    return "%dx%d" % (width, height)


_SEEDREAM_CHANNEL = {}      # (模型 key, 密钥尾号) -> 上次成功的 (base, model)，省掉反复试探


def _seedream_tag(entry, key: str = ""):
    """缓存要带上这把 key 的指纹。

    方舟两条入口互不通用：套餐 key 只能走 /api/plan/v3，按量 key 只能走 /api/v3。
    只按模型名缓存的话，用户换一把 key 后会先命中上一条 key 的通道 → 401 →
    白打一次请求才换到正确的通道。
    """
    return (entry.get("key") or entry["id"], (key or "")[-8:])


def _seedream_attempts(entry, key: str = ""):
    """返回要依次尝试的 (base, model) 列表。

    方舟的两个入口是互斥的：Agent Plan 用 /api/plan/v3，按量付费用 /api/v3，
    拿错 key 调另一条会直接 401（官方文档写明了这一点）。所以两边都得试，
    成功的组合缓存下来，后续请求直接命中，不再多打一次。

    套餐入口的模型名有三个版本（控制台 doubao-seedream-5-0-pro、
    套餐页 doubao-seedream-5.0-flash、官方 Model ID 带日期），官方文档确认
    「套餐入口同样接受带日期的 Model ID」，所以套餐通道先试官方 ID 最稳，
    再退回控制台写法。
    """
    spec = provider_spec("seedream")
    tag = _seedream_tag(entry, key)
    plan_base = (entry.get("plan_base") or "").rstrip("/")
    plan_id = entry.get("plan_id") or ""
    seq = []
    with _STATE_LOCK:
        cached = _SEEDREAM_CHANNEL.get(tag)
    if cached:
        seq.append(cached)
    if plan_base:
        seq.append((plan_base, entry["id"]))          # 套餐通道 + 官方 Model ID
        if plan_id and plan_id != entry["id"]:
            seq.append((plan_base, plan_id))          # 套餐通道 + 控制台写法
    seq.append(((entry.get("base") or spec["base"]).rstrip("/"), entry["id"]))

    seen, out = set(), []
    for base, model in seq:
        if (base, model) in seen:
            continue
        seen.add((base, model))
        out.append((base, model))
    return out


def _seedream_retryable(status: int, body: str) -> bool:
    """这个失败要不要换通道再试？

    401 必须重试：plan 入口和按量入口的 key 互不通用，官方写明用错入口就是 401。
    以前没把 401 算进来，用普通按量 key 的用户选 5.0 会先撞 plan 入口的 401，
    然后直接失败——等于 5.0 对按量用户完全不可用。
    其余只认「模型/接口不存在、没权限」这一类，别把真正的参数错误也重试掉。
    """
    if status == 401:
        return True
    if status not in (400, 403, 404):
        return False
    low = (body or "").lower()
    keys = ("model", "invalidendpoint", "not found", "notfound", "invalid endpoint",
            "does not exist", "unsupported", "no permission", "permission")
    return any(k in low for k in keys)


def split_seedream_layers(key, entry, req):
    """v3.7.9 · 官方图层拆分：1 张底图 + 最多 99 张带 alpha 的透明 PNG 图层。

    layer_decomposition=true 时 image 必须恰好 1 张，size 只认 1K/1.5K/2K/auto。
    响应 data[] 中 z_index=0 是底图，其余每层带 name / description / bounding_box
    （absolute 与 normalized 两套坐标），前端按 z_index 叠放即可还原画面。
    Seedream 5.5 额外支持 layer_decomposition_options.max_images（2–100，默认 30）
    与 text_recognition（文字图层的富文本 OCR）。
    """
    mid = str(entry.get("id") or "")
    is55 = "seedream-5-5" in mid
    is50 = "seedream-5-0-" in mid and ("pro" in mid or "flash" in mid)
    if not (is50 or is55):
        return {"ok": False, "code": "model",
                "error": "图层拆分只支持 Seedream 5.5 / 5.0 pro / flash（当前 %s）" % (mid or "未知模型")}
    images = req.get("images") or []
    if len(images) != 1:
        return {"ok": False, "code": "image", "error": "图层拆分只接收 1 张原图"}
    # 图层拆分场景 size 只认档位 token（1K/1.5K/2K/auto），不接受宽x高
    try:
        want_res = int(req.get("res") or 0)
    except (TypeError, ValueError):
        want_res = 0
    payload = {
        "model": mid,
        "image": images[0],
        # 官方说 prompt 可选，但 OpenAI SDK 形态要求有；不写会 400
        "prompt": str(req.get("prompt") or "拆分画面里的主要视觉元素"),
        "size": _seedream_tier(entry, want_res) if want_res > 0 else "auto",
        "layer_decomposition": True,
        "output_format": "png",       # 只影响底图，图层一律透明 PNG
        "response_format": "b64_json",
        "watermark": False,
    }
    if is55:
        opts = {}
        try:
            cap = int(req.get("layer_max") or 0)
        except (TypeError, ValueError):
            cap = 0
        if cap:
            opts["max_images"] = max(2, min(100, cap))
        if req.get("layer_ocr"):
            opts["text_recognition"] = True
        if opts:
            payload["layer_decomposition_options"] = opts
    last = None
    for base, model in _seedream_attempts(entry, key):
        payload["model"] = model
        try:
            resp = requests.post(base + "/images/generations",
                                 headers={"Authorization": "Bearer " + key,
                                          "Content-Type": "application/json"},
                                 data=json.dumps(payload), timeout=(10, 600))
        except requests.RequestException as exc:
            last = {"ok": False, "code": "network", "error": "连不上 Seedream：%s" % exc}
            continue
        if resp.status_code >= 400:
            code, message = classify(resp.status_code, resp.text)
            last = {"ok": False, "code": code, "error": message,
                    "status": resp.status_code, "raw": resp.text[:400]}
            if resp.status_code == 401 or _seedream_retryable(resp.status_code, resp.text):
                log("layer split channel %s / %s not accepted (%s), trying next"
                    % (base, model, resp.status_code))
                continue
            return last
        try:
            data = resp.json()
        except ValueError:
            return {"ok": False, "code": "server", "error": "接口返回的不是 JSON"}
        layers = []
        for i, it in enumerate(data.get("data") or []):
            if not isinstance(it, dict):
                continue
            b64 = str(it.get("b64_json") or "")
            if not b64 and it.get("url"):
                try:
                    blob = requests.get(it["url"], timeout=180)
                    if blob.status_code == 200:
                        b64 = base64.b64encode(blob.content).decode("ascii")
                except requests.RequestException as exc:
                    log("layer split fetch url failed: %s" % exc)
            if b64.startswith("data:") and "," in b64:
                b64 = b64.split(",", 1)[1]
            if not b64:
                continue
            try:
                z = int(it.get("z_index") if it.get("z_index") is not None else i)
            except (TypeError, ValueError):
                z = i
            layers.append({
                "b64": b64, "z_index": z,
                "name": str(it.get("name") or ("底图" if z == 0 else "图层 %d" % z)),
                "description": str(it.get("description") or ""),
                "bounding_box": it.get("bounding_box") or {},
                "width": it.get("width"), "height": it.get("height"),
                # v3.7.9 · 5.5 文字图层的富文本 OCR（文字、逐行坐标、近似样式）
                "text_recognition": it.get("text_recognition") or None,
            })
        if not layers:
            err = data.get("error")
            msg = err.get("message") if isinstance(err, dict) else ""
            return {"ok": False, "code": "server",
                    "error": str(msg or "图层拆分没有返回图片数据")}
        layers.sort(key=lambda L: L["z_index"])
        with _STATE_LOCK:
            _SEEDREAM_CHANNEL[_seedream_tag(entry, key)] = (base, model)
        return {"ok": True, "layers": layers, "model": entry["id"],
                "usage": data.get("usage") or {},
                "channel": ("plan" if "/plan/" in base else "pay")}
    return last or {"ok": False, "code": "server", "error": "图层拆分请求未发出"}


def render_seedream(key, entry, req):
    """Seedream / 火山方舟：OpenAI 风格的 /images/generations，
    参考图放在 image 字段（单张传字符串，多张传数组，data URL 直接可用）。"""
    if req.get("layers"):
        return split_seedream_layers(key, entry, req)
    want_fmt = req.get("fmt") or "png"
    payload = {
        "model": entry["id"],           # 进循环后按通道改写
        "prompt": req["prompt"],
        "size": _seedream_size(entry, req["ratio"], req["res"]),
        "response_format": "b64_json",
        "watermark": False,
    }
    # output_format 只有 5.0 / 5.5 系列认，而且是「png / jpeg」二选一、默认 jpeg。
    # 不显式下发的话，用户选 png 也会拿到 jpeg。4.0 不认这个字段，传了反而可能 400。
    if entry.get("out_fmt"):
        payload["output_format"] = "png" if want_fmt == "png" else "jpeg"
    # v3.7.9 · Seedream 5.5 原生 RGBA：background=transparent 必须配 png，
    # 5.0 pro / flash 只支持「1 张带透明通道的 PNG 图生图」，认这个字段会 400，
    # 所以只给显式标了 rgba 的模型下发。
    bg = str(req.get("background") or "").strip().lower()
    if bg in ("transparent", "opaque") and entry.get("rgba"):
        payload["background"] = bg
        if bg == "transparent":
            payload["output_format"] = "png"
            if want_fmt != "png":
                log("seedream transparent background forces png output")
    images = req["images"]
    if images:
        if int(entry.get("max_refs") or 0) <= 0:
            return {"ok": False, "code": "model",
                    "error": "%s 只支持文生图，换 Seedream 4.0 / 5.0 才能吃参考图" % entry["label"]}
        payload["image"] = images[0] if len(images) == 1 else images

    attempts = _seedream_attempts(entry, key)
    last = None
    dead_base = None            # 已经确认这把 key 进不去的入口，整条跳过
    for idx, (base, model) in enumerate(attempts):
        if base == dead_base:
            continue
        payload["model"] = model
        try:
            resp = requests.post(base + "/images/generations",
                                 headers={"Authorization": "Bearer " + key,
                                          "Content-Type": "application/json"},
                                 data=json.dumps(payload), timeout=(10, 300))
        except requests.RequestException as exc:
            last = {"ok": False, "code": "network", "error": "连不上 Seedream：%s" % exc}
            if idx + 1 < len(attempts):
                log("seedream %s failed (%s), trying next channel", base, exc.__class__.__name__)
                continue
            return last

        if resp.status_code >= 400:
            code, message = classify(resp.status_code, resp.text)
            if code in ("unknown", "bad_request"):
                message = "Seedream 拒绝请求：" + message
            last = {"ok": False, "code": code, "error": message,
                    "status": resp.status_code, "raw": resp.text[:400]}
            if resp.status_code == 401 and idx + 1 < len(attempts):
                # 401 是「这条入口不认这把 key」，同一入口换个模型名也没用，
                # 整条跳过，直接去另一条入口，省掉一次白跑。
                dead_base = base
                log("seedream channel %s rejected the key (401), skipping it" % base)
                continue
            if idx + 1 < len(attempts) and _seedream_retryable(resp.status_code, resp.text):
                log("seedream channel %s / %s not accepted (%s), trying next"
                    % (base, model, resp.status_code))
                continue
            return last

        try:
            data = resp.json()
        except ValueError:
            return {"ok": False, "code": "server", "error": "接口返回的不是 JSON"}

        item = (data.get("data") or [{}])
        item = item[0] if item else {}
        b64 = (item or {}).get("b64_json") or ""
        if not b64 and (item or {}).get("url"):
            try:
                blob = requests.get(item["url"], timeout=120)
                if blob.status_code == 200:
                    b64 = base64.b64encode(blob.content).decode("ascii")
            except requests.RequestException as exc:
                log("seedream fetch url failed: %s" % exc)
        if b64.startswith("data:") and "," in b64:
            b64 = b64.split(",", 1)[1]
        if not b64:
            err = data.get("error")
            msg = err.get("message") if isinstance(err, dict) else ""
            return {"ok": False, "code": "server", "error": str(msg or "接口没有返回图片数据")}
        with _STATE_LOCK:
            _SEEDREAM_CHANNEL[_seedream_tag(entry, key)] = (base, model)
        # 方舟会在 data[0].size 里回真实像素（模型可能对对齐做了微调），比请求值准
        got = str((item or {}).get("size") or "")
        return {"ok": True, "b64": b64,
                "format": sniff_image_b64(b64, payload.get("output_format") or "jpeg"),
                "model": entry["id"], "usage": data.get("usage") or {},
                "sizeAsked": got if "x" in got else payload["size"],
                "channel": ("plan" if "/plan/" in base else "pay")}
    return last or {"ok": False, "code": "server", "error": "Seedream 请求未发出"}


def _qwen_size(ratio: str, res) -> str:
    """DashScope 的尺寸写法是「宽*高」（星号），且每边 512–1440。"""
    if not ratio or ratio == "auto":
        return "1328*1328"
    width, height = pixel_size(ratio, res or 1024)
    k = min(1.0, 1440.0 / max(width, height))
    width = max(512, int(width * k)) // 2 * 2
    height = max(512, int(height * k)) // 2 * 2
    return "%d*%d" % (width, height)


def render_qwen(key, entry, req):
    """Qwen-Image：文生图走 OpenAI 兼容模式，指令编辑走原生 multimodal-generation。"""
    spec = provider_spec("qwen")
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    images = req["images"]
    if images:
        if int(entry.get("max_refs") or 0) <= 0:
            return {"ok": False, "code": "model",
                    "error": "%s 只支持文生图，换 Qwen-Image Edit 才能吃参考图" % entry["label"]}
        url = spec["base_native"] + "/services/aigc/multimodal-generation/generation"
        content = [{"image": u} for u in images]
        content.append({"text": req["prompt"]})
        payload = {
            "model": entry["id"],
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": {"negative_prompt": "", "watermark": False, "prompt_extend": False},
        }
        size_asked = "auto"
    else:
        url = spec["base"] + "/images/generations"
        size_asked = _qwen_size(req["ratio"], req["res"])
        payload = {"model": entry["id"], "prompt": req["prompt"], "size": size_asked,
                   "n": 1, "response_format": "b64_json"}
    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=300)
    if resp.status_code >= 400:
        code, message = classify(resp.status_code, resp.text)
        if code in ("unknown", "bad_request"):
            message = "Qwen 拒绝请求：" + message
        return {"ok": False, "code": code, "error": message, "status": resp.status_code,
                "raw": resp.text[:400]}
    try:
        data = resp.json()
    except ValueError:
        return {"ok": False, "code": "server", "error": "接口返回的不是 JSON"}

    b64, remote = "", ""
    item = (data.get("data") or [{}])
    item = item[0] if item else {}
    b64 = (item or {}).get("b64_json") or ""
    if not b64:
        remote = (item or {}).get("url") or ""
    if not b64 and not remote:
        output = data.get("output") or {}
        for choice in output.get("choices") or []:
            for part in ((choice.get("message") or {}).get("content") or []):
                if part.get("image"):
                    remote = part["image"]
                    break
            if remote:
                break
        if not remote:
            for row in output.get("results") or []:
                if row.get("url"):
                    remote = row["url"]
                    break
    if not b64 and remote:
        try:
            blob = requests.get(remote, timeout=120)
            if blob.status_code == 200:
                b64 = base64.b64encode(blob.content).decode("ascii")
        except requests.RequestException as exc:
            log("qwen fetch url failed: %s" % exc)
    if not b64:
        err = data.get("error") or data.get("message")
        msg = err.get("message") if isinstance(err, dict) else (err or "")
        return {"ok": False, "code": "server", "error": str(msg or "接口没有返回图片数据")}
    if b64.startswith("data:") and "," in b64:
        b64 = b64.split(",", 1)[1]
    return {"ok": True, "b64": b64, "format": req["fmt"], "model": entry["id"],
            "usage": data.get("usage") or {}, "sizeAsked": size_asked}


# --------------------------------------------------------------------------
# MiniMax H3-Image（v3.7.2）
# --------------------------------------------------------------------------
# 两套接口要分开打：没有参考图 → images/generations；有参考图 → images/edits。
# size 用 "宽x高" 明确像素（65.5 万–2000 万，宽高比 1:3–3:1），
# 不传 aspect_ratio / area —— 官方说两种形式混着传直接 400。
MINIMAX_PIXEL_MIN = 655360
MINIMAX_PIXEL_MAX = 20000000


def _minimax_size(ratio, res) -> str:
    """给 H3-Image 算一个合法的 "宽x高"；auto 按 res 出正方形。"""
    r = str(ratio or "").strip()
    try:
        long_side = int(res or 0)
    except (TypeError, ValueError):
        long_side = 0
    if not long_side:
        long_side = 2048
    if not r or r == "auto":
        side = max(1024, min(4096, long_side))
        return "%dx%d" % (side, side)
    w, h = pixel_size(r, long_side)
    # pixel_size 已保证单边 512–4096、比例 ≤3:1，这里只补「总像素」这一条，
    # 少了它会吃 400（上下限都是官方写死的）。
    total = float(w) * float(h)
    if total < MINIMAX_PIXEL_MIN:
        k = (MINIMAX_PIXEL_MIN / total) ** 0.5
        w = min(4096, int(w * k + 0.5) // 8 * 8)
        h = min(4096, int(h * k + 0.5) // 8 * 8)
        # 取整到 8 的倍数会掉回下限以下，往上补到过线为止（比例几乎不变）
        while w * h < MINIMAX_PIXEL_MIN and (w < 4096 or h < 4096):
            w = min(4096, w + 8)
            h = min(4096, h + 8)
    elif total > MINIMAX_PIXEL_MAX:
        k = (MINIMAX_PIXEL_MAX / total) ** 0.5
        w = max(512, int(w * k) // 8 * 8)
        h = max(512, int(h * k) // 8 * 8)
    return "%dx%d" % (w, h)


def render_minimax(key, entry, req):
    """MiniMax H3-Image：文生图 / 多图参考 / 指令编辑。

    三个容易踩的点写死在这儿：
    ① 有参考图必须换 images/edits 端点，不能拿 generations 硬塞；
    ② size 与 aspect_ratio 不能同时传（400），这里一律给像素；
    ③ HTTP 200 不代表全成功 —— 部分图会被内容安全拦掉，得逐条看 data[].error。
    """
    spec = provider_spec("minimax")
    images = [u for u in (req.get("images") or []) if u]
    editing = bool(images)
    url = spec["base"] + ("/images/edits" if editing else "/images/generations")
    payload = {
        "model": entry["id"],
        "prompt": str(req.get("prompt") or ""),
        "size": _minimax_size(req.get("ratio"), req.get("res")),
        "n": 1,
        "response_format": "b64_json",
        "output_format": "png",
    }
    if editing:
        cap = int(entry.get("max_refs") or 0)
        if cap <= 0:
            return {"ok": False, "code": "model",
                    "error": "%s 只支持文生图，不接受参考图" % entry["label"]}
        payload["images"] = [{"image_url": u} for u in images[:cap]]
    try:
        resp = requests.post(url,
                             headers={"Authorization": "Bearer " + key,
                                      "Content-Type": "application/json"},
                             data=json.dumps(payload), timeout=300)
    except requests.RequestException as exc:
        return {"ok": False, "code": "network", "error": "请求 MiniMax 失败：%s" % exc}
    if resp.status_code >= 400:
        code, message = classify(resp.status_code, resp.text)
        return {"ok": False, "code": code, "error": "MiniMax 拒绝请求：" + message,
                "status": resp.status_code, "raw": resp.text[:400]}
    try:
        data = resp.json()
    except ValueError:
        return {"ok": False, "code": "server", "error": "接口返回的不是 JSON"}

    b64, remote, first_err = "", "", ""
    for item in (data.get("data") or []):
        if not isinstance(item, dict):
            continue
        if item.get("b64_json") and not b64:
            b64 = item["b64_json"]
        if item.get("url") and not remote:
            remote = item["url"]
        err = item.get("error")
        if err and not first_err:
            first_err = (err.get("message") if isinstance(err, dict) else str(err)) or "出图失败"
    if not b64 and remote:
        try:
            blob = requests.get(remote, timeout=120)
            if blob.status_code == 200:
                b64 = base64.b64encode(blob.content).decode("ascii")
        except requests.RequestException as exc:
            log("minimax fetch url failed: %s" % exc)
    if not b64:
        msg = first_err or "接口没有返回图片数据"
        return {"ok": False, "code": ("content" if first_err else "server"),
                "error": "MiniMax：" + msg, "raw": resp.text[:400]}
    if b64.startswith("data:") and "," in b64:
        b64 = b64.split(",", 1)[1]
    return {"ok": True, "b64": b64, "format": sniff_image_b64(b64, "png"),
            "model": entry["id"], "usage": data.get("usage") or {},
            "sizeAsked": payload["size"],
            "channel": ("edit" if editing else "gen")}


def render_image(pid: str, key: str, entry: dict, req: dict):
    try:
        if pid == "sensenova":
            return render_sensenova(key, entry, req)
        if pid == "openai":
            return render_openai(key, entry, req)
        if pid == "google":
            return render_google(key, entry, req)
        if pid == "seedream":
            return render_seedream(key, entry, req)
        if pid == "qwen":
            return render_qwen(key, entry, req)
        if pid == "minimax":
            return render_minimax(key, entry, req)
    except requests.RequestException as exc:
        return {"ok": False, "code": "network", "error": "请求 %s 失败：%s"
                % (provider_spec(pid).get("label", pid), exc)}
    return {"ok": False, "code": "provider", "error": "未知供应商：%s" % pid}


def _probe_seedream_plan(key: str) -> bool:
    """Agent Plan 套餐 Key 只能用套餐通道验证。

    套餐入口没有 /models（GET 回来 404），拿按量通道的 /models 验又必然 401 ——
    这就是「明明能用，测试按钮却说密钥无效」的原因。
    这里改用一个**不会真出图**的探针：拿一个根本不存在的模型名发一单，
    套餐 Key 会回 404 UnsupportedModel（鉴权已通过、只是模型不认），
    无效 Key 才会回 401/403。既验证了鉴权，又不消耗出图额度。
    """
    base = "https://ark.cn-beijing.volces.com/api/plan/v3"
    try:
        resp = requests.post(base + "/images/generations",
                             headers={"Authorization": "Bearer " + key,
                                      "Content-Type": "application/json"},
                             json={"model": "__snc_probe__", "prompt": "ping", "size": "1K"},
                             timeout=15)
    except requests.RequestException:
        return False
    if resp.status_code in (401, 403):
        return False
    if resp.status_code in (400, 404):
        low = (resp.text or "").lower()
        # 模型不支持 / 参数不对都说明鉴权过了；只认这一种，别把限流之类算成成功
        keys = ("unsupportedmodel", "not support", "does not exist", "invalidparameter",
                "model")
        return any(k in low for k in keys)
    return False


def probe_provider(pid: str, key: str) -> dict:
    """列模型校验凭据，不消耗出图额度。"""
    spec = provider_spec(pid)
    if not spec:
        return {"ok": False, "code": "provider", "message": "未知供应商"}
    if not key:
        return {"ok": False, "code": "missing", "message": "尚未配置 %s 的密钥" % spec["label"]}
    try:
        if pid == "google":
            resp = requests.get(spec["base"] + "/models",
                                headers={"x-goog-api-key": key}, timeout=12)
        else:
            resp = requests.get(spec["base"] + "/models",
                                headers={"Authorization": "Bearer " + key}, timeout=12)
    except requests.RequestException as exc:
        return {"ok": False, "code": "network",
                "message": "无法连接 %s：%s" % (spec["label"], exc)}
    if resp.status_code != 200:
        # 火山方舟的 Agent Plan 套餐 Key 只认 /api/plan/v3，按量通道的 /models 一定 401。
        # 这种情况改用套餐通道探一次，成功了就别再报「密钥无效」误导用户。
        if pid == "seedream" and resp.status_code in (401, 403, 404):
            if _probe_seedream_plan(key):
                known = [m.get("plan_id") or m["id"]
                         for m in spec["image"] if m.get("plan_base")]
                plan_text = [t["id"] for t in (spec.get("text") or [])
                             if t.get("plan")]
                known += plan_text
                return {"ok": True, "models": known, "provider": pid,
                        "label": spec["label"], "channel": "plan",
                        "message": "Agent Plan 套餐通道已验证（按量通道不认这把 Key）"
                                   " · 含 %d 个套餐语言模型" % len(plan_text)}
        code, message = classify(resp.status_code, resp.text)
        if code == "auth":
            owner = _probe_owner(key, exclude=pid)
            if owner:
                ospec = provider_spec(owner)
                return {"ok": False, "code": "wrong_provider",
                        "message": "这把 Key 是 %s 的，不是 %s 的 —— 贴错家了。"
                                   "到「%s」那张卡片重新粘贴一次，这边这把可以删掉。"
                                   % (ospec["label"], spec["label"], ospec["label"]),
                        "suggest": {"provider": owner, "label": ospec["label"]}}
        return {"ok": False, "code": code, "message": message}
    try:
        data = resp.json()
    except ValueError:
        return {"ok": True, "models": []}
    models = []
    if pid == "google":
        for item in data.get("models") or []:
            name = str(item.get("name") or "")
            if name:
                models.append(name.split("/")[-1])
    else:
        for item in data.get("data") or []:
            if isinstance(item, dict) and item.get("id"):
                models.append(str(item["id"]))
    return {"ok": True, "models": models, "provider": pid, "label": spec["label"]}


def _probe_owner(key: str, exclude: str = "", timeout: float = 6.0) -> str:
    """这把钥匙到底是哪一家的。

    只在上游回 401/403 时才调：把 A 家的 Key 贴进 B 家卡片，是最常见的一种配置错误，
    而原来的文案是「key 无效或已注销」——用户照着去控制台重签一把新的，
    回来还是贴在同一张卡片里，照样失败。这里拿同一把 Key 挨家列一次模型，
    谁回 200 就是谁的。成功路径一次都不多花，失败路径最多多几次 /models。
    """
    for pid in PROVIDER_ORDER:
        if pid == exclude:
            continue
        spec = provider_spec(pid)
        if not spec:
            continue
        try:
            if pid == "google":
                resp = requests.get(spec["base"] + "/models",
                                    headers={"x-goog-api-key": key}, timeout=timeout)
            else:
                resp = requests.get(spec["base"] + "/models",
                                    headers={"Authorization": "Bearer " + key},
                                    timeout=timeout)
        except requests.RequestException:
            continue
        if resp.status_code == 200:
            return pid
    # Agent Plan 套餐 Key 对任何 /models 都回 401，但对套餐通道能验出来。
    # 不补这一句，把套餐 Key 贴错卡片时会误报「密钥无效」。
    try:
        if _probe_seedream_plan(key):
            return "seedream"
    except Exception:
        pass
    return ""


def polish_with(pid: str, key: str, model: str, text: str, context: str,
                images=None, plan=False) -> dict:
    """按供应商润色：Google 走 generateContent，其余走 OpenAI 兼容 chat/completions。

    v3.7.5 两处变化：
      ① 带参考图时改成多模态 content / inline_data，模型能真的看到画面；
      ② Seedream 这把 Key 可能是 Agent Plan 套餐 Key（只认 /api/plan/v3），
         也可能是按量 Key（只认 /api/v3）——按选中的模型决定先试哪条通道，
         401/404 就换另一条，别让用户手动判断自己买的是哪种套餐。
    """
    images = list(images or [])
    user = text if not context else "画面背景：%s\n需要润色的内容：%s" % (context, text)
    started = time.time()

    def fail(resp):
        code, message = classify(resp.status_code, resp.text)
        return {"ok": False, "code": code, "message": message,
                "status": resp.status_code, "imagesUsed": 0}

    if pid == "google":
        base = provider_spec("google")["base"]
        model = model or "gemini-2.5-flash"
        variants = [images, []] if images else [[]]
        resp, used = None, []
        for ims in variants:
            payload = {
                "contents": [{"role": "user",
                              "parts": polish_google_parts(polish_system(bool(ims)),
                                                           user, ims)}],
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1800},
            }
            try:
                resp = requests.post("%s/models/%s:generateContent" % (base, model),
                                     headers={"x-goog-api-key": key,
                                              "Content-Type": "application/json"},
                                     data=json.dumps(payload), timeout=90)
            except requests.RequestException as exc:
                return {"ok": False, "code": "network",
                        "message": "润色请求失败：%s" % exc}
            if resp.status_code < 400:
                used = ims
                break
            if not (ims and polish_image_rejected(resp)):
                return fail(resp)
            log("polish: %s rejected image input, retry text-only" % model)
        if resp is None or resp.status_code >= 400:
            return fail(resp)
        try:
            data = resp.json()
        except ValueError:
            return {"ok": False, "code": "server", "message": "接口返回的不是 JSON"}
        out = ""
        for cand in data.get("candidates") or []:
            for part in ((cand.get("content") or {}).get("parts") or []):
                if part.get("text"):
                    out += str(part["text"])
        out = out.strip().strip('"').strip("“”").strip()
        if not out:
            return {"ok": False, "code": "empty", "message": "模型没有返回正文，换个模型再试"}
        return {"ok": True, "text": out, "model": model,
                "latencyMs": int((time.time() - started) * 1000),
                "usage": data.get("usageMetadata") or {}, "imagesUsed": len(used)}

    spec = provider_spec(pid)
    default_model = ("doubao-seed-2.1-lite" if pid == "seedream" else "gpt-4.1-mini")
    model = model or default_model
    if pid == "seedream":
        # plan=True 的是套餐模型：先走套餐通道；按量模型反过来。
        first = spec.get("plan_base") if plan else spec["base"]
        second = spec["base"] if plan else spec.get("plan_base")
        bases = [b for b in (first, second) if b]
    else:
        bases = [spec["base"]]
    variants = [images, []] if images else [[]]

    resp, used, hit = None, [], ""
    for base in bases:
        for ims in variants:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": polish_system(bool(ims))},
                    {"role": "user", "content": polish_user_content(user, ims)},
                ],
                "max_tokens": 1800,
                "temperature": 0.7,
                "stream": False,
            }
            try:
                resp = requests.post(base + "/chat/completions",
                                     headers={"Authorization": "Bearer " + key,
                                              "Content-Type": "application/json"},
                                     data=json.dumps(payload), timeout=90)
            except requests.RequestException as exc:
                return {"ok": False, "code": "network",
                        "message": "润色请求失败：%s" % exc}
            if resp.status_code < 400:
                used, hit = ims, base
                break
            if resp.status_code in (401, 403, 404):
                # 这条通道不认这把钥匙 / 这个模型，换下一条通道重来
                log("polish: channel %s rejected (%s), trying next" % (base, resp.status_code))
                break
            if ims and polish_image_rejected(resp):
                log("polish: %s rejected image input, retry text-only" % model)
                continue
            return fail(resp)
        if hit:
            break
    if not hit:
        return fail(resp)
    try:
        data = resp.json()
    except ValueError:
        return {"ok": False, "code": "server", "message": "接口返回的不是 JSON"}
    choice = (data.get("choices") or [{}])[0]
    out = _message_text((choice.get("message") or {}).get("content"))
    out = out.strip('"').strip("“”").strip()
    if not out:
        return {"ok": False, "code": "empty", "message": "模型没有返回正文，换个模型再试"}
    return {"ok": True, "text": out, "model": data.get("model") or model,
            "latencyMs": int((time.time() - started) * 1000),
            "usage": data.get("usage") or {}, "imagesUsed": len(used),
            "channel": "plan" if hit == spec.get("plan_base") else "standard"}


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
# 静态资源白名单：路径 -> 包内文件名。只放行前端页面和图标，其余一律 404。
STATIC_FILES = {
    "/canvas.html": "canvas.html",
    "/app.ico": "app.ico",
    "/favicon.ico": "app.ico",
    # v3.8.2：标题栏 / 左栏 / 顶栏三处标识用的是这张裁出来的彩色 ∞
    "/mark.png": "mark.png",
}

# v3.7.4：技能预览图从内联 base64 改成 /art/ 外链。
# 页面体积 2.0MB -> 0.6MB，图片还能吃浏览器缓存；
# URL 带 ?v=<版本> 查询串，换版本自然失效，所以可以放心长缓存。
ART_DIR = "art"
ART_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ART_CACHE = "public, max-age=604800"

# 单次请求体上限。20MB 参考图转 base64 约 27MB，再留一倍余量给蒙版和 JSON 结构。
MAX_BODY_BYTES = 64 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    server_version = "snc-bridge/1.0"
    protocol_version = "HTTP/1.1"

    # ---- 基础输出 ----
    def log_message(self, fmt, *args):
        log("%s - %s" % (self.address_string(), fmt % args))

    def handle_one_request(self):
        """客户端中途断开（关窗、切画布 abort fetch）不该在日志里刷一屏 traceback。"""
        try:
            BaseHTTPRequestHandler.handle_one_request(self)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            self.close_connection = True

    def _json(self, payload, status=200):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _file(self, path, cache="no-store"):
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError:
            self._json({"ok": False, "error": "not found"}, 404)
            return
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            return {}
        if length > MAX_BODY_BYTES:
            # 不读就走，连接会被关掉；do_POST 已经先回过 413 了
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    # ---- v3.8.0 存档导出：原始字节流写盘 ----
    def _drain(self, length: int):
        """把没消费的请求体读掉，让客户端能正常收到响应而不是被 reset。"""
        left = max(0, int(length or 0))
        try:
            while left > 0:
                block = self.rfile.read(min(1 << 20, left))
                if not block:
                    break
                left -= len(block)
        except (OSError, ValueError):
            pass

    def _handle_backup_save(self):
        """POST /api/backup/save?name=<文件名>，请求体是 gzip 过的 .sncbak。

        先弹系统「另存为」再收流：用户取消就快速排空请求体并回 canceled，
        否则客户端会卡在「请求发完了却等不到响应」。
        """
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            self._json({"ok": False, "error": "没有收到备份内容"})
            return
        qs = parse_qs(urlparse(self.path).query)
        name = (qs.get("name") or [""])[0]
        auto = (qs.get("auto") or [""])[0] == "1"
        if auto:
            target = backup_auto_target()
            if not target:
                self._drain(length)
                self._json({"ok": False, "error": "无法创建自动备份目录"})
                return
        else:
            ok, target = backup_dialog(name)
            if not ok:
                self._drain(length)
                self._json({"ok": False, "error": target})
                return
            if target == "":
                self._drain(length)
                self._json({"ok": True, "canceled": True})
                return
        written = 0
        try:
            parent = os.path.dirname(target)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent, exist_ok=True)
            with open(target, "wb") as fh:
                left = length
                while left > 0:
                    block = self.rfile.read(min(1 << 20, left))
                    if not block:
                        break
                    fh.write(block)
                    left -= len(block)
                    written += len(block)
        except OSError as exc:
            self._json({"ok": False, "error": "写备份失败：%s" % exc})
            return
        log("backup saved: %s (%d bytes)" % (target, written))
        self._json({"ok": True, "path": target, "bytes": written})

    # ---- v3.5.1 本地接口防护 ----
    def _api_guard(self) -> bool:
        """挡住别的网页对本机 8000 端口发的跨站写请求。

        text/plain 属于 CORS「简单请求」，不触发预检，所以任意网页都能悄悄
        POST /api/config/clear 清掉密钥、或 /api/generate 烧额度——读不到响应，
        但副作用已经发生。两道闸：Origin 必须是本机（或没有 Origin，例如 curl、
        原生壳），且带 body 的请求必须声明 application/json（非简单请求 →
        浏览器会先发预检，而这里不回预检，请求就过不来）。
        """
        origin = (self.headers.get("Origin") or "").strip()
        if origin:
            try:
                host = (urlparse(origin).hostname or "").strip().lower()
            except ValueError:
                host = ""
            if host not in ("127.0.0.1", "localhost", "::1"):
                log("blocked cross-site POST %s from %s" % (self.path, origin))
                self._json({"ok": False, "code": "forbidden",
                            "error": "拒绝跨站请求"}, 403)
                return False
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0
        # v3.8.0 · 存档导出是二进制流（gzip），不能套用 JSON 那条 64MB / application/json 的规则。
        # 单独给一套上限与类型白名单，跨站防护（Origin 必须本机）仍然生效。
        if urlparse(self.path).path == "/api/backup/save":
            if length > BACKUP_LIMIT:
                self._json({"ok": False, "code": "too_large",
                            "error": "备份超过 %dGB，请先精简画布再导出"
                                     % (BACKUP_LIMIT // (1024 ** 3))}, 413)
                return False
            btype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if length > 0 and btype not in ("application/gzip", "application/octet-stream"):
                self._json({"ok": False, "code": "unsupported",
                            "error": "存档导出只接受 gzip 二进制流"}, 415)
                return False
            return True
        if length > MAX_BODY_BYTES:
            self._json({"ok": False, "code": "too_large",
                        "error": "请求体超过 %dMB，请减少参考图张数"
                                 % (MAX_BODY_BYTES // 1048576)}, 413)
            return False
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if length > 0 and ctype != "application/json":
            self._json({"ok": False, "code": "unsupported",
                        "error": "Content-Type 必须是 application/json"}, 415)
            return False
        return True

    # ---- GET ----
    def do_GET(self):
        global LAST_PAGE_PING
        path = urlparse(self.path).path

        if path == "/api/health":
            env = env_map()
            key, model = load_env()
            resolved, _ = resolve_model(model)
            catalog = fetch_catalog(key or primary_key())
            states = [provider_state(pid, env) for pid in PROVIDER_ORDER]
            ready = [s for s in states if s["configured"]]
            routes = load_routes(env)
            self._json({
                "ok": True,
                # v3.8.1：给「端口上跑的是不是本程序」一个明确标识。
                # 以前只能靠 backend=multi 猜，万一别的服务也回这个字段就误判。
                "app": "sensenova-canvas",
                "backend": "multi",
                "version": APP_VERSION,
                "port": PORT_INFO.get("got") or 0,
                "portWant": PORT_INFO.get("want") or 0,
                "portDrift": (bool(PORT_INFO.get("got"))
                              and PORT_INFO.get("got") != PORT_INFO.get("want")),
                "keyPresent": bool(ready),
                "key": (ready[0]["keys"][0]["mask"] if ready else ""),
                "defaultModel": model,
                "model": resolved or MODELS["fast"],
                "models": catalog["image"],
                "imageModels": catalog["image"],
                "textModels": catalog["text"],
                "defaultTextModel": default_text_model(catalog),
                "modelCount": len(catalog["raw"]),
                "catalogError": catalog["error"],
                "providers": states,
                "providersReady": [s["id"] for s in ready],
                "routes": routes,
                "capabilities": {
                    "textToImage": True,
                    "referenceEdit": True,
                    "maxReferenceImages": 10,
                    "mask": any((s["image"][0].get("mask") if s["image"] else False)
                                for s in states),
                    "multiN": False,
                    "sizeAuto": True,
                    "promptPolish": True,
                    "outputFormats": list(OUTPUT_FORMATS),
                },
            })
            return

        if path == "/api/providers":
            self._json(providers_payload())
            return

        if path == "/api/models":
            want = ""
            query = self.path or ""
            if "?" in query:
                for pair in query.split("?", 1)[1].split("&"):
                    if pair.startswith("provider="):
                        want = pair.split("=", 1)[1].strip().lower()
            force = "refresh=1" in query
            if want and want in PROVIDER_SPECS:
                env = env_map()
                keys = load_keys(want, env)
                spec = provider_spec(want)
                probe = probe_provider(want, keys[0]["key"]) if keys else {"ok": False}
                self._json({
                    "ok": True,
                    "provider": want,
                    "image": [dict(i, provider=want, value="%s:%s" % (want, i["key"]))
                              for i in spec.get("image") or []],
                    "text": [dict(i, provider=want, value="%s:%s" % (want, i["id"]))
                             for i in spec.get("text") or []],
                    "total": len(probe.get("models") or []),
                    "error": "" if probe.get("ok") else (probe.get("message") or ""),
                })
                return
            key, _ = load_env()
            catalog = fetch_catalog(key or primary_key(), force=force)
            self._json({
                "ok": True,
                "image": catalog["image"],
                "text": catalog["text"],
                "total": len(catalog["raw"]),
                "error": catalog["error"],
            })
            return

        # v2.6 · B2 / B3：更新通道与排障入口
        if path == "/api/update/check":
            self._json(update_info())
            return
        if path == "/api/logs/open":
            # v3.8.6 安全修复：打开本地目录属于带副作用操作，禁止 GET（防止跨站 <img> 静默触发），请改用 POST
            self._json({"ok": False, "code": "method_not_allowed",
                        "error": "请使用 POST /api/logs/open"}, 405)
            return
        if path == "/api/logs/tail":
            self._json({"ok": True, "path": LOG_PATH, "text": log_tail()})
            return

        if path in ("/", "/index.html"):
            path = "/canvas.html"
        if path == "/canvas.html":
            LAST_PAGE_PING = time.time()

        # v3.5.1 · 只发前端真正会加载的文件。
        # 以前是把整个程序目录裸发出去：GET /.env 能拿到密钥密文和模型配置，
        # GET /server.py 能下到全部后端源码；配合 --host 0.0.0.0 等于局域网可读。
        # 页面里已经不再内联图片（v3.7.4 起预览图走 /art/），
        # 所以白名单就是「页面 + 图标 + art 目录」三样，别的一律 404。
        # 预览图：只认 art/ 下一层的图片，白名单扩展名 + realpath 前缀双重校验，
        # 挡住 /art/../../server.py 这类穿越。
        if path.startswith("/art/"):
            self._send_art(path[len("/art/"):])
            return

        name = STATIC_FILES.get(path)
        if not name:
            self._json({"ok": False, "error": "not found"}, 404)
            return
        self._file(os.path.join(asset_dir(), name))

    def _send_art(self, name: str):
        """发一张 art 目录下的预览图。文件名里不允许分隔符，扩展名必须在白名单。"""
        bad = (not name) or ("/" in name) or ("\\" in name) or name.startswith(".")
        if not bad:
            ext = os.path.splitext(name)[1].lower()
            base = os.path.realpath(os.path.join(asset_dir(), ART_DIR))
            target = os.path.realpath(os.path.join(base, name))
            if ext in ART_EXT and target.startswith(base + os.sep):
                self._file(target, cache=ART_CACHE)
                return
        self._json({"ok": False, "error": "not found"}, 404)

    # ---- POST ----
    def do_POST(self):
        path = urlparse(self.path).path
        if not self._api_guard():
            return
        # v3.8.0 · 存档导出走原始字节流（gzip），不能先按 JSON 解析。
        # 放在 _read_json 之前，否则几十 MB 的备份会被 json.loads 拒掉。
        if path == "/api/backup/save":
            self._handle_backup_save()
            return
        body = self._read_json()

        # v2.7：导出走系统「另存为」，前端拿不到窗口就自动回退浏览器下载
        if path == "/api/save-file":
            self._json(save_export(body if isinstance(body, dict) else {}))
            return
        # v3.7.7：分层素材包一次另存为（ZIP）
        if path == "/api/save-zip":
            self._json(save_zip(body if isinstance(body, dict) else {}))
            return
        # v3.8.0 · 一键更新：下载解压 → 生成替换脚本（真正的替换在进程退出后由 .cmd 做）
        if path == "/api/update/download":
            self._json(update_download())
            return
        if path == "/api/update/apply":
            self._json(update_apply())
            return
        # v3.8.6 安全修复：打开日志目录走 POST + _api_guard 跨站防护
        if path == "/api/logs/open":
            self._json(open_logs_dir())
            return

        if path == "/api/config":
            self._handle_config(body)
            return
        if path == "/api/config/clear":
            self._handle_clear()
            return
        # v3.0 · 供应商卡片：加/删钥匙、改模型、改分流、测试连接
        if path == "/api/providers/key":
            self._handle_provider_key(body)
            return
        if path == "/api/providers/key/delete":
            self._handle_provider_key_delete(body)
            return
        if path == "/api/providers/model":
            self._handle_provider_model(body)
            return
        if path == "/api/providers/route":
            self._handle_provider_route(body)
            return
        if path == "/api/providers/test":
            self._handle_provider_test(body)
            return
        if path == "/api/verify":
            want = str(body.get("provider") or "").strip().lower()
            if want in PROVIDER_SPECS:
                keys = load_keys(want)
                if not keys:
                    self._json({"ok": False, "code": "missing",
                                "message": "尚未配置 %s 的密钥"
                                           % provider_spec(want)["label"]}, 200)
                    return
                res = probe_provider(want, keys[0]["key"])
                res["provider"] = want
                self._json(res)
                return
            # 老接口只认 SenseNova：以前这里落到 primary_key()，而 primary_key() 会先看
            # 「文生图分流」的供应商 —— 分流切到 Seedream 之后，这个接口就拿火山方舟的
            # 钥匙去问 SenseNova，永远 401，看起来像「Key 全废了」。
            key, _ = load_env()
            if not key:
                ks = load_keys("sensenova")
                key = ks[0]["key"] if ks else primary_key()
            self._json(verify_key(key or ""))
            return
        if path == "/api/generate":
            self._handle_generate(body)
            return
        if path == "/api/polish":
            self._handle_polish(body)
            return

        self._json({"ok": False, "error": "not found"}, 404)

    # ---- 供应商与密钥（v3.0）----
    def _provider_of(self, body):
        pid = str((body or {}).get("provider") or "").strip().lower()
        spec = provider_spec(pid)
        if not spec:
            self._json({"ok": False, "error": "未知供应商：%s" % (pid or "空")}, 400)
            return ""
        return pid

    def _handle_provider_key(self, body):
        pid = self._provider_of(body)
        if not pid:
            return
        spec = provider_spec(pid)
        key = str(body.get("key") or "").strip()
        label = str(body.get("label") or "").strip()[:24]
        if not key:
            self._json({"ok": False, "error": "API Key 不能为空"}, 400)
            return
        if any(ch.isspace() for ch in key):
            self._json({"ok": False, "error": "API Key 中包含空格或换行，请重新复制"}, 400)
            return
        # v3.7.6：输入框里显示的是「前 4 + 掩码 + 后 4」的预览，绝不能被当成真 Key 写进 .env
        if any(ch in key for ch in "•…") or "..." in key:
            self._json({"ok": False, "error": "这是脱敏预览，不是完整密钥，请重新粘贴"}, 400)
            return
        if len(key) < 16:
            self._json({"ok": False, "error": "API Key 长度不足，可能被截断了"}, 400)
            return
        warn = ""
        if spec.get("key_prefix") and not key.startswith(spec["key_prefix"]):
            warn = "%s 的密钥通常以 %s 开头，请确认没复制错" % (spec["label"],
                                                              spec["key_prefix"])
        try:
            action, item = add_key(pid, key, label)
        except OSError as exc:
            self._json({"ok": False, "error": "写入配置失败：%s" % exc}, 500)
            return
        if action == "full":
            self._json({"ok": False, "error": "每家最多 %d 把钥匙，先删一把再加" % KEY_SLOTS}, 400)
            return
        log("provider key %s (%s, %s)" % (pid, mask(key), action))
        self._json({"ok": True, "action": action, "provider": pid, "warn": warn,
                    "key": {"id": item["id"], "label": item["label"], "mask": mask(key)},
                    "state": provider_state(pid)})

    def _handle_provider_key_delete(self, body):
        pid = self._provider_of(body)
        if not pid:
            return
        key_id = str(body.get("keyId") or "").strip()
        try:
            slot = int(body.get("slot") or 0)
        except (TypeError, ValueError):
            slot = 0
        if not drop_key(pid, key_id, slot):
            self._json({"ok": False, "error": "没找到这把钥匙"}, 404)
            return
        log("provider key removed: %s %s" % (pid, key_id or slot))
        self._json({"ok": True, "provider": pid, "state": provider_state(pid)})

    def _handle_provider_model(self, body):
        pid = self._provider_of(body)
        if not pid:
            return
        want = str(body.get("model") or "").strip()
        entry = model_entry(pid, want)
        if not entry or (want and want not in (entry.get("key"), entry.get("id"))):
            self._json({"ok": False, "error": "没有这个图片模型：%s" % want}, 400)
            return
        env = env_map()
        env["SNC_MODEL_%s" % pid.upper()] = entry["key"]
        try:
            env_write(env)
        except OSError as exc:
            self._json({"ok": False, "error": "写入配置失败：%s" % exc}, 500)
            return
        self._json({"ok": True, "provider": pid, "defaultImage": entry["key"],
                    "state": provider_state(pid)})

    def _handle_provider_route(self, body):
        try:
            routes = save_routes(body.get("routes") or {})
        except OSError as exc:
            self._json({"ok": False, "error": "写入配置失败：%s" % exc}, 500)
            return
        self._json({"ok": True, "routes": routes})

    def _handle_provider_test(self, body):
        pid = self._provider_of(body)
        if not pid:
            return
        env = env_map()
        keys = load_keys(pid, env)
        if not keys:
            self._json({"ok": False, "code": "missing",
                        "error": "还没配置 %s 的密钥" % provider_spec(pid)["label"]}, 200)
            return
        rows = []
        first_models = None
        channel = ""
        note = ""
        for item in keys:
            res = probe_provider(pid, item["key"])
            if first_models is None and res.get("ok"):
                first_models = res.get("models") or []
                channel = res.get("channel") or ""
                note = res.get("message") or ""
            rows.append({"id": item["id"], "mask": item["mask"],
                         "ok": bool(res.get("ok")),
                         "code": res.get("code") or "",
                         "message": res.get("message") or "",
                         "suggest": res.get("suggest"),
                         "models": len(res.get("models") or [])})
        good = [r for r in rows if r["ok"]]
        if good:
            # 模型列表复用刚探到的结果，别再打一次接口（原来这里重复探测，按钮要多等一倍时间）
            self._json({"ok": True, "provider": pid,
                        "label": provider_spec(pid)["label"],
                        "models": first_models or [],
                        "channel": channel,          # "plan" = Agent Plan 套餐通道
                        "message": note,
                        "keys": rows})
            return
        first = rows[0]
        payload = {"ok": False, "code": first.get("code") or "auth", "provider": pid,
                   "error": first["message"] or "鉴权失败", "keys": rows}
        if first.get("suggest"):
            payload["suggest"] = first["suggest"]
        self._json(payload)

    # ---- 配置（老接口：等价于给 SenseNova 写入第一把钥匙）----
    def _handle_config(self, body):
        key = str(body.get("apiKey") or "").strip()
        model = str(body.get("model") or "fast").strip()

        if not key:
            self._json({"ok": False, "error": "API Key 不能为空"}, 400)
            return
        if any(ch.isspace() for ch in key):
            self._json({"ok": False, "error": "API Key 中包含空格或换行，请重新复制"}, 400)
            return
        if len(key) < 24:
            self._json({"ok": False, "error": "API Key 长度不足，可能被截断了"}, 400)
            return

        # 旧版本存过 "flash"（对应 sensenova-6.8-flash，图片接口 404），这里顺手纠正
        _, model_error = resolve_model(model)
        if model_error:
            log("config model %r not usable, falling back to fast" % model)
            model = "fast"

        env = env_map()
        env[_slot("sensenova", 1, "ENC")] = _encrypt_secret(key)
        env[_slot("sensenova", 1, "NAME")] = env.get(_slot("sensenova", 1, "NAME")) or "主账号"
        env["SNC_MODEL_SENSENOVA"] = model
        try:
            env_write(env)
        except OSError as exc:
            self._json({"ok": False, "error": "写入配置失败：%s" % exc}, 500)
            return

        log("config saved (sensenova key %s, model %s)" % (mask(key), model))
        self._json({"ok": True, "provider": "sensenova", "key": mask(key), "model": model,
                    "state": provider_state("sensenova")})

    def _handle_clear(self):
        """清除所有供应商的密钥（分流与模型选择保留）。"""
        env = env_map()
        removed = 0
        for name in list(env.keys()):
            if name.startswith("SNC_KEY_") or name in ("SENSENOVA_API_KEY",
                                                       "SENSENOVA_API_KEY_ENC"):
                env.pop(name, None)
                removed += 1
        try:
            env_write(env)
        except OSError as exc:
            self._json({"ok": False, "error": "清除失败：%s" % exc}, 500)
            return
        log("config cleared (%d entries)" % removed)
        self._json({"ok": True, "removed": removed, "providers": providers_payload(env)})

    # ---- 提示词润色 ----
    def _handle_polish(self, body):
        text = str(body.get("text") or "").strip()
        if not text:
            self._json({"ok": False, "code": "bad_request", "error": "先写一句要润色的内容"}, 400)
            return
        if len(text) > 2000:
            text = text[:2000]

        context = str(body.get("context") or "").strip()[:200]
        env = env_map()
        routes = load_routes(env)
        target = routes.get("polish") or DEFAULT_ROUTES["polish"]
        pid, t_model = (target.split(":", 1) + [""])[:2]

        want = str(body.get("provider") or "").strip().lower()
        if want in PROVIDER_SPECS:
            pid = want
        elif provider_spec(pid) is None or not provider_spec(pid):
            pid = "sensenova"
            t_model = ""

        keys = load_keys(pid, env)
        if not keys:
            # 润色分流指向的那家没配钥匙时，退到任何一家已配置的，别让用户卡在润色上
            for fallback in PROVIDER_ORDER:
                if fallback == pid:
                    continue
                keys = load_keys(fallback, env)
                if keys:
                    pid = fallback
                    t_model = (provider_spec(pid).get("text") or [{}])[0].get("id", "")
                    break
        if not keys:
            self._json({"ok": False, "code": "missing",
                        "error": "尚未配置任何密钥：设置 → 大模型调用 里填一把"}, 400)
            return

        model = str(body.get("model") or "").strip() or t_model
        entry = text_entry(pid, model)
        model_id = entry.get("id") or model

        # v3.7.5：润色由图 + 文一起进模型。清单里明确标了 vision=False 的
        # （GLM-5.3、DeepSeek V4 Flash/Pro 等）直接走纯文本，别浪费一次 400；
        # 没标的一律先带图发，上游不认图再由 polish_* 自动降级重发。
        images = clean_polish_images(body)
        if entry.get("vision") is False:
            images = []
        plan = bool(entry.get("plan"))

        if pid == "sensenova":
            result = polish_prompt(keys[0]["key"], text, model_id, context, images)
        else:
            result = polish_with(pid, keys[0]["key"], model_id, text, context,
                                 images, plan)

        if result.get("ok"):
            result["provider"] = pid
            result["imagesUsed"] = int(result.get("imagesUsed") or 0)
            result["vision"] = result["imagesUsed"] > 0
            log("polish ok: %s/%s %dms %d chars %d images" %
                (pid, result.get("model"), result.get("latencyMs", 0),
                 len(result.get("text", "")), result["imagesUsed"]))
            self._json(result)
            return

        log("polish failed: %s %s %s" % (pid, result.get("code"), result.get("message")))
        self._json({"ok": False, "code": result.get("code", "unknown"),
                    "provider": pid,
                    "error": result.get("message") or "润色失败"}, 200)

    # ---- 生成 ----
    def _handle_generate(self, body):
        prompt = str(body.get("prompt") or "").strip()
        if not prompt:
            self._json({"ok": False, "code": "bad_request", "error": "prompt 不能为空"}, 400)
            return

        # v3.7.7 · 图层拆分（导出「拆分图层 ZIP」）：
        # Seedream 5.5 / 5.0 pro / flash 支持，且 image 必须恰好 1 张。
        # 点名 seedream-5-5（5.5 支持 1 底图 + 99 层、可指定 max_images、带 OCR），
        # 再走原来的 pick_target / 多把钥匙轮换 / 套餐与按量双通道兜底，
        # 不另起一套鉴权逻辑；结果由 render_seedream 以 layers 返回。
        want_layers = bool(body.get("layerDecomposition"))
        if want_layers:
            one = [u for u in (body.get("images") or [])
                   if isinstance(u, str) and u.startswith("data:image")][:1]
            if not one:
                self._json({"ok": False, "error": "图层拆分需要一张原图"}, 400)
                return
            body = dict(body)
            body["images"] = one
            body["provider"] = "seedream"
            body["model"] = "seedream-5-5"
            body["task"] = "text2img"

        env = env_map()
        pid, entry, err = pick_target(body, env)
        if err:
            self._json({"ok": False, "code": err[0], "error": err[1]}, err[2])
            return

        fmt = str(body.get("format") or "png").strip().lower()
        if fmt not in OUTPUT_FORMATS:
            fmt = "png"

        # sizeMode="auto"（或 ratio="auto"）交给上游按输入图比例自己定尺寸。
        # 官方对 edits 的 size 默认值就是 auto，参考图编辑用它能完整保住原图比例。
        ratio = str(body.get("ratio") or "16:9").strip()
        want_auto = str(body.get("sizeMode") or "").lower() == "auto" or ratio.lower() == "auto"
        if want_auto:
            ratio = "auto"

        max_refs = int(entry.get("max_refs") or 5)
        images = [u for u in (body.get("images") or [])
                  if isinstance(u, str) and u.startswith("data:image")]
        images = images[:max_refs]

        # 前端规范化之外的最后一道兜底：本地先判一遍，别把不合规图丢给上游等 400。
        # 以前只对 SenseNova 生效，另外四家全靠前端压缩兜底——前端被绕过、
        # 或用户拖进一张 8K 截图时，就是一次白跑的上游请求。
        # 图层拆分官方允许的比例是 1/16–16、总像素 512²–6000²，比普通参考图宽，
        # 不能套 /images/edits 的 3:1 校验，交给上游判。
        if images and not want_layers:
            ref_error = validate_ref_images(images)
            if ref_error:
                log("generate(edit) rejected locally: %s" % ref_error)
                self._json({"ok": False, "code": "image", "error": ref_error}, 200)
                return

        # 蒙版只在支持蒙版的模型上透传；不支持的直接丢掉，别让上游 400
        mask = body.get("mask")
        if not (isinstance(mask, str) and mask.startswith("data:image")) or not entry.get("mask"):
            mask = ""

        extend = body.get("promptExtend")
        extend = True if extend is None else bool(extend)
        req = {
            "prompt": prompt,
            "images": images,
            "ratio": ratio,
            "res": body.get("res") or 2048,
            "fmt": fmt,
            "mask": mask,
            "extend": extend,
            "size_mode": "auto" if want_auto else "",
            "layers": want_layers,
            # v3.7.9：5.5 图层拆分的两项扩展 + 原生 RGBA 背景类型
            "layer_max": body.get("layerMax"),
            "layer_ocr": bool(body.get("layerOcr")),
            "background": str(body.get("background") or "").strip().lower(),
        }

        keys = load_keys(pid, env)
        if not keys:
            self._json({"ok": False, "code": "missing",
                        "error": "尚未配置 %s 的密钥：设置 → 大模型调用 里填一把"
                                 % provider_spec(pid)["label"]}, 400)
            return

        # 同家多把钥匙时轮流先用，遇到 401 自动换下一把——
        # 一个账号欠费 / 被限流不该让整张画布卡死。
        with _STATE_LOCK:
            start = _KEY_RR.get(pid, 0) % len(keys)
            _KEY_RR[pid] = start + 1
        ordered = keys[start:] + keys[:start]

        started = time.time()
        result, used = {}, {}
        for item in ordered:
            result = render_image(pid, item["key"], entry, req)
            used = item
            if result.get("ok"):
                break
            log("generate(%s/%s) key#%d failed: %s %s" % (
                pid, entry["id"], item["slot"], result.get("code"),
                str(result.get("error") or "")[:200]))
            if result.get("code") != "auth":
                break
        latency = int((time.time() - started) * 1000)

        if not result.get("ok"):
            status = result.get("status")
            self._json({"ok": False, "code": result.get("code") or "server",
                        "error": result.get("error") or "生成失败",
                        "provider": pid, "status": status},
                       200 if status else 502)
            return

        # 图层拆分响应没有单张 b64，直接把整组图层回给前端打包 ZIP
        if isinstance(result.get("layers"), list):
            self._json({
                "ok": True,
                "layers": result["layers"],
                "model": result.get("model") or entry["id"],
                "provider": pid,
                "latencyMs": latency,
                "usage": result.get("usage") or {},
            })
            return

        b64 = result["b64"]
        out_fmt = result.get("format") or fmt
        size = result.get("sizeAsked") or ""

        # 尺寸以上游实际产出的像素为准，不用请求参数冒充。
        # 只解 base64 头部就够了：PNG/JPEG 的宽高都在前几百字节里。
        head_b64 = b64[:4096]
        head_b64 += "=" * (-len(head_b64) % 4)
        try:
            real = image_dimensions(base64.b64decode(head_b64))
        except Exception:
            real = None
        if real:
            real_size = "%dx%d" % real
            out_w, out_h = real
        else:
            real_size, out_w, out_h = size, 0, 0

        log("generate(%s/%s) ok: %s %s %dms %s key#%s" % (
            pid, entry["id"], real_size, req["ratio"], latency, out_fmt, used.get("slot")))
        self._json({
            "ok": True,
            "b64": b64,
            "size": real_size,
            "width": out_w,
            "height": out_h,
            "format": out_fmt,
            "sizeAsked": size,
            "model": result.get("model") or entry["id"],
            "modelKey": entry["key"],
            "provider": pid,
            "providerLabel": provider_spec(pid)["label"],
            "masked": bool(mask),
            "mode": "edit" if (images or mask) else "gen",
            "promptExtend": extend,
            "keyMask": used.get("mask", ""),
            "latencyMs": latency,
            "usage": result.get("usage") or {},
        })

# --------------------------------------------------------------------------
# 窗口
# --------------------------------------------------------------------------
# 无边框外壳（方案 B：顶部 32px 细标题栏 + 页面自绘 10px 圆角）
#
# 为什么不用系统边框：这台机器是 Win10 19045，没有 Win11 的 DWM 圆角，
# 系统画的标题栏也不可能跟这套暗色界面同色。所以窗口走 frameless + transparent，
# 圆角由页面自己画（抗锯齿），圆角外是真的透明，能透出桌面。
#
# 代价是无边框后既拖不动也拉不动。
#
# v3.5：拖动改成「轮询光标、自己算位移」。v3.3 走的 ReleaseCapture +
# WM_NCLBUTTONDOWN(HTCAPTION) 在 WebView2 上不可靠：捕获属于 Chromium 的
# 子窗口/另一线程，js_api 又在第三个线程里调，系统移动循环收不到 mousemove，
# 表现就是「按住标题栏完全不动」。现在按下后起一个 60fps 的线程读
# GetCursorPos，把窗口左上角设成「按下时的位置 + 光标位移」，按键松开就退出 ——
# 全程不依赖鼠标捕获，也不依赖消息循环，跨进程/跨线程都成立。
_WIN = {"frame": None, "hwnd": 0, "frameless": False}

_WM_NCLBUTTONDOWN = 0x00A1
_HTCAPTION = 2
_HIT_CODES = {"left": 10, "right": 11, "top": 12, "topleft": 13, "topright": 14,
              "bottom": 15, "bottomleft": 16, "bottomright": 17}

_VK_LBUTTON = 0x01
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_DRAG = {"token": 0, "alive": False}


def _decl_drag(user32):
    """拖动要用到的几个函数。64 位下不声明签名，HWND 会被截成 32 位。"""
    import ctypes
    from ctypes import wintypes as wt

    user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
    user32.GetCursorPos.restype = wt.BOOL
    user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    user32.GetWindowRect.restype = wt.BOOL
    user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wt.UINT]
    user32.SetWindowPos.restype = wt.BOOL
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wt.BOOL
    user32.IsZoomed.argtypes = [wt.HWND]
    user32.IsZoomed.restype = wt.BOOL


def _drag_thread(hwnd: int, zone: str, token: int, min_w: int, min_h: int):
    import ctypes
    from ctypes import wintypes as wt

    user32 = ctypes.windll.user32
    _decl_drag(user32)

    def cursor():
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def rect():
        r = wt.RECT()
        if not user32.GetWindowRect(int(hwnd), ctypes.byref(r)):
            return None
        return r.left, r.top, r.right - r.left, r.bottom - r.top

    try:
        # 最大化状态下拖标题栏 = 先还原，再从还原后的位置接着拖（跟系统一致）
        if zone == "move" and user32.IsZoomed(int(hwnd)):
            user32.ShowWindow(int(hwnd), 9)          # SW_RESTORE
            time.sleep(0.06)

        base = rect()
        if not base:
            return
        ox, oy = cursor()
        while _DRAG["token"] == token:
            if not (user32.GetAsyncKeyState(_VK_LBUTTON) & 0x8000):
                break
            cx, cy = cursor()
            dx, dy = cx - ox, cy - oy
            x, y, w, h = base
            if zone == "move":
                x += dx
                y += dy
                flags = _SWP_NOSIZE | _SWP_NOZORDER | _SWP_NOACTIVATE
            else:
                if "left" in zone:
                    x += dx
                    w -= dx
                if "right" in zone:
                    w += dx
                if "top" in zone:
                    y += dy
                    h -= dy
                if "bottom" in zone:
                    h += dy
                if w < min_w:                        # 别拉得比最小尺寸还小
                    if "left" in zone:
                        x = base[0] + base[2] - min_w
                    w = min_w
                if h < min_h:
                    if "top" in zone:
                        y = base[1] + base[3] - min_h
                    h = min_h
                flags = _SWP_NOZORDER | _SWP_NOACTIVATE
            user32.SetWindowPos(int(hwnd), None, int(x), int(y), int(w), int(h), flags)
            time.sleep(0.012)                        # ≈80fps，够跟手又不吃 CPU
    except Exception as exc:
        log("drag thread failed: %s" % exc)
    finally:
        if _DRAG["token"] == token:
            _DRAG["alive"] = False


def _is_win11() -> bool:
    try:
        return sys.platform.startswith("win") and sys.getwindowsversion().build >= 22000
    except Exception:
        return False


def _apply_dwm_frame(hwnd: int, zoomed: bool = False) -> bool:
    """v3.8.6 · Win11 优先走原生 DWM 硬件抗锯齿圆角 + 原生窗口阴影。"""
    if not hwnd or not _is_win11():
        return False
    try:
        import ctypes
        from ctypes import wintypes as wt

        dwmapi = ctypes.windll.dwmapi
        dwmapi.DwmSetWindowAttribute.argtypes = [
            wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD
        ]
        dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
        # DWMWA_WINDOW_CORNER_PREFERENCE = 33; DWMWCP_DONOTROUND = 1, DWMWCP_ROUND = 2
        pref = ctypes.c_int(1 if zoomed else 2)
        hr = dwmapi.DwmSetWindowAttribute(int(hwnd), 33, ctypes.byref(pref), ctypes.sizeof(pref))
        if hr != 0:
            return False

        # 扩展 1px 客户端边框以唤醒 DWM 原生投影（无边框窗体默认无系统阴影）
        class _MARGINS(ctypes.Structure):
            _fields_ = [("cxLeftWidth", ctypes.c_int), ("cxRightWidth", ctypes.c_int),
                        ("cyTopHeight", ctypes.c_int), ("cyBottomHeight", ctypes.c_int)]
        m = _MARGINS(0, 0, 0, 0) if zoomed else _MARGINS(1, 1, 1, 1)
        dwmapi.DwmExtendFrameIntoClientArea.argtypes = [wt.HWND, ctypes.POINTER(_MARGINS)]
        dwmapi.DwmExtendFrameIntoClientArea.restype = ctypes.c_long
        dwmapi.DwmExtendFrameIntoClientArea(int(hwnd), ctypes.byref(m))
        return True
    except Exception as exc:
        log("dwm frame failed: %s" % exc)
        return False


def _apply_window_region(hwnd: int, radius_css: float = 12.0) -> bool:
    """把窗口裁成圆角矩形：Win11 优先原生 DWM 抗锯齿圆角+阴影，Win10 兜底 SetWindowRgn。"""
    if not hwnd:
        return False
    try:
        import ctypes
        from ctypes import wintypes as wt

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
        user32.SetWindowRgn.argtypes = [wt.HWND, wt.HRGN, wt.BOOL]
        user32.SetWindowRgn.restype = ctypes.c_int
        user32.IsZoomed.argtypes = [wt.HWND]
        user32.IsZoomed.restype = wt.BOOL
        gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
        gdi32.CreateRoundRectRgn.restype = wt.HRGN

        zoomed = bool(user32.IsZoomed(int(hwnd)))
        if _apply_dwm_frame(hwnd, zoomed=zoomed):
            # 确保没有残留的 GDI 硬裁剪区干扰 DWM 抗锯齿
            user32.SetWindowRgn(int(hwnd), None, True)
            return True

        rect = wt.RECT()
        if not user32.GetWindowRect(int(hwnd), ctypes.byref(rect)):
            return False
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return False
        if zoomed:
            user32.SetWindowRgn(int(hwnd), None, True)
            return True

        dpi = 96
        try:
            dpi = int(user32.GetDpiForWindow(int(hwnd)) or 96)
        except Exception:
            pass
        rad = max(2, int(round(radius_css * dpi / 96.0)))
        rgn = gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, rad * 2, rad * 2)
        if not rgn:
            return False
        return bool(user32.SetWindowRgn(int(hwnd), rgn, True))
    except Exception as exc:
        log("window region failed: %s" % exc)
        return False


def _region_watcher(hwnd: int):
    """窗口尺寸变了就重新裁一次圆角（最大化 / 手动拉伸都会变）。"""
    import ctypes
    from ctypes import wintypes as wt

    last = None
    while True:
        try:
            if not ctypes.windll.user32.IsWindow(int(hwnd)):
                return
            r = wt.RECT()
            ctypes.windll.user32.GetWindowRect(int(hwnd), ctypes.byref(r))
            # 只看尺寸和最大化状态：纯移动时窗口大小没变，重新裁一次会闪一下
            key = (r.right - r.left, r.bottom - r.top,
                   bool(ctypes.windll.user32.IsZoomed(int(hwnd))))
            if key != last:
                _apply_window_region(hwnd)
                last = key
        except Exception:
            return
        time.sleep(0.35)


def _start_region_watcher(hwnd: int):
    if not hwnd:
        return
    _apply_window_region(hwnd)
    try:
        t = threading.Thread(target=_region_watcher, args=(int(hwnd),),
                             name="snc-rgn", daemon=True)
        t.start()
    except Exception as exc:
        log("region watcher failed: %s" % exc)


def _track_window_drag(hwnd: int, zone: str = "move",
                       min_w: int = 1024, min_h: int = 680) -> bool:
    """按下时调用一次：起线程跟着鼠标走，返回 True 表示已接管。"""
    if not hwnd:
        return False
    _DRAG["token"] += 1
    _DRAG["alive"] = True
    try:
        t = threading.Thread(target=_drag_thread, name="snc-drag",
                             args=(int(hwnd), zone, _DRAG["token"], min_w, min_h))
        t.daemon = True
        t.start()
        return True
    except Exception as exc:
        _DRAG["alive"] = False
        log("drag start failed: %s" % exc)
        return False


def _native_hwnd(window) -> int:
    """pywebview 的 WinForms Form 才是真正的窗口，Handle 就是 HWND。"""
    try:
        handle = getattr(getattr(window, "native", None), "Handle", None)
        return int(str(handle)) if handle is not None else 0
    except Exception:
        return 0


def _begin_system_move(hwnd: int, zone: str = "move") -> bool:
    """把这次鼠标按下交给系统处理：移动或按方向拉伸。

    v3.3 修：以前只调 ReleaseCapture()，拖动完全没反应。原因是鼠标在
    WebView2 的页面上按下时，捕获属于 Chromium 的**子窗口**（另一个线程），
    而 ReleaseCapture 只释放「调用线程」的捕获 —— 对 Chromium 无效。
    捕获没交出来，系统的移动循环收不到 mousemove，窗口就拖不动。

    现在先用 SetCapture(hwnd) 把捕获从 Chromium 抢到我们的 Form 上，
    紧接着 ReleaseCapture()。Chromium 收到 WM_CAPTURECHANGED 会自己收尾，
    移动循环随后能正常接管鼠标。
    """
    try:
        import ctypes
        from ctypes import wintypes as wt

        _decl_user32()
        user32 = ctypes.windll.user32
        # 这几个之前没声明：64 位下 ctypes 默认按 32 位 int 传 HWND，
        # 句柄一旦超过 2^31 就会截断成无效值。
        user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        user32.SetCapture.argtypes = [wt.HWND]
        user32.SetCapture.restype = wt.HWND
        user32.ReleaseCapture.argtypes = []
        user32.ReleaseCapture.restype = wt.BOOL
        user32.GetCapture.argtypes = []
        user32.GetCapture.restype = wt.HWND

        code = _HTCAPTION if zone == "move" else _HIT_CODES.get(zone, _HTCAPTION)
        user32.SetCapture(int(hwnd))
        user32.ReleaseCapture()
        user32.SendMessageW(int(hwnd), _WM_NCLBUTTONDOWN, code, 0)
        return True
    except Exception as exc:
        log("system move failed: %s" % exc)
        return False


def _is_zoomed(hwnd: int) -> bool:
    """是否最大化。查系统状态比信 pywebview 的缓存可靠（用户按 Win+↑ 也要能跟上）。"""
    try:
        import ctypes
        return bool(ctypes.windll.user32.IsZoomed(hwnd or 0))
    except Exception:
        return False


def _bring_to_front(hwnd: int):
    """从托盘唤回来时顶到最前，否则窗口可能出现在其它窗口后面。"""
    if not hwnd:
        return
    try:
        import ctypes
        _decl_user32()
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)               # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
    except Exception:
        pass


def _asset_roots() -> list:
    """静态资源可能落在的三个地方：打包临时目录、源码目录、exe 目录。"""
    roots = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(meipass)
    roots.append(os.path.dirname(os.path.abspath(__file__)))
    try:
        roots.append(os.path.dirname(os.path.abspath(sys.executable)))
    except Exception:
        pass
    return roots


def _asset_path(name: str) -> str:
    for root in _asset_roots():
        candidate = os.path.join(root, name)
        if os.path.exists(candidate):
            return candidate
    return ""


def _icon_path() -> str:
    """app.ico 的位置。

    打包后 PyInstaller 把它解到 sys._MEIPASS；开发时就在 server.py 旁边。
    找不到就返回空串，调用方退回系统默认图标（总比不显示强）。
    """
    return _asset_path("app.ico")


_U32_READY = False


# ======================================================================
# 启动画面（纯 Win32 GDI，不依赖任何 GUI 库）
# ======================================================================
# 为什么不走常规两条路：
#   · tkinter —— 本机 Python 是精简安装，压根没有 tcl/tk（打包出来也不会有）
#   · 再开一个 WebView2 窗口当 splash —— WebView2 自己初始化就要 1s，
#     等于拿慢的部分去掩盖慢，用户还是先看到一片黑
# user32/gdi32 是系统自带的，画这块 420×236 的框只要几十毫秒，也不增加打包体积。
# v3.7.3 冷启 8.7 秒，这块框负责把前面那段「双击了没反应」填上。
_SPLASH = {"hwnd": 0, "msg": ""}
# v3.8.2：启动画面不再手画图案，直接播放 动画.mp4 的帧。
# 片源 2560×1440 / 30fps / 103 帧，构建期压成 640×360 的 zlib 帧序列（splash.dat），
# 运行期解一帧贴一帧 —— 屏幕上就是这段视频本身，不是重绘的近似。
_SPLASH_W, _SPLASH_H = 640, 360
_SPLASH_FPS = 30
_SPLASH_FRAMES = {}                      # 只读一次，多个线程共用
# COLORREF 是 0x00BBGGRR，跟 CSS 的 #RRGGBB 是反的
_SP_BG, _SP_GOLD, _SP_INK = 0x141110, 0x6AA8C9, 0xEFEDEC
_SP_DIM, _SP_MUTED, _SP_TRACK, _SP_CHIP = 0x80756F, 0x5C554F, 0x211D1B, 0x131719


def _splash_load_frames() -> dict:
    """读 splash.dat：magic(8) + count/w/h/fps(10) + N×(len(4) + zlib 帧)。

    这里只把整包读进内存、把每帧的偏移记下来，解压留到播放时一帧一帧做 ——
    103 帧一起解就是 95MB 常驻，不值得。
    """
    if _SPLASH_FRAMES:
        return _SPLASH_FRAMES
    path = _asset_path("splash.dat")
    if not path:
        return {}
    try:
        import struct
        with open(path, "rb") as fh:
            raw = fh.read()
        if raw[:8] != b"SNCSF001":
            log("splash: splash.dat magic mismatch, fallback to drawn")
            return {}
        count, w, h, fps = struct.unpack_from("<IHHH", raw, 8)
        offs, pos = [], 18            # 8 字节 magic + 4+2+2+2 头
        for _ in range(count):
            ln = struct.unpack_from("<I", raw, pos)[0]
            offs.append((pos + 4, ln))
            pos += 4 + ln
        _SPLASH_FRAMES.update(raw=raw, count=count, w=w, h=h,
                              fps=fps or _SPLASH_FPS, offs=offs)
        log("splash: %d frames %dx%d @%dfps, %.1f MB" %
            (count, w, h, _SPLASH_FRAMES["fps"], len(raw) / 1048576.0))
        return _SPLASH_FRAMES
    except Exception as exc:
        log("splash: load frames failed: %s" % exc)
        return {}


def _splash_frame_bytes(i: int) -> bytes:
    """解出一帧，转成 32 位 DIB 需要的 BGRX 顺序（BI_RGB 直接贴，不用再做转换）。"""
    import zlib
    fr = _SPLASH_FRAMES
    if not fr:
        return b""
    o, ln = fr["offs"][i]
    rgb = zlib.decompress(fr["raw"][o:o + ln])
    n = fr["w"] * fr["h"]
    buf = bytearray(n * 4)
    # 步长切片在 C 层跑，230k 像素约 1.5ms，比 Python 循环快两个数量级
    buf[0::4] = rgb[2::3]
    buf[1::4] = rgb[1::3]
    buf[2::4] = rgb[0::3]
    buf[3::4] = b"\xff" * n
    return bytes(buf)

_GDI = {}


def _gdi():
    """一次声明好要用的 Win32 签名。

    64 位下不声明 restype，句柄会被截成 32 位 —— 画刷/字体全变成野指针。
    """
    if _GDI:
        return _GDI
    import ctypes
    from ctypes import wintypes as wt

    u = ctypes.WinDLL("user32", use_last_error=True)
    g = ctypes.WinDLL("gdi32", use_last_error=True)
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wt.HINSTANCE), ("hIcon", wt.HANDLE),
                    ("hCursor", wt.HANDLE), ("hbrBackground", wt.HANDLE),
                    ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]

    class PAINTSTRUCT(ctypes.Structure):
        _fields_ = [("hdc", wt.HDC), ("fErase", wt.BOOL), ("rcPaint", wt.RECT),
                    ("fRestore", wt.BOOL), ("fIncUpdate", wt.BOOL),
                    ("rgbReserved", ctypes.c_byte * 32)]

    u.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    u.DefWindowProcW.restype = LRESULT
    u.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    u.RegisterClassW.restype = wt.ATOM
    u.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  wt.HWND, wt.HANDLE, wt.HINSTANCE, wt.LPVOID]
    u.CreateWindowExW.restype = wt.HWND
    u.DestroyWindow.argtypes = [wt.HWND]
    u.DestroyWindow.restype = wt.BOOL
    u.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    u.UpdateWindow.argtypes = [wt.HWND]
    u.BeginPaint.argtypes = [wt.HWND, ctypes.POINTER(PAINTSTRUCT)]
    u.BeginPaint.restype = wt.HDC
    u.EndPaint.argtypes = [wt.HWND, ctypes.POINTER(PAINTSTRUCT)]
    u.FillRect.argtypes = [wt.HDC, ctypes.POINTER(wt.RECT), wt.HANDLE]
    u.FrameRect.argtypes = [wt.HDC, ctypes.POINTER(wt.RECT), wt.HANDLE]
    u.SetTimer.argtypes = [wt.HWND, ctypes.c_size_t, wt.UINT, wt.HANDLE]
    u.SetTimer.restype = ctypes.c_size_t
    u.KillTimer.argtypes = [wt.HWND, ctypes.c_size_t]
    u.InvalidateRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT), wt.BOOL]
    u.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    u.PostQuitMessage.argtypes = [ctypes.c_int]
    u.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
    u.GetMessageW.restype = ctypes.c_int
    u.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
    u.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
    u.DispatchMessageW.restype = LRESULT
    k.GetModuleHandleW.argtypes = [wt.LPCWSTR]
    k.GetModuleHandleW.restype = wt.HINSTANCE
    u.SetWindowRgn.argtypes = [wt.HWND, wt.HANDLE, wt.BOOL]
    u.GetSystemMetrics.argtypes = [ctypes.c_int]
    u.GetSystemMetrics.restype = ctypes.c_int

    g.CreateSolidBrush.argtypes = [wt.DWORD]
    g.CreateSolidBrush.restype = wt.HANDLE
    g.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wt.DWORD]
    g.CreatePen.restype = wt.HANDLE
    g.CreateFontW.argtypes = ([ctypes.c_int] * 5 + [wt.DWORD] * 8 + [wt.LPCWSTR])
    g.CreateFontW.restype = wt.HANDLE
    g.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
    g.CreateRoundRectRgn.restype = wt.HANDLE
    g.SelectObject.argtypes = [wt.HDC, wt.HANDLE]
    g.SelectObject.restype = wt.HANDLE
    g.DeleteObject.argtypes = [wt.HANDLE]
    g.DeleteObject.restype = wt.BOOL
    g.GetStockObject.argtypes = [ctypes.c_int]
    g.GetStockObject.restype = wt.HANDLE
    g.SetTextColor.argtypes = [wt.HDC, wt.DWORD]
    g.SetBkMode.argtypes = [wt.HDC, ctypes.c_int]
    g.TextOutW.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int, wt.LPCWSTR, ctypes.c_int]
    g.Ellipse.argtypes = [wt.HDC] + [ctypes.c_int] * 4
    g.SaveDC.argtypes = [wt.HDC]
    g.SaveDC.restype = ctypes.c_int
    g.RestoreDC.argtypes = [wt.HDC, ctypes.c_int]

    # v3.8.2：启动画面逐帧贴图要用到的一小撮 GDI
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                    ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
                    ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                    ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                    ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]

    g.CreateDIBSection.argtypes = [wt.HDC, ctypes.POINTER(BITMAPINFOHEADER), wt.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]
    g.CreateDIBSection.restype = wt.HANDLE
    g.CreateCompatibleDC.argtypes = [wt.HDC]
    g.CreateCompatibleDC.restype = wt.HDC
    g.DeleteDC.argtypes = [wt.HDC]
    g.StretchBlt.argtypes = ([wt.HDC] + [ctypes.c_int] * 4 + [wt.HDC] +
                             [ctypes.c_int] * 4 + [wt.DWORD])
    g.SetStretchBltMode.argtypes = [wt.HDC, ctypes.c_int]
    u.GetDC.argtypes = [wt.HWND]
    u.GetDC.restype = wt.HDC
    u.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
    g.GetDeviceCaps.argtypes = [wt.HDC, ctypes.c_int]
    g.GetDeviceCaps.restype = ctypes.c_int

    _GDI.update(u=u, g=g, k=k, WNDPROC=WNDPROC, WNDCLASSW=WNDCLASSW,
                PAINTSTRUCT=PAINTSTRUCT, BMI=BITMAPINFOHEADER)
    return _GDI


def _splash_thread(ver: str, ready) -> None:
    import ctypes
    from ctypes import wintypes as wt

    api = _gdi()
    u, g, k = api["u"], api["g"], api["k"]
    WNDPROC, WNDCLASSW, PAINTSTRUCT, BMI = (api["WNDPROC"], api["WNDCLASSW"],
                                            api["PAINTSTRUCT"], api["BMI"])
    st = {"msg": "正在准备画布…", "i": -1, "t0": 0.0, "playing": True}

    frames = _splash_load_frames()
    use_video = bool(frames)
    fw = frames.get("w", _SPLASH_W) if use_video else _SPLASH_W
    fh = frames.get("h", _SPLASH_H) if use_video else _SPLASH_H
    total = frames.get("count", 0) if use_video else 0

    def fill(hdc, x, y, w, h, color, edge=None):
        r = wt.RECT(int(x), int(y), int(x + w), int(y + h))
        b = g.CreateSolidBrush(color)
        u.FillRect(hdc, ctypes.byref(r), b)
        g.DeleteObject(b)
        if edge is not None:
            e = g.CreateSolidBrush(edge)
            u.FrameRect(hdc, ctypes.byref(r), e)
            g.DeleteObject(e)

    def draw_text(hdc, x, y, s, font, color):
        old = g.SelectObject(hdc, font)
        g.SetTextColor(hdc, color)
        g.SetBkMode(hdc, 1)                    # TRANSPARENT
        g.TextOutW(hdc, int(x), int(y), s, len(s))   # TextOutW 只认字符数，-1 会画 0 个
        g.SelectObject(hdc, old)

    fonts = {
        "title": g.CreateFontW(-21, 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 5, 0,
                               "Microsoft YaHei UI"),
        "sub": g.CreateFontW(-13, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 5, 0,
                             "Microsoft YaHei UI"),
        "tip": g.CreateFontW(-12, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 5, 0,
                             "Microsoft YaHei UI"),
    }
    pen_gold = g.CreatePen(0, 1, _SP_GOLD)
    hollow = g.GetStockObject(5)               # NULL_BRUSH / HOLLOW_BRUSH

    # 图标：拿不到 splash 帧时用 app.ico 兜底
    hicon = None
    uico = None
    try:
        ico = _icon_path()
        if ico:
            uico = ctypes.WinDLL("user32", use_last_error=True)
            uico.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT,
                                       ctypes.c_int, ctypes.c_int, wt.UINT]
            uico.LoadImageW.restype = wt.HANDLE
            uico.DrawIconEx.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int,
                                        wt.HANDLE, ctypes.c_int, ctypes.c_int,
                                        wt.UINT, wt.HANDLE, wt.UINT]
            uico.DrawIconEx.restype = wt.BOOL
            uico.DestroyIcon.argtypes = [wt.HANDLE]
            uico.DestroyIcon.restype = wt.BOOL
            hicon = uico.LoadImageW(None, ico, 1, 48, 48, 0x0010)
    except Exception as exc:
        log("splash icon load failed: %s" % exc)
        hicon = None

    # ---- DPI：640×360 是设计尺寸，按系统缩放放大，贴图用 HALFTONE 拉伸 ----
    dpi = 96
    try:
        sdc = u.GetDC(None)
        if sdc:
            d = g.GetDeviceCaps(sdc, 88)       # LOGPIXELSX
            u.ReleaseDC(None, sdc)
            if d:
                dpi = d
    except Exception:
        pass
    scale = max(1.0, dpi / 96.0)
    win_w = int(round(_SPLASH_W * scale))
    win_h = int(round(_SPLASH_H * scale))

    # ---- 32 位 DIB：一帧一块，解完 memmove 进去直接贴 ----
    hbmp = hdc_mem = None
    bits = ctypes.c_void_p()
    if use_video:
        try:
            bmi = BMI()
            bmi.biSize = ctypes.sizeof(BMI)
            bmi.biWidth = fw
            bmi.biHeight = -fh                 # 负数 = 自上而下，行序跟 zlib 帧一致
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0              # BI_RGB
            hbmp = g.CreateDIBSection(None, ctypes.byref(bmi), 0,
                                      ctypes.byref(bits), None, 0)
            if hbmp:
                hdc_mem = g.CreateCompatibleDC(None)
                g.SelectObject(hdc_mem, hbmp)
            else:
                log("splash: CreateDIBSection failed, fallback to drawn")
                use_video = False
        except Exception as exc:
            log("splash: DIB init failed: %s" % exc)
            use_video = False

    def push_frame(idx):
        data = _splash_frame_bytes(idx)
        if data and bits:
            ctypes.memmove(bits, data, len(data))
            st["i"] = idx
            return True
        return False

    if use_video:
        push_frame(0)

    def advance():
        """按媒体时钟走帧：落后就跳帧，绝不排队补播。"""
        if not use_video or not total:
            return False
        el = time.perf_counter() - st["t0"]
        idx = int(el * frames["fps"])
        if idx > total - 1:
            idx = total - 1
        if idx != st["i"]:
            push_frame(idx)
        return idx < total - 1

    def paint(hdc):
        saved = g.SaveDC(hdc)
        try:
            if use_video and st["i"] >= 0:
                g.SetStretchBltMode(hdc, 4)    # HALFTONE
                g.StretchBlt(hdc, 0, 0, win_w, win_h, hdc_mem,
                             0, 0, fw, fh, 0x00CC0020)   # SRCCOPY
                # 状态文字压在最后一帧留白处：左下角一行，右下角版本号
                if st["msg"]:
                    draw_text(hdc, int(24 * scale), win_h - int(38 * scale),
                              st["msg"], fonts["tip"], _SP_MUTED)
                draw_text(hdc, win_w - int(92 * scale), win_h - int(38 * scale),
                          "v" + ver, fonts["tip"], 0x3A3F4A)
                return
            # ---- 兜底：没有 splash.dat 时，退回最朴素的一块牌子 ----
            fill(hdc, 0, 0, _SPLASH_W, _SPLASH_H, _SP_BG)
            if hicon and uico:
                uico.DrawIconEx(hdc, 28, 26, hicon, 46, 46, 0, None, 0x0003)
            else:
                fill(hdc, 28, 26, 46, 46, _SP_CHIP, _SP_GOLD)
                oldp = g.SelectObject(hdc, pen_gold)
                oldb = g.SelectObject(hdc, hollow)
                g.Ellipse(hdc, 33, 44, 55, 56)
                g.Ellipse(hdc, 46, 44, 68, 56)
                g.SelectObject(hdc, oldb)
                g.SelectObject(hdc, oldp)
            draw_text(hdc, 92, 27, APP_NAME, fonts["title"], _SP_INK)
            draw_text(hdc, 93, 61, "本地画布 · v" + ver, fonts["sub"], _SP_DIM)
            draw_text(hdc, 28, _SPLASH_H - 62, st["msg"], fonts["sub"], _SP_MUTED)
            fill(hdc, 0, _SPLASH_H - 3, _SPLASH_W, 3, _SP_TRACK)
            bar = int(_SPLASH_W * 0.28)
            fill(hdc, (_SPLASH_W - bar) // 2, _SPLASH_H - 3, bar, 3, _SP_GOLD)
        finally:
            g.RestoreDC(hdc, saved)

    def on_timer(hwnd):
        if _SPLASH.get("msg"):
            st["msg"] = _SPLASH["msg"]
        if use_video:
            if st["playing"] and not advance():
                st["playing"] = False
                u.KillTimer(hwnd, 1)           # 播完停在最后一帧，不再空转
        u.InvalidateRect(hwnd, None, False)

    def wndproc(hwnd, msg, wp, lp):
        if msg == 0x000F:                      # WM_PAINT
            ps = PAINTSTRUCT()
            hdc = u.BeginPaint(hwnd, ctypes.byref(ps))
            try:
                paint(hdc)
            finally:
                u.EndPaint(hwnd, ctypes.byref(ps))
            return 0
        if msg == 0x0113:                      # WM_TIMER
            on_timer(hwnd)
            return 0
        if msg == 0x0014:                      # WM_ERASEBKGND：自己填过底了，别闪
            return 1
        if msg == 0x0010:                      # WM_CLOSE
            u.DestroyWindow(hwnd)
            return 0
        if msg == 0x0002:                      # WM_DESTROY
            u.KillTimer(hwnd, 1)
            u.PostQuitMessage(0)
            return 0
        return u.DefWindowProcW(hwnd, msg, wp, lp)

    proc = WNDPROC(wndproc)
    api["proc"] = proc                         # 保住引用，否则回调被 GC 掉会直接崩

    try:
        hinst = k.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.style = 3                           # CS_HREDRAW | CS_VREDRAW
        wc.lpfnWndProc = proc
        wc.hInstance = hinst
        wc.lpszClassName = "SncSplashWnd"
        u.RegisterClassW(ctypes.byref(wc))

        sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
        hwnd = u.CreateWindowExW(0x00000008 | 0x00000080,   # TOPMOST | TOOLWINDOW
                                 "SncSplashWnd", APP_NAME + " · 启动中", 0x80000000,  # WS_POPUP
                                 int((sw - win_w) / 2),
                                 int((sh - win_h) / 2) - 20,
                                 win_w, win_h, None, None, hinst, None)
        if not hwnd:
            ready.set()
            return
        _SPLASH["hwnd"] = hwnd
        try:
            r = int(12 * scale)
            rgn = g.CreateRoundRectRgn(0, 0, win_w + 1, win_h + 1, r * 2, r * 2)
            if rgn:
                u.SetWindowRgn(hwnd, rgn, True)   # 成功后 region 归系统管，不要删
        except Exception:
            pass
        st["t0"] = time.perf_counter()
        u.ShowWindow(hwnd, 4)                   # SW_SHOWNOACTIVATE，不抢焦点
        u.UpdateWindow(hwnd)
        if use_video:
            u.SetTimer(hwnd, 1, 16, None)       # 16ms 一跳，靠媒体时钟决定贴第几帧
        else:
            u.SetTimer(hwnd, 1, 40, None)
        ready.set()

        def watchdog():
            """45 秒还没关就自己走 —— 万一 WebView 卡死，别留一块框挡住整个屏幕。"""
            for _ in range(45):
                time.sleep(1.0)
                if not _SPLASH.get("hwnd"):
                    return
            h = _SPLASH.get("hwnd")
            if h:
                u.PostMessageW(h, 0x0010, 0, 0)

        threading.Thread(target=watchdog, daemon=True, name="splash-wd").start()

        msg = wt.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u.TranslateMessage(ctypes.byref(msg))
            u.DispatchMessageW(ctypes.byref(msg))
    except Exception as exc:
        log("splash crashed: %s" % exc)
        ready.set()
    finally:
        _SPLASH["hwnd"] = 0
        try:
            if hdc_mem:
                g.DeleteDC(hdc_mem)
            if hbmp:
                g.DeleteObject(hbmp)
        except Exception:
            pass
        if hicon and uico:
            try:
                uico.DestroyIcon(hicon)
            except Exception:
                pass
        for f in fonts.values():
            try:
                g.DeleteObject(f)
            except Exception:
                pass
        try:
            g.DeleteObject(pen_gold)
        except Exception:
            pass


def splash_show(version: str = "") -> bool:
    """开启动画面，返回是否真的画出来了。失败不影响主流程。"""
    if _SPLASH.get("hwnd"):
        return True
    if os.name != "nt":
        return False
    ver = version or APP_VERSION
    ready = threading.Event()
    threading.Thread(target=_splash_thread, args=(ver, ready), daemon=True,
                     name="splash").start()
    ready.wait(1.2)                            # 等第一帧真的贴到屏幕上再往下走
    return bool(_SPLASH.get("hwnd"))


def splash_text(msg: str) -> None:
    """换一行状态文字（下一帧生效，不跨线程碰窗口）。"""
    _SPLASH["msg"] = msg
    hwnd = _SPLASH.get("hwnd")
    if hwnd:
        try:
            _GDI["u"].InvalidateRect(hwnd, None, False)
        except Exception:
            pass


def splash_close() -> None:
    """关掉启动画面。可以重复调用。"""
    hwnd = _SPLASH.get("hwnd") or 0
    _SPLASH["hwnd"] = 0
    _SPLASH["msg"] = ""
    if not hwnd:
        return
    try:
        _GDI["u"].PostMessageW(hwnd, 0x0010, 0, 0)     # WM_CLOSE
    except Exception:
        pass




def _notice(text: str, title: str = "") -> None:
    """一个朴素的信息框。只在"第二次双击"这种场景用，别处不要弹。"""
    if os.name != "nt" or os.environ.get("SNC_NO_MSG"):
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title or APP_NAME, 0x40)
    except Exception:
        pass


def _focus_existing_window() -> bool:
    """把已经在跑的那个窗口提到最前面（找不到返回 False）。

    这里**不能**用 webbrowser.open 兜底：系统浏览器和 WebView2 用的是两套
    profile，同一个地址进去看到的是另一份 IndexedDB —— 用户会以为画布没了。
    找不到窗口就老实说"请从任务栏/托盘打开"。
    """
    if os.name != "nt":
        return False
    try:
        import ctypes
        u = ctypes.windll.user32
        hwnd = u.FindWindowW(None, APP_NAME)
        if not hwnd:
            found = []

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def _enum(h, _l):
                buf = ctypes.create_unicode_buffer(256)
                u.GetWindowTextW(h, buf, 256)
                if buf.value and APP_NAME in buf.value:
                    found.append(h)
                    return False
                return True

            u.EnumWindows(_enum, 0)
            hwnd = found[0] if found else 0
        if not hwnd:
            return False
        if u.IsIconic(hwnd):
            u.ShowWindow(hwnd, 9)          # SW_RESTORE
        u.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def _decl_user32(user32=None, shell32=None, kernel32=None):
    """给用到的 Win32 函数声明签名。

    ctypes 不声明 argtypes 时一律按 32 位 int 传参：hInstance 这种 64 位值会直接
    "OverflowError: int too long to convert"；不声明 restype 则句柄被截成 32 位，
    托盘窗口/图标句柄都是坏的。设置一次即可，进程内所有调用方共享。
    """
    global _U32_READY
    if _U32_READY:
        return
    import ctypes
    from ctypes import wintypes as wt

    user32 = user32 or ctypes.windll.user32
    shell32 = shell32 or ctypes.windll.shell32
    kernel32 = kernel32 or ctypes.windll.kernel32

    user32.CreateWindowExW.argtypes = [
        wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
    user32.CreateWindowExW.restype = wt.HWND
    user32.RegisterClassExW.argtypes = [ctypes.c_void_p]
    user32.RegisterClassExW.restype = wt.WORD
    user32.GetClassInfoExW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, ctypes.c_void_p]
    user32.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT,
                                  ctypes.c_int, ctypes.c_int, wt.UINT]
    user32.LoadImageW.restype = wt.HANDLE
    user32.LoadIconW.argtypes = [wt.HINSTANCE, ctypes.c_void_p]
    user32.LoadIconW.restype = wt.HANDLE
    user32.CreatePopupMenu.argtypes = []
    user32.CreatePopupMenu.restype = wt.HMENU
    user32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR]
    user32.AppendMenuW.restype = wt.BOOL
    user32.TrackPopupMenu.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, wt.HWND, ctypes.c_void_p]
    user32.TrackPopupMenu.restype = ctypes.c_int
    user32.DestroyMenu.argtypes = [wt.HMENU]
    user32.SetForegroundWindow.argtypes = [wt.HWND]
    user32.SetForegroundWindow.restype = wt.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wt.HWND
    user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    user32.GetWindowThreadProcessId.restype = wt.DWORD
    user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
    user32.AttachThreadInput.restype = wt.BOOL
    kernel32.GetCurrentThreadId.argtypes = []
    kernel32.GetCurrentThreadId.restype = wt.DWORD
    user32.BringWindowToTop.argtypes = [wt.HWND]
    user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
    user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    user32.DefWindowProcW.restype = ctypes.c_ssize_t
    user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
    user32.GetMessageW.restype = ctypes.c_int
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
    user32.IsZoomed.argtypes = [wt.HWND]
    user32.IsZoomed.restype = wt.BOOL

    shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.c_void_p]
    shell32.Shell_NotifyIconW.restype = wt.BOOL

    kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wt.HINSTANCE
    _U32_READY = True


class TrayIcon:
    """系统托盘图标：点 × 收进托盘，右键托盘图标才能真正退出。
    pywebview 没有托盘能力，这里直接用 Shell_NotifyIconW 搭一个。
    单独开线程 + 独立 message-only 窗口，是因为主窗口的消息循环在 WinForms 手里，
    插不进自己的 WndProc；独立窗口类 + 自己的 GetMessage 循环互不干扰。
    """

    WM_TRAY = 0x8000 + 1          # WM_APP + 1，托盘回调都用它
    ID_SHOW = 1001
    ID_SAVE = 1002
    ID_SAVE_EXIT = 1003
    ID_EXIT = 1004

    def __init__(self, tooltip: str, on_show, on_exit,
                 on_save=None, on_save_exit=None):
        self._tooltip = tooltip
        self._on_show = on_show
        self._on_exit = on_exit
        self._on_save = on_save
        self._on_save_exit = on_save_exit
        self._hwnd = 0
        self._hicon = 0
        self._ok = False
        self._wndproc_ref = None      # 回调必须留引用，否则被 GC 后消息循环会崩
        self._nid = None
        self._nid_cls = None
        self._user32 = None
        self._shell32 = None

    # ------------------------------------------------ 对外
    def start(self, timeout: float = 4.0) -> bool:
        """把托盘建起来并等它出结果；失败返回 False，调用方就别隐藏窗口了。"""
        ready = threading.Event()
        threading.Thread(target=self._run, args=(ready,), daemon=True).start()
        ready.wait(timeout)
        return self._ok

    def alive(self) -> bool:
        return bool(self._ok and self._hwnd)

    def balloon(self, title: str, text: str):
        """弹一次气泡。藏在托盘之后不吭一声，用户会以为程序被关了。"""
        if not self._nid or not self._shell32 or not self._nid_cls:
            return
        try:
            import ctypes
            nid = self._nid_cls()
            nid.cbSize = ctypes.sizeof(self._nid_cls)
            nid.hWnd = self._hwnd
            nid.uID = 1
            nid.uFlags = 0x10                      # NIF_INFO
            nid.szInfo = text[:250]
            nid.szInfoTitle = title[:60]
            nid.dwInfoFlags = 0x1                  # NIIF_INFO
            self._shell32.Shell_NotifyIconW(1, ctypes.byref(nid))   # NIM_MODIFY
        except Exception as exc:
            log("tray balloon failed: %r" % exc)

    # ------------------------------------------------ 内部
    def _run(self, ready):
        try:
            self._ok = self._setup()
        except Exception as exc:
            log("tray setup failed: %r" % exc)
            self._ok = False
        ready.set()
        if not self._ok:
            return
        try:
            self._pump()
        except Exception as exc:
            log("tray loop exited: %r" % exc)
        finally:
            self._remove_icon()

    def _setup(self) -> bool:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32
        kernel32 = ctypes.windll.kernel32
        _decl_user32(user32, shell32, kernel32)
        self._user32, self._shell32 = user32, shell32

        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                     wintypes.WPARAM, wintypes.LPARAM)

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT),
                        ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                        ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                        ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                        ("hbrBackground", wintypes.HBRUSH),
                        ("lpszMenuName", wintypes.LPCWSTR),
                        ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD), ("Data4", ctypes.c_byte * 8)]

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                        ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                        ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                        ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD),
                        ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
                        ("uVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
                        ("dwInfoFlags", wintypes.DWORD), ("guidItem", GUID),
                        ("hBalloonIcon", wintypes.HICON)]

        self._header_cls = (WNDCLASSEXW, NOTIFYICONDATAW, GUID)
        self._nid_cls = NOTIFYICONDATAW

        def wndproc(hwnd, msg, wparam, lparam):
            try:
                if msg == self.WM_TRAY:
                    ev = lparam & 0xFFFF
                    if ev in (0x0202, 0x0203):         # WM_LBUTTONUP / DBLCLK
                        self._fire(self._on_show)
                    elif ev == 0x0205:                 # WM_RBUTTONUP
                        self._popup_menu()
                    return 0
                if msg == 0x0002:                      # WM_DESTROY
                    user32.PostQuitMessage(0)
                    return 0
            except Exception as exc:
                log("tray wndproc error: %r" % exc)
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc_ref = WNDPROC(wndproc)
        hinst = kernel32.GetModuleHandleW(None)
        cls_name = "SncTrayWnd"
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = hinst
        wc.lpszClassName = cls_name
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            # 类已注册（重复启动）也算可用
            if not user32.GetClassInfoExW(hinst, cls_name, ctypes.byref(wc)):
                log("RegisterClassEx failed: %s" % ctypes.get_last_error())
                return False

        # 必须是普通顶层窗口（WS_POPUP + 挪到屏幕外且不 ShowWindow），
        # 不能用 HWND_MESSAGE：message-only 窗口当不了前台窗口，
        # TrackPopupMenu 弹出来的菜单会立刻被系统收掉。
        self._hwnd = user32.CreateWindowExW(
            0x00000080,                       # WS_EX_TOOLWINDOW：不出现在任务栏/Alt+Tab
            cls_name, self._tooltip,
            0x80000000,                       # WS_POPUP
            -32000, -32000, 0, 0,
            None, None, hinst, None)
        if not self._hwnd:
            log("CreateWindowEx for tray failed")
            return False

        icon = 0
        ico_file = _icon_path()
        if ico_file:
            # IMAGE_ICON | LR_LOADFROMFILE | LR_DEFAULTSIZE：直接吃 app.ico，
            # 不依赖 exe 资源。开发时跑 python server.py 才会是应用图标而不是蟒蛇。
            icon = user32.LoadImageW(None, ico_file, 1, 0, 0, 0x0010 | 0x0040)
            if not icon:
                log("LoadImage(app.ico) failed, falling back to exe icon")
        if not icon:
            icon = user32.LoadIconW(hinst, 1)          # exe 的第一个图标资源
        if not icon:
            icon = user32.LoadIconW(None, 32512)       # IDI_APPLICATION 兜底
        self._hicon = icon

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = 0x01 | 0x02 | 0x04                # MESSAGE | ICON | TIP
        nid.uCallbackMessage = self.WM_TRAY
        nid.hIcon = self._hicon
        nid.szTip = self._tooltip[:120]
        if not shell32.Shell_NotifyIconW(0, ctypes.byref(nid)):   # NIM_ADD
            log("Shell_NotifyIcon(NIM_ADD) failed")
            return False
        self._nid = nid
        log("tray icon ready (hwnd=%s)" % hex(self._hwnd))
        return True

    def _build_menu(self):
        """托盘右键菜单：显示主窗口 / 保存 / 退出▸（保存并退出、直接退出）。

        「退出」挂成子菜单而不是点一下就退：托盘图标太小，误点一次就丢窗口太狠，
        二级菜单把那句话讲明白。没有保存回调时（老调用方）退回只有「退出」的样子。
        """
        user32 = self._user32
        hmenu = user32.CreatePopupMenu()
        if not hmenu:
            log("tray menu: CreatePopupMenu failed")
            return 0
        user32.AppendMenuW(hmenu, 0x0000, self.ID_SHOW, "显示主窗口")
        user32.AppendMenuW(hmenu, 0x0800, 0, None)               # MF_SEPARATOR
        if self._on_save:
            user32.AppendMenuW(hmenu, 0x0000, self.ID_SAVE, "保存")
        hsub = user32.CreatePopupMenu()
        if hsub:
            if self._on_save_exit:
                user32.AppendMenuW(hsub, 0x0000, self.ID_SAVE_EXIT, "保存并退出")
            user32.AppendMenuW(hsub, 0x0000, self.ID_EXIT, "直接退出")
            user32.AppendMenuW(hmenu, 0x00000010, hsub, "退出")   # MF_POPUP
        else:
            user32.AppendMenuW(hmenu, 0x0000, self.ID_EXIT, "退出")
        return hmenu

    def _popup_menu(self):
        import ctypes
        from ctypes import wintypes
        user32 = self._user32
        kernel32 = ctypes.windll.kernel32
        hmenu = self._build_menu()
        if not hmenu:
            return
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))

        # 菜单能不能留住取决于 owner 是不是"前台"。
        # 托盘窗口平时是隐藏的，SetForegroundWindow 会被系统拒绝，
        # 于是先 AttachThreadInput 借前台线程的输入状态再抢，抢完立刻解绑。
        fg = user32.GetForegroundWindow()
        tid_fg = user32.GetWindowThreadProcessId(fg, None)
        tid_me = kernel32.GetCurrentThreadId()
        attached = False
        try:
            if tid_fg and tid_fg != tid_me:
                attached = bool(user32.AttachThreadInput(tid_me, tid_fg, True))
            user32.SetForegroundWindow(self._hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(tid_me, tid_fg, False)

        cmd = user32.TrackPopupMenu(hmenu, 0x0100 | 0x0002, pt.x, pt.y, 0, self._hwnd, None)
        user32.PostMessageW(self._hwnd, 0, 0, 0)
        user32.DestroyMenu(hmenu)
        log("tray menu returned %s at %s,%s" % (cmd, pt.x, pt.y))
        self._handle(cmd)

    def _handle(self, cmd):
        """菜单命令分发。单拎出来是为了能脱开弹窗直接测。"""
        if cmd == self.ID_SHOW:
            self._fire(self._on_show)
        elif cmd == self.ID_SAVE and self._on_save:
            self._fire(self._on_save)
        elif cmd == self.ID_SAVE_EXIT and self._on_save_exit:
            self._remove_icon()
            self._fire(self._on_save_exit)
        elif cmd == self.ID_EXIT:
            self._remove_icon()
            self._fire(self._on_exit)

    def _fire(self, fn):
        try:
            fn()
        except Exception as exc:
            log("tray callback failed: %r" % exc)

    def _pump(self):
        import ctypes
        from ctypes import wintypes
        user32 = self._user32
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _remove_icon(self):
        if not self._nid or not self._shell32:
            return
        try:
            self._shell32.Shell_NotifyIconW(2, ctypes.byref(self._nid))   # NIM_DELETE
        except Exception:
            pass
        self._nid = None

    def stop(self):
        """从外部收掉托盘（正常退出时调用）。"""
        try:
            if self._hwnd:
                self._user32.PostMessageW(self._hwnd, 0x0002, 0, 0)       # WM_DESTROY
        except Exception:
            pass


class WindowApi:
    """页面调用 window.pywebview.api.xxx()。浏览器模式下这个对象不存在，前端自动降级。

    注意：pywebview 会把 js_api 对象的**所有公开属性**递归遍历一遍暴露给 JS
    （util.get_functions）。所以窗口引用必须挂在下划线属性上——写成 self.window
    会把整个 WinForms 对象树拖进遍历，出现
    "window.native.AccessibilityObject.Bounds.Empty.Empty.Empty…: maximum recursion depth exceeded"
    这种刷屏报错，启动也会被拖慢。
    """

    def __init__(self):
        self._window = None
        self._tray = None

    # ---- 内部 ----
    def _hwnd(self) -> int:
        return _WIN.get("hwnd") or _native_hwnd(self._window)

    # ---- 给前端 ----
    def win_state(self):
        hwnd = self._hwnd()
        return {"ok": bool(hwnd),
                "frameless": bool(_WIN["frameless"]),
                "maximized": _is_zoomed(hwnd),
                "hwnd": hwnd,
                "tray": bool(self._tray and self._tray.alive())}

    def win_min(self):
        try:
            self._window.minimize()
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def win_max(self):
        """切换最大化 / 还原，返回切换后的状态。"""
        try:
            hwnd = self._hwnd()
            if _is_zoomed(hwnd):
                self._window.restore()
            else:
                self._window.maximize()
            return {"ok": True, "maximized": _is_zoomed(hwnd)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def win_hide(self):
        """点 × 只是收进托盘，服务继续在后台跑。

        没有托盘图标就绝不隐藏——否则窗口一没，用户既看不见也关不掉。
        这种情况下退回「关掉窗口」，跟以前一样。
        """
        if not (self._tray and self._tray.alive()):
            log("hide requested but tray unavailable; closing window instead")
            return self.win_quit()
        try:
            self._window.hide()
            log("window hidden to tray")
            self._tray.balloon(APP_NAME, "已收进托盘，右键托盘图标可以退出程序")
            return {"ok": True, "hidden": True}
        except Exception as exc:
            log("hide failed: %s" % exc)
            return {"ok": False, "error": str(exc)}

    def win_show(self):
        try:
            self._window.show()
            self._window.restore()
            _bring_to_front(self._hwnd())
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def win_quit(self):
        """真正退出：关窗口，main 里 webview.start() 返回后收掉服务与托盘。"""
        try:
            self._window.destroy()
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def tray_saved(self, ok=True):
        """页面写盘完成后回报一句，窗口藏在托盘里时用它弹系统气泡。

        页面 toast 在隐藏窗口里看不见，所以真正有信息量的是这个气泡。
        """
        tray = self._tray
        if tray and tray.alive():
            tray.balloon(APP_NAME,
                         "画布已保存到本机" if ok
                         else "保存失败：本机存储不可用，建议先导出画布")
        return {"ok": True}

    def app_quit(self):
        """前端确认保存完成后才调用的退出入口。

        托盘退出不再直接 destroy 窗口：先让页面弹「保存并退出 / 直接退出 / 取消」，
        等 IndexedDB 写盘 Promise 落地，前端再调这个方法来真正关窗。
        """
        log("app_quit after save confirmation")
        return self.win_quit()

    # 老名字留着，前端/测试里可能还引用
    def win_close(self):
        return self.win_quit()

    def win_drag(self, zone="move"):
        hwnd = self._hwnd()
        if not hwnd:
            return {"ok": False, "error": "no hwnd"}
        if zone != "move" and _is_zoomed(hwnd):
            return {"ok": False, "error": "maximized"}          # 最大化时不允许拉伸
        # 主路径：轮询光标自己挪窗口（不依赖捕获/消息循环，WebView2 上也稳）
        ok = _track_window_drag(hwnd, zone)
        if not ok:
            ok = _begin_system_move(hwnd, zone)                 # 兜底：交回系统
        return {"ok": bool(ok), "zone": zone}


def run_native(url: str, auto_close: bool = False, wait_page: float = 25.0,
               frameless: bool = True) -> bool:
    """内嵌 WebView2 窗口。返回 False 表示这个模式没起来（调用方继续退让）。"""
    try:
        import webview
    except Exception as exc:
        log("pywebview unavailable: %s" % exc)
        return False

    store = os.path.join(data_dir(), "webview")
    try:
        os.makedirs(store, exist_ok=True)
    except OSError as exc:
        log("webview profile unavailable: %s" % exc)
        store = None

    api = WindowApi()
    base = dict(width=1440, height=920, min_size=(1024, 680),
                background_color="#0D0E10", text_select=True)
    if frameless:
        # 带上 shell=1，页面首帧就按无边框布局画，不会先跳一下再下移 32px
        url = url + ("&shell=1" if "?" in url else "?shell=1")
    try:
        if frameless:
            window = webview.create_window(
                APP_NAME, url, js_api=api,
                frameless=True, transparent=True, easy_drag=False, shadow=True, **base)
        else:
            window = webview.create_window(APP_NAME, url, **base)
    except Exception as exc:
        # 老版本 pywebview 不认这些参数，或透明窗口创建失败 → 老老实实用系统边框
        log("frameless window unavailable (%s), falling back to native frame" % exc)
        url = url.replace("?shell=1", "").replace("&shell=1", "")
        try:
            window = webview.create_window(APP_NAME, url, **base)
            frameless = False
        except Exception as exc2:
            log("create_window failed: %s" % exc2)
            return False

    api._window = window
    _WIN["frame"] = window
    _WIN["frameless"] = bool(frameless)

    def on_tray_show():
        log("show window from tray")
        try:
            window.show()
            window.restore()
        except Exception as exc:
            log("show from tray failed: %s" % exc)
        _bring_to_front(_WIN["hwnd"])

    def on_tray_exit():
        log("quit requested from tray")
        # 先交给前端：有未落盘的改动就弹保存确认，保存完成再调 api.app_quit()。
        # 页面还没加载好（钩子不存在）或桥断了才直接 destroy，避免点了没反应。
        try:
            ready = window.evaluate_js("!!window.__sncRequestQuit")
            if ready:
                window.evaluate_js("window.__sncRequestQuit()")
                return
            log("quit hook not ready, closing directly")
        except Exception as exc:
            log("quit hook failed: %r" % exc)
        try:
            window.destroy()
        except Exception:
            pass

    def on_tray_save():
        """托盘「保存」：交给页面写 IndexedDB，写完页面会回 api.tray_saved 弹气泡。"""
        log("save requested from tray")
        try:
            if window.evaluate_js("!!window.__sncTraySave"):
                window.evaluate_js("window.__sncTraySave()")
                return
            log("tray save: page hook not ready")
        except Exception as exc:
            log("tray save failed: %r" % exc)

    def on_tray_save_exit():
        """托盘「保存并退出」：先写盘，成功才关窗；失败就留在原地并提示。

        保存是异步的，所以这里只负责把请求交给页面，真正 destroy 由页面
        await 完 IndexedDB 之后调 api.app_quit()。
        """
        log("save-and-quit requested from tray")
        try:
            if window.evaluate_js("!!window.__sncTraySaveQuit"):
                window.evaluate_js("window.__sncTraySaveQuit()")
                return
            log("tray save-quit: page hook not ready, closing directly")
        except Exception as exc:
            log("tray save-quit failed: %r" % exc)
        try:
            window.destroy()
        except Exception:
            pass

    def on_loaded():
        # 页面第一帧到了，启动画面的使命结束 —— 立刻让位给真窗口
        splash_close()
        _WIN["hwnd"] = _native_hwnd(window)
        log("window loaded: frameless=%s hwnd=%s" % (_WIN["frameless"],
                                                     hex(_WIN["hwnd"]) if _WIN["hwnd"] else "?"))
        # 无边框窗口的圆角只能自己裁（Win10 没有 DWM 圆角偏好）
        if _WIN["frameless"] and _WIN["hwnd"]:
            _start_region_watcher(_WIN["hwnd"])
        try:
            if not _WIN["frameless"]:
                # 退回系统边框时把 URL 里带来的 shell 样式摘掉，否则会出现两条标题栏
                window.evaluate_js("document.documentElement.classList.remove('snc-shell')")
            window.evaluate_js("window.SNC_WIN_READY && window.SNC_WIN_READY()")
        except Exception:
            pass

        # 托盘：点 × 收起来之后得有地方把它叫回来。self-test 不建，免得测试留图标。
        if not auto_close:
            def setup_tray():
                try:
                    tray = TrayIcon(APP_NAME, on_tray_show, on_tray_exit,
                                    on_save=on_tray_save,
                                    on_save_exit=on_tray_save_exit)
                    if tray.start(4.0):
                        api._tray = tray
                        _WIN["tray"] = tray
                        try:
                            window.evaluate_js(
                                "window.SNC_TRAY_READY && window.SNC_TRAY_READY()")
                        except Exception:
                            pass
                except Exception as exc:
                    log("tray unavailable: %s" % exc)
            threading.Thread(target=setup_tray, daemon=True).start()

        # 排查用：SNC_DEBUG_JS="document.querySelector('[data-win=max]').click()"
        # 等桥注入完再执行，避免 window.pywebview 还不存在
        dbg = (os.environ.get("SNC_DEBUG_JS") or "").strip()
        if dbg:
            def run_debug_js():
                time.sleep(1.5)
                try:
                    log("debug js => %r" % (window.evaluate_js(dbg),))
                except Exception as exc:
                    log("debug js failed: %s" % exc)
            threading.Thread(target=run_debug_js, daemon=True).start()

    try:
        window.events.loaded += on_loaded
    except Exception:
        pass

    def watchdog():
        deadline = time.time() + wait_page
        while time.time() < deadline:
            if LAST_PAGE_PING:
                return
            time.sleep(0.4)
        log("native window never requested the page; closing it")
        try:
            window.destroy()
        except Exception:
            pass

    threading.Thread(target=watchdog, daemon=True).start()

    if auto_close:
        def closer():
            deadline = time.time() + wait_page
            while time.time() < deadline and not LAST_PAGE_PING:
                time.sleep(0.2)
            time.sleep(1.0)
            try:
                window.destroy()
            except Exception:
                pass

        threading.Thread(target=closer, daemon=True).start()

    # 窗口 / 任务栏图标统一用 app.ico，跟打包进 exe 的是同一张图
    ico = _icon_path() or None
    try:
        if store:
            webview.start(gui="edgechromium", storage_path=store, private_mode=False, icon=ico)
        else:
            webview.start(gui="edgechromium", icon=ico)
    except Exception as exc:
        log("webview.start failed: %s" % exc)
        return False
    finally:
        # 窗口已经没了还挂着 loaded 回调，pywebview 的 events 线程会在销毁后
        # 再调一次 evaluate_js，抛出 InvalidAsynchronousStateException（偶发，退出码异常）。
        try:
            window.events.loaded -= on_loaded
        except Exception:
            pass

    tray = _WIN.get("tray")
    if tray:
        tray.stop()
    return bool(LAST_PAGE_PING)


def _edge_exe():
    roots = (
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("PROGRAMFILES"),
        os.environ.get("LOCALAPPDATA"),
    )
    for root in roots:
        if not root:
            continue
        candidate = os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe")
        if os.path.exists(candidate):
            return candidate
    return None


def _edge_window_visible(needle: str) -> bool:
    """Edge 关窗后常驻后台进程，等 proc.wait() 会永远卡住，所以要盯窗口本身。"""
    try:
        import ctypes
        from ctypes import wintypes

        found = []
        user32 = ctypes.windll.user32
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, lparam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if needle in buf.value:
                    found.append(hwnd)
                    return False
            except Exception:
                pass
            return True

        user32.EnumWindows(enum_proc(cb), 0)
        return bool(found)
    except Exception as exc:
        log("edge window probe failed: %s" % exc)
        return True


def run_edge_app(url: str) -> bool:
    """无标签栏、无地址栏的 Edge 应用窗口。内嵌窗口不可用时的第一退路。"""
    exe = _edge_exe()
    if not exe:
        log("edge not found; cannot use app mode")
        return False

    profile = os.path.join(data_dir(), "edge-profile")
    try:
        os.makedirs(profile, exist_ok=True)
    except OSError:
        profile = data_dir()

    args = [
        exe,
        "--app=" + url,
        "--window-size=1440,920",
        "--user-data-dir=" + profile,
        "--no-first-run",
        "--no-default-browser-check",
    ]
    try:
        proc = subprocess.Popen(args)
    except OSError as exc:
        log("edge app failed: %s" % exc)
        return False

    log("edge app window opened (pid %d)" % proc.pid)

    deadline = time.time() + 20
    while time.time() < deadline and not LAST_PAGE_PING:
        time.sleep(0.3)
    if not LAST_PAGE_PING:
        log("edge app window never appeared")
        try:
            proc.terminate()
        except Exception:
            pass
        return False

    # 页面起来了，就盯窗口可见性等用户关窗
    while _edge_window_visible("无限画布") or _edge_window_visible("SenseNova"):
        time.sleep(0.8)

    log("edge app window closed")
    try:
        proc.terminate()
    except Exception:
        pass
    return True


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--port", type=int, default=8000, help="首选端口，被占用时自动换")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--window", choices=["native", "app", "browser"], default="native",
                        help="native = 内嵌窗口 / app = 无边框 Edge / browser = 默认浏览器")
    parser.add_argument("--open", action="store_true", help="用默认浏览器打开")
    parser.add_argument("--no-open", action="store_true", help="不自动打开窗口")
    parser.add_argument("--classic-window", action="store_true",
                        help="用系统原生边框开窗（无边框在某些远程桌面/老显卡下会闪黑时的退路）")
    parser.add_argument("--self-test", action="store_true", help="起窗即关，验证链路")
    args = parser.parse_args(argv)

    # 最先做的一件事：让屏幕上有反应。后面读配置、起服务、等 WebView 都在这块框后面进行。
    splash_show()

    global NATIVE_DIALOG
    NATIVE_DIALOG = not _SAVE_DIALOG_DISABLED

    # v3.0：老版本的单把密钥搬到多密钥槽位，别让老用户升级后变成"未配置"
    try:
        migrate_legacy_keys()
    except Exception as exc:      # 迁移失败不影响启动，页面里还能重新填
        log("migrate legacy keys failed: %s" % exc)

    env = env_map()
    key, model = load_env()
    ready = [pid for pid in PROVIDER_ORDER if load_keys(pid, env)]
    # v3.8.1：端口就是存档的 origin（WebView2 的 IndexedDB 按 origin 隔离）。
    # 同一个端口上已经是本程序 → 上次那个窗口还开着，这次再起一个必然换端口，
    # 换完就是一份空白画布，用户当场以为"我的画布全没了"。这里直接复用它。
    if not args.self_test:
        running = _probe_instance(args.port, args.host)
        if running:
            log("instance already running on port %d (v%s), reuse it" % (args.port, running))
            splash_close()
            if _focus_existing_window():
                _notice("无限画布已经在运行（v%s），已切回那个窗口。\n\n"
                        "画布存档与端口绑定：再开一个窗口会得到一份空白画布，"
                        "所以这里只复用已经开着的那个。" % running)
            else:
                _notice("无限画布已经在运行（v%s）。\n\n"
                        "请从任务栏或右下角托盘图标把它调出来。\n\n"
                        "（程序不会另开新窗口：新窗口会换端口，等于换一份空白画布。）" % running)
            return 0

    port = free_port(args.port)
    PORT_INFO["want"] = args.port
    PORT_INFO["got"] = port
    if port != args.port:
        # 只有 8000 被别的程序占着才会走到这里。存档按 origin 隔离，换端口
        # 用户就会看到一份空画布，所以这件事必须留痕（页面也会提示）。
        log("#port drifted: wanted %d, got %d (old boards stay on %d)"
            % (args.port, port, args.port))
    server = BridgeServer((args.host, port), Handler)
    url = "http://127.0.0.1:%d/canvas.html" % port

    log("=" * 54)
    log("%s   port=%d  window=%s" % (APP_NAME, port, "self-test" if args.self_test else args.window))
    log("配置 %s（%s）" % (env_path(),
                          ("已配置：" + " / ".join(ready)) if ready else "尚未填写密钥"))
    log("服务 %s" % url)
    log("=" * 54)

    threading.Thread(target=server.serve_forever, daemon=True).start()
    splash_text("正在启动渲染内核…")

    if args.self_test:
        ok = run_native(url, auto_close=True, frameless=not args.classic_window)
        splash_close()
        log("self-test native window: %s" % ("OK" if ok else "FAILED"))
        server.shutdown()
        return 0 if ok else 1

    if args.window == "browser" or args.open:
        webbrowser.open(url)
        splash_close()                       # 浏览器已经接管，启动画面没意义了
        log("window mode: browser")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    elif args.window == "app":
        if run_edge_app(url):
            splash_close()
            log("window mode: app")
        else:
            log("#falling back to the default browser")
            webbrowser.open(url)
            splash_close()
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                pass
    else:
        log("window mode: native")
        if not run_native(url, frameless=not args.classic_window):
            if not run_edge_app(url):
                log("#falling back to the default browser")
                webbrowser.open(url)
                splash_close()
                try:
                    while True:
                        time.sleep(3600)
                except KeyboardInterrupt:
                    pass
        splash_close()

    server.shutdown()
    log("window closed, service stopped")
    return 0


if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        redirect_streams()
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        log("fatal: %r" % exc)
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, str(exc), APP_NAME, 0x10)
        except Exception:
            pass
        raise