# -*- coding: utf-8 -*-
"""成品构建器：workspace 工作文件里已填的中文 -> 可拖进游戏目录的完整补丁。

用法：
  python tools/build_final.py            # 输出到 build\\final
  python tools/build_final.py D:\\某目录  # 输出到指定目录

流程：
  1. 校验所有已填 zh（预算/GBK/占位符/禁引号换行）——未填的保持英文；
  2. 全部用字与 BFT 字体闭环比对（字形必须存在且正确）；
  3. 从 backup\\ 原版重建 DATA.PCK + data3.pck（FONT.CFG 语言开关 0->1）；
  4. 字体三件套从 assets\\Data\\FONTS 复制；
  5. 双包差异范围校验 + 成品回读逐条比对 + md5 清单 + 安装说明。
"""
import hashlib
import json
import os
import re
import shutil
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c3pck import PCK, deobf_abs
from strlib import blob_replacements, decode, list_entries, gbk_units, tokens
from fontlib import bft_table, glyph_rows

ROOT = os.environ.get('C3WORK') or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
WS = os.path.join(ROOT, 'translation', 'workspace')
ASSETS_FONTS = os.path.join(ROOT, 'assets', 'Data', 'FONTS')
BFT = os.path.join(ASSETS_FONTS, 'FONT_UNICODE.BFT')
FC_OFF, FC_SIZE = 0x3435000, 68


def validate_all(spec):
    errs = []
    for name, repls in spec.items():
        for key, zh in repls.items():
            if '"' in zh or '\t' in zh:
                errs.append('%s/%s: 含引号/制表符' % (name, key))
            try:
                gbk_units(zh)
            except Exception as e:
                errs.append('%s/%s: GBK 外字符 %s' % (name, key, e))
    return errs


def budgets_check(spec):
    """预算检查需要原文，从包里取。"""
    pck = PCK(os.path.join(ROOT, 'backup', 'DATA.PCK.original'))
    errs = []
    for name, repls in spec.items():
        if name not in pck.entries:
            continue
        text, _, _ = decode(pck.blob(name))
        cur = {k: v for k, v, _ in list_entries(text)}
        for key, zh in repls.items():
            if key not in cur:
                errs.append('%s/%s: KEY 不存在' % (name, key))
            elif len(zh) > len(cur[key]):
                errs.append('%s/%s: 超预算 %d > %d'
                            % (name, key, len(zh), len(cur[key])))
            elif Counter(tokens(cur[key])) != Counter(tokens(zh)):
                errs.append('%s/%s: 占位符不一致' % (name, key))
    return errs


def bft_check(spec):
    d, tbl, data_end, ch = bft_table(BFT)
    # 用 '主' 的步进字节识别字体模式：17=小字号(默认), 32=大字号
    off0, _ = tbl[0xD6F7]
    mode = 'SMALL' if d[data_end + off0] == 17 else 'FULL'
    from fontlib import expected_rows
    uniq = {}
    for repls in spec.values():
        for v in repls.values():
            for c in v:
                if ord(c) >= 0x80:
                    b = c.encode('gbk')
                    uniq[(b[0] << 8) | b[1]] = c
    for code, c in sorted(uniq.items()):
        if code not in tbl:
            raise AssertionError('%r GBK %04X 不在 BFT' % (c, code))
        off, span = tbl[code]
        want, _adv = expected_rows(c, mode)
        if glyph_rows(d, data_end + off, span) != want:
            raise AssertionError('%r 字形不符(模式%s)' % (c, mode))
    print('BFT 闭环(模式 %s): %d 个用字全部命中且字形一致' % (mode, len(uniq)))


def build_pack(src, dst, spec, flip_cfg):
    pck = PCK(src)
    reps = {}
    for name, repls in spec.items():
        if name not in pck.entries:
            continue
        new_blob, used = blob_replacements(pck.blob(name), repls)
        reps[name] = new_blob
        miss = set(repls) - used
        note = '' if not miss else '  (该包无 %d 键,跳过)' % len(miss)
        print('%s %-11s %3d 条%s' % (os.path.basename(dst), name,
                                     len(used), note))
    if flip_cfg:
        with open(src, 'rb') as f:
            f.seek(FC_OFF)
            fc = f.read(FC_SIZE)
        clean = deobf_abs(fc, FC_OFF)
        assert clean.startswith(b'[\r\n  .MENUPRINCIPALGRAFICO'), \
            'FONT.CFG 偏移失效'
        m = re.search(rb'\.IDIOMAORIENTAL\s+(\d)', clean)
        assert m and m.group(1) == b'0'
        reps['FONT.CFG'] = deobf_abs(
            clean[:m.start(1)] + b'1' + clean[m.end(1):], FC_OFF)
        pck.entries['FONT.CFG'] = (FC_SIZE, FC_OFF)
        print('%s FONT.CFG -> IDIOMAORIENTAL=1' % os.path.basename(dst))
    pck.splice_to(dst, reps)


def diff_check(src, dst, extra_ranges):
    with open(src, 'rb') as a, open(dst, 'rb') as b:
        o, n = a.read(), b.read()
    assert len(o) == len(n), '%s 包长变化' % dst
    pck = PCK(src)
    allowed = [(pck.entries[x][1], pck.entries[x][1] + pck.entries[x][0])
               for x in pck.entries] + list(extra_ranges)
    bad = [i for i in range(len(o))
           if o[i] != n[i] and not any(lo <= i < hi for lo, hi in allowed)]
    assert not bad, '范围外改动 @%08x' % bad[0]
    print('%s 差异范围检查通过' % os.path.basename(dst))


def readback(dst, spec):
    pck = PCK(dst)
    for name, repls in spec.items():
        if name not in pck.entries:
            continue
        text, _, _ = decode(pck.blob(name))
        cur = {k: v for k, v, _ in list_entries(text)}
        for key, zh in repls.items():
            if key not in cur:
                continue
            assert cur[key].rstrip(' ') == gbk_units(zh), \
                '%s/%s 回读不一致' % (name, key)
    print('%s 回读一致' % os.path.basename(dst))


README = '''盟军敢死队3 简体中文补丁（Steam 版专用）—— 安装
==================================================

适用：Steam 2016 版《Commandos 3: Destination Berlin》。
不替换 exe、不破解，直接覆盖资源文件。

【第 1 步】把本目录里的 DATA.PCK 和 data3.pck 拖进游戏根目录，覆盖：
    G:\\steam\\steamapps\\common\\Commandos 3 Destination Berlin\\
    （DATA.PCK 约 495MB；如本包缺失该文件，请到 GitHub Release 下载）

【第 2 步】把本目录里的 Data 文件夹整个拖进游戏根目录，
    问是否合并选"是"，问是否覆盖选"全部覆盖"。

【第 3 步】启动游戏。

还原原版：Steam 库中右键游戏 -> 属性 -> 已安装文件 -> 验证文件完整性，
    再删除游戏目录 Data\\FONTS\\ 里三个字体文件即可。

文件校验：见 md5.txt
'''


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'build',
                                                             'final')
    fonts_out = os.path.join(out, 'Data', 'FONTS')
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(fonts_out)

    spec = {}
    for fn in sorted(os.listdir(WS)):
        if not fn.endswith('.json'):
            continue
        work = json.load(open(os.path.join(WS, fn), encoding='utf-8'))
        zh = {k: w['zh'].strip() for k, w in work.items()
              if (w.get('zh') or '').strip()}
        if zh:
            spec[fn[:-5]] = zh
    n = sum(len(v) for v in spec.values())
    print('翻译规格: %d 文件 %d 条（未译条目保持英文）\n' % (len(spec), n))

    errs = validate_all(spec) + budgets_check(spec)
    if errs:
        for e in errs:
            print('ERR', e)
        sys.exit(1)
    print('译文校验通过\n')
    bft_check(spec)

    for fn in os.listdir(ASSETS_FONTS):
        shutil.copy(os.path.join(ASSETS_FONTS, fn),
                    os.path.join(fonts_out, fn))

    d1 = os.path.join(out, 'DATA.PCK')
    d3 = os.path.join(out, 'data3.pck')
    build_pack(os.path.join(ROOT, 'backup', 'DATA.PCK.original'), d1, spec,
               True)
    build_pack(os.path.join(ROOT, 'backup', 'data3.pck.original'), d3, spec,
               False)
    diff_check(os.path.join(ROOT, 'backup', 'DATA.PCK.original'), d1,
               [(FC_OFF, FC_OFF + FC_SIZE)])
    diff_check(os.path.join(ROOT, 'backup', 'data3.pck.original'), d3, [])
    readback(d1, spec)
    readback(d3, spec)

    with open(os.path.join(out, 'md5.txt'), 'w') as f:
        for fn in ['DATA.PCK', 'data3.pck'] + \
                  [os.path.join('Data', 'FONTS', x)
                   for x in sorted(os.listdir(fonts_out))]:
            h = hashlib.md5(open(os.path.join(out, fn), 'rb').read())
            f.write('%s *%s\n' % (h.hexdigest(), fn))
    with open(os.path.join(out, '安装说明.txt'), 'w', encoding='utf-8') as f:
        f.write(README)
    print('\n构建完成 -> %s' % out)


if __name__ == '__main__':
    main()
