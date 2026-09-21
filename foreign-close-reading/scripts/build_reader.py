#!/usr/bin/env python3
"""Merge per-sentence annotations into the interactive reader template.

Usage:
  python3 build_reader.py --data data.json --out reader.html
                        [--template PATH] [--theme NAME] [--lang CODE]
                        [--merge OLD.json] [--max-kb N] [--single] [--minify]
                        [--strict]

data.json schema (see SKILL.md for the annotated version):
{
  "title": "Война и мир · Том первый",
  "subtitle": "Лев Толстой",             # optional
  "lang": "ru",                          # optional; see LANG_ALIASES below
  "theme": "sepia",                      # optional default theme
  "chapters": [{"title": "Chapter I", "start": 1}],   # optional; see below
  "sentences": [
    {
      "id": 1, "text": "...", "para": 1, "ch": 1, "translation": "...",
      "words":   [{"w": "word", "p": "phonetic", "m": "meaning", "n": "note"}],
      "grammar": [{"t": "point", "d": "explanation"}],
      "culture": [{"t": "topic", "d": "content"}]
    }
  ]
}
Only id/text/para are structurally required; the reader degrades gracefully
when translation or any annotation list is missing.

chapters drives the left-hand outline AND volume packing. Each entry is
{"title", "start"}; "start" is the id of the chapter's first sentence. Omit it
and the builder falls back to the per-sentence "ch" numbers from
split_sentences.py (titles then come out empty). Whole chapters are never cut
in half: an html larger than --max-kb is emitted as <name>-1.html, -2.html …

--merge OLD.json [OLD.json …] folds earlier batches into --data by sentence id
(new wins), so "继续读下一批" can keep appending to one data.json; several
concurrent chunk files can be merged at once (later files override earlier ones).
Chapter lists are merged the same way, keyed by "start".
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


def merge_chapters(old, new):
    """Fold two chapter lists into one, keyed by start id, ordered by start."""
    by_start = {}
    order = []
    for c in list(old) + list(new):
        if not isinstance(c, dict):
            continue
        key = str(c.get('start'))
        if key not in by_start:
            order.append(key)
        by_start[key] = c
    out = [by_start[k] for k in order]
    try:
        out.sort(key=lambda c: float(c['start']))
    except (TypeError, ValueError, KeyError):
        pass
    for i, c in enumerate(out, 1):
        c['index'] = i
    return out


def normalize_chapters(chapters, sentences):
    """Keep chapters whose start id really exists; fill in the leading gap."""
    ids = [s['id'] for s in sentences]
    if not ids:
        return []
    lo, hi = ids[0], ids[-1]
    known = set(str(i) for i in ids)
    kept = []
    for c in chapters or []:
        if not isinstance(c, dict):
            continue
        start = c.get('start')
        if start is None:
            continue
        if str(start) not in known:
            # 起点不在本书里（多半是合并了别的分卷）——就近吸附到下一句
            try:
                nxt = [i for i in ids if float(i) >= float(start)]
            except (TypeError, ValueError):
                nxt = []
            if not nxt:
                continue
            start = nxt[0]
        if not (float(lo) <= float(start) <= float(hi)):
            continue
        kept.append({'title': str(c.get('title') or ''), 'start': start})
    kept.sort(key=lambda c: float(c['start']))
    if not kept or str(kept[0]['start']) != str(lo):
        kept.insert(0, {'title': '', 'start': lo})
    dedup = []
    for c in kept:
        if dedup and str(dedup[-1]['start']) == str(c['start']):
            dedup[-1] = c
        else:
            dedup.append(c)
    for i, c in enumerate(dedup, 1):
        c['index'] = i
    return dedup


def chapter_of(ids, chapters):
    """sentence id -> chapter index (1-based), from chapter start boundaries."""
    starts = [float(c['start']) for c in chapters]
    out = {}
    for sid in ids:
        v = float(sid)
        ch = 1
        for i, st in enumerate(starts):
            if v >= st:
                ch = i + 1
            else:
                break
        out[str(sid)] = ch
    return out


def compact(obj):
    """Same serialisation the template embeds, so size estimates are honest."""
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')


def split_volumes(data, chapters, template, title, limit):
    """Greedy: whole chapters per volume, each volume ≤ limit bytes.

    「以章回为单位向下取整」= 一卷在装得下的最后一章处收尾，绝不把一章劈开。
    单独一章就超过上限时无处可退，只能让它独占一卷并告警（见 main）。"""
    sentences = data['sentences']
    if not chapters or limit <= 0:
        return [{'chapters': list(chapters or []), 'sentences': sentences}]
    ids = [s['id'] for s in sentences]
    ch_of = chapter_of(ids, chapters)
    groups = [(c, []) for c in chapters]
    pos = dict((c['index'], i) for i, (c, _) in enumerate(groups))
    for s in sentences:
        groups[pos[ch_of[str(s['id'])]]][1].append(s)

    def render(chs, sents):
        d = dict(data)
        d['sentences'] = sents
        if chs:
            d['chapters'] = chs
        else:
            d.pop('chapters', None)
        return size_of(d, template, title)

    volumes, cur_chs, cur_sents = [], [], []
    for c, sents in groups:
        if cur_chs and render(cur_chs + [c], cur_sents + sents) > limit:
            volumes.append({'chapters': cur_chs, 'sentences': cur_sents})
            cur_chs, cur_sents = [], []
        cur_chs.append(c)
        cur_sents.extend(sents)
    if cur_chs or cur_sents:
        volumes.append({'chapters': cur_chs, 'sentences': cur_sents})

    # 贪心装进来的卷若仍是超限（估算与最终渲染有出入），把尾章退给下一卷再审，
    # 直到每卷都真的装得下，或退化成一章一卷（那时已无处可退）
    i = 0
    while i < len(volumes):
        v = volumes[i]
        if len(v['chapters']) > 1 and render(v['chapters'], v['sentences']) > limit:
            moved_ch = v['chapters'].pop()
            idx = moved_ch['index']
            moved = [s for s in v['sentences'] if ch_of[str(s['id'])] == idx]
            v['sentences'] = [s for s in v['sentences']
                              if ch_of[str(s['id'])] != idx]
            volumes.insert(i + 1, {'chapters': [moved_ch], 'sentences': moved})
        else:
            i += 1
    return volumes


def chapters_from_ch(sentences):
    """没有 chapters 只有每句的 ch 时，退化成按章号切边界（标题留空）。"""
    out = []
    for s in sentences:
        ch = s.get('ch')
        if ch in (None, '', 0, '0'):
            continue
        if not out or str(out[-1].get('_ch')) != str(ch):
            out.append({'title': '', 'start': s['id'], '_ch': ch})
    for c in out:
        c.pop('_ch', None)
    return out


def render_html(tpl, data, title):
    t = (str(title).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
    return tpl.replace('__TITLE__', t).replace('__DATA__', compact(data))


def size_of(data, tpl, title):
    return len(render_html(tpl, data, title).encode('utf-8'))


BLOCK_COMMENT = re.compile(r'/\*.*?\*/', re.S)


def minify(html):
    """保守压缩：只做绝不可能改变语义的三件事——去掉块注释、行首缩进和空行。

    不做 JS/CSS 的激进压缩（`//` 注释一删就会毁掉 URL 和正则），
    省下的这点体积不值得拿阅读器的正确性去赌。"""
    html = BLOCK_COMMENT.sub('', html)
    lines = [ln.strip() for ln in html.split('\n')]
    return '\n'.join(ln for ln in lines if ln)


def vol_name(out, i, n):
    if n <= 1:
        return out
    stem, ext = os.path.splitext(out)
    return '%s-%d%s' % (stem, i, ext)


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
    ap.add_argument('--max-kb', type=int, default=500, metavar='N',
                    help='单个阅读器 html 的体积上限，默认 500（KB）。超出时按章回'
                         '向下取整拆成多个分卷，同一章绝不跨卷；0 = 不限制、只出一个文件')
    ap.add_argument('--single', action='store_true',
                    help='强制只输出一个 html（忽略 --max-kb，超限只警告）')
    ap.add_argument('--minify', action='store_true',
                    help='保守压缩模板（去块注释/缩进/空行），体积再降一点')
    ap.add_argument('--strict', action='store_true',
                    help='fail when a sentence has no translation or no annotations')
    a = ap.parse_args()

    data = load_json(a.data)
    if not isinstance(data, dict):
        fail('data.json must be a JSON object')
    olds = []
    if a.merge:
        for path in a.merge:
            old = load_json(path)
            if not isinstance(old, dict):
                fail('%s must be a JSON object' % path)
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
        # 章回清单同样折叠：--data 里写了的覆盖一切，没写就用切片带过来的
        if not data.get('chapters'):
            chs = []
            for old in olds:
                if isinstance(old.get('chapters'), list):
                    chs = merge_chapters(chs, old['chapters'])
            if chs:
                data['chapters'] = chs

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

    chapters = data.get('chapters')
    if not isinstance(chapters, list) or not chapters:
        chapters = chapters_from_ch(data['sentences'])
    chapters = normalize_chapters(chapters, data['sentences'])
    if chapters and any(c.get('title') for c in chapters):
        data['chapters'] = chapters
    else:
        data.pop('chapters', None)

    with open(a.template, encoding='utf-8') as f:
        tpl = f.read()
    if a.minify:
        tpl = minify(tpl)
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

    limit = 0 if a.single else max(0, a.max_kb) * 1024
    volumes = split_volumes(data, chapters, tpl, data['title'], limit)
    if limit:
        overs = [(i + 1, v, size_of(_vol_data(data, v), tpl, data['title']))
                 for i, v in enumerate(volumes)]
        for i, v, sz in overs:
            if sz <= limit:
                continue
            if len(chapters) <= 1:
                print('warning: %d KB > %d KB 上限，但全书只有 %d 个章回边界，'
                      '无法在章与章之间拆开——整本写进一个文件'
                      % (sz // 1024, a.max_kb, len(chapters)))
            else:
                first = v['chapters'][0] if v['chapters'] else {'index': '?', 'title': ''}
                print('warning: 第 %d 卷（第 %s 章「%s」）单独成卷仍 %d KB > %d KB 上限'
                      % (i, first['index'], first['title'] or '(无题)',
                         sz // 1024, a.max_kb))

    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    n_vol = len(volumes)
    written = []
    for i, v in enumerate(volumes, 1):
        vdata = _vol_data(data, v)
        if n_vol > 1:
            vdata['nav'] = {
                'index': i, 'total': n_vol,
                'prev': os.path.basename(vol_name(out, i - 1, n_vol)) if i > 1 else '',
                'next': os.path.basename(vol_name(out, i + 1, n_vol)) if i < n_vol else '',
            }
            vtitle = '%s（%d/%d）' % (data['title'], i, n_vol)
            vdata['vol_title'] = vtitle
        else:
            vtitle = data['title']
        html = render_html(tpl, vdata, vtitle)
        path = vol_name(out, i, n_vol)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)
        written.append((path, len(html.encode('utf-8')), len(v['sentences'])))

    for path, size, n in written:
        print('reader written: %s (%d sentences, %.0f KB)' % (path, n, size / 1024.0))
    print('total %d sentences, lang=%s%s%s, %d 卷' % (
        len(data['sentences']), data.get('lang') or 'auto',
        ', theme=' + data['theme'] if data.get('theme') else '',
        ', total=%d' % data['total'] if data.get('total') else '',
        n_vol))
    if chapters:
        head = ' · '.join('%d. %s' % (c['index'], c['title'] or '(无题)')
                          for c in chapters[:6])
        print('chapters (%d): %s%s' % (len(chapters), head,
                                       ' …' if len(chapters) > 6 else ''))


def _vol_data(data, vol):
    """一卷的 data：只带这一卷的句子与章回（章回清单按起点裁开）。"""
    d = dict(data)
    d['sentences'] = vol['sentences']
    chs = [c for c in vol['chapters']]
    for i, c in enumerate(chs, 1):
        c = dict(c)
        c['index'] = i
        chs[i - 1] = c
    if chs and vol['sentences']:
        chs[0]['start'] = vol['sentences'][0]['id']
    if chs:
        d['chapters'] = chs
    else:
        d.pop('chapters', None)
    return d



if __name__ == '__main__':
    main()
