# -*- coding: utf-8 -*-
"""AI 翻译器：接 OpenAI 兼容 API，把 workspace 工作文件的未译条目翻成简体中文。

用法：
  1) 按 README「AI 翻译配置」创建 translation\llm_config.json
     （base_url / api_key / model 三项）；
  2) 运行：
       python tools/translate_llm.py                # 翻译全部未译条目
       python tools/translate_llm.py GLOBAL TUT1    # 只翻指定文件
       python tools/translate_llm.py --limit 20     # 试跑前 20 条
       python tools/translate_llm.py --check        # 只本地校验，不调 API

特性：
  * 断点续跑：已翻条目（zh 非空）自动跳过，每批翻译完立即写盘；
  * 逐条硬校验：长度预算 / GBK 可编码 / %占位符保留 / 禁引号换行制表符，
    不合格条目带错误原因自动重试（可配轮数），最终仍失败则留空并汇总报告；
  * 对应关系：工作文件以 KEY 为主键（KEY->译文），不依赖顺序，天然防错位。

文本源与产物：translation\\workspace\\<NAME>.json
  结构 {"KEY": {"budget": n, "flags": [...], "en": "...", "zh": "..."}}
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from strlib import gbk_units, tokens

ROOT = os.environ.get('C3WORK') or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
WS = os.path.join(ROOT, 'translation', 'workspace')
CFG_PATH = os.path.join(ROOT, 'translation', 'llm_config.json')
GLOSSARY_PATH = os.path.join(ROOT, 'translation', 'glossary.tsv')

# 每个文件的语境说明（喂给模型）
KIND = {
    'GLOBAL': '全局界面文本：主菜单、选项、武器/物品名、动作、系统提示。多为短词',
    'MANUALC3': '游戏内帮助手册，含 \\n 排版转义的长说明文',
    'TUT1': '教学任务1：教官对新兵的解说台词',
    'TUT2': '教学任务2：教官对新兵的解说台词',
    'BRIEFINGS': '战役任务简报正文：长段落军事叙述',
    'BER': '柏林战役任务：士兵对白与字幕',
    'ST1': '斯大林格勒战役任务：士兵对白与字幕',
    'ST2': '斯大林格勒战役任务：士兵对白与字幕',
    'CP': '战役任务：士兵对白与字幕',
    'DSP': '战役任务：士兵对白与字幕',
    'PT': '战役任务：士兵对白与字幕',
    'TC': '战役任务：士兵对白与字幕',
    'TC_01': '战役任务：士兵对白与字幕',
    'TE': '战役任务：士兵对白与字幕',
    'TM': '战役任务：士兵对白与字幕',
    'TV': '战役任务：士兵对白与字幕',
    'TA1': '战役任务：士兵对白与字幕',
    'RED': '结局字幕',
    'END': '通关结算文本',
}

SYSTEM_PROMPT = """你是《盟军敢死队3：目标柏林》(Commandos 3: Destination Berlin, 2003)\
的资深官方本地化译者。这是一款二战题材的即时战术潜入游戏：玩家指挥盟军敢死小队\
（绿贝雷、狙击手、工兵、司机、小偷、间谍等）深入德军后方完成破坏、侦察、营救任务。

把给你的英文游戏文本译成简体中文，要求：
1. 风格：军事、干练、符合2003年官方简中游戏腔调；界面词必须精炼。
2. 硬性规则（违反即废稿）：
   a. 每条译文长度不得超过给出的"预算"（一个汉字/字母/数字/标点都算1）；
   b. %开头的占位符（如 %CharacterKiller、%d）必须原样保留、位置语义对应；
   c. 原文里的 \\n 是排版换行符，译文必须保留；
   d. 译文中禁止出现英文双引号 " 、制表符、多余首尾空格；
   e. 只用 GBK 字符集内的汉字和全角标点（，。！？：；、·—…《》""''），
      禁用 emoji、生僻字、繁体字。
3. 术语表优先级最高，术语必须统一。
4. 只输出 JSON 对象，不要任何解释、不要代码块围栏。"""


def load_config():
    if not os.path.exists(CFG_PATH):
        print('缺少配置文件：%s' % CFG_PATH)
        print('请按 README「AI 翻译配置」一节创建该文件'
              '（base_url / api_key / model 三项）')
        sys.exit(1)
    cfg = json.load(open(CFG_PATH, encoding='utf-8'))
    for k in ('base_url', 'api_key', 'model'):
        if not cfg.get(k):
            print('llm_config.json 缺少 %s' % k)
            sys.exit(1)
    cfg.setdefault('temperature', 0.3)
    cfg.setdefault('max_batch_chars', 2400)
    cfg.setdefault('sleep_s', 0.5)
    cfg.setdefault('max_rounds', 3)
    return cfg


def chat(cfg, messages):
    """调用 OpenAI 兼容 chat/completions，返回文本。"""
    url = cfg['base_url'].rstrip('/') + '/chat/completions'
    body = json.dumps({
        'model': cfg['model'],
        'messages': messages,
        'temperature': cfg['temperature'],
    }).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers={
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + cfg['api_key'],
    })
    last_err = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(r.read().decode('utf-8'))
            return data['choices'][0]['message']['content']
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                wait = 5 * (attempt + 1)
                print('  HTTP %d，%d 秒后重试...' % (e.code, wait))
                time.sleep(wait)
                continue
            raise RuntimeError('API HTTP %d: %s' % (e.code, e.read()[:300]))
        except Exception as e:
            last_err = e
            if attempt < 3:
                time.sleep(3)
                continue
            raise RuntimeError('API 调用失败: %s' % e)
    raise RuntimeError('API 调用失败: %s' % last_err)


def parse_json_obj(text):
    """容错解析模型返回的 JSON 对象（剥围栏/截首尾）。"""
    t = text.strip()
    if t.startswith('```'):
        t = re.sub(r'^```[a-zA-Z]*\s*', '', t)
        t = re.sub(r'\s*```$', '', t)
    i, j = t.find('{'), t.rfind('}')
    if i < 0 or j <= i:
        raise ValueError('返回中没有 JSON 对象')
    return json.loads(t[i:j + 1])


def validate(en, zh, budget):
    """返回错误列表；空列表 = 合格。调用方须先 strip 过 zh。"""
    errs = []
    if len(zh) > budget:
        errs.append('超预算 %d/%d' % (len(zh), budget))
    try:
        gbk_units(zh)
    except Exception:
        errs.append('含 GBK 外字符')
    if Counter(tokens(en)) != Counter(tokens(zh)):
        errs.append('占位符不一致 原=%s 译=%s' % (tokens(en), tokens(zh)))
    if '"' in zh or '\t' in zh:
        errs.append('含引号/制表符')
    if '\n' in zh and '\n' not in en:
        errs.append('含换行而原文无')
    return errs


def load_glossary():
    if not os.path.exists(GLOSSARY_PATH):
        return ''
    lines = []
    for ln in open(GLOSSARY_PATH, encoding='utf-8'):
        ln = ln.rstrip('\n')
        if ln and not ln.startswith('#'):
            lines.append(ln)
    return '\n'.join(lines)


def build_batches(items, max_chars):
    """items: [(key, w_dict)] -> 按累计字符量分组。"""
    batches, cur, cur_chars = [], [], 0
    for key, w in items:
        size = w['budget']
        if cur and (cur_chars + size > max_chars or len(cur) >= 30):
            batches.append(cur)
            cur, cur_chars = [], 0
        cur.append((key, w))
        cur_chars += size
    if cur:
        batches.append(cur)
    return batches


def make_user_prompt(name, batch, glossary, feedback=None):
    lines = ['【文件】%s —— %s' % (name, KIND.get(name, ''))]
    if glossary:
        lines.append('【术语表】')
        lines.append(glossary)
    lines.append('【条目】（KEY / 预算 / 英文原文）')
    for key, w in batch:
        en = w['en']
        if '\n' in en:
            en = en.replace('\n', '\\n')
        lines.append('%s\n  预算=%d\n  原文=%s' % (key, w['budget'], en))
    keys = '","'.join(k for k, _ in batch)
    lines.append('【任务】逐条译成简体中文。只输出 JSON：{"%s" 对应各条译文}'
                 % keys)
    if feedback:
        lines.append('【上一轮失败原因，本轮必须修复】')
        lines.append(feedback)
    return '\n'.join(lines)


def _short(s, n=24):
    s = s.replace('\n', '\\n')
    return s[:n] + ('…' if len(s) > n else '')


def translate_file(cfg, name, work, glossary, limit=None):
    # 纯空格/空串原文 = 排版占位，无语义，直接跳过（不再报未通过）
    blanks = [k for k, w in work.items()
              if not w.get('zh') and not w['en'].strip()]
    todo = [(k, w) for k, w in work.items()
            if not w.get('zh') and w['en'].strip()]
    if blanks:
        print('%-11s 跳过 %d 条纯空格占位条目: %s'
              % (name, len(blanks), ','.join(blanks)))
    if limit is not None:
        todo = todo[:limit]
    if not todo:
        print('%-11s 无未译条目，跳过' % name)
        return 0, 0
    batches = build_batches(todo, cfg['max_batch_chars'])
    print('%-11s 待译 %d 条，分 %d 批' % (name, len(todo), len(batches)))
    done = fail = 0
    for bi, batch in enumerate(batches, 1):
        pending = list(batch)
        feedback = None
        for round_no in range(1, cfg['max_rounds'] + 1):
            if not pending:
                break
            print('  ▶ [%s] 批 %d/%d 第 %d 轮请求中（%d 条，已成功 %d）...'
                  % (name, bi, len(batches), round_no, len(pending), done))
            prompt = make_user_prompt(name, pending, glossary, feedback)
            try:
                resp = chat(cfg, [
                    {'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user', 'content': prompt},
                ])
                got = parse_json_obj(resp)
            except Exception as e:
                print('  批 %d/%d 第 %d 轮失败: %s'
                      % (bi, len(batches), round_no, e))
                time.sleep(cfg['sleep_s'])
                feedback = None
                continue
            next_pending, fb_lines = [], []
            for key, w in pending:
                zh = got.get(key)
                if isinstance(zh, str) and zh.strip():
                    zh = zh.strip()          # 首尾空格一律去掉
                    errs = validate(w['en'], zh, w['budget'])
                else:
                    zh, errs = '', ['模型未返回该条']
                if errs:
                    next_pending.append((key, w))
                    fb_lines.append('%s 错误=%s（预算=%d 原文=%s）'
                                    % (key, '; '.join(errs), w['budget'],
                                       w['en'].replace('\n', '\\n')))
                else:
                    work[key]['zh'] = zh
                    done += 1
                    print('  ✓ %s/%s → %s' % (name, key, _short(zh)))
            pending = next_pending
            feedback = '\n'.join(fb_lines) if pending else None
            if pending and round_no < cfg['max_rounds']:
                print('  ↻ 本轮 %d 条未过，带错误反馈重试' % len(pending))
        for key, w in pending:
            print('  ✗ %s/%s: 最终未通过，保持英文' % (name, key))
        fail += len(pending)
        save_work(name, work)            # 每批落盘，断点续跑
        print('  ■ [%s] 批 %d/%d 完成，累计成功 %d' % (name, bi, len(batches),
                                                    done))
        time.sleep(cfg['sleep_s'])
    return done, fail


def save_work(name, work):
    path = os.path.join(WS, name + '.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(work, f, ensure_ascii=False, indent=1)


def local_check(names):
    """不调 API 的本地校验（宽松模式：纯空格原文=跳过，zh 自动去首尾空格）。"""
    grand_err = grand_zh = grand_todo = grand_blank = 0
    for name in names:
        work = json.load(open(os.path.join(WS, name + '.json'),
                              encoding='utf-8'))
        errs = []
        n_zh = n_todo = n_blank = 0
        for key, w in work.items():
            zh = (w.get('zh') or '').strip()
            if not w['en'].strip():
                n_blank += 1                    # 排版占位，无需翻译
                continue
            if not zh:
                n_todo += 1
                continue
            n_zh += 1
            errs += ['%s/%s: %s' % (name, key, e)
                     for e in validate(w['en'], zh, w['budget'])]
        grand_err += len(errs)
        grand_zh += n_zh
        grand_todo += n_todo
        grand_blank += n_blank
        for e in errs[:10]:
            print('ERR ', e)
        print('%-11s 已译 %d  未译 %d  空格跳过 %d  错误 %d'
              % (name, n_zh, n_todo, n_blank, len(errs)))
    print('\n合计: 已译 %d  未译 %d  空格跳过 %d  错误 %d'
          % (grand_zh, grand_todo, grand_blank, grand_err))
    return grand_err


def main():
    args = sys.argv[1:]
    limit = None
    if '--check' in args:
        i = args.index('--check')
        names = [a for a in args[:i] + args[i + 1:] if not a.startswith('--')]
        all_names = sorted(f[:-5] for f in os.listdir(WS)
                           if f.endswith('.json'))
        sys.exit(1 if local_check(names or all_names) else 0)
    if '--limit' in args:
        i = args.index('--limit')
        limit = int(args[i + 1])
        del args[i:i + 2]
    names = args or sorted(f[:-5] for f in os.listdir(WS)
                           if f.endswith('.json'))
    cfg = load_config()
    glossary = load_glossary()
    print('模型: %s @ %s\n' % (cfg['model'], cfg['base_url']))
    grand_done = grand_fail = 0
    try:
        for name in names:
            work = json.load(open(os.path.join(WS, name + '.json'),
                                  encoding='utf-8'))
            d, f = translate_file(cfg, name, work, glossary, limit)
            grand_done += d
            grand_fail += f
            save_work(name, work)
    except KeyboardInterrupt:
        print('\n中断：已翻译的条目已保存，可直接重跑续译。')
        sys.exit(130)
    print('\n翻译完成：成功 %d 条，失败 %d 条（失败的保持英文，可重跑重试）'
          % (grand_done, grand_fail))


if __name__ == '__main__':
    main()
