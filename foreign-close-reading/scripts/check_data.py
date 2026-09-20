#!/usr/bin/env python3
"""Lint a close-reading data.json before it ships.

Usage:
  python3 check_data.py --data data.json [--sentences sentences.json] [--strict]

Catches the failure modes that ruin a reader:
  · sentence text retyped/damaged instead of copied (ids/para drift, lost à/ё/가)
  · missing or empty translation
  · placeholder junk ("不支持" / TODO / undefined / null / 待补充 …)
  · 生词 entries without a headword or without a meaning
  · Japanese entries without a kana reading, Russian without stress, etc.
  · empty annotation objects (grammar / culture / native) that render as a bare heading

Exit code 0 = clean (warnings allowed), 1 = errors found.
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter

# 整段就是一个占位符（"N/A" / "待补充" / "null" …） → 一定是漏填
WHOLE_PLACEHOLDER = re.compile(
    r'^\s*(N/?A|none|null|nil|undefined|nan|todo|fixme|tbd|待补充|待定|待填|'
    r'占位|placeholder|不支持|无法解析|-+|\?+)\s*$', re.IGNORECASE)
# 出现在正文里的引擎泄漏痕迹 → 一定有问题
LEAK = re.compile(r'(\bundefined\b|\[object Object\]|\bNaN\b|不支持(解析|该语言|此语言|的语言))',
                  re.IGNORECASE)
# 「不支持」只在“没有讲解”的意义上算错；正常行文里偶尔出现不算
TRIVIAL = {'the', 'a', 'an', 'and', 'of', 'to', 'is', 'are', 'was', 'were', 'it',
           'he', 'she', 'they', 'you', 'i', 'in', 'on', 'at', 'for', 'with', 'that',
           'это', 'и', 'в', 'не', 'он', 'она', 'на', 'с', 'как', 'то',
           'le', 'la', 'les', 'un', 'une', 'et', 'de', 'des', 'du', 'il', 'elle',
           '私', 'それ', 'これ', 'こと', 'もの', '그', '것', '있다', '하다', '나는'}

HEAD_KEYS = ('w', 'word', 'term', 'phrase', 'vocab')
MEAN_KEYS = ('m', 'meaning', 'mean', 'def', 'definition', 'gloss', 'translation')
READ_KEYS = ('p', 'ipa', 'phonetic', 'pron', 'reading', 'pronunciation')
NOTE_T = ('t', 'title', 'name', 'point', 'topic', 'label', 'head')
NOTE_D = ('d', 'desc', 'detail', 'text', 'body', 'explain', 'm', 'note', 'content')

CJK_LANGS = ('ja', 'ko', 'zh', 'jpn', 'kor', 'cjk')
CYRL_LANGS = ('ru', 'uk', 'be', 'bg', 'sr', 'cyrl')

# data.json 的 lang 可能写的是排版族名（SKILL.md 允许 cyrl/jpn/kor/cjk），
# 发音规则按具体语言查，先归一化回去
LANG_FAMILY = {'cyrl': 'ru', 'jpn': 'ja', 'kor': 'ko', 'cjk': 'zh',
               'latn': 'en', 'rtl': 'ar'}

# IPA 元音字符：用来判断一个转写是不是只有一个音节（单音节词不需要重音符）
IPA_VOWELS = set('aeiouy\u0251\u0250\u0252\u00e6\u0254\u0258\u0259\u025a\u0264'
                 '\u025b\u025c\u0153\u0276\u0268\u026a\u028a\u0289\u028c\u028f')
STRESS_MARKS = re.compile('[\u02c8\u02cc\u0301\u00b4]')


def needs_stress(phon):
    """多音节的俄语转写必须带重音符（ˈ / ́）；单音节词（я → ja）没有重音可言。"""
    vowels = [c for c in phon if c in IPA_VOWELS]
    return len(vowels) >= 2 and not STRESS_MARKS.search(phon)


def is_cyrillic_word(head):
    """重音规则只管西里尔词；俄文书里的法语借词（Eh bien）不适用。"""
    return has(head) and bool(re.search(r'[\u0400-\u04ff]', str(head)))

errors, warnings = [], []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def has(v):
    return v is not None and str(v).strip() != ''


def pick(o, keys):
    for k in keys:
        if k in o and has(o[k]):
            return o[k]
    return None


def scan_strings(node, where):
    """Placeholder junk anywhere in a sentence's annotations."""
    if isinstance(node, str):
        if WHOLE_PLACEHOLDER.match(node):
            err('%s is a placeholder value (%r)' % (where, node.strip()[:40]))
        else:
            m = LEAK.search(node)
            if m:
                err('%s contains engine leakage %r' % (where, m.group(0)))
    elif isinstance(node, dict):
        for k, v in node.items():
            scan_strings(v, where + '.' + str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            scan_strings(v, '%s[%d]' % (where, i))


def norm_text(s):
    s = unicodedata.normalize('NFC', str(s))
    return re.sub(r'\s+', ' ', s).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--sentences', help='the sentences.json this data was built from')
    ap.add_argument('--strict', action='store_true',
                    help='treat warnings (missing phonetics, thin annotations) as errors')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()

    try:
        with open(a.data, encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        sys.exit('check_data: no such file: %s' % a.data)
    except UnicodeDecodeError as e:
        sys.exit('check_data: %s is not UTF-8 (%s)' % (a.data, e.reason))
    except json.JSONDecodeError as e:
        sys.exit('check_data: %s is not valid JSON: %s (line %d, column %d)'
                 % (a.data, e.msg, e.lineno, e.colno))

    if not has(data.get('title')):
        err('data.json has no title')
    sents = data.get('sentences')
    if not isinstance(sents, list) or not sents:
        sys.exit('check_data: "sentences" must be a non-empty list')

    lang = str(data.get('lang') or '').lower()
    ids = [str(s.get('id')) for s in sents if isinstance(s, dict)]
    dup = sorted(k for k, c in Counter(ids).items() if c > 1)
    if dup:
        err('duplicate sentence ids: %s' % ', '.join(dup))
    try:
        nums = [float(i) for i in ids]
        if nums != sorted(nums):
            warn('sentences are not in ascending id order')
    except ValueError:
        warn('some sentence ids are not numeric')

    total_w = total_g = total_c = total_n = with_culture = with_native = 0
    for s in sents:
        if not isinstance(s, dict):
            err('a sentence entry is not an object')
            continue
        sid = s.get('id')
        tag = 'id=%s' % sid
        for k in ('id', 'text', 'para'):
            if k not in s:
                err('%s is missing "%s"' % (tag, k))
        text = s.get('text')
        if not has(text):
            err('%s has empty text' % tag)
        scan_strings(s, tag)

        trans = pick(s, ('translation', 'trans', 'zh', 'translation_zh', 'cn'))
        if not has(trans):
            err('%s has no translation' % tag)

        words = s.get('words') or s.get('vocab') or s.get('vocabulary') or []
        if isinstance(words, dict):
            words = [{'w': k, 'm': v} if not isinstance(v, dict) else v
                     for k, v in words.items()]
        if not isinstance(words, list):
            err('%s words must be a list or dict' % tag)
            words = []
        total_w += len(words)
        for i, w in enumerate(words):
            if not isinstance(w, dict):
                err('%s words[%d] is not an object' % (tag, i))
                continue
            head = pick(w, HEAD_KEYS)
            mean = pick(w, MEAN_KEYS)
            if not has(head) and not has(mean):
                err('%s words[%d] has neither a headword nor a meaning' % (tag, i))
            if not has(mean):
                err('%s words[%d] (%s) has no meaning' % (tag, i, head))
            if has(head) and str(head).strip().lower().strip('.,!?') in TRIVIAL:
                warn('%s words[%d] "%s" is too basic to gloss' % (tag, i, head))
            fam = LANG_FAMILY.get(lang, lang)
            phon = pick(w, READ_KEYS)
            if not has(phon):
                if fam.startswith('ja'):
                    err('%s words[%d] (%s) has no kana reading (p)' % (tag, i, head))
                elif fam.startswith(('ru', 'uk', 'be', 'bg')):
                    # 俄语重音可移动且不可从拼写推出，不标出来就没有教学价值；
                    # 缺 p 一律警告（--strict 下升级为错误）
                    warn('%s words[%d] (%s) has no stress-marked phonetic (p)' % (tag, i, head))
                elif fam.startswith(('en', 'fr', 'de', 'es', 'it', 'pt', 'ko')) and a.strict:
                    warn('%s words[%d] (%s) has no IPA (p)' % (tag, i, head))
            elif fam.startswith(('ru', 'uk', 'be', 'bg')) and is_cyrillic_word(head) \
                    and needs_stress(str(phon)):
                warn("%s words[%d] (%s) phonetic %r carries no stress mark"
                     % (tag, i, head, str(phon)[:24]))
            if has(mean) and re.search(r'(——|--|\|)', str(mean)) and not has(head):
                warn('%s words[%d] puts the headword inside "m"; use "w" instead' % (tag, i, head))

        for key, label in (('grammar', 'grammar'), ('culture', 'culture'),
                           ('native', 'native')):
            items = s.get(key) or []
            if isinstance(items, dict):
                items = [items]
            if not isinstance(items, list):
                err('%s %s must be a list or object' % (tag, key))
                items = []
            kept = 0
            for i, g in enumerate(items):
                if isinstance(g, str):
                    if has(g):
                        kept += 1
                    else:
                        err('%s %s[%d] is an empty string' % (tag, label, i))
                    continue
                if not isinstance(g, dict):
                    err('%s %s[%d] is not an object or string' % (tag, label, i))
                    continue
                if not any(has(g.get(k)) for k in NOTE_T + NOTE_D):
                    err('%s %s[%d] is empty and will not render' % (tag, label, i))
                    continue
                kept += 1
                if key == 'grammar' and not has(pick(g, NOTE_D)):
                    warn('%s grammar[%d] has a title but no explanation' % (tag, i))
            if key == 'grammar':
                total_g += kept
            elif key == 'culture':
                total_c += kept
                if kept:
                    with_culture += 1
            else:
                total_n += kept
                if kept:
                    with_native += 1

    if a.sentences:
        try:
            with open(a.sentences, encoding='utf-8') as f:
                src = json.load(f)
        except Exception as e:
            sys.exit('check_data: cannot read %s: %s' % (a.sentences, e))
        want = {str(x['id']): x for x in src.get('sentences', [])}
        got = {str(x.get('id')): x for x in sents if isinstance(x, dict)}
        missing = sorted(set(want) - set(got), key=lambda v: float(v) if v.replace('.', '', 1).isdigit() else 0)
        extra = sorted(set(got) - set(want), key=lambda v: float(v) if v.replace('.', '', 1).isdigit() else 0)
        if missing:
            warn('sentences.json has ids missing from data.json: %s' % ', '.join(missing[:12]))
        if extra:
            err('data.json has ids not in sentences.json: %s' % ', '.join(extra[:12]))
        for sid, w in want.items():
            g = got.get(sid)
            if not g:
                continue
            if norm_text(w.get('text')) != norm_text(g.get('text')):
                err('id=%s text differs from sentences.json (copy it verbatim!)' % sid)
            if str(w.get('para')) != str(g.get('para')):
                warn('id=%s para %s != %s from sentences.json' % (sid, g.get('para'), w.get('para')))
        if src.get('layout') and data.get('lang'):
            ok = {src['layout']} | {
                'latn': {'en', 'fr', 'de', 'es', 'it', 'pt', 'nl', 'sv', 'pl', 'la', 'vi'},
                'cyrl': {'ru', 'uk', 'be', 'bg', 'sr', 'el', 'mk', 'kk'},
                'jpn': {'ja'}, 'kor': {'ko'}, 'cjk': {'zh'},
            }.get(src['layout'], set())
            if str(data['lang']).lower() not in ok:
                warn('data.lang=%r does not match sentences.json layout=%r'
                     % (data['lang'], src['layout']))

    if not a.quiet:
        print('sentences      : %d' % len(sents))
        print('lang / title   : %s / %s' % (data.get('lang') or '(auto)', data.get('title')))
        print('annotations    : %d 生词 · %d 语法 · %d 文化 · %d 母语者'
              % (total_w, total_g, total_c, total_n))
        print('coverage        : 文化 %d/%d 句 · 母语者 %d/%d 句'
              % (with_culture, len(sents), with_native, len(sents)))
    if warnings:
        print('\n%d warning(s):' % len(warnings))
        for w in warnings[:40]:
            print('  warn  ' + w)
        if len(warnings) > 40:
            print('  … %d more' % (len(warnings) - 40))
    if errors:
        print('\n%d error(s):' % len(errors))
        for e in errors[:60]:
            print('  ERROR ' + e)
        if len(errors) > 60:
            print('  … %d more' % (len(errors) - 60))
    if errors or (a.strict and warnings):
        print('\nFAILED — fix the above, then rerun check_data.py')
        sys.exit(1)
    print('\nOK — data.json is ready to build')
    sys.exit(0)


if __name__ == '__main__':
    main()
