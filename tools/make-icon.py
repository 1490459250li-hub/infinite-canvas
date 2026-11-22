# -*- coding: utf-8 -*-
"""重做 app.ico：把原图（RGB、四角纯白）的圆角外部挖成透明，并补齐多尺寸。

背景：原来的 app.ico 只有一条 256x256、颜色类型 2（RGB，无 alpha）。
四角是实打实的 (255,255,255)，任务栏缩到 32px 时就是一圈白边。
这里从四角做 flood fill 去掉外部白底，再把透明区的 RGB 刷成主色，
避免缩小时半透明像素和白背景平均出白晕。

用法：python tools/make-icon.py [源png] [输出ico]
"""
import struct
import sys
import zlib
from collections import deque

SRC = sys.argv[1] if len(sys.argv) > 1 else "tests/.ico_src.png"
OUT = sys.argv[2] if len(sys.argv) > 2 else "proto/app.ico"
SIZES = [256, 128, 64, 48, 32, 24, 16]
# 缩小时透明区的 RGB 会参与平均，刷成主色才不会在边上泛白
FILL = (228, 104, 62)


def load_png(path):
    """读 PNG（8 位，颜色类型 0/2/3/4/6），返回 RGBA。"""
    d = open(path, "rb").read()
    pos, idat = 8, b""
    w = h = bit = ct = None
    palette = b""
    while pos < len(d):
        ln = struct.unpack(">I", d[pos:pos + 4])[0]
        typ = d[pos + 4:pos + 8]
        data = d[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, bit, ct = struct.unpack(">IIBB", data[:10])
        elif typ == b"PLTE":
            palette = data
        elif typ == b"IDAT":
            idat += data
        pos += 12 + ln
    assert bit == 8, "只支持 8 位 PNG，实际 %s" % bit
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    stride = w * ch
    raw = zlib.decompress(idat)
    lines = []
    prev = bytearray(stride)
    i = 0
    for _y in range(h):
        f = raw[i]
        i += 1
        line = bytearray(raw[i:i + stride])
        i += stride
        if f == 1:
            for x in range(ch, stride):
                line[x] = (line[x] + line[x - ch]) & 255
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                a = line[x - ch] if x >= ch else 0
                line[x] = (line[x] + ((a + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x - ch] if x >= ch else 0
                b = prev[x]
                c = prev[x - ch] if x >= ch else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pr) & 255
        lines.append(bytes(line))
        prev = line

    out = bytearray(w * h * 4)
    for y in range(h):
        line = lines[y]
        for x in range(w):
            o = (y * w + x) * 4
            if ct == 6:
                out[o:o + 4] = line[x * 4:x * 4 + 4]
            elif ct == 2:
                out[o:o + 3] = line[x * 3:x * 3 + 3]
                out[o + 3] = 255
            elif ct == 0:
                v = line[x]
                out[o] = out[o + 1] = out[o + 2] = v
                out[o + 3] = 255
            elif ct == 4:
                out[o] = out[o + 1] = out[o + 2] = line[x * 2]
                out[o + 3] = line[x * 2 + 1]
            elif ct == 3:
                k = line[x] * 3
                out[o:o + 3] = palette[k:k + 3]
                out[o + 3] = 255
    return w, h, out


def knock_out_white(w, h, px):
    """从四个角把连通的白底挖成透明，返回新的 RGBA。"""
    out = bytearray(px)
    seen = bytearray(w * h)
    q = deque()
    for sx, sy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        q.append((sx, sy))
        seen[sy * w + sx] = 1

    cleared = 0
    while q:
        x, y = q.popleft()
        o = (y * w + x) * 4
        r, g, b, a = out[o], out[o + 1], out[o + 2], out[o + 3]
        # 只吃「接近白、且饱和度极低」的像素，橙色和白色卡片都不会被误伤
        if a > 40 and (min(r, g, b) < 205 or (max(r, g, b) - min(r, g, b)) > 26):
            continue
        out[o], out[o + 1], out[o + 2] = FILL
        out[o + 3] = 0
        cleared += 1
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx]:
                seen[ny * w + nx] = 1
                q.append((nx, ny))

    # 清完再把紧贴透明区的半透明边压一档：这一圈是「白 + 橙」的抗锯齿像素，
    # 留着会让 32px 下看起来还有一条浅边。
    for y in range(h):
        for x in range(w):
            o = (y * w + x) * 4
            if out[o + 3] == 0:
                continue
            edge = False
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < w and 0 <= ny < h and out[(ny * w + nx) * 4 + 3] == 0:
                    edge = True
                    break
            if edge:
                whiteness = min(out[o], out[o + 1], out[o + 2])
                if whiteness > 190:
                    k = max(0.0, min(1.0, (255 - whiteness) / 55.0))
                    out[o + 3] = int(255 * k)
                    if k > 0.05:
                        out[o] = int((out[o] - 255 * (1 - k)) / k)
                        out[o + 1] = int((out[o + 1] - 255 * (1 - k)) / k)
                        out[o + 2] = int((out[o + 2] - 255 * (1 - k)) / k)
                        out[o] = max(0, min(255, out[o]))
                        out[o + 1] = max(0, min(255, out[o + 1]))
                        out[o + 2] = max(0, min(255, out[o + 2]))
    return out, cleared


def resize(w, h, px, dw, dh):
    """面积平均（缩小用），alpha 与颜色分开处理，避免边缘发黑/发白。"""
    out = bytearray(dw * dh * 4)
    for y in range(dh):
        y0 = y * h // dh
        y1 = max(y0 + 1, (y + 1) * h // dh)
        for x in range(dw):
            x0 = x * w // dw
            x1 = max(x0 + 1, (x + 1) * w // dw)
            rs = gs = bs = asum = 0
            n = 0
            for yy in range(y0, y1):
                row = yy * w
                for xx in range(x0, x1):
                    o = (row + xx) * 4
                    a = px[o + 3]
                    # 预乘 alpha 后再平均，透明像素不会把颜色拉向白
                    rs += px[o] * a
                    gs += px[o + 1] * a
                    bs += px[o + 2] * a
                    asum += a
                    n += 1
            o = (y * dw + x) * 4
            if asum:
                out[o] = rs // asum
                out[o + 1] = gs // asum
                out[o + 2] = bs // asum
            out[o + 3] = asum // n
    return out


def encode_png(w, h, px):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += px[y * w * 4:(y + 1) * w * 4]

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data +
                struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def main():
    w, h, px = load_png(SRC)
    px, cleared = knock_out_white(w, h, px)
    print("源图 %dx%d，挖掉外部白底 %d 像素" % (w, h, cleared))

    entries = []
    for s in SIZES:
        data = px if s == w else resize(w, h, px, s, s)
        entries.append((s, encode_png(s, s, data)))

    head = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    dirc = b""
    blob = b""
    for s, png in entries:
        dirc += struct.pack("<BBBBHHII", 0 if s >= 256 else s, 0 if s >= 256 else s,
                            0, 0, 1, 32, len(png), offset)
        offset += len(png)
        blob += png
    open(OUT, "wb").write(head + dirc + blob)
    print("已写入 %s（%d 个尺寸：%s）" % (OUT, len(entries), ",".join(str(s) for s in SIZES)))


if __name__ == "__main__":
    main()
