#!/usr/bin/env python3
"""Merge per-sentence annotations into the interactive reader template.

Usage:
  python3 build_reader.py --data data.json --out reader.html
                        [--template PATH] [--theme NAME] [--lang CODE]
                        [--merge OLD.json] [--strict]

data.json schema (see SKILL.md for the annotated version):
{
  "title": "Война и мир · Том первый",
  "subtitle": "Лев Толстой",             # optional
  "lang": "ru",                          # optional; see LANG_ALIASES below
  "theme": "sepia",                      # optional default theme
  "sentences": [
    {
      "id": 1, "text": "...", "para": 1, "translation": "...",
      "words":   [{"w": "word", "p": "phonetic", "m": "meaning", "n": "note"}],
      "grammar": [{"t": "point", "d": "explanation"}],
      "culture": [{"t": "topic", "d": "content"}]
    }
  ]
}
Only id/text/para are structurally required; the reader degrades gracefully
when translation or any annotation list is missing.

--merge OLD.json [OLD.json …] folds earlier batches into --data by sentence id
(new wins), so "继续读下一批" can keep appending to one data.json; several
concurrent chunk files can be merged at once (later files override earlier ones).
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.join(HERE, '..', 'assets', 'reader_template.html')

# 语言代码 -> 模板使用的排版族：latn / cyrl / cjk / jpn / kor / rtl
LAYOUT_BY_LANG = {
    # 西里尔
    'ru': 'cyrl', 'uk': 'cyrl', 'be': 'cyrl', 'bg': 'cyrl', 'sr': 'cyrl',
    'mk': 'cyrl', 'kk': 'cyrl', 'russian': 'cyrl', '俄语': 'cyrl', '俄文': 'cyrl',
    # 日 / 韩 / 中
    'ja': 'jpn', 'jp': 'jpn', 'jpn': 'jpn', 'japanese': 'jpn',
    '日本語': 'jpn', '日语': 'jpn', '日文': 'jpn',
    'ko': 'kor', 'kr': 'kor', 'kor': 'kor', 'korean': 'kor',
    '한국어': 'kor', '韩语': 'kor', '韩文': 'kor',
    'zh': 'cjk', 'cn': 'cjk', 'cjk': 'cjk', 'chinese': 'cjk',
    '中文': 'cjk', '汉语': 'cjk',
    # 拉丁
    'en': 'latn', 'eng': 'latn', 'english': 'latn', 'latin': 'latn', 'latn': 'latn',
    'fr': 'latn', 'french': 'latn', 'français': 'latn', '法语': 'latn',
    'de': 'latn', 'german': 'latn', 'deutsch': 'latn', '德语': 'latn',
    'es': 'latn', 'spanish': 'latn', 'español': 'latn',
    'it': 'latn', 'italian': 'latn', 'italiano': 'latn',
    'pt': 'latn', 'portuguese': 'latn',
    'nl': 'latn', 'sv': 'latn', 'no': 'latn', 'da': 'latn', 'fi': 'latn',
    'pl': 'latn', 'cs': 'latn', 'sk': 'latn', 'hu': 'latn', 'ro': 'latn',
    'tr': 'latn', 'vi': 'latn', 'id': 'latn', 'ms': 'latn', 'la': 'latn',
    'el': 'cyrl',
    # 从右往左
    'ar': 'rtl', 'he': 'rtl', 'fa': 'rtl', 'ur': 'rtl',
}
THEMES = ('paper', 'ink', 'sepia', 'mist', 'night', 'forest', 'rose',
          'slate', 'solar', 'contrast')


def fail(msg):
    sys.exit('build_reader: ' + msg)


def norm_lang(value):
    """Return the layout family for a user-supplied language code."""
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if s in LAYOUT_BY_LANG:
        return LAYOUT_BY_LANG[s]
    if s in ('latn', 'cyrl', 'cjk', 'jpn', 'kor', 'rtl'):
        return s
    # 拼错的语言码静默给出拉丁排版，比报错更难发现——明说一声
    print('warning: unknown language code %r — falling back to latin typography' % value)
    return 'latn'


def load_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        fail('no such file: %s' % path)
    except UnicodeDecodeError as e:
        fail('%s is not UTF-8 (%s) — re-save it as UTF-8' % (path, e.reason))
    except json.JSONDecodeError as e:
        fail('%s is not valid JSON: %s (line %d, column %d)'
             % (path, e.msg, e.lineno, e.colno))


def merge_sentences(old, new):
    """Fold two sentence lists into one, keyed by id, ordered by id."""
    by_id = {}
    order = []
    for s in list(old) + list(new):
        key = str(s.get('id'))
        if key not in by_id:
            order.append(key)
        by_id[key] = s
    return [by_id[k] for k in order]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--template', default=DEFAULT_TEMPLATE)
    ap.add_argument('--theme', choices=THEMES,
                    help='default theme when the reader has no saved preference')
    ap.add_argument('--lang', help='override data.json lang (ru/fr/ja/ko/en/zh/...)')
    ap.add_argument('--merge', nargs='+', metavar='OLD',
                    help='merge these earlier data.json files in, keyed by sentence id; '
                         'files listed later override earlier ones, and --data overrides all')
    ap.add_argument('--total', type=int, metavar='N',
                    help='全书总句数（split 输出的 total）。增量生成时传它：'
                         '阅读器会显示「已覆盖 X/N 句」并在结尾提示继续')
    ap.add_argument('--strict', action='store_true',
                    help='fail when a sentence has no translation or no annotations')
    a = ap.parse_args()

    data = load_json(a.data)
    if not isinstance(data, dict):
        fail('data.json must be a JSON object')
    if a.merge:
        olds = []
        for path in a.merge:
            old = load_json(path)
            if (old.get('title') and data.get('title')
                    and str(data['title']) != str(old['title'])):
                # 阅读进度按 title 存在浏览器 localStorage 里，标题一变已读进度就不带了
                print('warning: title %r differs from merged file %r — '
                      'saved reading progress will NOT carry over'
                      % (data['title'], old['title']))
            olds.append(old)
        # 并发切片合并：--merge 按列出顺序折叠（后者覆盖前者），--data 最后折入（覆盖一切）。
        # 正常切片互不重叠，顺序只决定冲突时谁赢。
        combined = []
        for old in olds:
            if isinstance(old.get('sentences'), list):
                combined = merge_sentences(combined, old['sentences'])
        data['sentences'] = merge_sentences(combined, data.get('sentences') or [])
        # data 本体没写的元数据，从被合并文件里继承（total 让增量阅读器知道书还没做完）
        for k in ('title', 'subtitle', 'lang', 'theme', 'total'):
            if not data.get(k):
                for old in olds:
                    if old.get(k):
                        data[k] = old[k]
                        break

    if not isinstance(data.get('sentences'), list) or not data['sentences']:
        fail('data.json needs a non-empty "sentences" list')
    if not data.get('title'):
        fail('data.json needs a "title"')

    # 只在 id 全是数字时排序；混入字符串 id 时保持原有顺序，免得把正文打乱
    if all(isinstance(x.get('id'), (int, float)) and not isinstance(x.get('id'), bool)
           for x in data['sentences'] if isinstance(x, dict)):
        data['sentences'].sort(key=lambda x: x['id'])

    seen_ids = set()
    for i, s in enumerate(data['sentences']):
        if not isinstance(s, dict):
            fail('sentences[%d] must be an object' % i)
        for k in ('id', 'text', 'para'):
            if k not in s:
                fail('sentences[%d] is missing "%s"' % (i, k))
        if not str(s['text']).strip():
            fail('sentences[%d] (id=%s) has empty text' % (i, s.get('id')))
        key = str(s['id'])
        if key in seen_ids:
            fail('duplicate sentence id %s' % key)
        seen_ids.add(key)
        for k in ('words', 'grammar', 'culture', 'native'):
            if k not in s or s[k] is None:
                continue
            # grammar / culture / native 允许整段写成一句话；words 必须是词条集合
            ok = (str,) if k in ('grammar', 'culture', 'native') else ()
            if not isinstance(s[k], (list, dict) + ok):
                fail('sentences[%d].%s must be a list%s or object'
                     % (i, k, ' of strings' if ok else ''))
        if a.strict and not str(s.get('translation') or '').strip():
            fail('sentences[%d] (id=%s) has no translation (--strict)' % (i, s.get('id')))

    if a.lang:
        data['lang'] = norm_lang(a.lang)
    elif data.get('lang'):
        data['lang'] = norm_lang(data['lang'])
    if a.theme:
        data['theme'] = a.theme
    elif data.get('theme') not in THEMES:
        data.pop('theme', None)
    if a.total:
        data['total'] = a.total

    with open(a.template, encoding='utf-8') as f:
        tpl = f.read()
    # 主题清单有三份（这里、模板 CSS、模板 JS），加主题要三处同步——对不齐就拒绝构建
    css_ids = set(re.findall(r'\[data-theme="([a-z0-9]+)"\]', tpl))
    js_ids = set(re.findall(r"\{\s*id:\s*'([a-z0-9]+)'", tpl))
    if css_ids != set(THEMES) or js_ids != set(THEMES):
        fail('THEMES and the template have drifted — '
             'build_reader=%s template-css=%s template-js=%s'
             % (sorted(THEMES), sorted(css_ids), sorted(js_ids)))
    for token in ('__DATA__', '__TITLE__'):
        if token not in tpl:
            fail('template is missing the %s placeholder' % token)

    js = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    # keep the inline JSON from prematurely closing its <script> tag
    js = js.replace('</', '<\\/')

    title = str(data['title']).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    html = tpl.replace('__TITLE__', title).replace('__DATA__', js)

    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print('reader written: %s (%d sentences, lang=%s%s%s)' % (
        out, len(data['sentences']), data.get('lang') or 'auto',
        ', theme=' + data['theme'] if data.get('theme') else '',
        ', total=%d' % data['total'] if data.get('total') else ''))


if __name__ == '__main__':
    main()
