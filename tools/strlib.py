# -*- coding: utf-8 -*-
"""STR 整文解析/等长替换原语（v12 全量汉化用）。

与 build_patch.py 的逐行法不同：这里用整文正则解析，支持
  * 值内跨行的真实换行（MANUALC3 实测存在）
  * 值内字面 \\n 转义序列（简报/手册排版用，必须原样保留）
  * KEY 与值之间 TAB 或空格
核心不变式：替换后总字符数逐字节不变（中文不足处尾部补空格），
因此 blob 长度、TOC、混淆密钥序列全部不动。
"""
import re

SEQ = [0x8, 0x9, 0xa, 0xb, 0xc, 0xd, 0xe, 0x0, 0x1, 0x2, 0x3, 0x4, 0x5, 0x6]

# 整文条目正则：行首 KEY + 空白 + 引号值（值可跨行，非贪婪到最近引号）
ENTRY_RE = re.compile(r'(?m)^([A-Za-z0-9_]+)[ \t]+"(.*?)"', re.S)


def derive_params(blob):
    key0 = blob[0] ^ 0xFF
    low = key0 & 0xF
    if low in (0x7, 0xF):
        raise ValueError('BOM key 低半字节 %x，定律失效' % low)
    return (key0 >> 4), SEQ.index(low)


def decode(blob):
    """blob -> (text, H0, p0)。BOM 已剥；(H0,p0) 是该文件的密钥旋转
    参数，再编码时必须原样传回（BOM 自身反推不出来！）。"""
    H0, p0 = derive_params(blob)
    out = bytearray(blob)
    n = len(out)
    for k in range((n + 15) // 16):
        p = 16 * k
        if p < n:
            out[p] ^= (((H0 + k) & 0xF) << 4) | SEQ[(p0 + k) % 14]
    return out[2:].decode('utf-16-le', 'surrogatepass'), H0, p0


def encode(text, H0, p0):
    """明文文本（不含 BOM）+ 原文件 (H0,p0) -> 混淆 blob。"""
    clean = b'\xff\xfe' + text.encode('utf-16-le', 'surrogatepass')
    out = bytearray(clean)
    n = len(out)
    for k in range((n + 15) // 16):
        p = 16 * k
        if p < n:
            out[p] ^= (((H0 + k) & 0xF) << 4) | SEQ[(p0 + k) % 14]
    return bytes(out)


def list_entries(text):
    """[(key, value, value_span)]，span 为值在整文中的字符区间。"""
    return [(m.group(1), m.group(2), m.span(2))
            for m in ENTRY_RE.finditer(text)]


def patch_text(text, repls, strict=True):
    """{key: 伪单元中文} 等长替换 -> (new_text, used_keys)。
    中文不足预算处尾部补空格；总长度不变是硬校验。"""
    entries = {k: (v, sp) for k, v, sp in list_entries(text)}
    used, spans = set(), []
    for key, zh in repls.items():
        if key not in entries:
            if strict:
                raise KeyError('%s 不在该 STR 中' % key)
            continue
        val, (a, b) = entries[key]
        if len(zh) > len(val):
            raise ValueError('%s: 中文 %d 单元 > 预算 %d'
                             % (key, len(zh), len(val)))
        spans.append((a, b, zh + ' ' * (len(val) - len(zh))))
        used.add(key)
    out, last = [], 0
    for a, b, zh in sorted(spans):
        out.append(text[last:a])
        out.append(zh)
        last = b
    out.append(text[last:])
    new_text = ''.join(out)
    assert len(new_text) == len(text), '长度漂移!'
    return new_text, used


def gbk_units(s):
    """显示用汉字串 -> 引擎伪单元串（GBK 码直接当 UTF-16 单元）。"""
    out = []
    for c in s:
        if ord(c) < 0x80:
            out.append(c)
        else:
            b = c.encode('gbk')      # 不在 GBK 内会抛错 —— 天然质检
            assert len(b) == 2
            out.append(chr((b[0] << 8) | b[1]))
    return ''.join(out)


def tokens(s):
    """提取 %Name / %d 类占位符，供替换前后比对。"""
    return re.findall(r'%[A-Za-z_][A-Za-z0-9_]*|%\d*[dsfxX]', s)


def blob_replacements(blob, spec_zh, strict=False):
    """对一个 STR blob 应用 {key: 显示用中文} -> 新 blob（含自校验）。

    strict=False：该包里不存在的 KEY 直接跳过
    （DATA.PCK 与 data3.pck 键集不完全相同，data3 是语言覆盖包）。
    """
    text, H0, p0 = decode(blob)
    repls = {k: gbk_units(v) for k, v in spec_zh.items()}
    new_text, used = patch_text(text, repls, strict=strict)
    new_blob = encode(new_text, H0, p0)
    assert len(new_blob) == len(blob)
    chk = {k: v for k, v, _ in list_entries(decode(new_blob)[0])}
    for key in used:
        zh = repls[key]
        assert chk[key].rstrip(' ') == zh, '%s 回读不一致' % key
    return new_blob, used
