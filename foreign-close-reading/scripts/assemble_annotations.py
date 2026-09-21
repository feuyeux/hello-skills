#!/usr/bin/env python3
"""把「id + 讲解字段」的批次文件组装成 data.json（text/para/ch 由切片原样注入）。

多实例并发生成时最常见的事故不是讲解质量，而是实例把 text/para 手打了一遍：
丢重音、丢引号、id 漂移。用本脚本让实例**只写讲解字段**——

    {"id": 123, "translation": "…", "words": […], "grammar": […],
     "culture": […], "native": […]}

切片（sentences-K.json）里的 text / para / ch 永远原样注入，原文不可能被改坏。
批次文件可以乱序、可缺可补：同一个 id 后写入的文件覆盖先写入的（按文件名排序），
所以断点续跑就是「把缺的句子再写一个批次文件丢进来，重跑本脚本」。

用法：
  python3 scripts/assemble_annotations.py \\
      --sentences sentences-3.json --annots 'annots-3.b*.json' \\
      --out data-3.json --title '书名' --subtitle '作者' --lang fr

随后照常：check_data.py --data data-3.json --sentences sentences-3.json
（必须跑到 0 error），全部实例完成后用 build_reader.py --merge 合并。
"""

import argparse
import glob
import json
import os
import sys

FIELDS = ('translation', 'words', 'grammar', 'culture', 'native')


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sentences', required=True, help='该实例的 sentences-K.json 切片')
    ap.add_argument('--annots', required=True, help='批次文件 glob，如 annots-3.b*.json')
    ap.add_argument('--out', required=True, help='输出的 data-K.json')
    ap.add_argument('--title', required=True)
    ap.add_argument('--subtitle', default='')
    ap.add_argument('--lang', required=True, help='ru / fr / ja / ko / en / …')
    ap.add_argument('--theme', default='sepia')
    a = ap.parse_args()

    try:
        sl = load(a.sentences)
    except Exception as e:
        sys.exit('assemble_annotations: cannot read %s: %s' % (a.sentences, e))
    sentences = sl.get('sentences')
    if not sentences:
        sys.exit('assemble_annotations: %s has no sentences' % a.sentences)
    by_id = {str(s['id']): s for s in sentences}

    files = sorted(glob.glob(a.annots))
    if not files:
        sys.exit('assemble_annotations: no files match %s' % a.annots)

    ann, bad = {}, []
    for path in files:
        name = os.path.basename(path)
        try:
            items = load(path)
        except Exception as e:
            sys.exit('assemble_annotations: cannot read %s: %s' % (name, e))
        if isinstance(items, dict):      # 允许 {"id": {...}} 的映射写法
            items = [dict(v, id=k) for k, v in items.items()]
        if not isinstance(items, list):
            sys.exit('assemble_annotations: %s is not a JSON array of id-entries' % name)
        for item in items:
            i = str(item.get('id'))
            if i not in by_id:
                bad.append('%s: unknown id %r (not in %s)'
                           % (name, item.get('id'), os.path.basename(a.sentences)))
                continue
            if not str(item.get('translation') or '').strip():
                bad.append('%s: id %r has no translation' % (name, item.get('id')))
                continue
            if i in ann:
                print('note: id %s redefined by %s (later file wins)' % (i, name))
            ann[i] = {k: item[k] for k in FIELDS
                      if item.get(k) not in (None, '', [], {})}

    if bad:
        for line in bad[:20]:
            print('ERROR ' + line)
        sys.exit('assemble_annotations: %d bad entr(y/ies), nothing written' % len(bad))

    missing = [s['id'] for s in sentences if str(s['id']) not in ann]
    if missing:
        tail = ' …' if len(missing) > 10 else ''
        sys.exit('assemble_annotations: %d sentence(s) still unannotated '
                 '(write another batch and rerun): %s%s'
                 % (len(missing), missing[:10], tail))

    out = {'title': a.title, 'subtitle': a.subtitle, 'lang': a.lang,
           'theme': a.theme, 'sentences': []}
    if sl.get('chapters'):
        out['chapters'] = sl['chapters']
    for s in sentences:
        item = dict(ann[str(s['id'])])
        item['id'], item['text'], item['para'] = s['id'], s['text'], s['para']
        if 'ch' in s:
            item['ch'] = s['ch']
        out['sentences'].append(item)
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    nw = sum(len(x.get('words') or []) for x in out['sentences'])
    ng = sum(len(x.get('grammar') or []) for x in out['sentences'])
    nc = sum(len(x.get('culture') or []) for x in out['sentences'])
    nn = sum(len(x.get('native') or []) for x in out['sentences'])
    print('OK %s: %d sentences from %d batch file(s) | '
          'words %d · grammar %d · culture %d · native %d'
          % (a.out, len(out['sentences']), len(files), nw, ng, nc, nn))
    print('next: python3 scripts/check_data.py --data %s --sentences %s'
          % (a.out, a.sentences))


if __name__ == '__main__':
    main()
