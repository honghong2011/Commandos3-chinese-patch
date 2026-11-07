# -*- coding: utf-8 -*-
"""导出人类可读的全量待译文本 -> extract_cn\\

  全部文本.txt          合并版（浏览用，带统计头）
  <NAME>.txt            每文件一版
条目格式：KEY [预算] "原文"，多行值原样缩进展示，已译条目附 → 译文。
排除 CREDITS（制作名单，不翻）与 TM_DEMO（试玩版残留，游戏不用）。
"""
import os
import sys
import json
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strlib import decode, list_entries
from c3pck import PCK

ROOT = os.environ.get('C3WORK') or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'extract_cn')
WS = os.path.join(ROOT, 'translation', 'workspace')
SKIP = {'CREDITS', 'TM_DEMO'}
KIND = {
    'GLOBAL': '全局界面：菜单/物品/武器/动作/提示',
    'MANUALC3': '游戏内帮助手册（排版文本，含\\n）',
    'TUT1': '教学任务 1 台词/字幕',
    'TUT2': '教学任务 2 台词/字幕',
    'BRIEFINGS': '任务简报正文',
    'BER': '柏林战役 台词/字幕',
    'ST1': '斯大林格勒战役 台词/字幕',
    'ST2': '斯大林格勒战役 台词/字幕',
    'CP': '战役任务 台词/字幕',
    'DSP': '战役任务 台词/字幕',
    'PT': '战役任务 台词/字幕',
    'TC': '战役任务 台词/字幕',
    'TC_01': '战役任务 台词/字幕',
    'TE': '战役任务 台词/字幕',
    'TM': '战役任务 台词/字幕',
    'TV': '战役任务 台词/字幕',
    'TA1': '战役任务 台词/字幕',
    'RED': '结局字幕',
    'END': '通关结算',
}

ENTRY_TAIL = re.compile(r'(?m)^([A-Za-z0-9_]+)[ \t]+"(.*?)"[ \t]*(//[^\n]*)?',
                        re.S)


def dump_file(text, zh_map):
    """text -> 可读文本块。"""
    lines = []
    for m in ENTRY_TAIL.finditer(text):
        key, val, cmt = m.group(1), m.group(2), m.group(3) or ''
        zh = zh_map.get(key)
        head = '%s  [%d]  ' % (key, len(val))
        if '\n' in val:
            lines.append(head + '"')
            for ln in val.split('\n'):
                lines.append('      | ' + ln)
            lines.append('      "')
        else:
            lines.append(head + '"' + val + '"')
        if cmt.strip():
            lines.append('      ' + cmt.strip())
        if zh:
            lines.append('      → 已译: ' + zh)
    return '\n'.join(lines)


def main():
    os.makedirs(OUT, exist_ok=True)
    pck = PCK(os.path.join(ROOT, 'backup', 'DATA.PCK.original'))
    merged = []
    tot_n = tot_b = 0
    rows = []
    for name in pck.entries:
        if name in SKIP:
            continue
        text, _, _ = decode(pck.blob(name))
        ws_path = os.path.join(WS, name + '.json')
        zh_map = {}
        if os.path.exists(ws_path):
            work = json.load(open(ws_path, encoding='utf-8'))
            zh_map = {k: w['zh'] for k, w in work.items() if w.get('zh')}
        entries = list_entries(text)
        n, b = len(entries), sum(len(v) for _, v, _ in entries)
        rows.append((name, n, b, len(zh_map)))
        tot_n += n
        tot_b += b
        block = ('【%s】 %d 条 · %d 字符预算 · %s\n%s\n'
                 % (name, n, b, KIND.get(name, ''), '─' * 56)
                 + dump_file(text, zh_map))
        with open(os.path.join(OUT, name + '.txt'), 'w',
                  encoding='utf-8') as f:
            f.write(block)
        merged.append(block)

    header = ['盟军敢死队3 全量待译文本（明文提取）',
              '=' * 56,
              '范围：%d 个 STR 文件（另有 CREDITS 制作名单、TM_DEMO 试玩残留，'
              '不翻译）' % len(rows),
              '合计：%d 条 · %d 字符预算（UTF-16 单元）' % (tot_n, tot_b),
              '说明：[N] = 该条译文长度上限（中文按 1 字 1 单元计，'
              '超了构建器会拒收）', '     → 已译 = 此前实测通过的 v11 译法',
              '     %Name 类占位符翻译时必须原样保留', '',
              '统计一览：']
    for name, n, b, z in rows:
        header.append('  %-11s %4d 条 %7d 预算  已译 %d' % (name, n, b, z))
    header += ['', '=' * 56, '']
    with open(os.path.join(OUT, '全部文本.txt'), 'w',
              encoding='utf-8') as f:
        f.write('\n'.join(header) + '\n\n\n'.join(merged))
    print('导出完成 ->', OUT)
    for name, n, b, z in rows:
        print('  %-11s %4d 条 %7d 预算  已译 %d' % (name, n, b, z))
    print('合计 %d 条 / %d 字符预算' % (tot_n, tot_b))


if __name__ == '__main__':
    main()
