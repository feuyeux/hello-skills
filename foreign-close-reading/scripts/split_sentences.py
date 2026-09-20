#!/usr/bin/env python3
"""Split a foreign-language text file into sentences, preserving paragraphs.

Usage:
  python3 split_sentences.py INPUT.txt [--start N] [--limit N] [--out sentences.json]

Prints (or writes) JSON:
  {"lang": "latin"|"cjk", "total": M, "sentences": [{"id": 1, "text": "...", "para": 1}]}
- id is 1-based, continuous in reading order
- para is the 1-based natural-paragraph number (the reader rebuilds layout from it)
- --start/--limit slice by sentence id (inclusive start, limit = max count)
"""

import argparse
import json
import re
import sys

LATIN_ABBR = {
    'mr', 'mrs', 'ms', 'dr', 'prof', 'rev', 'hon', 'st', 'jr', 'sr', 'mt',
    'no', 'nos', 'vs', 'etc', 'e.g', 'i.e', 'cf', 'al', 'fig', 'figs', 'ch',
    'chap', 'sec', 'vol', 'p', 'pp', 'ed', 'eds', 'trans', 'inc', 'ltd',
    'co', 'corp', 'dept', 'univ', 'est', 'fl', 'c', 'ca',
    'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'sept', 'oct',
    'nov', 'dec', 'mon', 'tue', 'tues', 'wed', 'thu', 'thur', 'thurs',
    'fri', 'sat', 'sun',
}

LATIN_CLOSERS = '"\'\u201d\u2019\u300d\u300f\uff09)\u00bb]\u201d'
CJK_END = '\u3002\uff01\uff01\uff1f?\u2026'
CJK_CLOSERS = '\u300d\u300f\uff09)\u201d\u2019\u300b"'


def read_text(path):
    for enc in ('utf-8', 'utf-8-sig', 'shift_jis', 'gbk', 'big5', 'latin-1'):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    sys.exit('cannot decode file: ' + path)


def looks_cjk(text):
    cjk = sum(1 for c in text
              if '\u3040' <= c <= '\u30ff' or '\u3400' <= c <= '\u9fff')
    return cjk * 5 > len(text)


def split_latin(p):
    sents, start, i, n = [], 0, 0, len(p)
    while i < n:
        if p[i] not in '.!?\u2026':
            i += 1
            continue
        j = i + 1
        while j < n:
            if p[j] in '.!?\u2026' + LATIN_CLOSERS:
                j += 1
            # 法语引号写作 ". »"——句号后隔空格才是闭合引号
            elif p[j] in ' \u00a0' and j + 1 < n and p[j + 1] in LATIN_CLOSERS:
                j += 1
            else:
                break
        if p[i] == '.' and j < n:
            m = re.search(r'([A-Za-z\u00c0-\u024f]+)\.\s*$', p[start:i + 1])
            word = m.group(1) if m else ''
            if word and (word.lower() in LATIN_ABBR or
                         (len(word) == 1 and word.isupper())):
                i = j
                continue
            if i > 0 and p[i - 1].isdigit() and p[j].isdigit():
                i = j
                continue
            if p[j].islower() or p[j] == ',':
                i = j
                continue
        sents.append(p[start:j].strip())
        start = i = j
    if p[start:].strip():
        sents.append(p[start:].strip())
    return sents


def split_cjk(p):
    sents, start, i, n = [], 0, 0, len(p)
    while i < n:
        if p[i] in CJK_END:
            j = i + 1
            while j < n and p[j] in CJK_END + CJK_CLOSERS:
                j += 1
            sents.append(p[start:j].strip())
            start = i = j
        else:
            i += 1
    if p[start:].strip():
        sents.append(p[start:].strip())
    return sents


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input')
    ap.add_argument('--start', type=int, default=1,
                    help='first sentence id to keep (1-based)')
    ap.add_argument('--limit', type=int, default=0,
                    help='max number of sentences to keep (0 = all)')
    ap.add_argument('--out', help='write JSON here instead of stdout')
    a = ap.parse_args()

    text = read_text(a.input)
    lang = 'cjk' if looks_cjk(text) else 'latin'
    split = split_cjk if lang == 'cjk' else split_latin

    sentences = []
    for pid, para in enumerate(q.strip() for q in
                               re.split(r'\n\s*\n', text) if q.strip()):
        for s in split(para):
            sentences.append({'id': len(sentences) + 1, 'text': s,
                              'para': pid + 1})

    selected = [s for s in sentences if s['id'] >= a.start]
    if a.limit:
        selected = selected[:a.limit]

    out = {'lang': lang, 'total': len(sentences), 'sentences': selected}
    js = json.dumps(out, ensure_ascii=False, indent=1)
    if a.out:
        with open(a.out, 'w', encoding='utf-8') as f:
            f.write(js)
        kept = '{}-{}'.format(selected[0]['id'], selected[-1]['id']) if selected else 'none'
        print('lang={} total={} kept sentences {} -> {}'.format(
            lang, len(sentences), kept, a.out))
    else:
        print(js)


if __name__ == '__main__':
    main()
