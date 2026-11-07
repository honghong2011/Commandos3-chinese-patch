# -*- coding: utf-8 -*-
"""BFT 字体原语与重建器（从验证过的 v10 生成器提炼）。

成功路径（v10/v11 实测）：
  字形 = 6 字节头(引擎跳过) + 纯行程 RLE，每行严格 32 像素
  0x40|n = n 像素背景   0x80|n = n 像素笔画   n = byte&0x3F (1..63)
  行程不跨行；不用任何 literal 字节(0x00-0x3F)。
"""
import struct
from PIL import Image, ImageDraw, ImageFont

W, H = 32, 26
GHDR = struct.pack('<HHH', W, H, 0)
SIMSUN = r'C:\Windows\Fonts\simsun.ttc'


def raster(ch, font):
    """32x26 双色位图 -> [[0/1]*32]*26"""
    img = Image.new('L', (W, H), 0)
    ImageDraw.Draw(img).text((4, 1), ch, fill=255, font=font)
    px = img.load()
    return [[1 if px[x, y] >= 128 else 0 for x in range(W)] for y in range(H)]


def rle(rows):
    """纯行程编码；游程最长 32 < 64，必为单字节。"""
    out = bytearray()
    for row in rows:
        i = 0
        while i < W:
            v = row[i]
            j = i
            while j < W and row[j] == v:
                j += 1
            out.append((0x40 if v == 0 else 0x80) | (j - i))
            i = j
    return bytes(out)


def engine_decode(glyph):
    """按引擎 0x8fc5f0 行循环镜像解码，异常即抛错。"""
    stream = glyph[6:]
    pos = col = 0
    rows, cur = [], []
    while len(rows) < H:
        assert pos < len(stream), '流提前耗尽'
        b = stream[pos]
        pos += 1
        n = b & 0x3F
        assert 1 <= n <= 63 and (b & 0xC0) in (0x40, 0x80), \
            '非常规字节 %02x' % b
        cur.extend([0 if (b & 0xC0) == 0x40 else 1] * n)
        col += n
        assert col <= W, '行越界'
        if col == W:
            rows.append(cur)
            cur, col = [], 0
    assert pos == len(stream), '26 行后还有剩余字节'
    return rows


def build_bft(out_path, simsun=SIMSUN):
    """重建全量大字号 BFT（= build_bft_mode(out,'FULL')）。"""
    font = ImageFont.truetype(simsun, H - 2)
    codes = list(range(0x20, 0x7F))
    for lead in range(0x81, 0xFF):
        for trail in list(range(0x40, 0x7F)) + list(range(0x80, 0xFF)):
            codes.append((lead << 8) | trail)
    blank_rows = [[0] * W for _ in range(H)]
    bitmap = bytearray()
    table = {}
    for code in codes:
        ch = chr(code) if code < 0x100 else None
        if ch is None:
            try:
                ch = bytes([code >> 8, code & 0xFF]).decode('gbk')
            except UnicodeDecodeError:
                pass
        if ch is None:
            table[code] = None
            continue
        rows = raster(ch, font)
        assert engine_decode(GHDR + rle(rows)) == rows
        table[code] = len(bitmap)
        bitmap += GHDR + rle(rows)
    blank_off = len(bitmap)
    bitmap += GHDR + rle(blank_rows)
    for code in table:
        if table[code] is None:
            table[code] = blank_off
    out = struct.pack('<HHI', len(table), H, len(bitmap))
    for code in sorted(table):
        out += struct.pack('<HI', code, table[code])
    out += bytes(bitmap)
    with open(out_path, 'wb') as f:
        f.write(out)
    return out_path


def bft_table(bft_path):
    """读 BFT -> (bytes, {code: (offset, span)}, data_end, cell_height)。

    span 必须按【偏移顺序】的下一字形起点计算——按码位顺序会踩
    "共享空白格位于位图区末尾"的坑（未定义码散布全码位空间）。
    """
    d = open(bft_path, 'rb').read()
    count, ch, bsz = struct.unpack_from('<HHI', d, 0)
    tbl = {}
    for k in range(count):
        code, off = struct.unpack_from('<HI', d, 8 + 6 * k)
        tbl[code] = off
    data_end = 8 + 6 * count
    offs = sorted(set(tbl.values()))
    nxt = {o: (offs[i + 1] if i + 1 < len(offs) else bsz)
           for i, o in enumerate(offs)}
    return d, {c: (tbl[c], nxt[tbl[c]] - tbl[c]) for c in tbl}, data_end, ch


def glyph_rows(d, off, span):
    return engine_decode(d[off:off + span])


# ---------------- 尺寸模式（反汇编确认的机制） ----------------
# 引擎每字步进 = 字形首字节(0x8727a0 movzx eax,byte ptr [eax])；
# 每行固定解码 32 像素(0x8fc578 cmp eax,0x20)；行数 = 文件头 cellHeight。
# FULL  = v11 实测版：满格 32x26，步进 32。
# SMALL = 半尺寸：墨迹限左 16 列 x 中间 13 行，汉字步进 17，ASCII 比例步进。
MODES = {
    'FULL':  dict(hanzi_px=24, hanzi_win=32, hanzi_adv=32,
                  asc_px=24, asc_win=32, band_h=26, y0=0),
    'SMALL': dict(hanzi_px=12, hanzi_win=16, hanzi_adv=17,
                  asc_px=12, asc_win=9,  band_h=13, y0=6),
}


def expected_rows(ch, mode='FULL'):
    """按模式渲染字符 -> 26 行 x 32 列网格（第 1 字节步进由调用方取）。"""
    p = MODES[mode]
    if ord(ch) < 0x80:
        font = ImageFont.truetype(SIMSUN, p['asc_px'])
        img = Image.new('L', (p['asc_win'], p['band_h']), 0)
        ImageDraw.Draw(img).text((0, 0), ch, fill=255, font=font)
        px = img.load()
        adv = img.getbbox()[2] + 1 if img.getbbox() else 4
        adv = max(4, min(adv, 31))
    else:
        font = ImageFont.truetype(SIMSUN, p['hanzi_px'])
        img = Image.new('L', (p['hanzi_win'], p['band_h']), 0)
        ImageDraw.Draw(img).text((1, 0), ch, fill=255, font=font)
        px = img.load()
        adv = p['hanzi_adv']
    rows = []
    for y in range(26):
        gy = y - p['y0']
        row = []
        for x in range(32):
            if 0 <= gy < p['band_h'] and x < img.width:
                row.append(1 if px[x, gy] >= 128 else 0)
            else:
                row.append(0)
        rows.append(row)
    return rows, adv


def build_bft_mode(out_path, mode='SMALL'):
    """按尺寸模式重建全量 BFT。SMALL 模式字形墨迹减半、步进减半。"""
    codes = list(range(0x20, 0x7F))
    for lead in range(0x81, 0xFF):
        for trail in list(range(0x40, 0x7F)) + list(range(0x80, 0xFF)):
            codes.append((lead << 8) | trail)
    blank_rows = [[0] * W for _ in range(H)]
    bitmap = bytearray()
    table = {}
    for code in codes:
        ch = chr(code) if code < 0x100 else None
        if ch is None:
            try:
                ch = bytes([code >> 8, code & 0xFF]).decode('gbk')
            except UnicodeDecodeError:
                pass
        if ch is None:
            table[code] = None
            continue
        rows, adv = expected_rows(ch, mode)
        hdr = struct.pack('<HHH', adv, H, 0)
        assert engine_decode(hdr + rle(rows)) == rows
        table[code] = len(bitmap)
        bitmap += hdr + rle(rows)
    blank_off = len(bitmap)
    bitmap += struct.pack('<HHH', 17 if mode == 'SMALL' else 32, H, 0)         + rle(blank_rows)
    for code in table:
        if table[code] is None:
            table[code] = blank_off
    out = struct.pack('<HHI', len(table), H, len(bitmap))
    for code in sorted(table):
        out += struct.pack('<HI', code, table[code])
    out += bytes(bitmap)
    with open(out_path, 'wb') as f:
        f.write(out)
    return out_path
