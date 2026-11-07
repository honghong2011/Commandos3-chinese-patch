# -*- coding: utf-8 -*-
"""生成全量汉化工作文件：translation/workspace/<NAME>.json

每个文件一个 JSON：
  { "KEY": {"budget": 原文UTF16单元数, "flags": [...], "en": 原文, "zh": ""} }
AI 翻译只需填 "zh" 字段（显示用简体中文，可含全角标点）。
排除：CREDITS(制作名单)、TM_DEMO(试玩残留)。
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strlib import decode, list_entries, tokens
from c3pck import PCK

# 工作根目录 = tools 的上级目录；也可用环境变量 C3WORK 覆盖
ROOT = os.environ.get('C3WORK') or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'translation', 'workspace')
SKIP = {'CREDITS', 'TM_DEMO'}


def flags_of(en):
    fl = []
    if tokens(en):
        fl.append('含占位符:' + ' '.join(sorted(set(tokens(en)))))
    if '\n' in en:
        fl.append('含真实换行')
    if '\\n' in en:
        fl.append('含\\n转义')
    if en.strip() == '':
        fl.append('空白/装饰')
    if len(en) <= 2:
        fl.append('超短')
    return fl


def main():
    os.makedirs(OUT, exist_ok=True)
    pck = PCK(os.path.join(ROOT, 'backup', 'DATA.PCK.original'))
    grand_n = grand_c = 0
    for name in pck.entries:
        if name in SKIP:
            continue
        text, _, _ = decode(pck.blob(name))
        work = {}
        for key, val, _ in list_entries(text):
            work[key] = {'budget': len(val), 'flags': flags_of(val),
                         'en': val, 'zh': ''}
        path = os.path.join(OUT, name + '.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(work, f, ensure_ascii=False, indent=1)
        n = len(work)
        c = sum(w['budget'] for w in work.values())
        grand_n += n
        grand_c += c
        print('%-11s %4d 条  %6d 字符预算' % (name, n, c))
    print('\n共 %d 个文件, %d 条, %d 字符预算 -> %s'
          % (len([f for f in os.listdir(OUT)]), grand_n, grand_c, OUT))


if __name__ == '__main__':
    main()
